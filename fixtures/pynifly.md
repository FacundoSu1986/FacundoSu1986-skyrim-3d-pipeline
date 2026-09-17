# PyNifly, medido

La fila del toolchain que estaba declarada como **no verificado** ahora tiene
número. Esto es lo que pasa cuando se importa un static vanilla con PyNifly y
se lo vuelve a exportar, sin tocar nada en el medio.

```
Blender 4.4.1        PyNifly io_scene_nifly v27.2.0
target_game=SKYRIMSE     blender_xf=False
N = 1.857 estáticos simples (los candidatos de fixtures/README.md)
```

La comparación **no la hace Blender**. Los bytes se leen con
`census/parser_nif.py` y `census/parser_uv.py`, que no saben nada de PyNifly.
Si la comparación se hiciera releyendo con el mismo addon, un defecto simétrico
de lectura y escritura se cancelaría solo.

---

## 1. La geometría sobrevive intacta

**AFIRMACIÓN**: Las posiciones de vértice vuelven **exactas en 1.857 de 1.857**
archivos — peor desvío `0,000000000`. Las UV en **1.856 de 1.857**. Los índices
de triángulo, idénticos y en el mismo orden, en **1.831 de 1.857**.
**CONSULTA**: comparación vértice a vértice con `parser_uv.geometria()`.
**N**: 1.857 archivos, un shape cada uno.
**EXCEPCIONES**: la única UV que cambia es
`architecture/whiterun/wrinteriors/wrintfloorstmid01largealtar01.nif`, con un
desvío de **1,66** — que no es ruido, es otra coordenada. De los 26 con
triángulos distintos, **16 son `clutter/potions/`**: un patrón demasiado limpio
para ser casualidad.

> Sobre el `roadsignwhiterun01.nif` desglosamos los 342 bytes que cambian
> dentro del `BSTriShape`: están todos en los offsets `+12..+15` y `+21..+27`
> del vértice — bitangente, normal y tangente. Las posiciones (`+0..+11`) y las
> UV (`+16..+19`) no cambian un byte. PyNifly recalcula las tangentes; no toca
> lo que se le dio.

## 2. Pero la estructura alrededor se reescribe

**AFIRMACIÓN**: Solo **1.264 de 1.857 (68,07 %)** conservan el mismo conjunto
de tipos de bloque, y apenas **170 (9,15 %)** conservan además los tamaños.
**CONSULTA**: comparación de la tabla de bloques.
**N**: 1.857.
**EXCEPCIONES**: lo que se reescribe:

| | |
|---|---:|
| `bhkRigidBodyT` → `bhkRigidBody` | **504** archivos |
| `bhkRigidBody` → `bhkRigidBodyT` | 10 |
| pierde `bhkMoppBvTreeShape` | 42 |
| pierde `NiFloatInterpolator` / `NiFloatData` | 22 / 20 |
| pierde `BSLightingShaderPropertyFloatController` | 16 |

La variante `T` del cuerpo rígido lleva un *transform* propio. Convertirla en la
variante sin transform es la reescritura más frecuente del corpus.

## 3. Lo que de verdad importa: dónde queda la cosa

Comparar bytes no dice si el asset queda bien. Lo que lo dice es **dónde queda
la geometría en espacio de mundo**. Se midió importando el original y el
exportado y comparando la caja envolvente de cada uno.

**AFIRMACIÓN**: La malla queda en un lugar distinto en **112 de 1.857
(6,03 %)**. La colisión, en **56 de 615 (9,11 %)** de los que la tienen, y
**se pierde entera en 3**.
**CONSULTA**: AABB en espacio de mundo, original vs exportado, tolerancia 0,05
unidades.
**N**: 1.857 mallas; 618 con colisión.
**EXCEPCIONES**: el peor caso mueve la malla **724,6 unidades** — más de diez
metros. `architecture/markarth/mrkriverbaseupper.nif`.

**La firma es una rotación, no un desplazamiento.** De los 112 que se mueven,
**81 (72,3 %) tienen el eje Z intacto** mientras X e Y cambian. En 62 el AABB
simplemente intercambia X e Y —giro de 90° o 180°— y en 50 cambia de tamaño,
que es lo que hace un giro de un ángulo cualquiera.

