# ¿Contribuye Smart Remesh al flujo de `modelo-ia-a-skyrim`?

Evaluación de un complemento de terceros contra el flujo de este repo. Pedida el
2026-09-26.

**Nada de acá se midió.** No hay una sola corrida del addon en este repo: todo
lo que el addon dice de sí mismo va `[PROVIDER]` y **sin verificar**, y lo que
este repo dice de su propio flujo va con la etiqueta que ya tiene. Este
documento no cambia `SKILL.md` ni ninguna referencia; decide dónde habría que
mirar y qué habría que medir antes de escribirlo.

## En una frase

**Sirve para que el asset sea más liviano, no para que se vea mejor.** No agrega
detalle ni mejora las texturas: agarra una malla pesada y la vuelve más prolija y
más liviana, con un número de polígonos que elegís vos. Y de todo lo que ofrece,
solo una parte te sirve: lo demás ya lo hace el repo, o es para otro tipo de
trabajo. Antes de comprarlo hay que probar una cosa sola (¿funciona sin abrir la
ventana de Blender?), y para probar la mitad principal hay una versión gratis que
ya viene con Blender.

## Qué es

| Dato | Valor | Fuente |
|---|---|---|
| Qué es | Addon de Blender: retopología/remesh, dos modos (Organic, Hardsurface) | página del vendedor |
| Versión | Smart Remesh 3 (las 1.x y 2.x quedan como historial) | página del vendedor |
| Precio / licencia | USD 17 · GPL · compatible con extensiones | página del vendedor |
| Blender | 4.2+ (build extensión) y un zip legacy para 4.0–4.1 | docs del vendedor |
| Motores | Organic **es Instant Meshes** (BSD-3, redistribuido sin cambios). Hardsurface es Python propio | docs + FAQ |
| Plataformas | El detalle dice `WIN · MAC · LINUX` y el changelog de 1.2.2 anuncia soporte nativo de macOS y Linux; **la FAQ dice "Windows 64-bit only, el motor Organic se distribuye como ejecutable de Windows"** | página vs FAQ — se contradicen |

Esa contradicción no la resuelve este documento: si no estás en Windows,
verificala con el vendedor antes de comprar. El FAQ parece viejo (texto de la
1.x), pero es la única fuente que habla de la plataforma del motor.

