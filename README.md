# skyrim-3d-pipeline

Herramientas para llevar modelos 3D generados por IA (Tripo, Meshy, Hunyuan3D,
Rodin, Trellis) a assets funcionales de **Skyrim Special Edition**: malla, rig,
texturas y un NIF verificado.

El contenido principal son dos skills, pensadas para Claude Code pero legibles
como documentación técnica por sí solas:

- [`modelo-ia-a-skyrim`](skills/modelo-ia-a-skyrim): del modelo generado por
  la IA al asset en el juego (malla, rig, texturas, horneado HD, NIF).
- [`asset-nuevo-skyrim`](skills/asset-nuevo-skyrim): un item **nuevo** y
  equipable, hasta el plugin que lo registra.

---

## Qué problema resuelve

Los generadores de 3D por IA producen **mallas de escultura**, no assets de
juego: cientos de miles de triángulos, vértices partidos por isla de UV, sin
rig, a veces orientadas al revés, y sin ninguna noción de las restricciones del
motor.

Cerrar esa brecha es mecánico. Lo difícil es otra cosa: **casi nada de lo que
sale mal tira un error.** El asset se exporta "bien", se instala "bien", y el
problema aparece recién mirando el archivo generado o probando en el juego —
brazos invisibles, la criatura peleando de espaldas, texturas superpuestas, una
articulación perdida que nadie nota hasta que camina.

Por eso la parte más valiosa de este repo no es el pipeline: son las listas de
**fallos silenciosos** —40 en `modelo-ia-a-skyrim` y 24 en
`asset-nuevo-skyrim`— con su síntoma y su arreglo, y la disciplina de
verificación que los atrapa.

## Contenido

La skill [`modelo-ia-a-skyrim`](skills/modelo-ia-a-skyrim):

