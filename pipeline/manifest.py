# -*- coding: utf-8 -*-
"""JobManifest: configuración declarativa, inmutable y validada de un job.

Implementa la hipótesis 2 del issue #5 (configuración declarativa) para el
alcance MVP del repo: Skyrim SE/AE, static/clutter, asset no skinned. Cualquier
dominio fuera de eso (criaturas, armaduras, BodySlide, Havok) queda fuera del
enum y da error de configuración, no soporte silencioso.

Reglas de validación (todas verificables con tests):
  - job_id seguro para usar como nombre de directorio;
  - rutas resueltas con containment: workspace_raiz y raiz_salida deben vivir
    dentro de raiz_proyecto; una ruta que escapa del root se rechaza;
  - source_mesh y texture_inputs deben existir y ser archivos;
  - extensiones por whitelist;
  - max_lado_textura: entero, potencia de dos, dentro del rango que mide el
    corpus (ver MAX_LADO_TEXTURA);
  - sombreado: "vanilla" o "cs_pbr" (SOMBREADOS_SOPORTADOS);
  - compresion: "ninguna" o "dxt" (COMPRESIONES_SOPORTADAS); "dxt" necesita
    numpy, y sin numpy es error de configuracion, no de la fase;
  - los campos nulos/vacíos no son válidos.

No hay paths hardcodeados: todas las rutas vienen del llamador.
"""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigurationError

# Alcance MVP acordado (spec + issues #2/#3/#5): SE/AE, static/clutter.
EDICIONES_SOPORTADAS = frozenset({"skyrim-se-ae"})
CATEGORIAS_SOPORTADAS = frozenset({"static", "clutter"})

# [PROVIDER] Las extensiones que el runner acepta hoy de entrada. Generadores
# de IA entregan sobre todo GLB/GLTF; FBX/OBJ están por compatibilidad con los
# scripts existentes (medir_parte.py los aceptan). Ampliar = evidencia, no deseo.
EXTENSIONES_MESH = frozenset({".glb", ".gltf", ".fbx", ".obj"})
EXTENSIONES_TEXTURA = frozenset({".png", ".tga", ".dds"})

# Para que shader se escriben las texturas. "vanilla" es la convencion del
# juego (`_n` con mascara especular en el alfa, `_m` de reflejo). "cs_pbr" es
# el True PBR de Community Shaders [PROVIDER]: `_rmaos` en la ranura 5 y sin
# `_m`. Ver skills/modelo-ia-a-skyrim/references/pbr-community-shaders.md.
SOMBREADOS_SOPORTADOS = frozenset({"vanilla", "cs_pbr"})

# Como se escriben los DDS. "ninguna": sin comprimir de 32 bpp, como el 31,2 %
# del corpus. "dxt": DXT5 el `_n` (los 12.075 `_n` vanilla lo son) y todo mapa
# con alfa; DXT1 el resto. Lo comprime census/compresor_dxt.py, con numpy.
COMPRESIONES_SOPORTADAS = frozenset({"ninguna", "dxt"})

# Lado máximo de textura, en téxeles. [OBSERVED] Del censo de 32.241 DDS: la
# mediana del lado mayor es 256 en terrain, 512 en actors y clutter, 1024 en
# architecture y armor; el máximo de TODO el corpus es 8192 y hay un solo
# archivo. 2048 queda muy por encima del vanilla --el 5,2 % del corpus llega
# ahí-- y ésa es la decisión, no una consecuencia: se declara en el manifest
# para que el costo de VRAM sea una elección visible (ver
# references/limites-skyrim.md, "Resoluciones").
MAX_LADO_TEXTURA = 2048
MIN_LADO_TEXTURA = 64
MAX_LADO_CORPUS = 8192


