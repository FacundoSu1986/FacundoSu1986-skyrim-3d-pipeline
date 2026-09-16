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
