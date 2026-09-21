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


### 22. (#21) "Cada hueso dentro de la caja de su pieza" es falso en el 75,9 %

**AFIRMACIÓN**: De **27.927** shapes skinneados con huesos y caja calculable, solo **6.719 (24,1 %)** tienen **todos** sus huesos dentro de su propia caja envolvente; de los **114.751** pares (pieza, hueso), el **64,8 %** cae adentro. Aflojar el criterio no lo salva: aceptando que el peor hueso se salga hasta **una diagonal entera** de la caja, siguen fallando **467 shapes (1,7 %)**.
**CONSULTA QUE LA PRODUJO**: para cada `BSTriShape`/`BSDynamicTriShape` skinneado, la lista de huesos de su skin instance contra la caja de sus vértices en espacio de mundo (`parser_colision.cajas_de_shapes`).
**N**: 7.103 archivos con skin, 27.927 shapes, 114.751 pares.
**EXCEPCIONES ENCONTRADAS**: las peores son bocas — `mouthwerewolf.nif::NeutralMouth` a **18.323 u** de su caja, y las `MouthKhajiit` de facegen a 17.241 u. **Esta entrada existe para impedir una regla**: SKILL.md la nombra como control del paso 8b, y escribirla en forma absoluta habría reprobado a tres de cada cuatro mallas vanilla — el mismo error que "la colisión envuelve la malla" (entrada 21) y que "toda ruta de textura empieza con `textures\`". Lo que sí sirve es su forma **relativa**: que la distancia del hueso a la caja no crezca respecto del original.

> **Y el 24,1 % no es un accidente de Bethesda: la comparación está mal construida.** El origen de un hueso no es un punto de la malla. Un peso en la manga se articula en el codo, y el codo puede caer fuera de la caja de la manga sin que nada esté mal. Las bocas del hombre lobo y de los khajiit son el caso extremo del mismo efecto: huesos de cara compartidos, cuyo origen está en otra parte de la cabeza. Dicho así, la regla no es "falsa el 76 % de las veces" — es **la comparación equivocada por construcción**, que es un argumento más fuerte para no escribirla nunca.

### 23. (#21) El nodo raíz lleva el nombre del archivo

**AFIRMACIÓN**: En **2.786 de 3.000** archivos de una muestra aleatoria (**92,9 %**) el nodo raíz se llama igual que el `.nif` que lo contiene, con o sin extensión.
**CONSULTA QUE LA PRODUJO**: nombre del bloque 0 contra el basename, sobre `random.sample(rutas, 3000)` con semilla fija.
**N**: 3.000 archivos, 0 errores de lectura, 0 sin nodo raíz.
**EXCEPCIONES ENCONTRADAS**: 214 (7,1 %) con otro nombre, casi siempre el del asset del que se derivó: `werewolfhead3.nif` → `WerewolfStaff3`, `rustymaceofmolagbal.nif` → `RustyMaceLow`, `1stpersonskullofcorruption.nif` → `Staff`. **Consecuencia práctica**: comparar el juego de nombres de nodo entre dos archivos sin sacar la raíz es comparar nombres de archivo. Reprobaba **1.198 de los 1.216** pares `_0.nif`/`_1.nif` —el mismo asset— y dejaba a los LOD, que traen un solo nodo, sin ningún nodo en común.

### 24. (#21) Las posiciones de hueso del mismo asset son idénticas

