# Hallazgos del censo de `meshes/` — Skyrim SE (22.394 NIF)

Fuente: `meshes/` (22.394 archivos .nif, solo lectura). Parser: `parser_nif.py` (CLI `censo_nif.py`); auditoría estructural: `verificar.py`; consultas: `agregados.py`; datos: `censo.jsonl` (22.394 filas, 0 con error). `clase` = primera carpeta de `ruta_relativa`; archivos sueltos en la raíz de `meshes/` = `(raiz)`. Donde un id no tiene nombre en el spec se reporta el id crudo.

---

### 1. Suite de falsificación del parser
**AFIRMACIÓN**: El parser reproduce exactamente los seis archivos de referencia, incluidos los 6.007 triángulos de `steamcenturion.nif` (geometría en `NiSkinPartition`), los BSXFlags 130/194/203/523, los conteos de bloques (112/9/10/20) y la raíz de cada archivo. Total: 75 comprobaciones, 0 fallas.
**CONSULTA QUE LA PRODUJO**: `python parser_nif.py --autotest meshes`
**N**: 6 archivos mandatados (21 valores exactos) + 54 comprobaciones adicionales de campos nuevos
**EXCEPCIONES ENCONTRADAS**: 0 de 75 fallas. Durante el desarrollo se detectó y corrigió un caso que rompía el parseo: `BSFurnitureMarkerNode` no hereda de NiNode (hereda de BSFurnitureMarker ← NiExtraData); incluirlo hacía fallar 123 archivos de muebles, hoy 0.

### 2. Cotas de sanidad de la cadena de skinning
**AFIRMACIÓN**: Pesos por vértice = 4 en las 42.243 particiones (cota ≤4 nunca violada). Los arrays `Bones[]` de cada partición indexan siempre dentro de la lista de huesos de su skin instance (0 violaciones) y los índices de hueso por vértice son siempre < `numBones` (0 violaciones). La cota literal "huesos por partición ≤ cantidad de NiNode del archivo" NO se cumple en 1.095 de 42.243 particiones: el array va padded (4 ranuras típico) en piezas de 2-3 nodos; p.ej. `actors/character/character assets/eyesargonian.nif` declara `numBones=4` con array `(0,0,0,0)` sobre una instancia de 1 hueso. Máximo real de `numBones`: 60 (`actors/alduin/alduin.nif`, 78 nodos del archivo).
**CONSULTA QUE LA PRODUJO**: barrido de `NiSkinPartition` sobre `meshes/` (leyendo `numBones`, `Bones[]` y los índices por vértice) + `python verificar.py meshes`
**N**: 42.243 particiones
**EXCEPCIONES ENCONTRADAS**: 0 de 42.243 violaciones de índices (los dos invariantes reales); 1.095 de 42.243 superan la cota literal por padding (en esas mismas particiones la identidad de tamaño de bloque y los índices válidos se cumplen igual).


### 3. Identidad de tamaño de bloque en todo el corpus
**AFIRMACIÓN**: Cada bloque que el censo lee termina exactamente en `offset + size` declarado por la cabecera del archivo: 82.694 shapes (60.737 `BSTriShape` + 21.957 `BSDynamicTriShape`), 42.243 particiones, 11.263 rigid bodies, 63.709 texture sets, 82.808 shader properties, 13.223 BSXFlags y 22.394 trailers de archivo. Ninguna identidad falla.
**CONSULTA QUE LA PRODUJO**: `python verificar.py meshes --json verif_resumen.json`
**N**: 22.394 archivos
**EXCEPCIONES ENCONTRADAS**: 37 shapes sin geometría propia (`tri=0, dataSize=0`, sin skin): son placeholders de efectos (p.ej. `effects/mg07labyrinthianlightbeam.nif` ×3, `magic/impactshock02.nif` ×1). 1 archivo con BS version 83 (`creationclub/_shared/dungeons/ayleidruins/interior/triggers/artrigpressureplate01.nif`), el único ≠ (20.2.0.7/12/100); parsea sin error.

