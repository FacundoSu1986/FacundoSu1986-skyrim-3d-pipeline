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

## Recomendación pendiente (no bloqueante)

`skills/modelo-ia-a-skyrim/scripts/censo_nif.py` (semilla, #6) y
`census/parser_nif.py` (versión completa, #7) se solapan conceptualmente. Conviven
en carpetas distintas y no chocan como archivo, pero conviene, en un PR futuro,
dejar la skill apuntando al parser de `census/` o documentar explícitamente por
qué se mantienen dos. Se deja fuera de la integración para no reescribir el
parser de otro autor.