**AFIRMACIÓN**: Entre el mismo asset a peso 0 y a peso 100 (`_0.nif` / `_1.nif`), **21.641 de 21.683** comparaciones de posición de nodo en mundo dan el valor **idéntico**. Los **42** desacuerdos son **todos** `InvMarker`, el marcador de cámara del inventario, que no mueve geometría. Dentro de `actors/character/character assets/` —569 archivos sobre el mismo esqueleto humano— **2.108 de 2.112** son idénticas y las 4 restantes difieren en exactamente **0,010**, que es el redondeo a dos decimales del lector.
**CONSULTA QUE LA PRODUJO**: `nif_nodos.mundo()` sobre 1.166 pares `_0`/`_1` y sobre la carpeta de character assets.
**N**: 21.683 + 2.112 comparaciones.
**EXCEPCIONES ENCONTRADAS**: 42 `InvMarker` y 4 de redondeo. Esto es lo que da la tolerancia de **0,01 u** de `verificar_export.py`: no es un umbral elegido, es la unidad más chica que el lector distingue. Y está muy por debajo de lo que tiene que atrapar — ponerle a `childbody.nif` el esqueleto de `frostgiant2.nif` mueve los 10 huesos comparables, el que menos **57,34 u**.

### 25. (#21) Vanilla no es consistente consigo mismo entre `_0` y `_1`

**AFIRMACIÓN**: De los **1.216** pares `_0.nif`/`_1.nif`, **1.163 (95,6 %)** pasan la comparación completa de `verificar_export.py`. Los **53** que no son diferencias reales de contenido de Bethesda, no artefactos del lector.
**CONSULTA QUE LA PRODUJO**: `verificar_export.comparar(a, b)` sobre cada par.
**N**: 1.216 pares.
**EXCEPCIONES ENCONTRADAS**: los conteos por regla que siguen **no son disjuntos** —un par puede fallar por varias a la vez, y suman 65 sobre 53 pares—. 1 es `tfxbloodshirt_0.nif`, que repite **15 nombres de hueso** dentro del archivo y por eso no se puede comparar por nombre (ver entrada 27); 47 difieren en nombres de pieza — `dragonhelm_0.nif` llama a las suyas `DragonHood:0`/`:1` y `dragonhelm_1.nif` las llama `Plane02:0`/`:1`—, 15 en cuenta de bloques —`1stpersondraugrarmormale_0.nif` tiene 17 `NiNode` y el `_1` tiene 16— y 1 en huesos por pieza. Verificado contra `parser_nif` en los dos casos citados.

### 26. (#21) La esfera envolvente de un shape skinneado está en cero

**AFIRMACIÓN**: En un `BSTriShape` skinneado, la esfera envolvente que precede a los refs de skin viene **centro (0,0,0) radio 0**, igual que `numTriangles`, `numVertices` y `dataSize`.
**CONSULTA QUE LA PRODUJO**: los 4 floats en el offset de la esfera contra la caja real de los vértices, en `childbody.nif`.
**N**: 1 archivo para determinar; no se barrió el corpus.
**EXCEPCIONES ENCONTRADAS**: sin medir. **Queda declarado como no barrido**: se anota para que nadie use la esfera como atajo a la caja de la pieza —que es lo que se intentó— sin medirla antes.

### 27. (#21) Nombres repetidos dentro de un mismo archivo

**AFIRMACIÓN**: **557 de 22.394** archivos (**2,49 %**) tienen al menos un nombre de nodo repetido, y **222 (0,99 %)** tienen dos o más shapes con el mismo nombre.
**CONSULTA QUE LA PRODUJO**: `Counter` sobre los nombres de `nodos()` y sobre los de los bloques de `TIPOS_SHAPE`, en los 22.394 archivos.
**N**: 22.394 archivos, 0 errores de lectura.
**EXCEPCIONES ENCONTRADAS**: el nodo repetido es casi siempre `InvMarker`. En los shapes el caso típico es distinto y peor: en `_resourcepack/landscape/trees/mugopine01.nif` los dos shapes **no tienen nombre**, los dos caen en la clave `"?"`, y una estructura indexada por nombre los reduce a **uno**. **Consecuencia práctica**: cualquier comparación por nombre —la de `verificar_export.py` entre otras— no puede decidir nada sobre esos archivos, y una pieza perdida sería invisible. Se reprueba en vez de comparar mal. El caso más extremo es `tfxbloodshirt_0.nif`, con 15 nombres de hueso repetidos.

### 28. (#21) Ningún hueso vanilla apunta fuera de la jerarquía de nodos

