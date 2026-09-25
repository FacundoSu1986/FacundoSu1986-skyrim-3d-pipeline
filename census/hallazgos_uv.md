# Hallazgos del censo de UV — Skyrim SE

Formato fijo: `AFIRMACIÓN — CONSULTA QUE LA PRODUJO — N — EXCEPCIONES ENCONTRADAS`.
Sin recomendaciones. Sin umbrales inventados.

**Muestra, no censo completo.** 2.978 archivos tomados al azar con semilla fija,
hasta 120 por clase, sobre 32 clases. No es el corpus entero (22.394): una
primera corrida completa se cortó y lo que quedó era 100 % `actors/`, que es un
sesgo, no una muestra. Los N van declarados en cada entrada.

---

### 1. Validación del medidor

**AFIRMACIÓN**: El área rasterizada contando profundidad coincide con la suma
analítica de áreas de triángulo —dos caminos independientes al mismo número—
con un desvío peor de **0,302 %** sobre archivos reales. Y las UV extraídas
coinciden **exactamente** con las que lee Blender por PyNifly.
**CONSULTA**: `python census/parser_uv.py --autotest <corpus>`; cruce contra
Blender sobre mallas estáticas.
**N**: 12 shapes para el cruce analítico; 20 archivos y 8.442 coordenadas para
el cruce contra Blender.
**EXCEPCIONES**: peor discrepancia contra Blender **0,000000** (half-float a
float32 es exacto). 1.998 shapes de `armor/` leídos sin violar ninguna
identidad de tamaño, 0 errores.

> **Los números de arriba se midieron; el exit code no los respaldaba.**
> Los dos casos de la suite que dependen del corpus no podían fallar: el
> del cruce analítico calculaba "peor desvío" sobre cero shapes y 0,0 < 0,02
> imprimía `ok`; el de la identidad de tamaño acumulaba los errores en un
> contador y le sumaba al total **otro** contador que nunca se incrementaba.
> Apuntada a una carpeta sin un solo NIF, la suite decía "Sin fallas" y
> devolvía 0. Corregido, y con un test que enumera la propiedad —no el
> caso— para que un caso futuro escrito con el mismo reflejo caiga ahí.

### 2. Dos defectos que la suite atrapó ANTES de censar nada

**AFIRMACIÓN**: (a) Sin regla de relleno, dos triángulos que comparten una
arista cuentan dos veces las celdas de esa arista: un atlas de 4 islas **bien
separadas** reportaba 816 celdas solapadas en vez de 0. (b) Los índices de
triángulo en SSE son **globales**, no locales a la partición; remapearlos por el
vertex map reventaba en 624 shapes.
**CONSULTA**: casos analíticos (d) y (e) del autotest; `--autotest meshes/armor`.
**N**: 4 islas sintéticas; 2.622 shapes de `armor/`.
**EXCEPCIONES**: el archivo con el que se probó primero, `steamcenturion.nif`,
tiene 1.106 vértices de partición sobre 1.106 globales — los dos espacios
coinciden y el defecto (b) **no se nota ahí**. El caso de prueba era degenerado.

> Sobre una malla real, (a) son miles de aristas internas: el solape de todo el
> censo habría salido inflado por un borde falso en cada una. Plausible, con
> decimales, y equivocado.

### 3. El solape intra-shape es bimodal

**AFIRMACIÓN**: Fracción de la huella UV cubierta por 2+ triángulos, por shape:
mediana global **0,249**. Pero la distribución no se concentra en el medio:
**39,1 %** de los shapes no tiene nada de solape (<0,001) y **28,7 %** lo tiene
casi todo (>0,95).
**CONSULTA**: percentiles de `solape_huella` por clase.
**N**: 8.441 shapes con UV.
**EXCEPCIONES**: por clase la mediana va de **0,000** (`actors`, `creationclub`,
`magic`) a **1,000** (`_byoh`). `furniture` 0,803; `loadscreenart` 0,435;
`architecture` 0,267.

### 4. Profundidad de reuso

**AFIRMACIÓN**: Área UV total dividida por la huella: mediana **1,78**,
p90 **8,00**.
**CONSULTA**: `1 / (1 - solape_exceso)` por shape.
**N**: 7.395 shapes.
**EXCEPCIONES**: máximo 472. Medido en tres archivos conocidos:
`dwarvenshield.nif` 1,00 (sin reuso); `soulgemgreater01.nif` 2,26;
`dwarvensteamcenturion.nif` 3,33.

### 5. La mitad del corpus sale de [0,1]

**AFIRMACIÓN**: **4.153 de 8.441** shapes (49,2 %) tienen al menos un triángulo
con UV fuera del cuadro unitario.
**CONSULTA**: conteo de `tris_fuera_01 > 0`.
**N**: 8.441 shapes.
**EXCEPCIONES**: se concentra donde se espera repetición de textura —
`dungeons` 74 %, `dlc02` 68 %, `architecture` 62 %, `furniture` 61 % — y baja en
`loadscreenart` (40 %). Salir de [0,1] es *tiling*, no un defecto.

### 6. El resultado negativo: compartir texture set y pisarse es LA NORMA

**AFIRMACIÓN**: De los grupos de 2 o más shapes que comparten un mismo
`BSShaderTextureSet`, la mediana de solape entre ellos es **0,888**, y solo
**42 de 481 (9 %)** no se pisan.
**CONSULTA**: rasterización conjunta de todos los shapes de un archivo que
referencian el mismo texture set.
**N**: 481 grupos.
**EXCEPCIONES**: p10 = 0,044, o sea que existen grupos limpios; pero son la
minoría. El `steamcenturion.nif` vanilla tiene **15 shapes sobre un solo texture
set, pisándose 0,938** — y en el juego se ve perfecto.

