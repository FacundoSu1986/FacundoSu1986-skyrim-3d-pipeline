---
name: asset-nuevo-skyrim
description: Crea un asset NUEVO y equipable para Skyrim SE — escudo, arma, pieza de armadura, clutter — desde el modelado en Blender hasta el plugin que lo registra. Usala cuando haya que hacer un item nuevo (no un replacer); cuando el item ya esté en el inventario pero no se equipe o sea invisible al equiparlo; cuando salga girado, flotando al costado del brazo o con el agarre lejos de la mano; cuando al soltarlo se hunda o salga volando; cuando haya que escribir, reparar o inspeccionar records ARMO/ARMA o WEAP de un .esp; cuando un arma pese 0 o haga 0 de daño con el valor bien, no se vea en primera persona o cuelgue envainada en el lugar equivocado; convertir un plugin a ESL, poner colisión Havok a un objeto suelto, o hacer un panel transparente estilo vidrio de Skyrim. También cuando el mod no aparezca con `help "..." 0`, o cuando haya que decidir qué campos llenar en el Creation Kit.
compatibility: Blender 4.4 con PyNifly (io_scene_nifly) para modelar y para exportar_nif.py, que escribe el NIF con la API del addon. Los demás scripts de la skill (plugin, ESL, colisión, nodos) son Python 3.11 o 3.12 sin nada fuera de la biblioteca estándar. Para copiar los valores del vanilla hacen falta Skyrim.esm y los NIF vanilla extraídos del juego, y el repo no los trae. Todo se midió sobre Skyrim SE.
metadata:
  inputs: un modelo en Blender, propio o salido de modelo-ia-a-skyrim, o un plugin .esp/.esl a revisar o reparar
  outputs: un NIF colgado del nodo de anclaje correcto, con su colisión, y un plugin ESL con los records ARMO/ARMA o WEAP que lo registran
---

# Un asset nuevo y equipable para Skyrim SE

Esta skill cubre la rama que `modelo-ia-a-skyrim` deja abierta cuando pregunta
"¿replacer o asset nuevo?". Un **replacer** hereda todo del vanilla y no necesita
plugin. Un **asset nuevo** es libre, pero a cambio hay que decirle al motor que
existe — y ahí es donde se pierde el tiempo.

## La idea que ordena todo lo demás

**Un asset nuevo se rompe en dos archivos distintos, y los síntomas no te dicen
en cuál.**

| | El NIF | El plugin (.esp) |
|---|---|---|
| Decide | cómo se ve, cómo cuelga, cómo choca | si el motor sabe que existe y a quién se lo pone |
| Se arregla con | Blender + PyNifly + parches binarios | records ARMO + ARMA |
| Síntoma típico | girado, invisible, se hunde, opaco | no aparece, no se equipa, armadura 0 |

"No se equipa" salió **tres veces** en el proyecto de origen con tres causas
distintas: una en el NIF (inercia cero → NaN de Havok), una en el plugin (ARMA
sin razas adicionales) y una que no era ninguna de las dos (el plugin no estaba
cargado). Antes de tocar nada, **separá de qué lado está el problema**. La tabla
de síntomas al principio de `references/trampas.md` es para eso.

## Tres clases de afirmación

Igual que en `modelo-ia-a-skyrim`, cada afirmación fuerte va etiquetada:
`[INVARIANT]` (propiedad del formato o del motor, permanente), `[PROVIDER]`
(cómo se comporta hoy PyNifly o el Creation Kit, caduca), `[OBSERVED]` (medido
una vez en `Escudo_Dwemer_SE_v01`, un caso).

**El error caro es promover un `[OBSERVED]` a `[INVARIANT]` y anunciar un bloqueo
que no existe.** Si una regla tuya te lleva a decir "esto no se puede", abrí
primero el archivo de Bethesda equivalente y contá.

## Lo primero, y lo que más caro sale saltearse

**La orientación del asset no la elegís vos: la fija el nodo de anclaje.**

Un escudo, un arma o cualquier cosa equipable que no se deforme **no se
skinnea**. Se cuelga de un nodo del esqueleto con un `NiStringExtraData` de
nombre `Prn` y valor el nombre del nodo (`SHIELD`, por ejemplo), y el motor
dibuja la malla **en el espacio local de ese nodo**. `[INVARIANT]`