**AFIRMACIÓN**: De **115.766** referencias de hueso en los `Bones[]` de las skin instances del corpus, **115.766 (100 %)** resuelven a un bloque que está en `TIPOS_NODO`. Cero apuntan a `-1` o a un tipo que la tabla no reconozca.
**CONSULTA QUE LA PRODUJO**: barrido de `Bones[]` de los 28.012 bloques `NiSkinInstance`/`BSDismemberSkinInstance`, contra `nodos()`.
**N**: 22.394 archivos, 28.012 skin instances, 115.766 refs.
**EXCEPCIONES ENCONTRADAS**: 0. Esto **acota un desacuerdo conocido entre los dos lectores**: ante un ref que no resuelve, `censo_nif.skin_por_shape()` devuelve `"?N"` y `parser_nif._parse_dismember_instances()` lo descarta. Sobre el corpus la diferencia no se puede manifestar, pero la entrada del vanilla no es la única del pipeline —el archivo a verificar lo escribe un exportador—, así que la divergencia queda **declarada en el test que ata a los dos lectores** en vez de quedar tapada por un fixture que solo emite refs resolubles.

### 29. (#21) La esfera envolvente como ancla, no como medida

**AFIRMACIÓN**: complemento de la entrada 26. La esfera envolvente de un `BSTriShape` se usa en el lector **solo como ancla de offset** (`p += 16` para llegar a los refs de skin), nunca como caja de la pieza.
**CONSULTA QUE LA PRODUJO**: lectura del código de `_skin_de_shape` y `trishapes`.
**N**: no aplica — es una aclaración sobre el uso, no una medición.
**EXCEPCIONES ENCONTRADAS**: ninguna. Se anota porque la entrada 26 mide la esfera con **N=1** y sin barrido; quien la lea dentro de seis meses podría tomarla como la caja disponible. No lo es: para la caja de una pieza hay que leer la geometría, que está en `census/parser_uv.py`.

### 30. (#21) Las rotaciones de nodo del mismo asset son idénticas

**AFIRMACIÓN**: Entre `_0.nif` y `_1.nif` del mismo asset, **22.151 de 22.179** rotaciones de nodo en espacio de mundo son **idénticas** al redondeo de cuatro decimales (99,874 %).
**CONSULTA QUE LA PRODUJO**: composición de la cadena de rotaciones desde la raíz, sobre los 1.216 pares.
**N**: 22.179 comparaciones.
**EXCEPCIONES ENCONTRADAS**: **28 de 28** son `InvMarker`, el mismo nodo que ya aparece en la entrada 24 como único desacuerdo de posición. Cero nodos que sean huesos difieren. **Consecuencia práctica**: la orientación se puede comparar **exacta**, sin umbral — el corpus no pide ninguno, y la regla no produce un solo falso positivo sobre los 1.216 pares.

> **Por qué hacía falta medirlo**: `mundo()` devuelve posición y escala, no ejes. Un hueso **hoja** girado en su lugar tiene la misma posición y arrastra la malla con él, así que `verificar_export.py` daba "pasa: 0 fallas" con dos huesos girados 90°. Un giro en un nodo **con hijos** sí se veía, porque mueve a los hijos: el agujero era exactamente el de las hojas.

### 31. (#21) Ningún bloque vanilla cuelga de dos padres

**AFIRMACIÓN**: De **3.000** archivos de una muestra aleatoria, **0** tienen un bloque referenciado como hijo por dos nodos distintos.
**CONSULTA QUE LA PRODUJO**: `Counter` sobre las listas de hijos de todos los nodos de cada archivo.
**N**: 3.000 archivos, 0 errores de lectura.
**EXCEPCIONES ENCONTRADAS**: 0. Se mide porque el recorrido de `censo_nif` se queda con el **primer** padre que visita y no avisa; sobre entrada vanilla eso no puede manifestarse, pero el archivo que `verificar_export.py` recibe lo escribe un exportador. Queda declarado en la cabecera del script, no arreglado.