```
slgftraconmid01.nif   [188,54  40,04  32,06]  ->  [ 40,03  188,54  32,06]
smdshelf01.nif        [ 36,82 160,00  50,81]  ->  [160,00   36,81  50,81]
```

Los 31 restantes **también se mueven en Z** y no entran en esa explicación.
Queda como modo de falla sin caracterizar, no disimulado.

## 4. Las rutas de textura se reescriben casi siempre

**AFIRMACIÓN**: Solo **11 de 1.857 (0,59 %)** conservan las rutas exactas.
**1.571 (84,60 %)** coinciden salvo mayúsculas. El **15,4 % restante difiere
por más que el caso**, y en varios cambia la *cantidad* de rutas: 5→4, 3→2,
6→5, y un caso 0→2.
**CONSULTA**: comparación de `nif.texturas()`.
**N**: 1.857.
**EXCEPCIONES**: la causa está en el propio addon. Al correrlo headless sin
preferencias, el traceback apunta a
`shader_io.ShaderImporter._build_alt_pathlist_for_game`, que lee
`bpy.context.preferences.addons['io_scene_nifly'].preferences`: **PyNifly
resuelve las texturas contra rutas configuradas en tu instalación**, no contra
lo que dice el archivo. El resultado depende de cómo tengas configurado
Blender, que es exactamente lo que un pipeline reproducible no quiere.

## 5. El material Havok cambia en 71 archivos

**AFIRMACIÓN**: En **71 de 1.857**, el material de colisión que lee nuestro
parser pasa a `SKY_HAV_MAT_NONE` (`SKY_HAV_MAT_STONE`,
`..._CERAMIC_MEDIUM`, `..._HEAVY_WOOD` en el original). En 6 cambian además
`layer`, `motion_system` y `mass`.
**CONSULTA**: `parser_nif.colision_info()` sobre los dos archivos.
**N**: 1.857.
**EXCEPCIONES**: **no está verificado que PyNifly lo pierda.** Nuestro parser
busca el material recorriendo la jerarquía de shapes; si PyNifly la
reestructura —y sabemos que cambia el tipo del cuerpo rígido en 504 archivos—
el dato podría estar en otro lado y ser nuestro lector el que no lo encuentra.
Distinguir las dos cosas requiere decodificar la jerarquía nueva, y no se hizo.

---

## Lo que esto le dice al contrato, que es una crítica a nuestro propio trabajo

**El contrato de `comparar.py` pasa en 1.856 de 1.857 de los archivos
exportados.** Da verde sobre archivos donde el cuerpo rígido cambió de tipo, la
colisión se movió diez metros, las rutas de textura se reescribieron y se
perdieron slots.

No es que el contrato esté mal: es que mide **otra cosa**. Valida que un
archivo esté *bien formado* como NIF de Skyrim SE. No valida que sea *fiel* a
un original. Son dos propiedades distintas y hasta acá las veníamos tratando
como una sola.

Para el paso de verificación exportado-vs-vanilla hace falta la segunda, y hoy
no existe. Lo que sí existe ahora es la medición que dice qué tendría que
atrapar.

## Conclusión operativa

- **Para geometría, PyNifly es confiable.** Posiciones y UV vuelven exactas.
- **Para todo lo demás, no se le puede confiar sin verificar**: el 6 % de los
  assets queda rotado, el 9 % de las colisiones se mueve, y las rutas de
  textura dependen de tu configuración de Blender.
- **La verificación tiene que ser en espacio de mundo**, no por bytes. Un
  archivo puede tener los mismos bytes de vértice y estar en otro lado.

## Lo que esto NO mide

- **Mallas riggeadas.** Todo esto es sobre estáticos de un solo shape. Las
  trampas conocidas de PyNifly con esqueletos y huesos no se tocaron.
- **Si el juego lo carga bien.** Un archivo puede diferir del vanilla y andar
  perfecto. Lo único que cierra eso es verlo en el juego.
- **De quién es la culpa.** Se midió `importar → exportar`, así que un defecto
  del importador y uno del exportador no se distinguen. Lo que sí queda
  probado es que el ciclo completo **no es idempotente**.
