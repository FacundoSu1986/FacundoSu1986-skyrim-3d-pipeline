# Escudo mínimo: de una pieza de IA a un NIF verificado, sin el juego

Un caso de punta a punta, chico, que cualquiera puede correr **sin Skyrim**:
una "pieza de IA" (un GLB escrito por código, con los defectos típicos de lo
que devuelven Tripo o Meshy) pasa por los pasos de las dos skills del repo y
termina en un NIF de escudo que se verifica con lectores que no son el que lo
escribió.

```bash
python examples/escudo-minimo/correr.py --blender "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"
```

(o con la variable `BLENDER_EXE`). La salida queda en `examples/escudo-minimo/trabajo/`,
que git ignora y que cada corrida pisa; `--trabajo <carpeta>` la manda a otro lado.

## Qué necesita cada paso

| # | paso | script | necesita |
|---|---|---|---|
| 0 | la pieza de IA: una placa de 0,75 × 1 × 0,06, 12 triángulos | `pieza_ia.py` | Python |
| 1 | medirla | `modelo-ia-a-skyrim/scripts/medir_parte.py` | Blender |
| 2 | soldarla y ponerle presupuesto | `modelo-ia-a-skyrim/scripts/preparar_parte.py` | Blender |
| 3 | llevarla al marco del nodo `SHIELD` | `modelo-ia-a-skyrim/scripts/al_marco.py` + `plan_marco.json` | Blender |
| 4 | el donante sintético | `asset-nuevo-skyrim/scripts/donante_sintetico.py` | Blender + PyNifly |
| 5 | exportar el NIF | `asset-nuevo-skyrim/scripts/exportar_nif.py` + `plan_nif.json` | Blender + PyNifly |
| 6 | verificarlo | `nif_nodos.py`, `colision_caja.py` y los parsers de `census/` | Python |

**El juego no lo necesita ningún paso.** Blender (probado con 4.4) es
gratis; PyNifly es el addon de Blender que lee y escribe NIF, y se instala
aparte.

Sin Blender, `correr.py` hace el paso 0, saltea el resto diciendo qué falta y
sale con **3** ("incompleto"): un ejemplo a medias no se informa como un
éxito. Sale con 0 solo si corrieron los siete pasos y el NIF pasó la
verificación; con 1 si un paso que corrió falló.

## Qué comprueba el paso 6

Los números esperados salen de los dos planes, no de lo que dijo el export, y
ninguno de los lectores es PyNifly:

- con `nif_nodos.py`: la raíz es un `BSFadeNode` con el nombre del plan, el
  `Prn` es el del donante (`SHIELD`) y están el `BSXFlags`, el marcador de
  inventario y la colisión;
- con `colision_caja.py`, la librería y el comando: una caja, con las REGLAS
  de la colisión vanilla y la inercia mayor que cero;
- con los parsers de `census/`, la geometría en el espacio de la raíz: la
  pieza del plan, sus 12 triángulos, el largo que pide el plan (56), el dorso
  en el tope (Z = 2,2) y el centro sobre el antebrazo (X = −14,8, Y = 0).

## En qué se diferencia de un asset de verdad

- **El donante.** En un asset real sale del juego extraído: un escudo vanilla
  de la clase, del que se copian el `Prn`, el marcador, el cuerpo rígido y el
  material de la colisión. Acá lo reemplaza `donante_sintetico.py`, un NIF
  hecho con PyNifly que tiene esa misma estructura pero ningún número medido.
- **La pieza.** Una placa, no un modelo de IA: no hace falta despliegue UV ni
  horneado, y el NIF apunta a texturas (`textures\ejemplo\...`) que no
  existen.
- **Los planes.** `plan_marco.json` usa la convención del nodo `SHIELD` que
  documenta `asset-nuevo-skyrim` (el antebrazo corre por X; el arriba del
  mundo cae a 155,7° en el plano XY; el dorso de los escudos vanilla, en
  Z = 2,2). Para un escudo de verdad esos números salen de medir el vanilla
  de la clase, y el largo, del modelo.

## Qué no comprueba

Que se vea bien, ni que el juego lo cargue: no se probó en Skyrim, y un NIF
bien formado con la geometría en su lugar no alcanza para afirmarlo. Tampoco
las texturas, que el ejemplo no hace.