### 32. (#40) Casi ninguna malla vanilla está cerrada — la regla no puede ser absoluta

**AFIRMACIÓN**: Solo el **15,1 %** de los shapes vanilla son mallas cerradas (menos del 0,5 % de aristas de borde). La mediana tiene el **15,4 %** de sus aristas al aire, y por categoría va desde `actors` (mediana 1,6 %, el 36,4 % cerradas) hasta `architecture` (mediana 24,7 %, solo el **2,6 %** cerradas).
**CONSULTA QUE LA PRODUJO**: para cada shape, soldar los vértices por posición (tolerancia 2e-5 del lado mayor) y contar las aristas usadas por un solo triángulo. Sobre `census/parser_uv.geometria()`.
**N**: 700 archivos de muestra aleatoria, 1.347 shapes con al menos 50 triángulos útiles.
**EXCEPCIONES ENCONTRADAS**: no aplica — el hallazgo **es** la dispersión. La ropa, los carteles, las láminas de vegetación y casi toda la arquitectura son superficies abiertas a propósito.

> **Por qué importa**: "la malla tiene que estar cerrada" parecía la regla obvia después del hacha de Tencent, y es **falsa**. Escrita como REGLA habría bloqueado el 85 % de lo que Bethesda publica. Ver la entrada 33 para la que sí se sostiene.

### 33. (#40) Decimar correctamente nunca aumenta las aristas de borde

**AFIRMACIÓN**: Decimando al 25 % de sus triángulos, **soldar por distancia antes** de aplicar el modificador deja el número de aristas de borde **igual o menor** — peor caso medido **x0,70**, y las mallas cerradas siguen en cero. Decimar **sin soldar** lo multiplica: creció en **12 de 14** shapes, hasta **x25,5**, y las dos mallas cerradas de la muestra pasaron de 0 a **956** y a **544** aristas de borde.
**CONSULTA QUE LA PRODUJO**: las mismas 14 mallas decimadas de las dos formas en Blender 4.4, midiendo el borde sobre vértices soldados antes y después.
**N**: 14 shapes vanilla de al menos 2.000 triángulos, 28 decimaciones.
**EXCEPCIONES ENCONTRADAS**: 0 casos en que la decimación correcta aumentara el borde.

> **La causa**: un modelo de Tripo/Meshy trae los vértices **partidos por cada costura del atlas de UV** — medido en el hacha de Tencent, 858.627 vértices que sueldan a 749.992. Para el modificador `Decimate` una costura sin soldar **es** un borde de malla, y los bordes se conservan como bordes: cada isla queda como un parche suelto. Con un atlas de una isla por triángulo eso rasga el modelo entero. El GLB de origen tenía ratio tri/vert 2,00 exacto y **cero** aristas de borde; el OBJ decimado sin soldar quedó con el **49,4 %** de sus aristas abiertas, y la malla que llegó al juego con el **35,2 %**. En el juego se veía como "al arma le faltan partes". Nada dio error en ningún paso.

> **Consecuencia práctica**: la REGLA es **relacional** y la implementa `skills/modelo-ia-a-skyrim/scripts/salud_malla.py`. Sobre los archivos reales del hacha, la cadena vieja sale con exit 1 (59.078 aristas de borde contra 0 del origen) y la nueva con exit 0.

### 34. (#40) Contar aristas por índice de vértice no mide nada

**AFIRMACIÓN**: En un NIF los vértices de costura están **duplicados**, así que dos triángulos vecinos no comparten índice y toda arista parece de borde. Hay que soldar por posición **antes** de contar.
**CONSULTA QUE LA PRODUJO**: el mismo shape del hacha contado de las dos formas.
**N**: 1 asset, pero el efecto es estructural: los 8.608 vértices del NIF que se envía sueldan a 3.991.
**EXCEPCIONES ENCONTRADAS**: no aplica. Contando por índice, el hacha daba **2.953** piezas sueltas donde había 382, y 382 donde en realidad hay **1**. Los tres números salieron del mismo archivo.
