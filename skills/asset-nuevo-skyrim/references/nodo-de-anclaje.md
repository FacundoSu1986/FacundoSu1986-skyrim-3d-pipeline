# El nodo de anclaje: dónde y cómo cuelga tu asset

Esto es lo que hay que resolver **antes** de modelar. No después, porque casi
todo lo que se decide acá —orientación, envoltorio, dónde van las correas— es
imposible de corregir al final sin rehacer la malla.

## Qué es, y qué implica

Un asset equipable que no se deforma con el cuerpo **no se skinnea**. No tiene
`BSDismemberSkinInstance`, ni particiones de body-part, ni pares de pesos por
vértice. `[INVARIANT]`

En vez de eso lleva un `NiStringExtraData` con:

    Name  = "Prn"
    Value = "<nombre del nodo del esqueleto>"     p. ej. "SHIELD"

y el motor emparenta la **raíz del NIF entero** a ese nodo. A partir de ahí la
malla se dibuja **en el espacio local del nodo**, arrastrada por la animación.

Consecuencia directa, y es la que se olvida: **el sistema de coordenadas en el
que modelás no es el del mundo.** Es el del nodo, que está girado y desplazado.

### Corolarios que ahorran una iteración

- Si venís de un pipeline de criaturas, **borrá el reflejo de riggear**. Un
  chequeo que exija "cero bloques de armadura, cero particiones" atrapa el
  copiado por inercia.
- El nombre del nodo **se lee del esqueleto**, no de una lista de internet. El
  `skeleton.nif` humano vanilla tiene 99 nodos `[OBSERVED]`; volcalos y buscá el
  que corresponde. `SHIELD` está verificado; los de armas existen, pero
  confirmalos en el archivo antes de usarlos.
- El `Prn` va en la **raíz** del NIF, no en un shape.

## Medir el marco del nodo

```bash
python scripts/nif_nodos.py skeleton.nif --relativo-a "SHIELD" \
       "NPC L Forearm [LLar]" "NPC L Hand [LHnd]"
```

Salida real sobre el `skeleton.nif` humano vanilla de SSE `[OBSERVED]`:

```
base SHIELD  pos mundo=(-28.86,4.93,65.91)
  el +Z del mundo, en local de SHIELD: (-0.910,0.411,-0.044)
  o sea ARRIBA esta a 155.7 grados en el plano XY local (+Y seria 90; ...)
  NPC L Forearm [LLar]       local=(  -21.98,    0.31,    7.20)
  NPC L Hand [LHnd]          local=(   -7.56,   -0.00,    0.16)
```

Tres cosas salen de ahí, y las tres importan:

**1. El nodo está girado.** El "arriba" del mundo cae a **155,7°** en el plano
XY local, no a 90°. Una decoración modelada con el arriba en +Y sale **girada
66°** en el juego. En Blender se ve perfecta. La corrección es una rotación en Z
de `155,7° − 90° = 65,7°` aplicada a las piezas decorativas **mientras están
centradas en el origen** (girar sobre el origen una pieza centrada en el origen
es girarla en su lugar; hacerlo después de moverla la manda a orbitar).

**2. El hueso corre a lo largo del X local.** Codo en x≈−22, mano en x≈−7,6, los
dos con y≈0. **El antebrazo va por el eje X, pegado a y=0.** Cualquier cosa que
tenga que abrazarlo —correas, un agarre, una empuñadura— tiene que ir **a lo
largo de Y**, cruzándolo, y repartirse sobre la X. Correas a lo largo de X son
*paralelas* al brazo y no lo tocan por ningún lado, que es exactamente el bug
que costó dos iteraciones.

**3. El brazo no está en z=0.** Va de z=7,2 (codo) a z=0,16 (mano): baja. Una
correa cuyo pico esté en z=4 no llega al codo. Y ojo con el pico: la superficie
exterior de una correa de altura `h` con el centro en `z_pico` llega a
`z_pico + h/2`, que es lo que tiene que entrar en el envoltorio.

## Por qué no se puede medir con PyNifly

PyNifly convierte los nodos del NIF en **huesos de Blender**, y los huesos de
Blender tienen su propia convención de ejes (Y a lo largo del hueso). La matriz
que devuelve `bone.matrix_local` ya no es la del archivo: es plausible, tiene
los números en el orden correcto, y **da una orientación equivocada**.
`[PROVIDER]`