Ese nodo tiene rotación propia, y **ningún nodo de anclaje del juego mira
al +Y**. Medido sobre los **116 marcos de anclaje** (`SHIELD`, `QUIVER`,
`WeaponSword`, `WeaponBack`, `WeaponAxe`, `WeaponBow`, `WeaponDagger`,
`WeaponMace`) de los **64 esqueletos** del corpus: **cero** caen a menos de 5°
de 90, y solo 2 de 116 (1,7 %) a menos de 10°. `[OBSERVED, 116 marcos]` Modelar
con el arriba en +Y —lo natural— produce un asset **girado en el juego** y
perfecto en Blender. Eso costó una sesión entera y una captura del juego.

En el esqueleto humano el `SHIELD` está a **155,7°**, y `skeletonbeast.nif` da
el mismo valor. Pero **155,7 no es una constante del juego**: de los 17
esqueletos que tienen `SHIELD`, da 155,7 en 4, 179,0 en 2, 151,3 en 2, 165,2 en
1, 95,7 en el `dwarvenspherecenturion`… `[OBSERVED, 17 esqueletos]` **Medí el
tuyo. No copies el número.**

Y hay un caso donde el ángulo **no significa nada**: en 4 de los 116 marcos —el
`SHIELD`, el `QUIVER` y el `WeaponBow` del `dwarvenballistacenturion`, más el
`SHIELD` del troll— el arriba del mundo cae sobre el eje Z **local** y su
proyección en el plano XY es 0,0000. `atan2(0,0)` devuelve 0,0, que parece una
medida y no lo es. El script lo dice en vez de imprimir el cero.

Antes de modelar un solo vértice:

```bash
python scripts/nif_nodos.py skeleton.nif --relativo-a "SHIELD" "NPC L Forearm [LLar]" "NPC L Hand [LHnd]"
```

Eso te da las dos cosas que necesitás: **cuánto gira el nodo**, y **por dónde
pasa la parte del cuerpo que tu asset tiene que tocar**. Ver
`references/nodo-de-anclaje.md`.

## El flujo

Pasos numerados, cada uno reejecutable solo y con su reporte JSON
(ver `modelo-ia-a-skyrim` y `README.md` del repo para la convención):

0. **Medir el vanilla equivalente** — extraerlo del BSA, volcar su NIF, anotar
   su envoltorio, su material de colisión, sus flags de alfa, su presupuesto de
   texturas. Y **medir el nodo de anclaje en el esqueleto**.
1. **Modelar** en el espacio local del nodo, con el giro ya compensado. Si
   el modelo viene de una IA, no se modela: se lleva ahí con `al_marco.py`
   de `modelo-ia-a-skyrim` y un plan JSON cuyos números salen de medir los
   vanilla de la clase (dónde cae el agarre, hacia dónde va el eje largo,
   hasta dónde llega el dorso).
2. **UV** + 3. **texturas** + 4. **materiales** (grupos de nodos de PyNifly, no
   Principled).
5. **Exportar el NIF** con `Prn`, `BSXFlags`, `BSInvMarker`, colisión y **tensor
   de inercia a mano**. `scripts/exportar_nif.py` lo hace con un **donante**
   vanilla de la misma clase: copia de él `Prn`, `BSXFlags`, el marcador, el
   cuerpo de la colisión y, de la pieza vanilla que se nombre, la receta del
   shader de cada pieza; calcula la caja, y relee el archivo antes de dejarlo.
6. **Verificar reimportando el archivo escrito**, no la escena.
7. **DDS** con texconv, BC7, mipmaps completos.
8. **Parches binarios** que PyNifly no puede hacer. El que se usaba para un
   vidrio, `BSOrderedNode` (trampa 12), **no hace falta**: ninguna de las 262
   piezas con *blending* de armaduras y armas vanilla cuelga de uno.
9. **Plugin**: ARMO + ARMA, con las razas adicionales copiadas del vanilla.
10. **Render de pose** — el asset ya colgado del nodo, con el hueso dibujado.
11. **ESL**, si el mod es chico.
12. **Armar e instalar** el mod.