| Ruta | Qué es |
|---|---|
| [`SKILL.md`](skills/modelo-ia-a-skyrim/SKILL.md) | El flujo completo y la disciplina de verificación |
| [`references/pedir-a-la-ia-3d.md`](skills/modelo-ia-a-skyrim/references/pedir-a-la-ia-3d.md) | Cómo escribir el pedido al generador: plantillas, negative prompts, cómo expresar proporciones |
| [`references/limites-skyrim.md`](skills/modelo-ia-a-skyrim/references/limites-skyrim.md) | Límites del motor: presupuestos de polígonos medidos, formatos de textura, estructura del NIF, rig y particiones |
| [`references/trampas.md`](skills/modelo-ia-a-skyrim/references/trampas.md) | 40 fallos que no tiran error, con índice por síntoma |
| [`references/verificar-el-archivo.md`](skills/modelo-ia-a-skyrim/references/verificar-el-archivo.md) | Qué cubre cada control del NIF reimportado y qué no, con la evidencia |
| [`references/hd-texturas.md`](skills/modelo-ia-a-skyrim/references/hd-texturas.md) | La capa HD: hornear la malla alta de la IA sobre la baja de juego, en orden y con controles |
| [`references/acabado-y-validacion.md`](skills/modelo-ia-a-skyrim/references/acabado-y-validacion.md) | Conservar el atlas hasta el NIF y evaluar detalle real frente a resolución; lecciones del centurión V20/V21 |
| [`references/pbr-community-shaders.md`](skills/modelo-ia-a-skyrim/references/pbr-community-shaders.md) | El True PBR de Community Shaders `[PROVIDER]`: flags del NIF, ranuras y el `_rmaos`, desde su código fuente |
| [`scripts/censo_nif.py`](skills/modelo-ia-a-skyrim/scripts/censo_nif.py) | Parser NIF en Python puro, con suite de falsificación |
| [`scripts/nif_nodos.py`](skills/modelo-ia-a-skyrim/scripts/nif_nodos.py) | Jerarquía de nodos y posiciones de hueso reales |
| [`scripts/medir_parte.py`](skills/modelo-ia-a-skyrim/scripts/medir_parte.py) | Mide un GLB/FBX/OBJ recién generado (Blender) |
| [`scripts/preparar_parte.py`](skills/modelo-ia-a-skyrim/scripts/preparar_parte.py) | Soldar, decimar, orientar; guarda la malla alta para el bake (Blender) |
| [`scripts/render_referencia.py`](skills/modelo-ia-a-skyrim/scripts/render_referencia.py) | Renders de referencia de un asset vanilla para ControlNet (Blender) |
| [`scripts/salud_malla.py`](skills/modelo-ia-a-skyrim/scripts/salud_malla.py) | Si la malla se rompió al decimarla: aristas de borde, sobre el archivo |
| [`scripts/desplegar_uv.py`](skills/modelo-ia-a-skyrim/scripts/desplegar_uv.py) | Despliega las UV de la baja en un solo atlas para hornear, y no guarda si el empaquetado no se movió o las islas se pisan (Blender) |
| [`scripts/hornear.py`](skills/modelo-ia-a-skyrim/scripts/hornear.py) | Hornea normal, AO, albedo, rugosidad y metal desde la malla alta (Blender) |
| [`scripts/horneado_puro.py`](skills/modelo-ia-a-skyrim/scripts/horneado_puro.py) | Lo del horneado que no necesita Blender: reducción, margen, solape de UV |
| [`scripts/uv_exportacion.py`](skills/modelo-ia-a-skyrim/scripts/uv_exportacion.py) | Conserva una UV por nombre y comprueba sus coordenadas al limpiar una copia de exportación (API de Blender) |
| [`scripts/montar.py`](skills/modelo-ia-a-skyrim/scripts/montar.py) | Pasos 5 y 6: monta las partes en el lugar de las piezas vanilla y copia sus pesos (Blender) |
| [`scripts/montaje_puro.py`](skills/modelo-ia-a-skyrim/scripts/montaje_puro.py) | Lo del montaje que no necesita Blender: transformadas, pesos, controles, el plan |
| [`scripts/correr_en_blender.py`](skills/modelo-ia-a-skyrim/scripts/correr_en_blender.py) | Que un script de Blender que revienta no salga con 0 |
| [`scripts/verificar_uv.py`](skills/modelo-ia-a-skyrim/scripts/verificar_uv.py) | Que el NIF guarde la V invertida respecto del OBJ |
| [`scripts/verificar_export.py`](skills/modelo-ia-a-skyrim/scripts/verificar_export.py) | El NIF exportado contra el vanilla: bloques, nodos, piezas, huesos |
| [`scripts/proporciones_arma.py`](skills/modelo-ia-a-skyrim/scripts/proporciones_arma.py) | Las proporciones de un arma contra las de su clase |
| [`scripts/material_arma.py`](skills/modelo-ia-a-skyrim/scripts/material_arma.py) | El material de un arma contra el de las armas vanilla, o el del True PBR |
| [`scripts/mascara_especular.py`](skills/modelo-ia-a-skyrim/scripts/mascara_especular.py) | El alfa del `_n`: cuánto de la máscara especular está saturado |

La skill [`asset-nuevo-skyrim`](skills/asset-nuevo-skyrim):