def _es_potencia_de_dos(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0

# job_id se usa como nombre de directorio: se restringe a un alfabeto seguro
# en vez de "sanitizar" (sanitizar silencioso = proyectos que pisan a otros).
# Sin anclas "$"/"^": se usa fullmatch(), que además rechaza el salto de
# línea final que "$" aceptaría ("job-1\n" matchearía con match()).
_PATRON_JOB_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def _resuelta(ruta: Path) -> Path:
    """Resuelve una ruta sin exigir que exista (resolve() no lo exige)."""
    return Path(ruta).expanduser().resolve()


def _contenida_hijo(ruta_resuelta: Path, raiz_resuelta: Path) -> bool:
    """True si ruta_resuelta está dentro de raiz_resuelta (o es ella)."""
    try:
        ruta_resuelta.relative_to(raiz_resuelta)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class JobManifest:
    """Config declarativa e inmutable de un job del pipeline.

    raiz_proyecto delimita todo lo que el pipeline puede escribir:
    workspace_raiz (staging por job) y raiz_salida (destino de publicación)
    deben quedar dentro. Los insumos (source_mesh, texture_inputs) solo se
    leen, así que se exige existencia pero no containment.
    """

    job_id: str
    source_mesh: Path
    raiz_proyecto: Path
    workspace_raiz: Path
    raiz_salida: Path
    target_edition: str = "skyrim-se-ae"
    asset_category: str = "static"
    texture_inputs: tuple[Path, ...] = ()
    enabled_transformations: tuple[str, ...] = ()
    reference_asset: Path | None = None
    max_lado_textura: int = MAX_LADO_TEXTURA
    sombreado: str = "vanilla"
    compresion: str = "ninguna"

    def __post_init__(self) -> None:
        """Normalización de tipos (el dataclass es frozen, así que va por
        object.__setattr__): acepta str donde se esperaba Path porque la
        configuración declarativa llega como strings (issue #5, JSON).
        Los valores inválidos (None, "", tipos ajenos) NO se corrigen:
        quedan como están y validar() los reporta como ConfigurationError,
        nunca como AttributeError/TypeError accidentales."""
        for campo in ("source_mesh", "raiz_proyecto", "workspace_raiz",
                      "raiz_salida"):
            valor = getattr(self, campo)
            if isinstance(valor, str) and valor.strip():
                object.__setattr__(self, campo, Path(valor))
        ref = self.reference_asset
        if isinstance(ref, str) and ref.strip():
            object.__setattr__(self, "reference_asset", Path(ref))
        ti = self.texture_inputs
        if isinstance(ti, (str, Path)):
            ti = (ti,)
        if isinstance(ti, (list, tuple)):
            object.__setattr__(
                self, "texture_inputs",
                tuple(Path(v) if isinstance(v, str) and v.strip() else v
                      for v in ti),
            )
        # Si texture_inputs no es str/Path/list/tuple, queda como está y
        # validar() lo reporta (tuple() sobre él rompería con TypeError).

    @staticmethod
    def _ruta_util(valor) -> Path | None:
        """Path utilizable o None si el valor es inválido (a reportar)."""
        if isinstance(valor, Path) and str(valor) not in ("", "."):
            return valor
        return None

    def validar(self) -> None:
        """Valida el manifest completo. Lanza ConfigurationError agregando
        TODOS los problemas encontrados (no uno a la vez), para que el error
        sea accionable en una sola pasada."""
        problemas: list[str] = []

        if not isinstance(self.job_id, str) or not _PATRON_JOB_ID.fullmatch(
            self.job_id
        ):
            problemas.append(
                f"job_id inválido: {self.job_id!r} "
                "(minúsculas, dígitos, '.', '-', '_'; 1-64 chars; "
                "sin '/' ni '..' ni espacios ni saltos)"
            )

        if self.target_edition not in EDICIONES_SOPORTADAS:
            problemas.append(
                f"target_edition no soportada: {self.target_edition!r} "
                f"(soportadas: {sorted(EDICIONES_SOPORTADAS)})"
            )
        if self.asset_category not in CATEGORIAS_SOPORTADAS:
            problemas.append(
                f"asset_category no soportada: {self.asset_category!r} "
                f"(soportadas: {sorted(CATEGORIAS_SOPORTADAS)})"
            )
        if self.sombreado not in SOMBREADOS_SOPORTADOS:
            problemas.append(
                f"sombreado no soportado: {self.sombreado!r} "
                f"(soportados: {sorted(SOMBREADOS_SOPORTADOS)})"
            )
        if self.compresion not in COMPRESIONES_SOPORTADAS:
            problemas.append(
                f"compresion no soportada: {self.compresion!r} "
                f"(soportadas: {sorted(COMPRESIONES_SOPORTADAS)})"
            )
        elif (self.compresion == "dxt"
              and importlib.util.find_spec("numpy") is None):
            problemas.append(
                "compresion 'dxt' necesita numpy (census/compresor_dxt.py), y "
                "no esta instalado: `pip install numpy`, o compresion "
                "'ninguna'"
            )
        # El lado máximo se valida contra el corpus, no contra el gusto: una
        # textura de 3000 téxeles no es "grande", es un lado que no es potencia
        # de dos, y 0 de 32.241 texturas vanilla lo son.
        if isinstance(self.max_lado_textura, bool) or not isinstance(
            self.max_lado_textura, int
        ):
            problemas.append(
                "max_lado_textura tiene que ser un entero: "
                f"{self.max_lado_textura!r}"
            )
        elif not _es_potencia_de_dos(self.max_lado_textura):
            problemas.append(
                "max_lado_textura no es potencia de dos: "
                f"{self.max_lado_textura} (0 de 32.241 texturas vanilla "
                "tienen un lado que no lo sea)"
            )
        elif not (MIN_LADO_TEXTURA <= self.max_lado_textura
                  <= MAX_LADO_CORPUS):
            problemas.append(
                "max_lado_textura fuera de rango: "
                f"{self.max_lado_textura} (admitido {MIN_LADO_TEXTURA}-"
                f"{MAX_LADO_CORPUS}; el máximo del corpus es 8192 y hay un "
                "solo archivo)"
            )

        raiz = self._ruta_util(self.raiz_proyecto)
        if raiz is None:
            problemas.append(
                f"raiz_proyecto inválida o vacía: {self.raiz_proyecto!r}"
            )
        else:
            raiz = _resuelta(raiz)
            for nombre, ruta in (
                ("workspace_raiz", self.workspace_raiz),
                ("raiz_salida", self.raiz_salida),
            ):
                valor = self._ruta_util(ruta)
                if valor is None:
                    problemas.append(f"{nombre} inválida o vacía: {ruta!r}")
                    continue
                res = _resuelta(valor)
                if not _contenida_hijo(res, raiz):
                    problemas.append(
                        f"{nombre} fuera de raiz_proyecto: {ruta} "
                        f"(resuelta: {res}; raíz: {raiz})"
                    )

        # Inspección de entradas: existencia + whitelist de extensión.
        # None/""/tipos ajenos se reportan como problema de config, no como
        # AttributeError/TypeError.
        entradas: list[tuple[str, tuple, frozenset]] = [
            ("source_mesh", (self.source_mesh,), EXTENSIONES_MESH),
            (
                "texture_inputs",
                self.texture_inputs
                if isinstance(self.texture_inputs, tuple)
                else (self.texture_inputs,),
                EXTENSIONES_TEXTURA,
            ),
        ]
        if self.reference_asset is not None:
            entradas.append(
                ("reference_asset", (self.reference_asset,),
                 EXTENSIONES_MESH | frozenset({".nif"}))
            )
        for nombre, rutas, exts in entradas:
            for ruta in rutas:
                valor = self._ruta_util(ruta)
                if valor is None:
                    problemas.append(
                        f"{nombre}: valor inválido o vacío: {ruta!r}"
                    )
                    continue
                if valor.suffix.lower() not in exts:
                    problemas.append(
                        f"{nombre}: extensión no admitida en {valor.name!r} "
                        f"(admitidas: {sorted(exts)})"
                    )
                if not valor.is_file():
                    problemas.append(
                        f"{nombre}: no existe o no es archivo: {valor}"
                    )

        if problemas:
            raise ConfigurationError(
                "JobManifest inválido:\n  - " + "\n  - ".join(problemas)
            )
