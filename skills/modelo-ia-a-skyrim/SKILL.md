---
name: modelo-ia-a-skyrim
description: Convierte modelos 3D generados por IA (Tripo, Meshy, Hunyuan3D, Rodin, Trellis) en assets funcionales de Skyrim SE o LE con Blender y PyNifly — malla, rig, texturas DDS y NIF verificado. Usala siempre que aparezca un .glb/.fbx/.obj generado por IA que haya que meter en Skyrim, cuando haya que reemplazar una criatura, armadura o arma vanilla, cuando haya que escribir el prompt para pedirle el modelo a la IA 3D, o cuando se hable de presupuesto de polígonos, exportar NIF, convertir texturas a DDS, riggear a un esqueleto vanilla, o por qué un asset sale invisible, de espaldas o deformado en el juego. También cuando alguien pregunte si un modelo generado por IA "sirve" para un juego.
---

# Modelos 3D de IA → assets de Skyrim

Los generadores de 3D por IA producen mallas con mucho detalle y texturas PBR
decentes en minutos. Pero producen **mallas de escultura**, no assets de juego:
cientos de miles de triángulos, cáscaras abiertas, vértices partidos, sin rig,
orientadas al revés y sin ninguna noción de las restricciones del motor.

El trabajo de esta skill es cerrar esa brecha, y su parte más valiosa no es el
pipeline sino la **lista de fallos silenciosos**: casi todo lo que sale mal acá
no tira ningún error. El asset se exporta "bien", se instala "bien", y recién
aparece el problema mirando el archivo generado o probando en el juego.

## Tres clases de afirmación, y por qué te importa

Esta skill mezcla inevitablemente tres cosas que se parecen y no son lo mismo.
Las referencias las etiquetan, y conviene que vos también lo hagas cuando le
reportes algo a alguien:

| Etiqueta | Qué es | Vida útil |
|---|---|---|
| `[INVARIANT]` | Propiedad del formato NIF o del motor | permanente |
| `[PROVIDER]` | Cómo se comporta hoy un generador o PyNifly | caduca rápido |
| `[OBSERVED]` | Algo medido una vez en el proyecto de origen | un caso, no una ley |

**El error caro de este dominio es promover un `[OBSERVED]` a `[INVARIANT]`.**
En el proyecto de origen pasó dos veces y las dos terminaron en un "esto no se
puede hacer" que era falso. El control práctico: si una regla tuya te lleva a
declarar un bloqueo, comprobala contra un archivo real de Bethesda antes de
anunciarlo. Un bloqueo inventado cuesta más que un bug.

## Antes de tocar nada: dos preguntas

**1. ¿Es un replacer o un asset nuevo?**

Un **replacer** (misma ruta, mismo nombre de archivo, mismos nombres de nodo
que el vanilla) hereda gratis animaciones, behavior de Havok, ragdoll y
killmoves. No necesita ESP ni Creation Kit. El precio es que **la silueta no se
elige**: las animaciones llevan los huesos a posiciones fijas y la malla tiene
que construirse alrededor de ellas.

Un **asset nuevo** (arma, armadura, clutter) es más libre pero necesita registro
en un plugin.

Para criaturas, el replacer casi siempre gana. Reapuntar animaciones es un
proyecto aparte.

**2. ¿Cuánto mide y dónde van sus articulaciones?**

Antes de pedirle nada a la IA 3D, medí el vanilla que vas a reemplazar. Esas
medidas son el pliego de condiciones. Ver `references/limites-skyrim.md`
(sección "Medir el vanilla primero").

## El flujo

1. **Medir el vanilla** — extraer del BSA la malla y el esqueleto, parsear las
   posiciones de hueso del binario, anotar la caja de cada pieza.
2. **Escribir el pedido a la IA 3D** — una parte por pedido, con proporciones.
   Ver `references/pedir-a-la-ia-3d.md`.
