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
