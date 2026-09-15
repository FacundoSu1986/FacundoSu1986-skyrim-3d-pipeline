# skyrim-3d-pipeline

Herramientas para llevar modelos 3D generados por IA (Tripo, Meshy, Hunyuan3D,
Rodin, Trellis) a assets funcionales de **Skyrim Special Edition**: malla, rig,
texturas y un NIF verificado.

El contenido principal es la skill [`modelo-ia-a-skyrim`](skills/modelo-ia-a-skyrim),
pensada para Claude Code pero legible como documentación técnica por sí sola.

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

Por eso la parte más valiosa de este repo no es el pipeline: es la lista de
**23 fallos silenciosos** con su síntoma y su arreglo, y la disciplina de
verificación que los atrapa.

## Contenido

| Ruta | Qué es |
|---|---|
| [`SKILL.md`](skills/modelo-ia-a-skyrim/SKILL.md) | El flujo completo y la disciplina de verificación |
| [`references/pedir-a-la-ia-3d.md`](skills/modelo-ia-a-skyrim/references/pedir-a-la-ia-3d.md) | Cómo escribir el pedido al generador: plantillas, negative prompts, cómo expresar proporciones |
| [`references/limites-skyrim.md`](skills/modelo-ia-a-skyrim/references/limites-skyrim.md) | Límites del motor: presupuestos de polígonos medidos, formatos de textura, estructura del NIF, rig y particiones |
| [`references/trampas.md`](skills/modelo-ia-a-skyrim/references/trampas.md) | 23 fallos que no tiran error, con índice por síntoma |
| [`scripts/censo_nif.py`](skills/modelo-ia-a-skyrim/scripts/censo_nif.py) | Parser NIF en Python puro, con suite de falsificación |
| [`scripts/nif_nodos.py`](skills/modelo-ia-a-skyrim/scripts/nif_nodos.py) | Jerarquía de nodos y posiciones de hueso reales |
| [`scripts/medir_parte.py`](skills/modelo-ia-a-skyrim/scripts/medir_parte.py) | Mide un GLB/FBX/OBJ recién generado |
| [`scripts/preparar_parte.py`](skills/modelo-ia-a-skyrim/scripts/preparar_parte.py) | Soldar, decimar, orientar |

Y aparte, en [`census/`](census), las herramientas que producen los números:

| Ruta | Qué es |
|---|---|
| [`census/parser_nif.py`](census/parser_nif.py) | Parser NIF completo: geometría, particiones, huesos, pesos, shaders, colisión Havok |
| [`census/verificar.py`](census/verificar.py) | Auditoría estructural bloque por bloque |
| [`census/agregados.py`](census/agregados.py) | Las consultas del censo |
| [`census/hallazgos.md`](census/hallazgos.md) | 15 hallazgos medidos, con consulta y N cada uno |

## Uso

**Como skill de Claude Code.** Copiá `skills/modelo-ia-a-skyrim/` a tu carpeta
de skills, o empaquetala:

```bash
python build_skill.py
```

**Como scripts sueltos.** Los de `scripts/` que empiezan con `nif_` no necesitan
nada más que Python 3. Los que tocan geometría corren dentro de Blender:

```bash
blender -b --python skills/modelo-ia-a-skyrim/scripts/medir_parte.py -- modelo.glb
```

**Como documentación.** Los tres archivos de `references/` se leen solos.

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

## Sobre los números

Los presupuestos de polígonos, las distribuciones de flags de partición, los
formatos de textura y los límites de vértices **están medidos**, no estimados:
salen de un censo de las 22.394 mallas del juego base.

El censo en sí **no está en este repo** y no puede estarlo: se construye sobre
assets extraídos de Skyrim, que son propiedad de Bethesda. Lo que sí está son
las **herramientas para regenerarlo** desde tu propia copia legal del juego —
ver [`census/README.md`](census/README.md).

El parser está validado contra una segunda implementación escrita por separado:
400 archivos al azar, 400/400 de coincidencia. Y ningún campo entra al censo sin
un caso en la suite de falsificación, por un motivo concreto que está contado
ahí.

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

## Licencia

MIT. Ver [LICENSE](LICENSE).