## El plugin: estar en el inventario no es equiparse

Dos records como mínimo: **ARMO** (el objeto) y **ARMA** (qué malla, sobre qué
razas). El objeto aparece en el inventario con el ARMO solo; **equiparse depende
del ARMA**.

**`RNAM = DefaultRace` no alcanza** para algo que se equipa un humano. El
`DwarvenShieldAA` lista **23 razas adicionales** (subrecords `MODL` repetidos),
confirmado leyendo el `Skyrim.esm`. Sin esa lista el item se equipa "bien"
según el menú y **no se dibuja ni en primera ni en tercera persona**, sin un
solo mensaje.

Pero el 23 **no se copia, se mide**. De los **1.170 records `ARMA`** de los 10
plugins de una instalación SE:

| razas adicionales | cuántos `ARMA` | |
|---:|---:|---|
| 0 | 234 (20,0 %) | **todas criaturas**: esqueletos, gárgolas, chaurus. Ninguna es un escudo. |
| 1 | 232 (19,8 %) | |
| 23 | 215 (18,4 %) | el valor más común por encima de 1 |
| de 1 a 30 | 45 | los `ARMA` de escudo — y **ninguno en 0** |

`AurielsShieldAA` usa 30, `AtronachFrostShieldAA` usa 4,
`DLC1KeeperDragonplateShieldAA` usa 1. `[OBSERVED, 1.170 records]`

O sea: la regla no es "poné 23". Es **copiá la lista del vanilla equivalente**
leyendo el `Skyrim.esm` —que para un escudo humano nunca está vacía, y para una
criatura muchas veces sí—. No la escribas a mano. Ver
`references/plugin-armo-arma.md`.

El núcleo mínimo también está medido: **`EDID+RNAM+DNAM+BODT`** en el `ARMA`
(1 record vanilla lo demuestra; lo habitual es `EDID+RNAM+DNAM+MOD2+MODL+BODT`,
730 records), y **`EDID+OBND+RNAM+MODL+DATA+DNAM+BOD2`** en el `ARMO`, que
cumplen 3.905 de 3.915. Los otros 10 usan el `BODT` viejo en vez de `BOD2`.