3. **Recibir y medir** — `scripts/medir_parte.py` dice qué llegó realmente:
   triángulos, UV, texturas, proporción, si es sólido o cáscara, si vienen
   varias figuras en el archivo.
4. **Preparar** — soldar, decimar al presupuesto, orientar si hace falta.
   `scripts/preparar_parte.py`. Y **comprobar que la malla no se abrió**:
   `scripts/salud_malla.py <antes> <despues>`. Soldar bien y no verificarlo
   después no alcanza — ver trampa 28.
5. **Montar** — cortar cada parte en su tramo, escalar a su hueco, espejar. Dar
   espesor **solo si la medición dice que es una cáscara abierta**: `Solidify`
   duplica los triángulos y no siempre hace falta.
6. **Riggear** — grupos de vértices por hueso, particiones de body-part.
7. **Texturas** — PBR → convención de Skyrim, a DDS con mipmaps.
8. **Exportar y verificar** — reimportar el archivo generado y compararlo
   contra el vanilla: `scripts/verificar_export.py <nuevo.nif> <vanilla.nif>`.
   Y si el NIF lo escribió un conversor propio, además
   `scripts/verificar_uv.py <origen.obj> <nuevo.nif>`: el NIF guarda la V al
   revés que el OBJ y copiarla tal cual espeja toda la textura (trampa 29).

## Las tres cosas que hay que pedirle a la IA 3D

Estas tres están en `references/pedir-a-la-ia-3d.md` con plantillas completas,
pero si solo te acordás de tres cosas que sean estas, porque cada una costó una
prueba en el juego:

- **`solid closed volume, not flat sheets`** — los generadores tienden a
  devolver cáscaras de una cara. Skyrim tiene backface culling por defecto: una
  cáscara no se dibuja desde atrás y el asset sale con partes invisibles y
  huecas. Que venga cerrado de origen te ahorra un `Solidify`, que cuesta el
  doble de triángulos.
- **`front facing`** — en Skyrim el frente es **+Y**, y varios generadores
  devuelven el modelo mirando a −Y. Sirve sobre todo para que todas las partes
  vengan orientadas **igual entre sí**. No garantiza nada: **medí la orientación
  al recibir**, y girá solo si hace falta. Girar por costumbre un modelo que
  vino bien produce el mismo síntoma que no girar el que vino mal.
- **Una parte por pedido, una vista por ranura** — pegar frente/perfil/dorso en
  **una sola imagen** hace que el generador devuelva **tres modelos separados**
  parados uno al lado del otro. Si tu generador tiene entradas multivista
  separadas (varios las tienen hoy), usalas: eso sí ayuda, y mucho, con la
  profundidad.

## Verificar sobre el archivo, no sobre la escena

Esta es la disciplina que más veces salvó el proyecto de origen, así que vale
explicar por qué.

Entre la escena de Blender y el archivo que carga el juego hay un exportador, y
ese exportador puede perder o deformar cosas sin avisar. Verificar la escena en
memoria confirma lo que vos armaste, no lo que se va a cargar. **El último paso
siempre reimporta el NIF generado** y lo compara contra el vanilla:

- mismos tipos y cantidades de bloque, misma tabla de strings;
- las posiciones de hueso contra el `skeleton.nif` — desvío esperado 0,0;
- **dónde quedó cada pieza**, que es lo que se rompe cuando el exportador
  desarma el modelo;
- cada pieza con el mismo juego de huesos que su equivalente vanilla, más su
  partición, su UV y su capa de color;
- cada hueso dentro de la caja de la pieza que lo usa.

Ese último control encontró un NIF completamente desarmado —las piezas
desplazadas una por una— que visualmente ya se daba por bueno. Sin él se habría
instalado.

