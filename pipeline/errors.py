# -*- coding: utf-8 -*-
"""Jerarquía de excepciones del execution framework.

Pequeña y deliberada: no un árbol por cada fase, solo las categorías que
cambian la respuesta del llamador (config inválida vs. herramienta rota vs.
artefacto inválido vs. publicación). Toda traducción de excepción debe usar
`raise ... from e` para preservar la causa.
"""


class PipelineError(Exception):
    """Base de todos los errores del execution framework."""


class ConfigurationError(PipelineError):
    """El JobManifest es inválido: no debe ni arrancar el job."""


class ToolNotFoundError(PipelineError):
    """Una herramienta externa requerida (BAE, texconv, Blender) no existe."""


class ToolExecutionError(PipelineError):
    """Una herramienta externa falló: exit code, timeout, salida ausente."""


class TexturaError(PipelineError):
    """Una textura de entrada no se pudo leer o no está en un formato que
    esta slice sepa convertir.

    No es ArtifactValidationError a propósito: esa es para un artefacto que
    PRODUJIMOS y no pasó el read-back. Acá el problema es del insumo --un PNG
    entrelazado, un TGA con RLE, un DDS ya comprimido-- y el llamador tiene
    que poder distinguir "arreglá la entrada" de "el pipeline hizo algo mal".
    """


class ArtifactValidationError(PipelineError):
    """Un artefacto existió pero no superó la validación de read-back."""


class PublishError(PipelineError):
    """La publicación no se pudo completar; el destino quedó intacto."""
