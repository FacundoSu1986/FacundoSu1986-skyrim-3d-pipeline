# -*- coding: utf-8 -*-
"""Parser GLB mínimo y veraz, en stdlib pura.

Por qué existe: los providers (Meshy, Tripo, etc.) entregan casi siempre
GLB/GLTF, y la inspección del asset debe ser read-only e independiente de
Blender — la misma filosofía anti-independencia-circular que mantiene
`census/parser_nif.py` separado del toolchain de exportación.

Alcance declarado (no un parser glTF completo):
  - GLB binario con un chunk JSON y a lo sumo un chunk BIN;
  - accessors escalares/vectores con bufferView directo (sin sparse, sin
    extensions de compresión);
  - byteStride solo se acepta si coincide con el tamaño del elemento (datos
    contiguos); interleaved real se rechaza explícitamente;
  - cuenta de "triángulos" honesta: según el modo del primitive
    (TRIANGLES/STRIP/FAN); modos no triangulares (LINES, POINTS) se reportan
    como tal y no se cuenta nada a ojo.

Todo dato proviene del propio binario: nada se infiere de nombres de archivo.
Errores: ArtifactValidationError con causa preservada.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ArtifactValidationError

_MAGICO = b"glTF"
_SOPORTADA = 2
_CHUNK_JSON = 0x4E4F534A  # "JSON"
_CHUNK_BIN = 0x004E4942   # "BIN"

# Modos de primitive del spec glTF 2.0.
MODO_TRIANGLES = 4
MODO_STRIP = 5
MODO_FAN = 6
_TIPOS_ELEMENTO = {
    "SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
    "MAT2": 4, "MAT3": 9, "MAT4": 16,
}
_TAMANO_COMPONENTE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}


@dataclass(frozen=True)
class Accessor:
    index: int
    count: int
    tipo: str
    component_type: int
    min: tuple[float, ...] | None
    max: tuple[float, ...] | None

    @property
    def elementos(self) -> int:
        return _TIPOS_ELEMENTO[self.tipo]

    @property
    def tam_elemento(self) -> int:
        return self.elementos * _TAMANO_COMPONENTE[self.component_type]


@dataclass(frozen=True)
class Primitive:
    mode: int
    atributos: tuple[str, ...]
    indices_count: int | None  # None = non-indexed
    vertices: int              # accessor count del POSITION
    material: int | None

    @property
    def triangulos(self) -> int | None:
        """Cantidad real de triángulos según el modo. None si el modo no es
        triangular (LINES/POINTS): no se adivina."""
        n = self.indices_count if self.indices_count is not None else self.vertices
        if self.mode == MODO_TRIANGLES:
            return n // 3
        if self.mode in (MODO_STRIP, MODO_FAN):
            return max(0, n - 2)
        return None


@dataclass(frozen=True)
class ModeloGlb:
    """Resultado estructurado de parsear un GLB."""

    ruta: Path
    json: dict
    primitives: tuple[Primitive, ...]
    accessors: tuple[Accessor, ...]
    bin_len: int

    @property
    def triangulos(self) -> int:
        """Total solo si TODOS los primitives tienen modo triangular.
        Si alguno no lo es, esto sería mentira: se expone por primitive."""
        total = 0
        for p in self.primitives:
            t = p.triangulos
            if t is None:
                raise ArtifactValidationError(
                    f"{self.ruta.name}: primitive con modo {p.mode} no triangular"
                )
            total += t
        return total


def _leer_accessor(gltf: dict, bin_: bytes, indice: int, nombre: str) -> Accessor:
    """Valida un accessor sin leer los datos crudos (la inspección solo
    necesita counts y min/max del JSON; el cuerpo queda para slices futuras)."""
    try:
        a = gltf["accessors"][indice]
    except (KeyError, IndexError, TypeError) as e:
        raise ArtifactValidationError(
            f"accessor #{indice} de {nombre} inexistente"
        ) from e
    try:
        tipo = a["type"]
        ct = a["componentType"]
        count = a["count"]
    except KeyError as e:
        raise ArtifactValidationError(
            f"accessor #{indice} sin campo obligatorio {e}"
        ) from e
    if tipo not in _TIPOS_ELEMENTO or ct not in _TAMANO_COMPONENTE:
        raise ArtifactValidationError(
            f"accessor #{indice}: type/componentType desconocidos "
            f"({tipo!r}/{ct!r})"
        )
    if not isinstance(count, int) or count < 0:
        raise ArtifactValidationError(
            f"accessor #{indice}: count inválido ({count!r})"
        )
    # Containment del rango de bytes dentro del BIN chunk.
    acc = Accessor(
        index=indice, count=count, tipo=tipo, component_type=ct,
        min=tuple(a["min"]) if "min" in a else None,
        max=tuple(a["max"]) if "max" in a else None,
    )
    necesarios = count * acc.tam_elemento
    if "bufferView" in a and count > 0:
        try:
            bv = gltf["bufferViews"][int(a["bufferView"])]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise ArtifactValidationError(
                f"accessor #{indice}: bufferView inválido"
            ) from e
        off = int(bv.get("byteOffset", 0)) + int(a.get("byteOffset", 0))
        stride = bv.get("byteStride")
        if stride is not None and int(stride) != acc.tam_elemento:
            raise ArtifactValidationError(
                f"accessor #{indice}: byteStride {stride} interleaved no "
                "soportado por este parser (alcance declarado)"
            )
        if off < 0 or off + necesarios > len(bin_):
            raise ArtifactValidationError(
                f"accessor #{indice}: rango [{off}, {off + necesarios}) excede "
                f"el chunk BIN ({len(bin_)} bytes)"
            )
    elif count > 0:
        raise ArtifactValidationError(
            f"accessor #{indice} sin bufferView pero con count > 0"
        )
    return acc


def parsear_glb(ruta: Path | str) -> ModeloGlb:
    """Parsea un GLB y devuelve su estructura validada. Read-only."""
    ruta = Path(ruta)
    try:
        datos = ruta.read_bytes()
    except OSError as e:
        raise ArtifactValidationError(f"no se pudo leer {ruta}: {e}") from e

    if len(datos) < 12 or datos[:4] != _MAGICO:
        raise ArtifactValidationError(
            f"{ruta.name}: no es GLB (magic={datos[:4]!r})"
        )
    version, largo = struct.unpack_from("<II", datos, 4)
    if version != _SOPORTADA:
        raise ArtifactValidationError(
            f"{ruta.name}: glTF versión {version}, solo se soporta 2"
        )
    if largo != len(datos):
        raise ArtifactValidationError(
            f"{ruta.name}: largo de cabecera {largo} != archivo ({len(datos)})"
        )

    off = 12
    gltf: dict | None = None
    bin_ = b""
    primer_chunk = True
    while off + 8 <= len(datos):
        n, tipo = struct.unpack_from("<II", datos, off)
        cuerpo = datos[off + 8: off + 8 + n]
        if len(cuerpo) != n:
            raise ArtifactValidationError(
                f"{ruta.name}: chunk truncado en offset {off}"
            )
        if tipo == _CHUNK_JSON:
            if not primer_chunk:
                raise ArtifactValidationError(
                    f"{ruta.name}: el chunk JSON debe ser el primero"
                )
            try:
                gltf = json.loads(cuerpo.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise ArtifactValidationError(
                    f"{ruta.name}: chunk JSON inválido: {e}"
                ) from e
        elif tipo == _CHUNK_BIN:
            if bin_:
                raise ArtifactValidationError(
                    f"{ruta.name}: más de un chunk BIN (fuera del alcance)"
                )
            bin_ = bytes(cuerpo)
        primer_chunk = False
        off += 8 + n
        if off - len(datos) != 0 and off % 4:
            raise ArtifactValidationError(
                f"{ruta.name}: chunk no alineado a 4 bytes en offset {off}"
            )

    if gltf is None:
        raise ArtifactValidationError(f"{ruta.name}: sin chunk JSON")

    accessor_cache: dict[int, Accessor] = {}

    def leer(indice: int, nombre: str) -> Accessor:
        if indice not in accessor_cache:
            accessor_cache[indice] = _leer_accessor(gltf, bin_, indice, nombre)
        return accessor_cache[indice]

    primitives: list[Primitive] = []
    for mi, mesh in enumerate(gltf.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            nombre = f"meshes[{mi}].primitives[{pi}]"
            attrs = prim.get("attributes", {})
            if "POSITION" not in attrs:
                raise ArtifactValidationError(
                    f"{ruta.name}: {nombre} sin POSITION"
                )
            pos = leer(int(attrs["POSITION"]), nombre + ".POSITION")
            idx_acc = None
            if "indices" in prim:
                idx_acc = leer(int(prim["indices"]), nombre + ".indices")
            primitives.append(Primitive(
                mode=int(prim.get("mode", MODO_TRIANGLES)),
                atributos=tuple(sorted(attrs)),
                indices_count=idx_acc.count if idx_acc is not None else None,
                vertices=pos.count,
                material=prim.get("material"),
            ))

    return ModeloGlb(
        ruta=ruta,
        json=gltf,
        primitives=tuple(primitives),
        accessors=tuple(accessor_cache.values()),
        bin_len=len(bin_),
    )
