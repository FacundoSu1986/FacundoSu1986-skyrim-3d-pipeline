# Hallazgos del censo de plugins — Skyrim SE

Fuente: los 10 plugins de una instalación SE (`Skyrim.esm`, `Update.esm`, los
tres DLC y cinco de Creation Club). Parser: `census/parser_esm.py`. Nada de
Bethesda entra al repo: se versiona la medición.

Formato fijo: `AFIRMACIÓN — CONSULTA QUE LA PRODUJO — N — EXCEPCIONES`.
Sin recomendaciones. Sin umbrales inventados.

---

### 1. El formato se determinó por falsificación, no leyendo una especificación

**AFIRMACIÓN**: Dos preguntas del layout se contestaron probando las dos
lecturas posibles y viendo cuál embaldosa el archivo:

| Pregunta | Una lectura | La otra |
|---|---|---|
| ¿Cuánto mide la cabecera de un record? | **24 B** → el bloque siguiente al `TES4` es `GRUP` | 20 B → basura |
| ¿El tamaño de un `GRUP` incluye su cabecera? | **Sí** → el recorrido cierra exacto en 249.753.412 B | No → muere en +9.743.809 |

**CONSULTA**: recorrido de nivel superior de `Skyrim.esm` con cada hipótesis.
**N**: 1 archivo de 250 MB para determinar; 10 archivos para confirmar.
**EXCEPCIONES**: ninguna. Las dos lecturas erróneas fallan en el primer bloque
torcido, no "un poco más adelante".

### 2. La identidad se cumple en los tres niveles

**AFIRMACIÓN**: Los bloques embaldosan el archivo sin huecos ni solapes, en los
tres niveles —bloques de nivel superior, contenido de cada `GRUP`, subrecords
dentro de cada record— con **0 violaciones**. Los dos primeros niveles, sobre
**los 10 plugins**: **1.328.055 bloques** de **121 tipos**. El tercero, sobre
**todos los records de los 5 masters** que `--autotest` fija; los cinco plugins
de Creation Club no se fijan porque Bethesda los publica y actualiza aparte del
juego base, así que el ancla no puede exigirlos.
**CONSULTA**: `python census/parser_esm.py --autotest <carpeta Data>`
**N**: 10 plugins, 1.328.055 bloques; subrecords de cada record de los 5 masters
fijados.
**EXCEPCIONES**: 0. La pasada de subrecords corre también sobre los records
comprimidos, así que el camino de `zlib` del parser queda **ejercitado por el
corpus**, no solo por el fixture sintético. (`0 de 12.626` STAT tienen la
bandera de compresión; la bandera aparece en otros tipos.)

### 3. Qué tiene adentro un `STAT`

**AFIRMACIÓN**: De **12.626** records `STAT`:

| Subrecord | Presencia | Tamaños |
|---|---:|---|
| `EDID` (nombre de editor) | **100 %** | variable |
| `OBND` | **100 %** | 12 B siempre |
| `DNAM` | **100 %** | 8 B en 11.915, 12 B en 711 |
| `MODL` (la ruta al `.nif`) | 99,9 % | variable |
| `MODT` | 99,0 % | 12 B, 24 B, 48 B |
| `MODS` | 11,9 % | |
| `MNAM` | 8,7 % | 1040 B siempre |

**CONSULTA**: recorrido de subrecords de cada `STAT`.
**N**: 12.626.
**EXCEPCIONES**: **8 STAT no tienen `MODL`** — o sea que un static sin modelo
existe en vanilla. La combinación mínima observada es
**`EDID+OBND+MODL+DNAM`**, en **118 records (0,9 %)**; la más frecuente es
`EDID+OBND+MODL+MODT+DNAM`, en 10.019 (79,4 %). Hay 8 records con solo
`EDID+OBND+DNAM`.

> Esto es lo que hacía falta para el issue #31: el conjunto mínimo no es una
> deducción, son 118 archivos que existen y funcionan.

### 4. Las rutas `MODL` no llevan prefijo — a diferencia de las de textura

