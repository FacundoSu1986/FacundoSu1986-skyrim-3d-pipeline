# Tu primer mod: de un modelo de IA a algo que se ve en el juego

Un camino para quien **nunca hizo un mod**. Si ya hiciste alguno, esto no te
hace falta: andá directo a `SKILL.md`.

La regla de este documento: todo lo que dice acá **se puede correr**, y lo que
no está medido va marcado como tal. Si algo no te cierra, el archivo que manda
es `SKILL.md` — esto es el atajo para llegar a él.

## Lo que necesitás

| | |
|---|---|
| **Blender 4.4** | gratis, de blender.org. La versión importa: los scripts se midieron en la 4.4 |
| **PyNifly** | el addon de Blender que lee y escribe NIF. Se instala aparte. **Solo corre en Windows**, no en Linux ni en macOS |
| **Python 3.11 o 3.12** | para los scripts que no son de Blender. Blender trae el suyo |
| **El juego** | **solo si vas a reemplazar algo que ya existe** (Camino B). Para un ítem nuevo, no hace falta |

Y algo que conviene saber de entrada: **acá no hay nada de Bethesda**. Ni mallas,
ni texturas, ni archivos sacados del juego: el repo no los trae y no puede
traerlos. Lo que hay son las herramientas para trabajar sobre **tu** copia legal.

## Antes de nada: elegí el camino

Son dos, y el primero es el que te conviene si es tu primer mod.

| | **Camino A: un ítem nuevo** | **Camino B: reemplazar algo que ya existe** |
|---|---|---|
| Qué tenés que sacar del juego | **nada** | el NIF vanilla y sus texturas |
| Qué necesitás además | escribir el plugin (ARMO/ARMA) que registra el ítem | respetar el marco del nodo vanilla |
| Ventaja | no tocás archivos de Bethesda | el objeto ya existe y ya se ve en el juego |
| Dificultad | hay que hacer el plugin | hay que sacar el donante sin romperlo |
| El NIF que exportás | igual | igual |

**Si es tu primer mod, hacé el Camino A**: no necesitás el juego para empezar, y
el repo ya sabe escribirte el plugin. Si lo que querés es que la espada vanilla
pase a verse distinta, es el B, y el paso 0 del Camino B es sacar el donante
(acá abajo está cómo).

## Camino B: sacar el donante del vanilla

Los archivos del juego vienen empaquetados en archivos `.bsa` dentro de la
carpeta `Data` de tu instalación. Los que te interesan son los
`Skyrim - Meshes*.bsa` (mallas) y los `Skyrim - Textures*.bsa` (texturas).

Para abrirlos hace falta una herramienta aparte, porque **el repo no trae
ningún binario de terceros** — a propósito. La que conviene para empezar es
**BAE (Bethesda Archive Extractor)**: abre el `.bsa`, te muestra qué hay
adentro y te deja extraer solo lo que querés. Páginas verificadas el
2026-09-26:

- **BAE**: https://www.nexusmods.com/skyrimspecialedition/mods/974
- **Cathedral Assets Optimizer** (extrae también, y además optimiza texturas,
  pero no te deja ver el contenido antes): https://www.nexusmods.com/skyrimspecialedition/mods/23316

En tres pasos: abrís el `.bsa` (o lo arrastrás a la ventana), buscás el archivo
por nombre, y lo extraés a una carpeta. Después ese NIF se abre en Blender con
PyNifly, y `nif_nodos.py` te dice qué tiene adentro: qué nodos, dónde está cada
hueso y con qué medidas.

`[sin verificar]` en este repo: ninguna de las dos herramientas se corrió acá —
son ventanas de Windows y este repo no las trae. Lo que sí está medido es el
camino que espera: los `--autotest` de `censo_nif.py` y de `nif_nodos.py` te
dicen que apuntes a **la carpeta donde BAE extrajo el vanilla**, así que es el
camino que el proyecto asume de punta a punta.

Y el recordatorio que no está de más: podés trabajar sobre tu copia del juego,
**no redistribuir** lo que sacaste.

## Paso 0: probá el taller con el ejemplo, sin el juego

Antes de tocar tu modelo, corré esto. No hace tu mod: **te dice si el taller está
armado**, que es otra cosa.

```bash
python examples/escudo-minimo/correr.py --blender "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"
```

Imprime, paso por paso, qué hizo y qué salteó. Qué significa que salga cada cosa:

| Sale | Quiere decir |
|---|---|
| **0** | corrieron los siete pasos y el NIF pasó la verificación. **Tu taller está bien** |
| **1** | un paso que corrió falló. Ahí está el problema, y el informe dice cuál |
| **2** | la ruta de Blender que le pasaste no sirve |
| **3** | **incompleto**: falta Blender o PyNifly. Lo que corrió, anduvo |

El 3 no es un fracaso: es "falta instalar algo". Corrido el 2026-09-26 en este
repo, sin Blender, sale **3**, y el informe termina así:

```
[ejemplo] INCOMPLETO: corrio lo que se podia sin Blender. No es un exito: el NIF no se hizo.
```

**No saltees este paso.** Sin él, cualquier falla de más adelante es
indistinguible de "no tengo Blender instalado", y vas a estar buscando el
problema en el lugar equivocado.

## Cómo se instala la skill

Copiá la carpeta `skills/modelo-ia-a-skyrim/` a tu carpeta de skills (Claude
Code las lee de ahí), o empaquetala:

```bash
python build_skill.py
```

**Cómo saber que quedó bien.** Preguntale algo que solo está acá: *"¿por qué el
escudo sale negro si el NIF está bien?"*. Si quedó, te va a hablar de hornear el
albedo con `DIFFUSE` (trampa 31) y no de cosas genéricas.