### 4. Constantes uniformes medidas
**AFIRMACIÓN**: `NumWeightsPerVertex = 4` en las 42.243 particiones; `NumTextures = 9` en los 63.709 `BSShaderTextureSet`; el archivo termina siempre con el trailer de 8 bytes `01 00 00 00 00 00 00 00`; `VertexSize` de partición = `(VertexDesc & 0xF) × 4` en los 27.985 bloques `NiSkinPartition`.
**CONSULTA QUE LA PRODUJO**: `python verificar.py meshes` (categorías `numw`, `texset_num`, `trailer`) + barrido `VertexSize` vs `(desc & 0xF)*4` sobre `meshes/`
**N**: 42.243 / 63.709 / 22.394 / 27.985
**EXCEPCIONES ENCONTRADAS**: 0 de 42.243 con pesos/vertice ≠ 4; 0 de 63.709 con texturas ≠ 9; 0 de 22.394 con trailer distinto; 0 de 27.985 bloques con la identidad de `VertexSize` rota.

### 5. (a) Tipo de nodo raíz × carpeta y la mezcla con skinning
**AFIRMACIÓN**: `BSFadeNode` NO es exclusivo de estáticos: 3.641 de 18.526 (19,65%) tienen skin. `NiNode` es casi puro skinneado: 3.387 de 3.418 (99,09%); sus 31 estáticas son piezas auxiliares (pelucas `hairshorthumanfold.nif`, anillos, primera persona). `BSTreeNode` es 71/71 skinneado. La matriz raíz × carpeta muestra que `NiNode` como raíz se concentra en `armor` (1.151), `actors` (838), `clothes` (775), `dlc02` (317) y `dlc01` (239); `BSFadeNode` domina en las carpetas estáticas (`actors` 3.423, `dungeons` 3.216, `architecture` 2.941, `clutter` 1.727).
**CONSULTA QUE LA PRODUJO**: `python agregados.py a`
**N**: 22.394 (BSFadeNode 18.526; NiNode 3.418; BSLeafAnimNode 286; BSMasterParticleSystem 93; BSTreeNode 71)
**EXCEPCIONES ENCONTRADAS**: 3.641 skinneadas con raíz `BSFadeNode` (p.ej. `_resourcepack/landscape/plants/lilypadcluster01.nif`, `_byoh/clutter/food/floursack01.nif`); 31 estáticas con raíz `NiNode`.

### 6. (b) BSXFlags: distribución, sin valor estándar
**AFIRMACIÓN**: 9.171 archivos (40,95%) no tienen bloque BSXFlags; entre los 13.223 que sí, hay 62 valores distintos. Frecuencias: 130 → 7.654 (34,18%); 194 → 1.363; 1 → 846; 545 → 479; 139 → 343; 642 → 278; 32 → 241; 11 → 219; 513 → 205. Bits más usados: bit1 (11.203 archivos), bit7 (10.623), bit0 (2.891), bit6 (1.859), bit3 (1.492), bit9 (1.199).
**CONSULTA QUE LA PRODUJO**: `python agregados.py b`
**N**: 22.394
**EXCEPCIONES ENCONTRADAS**: 0 de 22.394 con bits fuera de las posiciones 0–7 y 9 (bit8 y ≥10 nunca aparecen). Frecuencia por clase: 130 domina en `dungeons` (2.786) y `architecture` (2.100); 194 en `clutter` (498) y `weapons` (223); 545 en `effects` (273) y `sky` (160).

### 7. (c) Formas bhk* × clase, material Havok × clase
**AFIRMACIÓN**: 11.200 archivos tienen colisión, 26 tipos bhk distintos. Arquitectura y mazmorras usan el par MOPP+mesh comprimida (architecture: `bhkMoppBvTreeShape` ×2.442 con `bhkCompressedMeshShape` ×2.431; dungeons: ×2.900 con ×2.897); objetos sueltos y armas usan convexos/cajas (`weapons`: `bhkBoxShape` 153, `bhkConvexVerticesShape` 112, `bhkListShape` 100, 0 MOPP). El campo Material del shape (N=3.501 archivos, 0 fuera del enum del spec): `clutter`→WOOD 188, BOTTLE_SMALL 122, HEAVY_METAL 111, SOLID_METAL 94; `clothes`→CLOTH 112; `plants`→GRASS 71; `weapons`→BLADE_1HAND 47, SOLID_METAL 47, AXE_1HAND 47; `armor`→SOLID_METAL 42, HEAVY_METAL 42. Materiales por chunk de mallas comprimidas (12.069 entradas, 0 fuera del enum): `dungeons`→STONE 1.940, GRAVEL 496, ICE 428, BROKEN_STONE 364, WOOD 362; `architecture`→STONE 1.515, WOOD 1.086. Layer: STATIC domina en dungeons/architecture (2.918/2.478), CLUTTER en clutter (556), WEAPON en weapons (256). Motion system: BOX_STABILIZED domina en estáticos; SPHERE_STABILIZED en clutter/weapons.
**CONSULTA QUE LA PRODUJO**: `python agregados.py c`
**N**: 11.200 con colisión; 3.501 con Material de shape; 12.069 materiales de chunk
**EXCEPCIONES ENCONTRADAS**: 91 archivos de `architecture` usan `bhkBoxShape` en vez de MOPP (91 de 2.941 de la clase). Constraints y phantoms repartidos en 15 clases: `bhkLimitedHingeConstraint` (188: `clutter` 90, `actors` 57, `armor` 14), `bhkRagdollConstraint` (76: `actors` 59), `bhkSimpleShapePhantom` (176: `actors` 37, `traps` 31, `effects` 20, `dlc01` 17, `water` 16); `bhkBallSocketConstraintChain` (5) solo en `traps`. 137 archivos tienen >1 rigid body (los campos layer/mass/motion se tomaron del primero del archivo).

