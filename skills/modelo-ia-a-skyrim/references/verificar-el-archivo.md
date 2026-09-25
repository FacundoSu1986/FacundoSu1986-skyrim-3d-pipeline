# Verificar sobre el archivo: qué cubre cada control, y qué no

La disciplina está en el SKILL.md: el último paso reimporta el NIF generado y
lo compara contra el vanilla, y un chequeo tiene que poder fallar. Acá está la
evidencia, y el detalle de qué cubre cada control, para no darlo por cubierto
cuando no lo está.

## Por qué el archivo y no la escena

Entre la escena de Blender y el archivo que carga el juego hay un exportador, y
ese exportador puede perder o deformar cosas sin avisar. Verificar la escena en
memoria confirma lo que vos armaste, no lo que se va a cargar. El control
completo, reimportando el NIF:

- mismos tipos y cantidades de bloque, misma tabla de strings;
- las posiciones de hueso contra el `skeleton.nif`: desvío esperado 0,0;
- **dónde quedó cada pieza**, que es lo que se rompe cuando el exportador
  desarma el modelo;
- cada pieza con el mismo juego de huesos que su equivalente vanilla, más su
  partición, su UV y su capa de color;
- cada hueso dentro de la caja de la pieza que lo usa.

El tercero encontró un NIF completamente desarmado --las piezas desplazadas
una por una-- que visualmente ya se daba por bueno. Sin él se habría
instalado.

## El último de la lista no es una regla absoluta

Medirlo lo demostró. De 27.927 piezas skinneadas del corpus vanilla, solo el
**24,1 %** tiene todos sus huesos dentro de su propia caja; de 114.751 pares
(pieza, hueso), el **64,8 %**. Escrito en forma absoluta, ese control
reprobaría a tres de cada cuatro mallas de Bethesda. Lo que sirve es su forma
**relativa** --que la distancia del hueso a la caja no crezca respecto del
original--, y eso exige la geometría de la pieza: la compara
`fixtures/comparar.py --fiel`. Ver la entrada 22 de `census/hallazgos.md`.

## Qué hace `scripts/verificar_export.py`, y qué no

Lee los bytes y no abre Blender. Sus REGLAS comparan contra el vanilla la
versión de NIF, los bloques, el tipo de raíz, los nombres, posiciones y ejes
de los nodos, los nombres y la **colocación** de cada pieza, el **formato de
vértice** de cada pieza (qué atributos lleva: UV, normal, tangente, colores,
skin) y sus huesos, particiones y tipo de skin instance. Lo que **no** cubre,
y conviene saberlo antes de darlo por cubierto:

| del control | lo cubre |
|---|---|
| tabla de strings completa | **no**: solo los nombres de nodo y de pieza, que es de donde sale casi toda; las rutas y los nombres de controller, no |
| UV y capa de color por pieza | **que estén, sí** (REGLA `formato`, del descriptor de vértice). **Sus valores, no**: viven en la geometría, que no lee. La V la controla `scripts/verificar_uv.py` contra el OBJ de origen |
| desvío exactamente 0,0 | **no**: usa 0,01, que es el redondeo del lector; el propio vanilla difiere en 0,010 en 4 de 2.112 comparaciones |
| hueso dentro de la caja | **no**, y a propósito: ver arriba |

Para la colocación con la geometría en la mano: `fixtures/comparar.py --fiel`.
**No se empaqueta con la skill**: vive en el repo, igual que
`docs/validacion.md`, que tiene la tabla de todos los controles.

## Un chequeo tiene que poder fallar

Si un control pasa siempre, no prueba nada. Alimentalo a propósito con datos
equivocados --por ejemplo, las posiciones de un esqueleto humano en vez del de
la criatura-- y confirmá que revienta. En el proyecto de origen esa
falsificación dio 7 fallos de 16 huesos comparables: recién ahí el `[ok]`
valió algo. Los controles de la skill traen la suya (`--falsificar`, o los
casos del `--autotest`).