**Y la cabecera de cada record lleva un `formVersion` que decide cómo se lee el
resto.** Con 0, el hacha de Tencent cargó, apareció en el inventario con el
valor correcto — y pesaba 0 y hacía 0 de daño. Tiene que ser **44**: los 10.273
records que Bethesda autoró para SE lo son, sin excepción. `[MEASURED]` Si el
plugin no sale de `census/escritor_plugin.py`, pasalo por
`scripts/verificar_plugin.py` antes de instalarlo. Ver
[trampa 23](references/trampas.md#23).

## Reproducir el juego fuera del juego

La malla se modela en el espacio local del nodo, y **en ese espacio no se ve
nada raro**: el render del `.blend` mostraba la decoración derecha y las correas
prolijas, y en el juego salía girada con las correas al aire.

El paso 10 arregla eso: toma la matriz de mundo del nodo de anclaje del
`skeleton.nif`, se la aplica a la malla y dibuja además el hueso relevante (el
antebrazo, como un cilindro entre codo y mano). Con eso, dos preguntas que antes
solo contestaba una captura del juego pasan a contestarse con un PNG:

- ¿la decoración queda derecha respecto del +Z del mundo?
- ¿las correas **cruzan** el hueso, o pasan por al lado?

Si estás haciendo un asset que se cuelga de un nodo, **escribí ese render antes
de la primera prueba en el juego**, no después de la tercera.

## Verificar sobre el archivo, no sobre la escena

Entre la escena de Blender y el archivo que carga el juego hay un exportador que
pierde cosas sin avisar. El último paso **reimporta el NIF escrito** y exige,
como mínimo:

- raíz `BSFadeNode` con el nombre correcto, `Prn` presente y apuntando al nodo;
- `BSXFlags` y marcador de inventario;
- colisión presente, con su forma, su material, y **diagonal de inercia > 0**;
- para paneles transparentes: `NiAlphaProperty` con flags de *blending* (4333, no
  4844: trampa 14) y, si la receta toma el alfa de los colores de vértice, ese
  alfa **no parejo en 1** —una capa uniforme en 1,0 es un panel opaco aunque
  el `NiAlphaProperty` esté perfecto— ni en 0, que es invisible. Un
  `BSOrderedNode`, no: el vanilla no lo usa para eso (trampa 12);
- **ausencia** de lo que no va: un escudo no tiene armadura ni particiones. Un
  chequeo que exige que algo NO esté atrapa el copiado por inercia desde un
  pipeline de criaturas.

**Y un chequeo tiene que poder fallar.** El validador del plugin del proyecto de
origen trae su propia suite de falsificación: le mete un plugin sin el flag de
escudo, sin tipo de equipo, con una referencia de tipo equivocado, con
`OBND` en cero, truncado, y con el tamaño de grupo mal — y exige que los rechace
a todos. Si nunca lo falsificaste, tu `[ok]` no significa nada.

## Trabajar sobre el trabajo de otro

En el proyecto de origen otro agente mejoró la forma y la textura mientras el
pipeline seguía vivo. Reejecutar el paso de texturas habría borrado su trabajo,
en silencio, y el pipeline habría dicho `ok`.

**Un pipeline reejecutable es incompatible con mejoras hechas a mano, salvo que
lo arregles a propósito.** Dos reglas:

- **Los pasos que generan un artefacto mejorable leen el archivo existente si
  está, en vez de regenerarlo.** El paso de texturas toma
  `tex_fuente/cara_color_mejorada.png` como *entrada* cuando existe. Así
  `python 03_texturas.py` es seguro de correr.
- **En el script de otro, tocá una línea y explicá por qué en un comentario.**
  Al convertir a ESL hubo que relajar una validación ajena que exigía
  `flags == 0`; el cambio fue una línea, con el motivo y el rango de FormIDs
  anotados al lado.

## Cuando hay juego, el bucle cambia

Poder probar en el juego es la diferencia entre adivinar y medir, pero cada
iteración cuesta minutos y una captura de pantalla. Para aprovecharla:

- **Pedí el síntoma exacto, no "no anda".** "Se equipa pero no se ve en primera
  ni en tercera" y "no aparece con `help`" son dos bugs distintos en dos archivos
  distintos.
- **Una captura vale por todo lo demás.** El giro de 66° y las correas al aire se
  vieron en una foto del juego y en ninguna medición.
- **Cuando el usuario marca algo en rojo sobre una captura, medí esa zona en el
  espacio del nodo antes de mover nada.** La primera corrección de las correas
  las subió en Z sin cambiar su eje, y siguieron sin tocar el brazo: estaban
  *paralelas* al antebrazo. El error no era la altura.

## Archivos de referencia

- **`references/nodo-de-anclaje.md`** — cómo se cuelga un asset del esqueleto,
  cómo medir el marco del nodo, dónde caen los huesos dentro de él, y cómo
  convivir con dos sistemas de coordenadas en la misma malla. **Leelo antes de
  modelar.**
- **`references/plugin-armo-arma.md`** — ARMO y ARMA campo por campo, qué se
  rompe sin cada uno, las razas adicionales, el layout binario del TES4, ESL, y
  el mapeo a los campos del Creation Kit. **Leelo antes de tocar el .esp.**
- **`references/plugin-weap.md`** — un **arma**: clonar un `WEAP` base de la
  misma clase, los nueve campos que cambian, el `STAT` de primera persona, el
  `Prn` por tipo de arma, el set de impactos y el `TES4`. Medido sobre las
  3.359 `WEAP` vanilla y probado en el juego con el hacha de Tencent. **Leelo
  antes de hacer un arma.**
- **`references/trampas.md`** — veinticinco fallos que no tiran error, con
  índice por síntoma. **Leelo entero antes de empezar**, no cuando algo falle.

## Scripts

- **`scripts/nif_nodos.py`** — parser binario de la jerarquía `NiNode`, sin
  dependencias. Da posiciones y ejes **del archivo**. Su modo `--relativo-a`
  expresa un nodo en el espacio local de otro y calcula hacia dónde queda el
  arriba del mundo: las dos medidas que hacen falta antes de modelar.

  Hace falta porque PyNifly, al importar, convierte los nodos en huesos de
  Blender, que tienen su propia convención de ejes (Y a lo largo del hueso). La
  matriz que sale de ahí es plausible y **no es la del archivo**.

  **Es el mismo archivo, byte a byte, que el de `modelo-ia-a-skyrim`**, y un
  test lo exige. Cuando esta skill vivía fuera del repo su copia ya había
  divergido: decidía qué es un nodo con `tipo.endswith("Node")` —la trampa de
  `BSFurnitureMarkerNode`, que termina en "Node" y hereda de `NiExtraData`— y
  se había quedado sin el arreglo de `BSMasterParticleSystem`. Medido: de 40
  archivos MPS del corpus, **39** daban un juego de nodos distinto al del
  lector validado.

  `--autotest <carpeta meshes>` reproduce 16 valores medidos sobre cuatro
  esqueletos, incluidos el contraejemplo del ángulo y el caso degenerado. Sin
  corpus devuelve 1, no 0.
- **`scripts/esl.py`** — informa y, si se lo pedís, marca o desmarca el flag ESL.
  Por defecto **no escribe**. Comprueba el rango de FormIDs antes de marcar,
  deja `.bak`, y avisa de la consecuencia en las partidas guardadas.

  **Y falla cerrado**, que antes no hacía. Fallaba *abierto*: un plugin
  truncado 30 bytes hacía que el recorrido viera 1 record en vez de 2; con un
  record menos no había ninguno fuera de rango, y `--marcar` **escribía el flag
  y salía con exit 0**. La comprobación que existe para que no corrompas tu mod
  pasaba justo porque no había mirado el record que tenía que mirar. Ahora, si
  el recorrido no cierra en el fin del archivo, no escribe nada.

  `--autotest <carpeta Data>` reproduce el conteo de records de 6 plugins. Su
  recorrido y el de `census/parser_esm.py` dan el **mismo número en los 10**
  plugins de una instalación: 1.188.811 records.
- **`scripts/colision_caja.py`** — comprueba las cajas de colisión de un NIF
  contra lo que hace el corpus. Dos REGLAS: `bhkRadius == min(semieje menor,
  0,1)` (2.667 de 2.684) y **masa > 0 ⟺ diagonal de inercia > 0** (1.194 de
  1.194, en los dos sentidos).

  Lo que **no** exige importa tanto como lo que exige: no hay fórmula para el
  **valor** de la inercia —contra `m(a²+b²)/12` la razón va de 1,2 a 471 y solo
  1 de 2.433 ejes cae dentro del ±10 %—, así que la informa como OBSERVACIÓN.
  Y el radio **sin** el tope de 0,1 parecía regla sobre armas (62 de 62) y es
  falsa sobre el corpus (73,25 %).

  `--autotest` y `--falsificar <carpeta meshes>`, que tuerce cuatro campos de
  cajas vanilla reales y exige que el control las pesque.
- **`scripts/verificar_plugin.py`** — lee un `.esp`/`.esl` **terminado** y
  reprueba lo que el juego lee mal sin avisar. Siete REGLAS: **`formVersion
  == 44`** en cada record (10.273 de 10.273 en los plugins autorados para SE),
  **índice de mod ≤ cantidad de masters** (1.188.810 de 1.188.811; la
  excepción es un `GMST` sucio de `Skyrim.esm`), en cada **`WEAP`** `DATA` de
  10 bytes, `DNAM` de 100 y un `WNAM` que apunte a un `STAT` existente (3.359
  de 3.359 `WEAP` vanilla pasan), y el **`Prn`** del NIF según el tipo de arma
  (305 de 306 armas del jugador; los bastones son observación). Para el `Prn`
  busca el NIF en `meshes/` al lado del plugin: corrélo sobre la carpeta del
  mod. Y tres del mundo ([trampa 25](references/trampas.md#25)): una
  **referencia colocada** en un grupo 8 lleva `0x400` y en uno 9 no (59.240 y
  820.513 de 879.753, cero excepciones); cada entrada del **`OFST`** de un
  `WRLD` cae dentro del archivo (76.250 de 76.250); y en un plugin **no
  localizado** cada `FULL` es texto, no un ID de 4 bytes. Un override de
  `WRLD` con `RNAM` es observación (10 de 45 overrides oficiales lo llevan).

  Es para **tu** plugin. Pasado sobre `Skyrim.esm` reprueba 1,1 millones de
  records que el juego carga perfecto: los masters de 2011 conservan la versión
  de la última edición de cada record, y por eso el corpus entero da 7,65 % en
  44. Medir ahí invierte la regla.

  Usa el recorrido de `esl.py`, no uno propio. Los subrecords los lee con una
  copia del lector de `census/parser_esm.py` —la skill no puede importar
  `census/`—, y un test ata las dos lecturas sobre los mismos bytes, con `XXXX`
  y con zlib. `--autotest` (292 casos) y `--falsificar <carpeta Data>`, que
  tuerce un record de cada plugin autorado para SE a 0, 39, 45 y a un índice
  de mod inexistente, y un `WEAP` real a `DATA` de 12, `DNAM` de 96 y un
  `WNAM` a la nada; y sobre los 10 plugins, masters incluidos, mide las
  referencias (cero excepciones), le saca la bandera a una del grupo 8 y se
  la pone a una del 9, le mete al `OFST` una entrada fuera del archivo y
  juzga una `FULL` localizada como si el plugin no lo fuera. `--falsificar-prn <carpeta Data> <carpeta meshes>` le pone
  a cada arma base real cada `Prn` equivocado: 324 armas, 1.944 roturas.
- **`scripts/exportar_nif.py`** (Blender) — el paso 5 con un plan JSON: cada
  pieza es un objeto del `.blend` y copia la receta de shader de una pieza
  vanilla (el metal de un arma, el brillo de una pieza con Glow Shader: dos
  piezas, porque ninguna vanilla combina mapa de entorno y de brillo). Del
  donante copia `Prn`, `BSXFlags`, `BSInvMarker` y los 63 campos del cuerpo
  rígido. Escribe con la API de PyNifly, no con su exportador (el camino de
  las armas que se vieron en el juego), a un temporal que relee con PyNifly
  y con `nif_nodos.py`, y pasa por las REGLAS de `colision_caja.py` antes de
  reemplazar el definitivo. Una pieza transparente copia la `NiAlphaProperty`
  de su receta; si la receta toma el alfa de los colores de vértice, exige la
  capa `VERTEX_ALPHA` y que no quede pareja en 1 ni en 0 (trampa 16); pareja
  en otro valor pasa con una nota, y un alfa pintado que la receta no usa
  también deja nota. No escribe `BSOrderedNode`: medido, el vanilla no lo usa
  para transparencia.
  `--falsificar` arma un donante sintético con PyNifly, sin archivos del juego.
- **`scripts/exportar_puro.py`** — lo de ese export que no necesita Blender,
  con `--autotest`: el plan, la soldadura con la V invertida y el tope de
  65.535 vértices, la caja y la inercia, los flags que dependen de la
  geometría de la pieza vanilla y qué texturas se copian de la receta
  (solo el cubemap).
- **`scripts/correr_en_blender.py`** — que un script de Blender que revienta no
  salga con 0. Es el mismo archivo que el de `modelo-ia-a-skyrim`, byte a byte,
  y un test lo exige.

## Cómo conviene trabajar

**Medí el vanilla, no leas la wiki.** Todo lo que este pipeline sabe de flags de
alfa, materiales de colisión, tensores de inercia y razas adicionales salió de
abrir un archivo de Bethesda y mirarlo. Los valores de Havok en particular **no
son la fórmula de libro**: copiarlos de un objeto equivalente funciona,
calcularlos no.

**Dimensioná cada textura por su contenido, no todas a 2048.** En un Skyrim muy
modeado el cuello de botella es la VRAM, no los triángulos. Bajar la máscara a
512 y el panel y las gemas a 256 llevó el asset de 17,30 MB a 11,38 MB (−34 %),
el mismo presupuesto que el vanilla pero con más detalle. `[OBSERVED]`

**Antes de decir "esto no se puede", comprobalo contra un archivo real.** Un
bloqueo inventado manda a la otra persona a rediseñar. Un bug, no.