Lo que el addon promete, en corto: Organic reconstruye toda la superficie como
una rejilla pareja de quads con un conteo de caras elegido ("pedí 10.000, te da
10.000"); Hardsurface encuentra las aristas reales y rearma cada panel plano como
un n-gono, **sin mover la superficie** ("cada vértice del resultado ya estaba en
el modelo"). Alrededor: conservación de UV/UDIM/materiales, bake desde el
original, limpieza de bucles inútiles, simetría, presets y "Back to Original".

## Veredicto corto

1. **Contribuye a un solo paso del flujo: el 4 (Preparar).** No toca nada del
   NIF, el rig, el plugin, la convención de texturas ni la verificación.
2. **Es un candidato, no un reemplazo.** Compite con `preparar_parte.py`
   (soldar+decimar) y con `hornear.py` (su "Bake From Original"), y su
   característica estrella —que las UV sobrevivan— es casi irrelevante acá,
   porque el paso 4b rehace las UV en un atlas propio.
3. **Lo que decide no son los USD 17, es si corre sin interfaz.** El repo
   entero descansa en scripts que se reejecutan solos (`blender -b --python`,
   trampa 37, "cada script tiene que poder reejecutarse solo"). Un addon que
   solo existe como panel en el viewport es un paso artesanal: no entra al
   runner (`PREPARE` sigue siendo stub), no entra al CI y no se puede
   falsificar. **Eso se prueba en diez minutos y hay que probarlo primero.**

## Contra el flujo, paso por paso

| Paso | ¿Aporta? | Por qué |
|---|---|---|
| 1. Medir el vanilla | No | Nada que ver con el donante ni con posiciones de hueso. |
| 2. Pedir a la IA 3D | Indirecto | `pedir-a-la-ia-3d.md` ya dice: si tu generador ofrece retopología o target polycount, probala y comparala; si dudás, pedí máximo detalle y decimá en Blender. Esto es la versión local de esa opción, con control propio. |
| 3. Recibir y medir | No | No reemplaza `medir_parte.py`. Al contrario: es un paso que **hay que medir** después. |
| 4. Preparar (soldar, decimar, orientar) | **Sí, y es el único lugar** | Ver "los tres casilleros", abajo. |
| 4a/4b (al_marco, desplegar_uv) | No | Rehace topología: va **antes** de las UV, nunca después. Ver "riesgos", punto 3. |
| 5. Montar | No | Es alineación y transformadas, no topología. |
| 6. Riggear | No medido | Una densidad pareja es mejor punto de partida para copiar pesos del vanilla, pero **este repo no midió** que los pesos se copien mejor desde una rejilla uniforme que desde una malla decimada. No se puede afirmar. |
| 7. Texturas | Compite | Su bake y `hornear.py`+`horneado_puro.py` resuelven lo mismo; los del repo tienen gates medidos. Ver "lo que no aporta". |
| 8. Exportar y verificar | No | `verificar_export.py`, `verificar_uv.py`, `material_arma.py`, `mascara_especular.py` siguen siendo la única verificación. |
| `pipeline/` | No | `PREPARE` es stub; esto sería un backend externo detrás de esa fase, no una fase nueva. |

## En palabras simples: ¿calidad o peso?

| Pregunta | Respuesta |
|---|---|
| ¿Hace el asset **más liviano**? | **Sí, para eso sirve.** Es su trabajo principal, y en un caso concreto es mejor que lo que hacés hoy: cuando el decimado actual "se traba" y no baja del número que pediste, esto sí llega al número. |
| ¿Mejora la **calidad**? | **No en el sentido de que se vea mejor.** No agrega detalle, no mejora las texturas y no arregla un modelo feo. A lo sumo deja la superficie un poco más *prolija* (aristas rectas donde deben ser rectas, piezas planas bien planas). |
| ¿Se ve distinto en el juego? | Poco y por bordes finos: si el decimado de hoy te ondula una arista recta, esto puede evitarlo. Eso **no está medido** con tus assets; se ve en un render, en una tarde de prueba. |
| ¿Arregla que falte una parte, que el modelo mire al revés o que salga invisible? | **No.** Nada de eso. |
| ¿Reemplaza lo que ya tenés? | **No reemplaza nada**: se sumaría en un paso, y los controles del repo siguen igual. Su característica más publicitada (que las texturas no se pierdan) no te sirve, porque tu flujo rehace las texturas al hornear. |

## Los tres casilleros donde podría entrar

### A. Sacar el piso del decimado (trampa 7)

La trampa 7 es el aporte más concreto: `[OBSERVED]` se pidieron 2.500
triángulos y el decimado se topó en 16.453, porque los generadores parten los
vértices por isla de UV y el colapso no puede cruzar una costura. Organic **no
colapsa nada**: fabrica una rejilla nueva con el conteo que le pidas, así que el
piso no existe por construcción.

Lo que hay que tener claro: *por construcción* no quiere decir *verificado*.
Cambia un problema medido (el piso, con la soldadura fina de 0,00001 como
palanca) por un problema sin medir (qué le hace esa rejilla a una malla con
costuras, detalles finos y cáscaras abiertas). Y **soldar sigue haciendo falta
igual**: el motor de rejilla necesita una superficie conectada, y el propio
addon trae "Merge Shells — weld AI/scan shells" para eso. Es una inferencia, no
un dato: hay que probarla.

Segundo detalle, y es del tipo que este repo ya sabe que muerde: **el conteo que
se pide está en caras, y el presupuesto del repo está en triángulos**. Pedir
10.000 te da ~10.000 quads, que son ~20.000 triángulos al exportar. Es una
trampa nueva esperando a que alguien pida "8.000" creyendo que pidió el
presupuesto del hacha.

### B. Paneles planos sin mover la superficie (modo Hardsurface)

El colapso decima bien una cabeza (`[OBSERVED]` 447.406 → 8.000,
indistinguible), y también se midió en un hacha y un escudo. Lo que **no** está
medido en este repo es el caso que este modo ataca: el panel plano con canto,
donde el colapso tiende a ondular la arista recta y el bake hornea esa
ondulación. Hardsurface, por lo que promete, devuelve exactamente los vértices
del original: no puede ondular nada.

Es el casillero con más sentido físico —props, clutter, placas de armadura— y
el que **no tiene un ocupante gratis equivalente**. Pero el dolor tampoco está
documentado en el repo: no hay ninguna trampa que diga "la arista recta salió
ondulada". Aporta si el síntoma existe en tus assets, y eso se ve en un render,
no en un número. El caso del vendedor (8.960 → 137 caras, 98,5 %) es de su
corpus, no del nuestro.

### C. Limpieza de topología (Remove Useless Loops, Smart Cleanup, Fill Missed Gaps)

"Faltan agujeros", "vienen componentes de más" y "el decimado no baja" ya están
en la lista de síntomas de `trampas.md`, y una herramienta que los toca sin
mover la superficie es defendible como paso previo a soldar/decimar. Es también
el casillero donde el repo tiene un hueco propio: **el borde y las piezas
sueltas se miden, la basura topológica no**. `salud_malla.py` la reportaría
recién al final y en forma relacional.

## Lo que no aporta, aunque se venda como aporte

- **"Las UV sobreviven al remesh".** El paso 4b (`desplegar_uv.py`) descarta las
  UV del generador y despliega un atlas propio para el bake. Que una herramienta
  conserve las UV que igual vas a rehacer no vale nada acá. Solo importaría en
  la ruta que **conserva el atlas hasta el NIF**
  (`references/acabado-y-validacion.md`), y en esa ruta la regla del repo
  tampoco cambia: la conservación no se declara, se comprueba (trampa 40,
  `uv_exportacion.py` compara coordenadas por loop, no nombres).
- **"Bake From Original".** Duplica a `hornear.py` + `horneado_puro.py`, que
  tienen gates con número (reducción por tipo de mapa, margen, relleno, PNG sin
  alfa, alineación alta/baja, solape de UV contra el 0,001 del censo). Dos
  fuentes de verdad para el mismo `_n`/`_m` es el problema que el pipeline de
  texturas ya tiene resuelto: `pipeline/texturas.py` no conoce al addon, y el
  addon no sabe nada de la máscara especular ni del `_rmaos` del True PBR.
- **"100 % quads, listo para animación".** El NIF guarda **solo triángulos**
  (`limites-skyrim.md`), y el repo ya dice que conviene triangular
  explícitamente antes de exportar para que el `.blend` sea igual al archivo.
  Los bucles que hacen linda una rejilla no llegan al juego.
- **El rig, el montaje, el plugin.** Nada: eso es `montar.py`, `esl.py`,
  `exportar_nif.py` y el esqueleto vanilla.

## Lo que sí agrega: riesgos nuevos

Ninguno de estos lo atrapa el addon, y todos son del tipo que este repo
colecciona —silenciosos—:

1. **Presupuesto en caras ≠ triángulos.** El techo de `BSTriShape` es 65.535
   vértices y el presupuesto de la clase está en triángulos. Hay que triangular
   y volver a contar con `medir_parte.py`, no confiar en el número que muestra
   el panel. (Trampa propuesta: *"puse el presupuesto y salió al doble"*.)
2. **El conteo exacto no dice si la malla quedó sana.** Un remesh puede dejar
   aristas de borde, no-manifold o piezas sueltas que el decimado por colapso no
   produce. El control ya existe: `salud_malla.py <antes.obj> <despues.obj>`,
   que es relacional y no necesita corpus. Sin ese paso, el aporte del punto A
   se compra a ciegas.
3. **Organic remuestrea la superficie** (los vértices del original los promete
   Hardsurface, no Organic). Consecuencia de orden, que es la parte importante:
   **remeshear va entre 4 y 4b, como el `Solidify`.** Después del bake agrega
   caras sin textura horneada (trampa 32, el mismo motivo) y después de
   desplegar las UV tira el atlas que el bake necesita.
4. **Simetría / "Mirror Retopology".** El repo prohíbe el espejo por
   construcción en `al_marco.py` (rechaza escala negativa, trampa 38) y tiene
   trampas propias para espejar (trampa 11). Un modo de simetría mal usado
   escribe exactamente eso.
5. **Sombreado duro sin control en el repo.** Los n-gonos con aristas marcadas
   (*Mark Sharp*, *Keep Circles Round*, *No Sharp Edges*) no aparecen en ninguna
   trampa ni en ningún script. El NIF lleva normales de vértice: un panel plano
   sombreado suave se ve en el juego, no en el test. Es un hueco de verificación
   nuevo que este proyecto todavía no tiene.
6. **Headless.** Ver el "experimento", punto 1. Es la diferencia entre un paso
   más del flujo y una herramienta de taller.

Y una nota de encaje, no de riesgo: el repo dice explícitamente que **no hay
ningún binario de terceros** y no versiona lo que no puede redistribuir. Un
addon GPL y pago queda como prerrequisito externo, igual que Blender, PyNifly o
`nif.xml`: se documenta, no se distribuye, y el CI nunca lo va a cubrir.

## Los otros ocupantes del mismo casillero

Antes de adoptar hay que mirar esto, porque cambia el precio real del aporte. Los
tres son gratis y ninguno necesita la interfaz de Blender:

| Herramienta | Qué es | A favor | En contra |
|---|---|---|---|
| **AutoRemesher** | Herramienta aparte, **MIT desde la 1.0** (reimplementó las dependencias GPL), con **CLI real**: `--input x.obj --output y.obj --target-quads 20000 [--sharp-edge 90] [--adaptivity] [--report]` | Es el único de la lista **diseñado para correr sin GUI**: `subprocess` y listo, como quiere el repo. Conteo objetivo en quads y parámetros de filos | Ida y vuelta por **OBJ** (ver abajo). Es un binario externo que hay que instalar y fijar de versión |
| **QuadriFlow** | Ya está **dentro de Blender**: `bpy.ops.object.quadriflow_remesh` con `mode='FACES'`, `target_faces`, `use_preserve_sharp`, `use_mesh_symmetry`, `use_preserve_boundary` y *Preserve Attributes* (el manual: transfiere máscara, face sets, colores) | Cero dependencias nuevas, corre en el mismo Blender 4.4 que la skill ya exige, sin licencia | Historial de **crashear justamente invocado por `bpy`** en background (issues #124004 y #71871, vistos hasta 4.1) y es **lento**; el manual avisa que no limpia geometría que se intersecta y que no reemplaza al remesh por vóxel. El parámetro `preserve_attributes` hay que verificarlo en el build real de 4.4 antes de escribir código: en la firma de la 2.83 no estaba |
| **QRemeshify** | Extensión **GPL-3.0 gratis** dentro de Blender (QuadWild/Bi-MDF), con simetría y guía por sharp edges, seams o face sets | Corre en Blender, sin binarios externos ni licencia, y ya es el "caballo de batalla" de mucha gente | Su propio autor recomienda **entradas por debajo de ~100 k triángulos**: con un asset de IA de 2 M hay que predecimar primero. Y su panel es interactivo (`N`), la automatización está `[sin verificar]` |

**Organic es Instant Meshes** (BSD-3, lo dice en sus créditos), pero eso **no**
significa que la mitad Organic se pueda automatizar gratis copiando: el binario
de Instant Meshes es una aplicación de escritorio OpenGL y su README no
documenta modo batch. La ruta headless práctica del mismo tipo de motor es
AutoRemesher, no Instant Meshes.

Con eso, lo que el addon aporta **por encima** de lo gratis se reduce a la mitad
Hardsurface y a los presets/limpieza alrededor. Y en contra de descartarlo del
todo hay un dato a favor que conviene decir: según su FAQ, **la mitad Hardsurface
es Python puro**, así que es la que tiene más chance de correr en `blender -b`
(el bloqueo es de empaquetado por plataforma, no de tecnología). O sea: los
USD 17 comprarían justamente la mitad que **no tiene reemplazo gratis** y que
**parece** automatizable. Eso es un aporte más chico que el que sugiere la página
de venta, y más honesto de describir así.

## El experimento que lo decide

Media hora, con las herramientas que ya están en el repo, y sobre un asset del
que ya hay números: el escudo de Tripo (2 M → 12.000, camino completo de
`hd-texturas.md`) o el hacha.

**Rama A — línea base (lo que hay hoy).**
`preparar_parte.py --guardar-alto` → `salud_malla.py antes despues` →
`desplegar_uv.py` → `hornear.py`.

**Rama B — Organic.** Soldar igual → remesh Organic con `target_faces` ≈
presupuesto/2 → triangular → `medir_parte.py` (triángulos reales) →
`salud_malla.py` → `desplegar_uv.py` → `hornear.py`.

**Rama C — Hardsurface** (si el asset es prop o placa). Remesh Hardsurface →
triangular → `medir_parte.py` → `salud_malla.py` → comparar caja y render
contra la rama A.

Las cinco preguntas que deciden, y ninguna necesita criterio:

1. ¿**Corre** con `blender -b --python`? (si no: es artesanal, y el veredicto
   cambia más que cualquier número de abajo)
2. ¿Llega al presupuesto **en triángulos**, después de triangular?
3. ¿El borde y las piezas sueltas **no aumentaron**? (`salud_malla.py`, regla
   dura)
4. ¿El bake sigue pasando sus gates? (alineación alta/baja, margen, solape de
   UV ≤ 0,001)
5. ¿Se ve mejor, igual o peor en el render? — la única que no es un número, y la
   única que el repo ya reconoce como no medible.

A las cinco conviene sumarles dos números que el repo **todavía no tiene** y que
son los que permitirían comparar dos ramas con datos en vez de con impresiones:

- **Desviación de superficie alta→baja.** A igual cantidad de triángulos, ¿cuánto
  se aleja la baja de la alta? Es la métrica que pone en números lo que hoy se
  juzga en el render, y se puede calcular sin dependencias nuevas: muestrear
  puntos en la alta y `mathutils.bvhtree.BVHTree.find_nearest` contra la baja
  (mediana y p95, no promedio — un solo pico importa más que el promedio). El
  decimado y la retopología se compararían con el mismo instrumento.
- **Aprovechamiento del atlas.** `census/parser_uv.py` ya lo devuelve
  (`area_cubierta`, `desperdicio_01`) y la trampa 17 ya tiene el número medido de
  la baja del escudo: cobertura **0,411** con margen 0,002 — o sea, un 2048 que
  rinde como un 1.313. Es el número que decide la pregunta de UVPackmaster de la
  sección siguiente, y ya existe.

### El gate que falta si entra cualquier backend de retopología

**Triangular antes de hornear, no dejárselo al exportador.** El repo ya dice que
conviene triangular explícitamente antes de exportar, para que el `.blend` sea
igual al archivo que se carga. Con un backend de retopología hay un motivo
adicional: la base tangente con la que se evalúa un normal map es **por
triángulo** y se deriva de la triangulación. Si Blender hornea sobre quads (o
n-gonos, en Hardsurface) y el motor triangula esas caras por otra diagonal, el
normal map se evalúa con otra base y quedan costuras visibles a lo largo de las
diagonales. Es teoría del formato, no una medición de este repo — pero el gate es
barato y su ausencia es silenciosa, así que va igual.

Detalle que lo acota: con el camino actual **el problema no existe**, porque el
decimado por colapso ya devuelve triángulos. Aparece recién cuando entra un
backend que devuelve quads.

Cualquier resultado se escribe con la etiqueta que le toque: `[PROVIDER]` para
lo que hace el addon, `[OBSERVED]` para lo que dé este caso. **Un caso no es una
ley**: si da bien con el escudo, eso no autoriza a escribir "usá Smart Remesh"
en `SKILL.md`; autoriza a escribir "con el escudo, esto pasó".

## Si se adopta, cómo

- **Como ruta alternativa documentada, nunca como dependencia.** Al lado de la
  nota de retopología que ya está en `pedir-a-la-ia-3d.md` ("si tu generador
  tiene retopología, probala y comparala"), con `[PROVIDER]` y con el sello
  "nada de esta ruta se vio en el juego", igual que la ruta `cs_pbr`.
- **El orden, en `hd-texturas.md`:** junto a lo que agrega caras del paso 4,
  antes de 4b. Nada que rehaga topología después del bake.
- **Una pieza va por A o por B, no por las dos** — la misma regla que ya
  separa vanilla de `cs_pbr`. Y el `.blend` intermedio dice de qué rama salió.
- **Los gates no se reemplazan.** `medir_parte.py`, `salud_malla.py`,
  `verificar_export.py`, `verificar_uv.py` y las comprobaciones de UV del bake
  siguen corriendo igual.
- **La abstracción de backends, después de la evidencia, no antes.** Un plan
  JSON que `preparar_parte.py` lea (`--retopologia decimate|backend`, con
  `decimate` por defecto) es barato y encaja con cómo el repo ya maneja
  `montar.py` y `al_marco.py`. Lo que no conviene es escribir un registro de
  backends antes de que **uno** de ellos pase el experimento de arriba: el repo
  ya se comió una vez el costo de construir un framework cuya mitad de fases
  quedaron en stub.
- **No** entra al runner, ni al CI, ni al README como requisito, y **no** es
  la fuente del bake mientras `hornear.py` sea el que tiene los gates. Si algún
  día entra al runner, entra como implementación de `Phase.PREPARE`, detrás del
  gate que ya impide publicar con fases sin conectar.

## "Quiero que los bordes se vean mejor terminados"

Caso concreto: la captura del 2026-09-25 (arma dorada con bandas azules, piezas
de metal con paneles y biseles). "¿Qué herramienta me conviene para los bordes?"
no tiene una sola respuesta, porque **"bordes mal terminados" son al menos tres
problemas distintos** — y se distinguen mirando de cerca, sin instrumentos.

| Lo que se ve de cerca | Qué es | Qué lo arregla | ¿Obliga a rehacer texturas? |
|---|---|---|---|
| El filo es una **línea recta** pero se ve redondeado, "derretido" | **Sombreado**: las normales se promedian sobre la arista | Marcar aristas duras en Blender (*Mark Sharp* / suavizado por ángulo) — **gratis** | **No.** Las UV no cambian; a lo sumo rehornear con las mismas UV |
| El filo **zigzaguea**, el panel se ve combado | **Geometría**: el colapso redondeó la arista | Planar → QRemeshify → Smart Remesh Hardsurface (ver abajo) | **Sí.** Rehacer 4b y 4c |
| El borde se ve **sucio o escalonado** | **Textura**: falta definición en esa zona; el atlas rinde al 41 % de cobertura (trampa 17) | Atlas más grande, o mejor empaquetado (UVPackmaster) | No cambia la malla; se rehace el horneado |

La diferencia de costo entre la primera fila y la segunda es enorme, y por eso el
orden de los chequeos importa: **marcar aristas duras no toca la geometría**, así
que no obliga a rehacer UV ni horneado; un remesh sí obliga a todo el paso 4 en
adelante. Probar primero lo gratis y lo barato.

### Para piezas de metal, el ranking se da vuelta

Lo que sirve para un cuerpo o una cabeza **no** sirve para una pieza de paneles.
AutoRemesher y QuadriFlow son **isótropos**: reparten una rejilla de densidad
pareja sobre toda la superficie sin distinguir un panel de un bisel, que es
exactamente lo que se quiere en un organismo y lo que ablanda una pieza de metal.

| Herramienta | Encaje en paneles de metal |
|---|---|
| **Decimación planar / *Limited Dissolve*** (Blender, gratis) | Junta las caras de un mismo panel en una sola sin mover la superficie. **Implementado** como `preparar_parte.py --planar <grados>`, opt-in, después de soldar, **después de copiar la alta** (la alta es el oráculo del bake y tiene que llegar densa) y antes de colapsar. **No endereza**: disolver una región casi plana borra geometría redundante, no proyecta un vértice sobre una recta. Su valor acá es indirecto: un panel que ya es una sola cara no le da al colapsador interior donde repartir el error, y por eso los filos quedan menos ondulados. Riesgo: los paneles de una malla de IA **no son perfectamente planos**, y un ángulo generoso deja n-gonos combados. El ángulo no está medido; **el pase no se corrió con Blender** |
| **Enderezado de cadenas duras** (Blender, gratis) | El arreglo **directo** de la línea que zigzaguea: ajustar la cuerda de la cadena y proyectar los vértices interiores sobre ella, con los extremos fijos. Implementado como `enderezar.py` + `enderezar_puro.py`, con tope fail-closed (si la cadena se aparta más que el tope es una **curva de diseño** y no se toca), rechazo de bifurcaciones y ciclos, y modo informe por defecto. La matemática está verificada por `test_enderezar_puro.py`; **el script de Blender no se corrió** y el tope no está medido |
| **QRemeshify** (gratis) | El mejor gratis para esto: se puede guiar por aristas duras, costuras o face sets. Límite: entradas por debajo de ~100 k triángulos, o sea predécimar primero |
| **AutoRemesher** (gratis, headless) | Tiene `--sharp-edge <ángulo>`, pero sigue siendo isótropo |
| **Superficie de Smart Remesh (Hardsurface)** | La única diseñada para esto: paneles a n-gono, círculos redondos, y **ningún vértice nuevo**. USD 17 y headless `[sin verificar]` |
| **QuadriFlow** (gratis, en Blender) | El peor encaje de la lista para metal: rejilla isótropa, lenta, y con historial de crashes por `bpy` |

### Tres correcciones a la primera versión de esta sección

Una tercera revisión (2026-09-26) encontró esto, y tiene razón en lo primero y
en lo tercero:

1. **Disolver no es enderezar.** La primera versión de esta sección proponía el
   pase planar como el arreglo de la línea ondulada. No lo es: `DISSOLVE` borra
   geometría redundante; no calcula una recta ni proyecta nada. Solo ayuda de
   forma indirecta (deja al colapsador menos interior donde repartir el error).
   El arreglo directo es el enderezado, y eso es `enderezar.py`.
2. **Sobre la alta, la revisión leyó mal, y el error de redacción fue mío.** El
   código siempre copió la alta **antes** de tocar la baja (`alto_malla =
   obj.data.copy()` va antes del pase planar), que es lo que la revisión
   recomienda —pero el texto que acompañó el cambio decía lo contrario
   ("va antes de copiar la alta"). El código estaba bien y la explicación mal;
   se corrigió la explicación.
3. **"Si la alta ya viene ondulada, ningún decimado ni addon lo arregla" era
   falso, y del tipo de error que este repo persigue.** Es exactamente un
   bloqueo inventado: el enderezado, la retopología guiada y la reconstrucción
   de cadenas atacan eso, y de hecho es para lo que se escribió `enderezar.py`.
   Lo que **sí** es cierto y sobrevive: si la ondulación viene del generador,
   el arreglo es una intervención geométrica deliberada, no un remesh genérico
   ni más polígonos.

Y un detalle que las tres versiones del análisis tenían mal y encontró el
autotest al escribirlo: el grupo de aristas que forma un **camino abierto**
también tiene grado máximo 2, igual que un ciclo, así que la primera versión
del detector rechazaba toda cadena como si fuera un círculo. Es la misma
familia de error que las trampas del repo: no tira excepción, no deja la malla
rota — simplemente no endereza nada, en silencio.

### Lo que salió de escribirlo: los cruces

El enderezado se escribió y se probó **antes** de que el usuario lo corriera, y
eso destapó dos cosas que ninguna de las tres opiniones había visto:

1. **En una pieza dura las crestas se cruzan.** La primera versión partía el
   grafo en "componentes conexos" y **rechazaba todo componente con un vértice
   de grado > 2** — con eso, en una pieza de metal con crestas que se cruzan no
   se enderezaba nada, y el informe culpaba al tope. Ahora el grafo se parte en
   **caminos que no comparten aristas**, con el cruce como EXTREMO de cada uno:
   los cruces nunca se mueven, y ninguna arista cae en dos caminos. Es el
   invariante que hace seguro enderezar caminos sin coordinarlos, y hay un test
   que lo exige sobre cinco figuras.
2. **Detectar crestas por ángulo es ruidoso en una malla de IA.** La superficie
   es densa y la cresta aparece y desaparece a lo largo de la misma línea, así
   que los caminos salen cortos. De ahí `--marcadas`: que la línea la elija una
   persona mirando la pieza y no un umbral de grados. Marcarla en Blender es
   trabajo manual, pero es **el único modo de que el script sepa cuál línea es
   intención de diseño** — que es exactamente el problema que ningún remesher
   automático resuelve, y la razón por la que el enderezado gana donde el
   remesh pierde.

### Un hueco de verificación que este caso destapa

**Nada en el repo controla el sombreado.** `preparar_parte.py` solo hace
`DECIMATE/COLLAPSE` (`use_collapse_triangulate`), y `shade_smooth`, `mark_sharp`
y el suavizado por ángulo no aparecen en ningún script, en ninguna trampa ni en
ningún test. El NIF lleva **normales de vértice**: una cara plana sombreada suave
—o una arista dura que quedó promediada— se ve en el juego y no en ningún
control. Es la misma familia que el resto de las trampas: falla en silencio.

## Contraste con la segunda opinión (recibida el 2026-09-26)

Otro agente propuso un plan más amplio: usar Smart Remesh solo para geometría,
abstraer el paso 4 en un `retopologia.py` con backends (decimate, QuadriFlow,
AutoRemesher), probar AutoRemesher primero, y además considerar UVPackmaster.
Verificado punto por punto:

| Afirmación de la segunda opinión | Veredicto |
|---|---|
| Smart Remesh no debe ser dependencia, solo geometría; el bake propio no se reemplaza | **De acuerdo.** Es lo mismo que concluye acá, y por los mismos motivos |
| Organic usa Instant Meshes (BSD-3) | **Confirmado** (créditos del addon) |
| Dejar Smart Remesh como backend opcional "especialmente para hard-surface" | **De acuerdo, y es el único casillero que sobrevive** al descarte de lo demás |
| **AutoRemesher es MIT y tiene CLI headless** | **Confirmado, y más fuerte de lo que dice**: la 1.0 (MIT) reimplementó las dependencias GPL e incorporó el CLI con `--target-quads`, `--sharp-edge`, `--smooth-normal`, `--adaptivity`, `--report`. Es el mejor candidato headless de la lista |
| Automatización de AutoRemesher "muy alta" | **De acuerdo**, con una reserva que la segunda opinión no menciona: **el CLI trabaja sobre OBJ**, o sea ida y vuelta por archivo. Ver abajo |
| QuadriFlow: "automatización **muy alta**" | **Matizado.** Está disponible desde `bpy`, sí, pero hay issues abiertos de **crashes al invocarlo por `bpy`** en background y el manual avisa que es lento y que no limpia geometría que se intersecta. "Disponible desde Python" no es lo mismo que "automatizable con confianza": hay que probarlo con 2 M de triángulos en 4.4 antes de contarlo como backend |
| Lista `preserve_attributes` entre los parámetros de QuadriFlow | **Existe en el Blender actual** (el manual lo llama *Preserve Attributes*), pero no estaba en firmas viejas: hay que verificarlo contra el build 4.4 real antes de escribir código. Es `[PROVIDER]`: caduca |
| QRemeshify "US$ 7 / GPL" | **El precio está mal al alza: es GPL-3.0 y gratis** (pago voluntario). A favor: corre dentro de Blender. En contra: el autor recomienda entradas **< ~100 k triángulos**, y un asset de IA trae 20 veces eso |
| QuadAnneal expone batch y modo determinista, y es MIT | **Sin verificar acá.** Es nuevo y no lo pude contrastar: queda en lista de observación, no en un plan |
| RetopoFlow no sirve para headless (`if bpy.app.background`) | **Coherente** con que sea una herramienta interactiva. No verifiqué la línea de código, pero la conclusión es correcta |
| **UVPackmaster 4: scriptable y ~US$ 55** | **Confirmado**: la arquitectura tiene Python embebido (`UVPM3_script(context, group_name)`), hay versión PRO de US$ 55 y la 3 a US$ 44. Y es **más interesante de lo que la segunda opinión sugiere**: el repo tiene el número medido (cobertura 0,411, trampa 17), así que el "antes de comprarlo, medí cuánto desperdiciás" ya está medido — se desperdicia ~59 %. Si un empacador llevara la cobertura a 0,6–0,7, eso es **1,5–1,7× de densidad de téxel en el mismo atlas**: calidad real, medible, sin tocar la malla. Ojo con dos cosas: el margen entre islas es lo que evita el sangrado en los mipmaps, así que la ganancia tiene que medirse **junto al solape y al margen**, no sola; y la licencia es comercial y atada a máquinas, contra la disciplina de "ningún binario de terceros" |
| Triangular antes de hornear | **De acuerdo, y es el mejor aporte técnico de la lista** (ya incorporado arriba). Con el detalle de que hoy no aplica: el decimado ya devuelve triángulos |
| Medir "desviación geométrica high→low" | **De acuerdo, y es el segundo mejor aporte**: el repo no tiene esa métrica y es la que convierte "se ve mejor" en un número comparable |
| `PREPARE` sigue siendo stub y esta capa sería su implementación futura | **Correcto.** Es el lugar natural, detrás del gate que ya existe del runner |
| Orden de investigación: QuadriFlow → AutoRemesher → Smart Remesh → UVPackmaster | **Se invierte en los dos primeros.** AutoRemesher tiene CLI nativo y no tiene el historial de crashes de QuadriFlow; QuadriFlow es la opción "sin instalar nada", no la más automatizable. Smart Remesh queda donde la segunda opinión lo pone, y UVPackmaster va en una **pista aparte**, porque no compite con nada de esto: es UV, no geometría |

**El punto que la segunda opinión no menciona y que cambia el encaje de
AutoRemesher:** su CLI trabaja sobre OBJ, así que entra por *subprocess* con ida
y vuelta por archivo. Este repo tiene una regla en contra —"la malla de juego no
sale de Blender", `hd-texturas.md`— porque un ida y vuelta puede reordenar o
fusionar vértices. Pero **la regla se aplica a lo que ya tiene datos que
perder**, y en el paso 4 todavía no hay UV propias, ni pesos, ni bake: no hay
nada que romper. La conclusión práctica es de **orden**, no de prohibición:
soldar y aplicar la matriz del importador **a la baja y a la alta**, retopologizar
**solo la baja**, y recién después UV (4b) y bake (4c). Dos cuidados que
corresponden a trampas que ya existen: el reimport del OBJ trae **otra matriz de
importador** (trampa 3, el modelo acostado) y el resultado hay que volver a
medirlo con `medir_parte.py` y `salud_malla.py`, sin creerle al reporte del
binario.

Y una cosa que ninguna de las dos opiniones puede decidir por sí sola: **el
orden de compra, si hay que comprar**. Smart Remesh son USD 17 por un casillero
que no tiene reemplazo gratis (Hardsurface, y solo si probás que corre en
background). UVPackmaster son USD 55 por un número que **ya está medido a favor**
(59 % de atlas desperdiciado). Si el objetivo es calidad de lo que se ve en el
juego, la pista de UV tiene mejor relación señal/precio que la de geometría.

## Contraste con la tercera opinión (guía de compras, 2026-09-26)

Un tercer documento propone una guía de addons pagos por etapa —MESHmachine,
Hard Ops, RetopoFlow 4, Quad Remesher, Zen UV, UVPackmaster, TexTools, Marmoset
Toolbag— con un orden de compra. Es un documento competente como guía de
compras, pero **casi todo lo que dice del flujo ya está en el repo, con
números medidos**, y su recomendación principal no encaja con la entrada de
esta skill. Lo verificable:

| Afirmación | Veredicto |
|---|---|
| **PyNifly corre solo en Windows** | **Confirmado, y es el aporte real de ese documento.** Lo dice su README. El `compatibility` de `SKILL.md` no lo decía: quedó escrito ahora. Sin eso, alguien en Linux o macOS instala la skill y lo descubre al final |
| El addon de NifTools no sirve para Blender 4.4 | **Confirmado**: su última release (v0.1.1, 2023) dice "compatible con Blender 2.8–3.6, NOT compatible con Blender 4.0" |
| "Work with quads, triangulation is handled on export" y "4 weight groups per vertex" (wiki de PyNifly) | **Correcto y ya cubierto**: `montaje_puro.py` tiene la REGLA `max4`, y la triangulación explícita está en `limites-skyrim.md` y en el gate nuevo de este PR |
| No confundir el cambio de referencia PNG→DDS que hace PyNifly con crear el DDS | **Correcto y ya cubierto**: `pipeline/texturas.py` escribe el DDS de verdad, con mipmaps, y `comparar.py` lo verifica |
| "No medir la calidad visual solo con el validador NIF" | **Correcto y ya está en el repo**, casi con las mismas palabras: `SKILL.md` dice que un asset puede pasar todos los chequeos y ser feo |
| El orden topología → seams → unwrap → densidad → packing → bake | **Correcto y ya está** en `hd-texturas.md`, con los gates que este documento no menciona |
| **MESHmachine primero** para hard-surface | **No encaja con esta skill.** MESHmachine es una caja de herramientas de chaflanes y empalmes para mallas **modeladas a mano con topología limpia**. La entrada de acá es una escultura de 2 M de triángulos de un generador: no se le puede hacer un chaflán a eso, ni el addon arregla un canto ondulado (eso lo hace `enderezar.py`, gratis) |
| **RetopoFlow segundo**, "control de loops" | **Como herramienta humana, sí; como paso del pipeline, no.** Es manual, de viewport, y su propio código se abstiene de inicializarse en `bpy.app.background` (lo verificó la segunda opinión). La misma disciplina que descartó a Smart Remesh por headless lo descarta acá |
| TexTools (gratuito, GPL) | **Aporte menor y válido**: entra a la lista de opciones gratis de UV/bake, con la advertencia de probarlo en Blender 4.4 |
| Quad Remesher (Exoside, pago, con prueba) | **Aporte al cuadro de remalladores**: es el patrón contra el que se comparan los gratis (AutoRemesher, QRemeshify, QuadriFlow). Tiene trial, así que es evaluable sin comprar |
| Marmoset Toolbag (USD 399 / desde 18,99 al mes) para bake | **No compite con lo que hay**: el bake del repo tiene gates medidos y conoce la convención de Skyrim; el de Marmoset no, y encima su documentación de *tangent handedness* toca el mismo problema que el gate de triangulación de este PR. Es una compra de volumen, no de esta etapa |
| Los precios | **Sin auditar.** El único que verifiqué antes es UVPackmaster 4 (USD 55, single user). Que estén en dólares de septiembre de 2026 no los hace parte de este análisis |

**Lo que el documento no dice, y es lo que decide acá:**

1. **Ignora el eje headless**, que es el que descartó a Smart Remesh y el que
   ordena toda esta skill. RetopoFlow y MESHmachine son herramientas de manos,
   y el repo se construyó alrededor de pasos que se reejecutan solos.
2. **No conoce los números del repo.** No menciona que el atlas ya llega al
   41 % de cobertura con dos arreglos gratis (trampa 17: margen `FRACTION` y la
   selección por bmesh) — el número contra el que tendría que competir su
   recomendación de empaquetado pago — ni los presupuestos medidos del censo.
3. **No sabe que el defecto ya está atacado.** La guía es anterior a este PR: el
   canto ondulado —lo que el usuario reportó— se arregla con `enderezar.py`,
   gratis, sin comprar nada.

### El hueco que la guía sí nombra, y que este repo no cubre

Hay una etapa que la guía pone primero y el repo **no tiene**: el **acabado
hard-surface** —chaflanes, empalmes, transiciones entre piezas. En todo el repo
la palabra "Bevel" aparece una sola vez, y como peligro (trampa 32: un bevel
después del unwrap superpone las UV). Si algún día se modelan las piezas a mano
en vez de generarlas, esa etapa es real y hace falta vocabulario para ella: qué
es un chaflán bien puesto y qué se rompe al hornearlo.

La pregunta que sigue —si esa etapa se puede replicar con IA, o hacer una
herramienta propia— está desarrollada aparte, en
[`docs/analisis-replicar-addons.md`](analisis-replicar-addons.md), con los
números de empaquetado de UV y las licencias.

Pero **no es la etapa de este flujo**, y decirlo importa para no gastar:
sobre una malla de escultura de IA, un chaflán no se modela, se **reconstruye**
—que es exactamente lo que hace el pase planar (`--planar`) y el enderezado de
este PR, con lo que ya trae Blender—. La compra se justifica el día que haya
geometría con topología limpia y controlada sobre la que trabajar, no antes.

## Lo que este documento no afirma

- Que el addon funcione, ni en background, ni en tu plataforma, ni con tus
  assets: no se corrió.
- Que aporte: los tres casilleros son hipótesis con su medición pendiente.
- Que no aporte: el caso "panel plano sin ondular la arista" es el más
  plausible de todos y el repo no tiene con qué rebatirlo.
- Ningún número del addon es de este repo. Su 98,5 % de reducción y su
  2.000.000 → 20.000 son de su corpus.
