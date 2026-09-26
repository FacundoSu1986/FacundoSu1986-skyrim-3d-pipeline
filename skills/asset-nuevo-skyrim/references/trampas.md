# Trampas: veinticuatro fallos que no tiran error

Casi todas se pagaron en `Escudo_Dwemer_SE_v01` (un escudo dwemer nuevo, con
panel transparente, para Skyrim SE); la [4b](#4b), la [23](#23) y la [24](#24)
salieron del hacha de Tencent. **Ninguna tira excepción.** El pipeline termina `ok`, el mod
se instala, y el problema aparece mirando el archivo escrito o probando en el
juego.

Leelas **antes** de empezar. Varias solo se descubren jugando, y para entonces
ya perdiste la iteración.

## Índice por síntoma

Empezá acá. La primera columna es lo que ve el jugador.

| Síntoma | Trampa |
|---|---|
| **En el juego** | |
| Está en el inventario, dice "equipado", y no se dibuja | [1](#1), [4](#4) |
| `help "nombre" 0` no devuelve nada | [2](#2) |
| Se equipa y la armadura no sube | [3](#3) |
| El arma pesa 0 y hace 0 de daño, y el valor sale bien | [23](#23) |
| El arma envainada cuelga en otro lado (la cadera, la espalda) | [24](#24) |
| Al soltarlo sale volando y se hunde en el piso | [4](#4) |
| Sale girado un ángulo raro | [5](#5) |
| Las correas / el agarre quedan lejos del brazo | [6](#6) |
| Queda flotando al costado del cuerpo | [7](#7) |
| No bloquea golpes, no suena como escudo | [8](#8) |
| Se ve de canto en el menú de inventario | [9](#9) |
| El panel transparente sale opaco | [14](#14), [15](#15), [16](#16) |
| Partes que deberían ser opacas salen invisibles | [16](#16) |
| El vidrio se dibuja por delante de lo que tiene detrás | [12](#12) |
| **En el archivo** | |
| El NIF no tiene un solo bloque `bhk` y el export dijo OK | [10](#10) |
| Hay `bhkCollisionObject` pero sin cuerpo ni forma | [11](#11) |
| "Export of nif failed" al exportar la colisión | [11](#11) |
| El NIF carga en LE y no en SE | [13](#13) |
| El PNG de textura sale negro entero | [17](#17) |
| El DDS desaparece después de generarse | [18](#18) |
| **Proceso** | |
| Una mejora hecha a mano desapareció al reejecutar | [19](#19) |
| El ESL carga pero el objeto sale corrupto | [20](#20) |
| El arreglo funcionó y al rato volvió el bug | [21](#21) |
| "LZ4: referencia fuera del buffer" al extraer texturas | [22](#22) |

---

## El plugin

### 1. Un ARMA sin razas adicionales no dibuja nada {#1}

`RNAM = DefaultRace` no alcanza. Hace falta además la lista de subrecords `MODL`
con las razas adicionales — el `DwarvenShieldAA` vanilla tiene **23**. Sin ella
el objeto se equipa según el menú y **no aparece ni en primera ni en tercera
persona**. El Creation Kit no avisa si la lista está vacía.

→ Copiar la lista del vanilla equivalente leyéndola del `Skyrim.esm`.

### 2. `help` vacío significa "plugin no cargado", no "NIF roto" {#2}

Si `help "nombre" 0` no devuelve nada, el problema no está en la malla ni en el
ARMA: el juego ni siquiera cargó el plugin. Tildado en el gestor de mods, ruta
correcta, master resoluble. Perseguir el NIF acá es tiempo perdido.

### 3. `Clothing` da 0 de armadura, y se equipa perfecto {#3}

La clase está en el **segundo dword de `BOD2`** (`0` Light, `1` Heavy, `2`
Clothing), no en el `DNAM`. Un escudo que quedó como *Clothing* funciona en todo
salvo en que no protege. Se confunde con un problema de balance.

### 23. `formVersion = 0` deja el peso y el daño en cero, y el valor bien {#23}

La cabecera de cada record lleva en los bytes 20-21 un `formVersion`, y el motor
**lee el resto del record con el layout de esa versión**. El `.esl` del hacha
salió con 0 en sus tres records: el plugin cargó, el arma apareció en el
inventario, el VALOR se leyó bien — y el PESO y el DAÑO salieron en **0**. Con
44, el mismo record dio peso 27 y daño 26, confirmado en el juego.

Parece de balance, o de un campo mal copiado del donante. No es ninguna de las
dos: el `DATA` está bien, lo que está mal es cómo se lo lee.

`[MEASURED]` Los 5 plugins que Bethesda autoró para SE: **10.273 de 10.273**
records en **44**. Y 44 es el máximo de todo el corpus.

**Ojo al medirlo.** Sobre los 10 plugins solo el **7,65 %** está en 44 y el
valor más común es el 39. Los masters de 2011 llevan, record por record, la
versión de la última vez que alguien lo tocó. Es la misma trampa que la
[4b](#4b): el subconjunto equivocado invierte la respuesta.

→ `census/escritor_plugin.py` ya escribe 44. Si armás los bytes a mano, o el
plugin viene de otra herramienta: `scripts/verificar_plugin.py MiMod.esl`.

### 24. Dónde cuelga el arma envainada lo decide el NIF, no el plugin {#24}

El `WEAP` dice qué arma es (`DNAM[0]`: espada, hacha, arco…) pero el nodo del
esqueleto del que cuelga cuando no está en la mano sale del NIF: un
`NiStringExtraData` llamado `Prn`. Nada en el plugin lo corrige: con el `Prn`
de otro tipo, el arma se cuelga del nodo de ese otro tipo. (Lo confirmado en
el juego es el caso bueno: el hacha, con `WeaponBack`, cuelga en la espalda.
Un `Prn` equivocado no se probó jugando.)

`[MEASURED]` El `Prn` sigue al tipo en **305 de 306** armas vanilla del
jugador: `WeaponBack` para las de dos manos, `WeaponSword`, `WeaponAxe`,
`WeaponMace`, `WeaponDagger` para las de una mano, `WeaponBow` para arcos y
ballestas. Los bastones no tienen regla. Tabla completa en
[`plugin-weap.md`](plugin-weap.md).

→ Copiá el `Prn` del NIF del donante. Y `scripts/verificar_plugin.py`, corrido
sobre la carpeta del mod, compara el `Prn` del NIF con el tipo del plugin.

## La colisión

### 4. Sin tensor de inercia, Havok da NaN — y eso es *dos* bugs {#4}

PyNifly **no calcula el tensor de inercia** y **no lo deriva del rigid body de
Blender**: el `bhkRigidBodyT` sale sin `inertiaMatrix`, o sea inercia cero. En
el juego eso da NaN, y NaN produce dos síntomas que parecen no tener nada que
ver entre sí:

- al soltarlo, **sale volando y se hunde** en el piso;
- al equiparlo, **es invisible** (la posición NaN lo saca de cuadro y el motor
  lo descarta).

Perseguir el segundo síntoma por el lado del esqueleto o del ARMA no lleva a
ningún lado.

→ Poner `col["inertiaMatrix"]` a mano (matriz 3×4, diagonal en los índices
0/5/10). **Los valores de Havok no son la fórmula de libro `(m/12)(a²+b²)`** ni
un escalado simple: copiar los de un objeto vanilla equivalente.

**Corrección (medido, corpus entero).** Este párrafo decía "el paso de
verificación tiene que exigir diagonal > 0", y así escrito **rechaza a
Bethesda**: 383 de los 1.194 cuerpos con caja del corpus —el 32 %— tienen la
diagonal en cero. La condición real es un bicondicional:

> `[MEASURED]` **masa > 0 ⟺ diagonal > 0**. Con masa 0, inercia cero en **383
> de 383**; con masa > 0, inercia cero en **0 de 811**. Sin excepciones en
> ninguno de los dos sentidos.

Un cuerpo de masa 0 es inamovible y su inercia en cero es correcta. El NaN
aparece cuando hay masa **y** no hay inercia, que es lo que deja PyNifly.

Y el **valor** de la inercia no se puede exigir: `[MEASURED]` contra
`m(a²+b²)/12` la razón va de 1,2 a 471 con mediana 7,1, y solo 1 de 2.433 ejes
cae dentro del ±10 %; las proporciones entre ejes tampoco (3,6 % dentro del
10 %). Adaptar la del donante escalándola por la fórmula es una **heurística**,
no una regla.

Lo comprueba `scripts/colision_caja.py`.

### 4b. El radio convexo de la caja también depende de la caja {#4b}

Mismo modo de falla que la inercia: se copia del donante y queda un radio que
no corresponde a esta forma.

`[MEASURED]` **`bhkRadius == min(semieje_menor, 0,1)`** en **2.667 de 2.684**
cajas del corpus (99,37 %), exacto. Las 17 excepciones son volúmenes de trampa
y de marcador.

**Ojo con la versión sin el tope.** Medida solo sobre armas, "bhkRadius es el
semieje menor" daba **62 de 62** y parecía regla; sobre el corpus entero es
**73,25 %**. Un arma es fina y su semieje menor casi siempre cae debajo de 0,1,
así que el subconjunto no podía mostrar el tope.

### 5. Un asset colgado de un nodo sale girado lo que esté girado el nodo {#5}

Ver `nodo-de-anclaje.md`. El `SHIELD` del esqueleto humano tiene el arriba del
mundo a **155,7°** en su plano local: modelar con el arriba en +Y da un escudo
girado **66°**. En Blender se ve perfecto.

### 6. Modelar el agarre a lo largo del hueso en vez de cruzándolo {#6}

En el espacio local del `SHIELD` el antebrazo corre a lo largo de **X**, pegado
a y=0, de z=7,2 (codo) a z=0,16 (mano). Correas a lo largo de X son *paralelas*
al brazo y no lo tocan. Tienen que ir a lo largo de **Y**, repartidas sobre X.

Y cuidado con el falso arreglo: subirlas en Z no sirve si el eje está mal. En el
proyecto de origen se perdió una iteración entera corrigiendo la altura de algo
cuyo problema era la dirección.

### 7. Envoltorio distinto del vanilla = flota al costado {#7}

La malla se dibuja en el espacio local del nodo. Si no ocupa aproximadamente el
mismo volumen que el vanilla, queda desplazada del cuerpo. Medí el vanilla y
construí adentro de esa caja. Esto también alimenta el `OBND`, que **no puede
quedar en cero**.

### 8. El bit de escudo va en la cabecera del record, no en un subrecord {#8}

Flag **`0x40`** en la cabecera del ARMO. Sin él, el objeto se equipa y se ve
pero no bloquea ni suena como escudo.

### 9. El marcador de inventario es otra cosa {#9}

`BSInvMarker` (rotación en centésimas de grado + zoom) solo afecta la vista del
menú. Si la pieza se ve de canto en el inventario y bien en la mano, es esto —
no el `Prn`.

### 10. La colisión necesita un CABLE, y sin él no se escribe nada {#10}

PyNifly la encuentra por una restricción `COPY_TRANSFORMS` en el nodo objetivo
apuntando al objeto de colisión, o por la propiedad `pynCollisionTarget`
(`nif/collision.py`, `export_collisions`). Sin eso el archivo sale **sin un solo
bloque `bhk`** y el export dice OK.

### 11. Y además necesita un Rigid Body de Blender {#11}

Primera línea de `export_collision_body`: `if not coll.rigid_body: return`. Con
el cable puesto pero sin Rigid Body, el archivo sale con el `bhkCollisionObject`
**huérfano** — sin cuerpo ni forma — que es peor que no tener nada, porque
parece que hay.

**Y el tipo de forma se elige por el NOMBRE del objeto** (`bhkBoxShape`,
`bhkConvexVerticesShape`, …, lista en `collision_names`). Con otro nombre el
export revienta con "Export of nif failed" — que al menos sí avisa.

## El NIF

### 12. PyNifly no puede escribir `BSOrderedNode` {#12}

`addBlock` fija el tipo solo por el `bufType`, y `BSOrderedNode` comparte
`NiNodeBufType` con `NiNode`. El único lugar que toma el tipo por nombre es
`createNif`, y solo para la raíz. Un `EMPTY` con `pynBlockName=BSOrderedNode` se
escribe como `NiNode` común, **sin aviso** — y el orden de dibujo del alfa se
pierde.

→ Parchear el binario: agregar el tipo a la tabla de la cabecera, reapuntar el
índice de tipo del bloque, y anexarle los **17 bytes** que `BSOrderedNode` tiene
de más sobre `NiNode` (`NiBound` 16 B + bool `Static Bound` 1 B). **El NIF
referencia bloques por índice, no por offset**, así que retipar y redimensionar
un bloque es una operación local y segura. Verificalo reimportando: PyNifly sí
sabe *leer* `BSOrderedNode`.

**Pero para un vidrio no hace falta.** `[MEASURED]` En 2.148 NIF vanilla de
armaduras y armas hay 262 piezas *Lighting* con *blending*: 234 cuelgan de la
raíz, 28 de un `NiNode` y **ninguna** de un `BSOrderedNode`. El único de esas
carpetas, el de `dlc01/armor/dwarven/1stpersondwarvenshieldcrystal.nif`, no
tiene hijos (leído con `nif_nodos.py`). En el corpus entero aparece en 244 de
22.394 NIF, casi todos efectos y gemas. El escudo ovalado lo usó y se vio bien
en el juego: no molesta, pero no es lo que hace el vanilla, y
`scripts/exportar_nif.py` cuelga las piezas transparentes de la raíz. Detalle
en la entrada 44 de `census/hallazgos.md`.

### 13. El `target_game` por defecto es `SKYRIM` (LE), no `SKYRIMSE` {#13}

Exportar con los valores por defecto da un NIF de la edición equivocada.

## Alfa y texturas

### 14. `4844` es alpha *testing*: el panel sale opaco {#14}

Decodificación de `NiAlphaProperty.flags`: bit 0 = blending activado, bits 1–4 =
modo origen, bits 5–8 = modo destino, bit 9 = testing activado, bits 10–12 =
función de test.

- **`4333` (0x10ED)** = blending real, `SRC_ALPHA / INV_SRC_ALPHA`. Es lo que
  hace falta para ver a través de un panel.
- **`4844` (0x12EC)** = alpha *testing*. Sirve para recortar una rejilla o unas
  hojas, no para transparencia. Con esto el "vidrio" se dibuja opaco.

Copiar el número de un vanilla cualquiera no alcanza: hay que copiarlo de uno
que haga **lo mismo** que querés. (El del astrolabio dwemer sirve; el cristal de
Dawnguard, no.)

### 15. PyNifly no exporta `NiAlphaProperty` con un Principled BSDF {#15}

`_export_alpha` busca una entrada `'Alpha Property'` en el nodo que alimenta la
salida del material, y si no la encuentra se va sin escribir nada. El Principled
no tiene esa entrada.

→ Armar el material con los grupos de nodos del addon
(`blender_assets/Shaders.blend`: `SkyrimShader:Default` + `AlphaProperty`).

### 16. El alfa por vértice va en una capa aparte, y su ausencia vale 0 {#16}

PyNifly **no lee el alfa del cuarto canal** de la capa de color. Busca una capa
llamada exactamente `VERTEX_ALPHA` y promedia su RGB (`find_colormaps` /
`extract_colors` en `nif/export_nif.py`). Con el alfa en `Col.a` escribe colores
pero todos opacos.

Y la vuelta de tuerca: **un nodo `Attribute` que apunta a una capa inexistente
devuelve 0, no 1**. Así que las mallas **opacas** también necesitan su capa
`VERTEX_ALPHA` en blanco, o se vuelven invisibles.

El chequeo que atrapa esto es exigir que el alfa por vértice **no quede parejo
en 1**: una capa uniforme en 1,0 es un panel opaco aunque el `NiAlphaProperty`
esté perfecto. Parejo en 0 es invisible. Parejo en un valor intermedio es otra
cosa, una transparencia pareja: `exportar_nif.py` la deja pasar con una nota.
Que las piezas vanilla con alfa por vértice lo tengan variando es una
observación, no un límite del motor.

### 17. Asignar el colorspace después de escribir los píxeles vacía la imagen {#17}

`img.colorspace_settings.name` invalida la imagen y la regenera desde
`generated_color` (negro). Pasa **incluso asignando el mismo valor que ya
tenía**. El PNG sale negro entero, sin aviso.

→ Fijar el espacio de color *antes* de `pixels.foreach_set` y no volver a
tocarlo. Para cambiarlo, guardar y recargar el archivo desde disco.

### 18. En Windows `.DDS` y `.dds` son el mismo archivo {#18}

Una lógica de "borrar el destino antes de generar" que compara rutas con
`os.path.exists` termina **borrando el archivo recién creado** por texconv,
porque el sistema de archivos no distingue mayúsculas y tu comparación de
strings sí.

→ Comparar con `os.path.normcase`.

## Proceso

### 19. Reejecutar el pipeline pisa las mejoras hechas a mano {#19}

Un pipeline reejecutable y un retoque manual son incompatibles salvo que lo
arregles a propósito. El paso que *genera* un artefacto mejorable tiene que
**leer el archivo existente si está**, en vez de regenerarlo. Si no, `python
03_texturas.py` borra en silencio el trabajo de otra persona y reporta `ok`.

### 20. Un FormID fuera de rango en un ESL no da error {#20}

Un ESL solo admite índices de objeto hasta `0xFFF` (12 bits en el espacio
`FE:xxx`). Por encima el motor **remapea** y el objeto sale corrupto o no sale,
sin mensaje. Comprobar el techo **antes** de encender el flag `0x200`.

El piso de `0x800` que aparece por todos lados es del Creation Kit, no del
motor: `_ResourcePack.esl` —que Bethesda distribuye— tiene **368 de 373**
records por debajo (`census/hallazgos_plugins.md`, entrada 10).

(Y avisar de la otra consecuencia: al pasar a `FE:XXX` cambian todos los
FormIDs, así que una partida guardada pierde el objeto.)

### 21. El archivo del proyecto y el instalado se desincronizan {#21}

Con un gestor de mods de por medio (la carpeta `overwrite` de MO2, por ejemplo)
hay dos copias del `.esp` y del NIF. Un arreglo aplicado a una de las dos
"funciona" y después vuelve el bug, o al revés: el arreglo se pierde al
reconstruir.

→ Una sola fuente de verdad en el proyecto, un paso explícito que despliega, y
el hash en el reporte.

### 22. Los BSA de texturas usan bloques LZ4 *enlazados* {#22}

El formato de frame LZ4 admite bloques enlazados (bandera de independencia en 0):
las referencias de un bloque pueden apuntar a datos del bloque anterior. Un
descompresor que arranca con un buffer nuevo por bloque revienta con "referencia
fuera del buffer". Los BSA de texturas de Skyrim los usan.

→ Un solo buffer de salida compartido entre bloques.

---

## La disciplina que atrapa las que faltan

Ninguna de estas tira excepción, así que ninguna se descubre "programando con
cuidado". Lo que las atrapa es otra cosa:

1. **Verificar sobre el archivo escrito, reimportándolo.** La escena de Blender
   confirma lo que armaste, no lo que se va a cargar.
2. **Exigir ausencias, no solo presencias.** "No tiene armadura ni particiones"
   atrapa el copiado por inercia desde otro pipeline.
3. **Exigir que los valores *varíen*** donde tienen que variar. Un alfa uniforme
   en 1,0 pasa cualquier chequeo de "existe la capa".
4. **Falsificar cada chequeo.** Alimentalo a propósito con datos malos y confirmá
   que revienta. Un chequeo que nunca falló no probó nada todavía.
5. **Renderizar la pose real**, con la transformada del nodo aplicada. Muchas de
   estas son invisibles en los números y obvias en una imagen.
