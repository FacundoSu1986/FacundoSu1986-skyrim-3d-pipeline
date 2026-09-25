# Capa HD: texturas horneadas desde la malla de la IA

La capa HD va **encima** de la integridad de los pasos 1–8 y no la reemplaza:
si un gate de integridad falla, subir de resolución no lo arregla.

La idea central: la IA ya entrega una **escultura**. El paso 4 la decima al
presupuesto y tira el detalle. Si se guarda la versión soldada **sin decimar**,
ese detalle vuelve a la baja por el bake, como normal map. ZBrush sirve para
limpiar o agregar detalle a esa malla alta: es opcional y no forma parte del
camino.

Lo que dice "medido" en esta página se midió con Blender 4.5.14 LTS (el `bpy`
de pip), sobre un asset sintético: una esfera con relieve, un albedo con una
franja de sombra pintada y un ORM con zonas. Después se repitió el camino
entero con **Blender 4.4.1**, el que documenta el repo: `.glb` →
`preparar_parte --guardar-alto` → UV → `hornear.py` a 512 (4 s) → fase de
texturas, que armó un solo texture set con el alfa del `_n` desde la
rugosidad y el `_m` desde el metal, sin pedir revisión. **No** se probó
todavía con un asset real de un generador ni dentro del juego.

## El orden

```
4.  preparar_parte.py ... --guardar-alto partes/X_alto.blend
    salud_malla.py antes despues
    Todo lo que AGREGA CARAS o DEFORMA va aca, antes de las UV: Solidify si
    la medicion dijo cascara, afinar (trampa 34, a la alta tambien).
4b. UV de la baja, en Blender (trampa 32). Varias piezas que comparten
    textura: un solo atlas, con area proporcional al area 3D (trampa 17).
    salud_malla.py --uv antes despues: la malla soldada tiene que ser la
    misma (cortar costuras parte vertices, y nada mas).
4c. hornear.py -- baja.blend texturas/ 2048 X_alto.blend [...]
    Aca la alta y la baja coinciden: salieron juntas de preparar_parte, y lo
    que deformo la baja en el paso 4 (afinar) se le aplico tambien a la alta.
    El Solidify no se repite en la alta: el control de alineacion saltea el
    eje delgado de una baja solidificada. Lo que si pasa es que la cara de
    atras y el canto de la baja no tienen alta enfrente: cuentan como
    fallidos (medido con Blender 4.4.1: 55,8 % en una chapa de 30 x 10
    solidificada a 1,0) y los llena el margen. El aviso es esperable ahi.
5.  Montar: cortar, escalar, espejar. No toca las UV: la textura sigue
    valiendo y a la alta no hay que aplicarle nada.
6.  Riggear. Los pesos no tocan las UV.
7.  PNG -> DDS: `_n` = normal + mascara especular (desde la rugosidad),
    `_m` desde la metalicidad, color. Albedo: ver 7b.
8.  Exportar y verificar, sin cambios.
```

Por qué se hornea en 4c y no después del rig: en 4c la alta y la baja están en
el mismo lugar sin hacer nada. Después de montar hay que repetir sobre la alta,
a mano y sin verificación, todo lo que se le hizo a la baja (trampa 34).
Montar, en cambio, no cambia lo que la textura ve: cortar deja las UV como
estaban. Escalar parejo tampoco cambia el espacio tangente. Lo que **no** se
midió es el efecto de escalar distinto en cada eje, o de espejar, sobre el
normal ya horneado. `[no medido]`

La regla que ordena todo esto: **la malla de juego no sale de Blender.** Rehacer
las UV en Blender no rompe el rig (las UV no dependen de los grupos de vértices).
Lo que sí puede romperlo es el ida y vuelta por otra herramienta, que puede
reordenar o fusionar vértices.

## 4c. Hornear — `scripts/hornear.py`

```
blender -b --python scripts/hornear.py -- baja.blend texturas/ 2048 X_alto.blend [Y_alto.blend ...]
```

Salida, con el nombre del `.blend` de la baja como base:

| Archivo | Qué es |
|---|---|
| `<base>_albedo.png` | color, RGB sRGB |
| `<base>_normalgl.png` | normal tangente, verde +Y (trampa 30) |
| `<base>_roughness.png`, `<base>_metallic.png` | grises, sobre las UV **nuevas** |
| `<base>_ao.png` | gris |
| `<base>_horneado.json` | los controles |

