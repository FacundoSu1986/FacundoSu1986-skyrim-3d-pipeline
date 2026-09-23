# El plugin de un arma: WEAP + STAT

Todo lo de acá sale de medir las 3.359 `WEAP` de los 10 plugins de una
instalación SE (`census/hallazgos_plugins.md`, entradas 14 a 18) y de un arma
que hizo el recorrido entero hasta el juego: el hacha de Tencent, un hacha de
dos manos clonada de `DaedricBattleaxe` (`000139B4`). Lo que dice "confirmado
en el juego" se vio jugando; lo demás está medido en los bytes.

## La división del trabajo

| Record | Qué es | Qué pasa si falta o está mal |
|---|---|---|
| **WEAP** | el arma: nombre, valor, peso, daño, modelo de tercera persona | no existe para el juego |
| **STAT** | el modelo de **primera persona**, apuntado por el `WNAM` del WEAP | el arma no se ve en primera persona |

A diferencia de un escudo, no hay un segundo record por raza: la malla del arma
cuelga del esqueleto por su `Prn`, no por un `ARMA`.

## No escribas el WEAP: clonalo

Un `WEAP` tiene unos 20 subrecords y un `DNAM` de 100 bytes con velocidad,
alcance, flags y sonidos. Escribirlo a mano es buscar el error. Se clona uno
vanilla **de la misma clase** y se cambian solo los campos declarados.

**Qué donante.** Una de las **472 armas base**: sin `CNAM`. Las otras 2.868
tienen plantilla (`CNAM`) — son las variantes encantadas — y aunque traen su
propio `MODL`, heredan el resto del arma base. Clonar la base es clonar lo que
el motor usa. `[MEASURED]`

**De la misma clase** quiere decir el mismo `DNAM[0]`, el tipo de animación:

| `DNAM[0]` | tipo |
|---|---|
| 1 | espada de una mano |
| 2 | daga |
| 3 | hacha de una mano |
| 4 | maza |
| 5 | espada de dos manos |
| 6 | **hacha de dos manos y martillo** (comparten el valor) |
| 7 | arco |
| 8 | bastón |
| 9 | ballesta |

Coincide con el nombre del arma en 245 de 253; las 8 que no, son maniquíes y
armas conjuradas. `[MEASURED]`

## Campo por campo

Del `DaedricBattleaxe` al hacha, **cambian nueve** y el resto se hereda en el
mismo orden:

