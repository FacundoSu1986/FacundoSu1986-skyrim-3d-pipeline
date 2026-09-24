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
  ese archivo-- y el `_n` es el primer mapa que lo va a pedir.
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