**Pero el cuarto de esa lista no es una regla absoluta, y medirlo lo demostró.**
De 27.927 piezas skinneadas del corpus vanilla, solo el **24,1 %** tiene todos
sus huesos dentro de su propia caja; de 114.751 pares (pieza, hueso), el
**64,8 %**. Escrito en forma absoluta, ese control reprobaría a tres de cada
cuatro mallas de Bethesda. Lo que sirve es su forma **relativa** —que la
distancia del hueso a la caja no crezca respecto del original—, y eso exige la
geometría de la pieza: la compara `fixtures/comparar.py --fiel`. Ver la entrada
22 de `census/hallazgos.md`.

**De los otros, `scripts/verificar_export.py` hace la mayor parte, no todo.**
Lee los bytes y no abre Blender. Compara bloques, tipo de raíz, nombres y
posiciones de nodo, nombres y **colocación** de cada pieza, y sus huesos,
particiones y tipo de skin instance. Lo que **no** hace, y conviene saberlo
antes de darlo por cubierto:

| del control | lo cubre |
|---|---|
| tabla de strings completa | **no** — solo los nombres de nodo y de pieza |
| UV y capa de color por pieza | **no** — están en la geometría, que no lee |
| desvío exactamente 0,0 | **no** — usa 0,01, que es el redondeo del lector; el propio vanilla difiere en 0,010 en 4 de 2.112 comparaciones |
| hueso dentro de la caja | **no**, y a propósito: ver arriba |

Para lo que falta: `fixtures/comparar.py --fiel` compara la colocación contra
un original con la geometría en la mano. **No se empaqueta con la skill**:
vive en el repo.

**Y un chequeo tiene que poder fallar.** Si un control pasa siempre, no prueba
nada. Alimentalo a propósito con datos equivocados (por ejemplo, las posiciones
de un esqueleto humano en vez del de la criatura) y confirmá que revienta. En
el proyecto de origen esa falsificación dio 7 fallos de 16 huesos comparables —
recién ahí el `[ok]` valió algo.

## Enumerar en vez de recordar

Cuando una criatura vanilla reparte una malla entre varios huesos, perder uno
de esos huesos **no da error**: simplemente se pierde articulación. Sin el hueso
del dedo el pie no rueda al caminar; sin los párpados la cara queda muerta.

No confíes en revisar las piezas que te acordás que tenían varios huesos.
Compará **las de todas**: para cada pieza, el juego de huesos de la nueva contra
el de la vanilla, y fallá si falta alguno. Así el control también atrapa la
pieza que mañana pierda una atadura.

## Archivos de referencia

- **`references/pedir-a-la-ia-3d.md`** — cómo escribir el pedido: plantillas por
  tipo de asset, negative prompts, qué formato descargar, cómo expresar
  proporciones. Leelo antes de escribir cualquier prompt para Tripo/Meshy.
- **`references/limites-skyrim.md`** — presupuestos de polígonos reales, formatos
  de textura, estructura del NIF, escala y ejes, límites de huesos y
  particiones. Leelo antes de decidir presupuestos o tocar el export.
- **`references/trampas.md`** — veintitrés fallos que no tiran error, con el
  síntoma y el arreglo, más un índice por síntoma al principio. **Leelo entero
  antes de empezar**, no cuando algo falle: la mitad de estas trampas se
  descubren recién probando en el juego, y para entonces ya perdiste la
  iteración. Cuando algo falle, volvé al índice por síntoma.

## Scripts

- **`scripts/nif_nodos.py`** — parser binario de la jerarquía `NiNode`. Da las
  posiciones de hueso **del archivo**, sin intermediarios.

  Hace falta porque PyNifly, al importar, puede sustituir un esqueleto de
  referencia y devolver posiciones que no son las del archivo, sin avisar. La
  vía soportada para evitarlo es pasarle el esqueleto correcto al importar
  (`reference_skel`, o la opción equivalente de tu versión) — hacelo. Pero
  seguí usando este parser como **verificador independiente**: un verificador
  que depende de la misma herramienta que estás verificando no verifica nada.