Y una cosa que conviene tener clara, para no pedirle peras al olmo: **el agente
no se vuelve más inteligente por tener la skill**. Lo que cambia es que tiene
los números medidos de este repo y los scripts que los verifican. Esos números
salen de un censo de las 22.394 mallas del juego: **ningún chat los tiene de
memoria**, y si le preguntás sin la skill te los va a inventar, con seguridad.

## El camino, paso por paso

En el Camino A, del pedido a la IA hasta el ítem en el inventario. Vos hacés
los pasos 0, 1 y 10; el agente corre los del medio.

| # | Qué | Con qué | Cómo sabés que salió |
|---|---|---|---|
| 0 | probar el taller | `examples/escudo-minimo/correr.py` | sale 0 (o 3, y sabés por qué) |
| 1 | pedirle el modelo a la IA | `references/pedir-a-la-ia-3d.md` | tenés un `.glb` |
| 2 | medirlo | `medir_parte.py` | el informe dice cuánto mide, en cm |
| 3 | soldarlo y llevarlo al presupuesto | `preparar_parte.py` | entra en los presupuestos medidos. Si tenés paneles planos, `--planar` |
| 4 | desplegar las UV | `desplegar_uv.py` | **un** atlas, sin islas pisadas |
| 5 | enderezar líneas que ondulan (si las hay) | `enderezar.py --marcadas` | primero **sin** `--aplicar`: te dice qué haría |
| 6 | hornear la capa HD (si la querés) | `hornear.py` | los mapas salen con sus controles |
| 7 | exportar el NIF | `exportar_nif.py` | el archivo existe y se puede releer |
| 8 | verificarlo | `verificar_export.py` | pasa sobre **el archivo**, no sobre la escena |
| 9 | que se pueda equipar | `census/escritor_plugin.py` + `verificar_plugin.py` | los registros ARMO/ARMA |
| 10 | probarlo en el juego | vos | una captura |

Los pasos 9 y 10 son de la otra skill del repo,
[`skills/asset-nuevo-skyrim/`](../../asset-nuevo-skyrim/SKILL.md): un NIF solo no
se equipa, hace falta el plugin que le dice al motor que existe.

Para que aparezca en una partida, la consola del juego: `help "<nombre>" 4 ARMO`
y después `player.additem <número> 1`.

## "Veo esto" → "corro aquello"

Cuando algo sale mal, casi nunca falla con un error: falla en silencio. Esta es
la traducción de lo que ves a lo que hay que correr. El número es la trampa en
`references/trampas.md`, que tiene el detalle y el arreglo.

| Lo que ves | Qué es | Qué correr |
|---|---|---|
| Se ve **invisible**, o solo de un lado | cáscaras abiertas + backface culling (trampa 6) | `salud_malla.py`, y cerrar la cáscara |
| Entra **mirando al revés** | el modelo entra mirando a −Y (trampa 2) | `al_marco.py` |
| Está **en el suelo, flotando o atravesado** | afinarlo sin medir el espacio del nodo (trampa 34) | `al_marco.py`, y medir antes de mover |
| Las **texturas se ven desordenadas o pisadas** | el empaquetado corrió en vacío, o dos objetos comparten atlas (trampa 17) | `desplegar_uv.py` |
| El **metal se ve negro** | horneaste el albedo con `DIFFUSE` (trampa 31) | `hornear.py` |
| Se ve **gris y plástico** en vez de metálico | PyNifly deja el material en `Default` y glossiness 20 (trampa 36) | `material_arma.py` |
| **Pesa muchísimo** y el juego va lento | el decimado se topa con un piso (trampa 7) | `preparar_parte.py --planar` |
| **No aparece en el inventario** | falta el plugin, o el `ARMO` está mal | `verificar_plugin.py` |
| **Se equipa pero no se ve** | es otro bug, en otro archivo (el NIF y el plugin son dos) | `verificar_export.py` |
| Blender dijo **"todo bien" pero el archivo no está** | Blender sin interfaz sale con 0 aunque el script reviente (trampa 37) | mirá el archivo, no el código de salida |

## Cuándo terminaste

Cuando el paso 8 pasa y el 9 también. Pero la regla honesta de este repo, que
conviene tener presente: **un asset puede pasar todos los controles y verse
feo**. Los controles verifican que el archivo está bien hecho, no que quedó
lindo. La última palabra la tiene una captura en el juego.

## Tres cosas que NO tenés que hacer

1. **No empieces por `pipeline/runner.py`.** Es un framework a medio conectar:
   5 de sus 9 fases son stubs declarados como tales, y su gate impide publicar
   **por diseño**. Vas a llegar a "no puede publicar" y no es un bug tuyo. El
   camino de este documento usa las dos skills y los scripts, no el runner.
2. **No le creas al código de salida de Blender** (trampa 37). Verificá el
   archivo.
3. **No subas nada de Bethesda.** Podés trabajar sobre tu copia del juego; no
   redistribuir sus mallas ni sus texturas.

## Si te trabás

En este orden, que es de lo más barato a lo más caro:

1. **Corré el ejemplo otra vez** (paso 0). Si sale 0, el taller está bien y el
   problema es de tu modelo.
2. **Buscá tu síntoma en la tabla de arriba** y corré lo que dice esa fila.
3. **Pegá el informe del script**, tal cual sale. Los informes están escritos
   para leerse: dicen qué midieron y qué no pudieron medir.
4. Si el agente te da un número que **no** sale de un informe, pedile que lo
   mida. Un número inventado con seguridad es el error más caro de todos — es la
   razón por la que existe este repo.
