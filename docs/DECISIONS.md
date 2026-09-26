# Registro de decisiones — orden de merge de los PRs iniciales

Este documento fija el orden y el criterio con que se integran los primeros
pull requests del repo. Es un registro de decisión, no un contrato técnico:
las afirmaciones de dominio viven en `SKILL.md`, `census/hallazgos.md` y las
referencias de la skill.

## Contexto

Dos agentes distintos propusieron, en paralelo, un framework para llevar assets
3D de IA (Meshy/Tripo/etc.) a Skyrim. Quedaron tres PRs abiertos:

| PR | Rama | Base | Qué aporta |
|---|---|---|---|
| #1 | `feat/bootstrap-framework` | `main` | Scaffold conservador: contratos Python (`src/`), `SKILL.md` raíz en inglés, CI mínima, tests, backlog de verificación. No entrega scripts de dominio. |
| #6 | `feat/skill-modelo-ia-a-skyrim` | `main` | La skill real: `SKILL.md` + referencias (`limites-skyrim`, `pedir-a-la-ia-3d`, `trampas`) + 4 scripts + `LICENSE`. |
| #7 | `feat/censo-corpus-vanilla` | **`feat/skill-modelo-ia-a-skyrim`** | Parser NIF completo y censo empírico de 22.394 mallas vanilla que respalda los números de #6. Encadenado sobre #6. |

## Decisión

**Base del framework: #6 + #7.** Son un cuerpo coherente del mismo autor, con
disciplina anti-invención (etiquetas `[INVARIANT]/[PROVIDER]/[OBSERVED]`, suites
de falsificación, "no anunciar un bloqueo sin comprobarlo contra un archivo
real"). #7 depende de #6 (referencia sus rutas), así que el orden es forzado.

**#1 se cierra** una vez integrado #6+#7. Su `SKILL.md` raíz y su paquete `src/`
compiten con la skill de #6 y son mucho más finos en valor de dominio. Lo que sí
valía la pena de #1 —tener CI y disciplina de tests— se rescató en el PR de
integración (ver abajo), adaptado a la estructura real de #6/#7. El `.gitignore`
de #1 **no** se rescató: el de #6 ya es más completo (excluye assets de Bethesda,
`*.jsonl`, artefactos derivados).

## Orden de merge

```
main
  └─ #6  feat/skill-modelo-ia-a-skyrim   (merge primero)
       └─ #7  feat/censo-corpus-vanilla   (merge después; reapunta a main al mergear #6)
            └─ integración: CI + tests      (este PR; merge último)
```

Al mergear #6 a `main`, GitHub reapunta la base de #7 a `main` automáticamente si
se borra la rama de #6. Igual para la base de este PR de integración cuando se
mergee #7.

Después de #1 cerrado y #6→#7→integración mergeados, `main` queda con: la skill,
las referencias medidas, las herramientas del censo, y CI verde.

## PR de integración (rescate de #1)

Aporta, sin tocar los archivos de #6/#7:

- `.github/workflows/ci.yml` — matriz Python 3.11/3.12: `compileall` de todos los
  scripts (incluidos los de Blender, que solo se validan por sintaxis porque
  importan `bpy`) + `unittest`.
- `tests/` — Python puro, sin corpus:
  - import smoke de los módulos stdlib (`parser_nif`, `verificar`, `agregados`,
    `generar_reporte`, `censo_nif`, `nif_nodos`);
  - invariantes de las tablas de enums de `parser_nif.py`;
  - guarda de regresión del bug documentado `BSFurnitureMarkerNode` (rompía 123
    archivos de muebles);
  - funciones puras de `agregados.py` (`mediana`, `p90`, `pct`).

Lo que CI **no** cubre y por qué: `--autotest` del parser necesita el corpus
vanilla, que no se versiona (assets con copyright, ~54 MB derivados); los scripts
de Blender no se pueden importar sin `bpy`.

## Actualización: el hueco de cobertura era más grande de lo que decía

