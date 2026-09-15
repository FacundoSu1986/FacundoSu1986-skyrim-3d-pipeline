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
