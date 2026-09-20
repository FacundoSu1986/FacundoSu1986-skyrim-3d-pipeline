# El plugin: ARMO + ARMA

Todo lo de acá está verificado leyendo el `Skyrim.esm` y el `.esp` generado, no
sacado de documentación. Los FormIDs concretos son del escudo dwemer vanilla
(`DwarvenShield` / `DwarvenShieldAA`) y de `Escudo_Dwemer_SE_v01`. `[OBSERVED]`

## La división del trabajo

| Record | Qué es | Qué pasa si falta o está mal |
|---|---|---|
| **ARMO** | el objeto: nombre, valor, peso, armadura, modelo de mundo | no existe para el juego |
| **ARMA** | *armor addon*: qué malla se pone, sobre qué razas | está en el inventario y **no se dibuja al equiparlo** |

El ARMO apunta al ARMA con un subrecord `MODL`. Un ARMO sin ARMA da un objeto
que se puede tener, vender y equipar **sin que aparezca en el personaje**.

## El error que cuesta una sesión: las razas adicionales

El ARMA tiene un `RNAM` con la raza por defecto (`DefaultRace` = `00000019`) y
además una **lista de subrecords `MODL`, uno por raza adicional**.

**`RNAM` solo no alcanza.** El `DwarvenShieldAA` vanilla lista **23 razas
adicionales**:

```
00013740 0008883A 00013741 0008883C 00013742 0008883D 00067CD8 000A82BA
00013743 00088840 00013744 00088844 00013745 00088845 0010760A 00013746
00088794 00013747 000A82B9 00013748 00088846 00013749 00088884
```

`00013743` es `ImperialRace`. Sin la lista, un imperial equipa el escudo, el
menú dice que está equipado, y **no se ve ni en primera ni en tercera persona**.
Ningún mensaje, ningún log.

Copiá la lista del vanilla equivalente leyéndola del `Skyrim.esm`. Escribirla a
mano es exactamente el tipo de cosa que se hace mal una vez y no se descubre
hasta que alguien juega con otra raza.

**En el Creation Kit** es la lista "Additional Races" del diálogo ArmorAddon. El
CK **no avisa** si está vacía.

## ARMO campo por campo