### 8. (d) Triángulos por clase: mediana / p90 / máximo
**AFIRMACIÓN**: Mediana (p90 / máx): `actors` 3.685 (4.692 / 42.438); `dungeons` 1.172 (5.055 / 117.216); `architecture` 480 (3.466 / 114.803); `armor` 996 (3.718 / 14.146); `clothes` 826 (3.100 / 15.161); `clutter` 514 (2.228 / 22.866); `dlc02` 906 (4.706 / 39.415); `dlc01` 797 (3.616 / 29.420). Total del corpus: 43.282.883 triángulos en 82.694 shapes.
**CONSULTA QUE LA PRODUJO**: `python agregados.py d`
**N**: 22.394 (la tabla completa por las 32 clases está en la consulta)
**EXCEPCIONES ENCONTRADAS**: el máximo absoluto es 117.216 (`dungeons/dwemer/animated/astrolabe/armillary/dweastrolabearmillary01.nif`), seguido de 114.803 (`architecture/skyhaventemple/skyhaventempletemplayout01.nif`) y 107.533 (`effects/fxtg09nocturnalbirds.nif`). Hay 463 archivos con 0 shapes (marcadores/placeholders, p.ej. `camera*`); `cameras` (106 de 120), `mps` (90 de 92) y `shadertests` (13 de 16) son clases mayormente sin geometría.

### 9. (e) Vértices por shape: techo global
**AFIRMACIÓN**: El máximo global es 36.138 vértices en un shape (`dlc02/architecture/telvannitower/dlc2telmithryndiseased02.nif`). Ningún shape del corpus supera el 75% del límite de 16 bits (49.151): 0 shapes. Distribución: 82.569 shapes <10k vértices; 104 en [10k,20k); 14 en [20k,30k); 7 en [30k,40k).
**CONSULTA QUE LA PRODUJO**: `python agregados.py e`
**N**: 82.694 shapes
**EXCEPCIONES ENCONTRADAS**: 0 de 82.694 con ≥49.151 vértices; solo 21 shapes superan 20.000. Los 7 con ≥30.000: `dlc02/architecture/telvannitower/dlc2telmithryndiseased02.nif` 36.138; `dlc02/dungeons/apocrypha/exterior/apoexttowerbase02.nif` 35.600; `dungeons/ship/shipwrecklarge02.nif` 34.612; `dlc02/architecture/thirsk/meadhall/dlc2thirskmeadhallinterior01.nif` 32.983; `dlc01/architecture/dawnguard/dextcorner02.nif` 32.716; `architecture/solitude/sbardscollege.nif` 31.715; `dungeons/ship/shipwrecklarge01.nif` 31.494.

### 10. (f) Huesos por vértice por criatura: rígidas vs skinneadas
**AFIRMACIÓN**: En `actors/` ninguna de las 42 carpetas con skin es 100% rígida (máx ≤ 1); las más rígidas: `dwarvensteamcenturion` máx=2 (5.845 vértices a 1 hueso, 913 a 2), `atronachstorm` máx=2 (2.924/25), `dwarvenspider` máx=3. Histograma global de influencias por vértice: 1 hueso → 9.045.224; 2 → 2.850.056; 3 → 1.311.467; 4 → 337.397. En todo el corpus, 544 archivos tienen TODOS sus vértices a 1 hueso.
**CONSULTA QUE LA PRODUJO**: `python agregados.py f`
**N**: 4.261 archivos en `actors/` (42 carpetas con skin)
**EXCEPCIONES ENCONTRADAS**: `character` concentra 7,07M vértices a 1 hueso y 1,18M a 2; `alduin` reparte 3.017/3.558/3.003/1.795 entre 1/2/3/4; un solo vértice del corpus en autómata llega a 4 huesos (`dwarvenspherecenturion`, 1 de 9.039); `dwarvenspider` y `mudcrab` no pasan de 3.

