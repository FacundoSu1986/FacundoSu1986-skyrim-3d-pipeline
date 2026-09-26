# -*- coding: utf-8 -*-
"""Mesh inspection veraz (issue #4), read-only, sobre GLB.

Produce un reporte estructurado ("AssetReport" del vocabulario del issue)
desde los datos del binario glTF, no desde nombres de archivo:

  - triángulos: conteo real por primitive según modo (Tri/Strip/Fan) —
    nunca len(polígonos) ni una suposición sobre quads/ngons, porque en GLB
    los primitives declaran su modo;
  - vértices: accessor.count del POSITION de cada primitive;
  - dimensiones: min/max del accessor POSITION, que glTF exige
    obligatoriamente en POSITION (spec 2.0);
  - materiales y slots de textura semánticos (pbrMetallicRoughness,
    normalTexture, occlusionTexture, emissiveTexture) con su imagen;
  - presencia de UV (TEXCOORD_0/1...) y normales (NORMAL).

Lo que NO hace:
  - no modifica el archivo (solo read_bytes);
  - no infiere nada fuera del formato (connected components y boundary
    edges requieren recorrer la geometría completa: pendiente de slice con
    corpus real del issue #2);
  - no acepta formatos no GLB: reportan "sin soporte" explícito.
"""
from __future__ import annotations

from pathlib import Path

from .glb import ModeloGlb, parsear_glb

_FORMATOS_INSPECCIONABLES = frozenset({"glb"})


def _slots_de_textura(modelo: ModeloGlb, indice_material: int) -> dict | None:
    """Extrae los slots semánticos de un material del JSON glTF."""
    materiales = modelo.json.get("materials", [])
    if indice_material is None or indice_material >= len(materiales):
        return None
    mat = materiales[indice_material]
    texturas = modelo.json.get("textures", [])
    imagenes = modelo.json.get("images", [])

    def imagen_de(ref) -> dict | None:
        if not isinstance(ref, dict):
            return None
        try:
            img = imagenes[texturas[ref["index"]]["source"]]
        except (KeyError, IndexError, TypeError):
            return {"error": "referencia de textura rota"}
        return {
            "uri": img.get("uri"),
            "mimeType": img.get("mimeType"),
            "bufferView": img.get("bufferView"),
        }

    pbr = mat.get("pbrMetallicRoughness", {})
    slots = {
        "baseColor": imagen_de(pbr.get("baseColorTexture")),
        "metallicRoughness": imagen_de(pbr.get("metallicRoughnessTexture")),
        "normal": imagen_de(mat.get("normalTexture")),
        "occlusion": imagen_de(mat.get("occlusionTexture")),
        "emissive": imagen_de(mat.get("emissiveTexture")),
    }
    return {
        "nombre": mat.get("name"),
        "doubleSided": bool(mat.get("doubleSided", False)),
        "slots": {k: v for k, v in slots.items() if v is not None},
    }


def inspeccionar_malla(ruta: Path | str) -> dict:
    """Inspecciona un mesh de entrada y devuelve un AssetReport JSON-able.

    Lanza ArtifactValidationError si el archivo es GLB inválido. Si el
    formato no tiene inspector, NO lanza: devuelve un reporte honesto con
    "inspeccionado": False.
    """
    ruta = Path(ruta)
    ext = ruta.suffix.lower().lstrip(".")
    if ext not in _FORMATOS_INSPECCIONABLES:
        return {
            "artefacto": ruta.name,
            "inspeccionado": False,
            "razon": f"sin inspector para .{ext} (soportados: "
                     f"{sorted(_FORMATOS_INSPECCIONABLES)})",
            "checks": {"parseable": False},
        }

    modelo = parsear_glb(ruta)

    # Dimensiones: min/max de los accessors POSITION, obligatorios por spec.
    pos_indices = {
        int(p["attributes"]["POSITION"])
        for m in modelo.json.get("meshes", [])
        for p in m.get("primitives", [])
        if "POSITION" in p.get("attributes", {})
    }
    pos_acc = [a for a in modelo.accessors if a.index in pos_indices]
    dimensiones = None
    if pos_acc and all(a.min is not None and a.max is not None
                       for a in pos_acc):
        mins = [a.min for a in pos_acc]
        maxs = [a.max for a in pos_acc]
        mn = [min(v) for v in zip(*mins)]
        mx = [max(v) for v in zip(*maxs)]
        dimensiones = {
            "min": mn,
            "max": mx,
            "tamano": [b - a for a, b in zip(mn, mx)],
        }

    total_vertices = sum(p.vertices for p in modelo.primitives)
    triangulos_por_primitive = [
        {"vertices": p.vertices, "indices": p.indices_count,
         "triangulos": p.triangulos, "material": p.material}
        for p in modelo.primitives
    ]
    todos_triangulares = all(
        p.triangulos is not None for p in modelo.primitives
    )

    atributos = sorted({a for p in modelo.primitives for a in p.atributos})
    materiales = sorted({p.material for p in modelo.primitives
                         if p.material is not None})
    reporte = {
        "artefacto": ruta.name,
        "inspeccionado": True,
        "herramienta": "pipeline.glb (parser propio stdlib)",
        "triangulos_total": (
            modelo.triangulos if todos_triangulares else None
        ),
        "vertices_total": total_vertices,
        "primitives": triangulos_por_primitive,
        "todos_triangulares": todos_triangulares,
        "dimensiones": dimensiones,
        "atributos": atributos,
        "uv_presente": any(
            a.startswith("TEXCOORD_") for a in atributos
        ),
        "normales_presentes": "NORMAL" in atributos,
        "materiales": [
            m for m in (_slots_de_textura(modelo, i) for i in materiales)
            if m is not None
        ],
        "checks": {
            "parseable": True,
            "position_presente": len(modelo.primitives) > 0,
        },
        "errores": [],
    }
    return reporte
