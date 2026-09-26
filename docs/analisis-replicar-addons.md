# ¿Se pueden replicar los addons pagos? ¿O hacer una herramienta propia?

Respuesta corta, en dos partes:

- **Replicar con IA: la pregunta está mal planteada, porque ninguna de las
  nueve es IA.** Ocho son algoritmos deterministas de geometría —empaquetar
  islas en 2D, chaflanar aristas, proyectar rayos— que ya existen como software
  libre, o como operadores que Blender trae y el repo ya llama; la novena,
  PyNifly, es un exportador de formato y ya está en el stack. La IA no hace más
  fácil ninguna: nadie "aprende" a empaquetar islas.
- **Una herramienta propia: no es descabellado, y en buena parte ya existe.** El
  repo *es* una herramienta propia del pipeline. Lo que falta es una etapa
  concreta y acotada —el acabado hard-surface— y se puede empezar por una
  medición de una tarde antes de escribir una línea.

El resto de este documento es el detalle, con lo que verifiqué y lo que no.

## 1. De qué naturaleza es cada problema

| Herramienta de la guía | Qué resuelve de verdad | Naturaleza | Reemplazo libre, verificado |
|---|---|---|---|
| **Zen UV** | Unwrap + empaquetado asistido | Algoritmo 2D + atajos de interfaz | `desplegar_uv.py` ya llama a `smart_project` → `average_islands_scale` → `pack_islands`. Es el mismo trío de operadores |
| **UVPackmaster** | Empaquetado denso | Optimización 2D (NP-difícil en la práctica) | xatlas (MIT, binding de Python, corre dentro de Blender) o el `pack_islands` actual |
| **MESHmachine** | Chaflanes y empalmes que sobreviven la edición | Operador BMesh + **workflow de manos** | `bmesh.ops.bevel` para el chaflán; el workflow no es replicable ni falta |
| **Hard Ops** | Booleanas y modelado mecánico | Operador + interfaz | Igual: operadores de Blender; la parte que se paga es la interfaz |
| **RetopoFlow 4** | Retopología a mano | **Humano en el viewport** | Retopología automática: QuadWild (vía QRemeshify), AutoRemesher (MIT, CLI headless), Instant Meshes (BSD) |
| **Quad Remesher** | Retopología automática | Geometría (Bi-MDF / campo de direcciones) | AutoRemesher y QRemeshify ya están en el cuadro de opciones del documento anterior |
| **TexTools** | UV y horneado | Operadores | Gratuito, entra a la lista |
| **Marmoset Toolbag** | Horneado de alta calidad y velocidad | Proyección de rayos + motor propio | `bpy.ops.object.bake` con `use_selected_to_active`, `use_cage`, `cage_extrusion`. El repo ya hornea con gates propios |
| **PyNifly** | Exportar NIF | Formato de archivo | Es el único sin reemplazo real, y ya está en el stack (Windows) |

**Conclusión de la tabla:** en ocho de nueve casos lo que se paga no es el
algoritmo, es el **producto** —la interfaz, la velocidad, la robustez con mallas
sucias, el soporte—. Reimplementar el algoritmo suele ser *fácil*; lo caro es
todo lo demás. Y en el flujo de este repo la interfaz no vale nada, porque no
hay nadie mirando el viewport.

## 2. Cuánto cuesta cada cosa, por orden de magnitud

Ordenado de "una tarde" a "no lo hagas". **Todas las estimaciones de esfuerzo
son `[sin medir]`**: no hay Blender en este entorno, así que no corrí nada.

### 2.1 Una tarde: el chaflán sobre las líneas marcadas

`bmesh.ops.bevel` toma las aristas que le des y acepta `segments`, `offset`,
`affect`, `loop_slide`, `clamp_overlap`, `mark_seam`, `mark_sharp`,
`harden_normals`, `miter_outer`. El repo **ya tiene el paso más difícil**, que
no es el chaflán: es saber *dónde* va — la convención `--marcadas` de
`enderezar.py`, con su informe de calibración.