### 11. (g) body_part_id: existencia, flags y assets
**AFIRMACIÓN**: Existen 31 ids distintos en 30.468 registros de partición. Flags observados: solo {0, 1, 256, 257}. Los más frecuentes: 131 (HAIR) ×6.607 [257:3.422; 1:2.377; 256:688; 0:120]; 130 (HEAD) ×5.428; 141 (LONGHAIR) ×4.943; 230 ×4.074; 143 (EARS) ×3.184 [1:3.180]. Los ids de armadura clásicos: 32 BODY ×2.112, 34 ×1.136, 33 ×645, 38 ×603. Con flag 256 exclusivamente: 142 ×171, 150 ×12.
**CONSULTA QUE LA PRODUJO**: `python agregados.py g`
**N**: 30.468 registros en 22.394 archivos
**EXCEPCIONES ENCONTRADAS**: 0 de 30.468 con flags fuera de {0,1,256,257}. Id 60 (MOD_MISC2) aparece 1 sola vez (`dlc02/effects/.../dlc2apocryphabookwarp01.nif`, flag 1); id 5 (BP_RIGHTARM) 2 usos en `armor`; id 1 (BP_HEAD) 46 usos en `actors`; 42 (CIRCLET) ×15 en clothes/creationclub/dlc01/magic; 41 (LONGHAIR) ×11 en actors.

### 12. (h) Combinaciones flags1/flags2 observadas
**AFIRMACIÓN**: 80.793 shapes con flags; 848 combinaciones distintas; la modal `flags1=0x82400301, flags2=0x00008021` cubre 22.164 (27,43%). Top-5: `0x82400301/0x8021` 27,43%; `0x82400300/0x8021` 5,74%; `0x82420303/0x02008081` 3,97%; `0x82401703/0x02008021` 3,87%; `0x82400381/0x8021` 3,76%.
**CONSULTA QUE LA PRODUJO**: `python agregados.py h`
**N**: 80.793 shapes con shader (8.248 `BSEffectShaderProperty`, 74.492 `BSLightingShaderProperty`, 35 sky, 33 water; 1.901 shapes sin shader)
**EXCEPCIONES ENCONTRADAS**: 182 combinaciones aparecen 1 sola vez; 848 distintas en total (la cola es larga, no hay un conjunto cerrado).

### 13. (i) Ranuras de textura pobladas × tipo de shader
**AFIRMACIÓN**: `Default` (N=45.755): `[0,1]` 92,18%; `[0,1,2]` 3,80%; `[0,1,7]` 2,83%. `Environment Map` (N=6.837): `[0,1,4]` 57,82%; `[0,1,4,5]` 36,04%. `Eye Envmap` (N=3.370): `[0,1,2,4,5]` 95,40%. `Face Tint` (N=3.274): `[0,1,2,3,6,7]` 98,38%. `Hair Tint` (N=11.254): `[0,1]` 99,86%. `Effect` (N=6.516): fuente `[0]` + greyscale `[0,1]`: `[0,1]` 50,46%, `[0]` 21,70%, 1.807 sin ranuras.
**CONSULTA QUE LA PRODUJO**: `python agregados.py i`
**N**: 80.793 shapes con shader
**EXCEPCIONES ENCONTRADAS**: 1 shape `Default` puebla `[0,1,4,5,6]` (1 de 45.755); `Parallax` 11/11 `[0,1,3]`; `Sky` 5/35 con `[0]`, resto vacío; `Water` 33/33 sin ranuras; `MultiLayer Parallax` reparte entre 10 combinaciones (la top `[0,1,4,6,7]` 42,90%).

### 14. (j) Archivos no parseables
**AFIRMACIÓN**: 0 archivos fallaron al parsear; los 22.394 entran al censo con datos completos.
**CONSULTA QUE LA PRODUJO**: `python agregados.py j`
**N**: 22.394
**EXCEPCIONES ENCONTRADAS**: 0 de 22.394 con campo `error`. Quedan dos límites de cobertura, ambos medidos y dentro del censo: 37 shapes placeholder sin geometría (§3) y 1 archivo de BS version 83 que no corresponde a la variante SSE/100 de los otros 22.393 (§3).