| Sub | Qué es | Detalle verificado |
|---|---|---|
| `EDID` | Editor ID | |
| `OBND` | caja envolvente, `<6h` | **no puede quedar en cero**; medila de la malla escrita. El escudo nuevo: `−29,−36,−11, 29,22,5` |
| `FULL` | nombre en pantalla | el que buscás con `help "..." 0` |
| `MOD2`/`MOD4` | modelo de mundo masculino / femenino | ruta relativa a `Data\`, p. ej. `meshes\escudodwemer\....nif` |
| `MO2T`/`MO4T` | hashes de textura del modelo | copiables del vanilla |
| `BOD2` | `<II`: slots de biped, clase de armadura | `512, 1` = **slot 39 (Shield), Heavy** |
| `ETYP` | tipo de equipo → `EQUP` | `000141E8` |
| `BIDS` | impact data set → `IPDS` | `000183FE` |
| `BAMT` | material de bash → `MATT` | `00016979` |
| `RNAM` | raza por defecto → `RACE` | `00000019` |
| `KSIZ`/`KWDA` | keywords | `0006BBD2 000965B2 0006BBD7 0008F959` |
| `DESC` | descripción | puede ir vacía (1 byte) |
| `MODL` | → el ARMA | |
| `DATA` | `<Ii`: valor, peso | |
| `DNAM` | armadura ×100 | `2400` = 24,0 |

Y en la **cabecera del record**, no en un subrecord: el bit **`0x40` = Shield**.
Sin ese bit el objeto no se comporta como escudo (no bloquea, no suena).

### La clase de armadura está en `BOD2`, y `Clothing` da 0

El segundo dword de `BOD2` es `0 = Light`, `1 = Heavy`, `2 = Clothing`. Un
escudo creado en el CK que quedó como *Clothing* se equipa perfecto y **suma
0 de armadura**, por mucho que el `DNAM` diga 2400. Es un síntoma distinto de
"no se equipa" y se confunde con un problema de balance.

## ARMA campo por campo

| Sub | Qué es |
|---|---|
| `EDID` | Editor ID |
| `BOD2` | los mismos slots/clase que el ARMO |
| `RNAM` | raza por defecto |
| `DNAM` | prioridades y flags de detección de peso |
| `MOD2`/`MOD3` | modelo masculino: mundo / primera persona |
| `MOD4`/`MOD5` | modelo femenino: mundo / primera persona |
| `MODL` ×N | **las razas adicionales** (una entrada por raza) |

Los cuatro modelos importan: si `MOD3`/`MOD5` (primera persona) faltan, la pieza
existe en tercera persona y no en primera.

## Layout binario, para parchearlo sin editor

Sirve cuando hay que inspeccionar, validar o cambiar un campo puntual sin abrir
el Creation Kit (que reescribe el archivo entero y puede tocar cosas que no
querés).

- **Cabecera de record**: 24 bytes — `tipo(4) tamañoDatos(4) flags(4) formID(4)
  timestamp+vcinfo(4) versión+desconocido(4)`. El `tamañoDatos` **no** incluye
  la cabecera.
- **Cabecera de GRUP**: 24 bytes — `'GRUP'(4) tamaño(4) etiqueta(4) tipo(4)
  stamp(4) misc(4)`. Acá el `tamaño` **sí** incluye la cabecera, y el contenido
  son más records: un GRUP se *entra*, no se saltea.
- **Subrecords**: `tipo(4) tamaño(2)` y después los datos.
- Flag de record **`0x40000` = comprimido**. Un parser que no lo contempla
  tiene que **rechazar** esos records, no leerlos como si fueran planos.

Al parchear, **exigí una prueba de preservación**: reparsear el archivo escrito
y comparar campo por campo contra el original, permitiendo solo los cambios que
pediste (y los tamaños que cambian por arrastre). Y hacelo **idempotente**:
correrlo dos veces tiene que dar el mismo archivo.

## ESL

Marcar el plugin como ESL es encender el bit **`0x200`** en los flags del
record `TES4` de cabecera — **offset 8 del archivo**. Nada más: no hace falta
renombrar a `.esl`, y así no hay que retocar el gestor de mods.

Gana un slot de los 255 que admite Skyrim SE. Para un mod de dos records, vale
la pena.

**El requisito que no da error:** un ESL solo puede tener FormIDs nuevos cuyo
**índice de objeto esté entre `0x800` y `0xFFF`**. Con uno fuera de rango el
juego no se queja: lo remapea, y el objeto sale corrupto o no sale. Comprobalo
**antes** de escribir el flag. (`0x000D62` y `0x000D63` entran; `0x000001`, que
es el tipo de índice que asigna el CK en un plugin nuevo y vacío, no.)

**Lo que rompe, y hay que avisarlo antes de convertir:** el plugin deja de
cargarse con índice `01` y pasa a `FE:XXX`. El FormID del objeto cambia de
`01000D62` a `FExxxD62`, así que **una partida guardada que ya lo tenía en el
inventario deja de encontrarlo**. Hay que volver a agregarlo:

```
help "<nombre>" 4 ARMO
player.additem <formid nuevo> 1
```

`scripts/esl.py` hace la comprobación, deja `.bak` y por defecto no escribe.

## Separar "no se equipa" de "no está cargado"

Son dos bugs distintos y se parecen:

- **`help "nombre" 0` no devuelve nada** → el plugin **no está cargado**. No es
  el NIF, no es el ARMA. Revisá que esté tildado en el gestor de mods, que esté
  en `Data\`, y que su master (`Skyrim.esm`) resuelva.
- **`help` lo encuentra, `player.additem` funciona, pero al equiparlo no se ve**
  → ahí sí: razas adicionales del ARMA, o el NIF (inercia cero → NaN de Havok,
  que también lo vuelve invisible).

## Validar de verdad

El validador del proyecto de origen trae una suite de falsificación que le mete
un plugin **sin el flag de escudo**, **sin `ETYP`**, **con una referencia de
tipo equivocado**, **con `OBND` en cero**, **truncado** y **con el tamaño de
grupo mal**, y exige que los rechace a todos. Sin esa suite, un validador que
siempre dice `ok` es indistinguible de uno roto.

Y validá también **las referencias**: que cada FormID apuntado exista en el
master **y sea del tipo esperado** (`ETYP`→`EQUP`, `BIDS`→`IPDS`,
`BAMT`→`MATT`, `RNAM`/`MODL` del ARMA→`RACE`, `KWDA`→`KYWD`). Un FormID de un
tipo equivocado carga sin error y falla en silencio.