La suite de arriba se falsificó a propósito, inyectando en `parser_nif.py` un
corrimiento de 4 bytes al leer la cabecera (`i += 8` en vez de `i += 4` al
saltear *max string length*). Ese bug destruye la tabla de strings y **todos**
los offsets de bloque — es la misma familia de error que produjo el
`pesos por vértice = 1035` documentado en `census/README.md`.

**Los once tests siguieron en verde.** Ninguno ejecutaba el parser sobre bytes
de un NIF: probaban formas de tablas y una constante de regresión.

El arreglo es `tests/nif_sintetico.py`: construye un NIF válido byte a byte en
memoria —cabecera, tabla de tipos, tabla de strings, tres bloques con tamaños
exactos— y declara junto a los datos qué tiene que recuperar un parser correcto.
Como los bytes se generan, no hay ni un byte de Bethesda y el fixture puede
vivir en el repo.

Con el mismo bug inyectado, la suite nueva da 4 errores.

`tests/test_parser_nif_sintetico.py` incluye además `ElFixtureEsDetectorTests`,
que corrompe el fixture a propósito y confirma que el parser revienta. Un
chequeo que no puede fallar no prueba nada; ese test existe para que, si el
parser deja de validar, se entere alguien.

### Dos correcciones que salieron de la review de Codex

**1. `-W error::ResourceWarning` no detecta fugas de descriptor.** Se había
agregado a CI diciendo que una fuga rompería el build. Es falso: el aviso lo
emite el destructor del objeto archivo, y una excepción lanzada ahí queda
*unraisable* — imprime un traceback y el proceso sale con código 0. Reproducido
en 3.11 con un test que hace `open(__file__, "rb").read()`: imprime el aviso,
`unittest` dice `ok`, exit 0.

Era exactamente el defecto que este documento acusaba dos párrafos más arriba:
una guarda que no puede fallar. El flag se sacó y las fugas se comprueban en
`SinFugasDeDescriptorTests`, que fuerza la recolección con el filtro activo y
afirma sobre lo capturado. Trae `test_el_detector_detecta`, que fuga a propósito
y exige que el detector lo vea.

**2. `BSFurnitureMarkerNode` seguía en `TIPOS_NODO` de la semilla.** Pese al
sufijo, hereda de `NiExtraData`, no de `NiAVObject`. `census/parser_nif.py` ya
lo excluía; `skills/.../censo_nif.py` no. Medido: **30 de 76** archivos de
`meshes/furniture/` reventaban con `unpack_from requires a buffer of at least
4093659953 bytes`. Corregido: 30 → 0.

El fixture sintético ahora incluye un `BSFurnitureMarkerNode` minado que
reproduce ese modo de falla exacto, así que la guarda es de **comportamiento**
—se parsea el bloque— y no solo de pertenencia a un set.

Esto también resuelve el solape entre este PR y #10: #10 asserta la invariante
sobre las tres tablas pero no toca `censo_nif.py`, que es archivo de este PR. Se
arregla acá, así los dos mergean verde sin pisarse.

## Los dos parsers: resuelto, se quedan los dos

