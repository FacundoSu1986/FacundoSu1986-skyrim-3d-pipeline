# Capa HD: texturas horneadas desde la malla de la IA

El paso 7 de `SKILL.md` en detalle. Va **después** de que la malla sea legal
(pasos 1–6) y no la reemplaza: si un gate de integridad falla, subir de
resolución no lo arregla.

La idea central: la IA ya entrega una **escultura**. El paso 4 la decima al
presupuesto y tira el detalle. Si se guarda la versión soldada **sin decimar**,
ese detalle vuelve a la baja por el bake, como normal map. ZBrush sirve para
limpiar o agregar detalle a esa malla alta: es opcional y no forma parte del
camino.

## El orden

```
4.  preparar_parte.py ... --guardar-alto partes/X_alto.blend
    salud_malla.py antes despues
4b. UV de la baja, en Blender, DESPUES de todo modificador que agregue caras
    (trampa 32). Atlas compartido: area proporcional al area 3D (trampa 17).
    salud_malla.py otra vez: cortar costuras parte vertices.
5-6. Montar y riggear. Todo lo que mueva o deforme la baja se le aplica IGUAL
    a la alta (trampa 34), o el bake sale corrido.
7a. hornear.py baja.blend X_alto.blend texturas/ 2048
7b. Albedo: quitar la luz horneada del generador (trampa 21).
7c. _n: RGB del normal + mascara especular en el alfa -> DXT5 con mipmaps.
    mascara_especular.py [--arma] sobre el .dds escrito.
8.  Exportar y verificar, sin cambios.
```

La regla que ordena todo esto: **la malla de juego no sale de Blender.** Rehacer
las UV en Blender no rompe el rig (las UV no dependen de los grupos de vértices).
Lo que sí puede romperlo es el ida y vuelta por otra herramienta, que puede
reordenar o fusionar vértices.

## 7a. Hornear — `scripts/hornear.py`

```
blender -b --python scripts/hornear.py -- baja.blend X_alto.blend texturas/ 2048
```

Hornea al doble y reduce 2×2 con `scripts/reducir_horneado.py`: el albedo se
promedia en lineal, el normal se renormaliza y el AO se promedia simple
(trampa 35). El normal sale con el verde tal cual, `POS_Y` (trampa 30). El
albedo sale con `EMIT` (trampa 31).

Límites que hay que conocer:

- La reducción es Python puro. A 2048 final (4096 horneado) es manejable; a
  4096 final horneás 8192² y la lista de píxeles ocupa varios GB. `[no medido]`
- Una malla por archivo. Si la parte tiene varias piezas, horneá cada una o
  unilas antes.
- El albedo necesita que las imágenes de la alta estén dentro del `.blend`
  (empaquetadas) o accesibles en disco. Si no aparece una textura, el script
  avisa que el albedo salió casi negro.

## 7b. Albedo

El generador texturiza desde imágenes iluminadas: el albedo trae sombras que el
juego vuelve a aplicar (trampa 21). Si el generador ofrece salida PBR o
"delight", pedila. Si no, atenuá el rango bajo con una curva y bajá la
saturación de las zonas oscuras. No se recupera del todo.

El AO horneado se puede multiplicar suave sobre el albedo, para que las
concavidades tengan contacto. Cuánto, se juzga en el juego: no hay un número
medido. `[no medido]`

Si no hay recortes (pelo, rejas), no hace falta alfa: DXT1. Con alfa, DXT5.

## 7c. `_n` y máscara especular

- En el `_n`, RGB es el normal en espacio tangente y el **alfa es la máscara
  especular**. Usá **DXT5**: el 100 % de los 12.075 `_n` del corpus lo es.
  DXT1 no tiene alfa, así que la máscara desaparece.
- Evitá BC7 en el `_n`: `mascara_especular.py` no puede medir su alfa y el gate
  se pierde. Para el albedo, BC7 funciona (se usó en el hacha, trampa 35), pero
  el corpus vanilla no tiene ninguno.
- Máscara gris, no blanca. En armas: `mascara_especular.py --arma` (como mucho
  10 % de bloques en blanco; las armas del corpus están por debajo del 6,9 %).
- Mipmaps siempre. Potencia de 2 siempre: 0 excepciones en 32.241 texturas.

## Resolución: partir del corpus

Mediana del lado mayor por clase (`census/hallazgos_texturas.md`, hallazgo 8):
`actors` 512, `clutter` 512, `architecture` 1024, `armor` 1024. Solo el 0,18 %
llega a 4096.

| Clase | Partir en | Techo razonable |
|---|---|---|
| clutter, armas chicas | 512–1024 | 2048 |
| armadura, armas grandes | 1024–2048 | 2048 |
| arquitectura principal | 2048 | 4096 |

Los techos son criterio, no medición. Mirar de cerca en primera persona decide
más que el número. `[no medido]`

## Replacer: ruta vanilla

Si reusás la ruta de textura vanilla, el DDS nuevo reemplaza la textura en
**toda** malla que la use, no solo en la tuya. Antes de reusarla, fijate si es
compartida. Si lo es, usá una ruta propia y cambiala en el NIF.

## Qué no hacer

- Subir los triángulos para que se vea HD. El detalle va en el `_n`.
- Pasar la malla de juego por ZBrush.
- Copiar el metal/rugosidad del generador a `_n` o `_m`: el shader vanilla no es
  PBR.
- Invertir el verde "porque es DirectX" sin un render de control (trampa 30).

## Gates

Por asset, en este orden:

1. `salud_malla.py` después de 4 y de 4b.
2. `census/parser_uv.py`: `solape_huella` = 0 sobre el archivo escrito
   (trampa 32).
3. `mascara_especular.py [--arma]` sobre el `_n.dds`.
4. `verificar_export.py nuevo.nif vanilla.nif`, que también compara rutas de
   textura.
5. Render con luz rasante y sin albedo: el relieve tiene que salir hacia
   afuera, no hundirse.
6. En el juego: que no parezca plástico y que las sombras no queden fijas al
   girar.

El CI no cubre los puntos 5 y 6 ni el bake. `reducir_horneado.py` sí tiene
autotest.

## Rama opcional: Community Shaders PBR

`[PROVIDER]` Es otro juego de archivos y un JSON de material propio. No se
mezcla con el `_n` vanilla en el mismo asset y queda fuera de esta referencia.
