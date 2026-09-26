# Qué se comprueba, y qué no

Todos los controles del repo en un lugar: qué afirma cada uno, con qué número
del corpus vanilla se sostiene, qué test se pone rojo si alguien lo rompe, y si
el CI lo corre. Sale del código, no de memoria: `tests/test_validacion_al_dia.py`
compara los flags de esta página con los que los scripts aceptan de verdad, en
los dos sentidos. Un flag documentado que no existe lo pone rojo, y uno nuevo
sin documentar también (issue
[#73](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/issues/73)).

## Cómo leerla

- **REGLA** reprueba y lleva atrás cuántos archivos vanilla la cumplen.
  **OBS** se informa y no reprueba. Una regla que el corpus no sostiene no se
  escribe como regla: en este repo el error caro es que sobren reglas
  inventadas, no que falten.
- **Códigos de salida** de los controles sobre archivos: 0 si pasa; **1 si no
  pasa o si no hubo nada que comprobar**, porque cero comprobaciones no es
  éxito; 2 si los argumentos no sirven. `comparar.py` usa 0 y 1.
- **¿En CI?** "sí": un test lo ejercita en cada PR. "vacío": en CI solo se
  prueba que sobre una carpeta vacía no dé éxito. "no": necesita el juego
  extraído o Blender.
- Las cifras salen del docstring de cada script. Si alguna difiere, manda el
  script.

## 1. Sobre tu asset, antes de entregarlo

| control | qué afirma | la cifra que lo sostiene | se pone rojo si lo rompés | ¿en CI? |
|---|---|---|---|---|
| `verificar_export.py <nuevo.nif> <vanilla.nif>` | 13 REGLAS contra el vanilla: `version`, `comparables`, `bloques`, `raiz`, `nodos`, `posiciones`, `orientacion`, `piezas`, `formato`, `colocacion`, `huesos/pieza`, `body parts`, `skin` | cada una con su número en el docstring; `formato` no reprueba ninguno de los 1.216 pares `_0`/`_1` del corpus | `test_verificar_export.py`, sobre NIF sintéticos | sí |
| `verificar_uv.py <origen.obj> <exportado.nif>` | REGLA `v_invertida`: la V del NIF es 1 − V del OBJ en la mayoría de los vértices apareados. Si no aparea ninguno, reprueba. La caja del NIF es la de todas sus piezas juntas | `[INVARIANT]`: la convención del NIF (`census/hallazgos_uv.md`) | `test_verificar_uv.py` y el autotest | sí |
| `salud_malla.py <antes> <despues>` | REGLAS `borde` y `piezas`: decimar no puede sumar aristas de borde ni partir la malla. Las piezas de un mismo marco se miden soldadas entre sí. OBS: `ratio`, `no_manifold`, `winding` | mide el mismo asset antes y después; la regla se sostiene con `--falsificar` (sección 2) | `test_salud_malla.py` y el autotest | sí |
| `salud_malla.py --uv <antes> <despues>` | REGLA del paso 4b: rehacer las UV no cambia la geometría soldada (vértices, triángulos, aristas, borde, no-manifold, winding, piezas) | `[INVARIANT]`: desplegar escribe coordenadas de textura, no posiciones | `test_salud_malla.py` | sí |
| `material_arma.py <arma.nif> [--clase <clase>]` | REGLAS `cierre`, `envmap`, `glow` y, en armas, `cubemap`. OBS: el tipo de shader contra las armas de su clase | 74.489 de 74.489 bloques cierran; 6.843 de 6.843 EnvMap con su flag; 1.396 con Glow y 73.093 sin; 149 de 149 armas EnvMap con cubemap | `test_material_arma.py` y el autotest | sí |
| `mascara_especular.py --arma <textura_n.dds>` | REGLA: en un `_n` de arma, como mucho el 10 % de los bloques con alfa 255. Sin `--arma` solo informa (OBS) | las 140 `_n` de armas del corpus quedan por debajo del 6,9 %; en objetos portables la mediana es 0,00 %, pero 59 de 1.201 están saturados | `test_mascara_especular.py` y el autotest | sí |
| `proporciones_arma.py <malla.nif> [--clase <clase>]` | REGLA: cada proporción dentro del [mín, máx] de su clase. OBS: en qué percentil cae | el rango de cada clase en el corpus (el de "las armas" no existe: `census/hallazgos.md`) | `test_proporciones_arma.py` y el autotest | sí |
| `colision_caja.py <archivo.nif>` | REGLAS `radio` (`bhkRadius` = mín(semieje menor, 0,1)) e `inercia` (masa > 0 ⇔ diagonal de inercia > 0) | 2.667 de 2.684 cajas, exacto; 1.194 de 1.194 cuerpos, en los dos sentidos | `test_colision_caja.py` y el autotest | sí |
| `verificar_plugin.py <MiMod.esl>` | 4 REGLAS: `formVersion` 44 en cada record; índice de mod ≤ cantidad de masters; WEAP con DATA de 10 bytes y DNAM de 100; el `Prn` del NIF según el tipo de animación | 10.273 de 10.273 records autorados para SE; 1.188.810 de 1.188.811; 3.359 de 3.359 WEAP; 305 de 306 armas del jugador | `test_verificar_plugin.py`, `test_prn_arma.py` y el autotest | sí |
| `esl.py <plugin.esp> --marcar` | antes de marcar, que el plugin pueda ser ESL: los FormIDs nuevos caben en 0xFFF (los overrides no cuentan y el piso 0x800 del Creation Kit solo se informa). Sin `--marcar` solo informa; no escribe si el recorrido de records no cierra | `census/hallazgos_plugins.md` | `test_skill_asset_nuevo.py`, `test_parser_esm.py` | sí |
| `exportar_nif.py -- <plan.json> <asset.blend>` y `exportar_nif.py -- --falsificar` (Blender) | el NIF de un asset nuevo con la estructura del donante; antes de reemplazar el definitivo lo relee con PyNifly y con `nif_nodos.py` (piezas, triángulos, shader, texturas, la V, `Prn`, los bloques de colisión) y le pasa las REGLAS de `colision_caja.py`. Rechaza recetas con *blending* y donantes sin inercia. `--falsificar`: un donante sintético y tres planes, uno bueno y dos que tienen que reprobar | las de `colision_caja.py`; la inercia es heurística declarada | la parte pura: `test_exportar_puro.py` y el autotest de `exportar_puro.py`, con cuatro mutantes que lo ponen rojo; con `BLENDER_EXE`, `test_exportar_nif_blender.py` | la parte pura |
| `comparar.py --contrato <archivo.nif> [<textures/>]` | las REGLAS del censo para un NIF entregable: cabecera SE, BS 100, raíz conocida, geometría legible, texturas DDS con separador de Windows, identidad del `bhkRigidBody`; y en cada DDS: parsea, tamaño, potencia de dos, alfa en el `_n` | 22.394 de 22.394 comparten cabecera; 22.393 de 22.394 son BS 100 | `test_contrato_texturas.py`, `test_fixture_vanilla.py` | sí |
| `comparar.py --fiel <original.nif> <exportado.nif>` | la COLOCACIÓN: cada shape y la colisión quedan donde estaban | el round-trip de PyNifly movió colisiones del corpus y el contrato daba verde (`fixtures/pynifly.md`) | `test_colocacion.py` | sí |
| `desplegar_uv.py -- <baja.blend> [--capa UV_Bake] [--margen 0.002]` y `desplegar_uv.py -- --falsificar` (Blender) | REGLAS `empaquetado` (igualar y empaquetar tiene que mover las UV: si no, `pack_islands` corrió en vacío), `rango` (todo en el cuadro 0..1) y `solape`. Si reprueba, no guarda. `--falsificar` despliega dos mallas sintéticas sin marcar las UV (tiene que reprobar) y marcándolas (tiene que pasar) | el tope de solape es el mismo de `hornear.py`; `[MEASURED]` en Blender 4.4.1, sin marcar las UV el empaquetado no mueve nada (trampa 17) | la parte pura: el autotest de `horneado_puro.py` (`juzgar_despliegue`); con `BLENDER_EXE`, `test_desplegar_uv_blender.py` | la parte pura |
| `hornear.py -- <baja.blend> <carpeta> <res> <alta.blend> [--permitir-solape]` (Blender) | corta ANTES de hornear si la resolución no es potencia de 2, si falta la alta, si la UV activa no es la de render, si la alta no está donde está la baja, o si más del 0,1 % de la huella UV se pisa (`--permitir-solape` lo baja a aviso). Avisa, sin cortar, por texeles sin alta, densidad dispareja entre piezas, luz horneada (albedo correlacionado con el AO) y albedo casi negro | el tope de solape es el "nada de solape" del censo; los avisos son criterio `[no medido]` | la parte pura: `test_horneado_puro.py` y el autotest de `horneado_puro.py` | la parte pura |
| `al_marco.py -- <plan.json> <baja.blend> <salida.blend> [<alta.blend> <salida_alta.blend>]` y `al_marco.py -- --falsificar` (Blender) | la misma matriz a la baja y a la alta; cada eje del marco fijado una vez (ancla o tope); rotación propia por construcción. Rechaza escala negativa (trampa 38), modificadores sin aplicar, mallas compartidas y escribir sobre la entrada; remide el largo y los topes en Blender antes de guardar. `--falsificar`: cuatro puntos conocidos, uno de ellos el que delata un espejo | los números del plan salen de medir los vanilla de la clase | la matemática: el autotest de `montaje_puro.py`, con tres mutantes (espejo, tope al revés, redondeo sin corregir) que lo ponen rojo; con `BLENDER_EXE`, `test_al_marco_blender.py` | la parte pura |
| `montar.py -- <plan.json>` (Blender) | al escribir el NIF, los pesos (REGLAS `suma`, `max4`, `particion` y `huesos` de `montaje_puro.py`) y `verificar_export` contra el donante. Sale 0, 1 o 2 como los demás | ver `verificar_export` | la parte pura: `test_montaje_puro.py` y el autotest de `montaje_puro.py` | la parte pura |
| `preparar_parte.py` (Blender) | no reprueba: avisa si el decimado quedó más de un 15 % arriba del presupuesto, y dice si la soldadura tiene que ser más chica o más grande. Lo que reprueba es `salud_malla.py` sobre sus `.obj` | — | — | no |
| `uv_exportacion.conservar_uv(mesh, nombre)` (Blender, desde un script) | deja una sola UV, activa y de render, sin cambiar sus coordenadas. Rechaza antes de borrar: Edit Mode, malla con más de un usuario, nombre ausente. Devuelve avisos de nodos del material que nombraban una capa borrada. `montar.py` no lo llama: PyNifly exporta la UV activa (trampa 40) | `[OBSERVED]` en Blender 4.4.1: el bucle viejo falla en 4 de los 6 órdenes de capas | `test_uv_exportacion.py` (malla falsa); con `BLENDER_EXE`, `test_uv_exportacion_blender.py` corre la malla real y el control negativo | la lógica sí; la API real de Blender, no |
| fase de texturas (`pipeline/texturas.py`) | cada DDS escrito pasa por `fixtures/comparar.py`; la máscara del `_n` se mide y pide revisión si sale de lo vanilla; el error de compresión va al reporte. Y el runner no llega a PUBLISHED mientras quede una fase stub | ver `mascara_especular.py` y `compresor_dxt.py` | `test_pipeline_texturas.py`, `test_pipeline_gate_stubs.py` | sí |

## 2. Contra el corpus vanilla

Las falsificaciones prueban que las REGLAS de arriba son ciertas, corriéndolas
sobre el juego: el vanilla tiene que pasar tal cual, y cada rotura tiene que
reprobar. Los censos recalculan los números que las reglas citan. Todo esto
necesita los archivos extraídos de los BSA, que el repo no trae.

| comando | qué hace | ¿en CI? |
|---|---|---|
| `salud_malla.py --falsificar <meshes>` | sobre hasta 10 mallas vanilla de 200 triángulos o más: agujerear, invertir y duplicar al lado tienen que hacer crecer su campo, y `borde` y `piezas` tienen que reprobar | no |
| `verificar_export.py --falsificar <meshes>` | pares de NIF vanilla reales con el resultado esperado escrito a mano: cuántas fallas y de qué regla | no |
| `colision_caja.py --falsificar <meshes>` | sobre cajas reales del corpus: torcer cada campo tiene que reprobar | no |
| `material_arma.py --falsificar <meshes>` | ninguna arma vanilla reprueba; después, cinco roturas del material y cada una la tiene que atrapar su regla | no |
| `material_arma.py --censo <meshes>` | recalcula los números de sus REGLAS | no |
| `verificar_plugin.py --falsificar <Data>` | sobre plugins reales: los que pasan tal cual son el patrón, y torcer cada campo tiene que reprobar. Los masters de 2011 quedan afuera a propósito (no pasan la REGLA 1) | vacío |
| `verificar_plugin.py --falsificar-prn <Data> <meshes>` | sobre las armas base de los 10 plugins con sus NIF: ponerles cualquier otro `Prn` tiene que reprobar | vacío |
| `montar.py -- --falsificar <donante.nif> [<esqueleto.nif>]` (Blender) | saca cada pieza del donante, la corre, la gira y la escala como si viniera de la IA, y la vuelve a montar con el plan | no |
| `proporciones_arma.py --censo <meshes/weapons>` | la tabla de rangos por clase | no |
| `mascara_especular.py --censo <textures>` | la máscara de los `_n` del corpus | no |
| `compresor_dxt.py --censo <textures> [--maximo N]` | compara el decodificador DXT con el de Pillow, píxel por píxel | no |
| `parser_nif.py --autotest <meshes>` | reproduce los valores medidos del corpus | no |
| `parser_nif.py --censo <carpeta> --salida censo.jsonl` | el censo de mallas | no |
| `parser_dds.py --autotest <textures>` | la identidad de tamaño de cada DDS del corpus | sí, sobre DDS sintéticos |
| `parser_dds.py --censo <carpeta> --salida censo_dds.jsonl` | el censo de texturas | no |
| `parser_uv.py --autotest [<corpus>]` | sin corpus, la suite analítica (solapes conocidos de antemano); con corpus, además los casos medidos | sí, sin corpus |
| `parser_uv.py --censo <carpeta> --salida censo_uv.jsonl` | el censo de UV | no |
| `parser_colision.py --autotest <meshes>` | la identidad de tamaño de la geometría de colisión | vacío |
| `parser_esm.py --autotest <Data>` | los conteos medidos de los plugins del juego | vacío |
| `parser_plugin.py --autotest <Data>` | que el recorrido de grupos y records caiga exacto en el fin de cada archivo | no |
| `censo_nif.py --autotest <corpus>` | los valores fijados archivo por archivo en su tabla `AUTOTEST` | no |
| `censo_nif.py --censo <carpeta> --salida censo.jsonl` | la semilla del censo | no |
| `nif_nodos.py --autotest <meshes>` | reproduce los valores medidos de archivos concretos, su tabla `AUTOTEST` (las dos copias son el mismo archivo) | vacío |
| `esl.py --autotest <Data>` | reproduce los conteos de ESL medidos | vacío |
| `census/verificar.py <raíz> [--json salida.json]` | la identidad de tamaño de cada bloque de los 22.394 NIF | no |
| `registrar.py <meshes> <textures> --verificar` | vuelve a medir el estático de referencia y lo compara con el JSON versionado, sha256 incluido | no |
| `comparar.py --identico <archivo.nif>` | la referencia campo por campo contra `fixtures/roadsignwhiterun01.json` | no |

## 3. Los autotests que no necesitan el corpus

Corren con Python solo. Los de las skills el CI los corre desde el paquete que
arma `build_skill.py`, extraído lejos del repo (`test_skill_empaquetada.py`):
un script que importe algo de `census/` anda en el repo y no instalado, y ahí
se ve.

| comando | cómo lo corre el CI |
|---|---|
| `verificar_uv.py --autotest` | desde el paquete, y `test_verificar_uv.py` |
| `salud_malla.py --autotest` | desde el paquete, y `test_salud_malla.py` |
| `material_arma.py --autotest` | desde el paquete, y `test_material_arma.py` |
| `mascara_especular.py --autotest` | desde el paquete, y `test_mascara_especular.py` |
| `proporciones_arma.py --autotest` | desde el paquete, y `test_proporciones_arma.py` |
| `horneado_puro.py --autotest` | desde el paquete, y `test_horneado_puro.py` |
| `montaje_puro.py --autotest` | desde el paquete, y `test_montaje_puro.py` |
| `colision_caja.py --autotest` | desde el paquete, y `test_colision_caja.py` |
| `verificar_plugin.py --autotest` | desde el paquete, y `test_verificar_plugin.py` |
| `compresor_dxt.py --autotest` | `test_compresor_dxt.py`, con Pillow de oráculo |
| `exportar_puro.py --autotest` | desde el paquete, y `test_exportar_puro.py` |
| `escritor_dds.py --autotest` | ningún test lo llama: `test_escritor_dds.py` prueba el escritor por su cuenta |
| `escritor_plugin.py --autotest` | ningún test lo llama: `test_plugin.py` y `test_verificar_plugin.py` prueban el escritor por su cuenta |

## 4. Qué corre el CI

`.github/workflows/ci.yml`, en Python 3.11 y 3.12:

1. `pip install -r requirements-dev.txt`: numpy, y Pillow como oráculo.
2. `compileall` sobre `census`, `skills`, `tests`, `pipeline` y `fixtures`:
   la sintaxis de todo, incluidos los scripts de Blender, que fuera de Blender
   no se pueden importar.
3. `test_skill_empaquetada.py`: cada skill empaquetada y extraída lejos del
   repo tiene que importar y pasar sus autotests.
4. La suite entera: `python -m unittest discover -s tests`.

Lo que el CI **no** cubre: la sección 2 (necesita el juego extraído), los
scripts de Blender más allá de su sintaxis y de que terminen con
`correr(main)` (`test_blender_sale_bien.py`), y el juego.

## 5. Lo que ningún control mide

- **Que se vea bien en el juego.** Los bytes dicen que un archivo está bien
  formado y que la geometría quedó donde iba, no que el juego lo cargue ni
  cómo se ve. Lo visto en el juego está en el "Estado" del README; el proceso
  es la issue
  [#31](https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline/issues/31).
- **Que sea lindo.** Un asset puede pasar todos los controles y ser feo.