**AFIRMACIÓN**: **12.618 de 12.618** rutas `MODL` son relativas a `meshes/`
**sin** el prefijo: `DLC01\Dungeons\Castle\LgHalls\CasExFreeSm01.nif`.
**CONSULTA**: conteo del prefijo de cada `MODL`.
**N**: 12.618 rutas.
**EXCEPCIONES**: 0. Es una convención más limpia que la de las texturas, donde
el 87,8 % lleva `textures\` y el 12,2 % no (hallazgo de `comparar.py`). Los dos
campos apuntan a carpetas del juego y **no** siguen la misma regla.

### 5. Las rutas cruzan bien contra el censo de mallas

**AFIRMACIÓN**: **12.483 de 12.618 (98,9 %)** rutas `MODL` resuelven a un
archivo del corpus de mallas medido en `hallazgos.md`.
**CONSULTA**: resolución de cada `MODL` contra el índice de `meshes/`.
**N**: 12.618.
**EXCEPCIONES**: las 135 que no resuelven son assets de prueba que quedaron en
los plugins —`DLC01\SoulCairn\Test\doortest.nif`,
`Architecture\SnowElfRuins\TestBossRoom01.nif`, `Effects\testPuddle01.nif`— y
contenido que este extraído no tiene.

### 6. `OBND` no es la caja envolvente de la malla

**AFIRMACIÓN**: Comparado contra la caja que `parser_uv` lee del `.nif`,
`OBND` coincide dentro de 1 unidad en **311 de 500 (62,2 %)**. En **158
(31,6 %)** ninguna de las dos cajas contiene a la otra. Y **608 de 12.626
(4,8 %)** traen `OBND` **en cero**.
**CONSULTA**: `struct.unpack("<6h", OBND)` contra el mínimo/máximo de las
posiciones de vértice del `.nif` referenciado.
**N**: 500 comparaciones; 12.626 para el conteo de ceros.
**EXCEPCIONES**: 62 % es demasiado para ser casualidad y demasiado poco para
ser una regla.

> **Dos hipótesis, dos refutaciones.** Primero supuse que `OBND` era la caja de
> la malla: falso. Después, que la diferencia venía de no aplicar el transform
> del nodo raíz —nuestro lector da posiciones en espacio local—: también falso.
> Entre los archivos con transform **identidad**, `OBND` coincide en
> **367 de 583 (63,0 %)**, igual que el total, y solo 17 archivos de 600 tienen
> un transform que no sea identidad.
>
> **Qué es `OBND` queda sin medir.** No se le inventa un significado.

Lo que sí se puede usar: **608 STAT vanilla traen `OBND` en cero y el juego los
carga**. Un STAT generado puede escribir ceros en vez de calcular algo que no
entendemos.

---

## Lo que este censo NO mide, declarado

- **Qué significa `OBND`.** Ver arriba.
- **`DNAM`, `MODT`, `MODS`, `MNAM`.** Se midió su presencia y su tamaño, no su
  contenido. `MNAM` mide siempre 1040 bytes, lo cual sugiere una estructura
  fija, y no se investigó.
- **El contenido del resto de los 121 tipos de record.** Solo se abrió `STAT`.
  `REFR` (866.240 records) es el que coloca un static en el mundo y no se tocó.
  La *estructura* de sus subrecords sí se comprueba: la pasada del autotest
  embaldosa los de cada record, sin mirar qué dicen.
- **Escribir.** Esto lee. Escribir un plugin exige completitud donde leer
  permite selectividad — la misma asimetría que decidió usar PyNifly en vez de
  escribir el NIF nosotros.
- **El camino de compresión en los STAT.** 0 de 12.626 STAT lo usan; en otros
  tipos sí aparece, y la pasada de subrecords del autotest los descomprime y
  verifica, pero el censo no mide cuántos ni de qué tipos.

### 7. (#21) `ARMA`: cuántas razas adicionales lleva un equipable

**AFIRMACIÓN**: De **1.170** records `ARMA`, la cantidad de razas adicionales (subrecords `MODL` repetidos) se reparte así: **234 (20,0 %) no tienen ninguna**, 232 (19,8 %) tienen una, y **215 (18,4 %) tienen 23**, que es el valor más frecuente por encima de 1. El máximo observado es 30.
**CONSULTA**: recorrido de los subrecords de cada `ARMA` de los 10 plugins.
**N**: 1.170 records.
**EXCEPCIONES**: los **234 sin ninguna raza son todos criaturas** —`NakedSkeletonArmor1AA`, `DLC1GargoyleVariantBossAA`, `DLC1_NakedChaurusFlyer2AA`—, **ninguno es un escudo**. De los **45** `ARMA` cuyo `EDID` contiene "Shield", el rango va de **1 a 30** y **ninguno está en 0**: `AurielsShieldAA` 30, `DwarvenShieldAA` 23, `AtronachFrostShieldAA` 4, `DLC1KeeperDragonplateShieldAA` 1.

> **Esto convierte un `[OBSERVED]` con N=1 en una regla con su población.** La skill `asset-nuevo-skyrim` decía "el `DwarvenShieldAA` lista 23 razas" y un lector podía leer "poné 23". El 23 es correcto para ese record y no es el número: es la lista del vanilla equivalente, que para un escudo humano nunca está vacía y para una criatura muchas veces sí.

### 8. (#21) El núcleo mínimo de `ARMO` y de `ARMA`

**AFIRMACIÓN**: En `ARMO`, **`EDID+OBND+RNAM+MODL+DATA+DNAM+BOD2`** aparece en **3.905 de 3.915** records. En `ARMA`, la combinación mínima observada es **`EDID+RNAM+DNAM+BODT`** —1 record— y la habitual es `EDID+RNAM+DNAM+MOD2+MODL+BODT`, en 730.
**CONSULTA**: presencia de subrecords de núcleo en cada `ARMO` y cada `ARMA`.
**N**: 3.915 `ARMO`, 1.170 `ARMA`.
**EXCEPCIONES**: los **10** `ARMO` restantes usan el `BODT` viejo en vez de `BOD2`. En `ARMA`, `MOD2` (la ruta del modelo masculino) está en el 99,6 % y `MODL` —que en este record **no** es una ruta de modelo sino la lista de razas— en el 80,0 %.

### 9. (#21) Dos recorridos de plugin independientes dan el mismo número

**AFIRMACIÓN**: El recorrido de `esl.py` —que entra a los `GRUP` sin usar su tamaño— y el de `census/parser_esm.py` —que comprueba la identidad en tres niveles— cuentan **exactamente los mismos records** en los **10 de 10** plugins: **1.188.811** en total.
**CONSULTA**: `len(esl.recorrer_formids(d))` contra el recorrido de `Plugin` para cada archivo.
**N**: 10 plugins, 1.188.811 records.
**EXCEPCIONES**: 0. Lo que el cruce **no** cubre: `esl.py` nunca lee el tamaño de un `GRUP`, así que un `GRUP` con el tamaño inflado no le cambia el resultado. Su comprobación de cierre es la cadena de records, no las tres identidades.

### 10. (#21) El piso de 0x800 para FormIDs de ESL es del Creation Kit, no del motor

**AFIRMACIÓN**: De los **3 archivos `.esl`** de una instalación SE —todos marcados como ESL y cargados por el juego— los **1.032** records propios tienen índices de objeto de **0x001 a 0xD9A**, y **ninguno** supera **0xFFF**. En `_ResourcePack.esl`, **368 de 373** están **por debajo de 0x800**.
**CONSULTA**: clasificación de cada FormID por índice de mod contra la cantidad de `MAST` del `TES4`, y el índice de objeto de los propios.
**N**: 3 archivos, 1.197 records, 1.032 propios.
**EXCEPCIONES**: ninguna por encima del techo. **Esto refuta una regla que este repo tenía escrita**: `esl.py` exigía `0x800 ≤ índice ≤ 0xFFF` y habría rechazado a `_ResourcePack.esl`, que Bethesda distribuye y el juego carga. El techo de **0xFFF** sí es del motor —son 12 bits en el espacio `FE:xxx`— y es el único que bloquea; el piso se informa con su medición.

### 11. (#21) Los overrides de un ESL no entran en la cuenta del rango

**AFIRMACIÓN**: `ccQDRSSE001-SurvivalMode.esl` trae **165 records override** —índice de mod menor que sus 5 masters— y **508 propios**. Un override conserva el FormID del master, así que el rango de ESL no lo toca.
**CONSULTA**: `clasificar(formids, len(masters(d)))` sobre cada `.esl`.
**N**: 3 archivos; 165 overrides en uno, 0 en los otros dos.
**EXCEPCIONES**: la versión anterior de `esl.py` reportaba **los 165 como "fuera de rango"** y se habría negado a marcar un ESL que el juego ya carga. La comprobación se aplicaba a *todos* los records no-`TES4` y el informe los llamaba "records propios", que es otra cosa.

### 12. (#31) `formVersion` es 44 en todo lo que Bethesda autoró para SE — y el corpus entero dice lo contrario

**AFIRMACIÓN**: En los **5 plugins autorados para SE** —`_ResourcePack.esl` y los cuatro de Creation Club— los **10.273** records llevan `formVersion` (bytes 20-21 de la cabecera) **44**. Sobre los **10 plugins**, 44 es además el **máximo**: no existe un 45 en 1.188.821 records.
**CONSULTA**: `struct.unpack_from("<H", d, offset + 20)` en cada record no-`GRUP`, separando los 5 masters de 2011 de los 5 autorados para SE.
**N**: 10.273 records autorados para SE; 1.188.821 en total.
**EXCEPCIONES**: 0 en el subconjunto SE. **El corpus entero invierte la conclusión**: solo el **7,65 %** está en 44 y el valor más común es el **39** (26,2 %). No es una excepción a la regla sino otra población: los masters de 2011 llevan, record por record, la versión de la última edición —hay 8 records que nadie tocó desde la **14**—. Es historia del archivo, no lo que escribe hoy el Creation Kit. Es la tercera vez en el proyecto que el subconjunto invierte la respuesta, después de `bhkRadius` y la máscara especular.

**Confirmado en el juego.** El `.esl` del hacha de Tencent salió con 0 en sus tres records: el plugin cargó, el VALOR se leyó bien y el PESO y el DAÑO salieron en 0. Con 44, el mismo record dio **peso 27 y daño 26**. El motor lee el `DATA` con el layout de la versión declarada, y el único síntoma fue un número mal en una pantalla. `skills/asset-nuevo-skyrim/scripts/verificar_plugin.py` lo reprueba; `--falsificar` torció un record de cada uno de los 5 plugins autorados para SE a 0, 39 y 45, y los 15 reprobaron.

### 13. El índice de mod de un FormID nunca pasa la cantidad de masters — salvo un record sucio de Bethesda

**AFIRMACIÓN**: En un plugin con N masters, el byte alto del FormID de cada record es **≤ N**: N es el propio plugin y cada índice menor, un override de ese master. Se cumple en **1.188.810 de 1.188.811** records.
**CONSULTA**: `form_id >> 24` contra la cantidad de `MAST` del `TES4`, en cada record no-`TES4` de los 10 plugins.
**N**: 10 plugins, 1.188.811 records.
**EXCEPCIONES**: **1**, con nombre: el `GMST` **`iDaysToRespawnVendor`** (`0123C00E`) de `Skyrim.esm`, índice 1 en un archivo **sin** masters —apunta a un plugin que no existe—. La regla lo marca, y el juego carga `Skyrim.esm` igual. Por qué ese record no rompe nada **no está medido**.

**Lo que la regla no ve.** El `.esl` del hacha del 20/9 tenía el `WEAP` en `00000800`: índice 0, un override de `Skyrim.esm`. Estructuralmente válido, así que pasa. Pero `00000800` **no existe** en `Skyrim.esm` —el más cercano es `00000810`—: el plugin estaba *inyectando* un record en el espacio del master. La inyección es una técnica usada y funciona, pero choca si una actualización ocupa ese número. Verificarlo exige cargar el master; no hay un N que la vuelva regla, y queda como observación. La línea `OBS` de `verificar_plugin.py` —`0 propio(s), 1 override(s)`— es lo que lo dejó a la vista.

---

## Armas (`WEAP`)

El hacha de Tencent fue la primera arma que hizo el recorrido entero hasta el juego. Estas entradas miden lo que su plugin daba por sentado.

### 14. `DATA` mide 10 bytes y `DNAM` 100 en todas las `WEAP`

**AFIRMACIÓN**: Las **3.359** `WEAP` de los 10 plugins tienen `DATA` de **10 bytes** y `DNAM` de **100**. El `DATA` es valor `u32`, peso `f32`, daño `u16`: con esa lectura el hacha dio **valor 2750, peso 27 y daño 26 en el juego**.
**CONSULTA**: `len()` del `DATA` y del `DNAM` de cada `WEAP`.
**N**: 3.359.
**EXCEPCIONES**: 0. `verificar_plugin.py` lo exige (REGLA 3), y sobre las 3.359 reprueba **cero**.

### 15. El primer byte del `DNAM` es el tipo de animación

**AFIRMACIÓN**: `DNAM[0]` vale 1 espada de una mano, 2 daga, 3 hacha de una mano, 4 maza, 5 espada de dos manos, **6 hacha de dos manos y martillo** (comparten el valor), 7 arco, 8 bastón, 9 ballesta. En las armas base cuyo `EDID` nombra el tipo coincide en **245 de 253**.
**CONSULTA**: `DNAM[0]` contra `battleaxe`, `warhammer`, `greatsword`, `dagger`, `waraxe`, `mace`, `bow` en el `EDID`.
**N**: 253.
**EXCEPCIONES**: las **8** que no coinciden son maniquíes y armas conjuradas —`DummyDagger`, `CWDummyWarhammerSons`, `DLC2BoundWeaponDagger`…—, todas con 1. Ninguna es un arma del jugador.

### 16. Las plantillas traen modelo, y el `WNAM` apunta siempre a un `STAT`

**AFIRMACIÓN**: **2.868** `WEAP` tienen plantilla (`CNAM`) y **las 2.868 traen su propio `MODL`**: la plantilla no quita el modelo, como yo suponía. Las armas base —sin `CNAM`— son **472**, y son las que sirven de donante. De esas, **463** tienen `WNAM` (el modelo de primera persona) y **las 463 apuntan a un `STAT`**.
**CONSULTA**: el `WNAM` resuelto como lo resuelve el motor —índice de mod contra la lista de masters—, no por los 24 bits bajos. La primera corrida lo resolvió por los 24 bits bajos y dio basura (`REFR`, `CELL`, `LAND`…), porque el mismo índice de objeto existe en varios plugins.
**N**: 472 armas base.
**EXCEPCIONES**: las **9** sin `WNAM` son `BoundWeaponBattleaxe`, `BoundWeaponBow` y sus variantes místicas, tres maniquíes `DummyBattleaxe`, `DemoQuestSword1` y un emblema de misión de Dawnguard. Sobre las 3.359 `WEAP` hay 28 sin `WNAM`, contando las de plantilla. Por eso la falta de `WNAM` es observación y no regla.

### 17. El `Prn` del NIF sigue al tipo de arma

**AFIRMACIÓN**: El `NiStringExtraData` `Prn` —dónde se cuelga el arma envainada— corresponde al tipo de animación en **305 de 306** armas del jugador:

| `DNAM[0]` | tipo | `Prn` | N |
|---|---|---|---|
| 1 | espada de una mano | `WeaponSword` | 80/80 |
| 2 | daga | `WeaponDagger` | 35/35 |
| 3 | hacha de una mano | `WeaponAxe` | 26/26 |
| 4 | maza | `WeaponMace` | 23/23 |
| 5 | espada de dos manos | `WeaponBack` | 30/31 |
| 6 | hacha de dos manos, martillo | `WeaponBack` | 53/53 |
| 7 | arco | `WeaponBow` | 54/54 |
| 9 | ballesta | `WeaponBow` | 4/4 |

**CONSULTA**: el `Prn` del NIF de cada arma base, filtrando de forma mecánica: NIF dentro de una carpeta `weapons` y sin `Dummy` ni `Bound` en el `EDID` ni en la ruta.
**N**: 306 armas de 163 NIF distintos.
**EXCEPCIONES**: **1**, `DLC02\Weapons\Nordic\NordicGreatSword.nif`: espada de dos manos con `WeaponSword`. Los **bastones no tienen regla**: `WeaponStaff` en 21 y `SHIELD` en 18 (Miraak, Magnus, Forsworn, los dwemer). Quedaron afuera 60 records que no son armas del jugador (`Clutter\DummyItems`, un pico decorativo) y 66 cuyo NIF no estaba extraído. El hacha lleva `WeaponBack` y **cuelga en la espalda en el juego**.

### 18. Dos convenciones del `TES4` que el motor no exige

**AFIRMACIÓN**: Los 10 plugins vanilla tienen la bandera `LOCALIZED` (`0x80`), y en los 10 el `numRecords` del `HEDR` es **records + `GRUP`s**, exacto.
**CONSULTA**: los flags del `TES4` y el `HEDR` contra un recorrido que cuenta records y grupos por separado.
**N**: 10 de 10 en las dos.
**EXCEPCIONES**: ninguna en vanilla, pero **no son reglas**. El hacha cargó con `HEDR` = 105 (v1) y = 2 (v2), las dos mal, así que el motor no lo valida. Y cargó **sin** `LOCALIZED`, con `FULL` y `DESC` como cadenas literales. Qué hace el motor con `LOCALIZED` y cadenas literales —el formato dice que las leería como IDs de la tabla de cadenas— **no está medido acá**. Copiar los flags del `TES4` de un plugin de Bethesda trae ese bit de arrastre.