> **Esta entrada existe para refutar la hipótesis que motivó el censo.**
>
> La pregunta "¿los shapes que comparten textura se pisan en UV?" se planteó
> como la que detectaría el bug de "texturas desordenadas". **No sirve para
> eso.** Pisarse es lo que hace Bethesda por defecto, en el 91 % de los casos.
>
> Lo que estaba mal en el proyecto de origen no era el solape: era que cada
> pieza apuntaba a la región equivocada del atlas. El solape es el mecanismo
> normal de reuso; el defecto era la *correspondencia*, y este censo no la mide.
>
> Un umbral de solape habría marcado como rotas 8 de cada 9 mallas del juego.

---

## Lo que este censo NO mide, declarado

- **Correspondencia UV↔textura.** Si una pieza mapea a la región equivocada del
  atlas —el defecto real del proyecto de origen— este censo no lo ve. Haría
  falta comparar el contenido de los téxeles, no la geometría de las islas.
- **Sesgo del rasterizador.** Muestreo por centro de celda: un triángulo más
  fino que una celda puede no contener ningún centro y contar como área cero.
  Real, medido en el autotest, no disimulado.
- **Resolución 256 en la muestra.** Contra la suma analítica el desvío va de
  −0,00 % a −0,87 %. Suficiente para distribuciones, no para valores por shape.
- **La cola de densidad de téxel.** La dispersión p90/p10 dentro de cada shape
  da mediana 2,3 y p90 15,5, pero la cola llega a valores absurdos por
  triángulos casi degenerados en UV. Se filtran los no finitos y los que caen
  por debajo de un piso relativo; aun así el máximo no es interpretable y por
  eso no se publica como dato.
- **No es el corpus completo.** 2.978 de 22.394 archivos.

> Una versión anterior de la entrada 5 reportaba un p10 (4,2) **mayor** que la
> mediana (1,5), que es aritméticamente imposible. La causa: valores no finitos
> envenenan `sorted()` —NaN compara falso contra todo— y la lista salía
> desordenada. Un percentil que viola su propio orden es la señal más barata de
> que hay basura en los datos.

### (#41) El NIF guarda la V con el origen ARRIBA: un conversor desde OBJ tiene que invertirla

**AFIRMACIÓN**: Un NIF almacena la coordenada V con el origen en la **fila 0 de la imagen** (convención DirectX); un OBJ y Blender la almacenan con el origen abajo. Un conversor OBJ → NIF que copie la V tal cual deja **todo el mapeo espejado en vertical**, y no da ningún error.

**CONSULTA QUE LA PRODUJO**: tres líneas independientes, porque ninguna sola alcanzaba.

1. **PyNifly**, el importador que usa la comunidad de modding, **invierte la V al importar**. Comparando las UV que devuelve Blender contra los bytes del archivo, apareando por posición: `elvenbattleaxe.nif` **2.648** loops invertidos contra **13** iguales; `ironbattleaxe.nif` **1.370** contra **23**; `daedricsword.nif` **2.716** contra **16**. Los pocos "iguales" son los que caen cerca de v = 0,5, donde invertir no cambia nada.

2. **El corpus**, de forma independiente. Las zonas vacías de un atlas son negro sólido, y eso se detecta **en los bytes comprimidos** de DXT1/DXT5 sin decodificar nada: un bloque de 4×4 con `color0 == color1 == 0` e índices en cero. Muestreando las UV vanilla sobre ese mapa, tomar `v` como fila desde arriba cae sobre pintura el **69,5 %** de las veces contra el **58,3 %** de la versión invertida, y gana en **86 de 120** archivos con al menos 25 % de atlas vacío.

3. **Un control renderizado**: la malla de `elvenbattleaxe.nif` con su propia textura vanilla sale correcta **solo** con la V invertida.

**N**: 3 archivos y 6.734 loops para PyNifly; 120 archivos para el corpus; 1 para el control.

**EXCEPCIONES ENCONTRADAS**: la línea 2 **no es unánime** — 30 de 120 archivos prefieren lo contrario, y los casos más fuertes en contra son mallas de ojo (`EyeBrown.dds`), donde la región que usa la malla es tan oscura que comprime a bloques negros y el detector la cuenta como vacía. Por eso la línea 2 queda como **tendencia**, no como prueba, y la afirmación se apoya en la 1, que es categórica.

> **Cómo se comprueba**: `skills/modelo-ia-a-skyrim/scripts/verificar_uv.py <origen.obj> <exportado.nif>`. Aparea por posición **normalizada por la caja de cada lado**, porque el conversor escala el modelo a tamaño de arma (en el hacha, ×79,7); del lado del NIF, la caja de **todas sus piezas juntas** (con la de cada pieza, el hacha de Filo Celeste —dos piezas por material— apareaba 0 vértices; con la de la unión, 12.898 invertidas y 0 iguales). Sobre los archivos reales del hacha: **8.299 invertidas, 0 iguales** (exit 0); regenerando el mismo NIF sin la inversión, **0 invertidas, 8.299 iguales** (exit 1).

> **Por qué importa**: con el atlas ruidoso de una IA 3D —una isla por triángulo— el espejado no se nota, porque ya era ruido. Con una textura horneada salta a la vista, y el síntoma se confunde con "el horneado salió mal", que es el paso más caro de rehacer.