**El asterisco, y es grande:** Blender tiene un problema viejo y conocido con las
UV de un bevel. En las esquinas, las caras nuevas salen con las UV aplastadas o
"puenteando" islas distintas — está en un reporte histórico del tracker de
Blender ([T56625](https://developer.blender.org/T56625)) y el hilo muestra que
seguía en 2.8 y 2.93. No verifiqué el estado en 4.4, así que `[sin verificar]`.
Es la explicación de fondo de la trampa 32 de `trampas.md`: un bevel después
del unwrap superpone las UV.

Es decir: la *operación* son cinco líneas; el *trabajo* es la reparación de UV
que viene detrás.

### 2.2 Un día o dos: re-atlas con xatlas

xatlas ([jpcy/xatlas](https://github.com/jpcy/xatlas)) es **MIT**, C++11 sin
dependencias, fork independiente de thekla_atlas (la de *The Witness*). Genera atlas desde cero: `ComputeCharts` → `PackCharts`.
Existe binding de Python ([xatlas-python](https://github.com/mworchel/xatlas-python),
`xatlas` en PyPI) y hay una receta pública de gente corriéndolo **dentro de
Blender 4.1+** ([issue 19](https://github.com/mworchel/xatlas-python/issues/19)) — `[sin verificar]` en
nuestro caso, es una receta de la comunidad, no del proyecto.

Para este pipeline lo interesante **no es el empaquetado** (sección 2.3), sino
que re-atlasa de cero: sería la salida limpia para el chaflán, en vez de
reparar UV a mano. Y como toda la malla se re-despliega, la trampa 32 deja de
aplicar.

### 2.3 Semanas o meses: el empaquetado de UVPackmaster

Acá hay que ser justo: **UVPackmaster no vende humo**, y hay un número medido
que lo prueba. En el pedido de mejora [68889 del tracker de
Blender](https://projects.blender.org/blender/blender/issues/68889) se compara el
empaquetado propio con Packmaster sobre el mismo asset:

| | Sin rotación | Con rotación |
|---|---|---|
| Blender (cajas envolventes convexas) | 46,4 % del área | 48,2 % |
| Packmaster, 3 s de heurística | 59,4 % | 68,5 % |

**Es una ventaja real de ~20 puntos de área** — y esos números son del tracker
de Blender con sus assets, no de este repo. La razón es de algoritmo: Blender
trata cada isla como una forma convexa; Packmaster las trata como cóncavas y
busca con heurística.

Replicarlo no es un problema de IA: es un **problema de optimización 2D** (el
empaquetado de formas convexas/cóncavas ya es NP-difícil) más un motor
multihilo. Su motor es una aplicación C++ aparte, así que "replicar" significa
reimplementar el algoritmo, que es exactamente donde está el valor.

**No lo hagas**, y además no hace falta: el problema de este pipeline no es el
empaquetado denso. Los dos arreglos gratis de la trampa 17 —margen
`margin_method="FRACTION"` y marcar las UV por bmesh antes de `pack_islands`—
llevaron la cobertura del atlas de **0,235 a 0,411** sobre la baja del escudo
(12.000 tris, 1.724 islas): un 2048 que rendía como un 993 pasó a rendir como un
1.313. Primero hay que agotar ese 41 % medido y gratis antes de pelear el 59-68 %
del tracker.

### 2.4 No aplica: el workflow de manos

MESHmachine y RetopoFlow valen por la **edición interactiva**: chaflán que se
rehace, bucles que se arrastran, previsualización. RetopoFlow además no se
inicializa en `bpy.app.background` (ya verificado en la segunda opinión). Sin
viewport no hay nada que replicar: es como replicar el volante de un auto en un
auto que va por rieles.

### 2.5 Ya está: el horneado

El bake del repo ya usa el mismo mecanismo que cobra Marmoset: proyección de
rayos con jaula. La firma completa está en `bpy.ops.object.bake`:
`use_selected_to_active`, `use_cage`, `cage_object`, `cage_extrusion`. Lo que
Marmoset agrega es velocidad, batching y robustez — producto, otra vez.

Un detalle que sí importa y conviene anotar: hay una regresión reportada en
**Blender 5.0** ([reporte
151027](https://projects.blender.org/blender/blender/issues/151027)) donde
`cage_object` no se encuentra en la escena evaluada, y el propio reporte dice que
anda bien en **4.5 LTS**. El repo apunta a 4.4, así que
no nos toca, pero es una razón medida para **no saltar de versión sin correr
los seis gates** antes.

## 3. Entonces, ¿dónde sí hace falta IA?

En dos lugares, y ninguno de los dos es una de las herramientas de la lista:

**a) Decidir dónde están las líneas estructurales.** Hoy es manual
(`--marcadas`), y el motivo es medido: la detección por ángulo es ruidosa sobre
malla de IA (segunda opinión). Es un problema de **segmentación**, que es la
forma que la IA sí resuelve bien — pero para aprenderlo hacen falta ejemplos
etiquetados que no existen, y el etiquetado es justamente lo caro. Lo barato ya
está hecho: marcar a mano y leer la calibración del informe.

**b) Decidir si el resultado se ve bien.** El repo tiene una regla explícita: un
asset puede pasar todos los gates y ser feo. Ese es el único casillero donde
"replicar con IA" tiene sentido literal: un modelo de visión que mire los
renders A/B/C/D y los ordene. `[sin medir]`, y con dos condiciones: no puede
ser la única autoridad, y hay que medirlo contra el juicio humano antes de
usarlo para decidir una compra o descartar una malla.

## 4. La herramienta propia: qué sería y qué falta

No es descabellado porque **ya existe en un 80 %**. El pase de acabado
hard-surface, que es la etapa que la guía pone primera y el repo no tiene,
sería:

| Paso | Estado |
|---|---|
| 1. Saber dónde están las líneas (ejes, cantos) | **Hecho**: convención `--marcadas` |
| 2. Enderezarlas | **Hecho**: `enderezar.py` + `enderezar_puro.py`, en este PR |
| 3. Chaflanarlas | **Falta**: una llamada a `bmesh.ops.bevel` |
| 4. Reparar o rehacer las UV | **Falta**: la parte difícil (2.1 y 2.2) |
| 5. Hornear la capa HD | **Hecho**: `hornear.py`, `horneado_puro.py` |
| 6. Verificar | **Falta el gate de la trampa 32**: medir cuánta UV se superpone |

Lo que falta es una etapa, no un producto. Y sigue el patrón que ya está
probado en este repo:

- un **módulo puro** (sin Blender) con el cálculo y su `--autotest`, para que
  corra en CI;
- un **pase de Blender** que lo aplique y escriba un **informe con calibración**
  —percentiles y conteos— como el de `enderezar.py`;
- **fail-closed**: sin margen de error conocido, no guarda;
- y una prueba estática que verifique que el pase no hace nada más que lo que
  dice.

**El primer paso no es programar nada: es medir.** Sobre un fixture, aplicar un
chaflán de un segmento a las líneas marcadas y medir cuánta área de UV se
superpone y cuánto cambia la densidad de téxel. Si el número es chico, el pase
es una tarde de trabajo después de eso. Si es grande, la respuesta correcta es
"no chaflanar, re-atlasar con xatlas", y también quedó contestado.

## 5. La regla de licencias: usar, no reimplementar

| Software | Licencia | Qué hacer |
|---|---|---|
| xatlas | MIT | Usar. Se puede empaquetar |
| AutoRemesher | MIT | Usar |
| Instant Meshes | BSD-3 | Usar |
| QuadWild / QRemeshify | GPL-3.0 | Usar como herramienta aparte; no linkear, la GPL contagia |
| UVPackmaster | Addon + **motor C++ aparte, propietario** ([verificado en el
  anuncio](https://blenderartists.org/t/uv-packmaster-efficient-uv-packing-solution-for-blender-c-based-multithreaded/1102737)) | No copiar. Reimplementar desde el algoritmo es legal, y es semanas de trabajo |
| MESHmachine, Hard Ops, RetopoFlow, Zen UV, Marmoset | Comerciales, cerrados | No copiar. Nada del repo los necesita |

La regla es la de siempre: **una herramienta libre se usa; una propietaria no se
desarma.** Y ninguna de las dos cosas se mete como dependencia del runner ni
del CI, que siguen sin terceros.

## 6. Lo que este documento no afirma

- **No corrí nada de esto.** No hay Blender en este entorno: las estimaciones de
  esfuerzo son `[sin medir]` y están marcadas una por una.
- **Los números de empaquetado no son de este repo.** Son del pedido 68889 del
  tracker de Blender, con sus assets y su hardware.
- **No verifiqué el estado del problema de UV del bevel en Blender 4.4.** El
  reporte es histórico y el hilo llega hasta 2.93.
- **No verifiqué la receta de xatlas dentro de Blender 4.4**: es de la
  comunidad, y el binding de Python no lo corrió nadie acá.
- **No toqué el runner ni el CI**: no entra ninguna dependencia nueva.
- **No es una recomendación de compra ni de gasto.** Es un mapa de qué es
  algoritmo, qué es producto y qué es trabajo de manos.
