# Censo del corpus vanilla

Herramientas para **medir** las mallas de Skyrim SE en vez de suponer cómo son.

Casi toda la documentación de modding de Skyrim —incluida la primera versión de
la que hay en este repo— está hecha de afirmaciones que alguien observó una vez
y escribió como si fueran ley del motor. `BSXFlags = 130` es el estándar. Las
partes en el mismo hueso comparten textura. `PF_START_NET_BONESET` va solo en la
primera partición.

Las tres son falsas, y las tres se refutan contando.

## Qué hay acá

| Archivo | Qué hace |
|---|---|
| `parser_nif.py` | Parser binario de NIF (BS version 100), Python puro, sin dependencias ni Blender. Solo lectura. |
| `verificar.py` | Auditoría estructural: comprueba que cada bloque leído termine exactamente en `offset + size` declarado por la cabecera. |
| `agregados.py` | Las consultas del censo, `a` a `j`. Cada una reproducible. |
| `generar_reporte.py` | Produce el reporte a partir del censo. |
| `hallazgos.md` | 43 hallazgos medidos sobre las mallas, en formato fijo. |
| `parser_dds.py` | Lee encabezados DDS. Su autotest predice el tamaño exacto de los 32.241 archivos del corpus. |
| `hallazgos_texturas.md` | 10 hallazgos medidos sobre las texturas. |
| `escritor_dds.py` | Escribe DDS con mipmaps: sin comprimir de 32 bpp, DXT1 o DXT5. Lo verifica `parser_dds.py`. |
| `compresor_dxt.py` | Comprime y decodifica DXT1/DXT5. Necesita numpy. Su `--censo` lo compara con Pillow sobre el corpus. |
| `parser_uv.py` | Extrae UV y triangulos del NIF y mide solape, densidad de texel e islas. Sin Blender. |
| `hallazgos_uv.md` | 6 hallazgos sobre UV, incluido uno que **refuta** la hipotesis que motivo el censo. |

## El censo no está en este repo

`censo.jsonl` (una línea por malla, ~54 MB) **no se versiona**, por dos motivos
independientes y cada uno suficiente:

1. Es un artefacto derivado y regenerable. Versionar datos generados de decenas
   de megabytes es mala práctica sin importar el contenido.
2. Se construye sobre assets extraídos de Skyrim, propiedad de Bethesda.

Para reproducirlo hace falta **tu propia copia legal del juego** y un extractor
de BSA (BAE, por ejemplo). Los números publicados en `hallazgos.md` y en
`../skills/modelo-ia-a-skyrim/references/limites-skyrim.md` son observaciones
factuales sobre esos archivos, no los archivos.

## Cómo reproducirlo

```bash
# 1. Extraé meshes/ de los BSA del juego a una carpeta limpia.
#    Que sea limpia importa: si hay copias del mismo nombre, el autotest aborta
#    en vez de elegir una al azar. Esa guarda existe porque en su momento
#    comparó contra el archivo equivocado sin avisar.

# 2. Validá el parser ANTES de censar nada.
python parser_nif.py --autotest meshes
#    -> 75 comprobaciones ok, 0 fallidas
#    Si dice otra cosa, resolvé eso primero. Un parser que corre no es un
#    parser que anda.

# 3. Auditoría estructural del corpus.
python verificar.py meshes --json verif_resumen.json

# 4. El censo.
python parser_nif.py --censo meshes --salida censo.jsonl

# 5. Las consultas.
python agregados.py            # todas
python agregados.py d e f      # solo algunas

# 6. Y lo mismo para las texturas.
python parser_dds.py --autotest textures
#    -> 32.241 con el tamano exacto que predice el encabezado
python parser_dds.py --censo textures --salida censo_dds.jsonl
#    y el compresor: decodificar igual que Pillow, recomprimir mejor que el
#    compresor de Pillow (necesita numpy y Pillow)
python compresor_dxt.py --censo textures --maximo 300
#    -> 300 de 300 iguales a Pillow; igual o mejor error en 297 de 300

# 7. Y las UV. --continuar reanuda si se corta: tarda una hora larga.
python parser_uv.py --autotest meshes
python parser_uv.py --censo meshes --salida censo_uv.jsonl --continuar
```

### La suite de falsificacion de DDS es mas fuerte que la de mallas

Con los NIF hubo que fijar valores esperados archivo por archivo. Con DDS el
formato impone una relacion:

    bytes = cabecera + suma( ceil(w/4) * ceil(h/4) * bytes_por_bloque )
                       * caras * profundidad

Si el parser leyo mal cualquier campo, la cuenta no da. Eso convierte cada
archivo del corpus en su propio caso de prueba, sin que nadie los escriba.

Encontro dos huecos reales del parser: los cubemaps guardan **6 caras** (59
archivos fallaban por un factor de 6 exacto) y existe **una** textura de
volumen que guarda una pila de slices. Los dos cerraron **al byte** despues de
corregir, no por aproximacion. Cuando una correccion cuadra exacto, es la
explicacion correcta; cuando cuadra "casi", es un parche.

## La disciplina

**Ningún campo entra al censo sin un caso en la suite de falsificación.** El
orden es: elegir un archivo donde ya sepas la respuesta, escribir el parser,
agregar el caso con el valor esperado, y recién entonces correr sobre el corpus.

La razón es concreta. Durante el desarrollo, un parser de `NiSkinPartition`
escrito de memoria devolvió enteros perfectamente formados que eran basura:
decía `pesos por vértice = 1035` cuando el máximo del motor es 4, porque leía
desde un offset corrido y ese 1035 era un pedazo del `vertexDesc` del bloque
anterior. **No tiró ninguna excepción.** Lo único que lo delató fue tener un
valor esperado de antemano y una cota de sanidad.

Sin eso, habría entrado basura bien formateada en 22.394 filas.

**Cada afirmación lleva su consulta y su N.** El formato de `hallazgos.md` es
fijo: `AFIRMACIÓN — CONSULTA QUE LA PRODUJO — N — EXCEPCIONES ENCONTRADAS`. Si
no hay excepciones, se dice explícitamente ("0 de 11.203"). Una afirmación sin
consulta detrás es una creencia con tipografía de dato.

## Un hallazgo que cambia cualquier censo

En SSE, un `BSTriShape` **skinneado no lleva la geometría adentro**:
`numTriangles = 0`, `dataSize = 0`. Vive en el `NiSkinPartition`. Los estáticos
sí la llevan inline.

Contar triángulos de la forma obvia devuelve **cero para toda criatura y toda
armadura** — justo las clases que más interesan — y no da ningún error.

## Validación independiente

El parser se cruzó contra una segunda implementación escrita por separado, sobre
400 archivos elegidos al azar: **400/400** coinciden en tipo de nodo raíz,
conteo de bloques por tipo, `BSXFlags`, BS version y user version.

Dos parsers independientes que concuerdan es evidencia. Un parser que pasa su
propia suite solo demuestra que reproduce los valores que le pusieron.
