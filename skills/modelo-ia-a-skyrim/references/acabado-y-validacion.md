# Del bake correcto al acabado que se parece a la referencia

Usar cuando un nuevo atlas se ve bien en Blender pero falla después del
export, o cuando aumentar resolución apenas mejora lo que ve el usuario.
Complementa [hd-texturas.md](hd-texturas.md); no reemplaza sus controles.

## Conservar el mapeo hasta el archivo entregado

Tres etapas distintas: UV que recibió el bake, UV después de preparar la
exportación, UV del NIF final. `hornear.py` comprueba activa = render en la
primera. `verificar_export.py` comprueba estructura, pero no demuestra que las
coordenadas del atlas sean las que se hornearon. Dos mapas distintos pueden
tener la misma cobertura y el mismo solape.

Cuando el material final usa un solo atlas, preparar una copia con una sola
capa evita ambigüedad. No es una obligación universal de Blender ni una
receta para materiales que aún necesitan varias UV. Después del bake y de
asignar el material final, con el objeto en Object Mode:

```python
from uv_exportacion import conservar_uv

export_obj = source_obj.copy()
export_obj.data = source_obj.data.copy()
conservar_uv(export_obj.data, "UV_Bake")
# Enlazar/seleccionar export_obj según el exportador. Conservar la fuente.
```

El helper verifica nombre y coordenadas por loop; no recupera datos perdidos.
Si la limpieza anterior ya cambió el atlas, volver al checkpoint bueno.
La copia de objeto/malla **todavía comparte materiales**: antes de modificar
nodos que otras piezas utilizan, copiar el material (`material.copy()`) y
asignarlo solo a esta pieza. No hace falta duplicar materiales que no cambian.
La copia del material aún comparte los `node_tree` de sus grupos de nodos:
si el cambio está dentro de un grupo, copiar y reasignar también ese grupo
y los grupos anidados del recorrido que se vaya a editar.
En particular, la alta puede seguir leyendo `UV_Original` mientras la baja
recibe `UV_Bake`; no borrar la primera durante el horneado.

Después de exportar:

1. Reimportar el **NIF entregable** y leer las texturas DDS finales. Una vista
   del `.blend` con los PNG fuente no verifica la compresión ni el export.
2. Comparar posiciones y UV con la copia exportada. El exportador puede
   dividir vértices en costuras y reordenarlos: no comparar por índice ni
   tomar una sola UV por posición. Conservar los candidatos por esquina de
   cara y comprobar correspondencias en ambos sentidos, incluidas costuras.
   Expresar la tolerancia en unidades y en UV según la precisión del formato.
3. Si se lee el binario, normalizar la convención V una sola vez (trampa 29).
   Si se reimporta con PyNifly, no agregar otra inversión por costumbre.
4. Medir solapes y caras UV colapsadas **después** de exportar. Informar su
   cantidad y qué fracción del área 3D representan. La cuantización puede
   colapsar islas diminutas; no ocultarlas bajo «UV perfectas». Revisar su
   ubicación: un detalle focal pequeño puede importar aunque el área sea baja.
5. Comparar material, rutas y propiedades con la versión anterior. En un
   montaje que copia shaders con PyNifly, copiar `shader.properties` no copia
   por sí solo `NiAlphaProperty`: conservar su presencia, flags y umbral si
   corresponde al donante. No agregar transparencia si el material no la usa.
6. Si solo se editó una parte, comparar las demás con la entrega anterior:
   geometría, UV, normales, colores, pesos, particiones, materiales y rutas;
   comprobar también las matrices del esqueleto. La igualdad de nombres o de
   cantidad de shapes no demuestra que permanezcan iguales.

Estos pasos describen el control completo; `uv_exportacion.py` implementa
solamente la limpieza de capas. No se agregó un comparador geométrico de NIF
ni se completaron las fases pendientes del runner con esta referencia.

## Elegir qué hay que mejorar