| Ruta | Qué es |
|---|---|
| [`SKILL.md`](skills/asset-nuevo-skyrim/SKILL.md) | Del modelo al item equipable y registrado en un plugin |
| [`references/nodo-de-anclaje.md`](skills/asset-nuevo-skyrim/references/nodo-de-anclaje.md) | El nodo del que cuelga el item y su giro |
| [`references/plugin-armo-arma.md`](skills/asset-nuevo-skyrim/references/plugin-armo-arma.md) | Los registros ARMO/ARMA de una armadura o un escudo |
| [`references/plugin-weap.md`](skills/asset-nuevo-skyrim/references/plugin-weap.md) | Los registros WEAP y STAT de un arma |
| [`references/trampas.md`](skills/asset-nuevo-skyrim/references/trampas.md) | 24 fallos que no tiran error |
| [`scripts/colision_caja.py`](skills/asset-nuevo-skyrim/scripts/colision_caja.py) | Las cajas de colisión de un NIF, contra lo que hace el corpus vanilla |
| [`scripts/esl.py`](skills/asset-nuevo-skyrim/scripts/esl.py) | Marca (o desmarca) un plugin como ESL, comprobando antes si puede |
| [`scripts/nif_nodos.py`](skills/asset-nuevo-skyrim/scripts/nif_nodos.py) | La misma jerarquía de nodos (copia idéntica a la de la otra skill) |
| [`scripts/exportar_nif.py`](skills/asset-nuevo-skyrim/scripts/exportar_nif.py) | El NIF de un asset nuevo con la estructura de un donante vanilla de la clase y la receta de shader de cada pieza; lo relee antes de dejarlo (Blender) |
| [`scripts/exportar_puro.py`](skills/asset-nuevo-skyrim/scripts/exportar_puro.py) | Lo de ese export que no necesita Blender: plan, soldadura, caja, inercia, flags, texturas |
| [`scripts/correr_en_blender.py`](skills/asset-nuevo-skyrim/scripts/correr_en_blender.py) | El mismo de `modelo-ia-a-skyrim`: un script de Blender que revienta no sale con 0 |
| [`scripts/verificar_plugin.py`](skills/asset-nuevo-skyrim/scripts/verificar_plugin.py) | El plugin terminado: formVersion, índices, WEAP, Prn |

Y aparte, en [`census/`](census), las herramientas que producen los números:

| Ruta | Qué es |
|---|---|
| [`census/parser_nif.py`](census/parser_nif.py) | Parser NIF completo: geometría, particiones, huesos, pesos, shaders, colisión Havok |
| [`census/verificar.py`](census/verificar.py) | Auditoría estructural bloque por bloque |
| [`census/agregados.py`](census/agregados.py) | Las consultas del censo |
| [`census/escritor_dds.py`](census/escritor_dds.py) | Escribe DDS con mipmaps: sin comprimir, DXT1 o DXT5, con la cabecera de los vanilla |
| [`census/compresor_dxt.py`](census/compresor_dxt.py) | Comprime y decodifica DXT1/DXT5 (numpy); verificado contra Pillow y contra el corpus |
| [`census/hallazgos.md`](census/hallazgos.md) | 43 hallazgos medidos sobre las mallas, con consulta y N cada uno |
| [`census/hallazgos_plugins.md`](census/hallazgos_plugins.md) | 18 hallazgos sobre los plugins |
| [`census/hallazgos_texturas.md`](census/hallazgos_texturas.md) | 10 hallazgos sobre las texturas |
| [`census/hallazgos_uv.md`](census/hallazgos_uv.md) | 6 hallazgos sobre las UV |

Y en [`pipeline/`](pipeline), el execution framework que orquesta todo eso:

| Ruta | Qué es |
|---|---|
| [`pipeline/runner.py`](pipeline/runner.py) | Máquina de estados explícita, 9 fases en orden, y el gate que impide publicar si alguna fase quedó sin conectar |
| [`pipeline/manifest.py`](pipeline/manifest.py) | Config declarativa e inmutable del job, validada antes de crear un solo directorio |
| [`pipeline/texturas.py`](pipeline/texturas.py) | La fase PROCESS_TEXTURES: PBR del generador → DDS con la convención de Skyrim |
| [`pipeline/staging.py`](pipeline/staging.py) | Workspace aislado por job, fail-closed ante reintentos |

## Uso

**Como skill de Claude Code.** Copiá `skills/modelo-ia-a-skyrim/` (o
`skills/asset-nuevo-skyrim/`) a tu carpeta de skills, o empaquetalas. Sin
argumentos, `build_skill.py` empaqueta cada carpeta de `skills/` que tenga un
`SKILL.md`:

