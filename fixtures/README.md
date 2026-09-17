# La referencia vanilla

Un pipeline que exporta a Skyrim necesita algo contra qué comparar. Este es ese
algo: **un static vanilla conocido, medido y registrado**, para que "el NIF
exportado está bien" deje de ser una opinión.

## Lo que hay acá, y lo que no

| | |
|---|---|
| Se versiona | la **medición**: árbol de bloques, shader, rutas de textura, colisión, caja envolvente, y el `sha256` del archivo original |
| **No** se versiona | el `.nif` ni los `.dds`. Son de Bethesda. |

El `sha256` es lo que hace reproducible la referencia sin copiarla: dos personas
pueden comprobar que están mirando exactamente los mismos bytes sin que el
archivo viaje.

## De dónde sale el archivo

```
Skyrim Special Edition/Data/Skyrim - Meshes0.bsa
  └─ meshes/clutter/signage/roadsigns/roadsignwhiterun01.nif
```

Se extrae con [BAE](https://www.nexusmods.com/skyrimspecialedition/mods/974)
(Bethesda Archive Extractor) o con cualquier herramienta que lea BSA. No hace
falta extraer el BSA entero: alcanza con ese archivo.

Para confirmar que tenés el mismo:

```bash
sha256sum roadsignwhiterun01.nif
# d435f916e43b865107d1dd6af7208250f83cc21626a0dab8f9d4c5b6c0a06574
```

Si no coincide, o tenés otra edición del juego, o un mod parcheó el archivo. El
`registrar.py` avisa y sigue, porque tu copia igual sirve para *tus* pruebas —
pero los números de este repo salieron de esos bytes.

## Por qué este archivo

No se eligió a ojo. Salió de filtrar los **8.644** NIF de `clutter/`,
`architecture/`, `furniture/`, `dungeons/` y `landscape/` con estos criterios:

- raíz `BSFadeNode`
- **un solo** shape, sin skin
- **un solo** `BSShaderTextureSet`
- con colisión
- sin violaciones de identidad de tamaño

Quedaron **1.857 candidatos**. Entre los más simples, éste es el único que
además tiene:

- **el par de texturas canónico y nada más**: difusa + `_n`. Los que empataban
  en tamaño arrastran un cubemap `_e` o un `_m`, que suman una variable a
  cualquier discrepancia futura.
- **colisión de caja** (`bhkBoxShape`), la forma más simple, y la que más
  probablemente necesite un estático generado.
- **extensión real en los tres ejes**. Las alfombras (`rug01`, 28 triángulos)
  empataban en simplicidad pero son planas, y un fixture plano no sirve para
  comprobar dimensiones.

Un fixture con dos shapes o dos texture sets deja de discriminar: cualquier
diferencia futura tendría dos explicaciones posibles.

## Lo que quedó medido

```
sha256        d435f916e43b865107d1dd6af7208250f83cc21626a0dab8f9d4c5b6c0a06574
bytes         3.625
cabecera      20.2.0.7 / user 12 / BS 100
raíz          BSFadeNode          BSXFlags 130 (bits 1 y 7)
bloques       8: BSFadeNode, BSTriShape, BSLightingShaderProperty,
                 BSShaderTextureSet, BSXFlags, bhkCollisionObject,
                 bhkRigidBodyT, bhkBoxShape
shape         RoadSignWhiterun01:0 — 70 vértices, 46 triángulos, con UV
shader        Default (id 0), ranuras pobladas [0, 1]
texturas      textures\clutter\signage\roadsigns\RoadSignsCities01.dds
              textures\clutter\signage\roadsigns\RoadSignsCities01_n.dds
colisión      SKYL_STATIC / SKY_HAV_MAT_WOOD / MO_SYS_BOX_STABILIZED, masa 0.0
caja          80,13 × 8,01 × 22,40 unidades  =  1,145 × 0,114 × 0,320 m
```

(1 metro = 70 unidades de Skyrim.)

## Uso

**Regenerar la medición** desde tu copia:

```bash
python fixtures/registrar.py "<ruta a meshes>"
```

**Comprobar que es reproducible** — vuelve a medir y compara contra el JSON
registrado, sin escribir nada:

```bash
python fixtures/registrar.py "<ruta a meshes>" --verificar
```

**Comparar un NIF exportado** contra el contrato que esta referencia demuestra:

```bash
python fixtures/comparar.py --contrato mi_asset.nif
```

**Comparar contra la referencia misma**, campo por campo (regresión):

```bash
python fixtures/comparar.py --identico "<ruta a meshes>/clutter/signage/roadsigns/roadsignwhiterun01.nif"
```

## Una advertencia sobre el contrato

`comparar.py` separa a propósito dos cosas que es fácil confundir:

- **Reglas**, que se aplican y pueden reprobar. Cada una lleva la evidencia que
  la sostiene — cuántos archivos del censo la cumplen. Si una regla no tiene
  número atrás, no está.
- **Observaciones**, que se informan y no reprueban. Ahí viven las cosas que
  este archivo tiene pero que el censo muestra que *no* son universales.

La distinción importa porque el modo de fallar de este repo es al revés del
habitual: no que falten reglas, sino que sobren inventadas. Salir del cuadro UV
`[0,1]` parece un defecto y es *tiling* en el 49,2 % de los shapes; compartir
texture set y pisarse parece un bug y es lo que hace Bethesda en el 91 % de los
casos.

## Cuánto reprueba el contrato, medido

Un contrato que aprueba todo no sirve; uno que reprueba a Bethesda tampoco. Los
dos números hay que saberlos, así que lo corrí sobre el corpus entero:

```
archivos: 22.394   pasan: 21.857  (97,602 %)
```

Los 537 que no pasan **tienen todos una causa entendida**:

| Regla | Archivos | Qué son |
|---|---:|---|
| `tiene_geometria` | 463 | los `skeleton.nif`: árboles de nodos sin shapes. Vanilla legítimo, pero no son assets entregables. |
| `nodo_raiz_conocido` | 93 | raíz `BSMasterParticleSystem` — efectos de partículas. **Ver la nota de abajo.** |
| `texturas_dds` | 73 | la ruta literal `NOR` como placeholder de Bethesda |
| `texturas_separador` | 71 | el mismo `NOR` |
| `bs_version` | 1 | `artrigpressureplate01.nif`, BS 83, ya documentado en el hallazgo 18 |

Ninguno es una sorpresa y ninguno es un falso positivo silencioso.

> **`BSMasterParticleSystem` no está en `TIPOS_NODO`.** Son 93 archivos vanilla
> cuya raíz el parser no reconoce como nodo. Puede ser que falte en la lista —
> o puede que no sea un nodo, como pasó con `BSFurnitureMarkerNode`, que se
> sacó justamente porque incluirlo rompía 123 archivos de muebles. No lo
> resolví acá: se decide midiendo si agregarlo mantiene verdes las identidades
> de tamaño, y eso es un cambio al parser, no al fixture.