Son los nombres de entrada de la fase de texturas del pipeline
(`pipeline/texturas.py`, PR #51): los nombres `_normalgl`, `_metallic` y
`_ao`, y la lectura del DDS sin comprimir en `mascara_especular.py`, llegaron
con ese PR. Esa fase arma el alfa
del `_n` como `255 - rugosidad` y el `_m` desde la metalicidad. Sin la rugosidad y la metalicidad horneadas sobre las UV nuevas,
nadie producía la máscara especular ni el `_m` después de re-desplegar.
Medido corriendo esa fase sobre esta salida: `_n` con 0,04 % de bloques
saturados, sin pedir revisión.

Qué hace, y por qué, medido:

- **Varias piezas, un atlas.** La baja `X` se empareja con la alta `X_alto`,
  que es el nombre que deja `--guardar-alto`. Las bajas se unen en memoria y
  se hornean de una sola vez, desde todas las altas. El `.blend` no se guarda.
- **Alineación antes de hornear.** Si la caja de una alta no coincide con la
  de su baja (centro corrido más del 10 % de la diagonal, o un eje fuera de
  ×1,25), sale con error sin escribir nada. Los topes son criterio.
- **UV activa = UV de render**, o sale con error. No elige por vos.
- **Las islas no se pisan**, o sale con error antes de cargar la alta. En el
  juego pisar UV es normal: 8 de cada 9 mallas vanilla lo hacen
  (`census/hallazgos_uv.md`), y por eso el censo no lo trata como defecto. En
  un bake sí lo es: cada téxel recibe el color de **un** punto de la alta, y
  dos islas en el mismo lugar se hornean una encima de la otra (gana la
  última, trampa 32). El tope es 0,001 de la huella, el "nada de solape" del
  censo. `--permitir-solape` lo deja pasar si el apilado es a propósito, y el
  número queda en el reporte.
- **Nada que hornear es un error.** Sin téxeles cubiertos, o sin un solo rayo
  que encuentre la alta, sale antes de escribir los mapas. Antes escribía PNG
  de relleno neutro y terminaba bien: la fase de texturas los convertía en un
  texture set plano.
- **El normal incluye el bump o el normal map del material de la alta**, no
  solo la geometría. Medido: con fuerza 0 sale plano, con fuerza 1 la
  desviación del canal R es 0,42. Si el generador trae un normal map
  conectado al material (el importador glTF lo conecta), su detalle pasa.
- **Rayos limitados a 2 × extrusión.** Sin límite, un rayo que no encuentra la
  superficie cercana sigue hasta el **otro lado** de la alta y trae su color.
  Medido: puntos verdes dentro de islas rojas. Con límite, ese téxel cuenta
  como fallido y el control lo reporta.
- **Margen propio.** Con margen > 0, Blender pone alfa 1 en toda la imagen y
  el hueco del atlas queda en RGB 0. Una rugosidad 0 se vuelve especular al
  máximo en el `_n`: medido, 24,7 % de téxeles saturados. Por eso se hornea
  sin margen, el margen se hace en `horneado_puro.dilatar`, y lo que no
  alcanza toma un valor neutro: normal plano, rugosidad 1, metal 0, AO 1,
  albedo en su color medio.
- **PNG sin alfa.** El bake escribe alfa 1 en todo lo horneado. Un `_n`
  convertido con ese alfa sale todo especular (plástico). El alfa lo pone la
  conversión a DDS, desde la rugosidad.
- **AO con sus propias muestras** (32 por defecto; `--muestras-ao`). Normal y
  EMIT usan 1 muestra, que da un resultado determinístico.
- **Distancia del AO** relativa a la pieza (`--distancia-ao`, 0,1 de la
  diagonal mediana). Si no se fija, sale del World de la escena: 10
  unidades, mida el asset 1 o 100, y una escena sin World da AO blanco sin
  error. La baja **no** tapa rayos del AO. Medido: un cubo de la baja encima
  de la alta deja el AO en 1,0, y el mismo cubo en la alta lo baja a 0,83.
- **Extrusión** como fracción de la diagonal **mediana de las piezas**, no la
  del conjunto: con piezas separadas, la del conjunto da rayos que cruzan de
  una pieza a otra. Por defecto 0,01. Medido en la esfera con relieve: 1,6 %
  de fallidos con 0,01 y 0 % con 0,03.

Costo medido, en 4 núcleos, un asset de 1.000 triángulos bajos y 16.000 altos:

| Resolución final | Horneado a | Tiempo | Pico de memoria |
|---|---|---|---|
| 512 | 1024² | ~10 s | — |
| 2048 | 4096² | ~3 min | 4,7 GB |
| 4096 | 8192² | no corrido | ~4 × el de 2048 `[calculado]` |

El pico de memoria lo pone el bake de Cycles, no el Python que viene después.
A 4096 final son cuatro veces los píxeles: del orden de 19 GB `[calculado]`,
fuera del alcance de una máquina de 16 GB. Para lo que no es arquitectura
principal, 2048 alcanza (ver la tabla de resolución).

## Los controles: `<base>_horneado.json`

| Control | Qué mide | Aviso |
|---|---|---|
| `solape_uv` | fracción de la huella UV pisada por 2+ triángulos | > 0,001 es error, salvo `--permitir-solape` |
| `cobertura` | fracción del atlas ocupada por islas | 0 es error; si no, se informa el tamaño equivalente lleno |
| `fallidos` | fracción de téxeles de isla donde el rayo no encontró la alta | > 1 % |
| `densidad_texel` | téxeles por unidad de cada pieza | max/min > 2 |
| `albedo_media_cubierta` | luminancia media, **solo** sobre téxeles cubiertos | < 0,02 (trampa 31) |
| `correlacion_albedo_ao` | Pearson entre la luminancia del albedo y el AO, sobre lo cubierto | > 0,5 |

La cobertura se validó contra el área UV de la malla: 24,1 % medido contra
24,09 % calculado. Los umbrales de aviso son criterio `[no medido]`. Los
números, y la lista de avisos (`avisos`), se guardan siempre en el JSON para
poder auditarlos; también `materiales_sin_principled` y `materiales_ambiguos`.
El Principled que se hornea es el que **llega a la salida** del material, no
el primero del árbol.

La correlación con el AO es **evidencia**, no prueba, de luz horneada. Detecta
la sombra que cae donde hay oclusión: huecos y contactos. No detecta una sombra
direccional pintada donde no hay oclusión. Medido: la franja de sombra pintada
del asset de prueba dio r = 0,03. Y la suciedad pintada a propósito en los
huecos también correlaciona.

## 7b. Albedo

El generador texturiza desde imágenes iluminadas: el albedo trae sombras que el
juego vuelve a aplicar (trampa 21). Si el generador ofrece salida PBR o
"delight", pedila. Si no, atenuá el rango bajo con una curva y bajá la
saturación de las zonas oscuras. No se recupera del todo, y **no hay camino
automático**: el control de correlación avisa, pero no corrige.

El AO horneado se puede multiplicar suave sobre el albedo, para que las
concavidades tengan contacto. Cuánto, se juzga en el juego. `[no medido]`

Si no hay recortes (pelo, rejas), no hace falta alfa: DXT1. Con alfa, DXT5.

## 7. `_n` y máscara especular

- En el `_n`, RGB es el normal en espacio tangente y el **alfa es la máscara
  especular**. Tiene que ir en un formato con alfa: DXT5 o BC7. DXT1 no tiene
  alfa, así que la máscara desaparece.
- **DXT5 o BC7.** `limites-skyrim.md` recomienda BC7 lineal para normales de
  contenido nuevo en SE. El corpus vanilla usa DXT5 en el 100 % de sus 12.075
  `_n` y no tiene ningún BC7. Las dos opciones sirven.
- **La máscara se mide sobre lo que se entrega.** `mascara_especular.py` lee
  el alfa de un DXT5 y de un sin comprimir de 32 bpp, no el de un BC7: es un
  límite de la herramienta, no del formato. La fase de texturas del pipeline
  escribe DXT con `compresion="dxt"` (`census/compresor_dxt.py`): el `_n` en
  DXT5, los mapas opacos en DXT1, y mide la máscara sobre el DXT5 escrito.
  Medido sobre esta capa: la máscara da lo mismo antes y después de comprimir
  (0 % de bloques en blanco; media 92,4 contra 92,6). Si elegís BC7, medila
  antes, sobre el sin comprimir, y comprimí después.
- Máscara gris, no blanca. En armas: `mascara_especular.py --arma` (como mucho
  10 % de bloques en blanco; las armas del corpus están por debajo del 6,9 %).
- Mipmaps siempre. Potencia de 2 siempre: 0 excepciones en 32.241 texturas.

## Resolución

Las medianas del corpus son el **piso**, no la meta HD. Describen lo que
Bethesda comprimió para LE: `actors` 512, `clutter` 512, `architecture` 1024,
`armor` 1024, y solo el 0,18 % llega a 4096 (`census/hallazgos_texturas.md`,
hallazgo 8).

| Clase | Vanilla (mediana) | Objetivo HD | Techo |
|---|---|---|---|
| clutter, armas chicas | 512 | 1024 | 2048 |
| armadura, armas grandes | 1024 | 2048 | 2048 |
| arquitectura principal | 1024 | 2048 | 4096 |

La columna HD es criterio, **sin relevar**: no se midió qué resoluciones usan
los mods HD publicados. `[PROVIDER, no medido]` La cobertura del atlas pesa
tanto como la resolución: un 2048 con 25 % de cobertura rinde como un 1024
lleno (lo informa `hornear.py`).

## Replacer: ruta vanilla

Si reusás la ruta de textura vanilla, el DDS nuevo reemplaza la textura en
**toda** malla que la use, no solo en la tuya. Antes de reusarla, fijate si es
compartida. Si lo es, usá una ruta propia y cambiala en el NIF.

## Qué no hacer

- Subir triángulos sin identificar qué detalle falta. Un grabado superficial
  puede ir en el `_n`; una silueta, un hueco o piezas separadas necesitan
  geometría. Ver [acabado-y-validacion.md](acabado-y-validacion.md).
- Pasar la malla de juego por ZBrush.
- Poner el metal o la rugosidad del generador **tal cual** en `_n` o `_m`: el
  shader vanilla no es PBR. Se **convierten** (rugosidad → alfa del `_n`,
  metal → `_m`).
- Invertir el verde "porque es DirectX" sin un render de control (trampa 30).
- Hornear con margen de Blender y después buscar el hueco por el alfa.

## Gates

Por asset, en este orden:

1. `salud_malla.py antes despues` después de 4, y `salud_malla.py --uv`
   después de 4b.
2. `hornear.py`: sin error de alineación ni de UV, y sin avisos en
   `<base>_horneado.json`, o con los avisos entendidos.
3. `census/parser_uv.py` sobre el NIF escrito: que el solape siga como lo
   dejó el bake (lo mide `hornear.py` antes de hornear; acá se comprueba que
   el export no lo cambió, trampa 32). El mismo solape no prueba que sea el
   mismo mapeo: comparar también las coordenadas con la copia de exportación
   (trampa 40 y [acabado-y-validacion.md](acabado-y-validacion.md)).
4. `mascara_especular.py [--arma]` sobre el `_n` que se entrega: DXT5 o sin
   comprimir. Un BC7 no se puede medir; medí el sin comprimir antes.
5. `verificar_export.py nuevo.nif vanilla.nif`, que también compara rutas de
   textura.
6. Render con luz rasante y sin albedo: el relieve tiene que salir hacia
   afuera, no hundirse.
7. En el juego: que no parezca plástico y que las sombras no queden fijas al
   girar.

El CI cubre `horneado_puro.py` (autotest: la reducción, el margen, el
relleno, el PNG, la alineación, el solape de UV, el Principled conectado y
las estadísticas). El margen, el relleno y la reducción con numpy --lo que
usa el bake real-- necesitan numpy: el CI lo instala, y
`tests/test_horneado_puro.py` falla si en CI faltara. Sin numpy el autotest
dice cuáles salteó en vez de dar un "OK" pelado. `hornear.py` necesita
Blender y no corre en CI. Los puntos 6 y 7 son manuales.

## Qué sigue abierto

- **Asset real: probado una vez.** El escudo ovalado de Tripo (2 M tris,
  tres texturas 4K) hizo el camino entero: `medir_parte` → `preparar_parte`
  (12.000 tris, 35 s) → UV (cobertura 0,411, trampa 17) → `hornear.py` a 2048
  (1 min 21 s, 0,03 % de fallidos, sin avisos) → fase de texturas con
  `compresion="dxt"` (máscara especular 0,009 % en blanco, sin revisión) →
  NIF que pasa `verificar_export` contra la versión anterior del escudo. Lo
  que encontró está en las trampas 7 y 17.
- **Juego: visto una vez.** Ese escudo se instaló en Skyrim SE el 2026-09-24
  y quien lo probó lo comparó con su imagen de referencia: "quedó casi
  igual", con "algún pequeño detalle fino" que no especificó. Eso dice que el
  juego carga el NIF y las texturas DXT1/DXT5 que salen de este camino, y que
  el resultado se parece a la referencia: una vez, con un asset mayormente
  metálico, a la luz en que se miró. No aísla la máscara especular, no se
  comparó contra un escudo vanilla en la misma escena y no se midió nada en el
  juego.
- **Luz horneada.** No hay corrección automática del albedo, solo el aviso.
- **BC7.** El repo comprime a DXT1/DXT5, no a BC7. El corpus corta los
  mipmaps en 2×2 (el 96,4 %); el escritor baja hasta 1×1, como 109 vanilla.
- **Atlas no cuadrados.** `hornear.py` solo hornea cuadrados. Vanilla también
  tiene rectangulares.
- **Mods HD.** Falta relevar qué resoluciones usan los mods HD publicados.

## Rama opcional: True PBR de Community Shaders

`[PROVIDER]` Usa los mismos mapas horneados, pero con otro destino: la fase de
texturas con `sombreado="cs_pbr"` arma un `_rmaos` (rugosidad, metal y la
oclusión que acá se ignora) en vez de la `_m`, y el NIF lleva otra flag y
otros valores. No se mezcla con el `_n` vanilla en la misma pieza. Todo en
`references/pbr-community-shaders.md`.