```bash
python build_skill.py
```

**Como scripts sueltos.** Los que leen archivos (NIF, DDS, plugins) no
necesitan nada más que Python 3. La compresión DXT y el bake HD necesitan
numpy (`requirements.txt`); para correr la suite, `requirements-dev.txt`, que
agrega Pillow como oráculo de los tests y es lo que instala el CI. Los que
marcan "Blender" en la tabla corren dentro de Blender, que trae su propio
numpy:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
blender -b --python skills/modelo-ia-a-skyrim/scripts/medir_parte.py -- modelo.glb
```

**Como documentación.** Los archivos de `references/` se leen solos.

## Cómo leer las afirmaciones

Cada afirmación fuerte va etiquetada, porque confundir estas tres categorías es
de donde vino casi todo el daño:

| Etiqueta | Qué es | Vida útil |
|---|---|---|
| `[INVARIANT]` | Propiedad del formato NIF o del motor | permanente |
| `[PROVIDER]` | Cómo se comporta hoy un generador o PyNifly | caduca rápido |
| `[OBSERVED]` | Algo medido en un corpus concreto | un caso, no una ley |

El error caro es promover un `[OBSERVED]` a `[INVARIANT]`. Varias afirmaciones
de las versiones anteriores de estos documentos eran exactamente eso, y están
documentadas como tales dentro de los propios archivos en vez de borradas — el
patrón enseña más que el dato.

Qué comprueba cada control, con qué número del corpus, qué test se pone rojo si
se rompe y si lo corre el CI: [`docs/validacion.md`](docs/validacion.md).

## Sobre los números

Los presupuestos de polígonos, las distribuciones de flags de partición, los
formatos de textura y los límites de vértices **están medidos**, no estimados:
salen de un censo de las 22.394 mallas del juego instalado (abajo, de qué
edición).

El censo en sí **no está en este repo** y no puede estarlo: se construye sobre
assets extraídos de Skyrim, que son propiedad de Bethesda. Lo que sí está son
las **herramientas para regenerarlo** desde tu propia copia legal del juego —
ver [`census/README.md`](census/README.md).

El parser está validado contra una segunda implementación escrita por separado:
400 archivos al azar, 400/400 de coincidencia. Y ningún campo entra al censo sin
un caso en la suite de falsificación, por un motivo concreto que está contado
ahí.

**De qué edición.** Todo se midió sobre Skyrim SE en la versión 1.6.1170, con
los diez plugins de una instalación sin contenido pago: `Skyrim.esm`,
`Update.esm`, las tres expansiones, `_ResourcePack.esl` y los cuatro de
Creation Club que vienen con el juego (pesca, Saints & Seducers, Rare Curios y
supervivencia). Sus mallas están en el corpus: las expansiones y un arma de
Creation Club entran en las cuentas. Si tenés otra:

- **Anniversary Edition**: es esta misma versión del juego más contenido pago
  de Creation Club. Ese contenido no está en el corpus; lo demás vale igual.
- **LE (la de 2011)**: no está soportada; el proyecto apunta solo a SE. Su
  NIF es otro formato (`bs_version` 83 con `NiTriShape`), y lo único que
  queda de LE es no exportarlo por accidente (trampa 33 de
  `modelo-ia-a-skyrim`).
- **GOG**: no se midió.

## Qué NO hay acá

- **Ningún asset de Bethesda.** Ni mallas, ni texturas, ni archivos extraídos de
  BSA. El `.gitignore` está escrito para que no entren por accidente.
- **Ningún binario de terceros** (BAE, NifSkope, Qt).
- **`nif.xml`** — la especificación legible por máquina del formato NIF es de
  [NifTools](https://github.com/niftools/nifskope) y tiene su propia licencia.
  Descargala de ahí.

## Estado

La skill se usó para construir un replacer del Dwarven Steam Centurion que
**funciona en el juego**: 20 huesos con desvío 0,0 contra el esqueleto vanilla,
animaciones sin deformación, particiones válidas.

El resultado estético no fue satisfactorio y el proyecto se abandonó. Esa parte
también está documentada: varias de las trampas de `references/trampas.md`
salieron de ahí, y `SKILL.md` es explícito sobre qué verifica el pipeline y qué
no. Un asset puede pasar todos los chequeos y ser feo — ninguna métrica acá
mide eso.

Después se usó para dos assets **nuevos** generados con IA, y los dos se
vieron en el juego:

- **Un hacha a dos manos** clonada de `DaedricBattleaxe`, con
  `asset-nuevo-skyrim` para el plugin (`references/plugin-weap.md`). Cada
  vuelta que salió mal en el juego dejó algo en el repo: la textura espejada
  (trampa 29), la máscara especular en blanco que la volvía plástico
  (`mascara_especular.py`), el material `Default` de PyNifly (trampa 36), el
  mango que hubo que afinar (trampa 34) y, del lado del plugin, el peso y el
  daño en 0 (trampa 23 de `asset-nuevo-skyrim`).
- **Un escudo ovalado dwemer** de Tripo, de 2 M a 12.000 triángulos, con la
  capa HD horneada a 2048 y comprimida a DXT: el camino entero de
  `references/hd-texturas.md`. Visto una vez: "quedó casi igual" a su imagen
  de referencia.

Ninguno de los dos pasó por `montar.py`: son assets nuevos, no replacers.
Ningún asset armado con `montar.py` se vio todavía en el juego.

**Del execution framework, qué está conectado y qué no.** De las 9 fases del
runner, INGEST, INSPECT, PROCESS_TEXTURES y PUBLISH hacen trabajo real;
PREPARE, EXPORT_NIF, READ_BACK, VALIDATE y PACKAGE siguen siendo stubs que se
declaran como tales. El gate impide publicar con cualquiera de ellas sin
conectar, así que una corrida hoy **no puede** terminar en PUBLISHED: es el
estado honesto de un pipeline a medias, no un bug.

`PROCESS_TEXTURES` convierte PNG/TGA/DDS sin comprimir a DDS con mipmaps
--sin comprimir de 32 bpp por defecto, o con `compresion="dxt"` el `_n` y lo
que tenga alfa en DXT5 y el resto en DXT1--, derivando el alfa del `_n` desde
la rugosidad (`255 − roughness`, una heurística) y la máscara `_m` desde la
metalicidad con el rango expandido. Reconoce los nombres de glTF, Substance, Poly Haven y Tripo, y
rechaza los que traen un rol que no conoce en vez de tomarlos por color. Lo que
**no** hace, y por qué, está escrito en el docstring de `pipeline/texturas.py`:
no comprime si no se lo piden, no escribe BC7 (el corpus no tiene ninguno y
`mascara_especular.py` no lo lee), no saca la luz horneada del albedo (se atenúa con curvas, no se recupera), no toca el
NIF y no puede comprobar que la malla conserve las UV del generador (lo deja
escrito como precondición). Cada DDS que escribe se verifica con
`fixtures/comparar.py`, y la máscara del `_n` se mide con
`scripts/mascara_especular.py` y pide revisión si queda fuera de lo que usa el
vanilla.

Con `sombreado="cs_pbr"` en el manifest, la misma fase escribe para el True PBR
de Community Shaders: en vez de la `_m` arma un `_rmaos` (rugosidad, metal,
oclusión), usa la altura como `_p`, y deja en `texture_set.json` las ranuras y
los valores que el NIF tiene que llevar. Las convenciones salen del código
fuente de Community Shaders, fijado a un commit; ver
`references/pbr-community-shaders.md`.

## Licencia

MIT. Ver [LICENSE](LICENSE).
