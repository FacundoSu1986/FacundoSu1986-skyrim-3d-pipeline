# -*- coding: utf-8 -*-
"""Fixture GLB sintético, construido byte a byte.

Mismo criterio que tests/nif_sintetico.py: como los bytes se generan acá, el
fixture puede vivir en el repo (no hay ni un byte de terceros) y corromperlo
es un test más — un parser que no puede fallar no verifica nada.

construir() devuelve un GLB válido mínimo con:
  - un mesh con UN primitive;
  - POSITION (float32 VEC3) con min/max declarados;
  - opcional TEXCOORD_0 (float32 VEC2) y NORMAL (float32 VEC3);
  - índices uint16 opcionales (non-indexed si se omite);
  - un material con slots semánticos (baseColor normal metallicRoughness
    occlusion emissive) apuntando a imágenes con uri placeholder.

Los parámetros permiten fabricar casos de falsificación:
  - modo=0/1 (POINTS/LINES) para probar que NO se cuentan triángulos;
  - accessor fuera del BIN; chunk truncado; magic incorrecto; etc.
"""
from __future__ import annotations

import json
import struct

_F32 = 5126   # FLOAT
_U16 = 5123   # UNSIGNED_SHORT


def _pad4(datos: bytes, pad: bytes = b"\x00") -> bytes:
    faltan = (-len(datos)) % 4
    return datos + pad * faltan


def construir(
    modo: int = 4,
    con_uv: bool = True,
    con_normal: bool = True,
    con_indices: bool = True,
    con_material: bool = True,
    con_slots: bool = True,
    vertices: tuple[tuple[float, float, float], ...] = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (1.0, 1.0, 0.0),
    ),
) -> bytes:
    """Devuelve los bytes de un GLB válido. Con los defaults: una "tira" de
    4 posiciones + 4 índices — alcanza para falsificar todos los conteos."""
    verts = [tuple(map(float, v)) for v in vertices]
    n = len(verts)

    bin_partes: list[bytes] = []
    buffer_views: list[dict] = []
    accessors: list[dict] = []

    def agregar(datos: bytes, componente: int, tipo: str, count: int,
                extra: dict | None = None) -> int:
        base = sum(len(b) for b in bin_partes)
        datos = _pad4(datos)
        buffer_views.append({
            "buffer": 0, "byteOffset": base, "byteLength": len(datos),
        })
        accessor = {
            "bufferView": len(buffer_views) - 1,
            "componentType": componente,
            "count": count,
            "type": tipo,
        }
        if extra:
            accessor.update(extra)
        accessors.append(accessor)
        bin_partes.append(datos)
        return len(accessors) - 1

    pos_b = b"".join(struct.pack("<3f", *v) for v in verts)
    mins = [min(c) for c in zip(*verts)]
    maxs = [max(c) for c in zip(*verts)]
    idx_pos = agregar(pos_b, _F32, "VEC3", n, {"min": mins, "max": maxs})

    attrs: dict[str, int] = {"POSITION": idx_pos}
    if con_normal:
        nor = b"".join(struct.pack("<3f", 0.0, 0.0, 1.0) for _ in verts)
        attrs["NORMAL"] = agregar(nor, _F32, "VEC3", n)
    if con_uv:
        uvs = b"".join(struct.pack("<2f", float(i % 2), float(i // 2))
                       for i in range(n))
        attrs["TEXCOORD_0"] = agregar(uvs, _F32, "VEC2", n)

    prim: dict = {"attributes": attrs, "mode": modo}
    if con_indices:
        índices = b"".join(struct.pack("<H", i) for i in range(n))
        prim["indices"] = agregar(índices, _U16, "SCALAR", n)
    if con_material:
        prim["material"] = 0

    documento: dict = {
        "asset": {"version": "2.0", "generator": "tests/glb_sintetico.py"},
        "meshes": [{"name": "sintetico", "primitives": [prim]}],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": sum(len(b) for b in bin_partes)}],
    }
    if con_material:
        mat: dict = {"name": "mat_sintetico"}
        if con_slots:
            documento["images"] = [
                {"uri": "albedo.png", "mimeType": "image/png"},
                {"uri": "normal.png", "mimeType": "image/png"},
                {"uri": "mr.png", "mimeType": "image/png"},
                {"uri": "occlusion.png", "mimeType": "image/png"},
                {"uri": "emissive.png", "mimeType": "image/png"},
            ]
            documento["textures"] = [{"source": i} for i in range(5)]
            mat["pbrMetallicRoughness"] = {
                "baseColorTexture": {"index": 0},
                "metallicRoughnessTexture": {"index": 2},
            }
            mat["normalTexture"] = {"index": 1}
            mat["occlusionTexture"] = {"index": 3}
            mat["emissiveTexture"] = {"index": 4}
        documento["materials"] = [mat]

    json_b = _pad4(json.dumps(documento).encode("utf-8"), b" ")
    bin_b = _pad4(b"".join(bin_partes))

    largo = 12 + 8 + len(json_b) + 8 + len(bin_b)
    return (
        struct.pack("<4sII", b"glTF", 2, largo)
        + struct.pack("<I4s", len(json_b), b"JSON") + json_b
        + struct.pack("<I4s", len(bin_b), b"BIN\x00") + bin_b
    )