(En el proyecto de origen los valores de posición coincidieron de casualidad.
El método seguía estando mal, y hubiera dado un resultado falso con otro nodo.)

Por eso `nif_nodos.py` lee el binario. El layout de `NiNode` en SSE (BSVersion
100) es:

    nameID(4) numExtraData(4) extraData[n](4) controller(4) flags(4)
    translation(12) rotation(36) scale(4) collisionObject(4)
    numChildren(4) children[n](4) numEffects(4) effects[n](4)

La rotación es una `Matrix33` en orden de filas y se aplica como
`v_padre = R · v_local + t`, así que **las columnas de R son los ejes locales
expresados en el espacio del padre**. Componiendo la cadena de padres desde la
raíz salen las transformadas de mundo.

## El envoltorio: ocupar el mismo volumen que el vanilla

Si el asset no ocupa aproximadamente el mismo volumen que su equivalente
vanilla, queda flotando al costado del cuerpo. Medí el vanilla y construí
adentro de esa caja.

Del `dwarvenshield.nif` `[OBSERVED]`:

    malla     X −26,8..26,9   Y −41,2..26,5   Z −13,3..8,1
    colisión  X −21,7..22,1   Y −36,5..21,7   Z  −8,2..3,1

De ahí salieron el centro `XY = (0, −7)` (el centro de la caja de colisión
vanilla) y el radio 29 del escudo nuevo.

**Y la cara frontal mira a −Z.** No se deduce: se comprueba por reparto de
vértices — el umbo central del vanilla llega a Z=−13,3 mientras el borde se
queda en Z≈0, así que el bulto sale hacia −Z. Modelar el domo hacia +Z da un
escudo cóncavo hacia afuera.

Ese envoltorio también alimenta el `OBND` del plugin, que **no puede quedar en
cero**: medilo de la malla escrita. En el proyecto de origen quedó
`[−29,−36,−11, 29,22,5]`.

## Dos sistemas de coordenadas en la misma malla

Esta es la parte que se enreda, así que conviene nombrarla explícitamente.

- **Espacio del nodo** — donde el motor dibuja. Ahí están las medidas del
  esqueleto (codo, mano) y ahí tiene que terminar todo.
- **Espacio de construcción** — donde es cómodo modelar: cada pieza centrada en
  el origen, y al final un traslado al centro del envoltorio.

Las piezas **decorativas** se construyen en el espacio de construcción y se
giran para compensar el nodo. Las piezas **ergonómicas** (las correas) se
posicionan con medidas del esqueleto, que ya están en el espacio del nodo, y por
lo tanto **no se giran**: hay que restarles el centro para que el traslado final
las deje donde va el brazo.

```python
def a_coords_de_construccion(x, y):
    return x - CENTRO_XY[0], y - CENTRO_XY[1]
```

Tener esa función con nombre, en vez de restar a mano en cada llamada, es lo que
evita que dentro de dos semanas alguien gire las correas "por consistencia" y
las mande otra vez al aire.

## El render de pose: el juego, fuera del juego

Un render del `.blend` muestra el espacio de construcción, donde **todo se ve
bien por definición**. Para ver lo que va a ver el jugador:

1. leer la matriz de mundo del nodo de anclaje del `skeleton.nif`;
2. aplicársela a la malla;
3. dibujar el hueso relevante como un cilindro entre sus dos extremos (codo →
   mano);
4. poner la cámara mirando desde el costado del personaje, con el +Z del mundo
   arriba.

Eso contesta de una las dos preguntas que si no solo contesta una captura del
juego: si la decoración queda derecha, y si las correas **cruzan** el hueso.

En el proyecto de origen es `scripts/10_pose_brazo.py`, y es el paso que
convirtió "probá y mandame una foto" en "mirá este PNG".

## No confundir con el marcador de inventario

`BSInvMarker` es otra cosa: define cómo gira la pieza en la vista 3D del menú de
inventario (rotación en centésimas de grado + zoom). No tiene nada que ver con
cómo se equipa. Copiá los valores del vanilla equivalente y seguí; si la pieza
se ve de canto en el inventario pero bien en la mano, es esto y no el `Prn`.
