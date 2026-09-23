# Trampas: treinta y cinco fallos que no tiran error

Casi todas se pagaron en el proyecto de origen (`Centurion_Marfil_SE_v01`,
reemplazo del Dwarven Steam Centurion); de la 28 en adelante salieron de otros
assets, y cada una lo dice. **Ninguna tira excepción.** El pipeline
termina "bien", el archivo se escribe, el mod se instala, y el problema aparece
mirando el archivo generado o probando en el juego.

Leelas **antes** de empezar. Varias solo se descubren probando en el juego, y
para entonces ya perdiste la iteración.

Índice por síntoma. Buscá acá primero: casi todo síntoma raro de este pipeline
ya está en la lista.

| Síntoma | Trampa |
|---|---|
| **Orientación y posición** | |
| El bicho pelea de espaldas | [2](#2), [19](#19) |
| La vista "de frente" muestra la espalda | [19](#19), [27](#27) |
| El modelo entra acostado | [3](#3) |
| El modelo sale desarmado, cada pieza para su lado | [5](#5) |
| Después de agregar un giro, el reparto se desarma | [4](#4) |
| **Geometría** | |
| Partes invisibles, agujeros en el torso | [6](#6), [8](#8) |
| Partes oscuras sin patrón aparente | [8](#8) |
| Brazos o piezas duplicadas al espejar | [11](#11) |
| Falta una garra, un cuerno, un detalle de un solo lado | [11](#11) |
| Vienen tres modelos en un archivo | [9](#9) |
| El decimado no baja de cierto número | [7](#7) |
| Una pieza invade a la vecina | [20](#20) |
| Una pieza pierde geometría de golpe, sin error | [4](#4) |
| El conteo de aristas de borde es absurdamente alto | [22](#22) |
| El render sale como una lámina gris que tapa todo | [24](#24), [25](#25) |
| Filtraste algo y sigue apareciendo | [25](#25) |
| Afinaste una parte y quedó un cono o se torció donde cambia el grosor | [34](#34) |
| Achicar una pieza deformó lo que tiene pegado | [34](#34) |
| La criatura entra con las piezas desparramadas | [26](#26), [5](#5) |
| **Rig** | |
| Falta articulación (pie plano, cara muerta) | [12](#12) |
| Una pieza no se dibuja o no sigue al hueso | [13](#13) |
| El NIF sale con el doble de nodos que el vanilla | [14](#14) |
| La pieza espejada sale con los huesos de los dos lados | [15](#15) |
| La malla se deforma en las uniones entre particiones | [23](#23) |
| Proporciones de hueso disparatadas | [1](#1) |
| **Texturas** | |
| Textura en negro | [16](#16), [31](#31) |
| El metal sale negro en el atlas y el cuero bien | [31](#31) |
| Una isla de la textura muestra el color de otro material | [32](#32) |
| Bordes dentados en el horneado, sobre todo en el normal map | [35](#35) |
| Texturas desordenadas, varias piezas sobre el mismo pedazo | [17](#17) |
| El archivo no tiene texturas ni UV | [10](#10) |
| El asset se ve sucio, con sombras que no se mueven | [21](#21) |
| En una cueva queda negro | [21](#21) |
| `TypeError: slice indices must be integers` | [18](#18) |
| `context is incorrect` en Blender sin interfaz | [17](#17) |
| **Exportación** | |
| El NIF "de SE" sale con `NiTriShape` y `bs_version 83` | [33](#33) |
| El export dice `Export successful` y SE no lo carga | [33](#33) |

---

## Importación y orientación

### 1. PyNifly sustituye un esqueleto de referencia al importar {#1}

**Síntoma:** las posiciones de hueso que devuelve son las de un humano — hombro
en Z=106, spine2 en 91 — para una criatura de 305 unidades (4,4 m). Además
inyecta huesos `CME *` de XPMSSE que no existen en el archivo, y mezcla las dos
escalas en la misma armature.

**Por qué importa:** si construís la malla alrededor de esas posiciones, queda
mal armada y las animaciones la deforman.

**Arreglo:** parsear el binario. Usá `scripts/nif_nodos.py`. La cabecera del
NIF trae los tamaños de bloque, y un `NiNode` en SSE es
`name(u32) numExtraData(u32)+refs controller(i32) flags(u32) trans(3f) rot(9f)
escala(f) collision(i32) numChildren(u32)+refs`. Acumulando desde la raíz salen
las posiciones de mundo reales.

### 2. El modelo puede entrar mirando a −Y {#2}

**Síntoma:** en el juego la criatura camina hacia el jugador pero ataca en la
dirección contraria. "Golpea de espaldas."

`[PROVIDER]` Pasa seguido, pero **no es universal**: depende del generador, de
la imagen de referencia y de la corrida. No lo des por hecho.

**Cómo confirmarlo sin abrir el juego:** compará hacia dónde se proyecta el arma
o las garras. El Steam Centurion vanilla lleva el martillo a **Y=+140**; el
modelo generado tenía las garras en **Y=−42**. Un render de perfil bien
etiquetado (ojo con la trampa [19](#19)) también alcanza: mirá la cara, el pico
o los dedos del pie.

**Arreglo:** rotar 180° sobre Z, **solo si comprobaste que hace falta**. Una
rotación es destructiva: aplicada por costumbre sobre un modelo que venía bien
lo deja de espaldas, y el síntoma es idéntico. Por eso `preparar_parte.py` NO
gira por defecto y pide `--girar-180` explícito.

La heurística de "dónde hay más masa respecto del centro de la caja" es solo una
pista y se equivoca fácil: una cresta que barre hacia atrás corre la masa al lado
contrario de la cara.

**Cuándo:** si hay que girar, **al principio**, apenas importás. Si rotás después
de repartir la geometría en piezas, cada pieza cambia de lado y queda atada al
hueso opuesto (trampa [4](#4)).

### 3. El importador de glTF deja la rotación Y-up→Z-up en la matriz del objeto {#3}

**Síntoma:** medís en coordenadas de mundo, transformás los datos de la malla, y
el modelo termina acostado con la altura sobre Y.

**Por qué pasa:** glTF es Y-up y Blender Z-up. El importador no rota los
vértices: pone la rotación en `matrix_world`. Si medís con
`obj.matrix_world @ v.co` pero después aplicás tu transformación a `obj.data`
(espacio local), estás mezclando dos espacios.

**Arreglo:** hornear la matriz antes de medir nada.

```python
obj.data.transform(obj.matrix_world)
obj.matrix_world = Matrix.Identity(4)
```

### 4. Girar la figura invierte el signo de Y en todas tus reglas {#4}

**Síntoma:** después de agregar el giro de 180°, el reparto de geometría se
desarma. Una pieza pasó de 1.856 triángulos a 385 sin ningún error.

**Por qué pasa:** las coordenadas Y que mediste antes del giro apuntan al revés
después.

**Arreglo:** cuando agregues o cambies una rotación global, revisá **todas** las
constantes de posición aguas abajo. Y dejá un control que compare el resultado
contra el anterior: una pieza que pierde el 80% de su geometría tiene que
fallar, no seguir.

## Geometría

### 5. Cada shape importado trae su propia matriz de objeto {#5}

**Síntoma:** el modelo sale **desarmado**, con las piezas desplazadas una por
una, cada una para su lado.

**Por qué pasa:** PyNifly le da a cada shape importado una transformación propia
y guarda los vértices relativos a ella. En el Steam Centurion la mayoría estaban
en (0, 45.4, 157.8), pero la pantorrilla en Y=84,2 y el muslo en Y=35,8.
Copiarla sobre geometría que ya está en coordenadas de mundo desplaza cada pieza
por su cuenta.

**Arreglo:** del donante heredá el padre y las propiedades `pyn*`, pero **no la
matriz**.

### 6. Cáscaras abiertas + backface culling = invisible {#6}

**Síntoma:** brazos invisibles, agujeros en el torso, piezas que aparecen y
desaparecen según el ángulo de cámara.

**Cómo confirmarlo:** contá aristas de borde **canonicalizando por posición**
(ver trampa [22](#22): contar por índice infla el número una barbaridad). Una
malla cerrada da cero; unas decenas son agujeritos; miles del orden del conteo
de triángulos es una cáscara de verdad.

**Arreglo, según el número:** agujeritos se tapan (`holes_fill`); una cáscara de
verdad se soluciona con `Solidify` de espesor real (0,5–1,5 unidades de juego).
Marcar el shader `DOUBLE_SIDED` tapa el síntoma pero deja ver superficies
interiores.

**No solidifiques por las dudas.** `Solidify` duplica los triángulos y sobre una
superficie irregular genera geometría autointersectada. Si la malla ya es un
volumen cerrado, estás pagando el doble de presupuesto por nada — que es
exactamente lo que pasó en el proyecto de origen por culpa de la trampa 22.

**Y ojo con el diagnóstico.** "Se ve invisible" también lo produce la trampa
[8](#8) (normales al revés), que se arregla gratis. Contá normales antes de
agregar geometría.

### 7. El decimado se topa con un piso {#7}

**Síntoma:** pedís 2.500 triángulos y se queda en 16.453, seis veces el
presupuesto, sin ningún aviso.

**Por qué pasa:** los generadores exportan los vértices **partidos por isla de
UV**. El decimado por colapso necesita aristas compartidas para trabajar, y una
costura de UV es, para el decimador, un borde: no puede colapsar a través de
ella. Cada parche queda con un mínimo irreducible y la suma es el piso.

**Y el modelo no está roto.** Es la misma confusión de la trampa [22](#22), y
conviene ver los dos números juntos. `[OBSERVED]` Medido sobre un brazo de
Tripo:

| | Brazo | Pie |
|---|---|---|
| Componentes contadas **por índice** (lo que ve el decimador) | 592 | 755 |
| Componentes contadas **por posición** (el sólido real) | **1** | **2** |

O sea: una sola pieza maciza, cortada en cientos de parches por las costuras de
UV. No hay "cáscaras sueltas" que arreglar — hay que **coserlas**.

**Arreglo:** soldar antes de decimar (`remove_doubles` con distancia ~0,08% del
alto del modelo). Con eso los seis presupuestos del proyecto de origen dieron
exactos. Soldar también arregla las UV: Blender conserva las costuras como datos
por cara (*loop*), así que unir los vértices no rompe el mapeo.

### 8. Las normales vienen mezcladas {#8}

**Síntoma:** partes que se ven oscuras o directamente no se ven, sin patrón
aparente.

**Cómo confirmarlo:** contá cuántas caras apuntan hacia afuera del centro de su
pieza. Una pieza del proyecto tenía 37 al derecho contra **166 al revés**.

**Arreglo:** `recalc_face_normals` por pieza, después de cortar y antes de dar
espesor. Y al espejar geometría, invertir el orden de los vértices de cada cara
o las normales quedan al revés.

### 9. Una lámina de tres vistas produce tres modelos {#9}

**Síntoma:** el archivo mide más de ancho que de alto. Al renderizarlo aparecen
tres figuras paradas una al lado de la otra.

**Por qué pasa:** el generador interpreta la hoja de personaje (frente / perfil
/ dorso) como una escena con tres objetos.

**Arreglo:** pedir con **una sola vista**. Si ya lo tenés así, separá por
componentes sueltos y agrupá por posición en X; después quedate con una figura.

### 11. Los modelos de IA no son simétricos {#11}

**Síntoma:** el reparto de geometría sale bien de un lado y mal del otro. O
aparecen **brazos dobles** al espejar.

**Por qué pasa:** cada lado tiene coordenadas distintas. Peor: puede haber
detalles en un lado y no en el otro — en el proyecto de origen, **un solo brazo
tenía garras**.

**Arreglo:** quedarse con **una mitad y espejarla**. Dos precisiones que costaron
iteraciones:

- **No asumas que la buena es la izquierda.** Contá la geometría de cada mitad y
  conservá la que tenga más. En el proyecto la derecha tenía 8.109 vértices
  contra 6.612, y quedarse siempre con la izquierda **descartaba las garras
  enteras**.
- **El espejado se decide por el lado de la cáscara, no por el nombre de la
  pieza.** Espejar solo las piezas `*L*` deja sin gemelo a toda la geometría
  izquierda que va a una pieza **central**. Síntoma: el bicho sale con un solo
  aro de dos y medio pecho hueco.

### 20. Recortar un cuerpo entero con reglas de región falla en silencio {#20}

**Síntoma:** piezas que invaden a la vecina. La pieza del brazo iba de X=−77 a
X=−18 y de Z=160 a Z=298: brazo, más medio torso, más algo a la altura de la
cabeza.

**Por qué pasa:** "todo lo que esté a más de X y por encima de Z es el brazo" es
una heurística, y las heurísticas sobre geometría orgánica fallan en los bordes.

**Arreglo:** **pedir una parte por archivo.** Cortar un brazo a la altura del
codo es un plano, que es exacto. Si igual tenés que trocear un cuerpo entero,
cortá con `bisect_plane` sobre los triángulos en vez de clasificar cáscaras
enteras: descartar islas completas es lo que hace perder geometría entera.

## Rig

### 12. Perder un hueso es articulación perdida, y no da error {#12}

**Síntoma:** el pie no rueda al caminar y el paso se ve planchado. La cara queda
muerta.

**Por qué pasa:** varias piezas vanilla reparten su malla entre varios huesos.
El pie del Steam Centurion usa `Foot`, `Toe0` y `Calf`; el cuerpo usa `Spine2`,
`LowerJaw` y los dos párpados. Si tu pieza pesa solo al hueso principal, esos
huesos no mueven nada.

**Arreglo:** comparar, **para todas las piezas**, el juego de huesos de la nueva
contra el de la vanilla, y fallar si falta alguno. No revises solo las que te
acordás que tenían varios: el control tiene que atrapar también la pieza que
mañana pierda una atadura.

### 13. PyNifly renombra los huesos, y no de forma uniforme {#13}

**Síntoma:** la pieza sale sin skin. No se dibuja o no sigue al hueso.

**Por qué pasa:** `NPC L Calf [LClf]` queda `NPC Calf.L`, pero
`NPC L Foot [Ltft ]` **conserva los corchetes**, porque la tabla de renombre no
lo cubre. Un grupo de vértices que no coincida exactamente con lo que espera el
exportador deja la pieza suelta, sin aviso. En el proyecto de origen, **12 de 15
piezas** necesitaban corrección.

**Arreglo:** tomar las grafías del **archivo donante**, nunca de una lista
escrita a mano. Cruzalas con una forma canónica que colapse las dos escrituras:

```python
def canon(n):
    n = n.split(" [")[0].strip()
    if n.startswith("NPC ") and n.endswith(".L"): n = "NPC L " + n[4:-2]
    elif n.startswith("NPC ") and n.endswith(".R"): n = "NPC R " + n[4:-2]
    return n
```

### 14. PyNifly exporta los huesos inyectados {#14}

**Síntoma:** el NIF sale con 41 `NiNode` contra los 21 del vanilla, incluidos
huesos humanos (`NPC Spine1 [Spn1]`) que la criatura no tiene.

**Arreglo:** antes de exportar, podar la armature a los huesos que el skin
vanilla usa de verdad. En un NIF de malla los huesos son hijos planos de la
raíz, así que borrarlos no rompe ninguna jerarquía.

## Blender

### 15. Los nombres de grupo de vértices viajan con la malla copiada {#15}

**Síntoma:** al espejar, la pieza derecha sale con los huesos de los dos lados y
**dos particiones**.

**Por qué pasa:** en Blender 4.x, copiar la malla trae los grupos. Si además
agregás los del lado opuesto, quedan duplicados.

**Arreglo:** **renombrar** los grupos que la copia ya trae, no agregar otros
encima. Dejá el camino alternativo por si la versión de Blender cambia:

```python
if copia.vertex_groups:
    for g in copia.vertex_groups:
        g.name = lado_opuesto(g.name)
else:
    for g in original.vertex_groups:
        copia.vertex_groups.new(name=lado_opuesto(g.name))
```

### 17. `uv.pack_islands` y `uv.select_all` exigen un editor de UV abierto {#17}

**Síntoma:** en Blender sin interfaz (`-b`), fallan con
`context is incorrect`.

**Arreglo:** `smart_project` **no** lo necesita —trabaja sobre las caras
seleccionadas— pero le da el cuadro 0..1 entero a **cada objeto**, así que
varios objetos quedan superpuestos usando el mismo pedazo de atlas. Ése es el
síntoma de "texturas desordenadas" en el juego. Si necesitás un atlas
compartido, empaquetá a mano: repartí área de atlas proporcional al **área real
en 3D** de cada pieza (eso da densidad de téxel pareja), rotá cada isla a
horizontal y bajá el factor de llenado hasta que entre.

### 18. `img.pixels` no admite slice con paso {#18}

**Síntoma:** `TypeError: slice indices must be integers`.

**Arreglo:** volcar con `foreach_get` a un array de numpy.

```python
import numpy as np
a = np.empty(w * h * 4, dtype=np.float32)
img.pixels.foreach_get(a)
```

## Texturas

### 10. El FBX "convertido" no trae UV ni texturas {#10}

**Síntoma:** el modelo llega sin material. El archivo pesa 220 KB en vez de
13 MB.

**Arreglo:** descargar **GLB**. Volver a bajar la misma generación en otro
formato no gasta créditos.

### 16. Asignar el colorspace después de escribir los píxeles vacía la imagen {#16}

**Síntoma:** el PNG sale negro entero. Sin ningún error.

**Por qué pasa:** Blender invalida la imagen y la regenera desde
`generated_color`. Pasa incluso asignando el mismo valor que ya tenía.

**Arreglo:** fijar `img.colorspace_settings.name` **al crear** la imagen, antes
de `pixels.foreach_set`, y no volver a tocarlo. Para cambiarlo, guardar y
recargar desde disco.

### 21. El difuso generado trae la luz horneada {#21}

**Síntoma:** el asset se ve sucio en el juego, con sombras que **no se mueven**
cuando el bicho gira, y en una celda oscura queda casi negro. En Blender se veía
bien.

**Por qué pasa:** `[PROVIDER]` los generadores texturizan a partir de imágenes
iluminadas, así que el albedo llega con oclusión ambiental, sombras de contacto
y a veces un brillo especular pegado al color. Skyrim después multiplica eso por
la iluminación real de la celda: la sombra se aplica dos veces.

Por qué no se nota antes: el visor de Blender lo muestra con luz de estudio, que
disimula justamente lo que está mal.

**Cómo confirmarlo:** mirá el difuso **plano, sin iluminación** —en un visor de
imagen, no en el 3D— y buscá degradados suaves donde el material debería ser
uniforme: debajo de un saliente, dentro de un pliegue. Eso es sombra horneada.

**Arreglo:** si el generador ofrece albedo sin luz (salida PBR), pedila. Si no,
se atenúa: levantar el rango bajo con una curva que no toque los medios y bajar
la saturación de las zonas más oscuras. No se recupera del todo.

### 22. Contar aristas de borde por índice infla el número {#22}

**Síntoma:** un modelo que en pantalla se ve perfectamente cerrado reporta
decenas de miles de aristas de borde. Sobre ese dato decidís solidificar y
duplicás el presupuesto de triángulos sin motivo.

**Por qué pasa:** los formatos de intercambio (glTF, FBX, OBJ) guardan las UV
**por vértice**, así que al importar cada costura de UV parte el vértice en dos
índices distintos que ocupan exactamente el mismo punto. Si emparejás aristas
comparando índices, las de los dos lados de la costura nunca se emparejan y
**toda costura cuenta como borde**.

`[OBSERVED]` Un brazo de Tripo: **55.528** aristas de borde contadas por índice,
**12** contadas por posición. El modelo era estanco.

**Arreglo:** canonicalizar por posición redondeada a una rejilla antes de
emparejar. Es lo que hace `aristas_de_borde()` en `scripts/medir_parte.py`.

```python
def clave_pos(i):
    c = malla.vertices[i].co
    return (round(c.x / tol), round(c.y / tol), round(c.z / tol))
```

Alternativa equivalente: soldar (`remove_doubles`) y recién después contar
`edge.is_boundary`. Lo importante es no contar sobre la malla cruda.

**La lección general:** un número que no cuadra con lo que ves en pantalla es un
número sospechoso, no un descubrimiento. Este bug vivió meses dentro de una
función cuyo comentario **afirmaba** que reconciliaba los vértices partidos.
Comentario y código pueden discrepar; el que manda es el código.

### 23. Las flags de partición mal puestas deforman la malla {#23}

**Síntoma:** la malla se rompe o estira en las uniones entre particiones, con
las animaciones normales.

**Por qué pasa:** cada partición lleva `PF_EDITOR_VISIBLE` y
`PF_START_NET_BONESET`. La segunda marca dónde **empieza** un conjunto de huesos
nuevo. Si queda encendida en todas las particiones de un shape, el juego trata
cada una como un conjunto separado y no comparte la transformación en el borde.

Relacionado: `[INVARIANT]` cada triángulo va en **exactamente una** partición.
En dos se dibuja dos veces (z-fighting); en ninguna no se dibuja.

**Arreglo:** copiar las flags del vanilla en vez de elegirlas. Si partís un
shape en dos, repartí los triángulos —no los dupliques— y dejá
`PF_START_NET_BONESET` encendida solo en la primera partición de cada conjunto.

### 24. PyNifly importa la colisión como una malla más {#24}

**Síntoma:** el render sale como una **lámina gris** del tamaño del modelo, que
lo tapa entero. Parece un problema de materiales, de iluminación o de encuadre.
No tira ningún error.

**Por qué pasa:** un `bhkBoxShape` son 8 vértices que forman una caja del
tamaño del asset. PyNifly la importa como objeto de malla igual que la
geometría visible.

**Cómo confirmarlo:** listá los objetos tras importar. `[OBSERVED]` En
`dwarvensteamcenturion.nif` aparecen dos mallas: `bhkBoxShape` con 8 vértices y
`SteamCenturion:0` con 5.630.

**Arreglo:** descartar los objetos cuyo nombre empiece con `bhk`. Es como
PyNifly nombra las formas de colisión (`bhkBoxShape`,
`bhkConvexVerticesShape`, `bhkCompressedMeshShape`, `bhkCapsuleShape`…).

### 25. Filtrar una lista de Python no saca nada del render {#25}

**Síntoma:** filtraste el objeto molesto, el script informa que lo descartó, y
**sigue apareciendo en la imagen**.

**Por qué pasa:** Blender renderiza lo que está **en la escena**, no lo que
quedó en tu variable. Excluirlo de una lista lo saca de tus cálculos —caja
envolvente, asignación de materiales— pero no del render.

```python
mallas = [o for o in todas if not o.name.startswith("bhk")]   # NO alcanza
for o in colision:
    bpy.data.objects.remove(o, do_unlink=True)                # esto sí
```

**Por qué merece entrada propia:** el síntoma es idéntico al de la trampa
[24](#24), así que parece que el filtro no funcionó. `[OBSERVED]` Costó tres
diagnósticos equivocados seguidos —material, planos de recorte de cámara,
encuadre— antes de mirar qué había realmente en la escena.

**La lección general:** cuando un arreglo "no tiene efecto", comprobá que se
haya aplicado sobre el mismo objeto que el sistema está usando. Casi siempre
hay dos: el tuyo y el de él.

### 26. Una malla skinneada no se ensambla sola al importarla {#26}

**Síntoma:** el NIF de una criatura entra con las piezas **desparramadas**, cada
una por su lado, aunque las matrices de objeto parezcan correctas.

**Por qué pasa:** en un NIF skinneado los vértices viven en espacio de skin, y
ensamblarlos necesita las transformadas de bind de cada hueso. `[OBSERVED]` En
`steamcenturion.nif`, `matrix_world` deja las piezas en rangos de Z sensatos
(torso 147–305, pie −0,4–31) y aun así el render sale desarmado: la caja
envolvente se calcula con `matrix_world @ v.co`, que **ignora modificadores**,
mientras que el render sí los aplica.

**Arreglo para renderizar:** usá el **NIF estático** del mismo bicho si existe
(`<bicho>.nif` en la carpeta padre): es un solo `BSTriShape` con la geometría
inline, sin skin y sin ambigüedad. Mismo modelo visual.

**Arreglo para trabajar de verdad:** pasale a PyNifly el esqueleto correcto al
importar y verificá las posiciones contra el binario (trampa [1](#1)).

### 27. Los props estáticos no miran para donde miran los actores {#27}

**Síntoma:** renderizás con la convención de actor y la vista etiquetada
"frente" muestra la espalda.

**Por qué pasa:** en Skyrim el frente de un **actor** es +Y, pero eso es una
convención del sistema de actores. `[OBSERVED]` El estático
`dwarvensteamcenturion.nif` mira a **−Y**: su vista de frente es azimut 0, no
180.

**Arreglo:** no lo deduzcas del tipo de archivo. Renderizá las dos y mirá cuál
tiene la cara. Por eso `scripts/render_referencia.py` toma `--frente-az` en vez
de traer la convención cableada, y avisa en pantalla cómo invertirla.

Es la misma familia que la trampa [19](#19): allá el error estaba en la cámara,
acá en el archivo. El síntoma es el mismo y la consecuencia también — juzgar un
modelo sobre un render mal etiquetado.

### 28. Soldar bien y no comprobarlo despues no alcanza {#28}

**Síntoma:** el arma llega al juego con agujeros por los que se ve el interior.
Ningún paso dio error: el archivo se escribió bien, el juego lo cargó, y el
modelo de origen era impecable.

**Por qué pasa:** la trampa [22](#22) y `scripts/preparar_parte.py` ya dicen que
hay que **soldar antes de decimar**, y lo hacen bien. Pero nada verifica el
resultado. En el hacha de Tencent la decimación la hizo un script escrito a
mano, fuera de `preparar_parte.py`, y la malla salió con el **49,4 %** de sus
aristas abiertas partiendo de un GLB con **cero**. Después yo volví a decimar
**desde ese archivo ya roto**, bajé a 35,2 % y lo leí como progreso.

`[MEASURED]` Decimando 14 shapes vanilla al 25 %: soldando primero el número de
aristas de borde **nunca aumentó** (peor caso x0,70); sin soldar creció en 12 de
14, hasta **x25,5**, y las dos mallas cerradas pasaron de 0 a 956 y a 544.

**Arreglo:** `scripts/salud_malla.py <antes> <despues>`. Corre sobre el
**archivo**, sin Blender, y reprueba si el número de aristas de borde aumentó.
Sobre los archivos reales del hacha, la cadena vieja sale con exit 1 y la nueva
con exit 0.

**Lo que NO se puede exigir:** que la malla esté cerrada. `[MEASURED]` Solo el
**15,1 %** de los shapes vanilla lo están; la mediana tiene el 15,4 % de sus
aristas al aire y `architecture` el 24,7 %. La ropa, los carteles y las láminas
de vegetación son superficies abiertas a propósito. Por eso la regla es
**relacional** —no abrir lo que estaba cerrado— y no absoluta.

**La lección general:** que un paso del pipeline haga lo correcto no sirve si
otro camino llega al mismo archivo sin pasar por él. El arreglo no es
documentar mejor el paso bueno: es poner la comprobación **sobre el resultado**,
donde la ve cualquiera que haya llegado por donde sea.

### 29. El NIF guarda la V al revés que el OBJ {#29}

**Síntoma:** la textura horneada se ve corrida o espejada sobre el modelo, y
todo lo demás está bien: la malla cerrada, el atlas correcto, el bake limpio.
Se concluye que el horneado salió mal y se rehace — que es el paso más caro.

**Por qué pasa:** un NIF guarda la V con el origen en la **fila 0** de la
imagen; un OBJ y Blender la guardan con el origen **abajo**. Un conversor que
copie la V tal cual deja todo el mapeo espejado en vertical. No da error: el
archivo se escribe bien y el juego lo carga.

Con el atlas de una IA 3D —una isla de UV por triángulo— ni se nota, porque ya
era ruido. Aparece recién cuando la textura es buena.

`[MEASURED]` **PyNifly invierte la V al importar**: sobre tres armas vanilla,
2.648 / 1.370 / 2.716 loops invertidos contra 13 / 23 / 16 iguales. `[MEASURED]`
El corpus apoya lo mismo, aunque no unánime: tomar v como fila desde arriba cae
sobre pintura el 69,5 % de las veces contra 58,3 %, ganando en 86 de 120
archivos. `[OBSERVED]` Y el control renderizado de `elvenbattleaxe.nif` con su
propia textura sale bien solo con la V invertida.

**Arreglo:** `uv = (u, 1.0 - v)` al escribir el NIF, y comprobarlo con
`scripts/verificar_uv.py <origen.obj> <exportado.nif>`. Sobre los archivos
reales del hacha: 8.299 invertidas y 0 iguales; regenerando el NIF sin la
inversión, 0 y 8.299.

**La lección general:** una convención de formato que no rompe nada al
escribirse solo se ve cuando el resto ya está bien. Cuanto más tarde aparece,
más caro es el paso que se sospecha primero.

### 30. Cómo NO medir la convención del canal verde {#30}

**Síntoma:** el relieve sale al revés —los remaches hundidos, las incisiones
sobresaliendo— y no hay forma de decidir por qué. El archivo es válido, el
juego lo carga, y las dos hipótesis parecen igual de plausibles.

**La práctica, primero:** **no inviertas el verde.** Es el valor por defecto
del bake de Blender (`bake.normal_g = POS_Y`), y coincide con un control
renderizado sobre un asset vanilla.

**Y ahora las dos formas en que intenté medirlo y fallé**, porque las dos son
tentadoras y cuestan tiempo:

1. **Comparar la normal reconstruida contra la normal suave del vértice.**
   Es **simétrico por construcción**: con `P = T·tx + B·ty + N·tz` y `T`, `B`
   perpendiculares a `N`, el producto `dot(P, N)` depende sólo de `tz`, y `tz`
   no cambia al invertir el verde. `[MEASURED]` Sobre dos mallas dio **0,8222
   contra 0,8222**, idéntico hasta el último decimal.

   La señal de alarma es esa: si un test devuelve el **mismo número** para las
   dos hipótesis, no está midiendo la hipótesis. Vale la pena comprobar eso
   antes de correrlo sobre el corpus.

2. **Coincidencia a través de una costura de UV.** Los dos lados de una
   costura tienen marcos tangentes distintos y la misma superficie física, así
   que la normal reconstruida debería coincidir; invertir el verde rompe esa
   coincidencia asimétricamente. `[MEASURED]` Sobre 40 mallas vanilla dio
   0,839 contra 0,801 y ganó "tal cual" en **31 de 40**.

   Parecía servir. **No sirve**: sobre `elvenbattleaxe.nif` —el único archivo
   con respuesta independiente— el mismo método vota **27 a 37 por invertido**,
   lo contrario del control. Y se mueve con detalles que no deberían importar:
   muestrear un 15 % hacia adentro de la isla lo lleva a 22 contra 41.

**Por qué es difícil:** el marco tangente se deriva de las UV, así que la **V y
el verde están acoplados**. Invertir la V cambia `T` y `B`, y eso es
indistinguible de invertir el verde. Medir uno presupone el otro ya fijado.

**Lo que sí funciona: un control vanilla renderizado.** Tomá un asset de
Bethesda con su propia textura, renderizalo **sin textura de color** y con luz
rasante desde arriba, con el verde tal cual y con el verde invertido. Mirá algo
cuya forma no admita discusión —un remache, una cabeza de clavo— y fijate en
cuál de los dos sobresale.

**La lección general:** un promedio favorable sobre 40 archivos **no rescata**
un método que contradice la verdad conocida en el único caso donde la verdad se
conoce. Cuando hay un caso con respuesta independiente, ese caso manda sobre el
agregado.

### 31. Hornear el albedo con `DIFFUSE` deja negro todo lo metálico {#31}

**Síntoma:** el atlas horneado sale a medias: el cuero marrón, el hierro
**negro**. Blender no da error.

**Por qué:** `[INVARIANT]` de Cycles, no de Skyrim. El pase `DIFFUSE` solo
captura la componente difusa del BSDF, y un Principled con `Metallic = 1.0` no
tiene. El color está en *Base Color*, que ese pase no lee. `[MEASURED]` Mismo
objeto, 1024²: con `DIFFUSE` el atlas pesaba 82.538 bytes, casi todo negro; con
`EMIT` y la misma red de color, 450.652 y completo (#36).

**Arreglo:** hornear el albedo con `type='EMIT'`: conectar *Base Color* a un
`ShaderNodeEmission` y ponerlo como salida del material solo durante ese bake.
Alternativa: `Metallic = 0` durante el bake, y restaurarlo — pero **solo con
`pass_filter={'COLOR'}`**. El operador trae `pass_filter=set()`, que toma la
configuración de la escena, y ahí `use_pass_direct`, `use_pass_indirect` y
`use_pass_color` vienen en `True`: el `DIFFUSE` por defecto hornea color × luz,
una textura iluminada con las sombras fijas de la trampa [21](#21). El `EMIT`
no tiene ese problema porque la emisión no depende de la luz.

### 32. Un Bevel después del unwrap superpone las UV {#32}

**Síntoma:** en el atlas, las islas de un material muestrean los píxeles de
otro. `[MEASURED]` Con emisión pura (hierro rojo, cuero verde), las caras de
cuero leían **83 % rojo**.

**Por qué:** las caras nuevas del Bevel heredan UV interpoladas de las vecinas
y caen **encima** de las originales. `census/parser_uv.py` sobre el NIF
exportado: `solape_huella` **0,093** antes, **0,0** después de
re-unwrappear (#37).

**Arreglo:** unwrappear **después** de todo modificador que agregue caras. Y
medir `solape_huella` sobre el archivo escrito, no confiar en el orden de los
pasos.

### 33. `target_game='SKYRIMSE'` no alcanza: PyNifly exporta LE igual {#33}

**Síntoma:** el export dice `Export successful`, pero el NIF sale con
`bs_version 83` y `NiTriShape` + `NiTriShapeData`: formato LE.

**Por qué:** con `intuit_defaults=True` (el default), PyNifly **pisa** el
`target_game` con el que deduce de la metadata del objeto
(`export_nif.py`, `_discover_game`). Un objeto creado desde cero no tiene esa
metadata y cae en `SKYRIM`. `[MEASURED]` Mismo estático: default → `bs_version
83`, 49.730 bytes; `intuit_defaults=False` → `bs_version 100`, `BSTriShape`,
27.421 bytes, leído con `census/parser_nif.py` (#35).

**Arreglo:** pasar **siempre** `target_game='SKYRIMSE', intuit_defaults=False`,
y verificar `bs_version == 100` en el archivo escrito. Es pariente de la
trampa 13 de `asset-nuevo-skyrim`: ahí el default era LE; acá lo es aunque
pidas SE.

### 34. Afinar una parte: la rampa y el centro deforman sin avisar {#34}

Salió del hacha de Tencent, que venía con un mango más grueso que el de
cualquier arma de dos manos vanilla y hubo que afinarlo al 59 %.

**Síntoma:** en el juego, "una pequeña imperfección en el mango donde se
reduce". De cerca eran dos defectos, y la malla sin afinar no tenía ninguno:

1. **Un cono.** La transición del factor iba de `y_norm` 0,45 a 0,60, pero el
   palo recto llegaba hasta 0,5525. El último tramo del palo volvía a engordar
   antes de la cabeza.
2. **Una torsión.** Se escalaba alrededor del centro de la caja del palo entre
   0,05 y 0,45, y esa caja agarraba el pomo, que está corrido: el "centro"
   quedaba **2,2 cm** al costado del eje real. Escalar alrededor de un centro
   corrido desplaza la sección (0,022 × 0,41 ≈ 0,9 cm); dentro de la rampa ese
   desplazamiento volvía a cero, y el palo se torcía hacia la cabeza.

**Por qué no lo ves venir:** los dos pasan cualquier control de salud de malla
(sin bordes, sin pliegues, una pieza) y el factor promedio del palo da bien.

**Arreglo, medido sobre la malla densa antes de tocar nada:**

- **El perfil por rebanadas.** Para cada franja de altura, el semiancho y el
  centro de su caja. Ahí se ve dónde termina el tramo recto (en el hacha, el
  semiancho es constante hasta 0,5525 y salta en 0,555: el collar).
- **El eje es la mediana de los centros de rebanada** del tramo recto, no el
  centro de una caja que puede agarrar otra pieza.
- **La transición va en una discontinuidad que ya existe** —la cara inferior
  del collar, 3 mm—, nunca adentro de un tramo recto. El palo "entra en su
  casquillo" y no hay cono posible.
- **El control que atrapa los dos defectos:** cada rebanada del tramo tiene que
  quedar **exactamente** al factor y con su centro donde manda la semejanza.
  Una rampa adentro o un eje corrido lo hacen fallar en el acto.
- **La misma función al modelo alto y al bajo**, o el horneado sale corrido.

**Achicar una pieza sin deformar lo que tiene pegado.** Después se achicó la
columna de la cabeza, donde se montan las hojas. Escalar todo por igual achica
también las hojas. Lo que funcionó: un mapa en la dirección de las hojas con
derivada `g` en el núcleo y 1 afuera, suave entre medio. El núcleo se escala y
las hojas se **trasladan enteras** lo justo para seguir pegadas. Es monótono,
así que no puede plegar la malla. Control: cada vértice de hoja trasladado sin
deformarse (desvío 1e-17).

Confirmado en el juego: "quedó genial". Los scripts son `afinar_v2.py` y
`afinar_v3.py` del hacha; los números de arriba son de ese modelo, **no los
copies**: medí el perfil del tuyo.

### 35. Hornear con una muestra por texel desde una textura más grande es aliasing {#35}

**Síntoma:** bordes dentados en el horneado, sobre todo en el normal map. Sin
ningún error.

**Por qué:** el bake de Cycles corre con `samples = 1`: cada texel del destino
lee **un** punto del modelo alto. El modelo de Tripo trae mapas de **4096²**; si
el destino es de 2048², es muestreo puntual de una textura dos veces más grande.

**Arreglo:** hornear al doble (4096, con el margen también al doble) y reducir
2×2 filtrando **cada mapa como lo que es**:

| mapa | cómo se promedia | por qué |
|---|---|---|
| albedo | sRGB → lineal, promedio, → sRGB | promediar los valores sRGB oscurece los bordes |
| normal | promediar los vectores y **renormalizar** | el promedio de cuatro unitarios distintos es más corto que 1 |
| metal / rugosidad | promedio simple | son datos lineales |

El archivo final pesa lo mismo. Control: la media de cada canal no se mueve más
que el redondeo (en el hacha, 0,00014 como máximo). En el normal map, entre el
0,03 y el 0,05 % de los texels —los de las costuras de UV— promediaban menos
de 0,5 de largo.

**Y al pasar a DDS:** `texconv -f BC7_UNORM_SRGB -srgb` para el albedo, y
**comprobarlo**: decodificar la DDS y comparar con el PNG. En el hacha las
medias coinciden a 0,02 y el error medio es 0,65/255, que es la compresión BC7.
Si `texconv` hubiera convertido la gamma, la media se movería decenas.

Lo que **no** se midió: cuánto mejora a la vista. El mecanismo es sólido y el
hacha salió bien, pero ese cambio vino junto con otros y la mejora del
horneado no se aisló.

## Proceso

### 19. La vista "de frente" de tu render puede estar mostrando la espalda {#19}

**Síntoma:** juzgás el modelo varias veces sobre un render mal etiquetado.

**Por qué pasa:** una cámara en azimut 0 se pone en **−Y** mirando hacia +Y, así
que muestra la cara que apunta a **−Y**. Si el personaje mira a +Y (como pide
Skyrim), ésa es la **espalda**. La vista de frente es azimut **180**.

**Arreglo:** verificalo una vez con algo inequívoco —el pecho, la cara, los
dedos del pie— y dejá la convención anotada en el script de render.

---

## La disciplina que atrapa las que faltan

Esta lista no va a estar completa nunca. Lo que sí generaliza:

**Verificá el archivo, no la escena.** Reimportá el NIF generado y compará
contra el vanilla: bloques, strings, posiciones de hueso, huesos por pieza,
particiones, capas. En el proyecto de origen, el control de "cada hueso dentro
de la caja de su pieza" encontró un NIF completamente desarmado que ya se daba
por bueno.

**Un chequeo que no puede fallar no prueba nada.** Alimentalo a propósito con
datos equivocados y confirmá que revienta. La falsificación con un esqueleto
humano dio 7 fallos de 16 huesos comparables; recién ahí el `[ok]` significó
algo.

**Mirá renders después de cada paso que toque geometría.** Varias de estas
trampas son invisibles en los números y evidentes en una imagen.

**No inventes invariantes.** El error más caro del proyecto de origen no fue
técnico: fue afirmar como ley del motor algo que solo era una propiedad del
montaje propio —"dos partes en el mismo hueso comparten obligatoriamente una
textura"— y declarar por eso un bloqueo que no existía. Antes de escribir una
regla, ubicala en una de tres categorías:

- `[INVARIANT]` — propiedad del formato o del motor. Comprobable contra la
  especificación o contra un archivo de Bethesda. Es ley.
- `[PROVIDER]` — comportamiento de un generador o de una herramienta hoy. Cambia
  entre versiones y entre planes. Verificalo cada vez.
- `[OBSERVED]` — algo que viste una vez. Vale como expectativa, no como regla.

Y el control práctico: **si la regla te lleva a decirle a alguien "esto no se
puede", comprobala contra un archivo real antes de decirlo.** Un bloqueo
inventado cuesta más que un bug.