| Subrecord | Qué va | Nota |
|---|---|---|
| `EDID` | un editor ID propio | |
| `OBND` | la caja del NIF, redondeada hacia afuera | medirla del archivo, no copiarla |
| `FULL` | el nombre | cadena literal si el `TES4` **no** tiene `LOCALIZED` (ver abajo) |
| `MODL` | la ruta del NIF, **sin** `meshes\` | `weapons\MiArma\miarma.nif` |
| `MODT` | vacío vale: `02 00 00 00 00 00 00 00 00 00 00 00` | confirmado en el juego |
| `DESC` | `\0` | |
| `WNAM` | el FormID del `STAT` propio | ver abajo |
| `DATA` | valor `u32`, peso `f32`, daño `u16` = **10 bytes** | confirmado en el juego |
| `INAM` | el set de impactos | se puede heredar; ver "Impactos" |

Heredados tal cual en el hacha: `ETYP BIDS BAMT KSIZ KWDA TNAM NAM9 NAM8 DNAM
CRDT VNAM`.

**`DATA` y `DNAM` tienen tamaño fijo.** 10 y 100 bytes en las 3.359 `WEAP`,
sin excepción. `[MEASURED]` Empaquetar el daño como `f32` o como `u32` da 12
bytes y el motor lee los campos corridos.

**El `STAT` de primera persona** es mínimo: `EDID`, `OBND`, `MODL` (el mismo NIF)
y `MODT`. De las 472 armas base, 463 tienen `WNAM` y **las 463 apuntan a un
`STAT`**; las 9 sin `WNAM` son conjuradas, maniquíes y de misión. `[MEASURED]`

## La cabecera de cada record: `formVersion = 44`

La trampa más cara del hacha. Con `formVersion = 0` el plugin cargó, el arma
apareció en el inventario **con el valor bien**, y pesaba 0 y hacía 0 de daño.
El motor lee el `DATA` con el layout de la versión declarada. Con 44: peso 27,
daño 26. Confirmado en el juego. Ver [trampa 23](trampas.md#23).

## El NIF: el `Prn` decide dónde cuelga el arma envainada

El `NiStringExtraData` llamado `Prn` es el nodo del esqueleto del que cuelga el
arma cuando no está en la mano. Sigue al tipo de animación en **305 de 306**
armas del jugador: `[MEASURED]`

| tipo | `Prn` |
|---|---|
| espada de una mano | `WeaponSword` |
| daga | `WeaponDagger` |
| hacha de una mano | `WeaponAxe` |
| maza | `WeaponMace` |
| espada de dos manos, hacha de dos manos, martillo | `WeaponBack` |
| arco, ballesta | `WeaponBow` |
| bastón | **sin regla**: `WeaponStaff` en 21, `SHIELD` en 18 |

La excepción es `NordicGreatSword.nif`. El hacha lleva `WeaponBack` y cuelga en
la espalda. Copiá el `Prn` del NIF del donante, no lo escribas de memoria.

La colisión del NIF tiene sus propias reglas: `scripts/colision_caja.py`.

## Impactos: `INAM` → `IPDS` → `IPCT`

```
WEAP --INAM--> IPDS --(material de lo golpeado)--> IPCT --MODL--> NIF del efecto
```

El `IPDS` es una lista de pares `PNAM` (material `MATT`, impacto `IPCT`) de 8
bytes. Heredar el `INAM` del donante ya da los efectos del arma vanilla. Para
cambiar qué pasa contra un material se escribe un `IPDS` propio que copia el del
donante y cambia pares.

**Al golpear un actor manda el material del actor, no el del arma.** El
centurión dwemer es `MaterialSkinMetalLarge` (`NAM4` de su raza), y el set del
hacha daédrica le da `FXMetalSparkImpactSlice.nif`: chispas.

El hacha de Tencent llevó un `IPDS` propio que pasa la familia mineral (piedra,
grava, vidrio, cerámica) a chispa. **Funciona, y el efecto es chico**:
confirmado en el juego. (El `DATA` del `IPCT` de chispa vanilla declara 0,1 de
duración; cuánto de lo chico viene de ahí no está medido.) No confundir "casi
no se ve" con "no anda" antes de medir la cadena.

## El `TES4`

- **Masters**: los que use el arma. Un FormID propio es
  `len(masters) << 24 | índice`; el hacha, con 3 masters, usa `03000800`.
- **Flags**: `ESM | ESL` (`0x201`) para un light master. **No copies los flags
  de un plugin de Bethesda**: los 10 traen `LOCALIZED` (`0x80`), y con ese bit el
  formato dice que `FULL` y `DESC` se leen como IDs de la tabla de cadenas, no
  como texto. El hacha cargó sin ese bit y con cadenas literales; con el bit no
  está probado. `[MEASURED]` los flags, `[PROVIDER]` el efecto.
- **`HEDR`**: `numRecords` = records + `GRUP`s, como en los 10 vanilla. El motor
  no lo valida — el hacha cargó con 105 y con 2 —, pero no hay razón para diferir.
- **ESL**: `scripts/esl.py` comprueba el techo de `0xFFF` antes de marcar.

## Validar de verdad

```
python scripts/verificar_plugin.py MiArma.esl
python scripts/colision_caja.py meshes/weapons/MiArma/miarma.nif
```

`verificar_plugin.py` exige `formVersion = 44`, índices de mod que resuelvan,
`DATA` de 10 y `DNAM` de 100 en cada `WEAP`, y que el `WNAM` apunte a un
`STAT` que exista. Sobre las 3.359 `WEAP` vanilla reprueba cero.

Lo que ningún script cierra y el hacha tuvo que ver jugando: que se equipa, que
golpea en primera y tercera persona, que se puede caminar con ella, el peso y
el daño del inventario, y dónde cuelga envainada.