### 15. Cobertura del censo
**AFIRMACIÓN**: 22.394 archivos; 82.694 shapes; 43.282.883 triángulos; 7.103 archivos skinneados (BSDismemberSkinInstance 16.368 bloques / NiSkinInstance 11.644) y 15.291 estáticos; 11.200 con colisión; 463 sin ningún shape; 13.223 con bloque BSXFlags; 66.797 bloques `bhk*` en total; 63.709 `BSShaderTextureSet`; 82.808 shader properties.
**CONSULTA QUE LA PRODUJO**: `python agregados.py j` + bloques de `censo.jsonl`
**N**: 22.394
**EXCEPCIONES ENCONTRADAS**: 0 de 22.394 archivos fuera del censo (ningún archivo fue salteado en silencio).

### 16. (#19) Reparto de los tipos de shape, y el 17 % que la semilla no veía
**AFIRMACIÓN**: De los 82.694 shapes del corpus, **60.737 son `BSTriShape`** y **21.957 `BSDynamicTriShape`**; `BSSubIndexTriShape` **no aparece** (0 bloques). Y el reparto por archivo es excluyente: **18.128 archivos tienen solo `BSTriShape`, 3.803 solo `BSDynamicTriShape`, y ninguno los dos**. Los 3.803 son el **17 %** del corpus y son los que `censo_nif.py` reportaba con `n_shapes = 0` sin avisar, porque iteraba únicamente `BSTriShape`.
**CONSULTA QUE LA PRODUJO**: recuento de `cuenta_tipos()` sobre los 22.394 archivos; comparación semilla vs parser completo sobre una muestra al azar de 1.500.
**N**: 22.394 archivos / 82.694 shapes (coincide con §15); 1.500 archivos en la comparación.
**EXCEPCIONES ENCONTRADAS**: 0 desacuerdos entre los dos parsers después del arreglo; 250 de esos 1.500 (16,7 %) daban 0 shapes antes. Que ningún archivo mezcle los dos tipos es lo que hacía el síntoma **total y silencioso**: no "faltan algunos shapes" sino "no hay ninguno".

### 17. (#20) `bhkRigidBody`: la identidad de tamaño se cumple entera
**AFIRMACIÓN**: `size == 250 + 4 * numConstraints` (con `numConstraints` leído en el offset +244) se cumple en **14.586 de 14.586 bloques**. Los tamaños observados son exactamente cuatro: 250 (c=0) ×12.939, 254 (c=1) ×1.645, 262 (c=3) ×1, 266 (c=4) ×1. **No existe ningún bloque entre 246 y 249 bytes.**
**CONSULTA QUE LA PRODUJO**: recorrido de todos los bloques `bhkRigidBody`/`bhkRigidBodyT` del corpus comprobando la identidad.
**N**: 14.586 bloques.
**EXCEPCIONES ENCONTRADAS**: 0 violaciones. El umbral `s >= 246` que usaba `parser_nif.colision_info` no lo justificaba ningún archivo. Subirlo a 250 cerraba la franja 246–249 pero **no el desacuerdo**: con `s=251` y `c=0` el parser seguía publicando layer/masa/motion de un bloque que `verificar` marcaba como roto. El parser exige ahora la identidad completa, igual que el verificador. Barrido de 192 combinaciones sintéticas (tamaños 246–277 × constraints 0–5): **0 desacuerdos**. Sobre el corpus real no cambia nada — **11.126 de 11.126** archivos con `bhkRigidBody` conservan su dato de colisión.

### 18. (#18) BS version: lo que el corpus puede validar, y lo que no
**AFIRMACIÓN**: **22.393 archivos con BS version 100** y **1 con BS 83** (`creationclub/_shared/dungeons/ayleidruins/interior/triggers/artrigpressureplate01.nif`). **Cero con BS ≥ 130.** Los 22.394 comparten `version 335675399 / user 12`.
**CONSULTA QUE LA PRODUJO**: lectura de la cabecera de los 22.394 archivos.
**N**: 22.394.
**EXCEPCIONES ENCONTRADAS**: los tres parsers del repo traían **dos lecturas distintas e incompatibles** del campo extra de cabecera para BS ≥ 130 —`nif_nodos.py` un SizedString en medio de los tres shorts, los del censo un cuarto ShortString después— y **ningún archivo del corpus ejercita ninguna de las dos**. No se eligió una: las tres ahora rechazan BS ≥ 130 explícitamente. Adivinar el largo de un campo de cabecera corre *todos* los offsets de bloque, que es la familia exacta del bug que produjo el `pesos por vértice = 1035` de `census/README.md`.