- **`scripts/censo_nif.py`** — parser de cabecera NIF en Python puro, para medir
  el corpus vanilla entero en vez de dos o tres archivos. Trae su propia suite
  de falsificación (`--autotest`) con valores medidos de antemano: si no los
  reproduce, avisa que no está listo para censar.

  Documenta un hallazgo que cambia cualquier censo: **en SSE un `BSTriShape`
  skinneado tiene `numTriangles = 0`** — la geometría está en el
  `NiSkinPartition`. Contar triángulos de la forma obvia da cero para toda
  criatura y toda armadura.
- **`scripts/verificar_export.py`** — el paso 8b: compara el NIF exportado
  contra el vanilla y **devuelve exit 1 si no pasa**. Diez reglas — nombres
  comparables, bloques, tipo de raíz, juego de nodos, posición y escala de
  cada nodo, juego de piezas, **dónde quedó cada pieza**, y sus huesos,
  particiones y tipo de skin instance. No abre Blender: lee los bytes, porque
  el exportador es justo lo que está bajo sospecha.

  **Exit 1 también cuando no comparó nada.** Un NIF de 73 bytes —solo
  cabecera— parsea sin dar error, y un veredicto de 0 fallas sobre 0
  comparaciones no es un `[ok]`.

  Cada regla lleva atrás su medición del corpus, y las que el corpus refutó
  **no están**: ver arriba. La tolerancia de posición es **0,01 unidades**, que
  no es un umbral elegido sino el redondeo del lector — medido sobre 1.166
  pares `_0.nif`/`_1.nif` del mismo asset, 21.641 de 21.683 posiciones son
  idénticas y los 42 desacuerdos son todos `InvMarker`.

  **Y está falsificado**: `--falsificar <carpeta meshes>` corre cuatro casos
  vanilla reales. Ponerle a `childbody.nif` el esqueleto de `frostgiant2.nif`
  da 10 fallas sobre 10 huesos comparables (la menor, 57,34 u de desvío), y el
  de `werebear.nif` da 18 de 18. El cuarto caso es el que hace que los otros
  valgan: `manekin.nif` usa el **mismo** esqueleto humano y da **cero** fallas
  de posición, aunque falle por bloques y por piezas. Sin él, "revienta con el
  esqueleto equivocado" sería compatible con "revienta con cualquier cosa".
- **`scripts/medir_parte.py`** — mide un GLB/FBX/OBJ recién llegado: triángulos,
  UV, texturas, proporción, aristas de borde (canonicalizadas por posición),
  cuántos cuerpos sueltos trae. Correlo **siempre** antes de trabajar con un
  modelo nuevo, y **decidí con sus números**, no con lo que esperabas.
- **`scripts/render_referencia.py`** — renderiza un asset vanilla como
  referencia limpia para ControlNet: profundidad, arcilla y silueta, con
  encuadre compartido entre vistas. Es el primer paso de la técnica de "meter el
  estilo dentro de la imagen antes del 3D" (ver `pedir-a-la-ia-3d.md`).

  A diferencia de un render de comparación, no dibuja nada encima: una regla de
  proporciones arruina un ControlNet.
- **`scripts/preparar_parte.py`** — soldar, decimar a un presupuesto y, si se lo
  pedís con `--girar-180`, orientar. No gira por defecto a propósito: una
  rotación es destructiva y no debe dispararse por una heurística.
- **`scripts/proporciones_arma.py`** — mide largo, grosor, ancho y empuñadura
  de un arma **en coordenadas de mundo** y los compara contra el rango de su
  **clase** (medido sobre 199 armas vanilla en 9 clases). REGLA: caer dentro
  del `[min, max]` de la clase. OBSERVACIÓN: en qué percentil cae cada medida.

  El rango vanilla es **ancho**, así que esto es una red de seguridad y no una
  regla de gusto: el mango del hacha de Tencent medía 0,1124 del largo y el
  rango de su clase es [0,0369, 0,1854] — la regla **no lo marcaba**, aunque a
  ojo se veía grueso. El número que le pone palabras a "se ve grueso" es el
  percentil.

  `--censo <carpeta meshes/weapons>` regenera la tabla. Tiene que regenerarse
  con **este mismo** clasificador: la primera versión usó otro y la REGLA
  rechazaba el 6,36 % del corpus del que había salido.
