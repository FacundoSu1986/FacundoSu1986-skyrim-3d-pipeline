# Cómo pedirle el modelo a la IA 3D

Índice:
- [Qué formato descargar](#qué-formato-descargar)
- [Imagen o texto](#imagen-o-texto)
- [Una parte por pedido](#una-parte-por-pedido)
- [Las frases que no pueden faltar](#las-frases-que-no-pueden-faltar)
- [Cómo expresar proporciones](#cómo-expresar-proporciones)
- [Negative prompts](#negative-prompts)
- [Plantillas por tipo de asset](#plantillas-por-tipo-de-asset)
- [Qué NO pedir](#qué-no-pedir)
- [Qué esperar que venga mal igual](#qué-esperar-que-venga-mal-igual)

---

> **Todo lo de esta página es `[PROVIDER]`.** Describe cómo se comportaban los
> generadores cuando se escribió, y ese es el material que caduca más rápido de
> toda la skill: las capacidades cambian de versión a versión y de plan a plan.
> Tratalo como punto de partida y **comprobá contra lo que ofrece tu generador
> hoy**, sobre todo antes de descartar una opción por "no existe". El criterio
> técnico de por qué cada cosa importa —eso sí dura— está en
> `limites-skyrim.md`.

## Qué formato descargar

**Bajá el formato que traiga las texturas, y comprobá que las traiga.** Eso
suele ser GLB: geometría, UV y texturas PBR en un solo archivo, sin material
externo que se pierda.

| Formato | Trae texturas | Trae UV | Peso típico |
|---|---|---|---|
| **GLB** | sí, embebidas | sí | 10–20 MB |
| FBX | **depende**: embebidas, en carpeta aparte, o nada | sí | variable |
| OBJ + MTL | sí, si viene el MTL y los archivos de imagen | sí | variable |
| USDZ | sí | sí | similar a GLB |

FBX y OBJ **pueden** llevar texturas perfectamente: el problema no es el
formato, es qué arma el generador al convertir. `[OBSERVED]` El zip de FBX que
ofrecía uno de ellos era una conversión de geometría sola, sin UV ni material.

**El peso delata.** Si el archivo pesa cientos de kilobytes en vez de decenas de
megabytes, no tiene texturas embebidas. No hace falta abrirlo para saberlo — y
`medir_parte.py` te lo confirma en un segundo.

Volver a descargar la misma generación en otro formato **no gasta créditos**.
Si ya generaste y bajaste el formato equivocado, no regeneres: volvé a bajar.

**Ojo con el nombre de archivo.** Los generadores nombran por el prompt, así que
dos pedidos parecidos producen archivos con el mismo nombre y se pisan.
Renombralos al guardar.

## Imagen o texto

Si el generador acepta **image-to-3D**, usalo. El texto describe; la imagen
manda la forma. Con imagen, varias partes de un mismo diseño salen coherentes
entre sí; con texto solo, cada parte parece de un diseño distinto.

**Ojo: en muchos generadores no podés dar imagen Y prompt a la vez.** `[PROVIDER]`
Suelen ser dos modos separados —texto→3D o imagen→3D— y en el segundo el campo
de texto no existe o se ignora.

Y en general **no es una limitación de la interfaz, es de la arquitectura**: los
reconstructores imagen→3D infieren la geometría de la imagen, y el texto no es
una entrada del modelo. Cambiar de herramienta no lo resuelve.

> Una versión anterior de este documento decía "la combinación que funciona
> mejor es imagen + prompt de texto", sin etiqueta y sin haberlo comprobado. Es
> el error de siempre: escribir lo que suena razonable en vez de lo que se
> midió.

**La salida es meter el prompt DENTRO de la imagen, antes del 3D.** En vez de
pedirle al generador 3D que combine forma y estilo, generá primero una imagen
que ya tenga los dos:

    render ortográfico del asset vanilla que vas a reemplazar
            |  ControlNet (depth o canny) + prompt de estilo
    imagen con las proporciones del vanilla y tu estilo
            |  imagen -> 3D
    malla que nace con la silueta del esqueleto correcto

Esto ataca la causa de que el ajuste sea difícil: dejás de pelear contra una
forma que nunca fue pensada para ese esqueleto. La silueta la impone el vanilla;
el prompt solo decide los materiales.

No hace falta una herramienta específica: cualquier cosa con img2img o
ControlNet sirve para el paso del medio, y la malla la seguís pidiendo donde te
dé mejor calidad. Un editor de nodos (tipo ComfyUI) da más control, pero es la
versión avanzada, no el requisito.

**Multivista: usá la que el generador tenga de verdad.** `[PROVIDER]` Varios
generadores aceptan hoy varias vistas **como entradas separadas** (una ranura
para frente, otra para perfil, otra para dorso). Eso funciona bien y es mejor que
una sola imagen: resuelve la profundidad, que es justamente lo que peor sale.

Lo que no funciona es **pegar las tres vistas en una sola imagen** y pasarla por
la ranura de imagen única. Ahí el generador ve tres objetos en una escena (ver la
sección siguiente).

O sea: la regla no es "una sola vista", es **una vista por ranura**.

## Una parte por pedido

Dos motivos distintos, los dos importantes.

**El técnico.** Un generador al que le pasás una lámina de tres vistas
(frente / perfil / dorso, como una hoja de personaje) la interpreta como **tres
objetos en una escena** y devuelve tres modelos completos parados uno al lado
del otro. El síntoma es fácil de reconocer: el archivo mide más de ancho que de
alto. Le pasó al proyecto de origen dos veces.

**El de calidad.** Los generadores tienen un presupuesto de detalle más o menos
fijo por pedido (del orden de 400–600 mil triángulos). Repartido en un cuerpo
entero, la cara se lleva unos pocos miles y sale sin ojos ni rasgos. Pidiendo la
cabeza sola, esos mismos 450.000 triángulos van todos ahí.

**Cómo partir un personaje:** cabeza, torso, cadera, brazo, pierna, pie. Seis
pedidos. Pedí **un solo** brazo, una sola pierna y un solo pie: el espejado se
hace en Blender y sale perfectamente simétrico, cosa que un modelo generado
nunca es.

## Las frases que no pueden faltar

Van en todos los pedidos. Cada una corresponde a un fallo real que aparece
recién en el juego.

**`solid closed volume with real thickness, not flat sheets`**

Los generadores devuelven superficies abiertas de una sola cara. Skyrim dibuja
con backface culling por defecto: una cara mirada desde atrás **no se dibuja**.
El síntoma en el juego son brazos invisibles, agujeros en el torso y piezas que
aparecen y desaparecen según el ángulo de cámara.

Se puede parchear con `Solidify` en Blender, pero es mucho mejor que venga con
volumen: el solidify sobre una cáscara muy irregular genera geometría
autointersectada.

**`front facing`**

En Skyrim el frente de un actor es **+Y**. Los generadores suelen entregar el
modelo mirando a −Y. Si entra así, la criatura pelea de espaldas: camina hacia
donde mira el jugador pero ataca en la dirección opuesta.

Es corregible con un giro de 180° en Blender, pero **comprobá primero hacia
dónde mira de verdad**: girar por costumbre un modelo que vino bien produce
exactamente el mismo síntoma que no girar el que vino mal.

El valor principal de la frase no es garantizar la orientación —ningún generador
la respeta de forma confiable— sino que las seis partes vengan orientadas
**igual entre sí**, que es lo que hace que el montaje cierre.

**`single object, no base, no pedestal, no ground plane, plain background`**

Sin esto aparece un pedestal, una peana o un pedazo de suelo pegado al modelo,
que después hay que identificar y borrar a mano.

## Cómo expresar proporciones

Los generadores **no respetan escala absoluta** y no entienden unidades. Lo que
sí captan razonablemente bien es una proporción dicha en lenguaje llano.

La escala no importa —se ajusta en Blender en un paso—; **la proporción sí**,
porque una parte con la forma equivocada no se arregla estirándola.

Traducí siempre la medida a palabras, y de paso dejá el número por si el
generador lo aprovecha:

| Medida | Cómo decirlo |
|---|---|
| ancho 1,04 : alto 1,00 | "about as wide as it is tall" |
| fondo 0,78 : alto 1,00 | "roughly three quarters as deep as it is tall" |
| ancho 0,32 : alto 1,00 | "tall and slender, the width only about a third of the height" |
| fondo 2,44 : alto 1,00 | "much longer front-to-back than it is tall, about two and a half times" |
| fondo 1,29 : alto 1,00 | "the front-to-back depth is the largest dimension" |

Poné en **mayúsculas** la dimensión contraintuitiva. Un torso que es más
profundo que ancho, o un pie mucho más largo que alto, es exactamente lo que el
generador va a ignorar si no lo destacás:

> Proportions: slightly taller than it is wide, and **DEEPER** front-to-back
> than it is wide, because the boiler projects behind and the chest projects in
> front.

Explicar **por qué** la proporción es así ayuda: el generador usa esa
justificación para construir la forma.

## Negative prompts

Si el generador los acepta, valen mucho. Base para cualquier asset de juego:

    flat, hollow, thin sheets, paper-thin, multiple views, turnaround sheet,
    three figures, base, pedestal, ground plane, stand, display case

Y agregá lo específico de cada pedido. Un ejemplo real: pedir una cabeza con
"a sharp downward-pointing beak" produjo un **cráneo humano**, porque el
generador leyó "beak" como nariz. El arreglo fue nombrar al animal desde la
primera línea *y* prohibir explícitamente lo que no querías:

    human skull, skull, cranium, human face, nose, nostrils, mouth, teeth,
    jawbone, lips, cheekbones

Cuando una palabra clave se interprete mal dos veces, no insistas con
sinónimos: **prohibí la interpretación equivocada por nombre**.

## Plantillas por tipo de asset

### Parte de criatura

    A single ornate mechanical automaton [PARTE], front facing. [DESCRIPCIÓN
    DE FORMA Y MATERIALES]. Proportions: [PROPORCIÓN EN PALABRAS, con la
    dimensión contraintuitiva en mayúsculas]. Solid closed volume with real
    thickness, not flat sheets. Single object, [qué NO incluir: no head, no
    arms, no legs], no base, no pedestal, plain background.

Poné el bloque de materiales **idéntico en las seis partes** o no van a
combinar. Ejemplo de bloque de estilo reutilizable:

    polished ivory-white ceramic armor plates over dark bronze machinery, gold
    filigree trim, glowing pale-blue runic inlays, ancient artifact, clean
    hard-surface design

### Arma

    A single [tipo de arma], side view, blade pointing up, hilt at the bottom.
    [descripción]. The whole weapon is one connected solid piece. Proportions:
    [largo total contra ancho de hoja]. Solid closed volume with real
    thickness. Single object, no hand, no character, no scabbard, no base, no
    pedestal, plain background.

Las armas son el caso más fácil: no llevan rig (van colgadas de un nodo del
esqueleto por un `NiStringExtraData "Prn"`) y el presupuesto de polígonos es
generoso respecto de lo que ocupan en pantalla.

### Pieza de armadura

    A single [pieza] of plate armor, front facing, worn shape with a hollow
    interior so it can fit over a body. [descripción]. Solid closed volume with
    real thickness, not flat sheets. Single object, no character, no body
    inside, no base, no pedestal, plain background.

`hollow interior so it can fit over a body` importa: si sale como un bloque
macizo, el cuerpo debajo lo atraviesa.

### Clutter / decorado

El caso más permisivo. Alcanza con las tres frases obligatorias y una
descripción. Pedí explícitamente que la base sea plana si el objeto se apoya:
`flat bottom so it sits on a table`.

## Qué NO pedir

- **No pidas que venga riggeado.** Los esqueletos que generan no son el de
  Skyrim y no sirven. El rig se hace contra el esqueleto vanilla.
- **Cuidado con el low-poly del generador.** `[OBSERVED]` Pedido como estilo
  ("low-poly"), sacrifica **forma**: te devuelve un modelo facetado y pobre, no
  el mismo modelo con menos triángulos. El resultado fue peor que el vanilla que
  se quería reemplazar.

  `[PROVIDER]` Es distinto de la **retopología** o el **target polycount** que
  varios generadores ofrecen hoy como opción de salida: eso sí es reducción de
  densidad y puede darte una malla más limpia (quads, bucles de borde) de lo que
  sale de decimar. Si tu generador la tiene, probala y comparala.

  Por defecto, y si dudás: **pedí el máximo detalle y decimá en Blender.** El
  decimado por colapso preserva la silueta notablemente bien (447.406 → 8.000
  triángulos, indistinguible) y tenés control sobre el número exacto.
- **No pidas la textura en baja.** Bajá siempre la resolución más alta
  disponible (4096 si la hay) y reducila vos. No se puede recuperar después.

  **Comprobá la resolución que te dieron, no la asumas.** `[OBSERVED]` En el proyecto de
  origen, el mismo generador entregó **4096²** para el modelo de cuerpo entero
  y **512²** para las seis generaciones por parte, sin decir nada. La
  resolución depende de la corrida y del plan, no de la parte. `medir_parte.py`
  la reporta y avisa si es baja.

  Esto pesa en la decisión de trocear: si las partes llegan a 512², seis partes
  a 512² tienen *más* téxeles totales que un cuerpo entero a 4096², pero cada
  pieza tiene menos definición de cerca. Mirá una parte renderizada antes de
  generar las otras cinco.
- **No pidas varias piezas separadas en un archivo.** Vienen como una sola
  malla con cáscaras sueltas y hay que volver a separarlas a mano.

## Qué esperar que venga mal igual

`[OBSERVED]` Aunque hagas todo bien, contá con esto y presupuestalo:

- **Las partes se pisan.** Pediste una cadera y viene con los muslos; pediste un
  pie y viene una bota entera con media pierna. Se recorta con un plano en
  Blender, pero decide cuánto material útil tenés.
- **No es simétrico.** Los dos lados tienen coordenadas distintas, y a veces
  detalles distintos: en el proyecto de origen, **un solo brazo tenía garras**.
  Por eso se pide una sola mitad y se espeja.
- **Es plano.** Un modelo generado desde una imagen frontal tiene poca
  profundidad: del orden de la mitad de lo que tendría un modelo esculpido. De
  perfil se ve delgado. Se puede estirar en Y, con moderación.
- **El detalle se va donde no lo pediste.** Un torso al que le pediste "caldera
  en la espalda" puede ponerla arriba, tapando el cuello. Mirá cada parte
  renderizada antes de montarla.
