# -*- coding: utf-8 -*-
"""Execution framework del pipeline de assets.

Capa nueva sobre el conocimiento y los verificadores existentes: no reemplaza
ni reimplementa `census/parser_nif.py`, `census/parser_dds.py` ni los scripts
de Blender de la skill; los invoca (en slices posteriores) como herramientas
externas verificadas.

Esta primera slice contiene únicamente:
  - JobManifest tipado e inmutable con validación de rutas (manifest.py);
  - staging aislado por job (staging.py);
  - runner con máquina de estados explícita (runner.py);
  - jerarquía de excepciones del pipeline (errors.py).

Sin Blender, BAE, TexConv ni PyNifly: los adaptadores reales llegan cuando los
contratos de los issues #2/#3 estén verificados. Relacionado con el issue #5
(configuración declarativa, hipótesis 2).

Convenciones del repo respetadas: stdlib pura, sin dependencias, sin src/
layout, tests con unittest en tests/.
"""