- **`scripts/mascara_especular.py`** — el alfa del `_n` es la máscara
  especular, y saturada deja el asset de plástico (el hacha llegó al juego con
  el 99,7 % de su máscara en blanco). Lee el alfa **sin decodificar**: en
  DXT5/BC3, `alpha0 == alpha1` en un bloque significa alfa constante.

  REGLA **solo para armas** (`--arma`): como mucho 10 % de bloques en blanco;
  las 140 texturas `_n` de arma del corpus están por debajo del 6,9 %. Para el
  resto informa, porque 59 de 1.201 objetos portables vanilla la tienen
  saturada y son materiales mate —ropa, comida, carbón—, donde el brillo lo
  apaga el shader.

  Un `_n` en BC7 **no se puede medir** con este lector, y lo dice como límite
  de la herramienta en vez de darlo por bueno.
- **`scripts/verificar_uv.py`** — compara las UV del OBJ de origen contra las
  del NIF exportado y exige que la **V esté invertida**. Aparea por posición
  normalizada por la caja de cada lado, así que tolera la escala y la
  traslación que aplica un conversor, pero no una rotación — y si alguien la
  agrega, deja de aparear y reprueba por "nada que comparar", que es el modo de
  fallar correcto. Trae `--autotest`.
- **`scripts/salud_malla.py`** — mide si la malla se **rompió** al decimarla, y
  lo hace sobre el **archivo** (`.nif` o `.obj`), sin Blender. Con dos
  argumentos aplica la REGLA: el número de aristas de borde no puede aumentar.
  Con uno, informa. Trae `--autotest` (18 comprobaciones sobre figuras de
  respuesta conocida) y `--falsificar <carpeta>`, que rompe mallas vanilla de
  cuatro formas distintas y exige que el control las pesque.

  La regla es **relacional** y no "la malla tiene que estar cerrada", porque eso
  es falso: solo el 15,1 % de los shapes vanilla lo están. Todo lo demás
  —ratio tri/vert, piezas sueltas, no-manifold, winding— se informa como
  OBSERVACIÓN y no reprueba: no está medido sobre el corpus con la densidad que
  hace falta para bloquear.

## Cómo conviene trabajar

**Por partes, no el cuerpo entero.** Pedir un cuerpo completo y después
recortarlo en piezas obliga a inventar reglas de región ("todo lo que esté a más
de X y por encima de Z es el brazo"), y esas reglas fallan en silencio: dejan
piezas invadiendo a la vecina, o descartan geometría entera. Pedir una parte por
archivo convierte el problema en un plano de corte, que es exacto.

**Mostrá renders, no describas.** Después de cada paso que cambie la geometría,
renderizá y mirá. Muchas de las trampas de la lista son invisibles en los
números y evidentes en una imagen — y al revés: el modelo que "se veía bien"
tenía las piezas desplazadas.

**Numerá los pasos y dejá un reporte JSON por paso.** Cada script tiene que
poder reejecutarse solo. Cuando algo sale mal tres pasos más adelante, querés
poder rehacer solo ese paso.

**Antes de decir "esto no se puede", comprobalo contra un archivo real.** Es la
regla que más plata habría ahorrado en el proyecto de origen. Un bloqueo
anunciado manda a la otra persona a rediseñar, a gastar créditos o a abandonar;
si el bloqueo no existe, todo ese costo fue por una creencia tuya. Abrí el NIF
vanilla, contá los bloques, mirá los huesos, y recién ahí hablá.
