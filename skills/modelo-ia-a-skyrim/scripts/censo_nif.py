# -*- coding: utf-8 -*-
"""Semilla para censar el corpus vanilla de Skyrim SE. Python puro, sin Blender.

Helper reducido / legado de la skill. La fuente de verdad del censo es
census/parser_nif.py (no importarlo desde aca: build_skill.py no empaqueta
census/). Este archivo se queda en la skill para --autotest y mediciones
de cabecera cuando se instala solo el .skill.

Parsea la cabecera de un NIF y expone lo que hace falta para medir miles de
archivos: tabla de tipos de bloque, offsets, tabla de strings, jerarquia de
nodos con posiciones de mundo, BSXFlags, conteo de triangulos y rutas de
textura.

QUE ESTA VERIFICADO Y QUE NO

Lo que hay aca se comprobo contra seis archivos vanilla cuyos valores se
conocian de antemano (correr --autotest). Todo lo demas que el censo necesita
--colision bhk*, particiones de body-part, pesos por vertice, flags de
shader-- NO esta implementado a proposito. Escribir esos parsers de memoria es
exactamente como se meten los errores que despues no dan error.

Para agregar un campo nuevo, el orden correcto es:
  1. Elegir un archivo donde YA SEPAS la respuesta (abrilo en NifSkope).
  2. Escribir el parser.
  3. Agregar el caso a AUTOTEST con el valor esperado.
  4. Recien entonces correrlo sobre el corpus.

HALLAZGO QUE CAMBIA EL CENSO

En SSE, un BSTriShape SKINNEADO no lleva la geometria adentro: numTriangles=0,
numVertices=0, dataSize=0. La geometria vive en el NiSkinPartition. Los
estaticos si la llevan inline. Medido:

  dwarvenshield.nif          estatico   1 shape    1.612 tri inline
  soulgemgreater01.nif       estatico   1 shape      316 tri inline
  dwarvensteamcenturion.nif  estatico   1 shape    6.154 tri inline
  steamcenturion.nif         SKINNEADO 15 shapes       0 tri inline

Contar triangulos de la forma obvia devuelve CERO para toda criatura y toda
armadura -- justo las clases que mas interesan. Por eso trishapes() reporta
"geometria_inline": sin esa marca, un censo de 40.000 archivos dice que la
mitad del juego no tiene poligonos y nadie se entera.

PENDIENTE #1 (el mas importante): triangulos de mallas skinneadas

No esta resuelto. Se intento leer NiSkinPartition asumiendo el layout
  numParticiones(u32) y luego por particion
  numVertices(u16) numTriangles(u16) numBones(u16) numStrips(u16)
  numWeightsPerVertex(u16)
y da basura: pesos-por-vertice = 1035 (el maximo real del motor es 4) y ese
1035 resulta ser un pedazo del vertexDesc del bloque anterior. O sea, el
offset de arranque esta mal para SSE.

No ajustes offsets hasta que salga el numero esperado: eso es ajustar ruido.
Saca el layout de nif.xml de NifSkope o de la libreria nifly, implementalo, y
falsificalo contra este valor conocido:

  steamcenturion.nif (el de ref/, NO el de out/) = 6.007 triangulos en total

Y contra estas dos cotas de sanidad, que atrapan el error de offset que tuve:
  - pesos por vertice <= 4 SIEMPRE
  - huesos por particion <= la cantidad de NiNode del archivo

Solo se valido con BS version 100 (Skyrim SE). Para Fallout 4 (BS >= 130) la
cabecera lleva un campo extra y BSTriShape cambia de layout: hay que volver a
falsificar antes de creerle nada.

Uso:
  python censo_nif.py --autotest <carpeta raiz del corpus>
  python censo_nif.py <archivo.nif> [<archivo.nif> ...]
  python censo_nif.py --censo <carpeta> --salida censo.jsonl
"""
import json
import os
import re
import struct
import sys

# Tipos que heredan de NiNode. BSFurnitureMarkerNode NO esta en la lista a
# proposito: pese al sufijo "Node", hereda de NiExtraData, no de NiAVObject.
# Incluirlo hace que se lea su contenido con el layout de NiNode y salga un
# conteo de hijos absurdo. Medido: 30 de 76 archivos de meshes/furniture/
# revientan con "unpack_from requires a buffer of at least 4093659953 bytes".
#
# El sufijo del nombre no dice de que hereda. Verificalo en nif.xml.
TIPOS_NODO = {"NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
              "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
              "BSBlastNode", "BSDamageStage", "NiBillboardNode",
              "NiSwitchNode"}