### 19. (#26) `BSMasterParticleSystem` sí es un nodo, y `BSRangeNode` no existe
**AFIRMACIÓN**: **93 archivos** traen `BSMasterParticleSystem`, y en los 93 está como **raíz**. El layout de `NiNode` —nombre, extra data, controller, flags, transform, colisión, hijos— parsea de forma coherente en **93 de 93** bloques: 1 hijo en 92 archivos, 2 en uno, y una cola de 14 a 30 bytes que son sus campos propios. Incluirlo en `TIPOS_NODO` recupera **93 nodos y 94 referencias de hijo** que se salteaban, y `verificar.py` devuelve **exactamente la misma evidencia** que antes: `header_cola` 93, `trailer` 93, `shape_tail` 1. Cero violaciones nuevas.
**CONSULTA QUE LA PRODUJO**: intento del layout de `NiNode` dentro de cada bloque, comprobando que los contadores no excedan el bloque y que los hijos sean índices válidos; después `nodos()` y `verificar._chequear()` sobre los 93, con y sin el tipo en la lista.
**N**: 22.394 archivos; 93 bloques `BSMasterParticleSystem`.
**EXCEPCIONES ENCONTRADAS**: 0 bloques incoherentes. Es el caso opuesto a `BSFurnitureMarkerNode` (§1), que se sacó de `TIPOS_NODO` porque el sufijo `Node` engañaba y su inclusión rompía 123 archivos de muebles. El sufijo del nombre no dice de qué hereda —en las dos direcciones—, así que se decide parseando.

**Segundo hallazgo del mismo barrido**: `BSRangeNode` estaba en `TIPOS_NODO` de `parser_nif.py` y **no** en las de `censo_nif.py` ni `nif_nodos.py`. Tiene **0 bloques en el corpus**, así que ningún archivo delataba la divergencia. Las tres listas quedan iguales y hay un test que las compara entre sí; el tipo se deja en las tres, declarado como no ejercitado.
### 20. La geometría de colisión, decodificada

**AFIRMACIÓN**: `bhkConvexVerticesShape` guarda `numVertices` en +32 y los vértices como `Vector4` desde +36, seguidos de `numNormals` y las normales. La identidad **`36 + 16·nv + 4 + 16·nn == tamaño del bloque`** se cumple en **3.553 de 3.553** bloques. El cuaternión del `bhkRigidBody` está en **+68** y la traslación en **+52**, en unidades de Havok (factor **69,99**).
**CONSULTA QUE LA PRODUJO**: `python census/parser_colision.py --autotest meshes`; el offset del cuaternión se buscó exigiendo norma 1 sobre los 14.586 bloques del corpus.
**N**: 3.553 formas convexas; 14.586 cuerpos rígidos; 22.394 archivos leídos.
**EXCEPCIONES ENCONTRADAS**: 0 violaciones de la identidad. Para el cuaternión, los candidatos dieron: +32 → 17 de 14.586; +36 → 0; +64 → 602; **+68 → 14.586**; +72 → 13.276. Yo había supuesto +36 leyendo el *orden* en que el exportador de PyNifly asigna los campos; en el archivo el orden es el contrario, y la medición lo corrigió. Validación cruzada contra Blender en tres archivos: las cajas coinciden al centésimo de unidad.

### 21. "La colisión envuelve la malla" es falso en el 96,7 % del corpus

**AFIRMACIÓN**: De los **3.126** archivos con malla y colisión decodificables, solo **102 (3,3 %)** tienen una colisión cuya caja contiene a la de la malla. La distancia entre centros tampoco da umbral: **p50 2,24 u, p90 89,80 u, p99 726,80 u, máximo 3.848 u**; relativa a la diagonal de la malla, p50 0,027 y p90 0,317.
**CONSULTA QUE LA PRODUJO**: caja envolvente de todas las formas de colisión contra la de todos los shapes, en espacio de mundo.
**N**: 3.126 archivos.
**EXCEPCIONES ENCONTRADAS**: el caso más extremo es `actors/atronachfrost/character assets/shield.nif`, con los centros a 13,9 diagonales de distancia. **Esta entrada existe para impedir una regla**: "la colisión tiene que envolver la malla" parece obvia, la viola el propio escudo de vidrio de Bethesda —su colisión es 1,2 unidades más corta que la malla en Y— y reprobaría al 96,7 % del corpus. Saber si una colisión quedó donde debía exige un original contra qué comparar, que es lo que hace `comparar.py --fiel`.