| Síntoma | Intervención que puede resolverlo |
|---|---|
| El contorno está torcido, dos mecanismos están fundidos o falta un hueco | Corregir geometría; UV nuevas no separan volúmenes |
| Falta un grabado o relieve superficial que sí existe en la alta | Revisar proyección/bake normal y densidad local del atlas |
| El ornamento tampoco existe en la alta ni en sus texturas | Modelar o pintar ese diseño antes de hornear |
| Textura estirada o rasgo en otro lugar | Corregir mapeo, proyección o selección de UV |
| Silueta correcta, detalles presentes pero pixelados | Medir densidad de texels, distribución de islas, mipmaps y compresión |
| Metal lavado, brillos que tapan el dibujo, sombras inmóviles | Revisar albedo, normal, máscara especular y shader con iluminación controlada |

Subir 2K a 4K puede representar más información **que ya exista** en la fuente;
ampliar una imagen borrosa no recupera el diseño perdido. Una reconstrucción
procedural con cilindros más limpios puede mejorar la lectura mecánica y a la
vez perder la ornamentación del original.

Para una misma superficie, una estimación de ganancia de densidad **lineal** es
`(R_nueva / R_vieja) * sqrt(A_uv_nueva / A_uv_vieja)`, con atlas cuadrados de
lado `R` y área UV medida de forma comparable, sin cambiar apilados. Es una
estimación global: medir también por región si hay mucha distorsión. No mide
fidelidad artística ni garantiza nitidez perceptible.

## Una comparación visual que permita decidir

Guardar tres estados: original de alta, versión de juego anterior y candidata.
Usar igual pose, cámara, proyección, escala, iluminación, exposición y gestión
de color. Mantener fijo el encuadre; recalcularlo por los límites de cada pieza
puede hacer que una parezca más gruesa o detallada solo por el zoom.

- Vista frontal, lateral y posterior, más un acercamiento a la zona cambiada.
- Albedo en emisión para separar textura de iluminación; gris con normal y
  luz rasante para separar relieve de color; material final para juzgar metal.
- Distancia de juego y primer plano. Comparar silueta, separación de piezas,
  bordes, continuidad, ornamentos reconocibles y distribución de materiales.

Las métricas estructurales y una imagen de diferencias sirven para detectar
cambios; no deciden si quedó más fiel o más bello. Mostrar la comparación al
usuario y registrar su valoración antes de extender una reconstrucción
artística al cuerpo entero. Si la pieza piloto pierde el detalle buscado,
revisar el diseño de esa pieza antes de aumentar resolución o repetir el método.
La validación en Blender/NIF y la confirmación en Skyrim se reportan por separado.

## Evidencia y límites de estas lecciones

`[OBSERVED]` Iteraciones locales V20/V21 del centurión, septiembre de 2026.
Son casos de una pieza, no un benchmark ni objetivos universales:

| Caso | Dato observado | Lo que no demuestra |
|---|---|---|
| V20, muslo de 16.000 triángulos, misma geometría | Área UV de 0,025404 en atlas 4096 a 0,403026 en 2048: ganancia nominal lineal 1,99× | El usuario percibió poca mejora: más densidad no reparó los mecanismos fundidos |
| V21, reconstrucción del interior de un muslo | 20.730 triángulos; mecanismos más separados; las otras 15 piezas se compararon contra V20 | El usuario vio mejora pero no el lujo de detalle buscado; limpieza técnica no equivale a fidelidad ornamental |
| V21, UV del NIF final | Solape de huella 0,0014 %; 170 caras con área UV cero, correspondientes al 0,013 % del área 3D | El atlas no está libre de defectos; esos porcentajes no son umbrales de aceptación para otros modelos |
| V21, reimportación | Error UV máximo observado 0,00024414 | No convierte esa tolerancia en regla para cualquier formato, escala o exportador |

Proveniencia: reportes locales `02_uv.json` (V20),
`04_validacion_nif.json`, `05_reimportacion.json` y
`06_skill_uv_y_mascara.json` (V21), y devolución del usuario. Los archivos de
producción y las capturas de juego no se distribuyen aquí; estos datos no
pueden regenerarse solo con este repo. El fallo de limpieza, en cambio, sí
se reproduce sin esos assets mediante la prueba sintética de la trampa 40.

La conversión BC7 también se verificó localmente decodificando el DDS y
comparándolo con el PNG previo; no basta la cabecera. Esto complementa la
receta de color/gamma de la trampa 35. El conversor de este repo sigue siendo
DXT1/DXT5: esta contribución no incorpora un codificador BC7.