`skills/modelo-ia-a-skyrim/scripts/censo_nif.py` (semilla, #6) y
`census/parser_nif.py` (versión completa, #7) se solapan, y la recomendación
anterior era unificarlos o justificar la duplicación.

**Se justifican, y ahora hay un test que lo sostiene.** Son dos
implementaciones escritas por separado de la misma cabecera, y esa
independencia es lo que da la validación cruzada: 400 archivos vanilla al azar
con 400/400 de coincidencia. Un verificador que depende de la herramienta que
verifica no verifica nada.

`ConcordanciaEntreParsersTests` los fija a coincidir sobre los mismos bytes: si
divergen, una de las dos está mal y CI lo dice. Unificarlos destruiría la
propiedad que los hace útiles.

La semilla se queda deliberadamente chica: enseña el método —autotest primero,
ningún campo sin caso de falsificación— sin el peso de los layouts de skin,
shader y colisión.

## Cablear PROCESS_TEXTURES: qué se convierte y qué deliberadamente no

Primera fase real del runner después de INGEST/INSPECT. La decisión de fondo no
es técnica: es **qué conversiones tienen un número atrás y cuáles no**, porque
una conversión inventada en esta fase no tira ningún error --se ve en el juego,
con el asset ya instalado.

**Se convierte, con número:**

- **alfa del `_n` desde la rugosidad** (`255 − roughness`). La CURVA es una
  heurística sin calibrar: sobre la rugosidad real de Tripo del hacha da una
  mediana tres veces más clara que la de las armas vanilla. Lo que tiene
  número es el control de después. El `_n` escrito se mide, y el texture set
  **pide revisión** (`motivos_revision`, con el número al lado) si pasa del
  10 % de bloques en blanco --la regla de armas; las 140 `_n` de arma del
  corpus están por debajo del 6,9 %-- o si la media del alfa cae fuera del
  p5-p95 de los objetos portables vanilla (14 a 219). El hueco negro del atlas
  es rugosidad 0 y sale en 255: ese control es el que lo ve.
- **máscara `_m` desde la metalicidad**, con el rango expandido. Es una
  HEURÍSTICA y se declara como tal en el código y en el reporte: no hay
  medición del corpus que fije cuánto expandir. Lo que sí hay es la medición de
  que los generadores entregan metalicidad comprimida (0 a 0,46, media 0,06 en
  el proyecto de origen) y de que sin expandir la máscara sale sin contraste.
  También es heurístico el piso: con metalicidad máxima por debajo de 16 el
  objeto se toma como no metálico y no se escribe `_m` (antes, un máximo de 2
  por ruido se estiraba a 255).
- **el canal lo decide el nombre**, no una mirada a los píxeles:
  `_orm`/`_metallicRoughness`/`_arm` es el empaquetado de glTF (G rugosidad,
  B metalicidad); `_roughness` y `_metallic` sueltos son grises, y se
  comprueba que lo sean sobre una grilla repartida por toda la imagen. Una
  rugosidad suelta **no** genera `_m`. Un nombre con una palabra de rol que
  no se reconoce (`_normalmap`) es un error, no un color; y un normal
  `_dx`/`_DirectX` se escribe con el verde invertido, porque Skyrim usa
  OpenGL.
- **cada mapa se reduce como lo que es**, en el nivel 0 y en cada mipmap:
  color en luz lineal, normal renormalizado, datos tal cual (trampa 35 de la
  skill).
- **potencia de dos en ambos lados**, redondeando hacia arriba y solo bajando
  cuando el manifest lo pide (`max_lado_textura`, default 2048). Medido: 0 de
  32.241 texturas vanilla tienen un lado que no lo sea.

**No se convierte, y el motivo queda escrito:**

- **No se comprime a DXT1/DXT5/BC7.** Se escribe sin comprimir de 32 bpp con la
  cadena completa de mipmaps, que es lo que ya hace y ya verifica
  `census/escritor_dds.py` (10.048 de 32.241 vanilla son así). Un compresor de
  bloques es otra pieza con su propia falsificación --lo dice el docstring de
  ese archivo-- y el `_n` es el primer mapa que lo va a pedir. *(Después:
  DXT1/DXT5 llegó como opción del manifest; ver "Compresión DXT propia".)*
- **No se saca la luz horneada del albedo.** `limites-skyrim.md` documenta que
  se atenúa con curvas y que no se recupera del todo. Hacerlo en silencio sería
  inventar una conversión que nadie midió; se informa como observación.
- **No se toca el NIF.** La fase deja la ruta declarada de cada mapa en el
  reporte, que es lo que una futura EXPORT_NIF necesita para llenar el
  `BSShaderTextureSet`.
- **No se comprueba que la malla conserve las UV del generador.** Los mapas
  sirven solo en ese caso; si PREPARE decima o re-despliega sin conservarlas,
  hay que hornear. Queda pendiente de decidir, y mientras tanto la fase lo
  deja escrito como `precondicion_uv` en el reporte y en `texture_set.json`.

**Las texturas pasan por INGEST.** Se copian a `input/texturas/` con su hash y
PROCESS_TEXTURES lee las copias: el hash del reporte y los bytes convertidos
son los mismos aunque alguien reescriba el original durante la corrida. Por
eso INSPECT ahora busca la malla por su nombre y no toma "el primer archivo"
de `input/`.

**La verificación es la mitad que ya existía.** Cada DDS escrito pasa por
`fixtures/comparar.reglas_dds` (`dds_parsea`, `dds_tamano`,
`dds_potencia_de_dos`, `normal_con_alfa`) y falla la fase si alguna regla
reprueba; las rutas declaradas se comprueban con `comparar.resolver_textura`,
que resuelve las cuatro formas del corpus y rechaza path traversal. La máscara
del `_n` se mide con `scripts/mascara_especular.py`.

**Dos cosas que hubo que arreglar para que eso fuera cierto:**

1. `mascara_especular.py` clasificaba el sin comprimir de 32 bpp como "lleva
   alfa pero este lector no lo decodifica" y lo reportaba como límite de la
   herramienta. Era falso: no hay nada que decodificar. Ahora lo mide texel por
   texel, con la misma semántica de bloque constante que en DXT5, busca el
   alfa en el byte que dice la máscara de la cabecera, y el autotest cuenta
   sus comprobaciones en vez de imprimir un total escrito a mano. El límite
   real sigue siendo BC7, que tiene ocho modos con particionado variable.
2. `fixtures/comparar.py` insertaba `census/` en `sys.path` con una ruta
   RELATIVA. Al importarlo desde `pipeline/texturas.py` con cualquier
   directorio de trabajo, ese import se caía. Ahora es absoluta.

**Una regla nueva, y su alcance.** La fase exige que cada grupo de mapas tenga
color base: sin difuso no hay `BSShaderTextureSet` posible. Es una regla de
formato, no de gusto. En cambio, la saturación del alfa del `_n` **informa y no
reprueba**, porque la regla de saturación está medida solo sobre armas y el
alcance del manifest es static/clutter --el mismo error de alcance que este repo
ya cometió tres veces (radio de colisión, "la malla tiene que estar cerrada",
solape de UV) y que acá se declara en vez de suponerse.

**El gate no se tocó.** Con PROCESS_TEXTURES cableada, publicar sigue siendo
imposible: lo que frena ahora es PREPARE, EXPORT_NIF, READ_BACK, VALIDATE y
PACKAGE. `tests/test_pipeline_gate_stubs.py` enumera la fase dejada como stub y
exige que ninguna llegue a PUBLISHED; el caso del issue #23 se actualizó con una
nota que dice por qué `process_textures` salió de esa lista.

## True PBR de Community Shaders: un modo aparte, desde el código fuente

El issue #57 dejó abierta una decisión: la capa HD, ¿cubre solo el `_n`/`_d`
vanilla, o también el True PBR de Community Shaders? Se incluyó, como **modo
aparte** del manifest (`sombreado="cs_pbr"`), no como reemplazo: el shader
vanilla sigue siendo el default y sus tests no cambiaron.

**Por qué del código fuente y no de guías.** Es `[PROVIDER]`: depende de un
mod de terceros. Las convenciones —el bit 23 de `Shader_Flags_2` que prende
el PBR, el `_rmaos` en la ranura 5 con rugosidad, metal, oclusión y
reflectancia, los campos del NIF que cambian de significado— se leyeron en su
repositorio, fijado al commit `898b167`, y se contrastaron con PBRNifPatcher y
con los nombres de PyNifly. Todo está en
`skills/modelo-ia-a-skyrim/references/pbr-community-shaders.md`.

**Qué se midió.** Que ningún NIF vanilla tiene ese bit (0 de 74.489 bloques),
así que la detección no puede confundirlos. Que PyNifly escribe el bit donde
lo espera CS: un NIF hecho con la receta y leído con `material_arma.py`.
**Qué no:** nada se vio en el juego con Community Shaders, ni sin él.

**Dos decisiones de la fase.** Sin fuente de rugosidad, `cs_pbr` falla: CS
llena la ranura 5 vacía con blanco, que es rugosidad 1 y metal 1. Y los topes
de revisión de la máscara vanilla no se aplican: en PBR el especular sale del
`_rmaos`, y el alfa del `_n` solo lo lee el SSR de la ruta no diferida.

## Compresión DXT propia, con Pillow de oráculo

Lo último que pedía el issue #57: escribir el `_n` en DXT5, como los 12.075
`_n` del corpus. Hasta acá la fase escribía solo sin comprimir: válido, pero un
`_n` de 2048 pesa 22 MB en vez de 5,6.

**Por qué un compresor propio.** `texconv` es un ejecutable de Windows que no
corre en el CI y que habría que bajar aparte. Pillow comprime DXT1/DXT5, pero
no escribe mipmaps, y comprime peor: recomprimiendo 300 texturas vanilla, su
error fue mayor que el del compresor propio en 297. El propio
(`census/compresor_dxt.py`) usa numpy, comprime un 2048 en 1,5 s, y tiene un
decodificador para poder verificarse.

**Contra qué se verifica.** Pillow es el oráculo, no una dependencia. Su
decodificador y el propio dan lo mismo, byte a byte, en 300 de 300 texturas
del corpus (`compresor_dxt.py --censo`). El CI instala Pillow y un test falla
si falta, para que el autotest no saltee esas comparaciones y diga "OK". De
18 mutaciones del compresor y de su conexión con la fase, 16 las detecta
algún test. Las otras dos tocaban líneas que no cambiaban nada --`argmin` ya
devolvía el índice 0-- y se sacaron.

**Qué formato va a cada mapa.** El `_n` siempre DXT5, aunque su alfa sea todo
255: sigue siendo la máscara, y en DXT1 desaparece. Lo que tenga algún alfa
menor a 255, DXT5. El resto, DXT1. BC7 no: el corpus no tiene ninguno y
`mascara_especular.py` no lee su alfa.

**Opción, no default.** `compresion="ninguna"` sigue siendo el default: sin
numpy la fase anda igual, y quien no pidió compresión recibe lo mismo que
antes. `"dxt"` sin numpy es un error del manifest, antes de correr.

**Lo que salió de rebote.** La cabecera de los DDS sin comprimir llevaba caps
0x1408: `DDSCAPS_MIPMAP` estaba en 0x400 y es 0x400000. Los 22.001 DXT
vanilla con mipmaps tienen 0x401008, y también los 1.999 sin comprimir de una
muestra. El test nuevo de la cabecera lo encontró al comparar con el corpus.

**Qué no se midió.** Nada de esto se vio en el juego. El `_rmaos` de True PBR
sale en DXT1, que comprime juntos tres canales que no se parecen (rugosidad,
metal, oclusión): el error por canal queda en el reporte, y cuánto se nota,
no se sabe.

## Montar y riggear: el enfoque donante, falsificado reconstruyendo el vanilla

Los pasos 5 y 6 (issue #21) no tenían script. El método es el del replacer
del centurión, el único que se probó en el juego con sus animaciones: cada
parte de la IA toma el lugar de una pieza del NIF vanilla --el donante--, que
pone material, particiones, propiedades del shape y esqueleto. Nada de eso se
reconstruye a mano.

**Por qué copiar los pesos del vértice vanilla más cercano.** Da el skin
rígido del proyecto de origen sin programarlo (12 de las 15 piezas del
centurión pesan a un solo hueso), y hereda el reparto donde lo hay: los pies
con `Toe0`, la cabeza con párpados y mandíbula. Perder uno de esos huesos es
perder una articulación sin error (trampa 12), y los controles lo reprueban.

**Cómo se sabe que funciona.** `montar.py --falsificar` usa el vanilla como
respuesta conocida: saca cada pieza, la corre, la gira y la escala como si
viniera de la IA, y exige que cada vértice vuelva a **su** lugar. Con el
centurión: 15 de 15, error máximo 0,0002 unidades. Y exige que un plan con
los extremos cruzados deje la pieza lejos (158 unidades, el 80 % de su
diagonal): la primera versión medía contra el vértice más cercano, y la
cabeza --casi simétrica-- dada vuelta quedaba a solo el 13 %.

**Lo que encontró la falsificación, que ninguna revisión a ojo habría visto:**

- PyNifly agrega a la armature el esqueleto de referencia y lo exporta: 53
  `NiNode` contra 21. `create_bones=False` (trampa 14).
- En Blender 4 los nombres de los grupos de vértices viven en la malla:
  cambiársela al objeto los borra (trampa 15).
- Espejar con `Mesh.transform` no da vuelta las caras (trampa 38).
- Una parte sin capa de color exporta la pieza sin `COLORS`, y ninguna regla
  lo veía: `verificar_export.py` suma la regla `formato`, que en los 1.216
  pares `_0`/`_1` del corpus no reprueba nada (trampa 39).
- PyNifly escribe un `BSShaderTextureSet` por pieza y el centurión vanilla
  comparte uno. No es un defecto: 9.375 de 13.109 NIF vanilla con 2+ shaders
  llevan uno por shader. La regla `bloques` pasó a informarlo.
- Una dirección de giro paralela al eje de la pieza (el pie es largo en Y) no
  fija nada: era una nota y ahora es un error, con `arriba` como alternativa.
- Blender sin interfaz sale con 0 cuando el script revienta. Estaba en los
  cinco scripts de Blender del repo (trampa 37).

**Qué no se hizo.** Nada de esto se vio en el juego. La falsificación prueba
que el montaje pone cada vértice donde el plan dice y que el NIF se parece al
vanilla; que la pieza se vea bien al animarse lo dice el juego. Tampoco hay
todavía un plan con partes reales de un generador: el camino está probado con
el propio vanilla y con una pieza sacada a `.obj`.

## El frontmatter de las skills: lo que el validador de subida acepta

*Issue [#65](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/issues/65), cerrada por el PR [#78](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/pull/78).*

Una reseña externa pidió agregar `version`, `inputs`, `outputs`,
`prerequisites` y `rendering-path` como claves del frontmatter, "porque los
cargadores las esperan". Ninguno las espera: Claude Code decide cuándo cargar
una skill por `name` y `description`. Y el validador de subida de claude.ai y
de la API de Skills (`quick_validate.py` de skill-creator, el que corre
`package_skill.py`) **rechaza** cualquier clave de primer nivel fuera de
`name`, `description`, `license`, `allowed-tools`, `metadata` y
`compatibility`. Escritas como se pedían, las dos skills dejaban de poder
subirse, y Claude Code las seguía cargando: nadie se habría enterado hasta
subirlas.

Lo que el pedido buscaba entra donde el validador lo acepta: los
prerrequisitos en `compatibility` (texto de hasta 500 caracteres) y las
entradas, salidas y rutas de render en `metadata`. **Sin `version`**: nadie la
sube cuando cambia el flujo, y un número que no se mantiene miente. Una copia
instalada se identifica por el commit de `main` desde el que se empaquetó.

`tests/test_frontmatter_skills.py` congela, por igualdad, qué skills hay y qué
claves lleva cada una, y aplica las reglas del validador que se rompen
editando texto. Falsificado: `version` de primer nivel, una subclave nueva en
`metadata` y una `compatibility` de 727 caracteres lo ponen rojo; la primera y
la última, además, las rechaza el validador oficial.

## `nif_nodos.py` sigue duplicado, no en `skills/_shared/`

*Issue [#75](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/issues/75), cerrada por el PR [#78](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/pull/78).*

`nif_nodos.py` está en las dos skills, byte a byte, porque cada una se
empaqueta y se instala sola: `tests/test_skill_empaquetada.py` exige que el
paquete corra sin nada más del repo. La reseña externa propuso sacarlo a un
`skills/_shared/scripts/` común.

**Se queda duplicado.**

- Con `_shared/`, la carpeta de la skill deja de ser la skill. El README dice
  "copiá `skills/<nombre>/` a tu carpeta de skills" y Claude Code la carga
  directo de ahí; una carpeta que importa de `../_shared` revienta apenas se
  copia sola. Para evitarlo, `build_skill.py` tendría que copiar el script en
  cada paquete, y copiar la carpeta a mano dejaría de ser una forma válida de
  instalar.
- El riesgo del duplicado --que las copias diverjan-- ya lo cubre
  `LasDosCopiasSonLaMismaTests` (`tests/test_skill_asset_nuevo.py`), que
  compara byte a byte y existe porque una copia, la que estaba fuera del
  repo, divergió de verdad.
- El costo es chico y visible: un arreglo se aplica dos veces, y si falta la
  segunda, la suite lo dice y nombra el archivo a copiar.

**Cuándo revisarla.** Si aparece un segundo script compartido o una tercera
skill que necesite `nif_nodos.py`. Ahí copiar desde `build_skill.py` empieza a
pagar, y el test de equivalencia tendría que mirar lo que se empaqueta, no la
fuente.

## El NIF de un asset nuevo: la API de PyNifly y un donante de la clase

Cada proyecto de asset nuevo escribió su propio export: siete versiones en el
hacha de dos manos, y uno por proyecto en la de una mano, la espada, el arco,
el escudo ovalado y el de vidrio. Tres llegaron por separado al mismo diseño,
que es el que pasa a `asset-nuevo-skyrim/scripts/exportar_nif.py`:

- **Un donante vanilla de la misma clase**, del que se copian `Prn`,
  `BSXFlags`, `BSInvMarker`, los 63 campos del cuerpo rígido y el material de
  la colisión. No se inventa la estructura: se copia.
- **La receta de shader de cada pieza**, copiada de una pieza vanilla que se
  vea como ella, sin los identificadores del archivo y con los bits que
  dependen de la geometría de ESA pieza apagados. Escrita a mano se pierde
  algo: el script de la espada escribía `flags2 0x8001` y la pieza que
  copiaba tiene `0x8011`.
- **La API de PyNifly, no su exportador**: es el camino de las dos armas que
  se vieron en el juego, y evita lo que el exportador pierde sin avisar
  (trampas 33 y 36 de `modelo-ia-a-skyrim`). Corre adentro de Blender, donde
  el addon ya está: sin la copia suelta de `pyn/` que usaban los proyectos.
- **Escribir, releer, y recién entonces reemplazar**, con dos lectores
  (PyNifly y `nif_nodos.py`) y las REGLAS de `colision_caja.py`.

Probado sobre el escudo ovalado v14 con el escudo enano de donante y la receta
de Dawnbreaker para las gemas: `colision_caja` y `material_arma` pasan, y
contra el v14 que se vio en el juego coinciden raíz, `BSXFlags`, `Prn`,
colisión, material, masa y capa.

**Lo que no hace todavía**: piezas transparentes con *blending* (piden
`BSOrderedNode` y alfa por vértice), piezas skinneadas y colores de vértice.
Una receta con *blending* se rechaza con el motivo. *(Después: el vidrio llegó,
y sin `BSOrderedNode`; ver "Las piezas transparentes, sin BSOrderedNode".)*

### El segundo archivo compartido (issue [#75](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/issues/75), revisada)

`exportar_nif.py` corre en Blender, así que `asset-nuevo-skyrim` necesita
`correr_en_blender.py` (`test_blender_sale_bien.py` lo exige), que vivía en
la otra skill. Es el segundo archivo compartido, el caso en que la decisión
de #75 decía revisarla. Se revisó y **se sigue copiando**: son 26 líneas. Lo
que cambia es el ancla. En vez de un test por archivo copiado,
`LoCompartidoEntreSkillsTests` enumera todo nombre que esté en las dos
carpetas de scripts, exige que sean el mismo archivo byte a byte, y congela
la lista por igualdad: un tercer compartido obliga a decidir.
