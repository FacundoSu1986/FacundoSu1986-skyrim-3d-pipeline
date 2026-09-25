# Límites del motor de Skyrim

Índice:
- [Medir el vanilla primero](#medir-el-vanilla-primero)
- [Escala y ejes](#escala-y-ejes)
- [Presupuesto de polígonos](#presupuesto-de-polígonos)
- [Triángulos, no cuadriláteros](#triángulos-no-cuadriláteros)
- [Estructura del NIF](#estructura-del-nif)
- [Rig: huesos y particiones](#rig-huesos-y-particiones)
- [Texturas](#texturas)
- [Una textura por shape](#una-textura-por-shape-no-por-hueso)
- [Backface culling](#backface-culling)
- [Solo SE](#solo-se)

---

## Cómo leer las etiquetas

Casi todo el daño de este dominio viene de confundir tres cosas muy distintas.
Cada afirmación fuerte de esta referencia va etiquetada:

| Etiqueta | Qué significa | Qué hacer con ella |
|---|---|---|
| `[INVARIANT]` | Propiedad del formato o del motor. No cambia. | Tratala como ley. |
| `[PROVIDER]` | Comportamiento de un generador o de una herramienta, en una fecha dada. | **Comprobalo**: cambia entre versiones y planes. |
| `[OBSERVED]` | Algo medido en el proyecto de origen. Un caso, no una ley. | Usalo como expectativa, no como regla. |

El error caro es promover un `[OBSERVED]` a `[INVARIANT]`. Pasó dos veces en el
proyecto de origen y las dos veces produjo un bloqueo que no existía. Si vas a
escribir una regla, preguntate de cuál de las tres filas es.

## Medir el vanilla primero

Nada de esto se deduce de la documentación: se copia de archivos reales de
Bethesda. Antes de generar o modelar, extraé del BSA el asset que vas a
reemplazar y medilo.

Qué anotar:

- **Posiciones de hueso** del `skeleton.nif`, parseadas del binario con
  `scripts/nif_nodos.py`. No se las pidas a PyNifly (ver trampa 1).
- **La caja de cada pieza** de la malla: dónde empieza y termina en X, Y, Z.
  Es el molde que hay que llenar.
- **El juego de huesos de cada pieza**, para no perder articulaciones.
- **Las particiones de body-part** que usa.
- **El material**: tipo de shader, flags, rutas de textura, cubemap.

Con eso armás el pliego de proporciones para pedirle las partes a la IA 3D, y
el patrón contra el cual verificar lo que exportes.

## Escala y ejes

- **1 unidad de Skyrim ≈ 1,42 cm.** Un humano adulto mide unas 120 unidades;
  1 metro son unas **70 unidades**.
- **+Z es arriba. +Y es adelante. +X es a la derecha del mundo** — que es la
  **izquierda del personaje**, porque el personaje mira hacia +Y. Por eso el
  hueso `NPC L Thigh` está en X negativo.
- Blender es Z-up igual que Skyrim, así que no hay conversión de ejes… salvo
  que el importador de glTF **sí** rota de Y-up a Z-up y deja esa rotación en
  la matriz del objeto (trampa 2).

Convención práctica cómoda: modelar en unidades de juego directamente y
exportar con `blender_xf=False` en PyNifly, de modo que 1 unidad de Blender = 1
unidad de NIF. Evita un montón de errores de escala.

## Presupuesto de polígonos

Los generadores devuelven del orden de **400.000 a 600.000 triángulos por
pedido**. Hay que bajar eso dos órdenes de magnitud.

**Lo que usa el vanilla de verdad.** `[OBSERVED]` Censo de las 22.394 mallas
de Skyrim SE, contando solo las que tienen geometría:

| Clase | N | Mediana | p90 | Máximo |
|---|---|---|---|---|
| `actors` | 4.189 | **3.706** | 4.697 | 42.438 |
| `armor` | 1.380 | 998 | 3.729 | 14.146 |
| `clothes` | 904 | 856 | 3.100 | 15.161 |
| `clutter` | 1.744 | 515 | 2.246 | 22.866 |
| `dungeons` | 3.216 | 1.172 | 5.052 | 117.216 |
| `architecture` | 2.941 | 480 | 3.466 | 114.803 |
| **todo el corpus** | 21.926 | **944** | 4.344 | 117.216 |

El Steam Centurion son 6.007 triángulos: por encima de la mediana de actores,
nada excepcional. La mitad de las mallas del juego no llega a mil triángulos.

Esto recalibra la tabla de abajo hacia arriba: los presupuestos que siguen son
**varias veces** lo que gasta Bethesda. Es deliberado —las pantallas de hoy no
son las de 2011— pero si estás dudando si 20.000 es mucho para una criatura, la
respuesta medida es que es **cinco veces la mediana vanilla**.

Presupuestos razonables para un mod de calidad en SE:

| Caso | Triángulos | Comentario |
|---|---|---|
| Arma | 3.000–10.000 | se ve de cerca en primera persona |
| Armadura del jugador | 20.000–50.000 | se ve todo el tiempo |
| Criatura única / jefe | 20.000–60.000 | aparece de a una |
| Criatura que aparece en grupo | 8.000–20.000 | multiplicá por cuántas hay en pantalla |
| Clutter | 500–3.000 | hay cientos por celda |

Arriba de ~80.000 en un actor que puede aparecer varias veces, empieza a
notarse. El costo real no es el conteo en sí sino **draw calls y overdraw**:
muchas piezas chicas con alfa son más caras que una pieza grande sólida.

**El decimado por colapso preserva la silueta mucho mejor que pedir low-poly al
generador.** En el proyecto de origen, una cabeza pasó de 447.406 a 8.000
triángulos —el 1,8%— y es visualmente indistinguible del original. No tengas
miedo de decimar fuerte.

## Triángulos, no cuadriláteros

El NIF guarda **solo triángulos**. Los cuadriláteros y n-gonos de Blender se
triangulan al exportar.

Conviene **triangular explícitamente antes de exportar**, no dejárselo al
exportador: así el `.blend` queda igual a lo que sale en el archivo y lo que
verificás es lo que se carga. Si el generador ofrece salida en **quads**
(algunos tienen "quad remesh"), tomala: los quads decimalizan mejor y se
triangulan al final igual.

## Estructura del NIF

Skyrim SE usa versión `20.2.0.7`, user version 12, BS version 100.

Bloques que vas a ver en una malla skinneada:

**El nodo raíz.** `[OBSERVED]` `BSFadeNode` domina en estáticos y `NiNode` en
skinneados, pero **no es una regla**: de las 18.401 mallas con raíz
`BSFadeNode`, **3.633 (19,7 %) están skinneadas**, y 31 de las 3.019 con raíz
`NiNode` no lo están. Heredá la raíz del donante en vez de elegirla por tipo de
asset.

| Bloque | Qué es |
|---|---|
| `BSFadeNode` / `NiNode` | raíz y nodos de hueso |
| `BSTriShape` | la geometría. `NiTriShape` + `NiTriShapeData` es el formato de LE: ver "Solo SE" |
| `BSDismemberSkinInstance` | el skin, con las particiones de body-part |
| `NiSkinData` / `NiSkinPartition` | pesos y reparto en particiones |
| `BSLightingShaderProperty` | el material |
| `BSShaderTextureSet` | las rutas de textura |
| `NiAlphaProperty` | mezcla/test de alfa |
| `bhk*` | colisión (Havok) |

### Límites duros del formato

`[INVARIANT]` **65.535 vértices por shape.** Los índices de triángulo de
`BSTriShape` son enteros de 16 bits sin signo. Un shape más grande no se puede
representar: hay que partirlo en dos. Es un techo del formato, no una
recomendación de rendimiento.

`[OBSERVED]` En la práctica está lejísimos: sobre los 82.694 shapes del corpus
vanilla, el más denso tiene **36.138 vértices** —el 55 % del techo— y solo 21
shapes pasan de 20.000. O sea que solo lo tocás si intentás meter el modelo
generado **sin decimar**, que es justamente lo que no hay que hacer.

`[INVARIANT]` **Tangentes y bitangentes.** `BSLightingShaderProperty` las usa
para aplicar el normal map. Si el shape se exporta sin ellas, el normal se
aplica en un espacio equivocado: la iluminación queda plana o con costuras
marcadas en los bordes de isla de UV. PyNifly las calcula al exportar siempre
que la malla tenga UV; sin capa de UV no hay tangentes posibles. Es otra razón
para no perder las UV del GLB.

**No armes el NIF de cero: usá el vanilla como donante.** Importalo, cambiale
la geometría y heredá verbatim el material, las flags, el cubemap, las
particiones y las matrices de bind. Reconstruir eso a mano es inventar, y los
valores que se inventan mal no dan error: dan un asset que se ve raro.

## Rig: huesos y particiones

- **Máximo 4 huesos por vértice.** Más pesos se descartan silenciosamente.
- **Skin rígido.** `[OBSERVED]` El Steam Centurion **sí está skinneado** —tiene
  `BSDismemberSkinInstance`, `NiSkinData` y `NiSkinPartition` como cualquier
  malla animada— pero su skin es **rígido**: cada vértice pesa 1,0 a un solo
  hueso y cada pieza va entera a su hueso. No es lo mismo que "no estar
  skinneado": la estructura de skin hace falta igual; lo que no hace falta es el
  weight painting.

  `[OBSERVED]` Pero "rígido" es una aproximación, no un absoluto: censando el
  juego entero, **ningún actor tiene el 100 % de sus vértices con un solo
  hueso**. El `steamcenturion.nif` tiene 5.466 vértices de un hueso y **120 de
  dos** (97,9 % rígido). Contando también sus mallas de FX, baja a 86,5 %.

  La escala real, de menos a más mezcla:

  | Actor | Máx. huesos/vértice | Vértices con 1 solo |
  |---|---|---|
  | `atronachstorm` | 2 | 99,2 % |
  | `dwarvenspider` | 3 | 92,8 % |
  | `dwarvensteamcenturion` | 2 | 86,5 % |
  | `dwarvenspherecenturion` | 4 | 82,6 % |
  | `sabrecat` | 4 | 18,3 % |
  | `witchlight` | 4 | 12,7 % |

  Averiguá dónde cae el tuyo **antes de presupuestar**, mirando los pesos del
  vanilla. Los autómatas están cerca del extremo rígido y eso borra casi todo
  el weight painting; un felino o un dragón están en el otro extremo.
- **Particiones de body-part**: el skin se reparte en particiones identificadas
  por un número. Si la partición está mal, la pieza puede **no dibujarse**.
- `[INVARIANT]` **Cada triángulo pertenece a exactamente una partición.** Un
  triángulo en dos particiones se dibuja dos veces (z-fighting); uno en ninguna
  no se dibuja. Si partís un shape, repartí los triángulos, no los dupliques.
- **Flags de partición: no hay regla, copiá el vanilla.** Cada partición lleva
  `PF_EDITOR_VISIBLE` (1) y `PF_START_NET_BONESET` (256). `[OBSERVED]` Sobre
  las 30.468 particiones del corpus vanilla completo, solo existen cuatro
  combinaciones:

  | flags | particiones | % |
  |---|---|---|
  | 257 (las dos) | 15.423 | 50,6 % |
  | 1 (solo EDITOR_VISIBLE) | 13.726 | 45,1 % |
  | 256 (solo START_NET_BONESET) | 1.075 | 3,5 % |
  | 0 (ninguna) | 244 | 0,8 % |

  > Acá decía: "encendida en la primera partición de cada conjunto, apagada en
  > las demás". Medido sobre los archivos con más de una partición, ese patrón
  > es **989 archivos**, contra **475** que la encienden en todas y **3.777**
  > que mezclan. Mi regla práctica describía el 19 % de los casos. La escribí
  > porque sonaba a mecanismo, no porque la hubiera contado.

  Lo único que sobrevive a la medición: **copiá las flags del vanilla que
  reemplazás.** No hay patrón que se pueda deducir.

IDs de body-part más usados:

| ID | Parte |
|---|---|
| 30 | cabeza |
| 31 | pelo |
| 32 | cuerpo |
| 33 | manos |
| 34 | antebrazos |
| 37 | pies |
| 38 | pantorrillas |
| 39 | escudo |
| 40 | cola |
| 42 | diadema |
| 43 | orejas |

`[OBSERVED]` Los IDs de arriba son los de **ranura de armadura**. Las mallas de
**actor** usan otro rango, y en el corpus son los más frecuentes de todos:

| ID | Parte | Particiones |
|---|---|---|
| 131 | pelo | 6.607 |
| 130 | cabeza | 5.428 |
| 141 | pelo largo | 4.943 |
| 230 | cabeza + cuello | 4.074 |
| 143 | orejas | 3.184 |
| 32 | cuerpo | 2.112 |

Existen 31 IDs distintos en total. Si estás reemplazando una cabeza y copiás un
ID del rango 30-43, te equivocaste de tabla.

Copiá los que use el vanilla que reemplazás en vez de elegirlos.

## Texturas

**Formato:** DDS con mipmaps completos. Sin mipmaps, la textura titila a
distancia.

| Uso | Formato recomendado |
|---|---|
| Difuso (color) | BC7 sRGB |
| Normal, máscaras | BC7 lineal |

Herramienta: `texconv.exe` (de DirectXTex).

> **BC7 es lo que SE *admite*, no lo que Bethesda *usó*.** `[OBSERVED]` Censo
> completo de las **32.241** texturas del juego base: DXT5 55,2 %, sin comprimir
> 32bpp 31,2 %, DXT1 13,0 %, **BC7 0 %**. Ni un solo archivo. Las texturas de
> SE son en su mayoría las de LE recomprimidas. Usá BC7 para contenido nuevo
> porque es mejor, no porque sea "el formato de SE" — y no te sorprendas si un
> asset vanilla que abrís viene en DXT.
>
> **Los normales son DXT5, siempre.** `[OBSERVED]` 12.075 archivos `_n`, y
> **0 excepciones**. Es el patrón más limpio del corpus. Si estás por guardar un
> normal en BC5 "porque es lo correcto para normales", sepé que el juego entero
> hace otra cosa.
>
> **Y lo que parece descuido no lo es.** El 31 % sin comprimir son terreno
> (9.365 mapas de mezcla y LOD) y **normales en espacio de modelo** (`_msn`) de
> cabezas, que necesitan precisión que un formato de bloques destruye. No los
> comprimas por prolijidad.

**Sufijos y para qué sirve cada uno:**

| Sufijo | Qué es |
|---|---|
| *(ninguno)* | difuso / color base |
| `_n` | normal map |
| `_m` | **máscara de entorno** — cuánto refleja el cubemap |
| `_g` | glow map (emisivo) |
| `_s` | subsurface / tinte de piel |
| `_p` | parallax |
| `_b` | backlight |

**Dos cosas que sorprenden:**

1. **El alfa del normal map es la especularidad**, no la transparencia. Un
   normal con alfa en negro da un asset completamente mate.

   **Corrección (medido).** Este punto decía "ponelo en blanco si no sabés qué
   querés", y ese consejo es justo el que produce el defecto: el hacha de
   Tencent llegó al juego con el **99,7 %** de su máscara en blanco y se veía
   de plástico, con la malla y el color ya correctos. `[MEASURED]` Las **140**
   texturas `_n` de malla de arma del corpus están todas por debajo del
   **6,9 %** de bloques en blanco; en objetos portables la mediana es
   **0,00 %** y el p90 **0,34 %**.

   Blanco entero no es un default neutro: es "todo brilla al máximo". Si no
   sabés qué querés, sacala de la rugosidad del modelo PBR
   (brillo = 1 − rugosidad) y calibrala; lo comprueba
   `scripts/mascara_especular.py`. Las 59 texturas vanilla que **sí** están
   saturadas son materiales mate —ropa, comida, carbón— donde el brillo lo
   apaga `Specular Strength` del shader.
2. **La máscara `_m` no es metalicidad de PBR.** Controla cuánto se refleja el
   cubemap del shader `Environment_Map`. Al convertir de PBR, el canal de
   **metalicidad** del mapa ORM es la mejor fuente, pero conviene expandir el
   rango: los generadores devuelven metalicidad muy comprimida (en el proyecto
   de origen, 0 a 0,46 con media 0,06) y la máscara sale sin contraste.

**El difuso generado trae luz horneada.** `[PROVIDER]` Los generadores
texturizan a partir de imágenes iluminadas, así que el albedo llega con sombras
de contacto, oclusión ambiental y a veces un brillo especular pegado al color.
En Skyrim eso se multiplica con la iluminación de la celda: el asset se ve
sucio, con sombras que no se mueven cuando gira, y en una cueva oscura queda
negro. No tira ningún error, y es difícil de ver en el visor de Blender, que
suele mostrarlo con luz de estudio.

Cómo detectarlo: mirá el difuso **plano, sin luz**, y buscá degradados suaves
donde el material debería ser uniforme —debajo de un saliente, en el interior de
un pliegue—. Ésa es la sombra horneada.

Cómo mitigarlo: levantar el rango bajo con una curva que no toque los medios, y
bajar la saturación de las zonas más oscuras. No se recupera del todo; se
atenúa. Si el generador ofrece salida **PBR con albedo sin luz**, pedila.

**Resoluciones: el vanilla es mucho más chico de lo que la gente supone.**
`[OBSERVED]` Sobre las 32.241 texturas del juego base:

| Resolución | Archivos | % |
|---|---|---|
| 256² | 21.557 | 66,9 % |
| 512² | 4.753 | 14,7 % |
| 1024² | 2.305 | 7,1 % |
| 2048² | 1.680 | 5,2 % |
| ≥ 4096 en algún lado | **57** | **0,18 %** |

Mediana del lado mayor por clase: `terrain` 256, `actors` **512**, `clutter`
512, `architecture` 1024, `armor` 1024. El máximo de todo el juego es 8192, y
hay uno solo.

Dicho de otro modo: **la textura mediana de un actor de Skyrim es 512²**. Si
generás a 2048 o 4096 estás muy por encima del vanilla — legítimo en 2026, pero
que sea una decisión y no una suposición. El costo es VRAM en toda celda donde
el asset aparezca.

`[INVARIANT]` **Potencia de dos, sin excepción.** 0 de 32.241 texturas del
corpus tienen un lado que no lo sea.

`[OBSERVED]` **Las cadenas de mipmaps cortan en 2×2**, no en 1×1: 96,4 % del
corpus. Y solo 192 archivos (0,6 %) no tienen mipmaps — 188 son máscaras de
tinte y 4 son efectos de lente. Ninguna superficie que se vea a distancia.

## Una textura por SHAPE, no por hueso

`[INVARIANT]` Cada `BSTriShape` lleva **un** `BSShaderTextureSet`. Toda la
geometría que metas en un mismo shape comparte una sola textura.

`[INVARIANT]` **Shape y hueso son dimensiones independientes.** Dos shapes
distintos pueden estar pesados al mismo hueso y llevar texturas distintas. Esto
se comprueba en el propio Steam Centurion vanilla: `SteamLCalf` y `SteamLFoot`
son dos shapes separados y los dos pesan a `NPC Calf.L`. Y PyNifly escribe un
`BSShaderTextureSet` **por shape**, así que un NIF con 15 shapes sale con 15
texture sets aunque compartan huesos.

**Por qué importa.** Si generaste la cabeza y el torso por separado, cada uno
con su textura, y en el esqueleto vanilla los dos cuelgan del mismo hueso, NO
hace falta atlasear. Alcanza con dejarlos como **dos shapes** pesados a ese
hueso, cada uno con su material. El atlas solo hace falta si decidís
*fusionarlos* en un shape.

> Este párrafo decía lo contrario. La afirmación "dos partes en el mismo hueso
> comparten obligatoriamente una textura" era falsa, y en el proyecto de origen
> llevó a declarar un bloqueo que no existía. Es el error típico de este
> dominio: promover a ley del motor algo que solo era una propiedad del montaje
> propio. Cuando escribas una regla, preguntate si la verificaste contra el
> formato o solo la observaste en tu caso.

**Cuántos shapes usar.** El vanilla es una guía, no un contrato: el juego ata
la animación a los **huesos**, no al número de shapes. Podés partir un shape
vanilla en dos —por ejemplo para darle textura propia a la cabeza— siempre que
los dos queden pesados al hueso correcto. Lo que sí conviene conservar son los
**nombres de nodo** que otros archivos referencian (un NIF estático o un FX
pueden nombrarlos).

## Backface culling

Está **activo por defecto**. Una superficie de una sola cara no se dibuja desde
atrás.

**Medí antes de arreglar.** Es tentador asumir que todo modelo generado es una
cáscara abierta y aplicarle `Solidify` de entrada. No lo hagas: `Solidify`
**duplica el conteo de triángulos** y sobre una superficie irregular genera
geometría autointersectada. Contá las aristas de borde con `medir_parte.py`
—que las canonicaliza por posición, ver trampa 22— y decidí con el número:

| Aristas de borde | Qué es | Qué hacer |
|---|---|---|
| 0 | volumen cerrado | nada |
| unas decenas | agujeritos sueltos | taparlos (`holes_fill`), no solidificar |
| miles, del orden del conteo de triángulos | cáscara abierta de verdad | `Solidify` |

`[OBSERVED]` Un brazo de Tripo que parecía tener 55.528 aristas de borde tenía
**12**: el conteo estaba inflado por vértices partidos por isla de UV. Sobre ese
dato falso se le aplicó `Solidify` y el modelo terminó con el doble de
triángulos sin necesidad.

Cuando hace falta de verdad, dos arreglos en orden de preferencia:

1. **Darles espesor real** con `Solidify` (0,5–1,5 unidades de juego según la
   pieza). Arregla la causa y además tapa el interior hueco.
2. Marcar el shader como `DOUBLE_SIDED` en `Shader_Flags_2`. Tapa el síntoma:
   las caras se dibujan de los dos lados, pero se ven superficies interiores
   donde antes había un agujero y la iluminación queda rara. Tiene costo real:
   desactiva el culling para ese shape, o sea el doble de fragmentos.

## Solo SE

El proyecto apunta solo a **Special Edition**. LE (Legendary Edition, la de
2011) quedó obsoleta y no se soporta.

Lo único que queda de LE es reconocer un export que salió en su formato por
accidente: `bs_version` 83 en vez de 100, y `NiTriShape` + `NiTriShapeData` en
vez de `BSTriShape`. PyNifly lo hace aunque le pidas SE (trampa 33), y
`scripts/verificar_export.py` lo reprueba por la regla `version`. En el corpus
de SE es 1 archivo de 22.394 (`artrigpressureplate01.nif`): todo lo demás, y
todo lo que mide este repo, es BS 100.
