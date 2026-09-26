# -*- coding: utf-8 -*-
"""La "pieza de IA" del ejemplo: un GLB escrito byte a byte, con Python solo.

    python pieza_ia.py <salida.glb>

Hace de lo que devuelve Tripo o Meshy, con tres de los defectos de siempre,
que son los que los pasos siguientes tienen que arreglar:

  * los vertices sin soldar: cada cara trae los suyos (24 para 12
    triangulos), como un export "flat";
  * el origen en la base, no en el centro;
  * la escala y la orientacion de la IA: 1 de alto, en metros, y la
    convencion de glTF (+Y arriba, el frente hacia +Z). Skyrim mide en
    unidades de 1/70 de metro y el escudo cuelga del nodo SHIELD, que no
    mira a ningun lado de esos.

Es una placa de 0,75 x 1 x 0,06: un escudo en su forma mas simple. Los bytes
salen siempre iguales, asi que un test puede comparar contra ellos.
"""
import json
import struct
import sys

ANCHO, ALTO, ESPESOR = 0.75, 1.0, 0.06
TRIANGULOS = 12
NOMBRE = "PiezaIA"

_F32, _U16 = 5126, 5123              # componentType de glTF
_ARRAY, _INDICES = 34962, 34963      # target de un bufferView


def caras():
    """[(normal, [4 esquinas en sentido antihorario visto de afuera])], en
    coordenadas de glTF. x y z centrados; y de 0 (la base) a ALTO."""
    x, y, z = ANCHO / 2, ALTO, ESPESOR / 2
    return [
        ((0, 0, 1), [(-x, 0, z), (x, 0, z), (x, y, z), (-x, y, z)]),        # frente
        ((0, 0, -1), [(x, 0, -z), (-x, 0, -z), (-x, y, -z), (x, y, -z)]),   # dorso
        ((1, 0, 0), [(x, 0, z), (x, 0, -z), (x, y, -z), (x, y, z)]),
        ((-1, 0, 0), [(-x, 0, -z), (-x, 0, z), (-x, y, z), (-x, y, -z)]),
        ((0, 1, 0), [(-x, y, z), (x, y, z), (x, y, -z), (-x, y, -z)]),      # arriba
        ((0, -1, 0), [(-x, 0, -z), (x, 0, -z), (x, 0, z), (-x, 0, z)]),     # base
    ]


def _pad4(datos, relleno=b"\x00"):
    return datos + relleno * ((-len(datos)) % 4)


def construir():
    """Los bytes del GLB."""
    pos, nor, uv, idx = [], [], [], []
    for normal, esquinas in caras():
        base = len(pos)
        pos += esquinas
        nor += [normal] * 4
        uv += [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    assert len(idx) == 3 * TRIANGULOS

    binario, vistas, accesos = b"", [], []

    def agregar(datos, componente, tipo, cuenta, destino, extra=None):
        nonlocal binario
        vistas.append({"buffer": 0, "byteOffset": len(binario),
                       "byteLength": len(datos), "target": destino})
        binario = _pad4(binario + datos)
        acceso = {"bufferView": len(vistas) - 1, "componentType": componente,
                  "count": cuenta, "type": tipo}
        acceso.update(extra or {})
        accesos.append(acceso)
        return len(accesos) - 1

    atributos = {
        "POSITION": agregar(b"".join(struct.pack("<3f", *p) for p in pos), _F32,
                            "VEC3", len(pos), _ARRAY,
                            {"min": [min(c) for c in zip(*pos)],
                             "max": [max(c) for c in zip(*pos)]}),
        "NORMAL": agregar(b"".join(struct.pack("<3f", *n) for n in nor), _F32,
                          "VEC3", len(nor), _ARRAY),
        "TEXCOORD_0": agregar(b"".join(struct.pack("<2f", *t) for t in uv), _F32,
                              "VEC2", len(uv), _ARRAY),
    }
    indices = agregar(b"".join(struct.pack("<H", i) for i in idx), _U16,
                      "SCALAR", len(idx), _INDICES)
    documento = {
        "asset": {"version": "2.0", "generator": "examples/escudo-minimo/pieza_ia.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": NOMBRE, "mesh": 0}],
        "meshes": [{"name": NOMBRE, "primitives": [
            {"attributes": atributos, "indices": indices, "mode": 4, "material": 0}]}],
        "materials": [{"name": "metal", "pbrMetallicRoughness": {
            "baseColorFactor": [0.55, 0.5, 0.45, 1.0],
            "metallicFactor": 0.8, "roughnessFactor": 0.4}}],
        "accessors": accesos,
        "bufferViews": vistas,
        "buffers": [{"byteLength": len(binario)}],
    }
    js = _pad4(json.dumps(documento, sort_keys=True, separators=(",", ":"))
               .encode("utf-8"), b" ")
    largo = 12 + 8 + len(js) + 8 + len(binario)
    return (struct.pack("<4sII", b"glTF", 2, largo)
            + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(binario), b"BIN\x00") + binario)


def escribir(ruta):
    datos = construir()
    with open(ruta, "wb") as fh:
        fh.write(datos)
    return len(datos)


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    n = escribir(argv[0])
    print("[pieza] %s: %d bytes, %d triangulos, %d vertices sin soldar"
          % (argv[0], n, TRIANGULOS, 4 * len(caras())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
