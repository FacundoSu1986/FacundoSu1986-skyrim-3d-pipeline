# -*- coding: utf-8 -*-
"""parser_dds.py — lee encabezados DDS del corpus de Skyrim. Python puro.

SIN dependencias. SIN Blender. SOLO LECTURA. No decodifica pixeles: solo el
encabezado, que es lo que hace falta para censar formato, resolucion, mipmaps
y consistencia.

LA SUITE DE FALSIFICACION DE ACA ES MEJOR QUE VALORES A MANO

En el censo de mallas hubo que fijar valores esperados archivo por archivo. Con
DDS hay algo mas fuerte: para los formatos comprimidos por bloques el tamano
del archivo es PREDECIBLE desde formato + dimensiones + cantidad de mipmaps.

    bytes = suma sobre cada nivel de  ceil(w/4) * ceil(h/4) * bytes_por_bloque

Si el parser leyo mal cualquiera de esos campos, la cuenta no da. Eso convierte
cada archivo del corpus en su propio caso de prueba: 32.361 comprobaciones que
nadie escribio a mano y que ningun error de offset sobrevive.

Es la misma idea que la identidad `cursor == offset + size` de verificar.py:
buscar una relacion que el formato obliga a cumplir, y exigirla.

Uso:
  python parser_dds.py --autotest <carpeta textures>
  python parser_dds.py <archivo.dds> [...]
  python parser_dds.py --censo <carpeta> --salida censo_dds.jsonl
"""
import json
import os
import struct
import sys

# --- formatos ---------------------------------------------------------------
# bytes por bloque de 4x4. Los formatos sin comprimir van aparte.
BLOQUE = {
    "DXT1": 8, "BC1": 8, "BC4": 8, "ATI1": 8,
    "DXT2": 16, "DXT3": 16, "DXT4": 16, "DXT5": 16,
    "BC2": 16, "BC3": 16, "BC5": 16, "ATI2": 16,
    "BC6H": 16, "BC7": 16,
}

# DXGI_FORMAT -> nombre. Solo los que aparecen en assets de juego.
DXGI = {
    71: "BC1", 72: "BC1", 73: "BC1",
    74: "BC2", 75: "BC2", 76: "BC2",
    77: "BC3", 78: "BC3", 79: "BC3",
    80: "BC4", 81: "BC4", 82: "BC4",
    83: "BC5", 84: "BC5", 85: "BC5",
    95: "BC6H", 96: "BC6H",
    98: "BC7", 99: "BC7",
    28: "R8G8B8A8", 87: "B8G8R8A8", 88: "B8G8R8X8",
}
DXGI_SRGB = {72, 75, 78, 99}

DDSD_MIPMAPCOUNT = 0x20000
DDPF_FOURCC = 0x4

# dwCaps2: un cubemap guarda una cadena de mipmaps POR CARA. Sin esto la
# prediccion de tamano falla por un factor de 6 exacto -- que es como se
# descubrio: 59 archivos de textures/cubemaps/ no cuadraban, y 696 bytes por
# cara x 6 + 128 de cabecera daba el tamano real al byte.
DDSCAPS2_CUBEMAP = 0x200
CARAS_CUBEMAP = (0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000)

# Textura de volumen: cada nivel de mip es un stack de `profundidad` slices, y
# la profundidad tambien se divide a la mitad en cada nivel. Un solo archivo
# del corpus lo usa (effects/noisevolume.dds) y fue el ultimo en cuadrar:
# 128^3 + 64^3 + ... + 1 = 2.396.745, mas 128 de cabecera = 2.396.873 exactos.
DDSCAPS2_VOLUME = 0x200000


class DdsInvalido(Exception):
    pass


def _ceil4(v):
    return (v + 3) // 4


def _mip_final(ancho, alto, mips):
    w, h = ancho, alto
    for _ in range(mips - 1):
        w = max(1, w // 2)
        h = max(1, h // 2)
    return [w, h]


def leer(ruta):
    """Encabezado + comprobacion de consistencia de tamano."""
    tam_archivo = os.path.getsize(ruta)
    with open(ruta, "rb") as fh:
        cab = fh.read(148)
    if len(cab) < 128 or cab[:4] != b"DDS ":
        raise DdsInvalido("no empieza con 'DDS '")

    dw_size, = struct.unpack_from("<I", cab, 4)
    if dw_size != 124:
        raise DdsInvalido("dwSize=%d, se esperaba 124" % dw_size)
    flags, alto, ancho = struct.unpack_from("<III", cab, 8)
    profundidad, = struct.unpack_from("<I", cab, 24)
    mips, = struct.unpack_from("<I", cab, 28)
    caps2, = struct.unpack_from("<I", cab, 112)
    pf_flags, = struct.unpack_from("<I", cab, 80)
    four = cab[84:88]
    bits, = struct.unpack_from("<I", cab, 88)
    mascara_alfa, = struct.unpack_from("<I", cab, 104)

    srgb = False
    if pf_flags & DDPF_FOURCC and four == b"DX10":
        if len(cab) < 148:
            raise DdsInvalido("declara DX10 pero no trae el header extra")
        dxgi, = struct.unpack_from("<I", cab, 128)
        fmt = DXGI.get(dxgi, "DXGI_%d" % dxgi)
        srgb = dxgi in DXGI_SRGB
        cabecera_bytes = 148
    elif pf_flags & DDPF_FOURCC:
        fmt = four.decode("latin-1").strip("\x00") or "?"
        cabecera_bytes = 128
    else:
        fmt = "sin_comprimir_%dbpp" % bits
        cabecera_bytes = 128

    if not (flags & DDSD_MIPMAPCOUNT) or mips == 0:
        mips = 1

    es_cubemap = bool(caps2 & DDSCAPS2_CUBEMAP)
    caras = sum(1 for c in CARAS_CUBEMAP if caps2 & c) if es_cubemap else 1
    caras = caras or 1
    es_volumen = bool(caps2 & DDSCAPS2_VOLUME)
    prof0 = max(1, profundidad) if es_volumen else 1

    # --- la identidad que falsifica el parseo ---
    esperado = None
    bpb = BLOQUE.get(fmt)
    if bpb:
        total, w, h, d = 0, ancho, alto, prof0
        for _ in range(mips):
            total += _ceil4(w) * _ceil4(h) * bpb * d
            w = max(1, w // 2)
            h = max(1, h // 2)
            d = max(1, d // 2)
        esperado = cabecera_bytes + total * caras
    elif fmt.startswith("sin_comprimir") and bits:
        total, w, h, d = 0, ancho, alto, prof0
        for _ in range(mips):
            total += w * h * d * (bits // 8)
            w = max(1, w // 2)
            h = max(1, h // 2)
            d = max(1, d // 2)
        esperado = cabecera_bytes + total * caras

    return {
        "ancho": ancho, "alto": alto, "mipmaps": mips,
        "formato": fmt, "srgb": srgb,
        "cubemap": es_cubemap, "caras": caras,
        "volumen": es_volumen, "profundidad": prof0,
        "comprimido": bpb is not None,
        "tiene_alfa": bool(mascara_alfa) or fmt in ("DXT3", "DXT5", "BC2", "BC3",
                                                    "BC7", "DXGI_98", "DXGI_99"),
        "bytes": tam_archivo,
        "bytes_esperados": esperado,
        "tamano_cuadra": (esperado is None) or (esperado == tam_archivo),
        "potencia_de_dos": (ancho & (ancho - 1)) == 0 and (alto & (alto - 1)) == 0,
        # Nivel mas chico de la cadena. NO se reporta "cadena completa" contra
        # 1x1: medido sobre el corpus, el 96,4% de las texturas de Skyrim corta
        # en 2x2, que es la convencion, no un defecto. Una metrica que marca
        # como rotas 31.940 texturas correctas es una metrica mal definida.
        "mip_mas_chico": _mip_final(ancho, alto, mips),
        "sin_mipmaps": mips <= 1,
    }


def autotest(raiz):
    """Cada archivo del corpus es su propio caso: el tamano tiene que cuadrar."""
    n = ok = malo = ilegible = sin_formula = 0
    ejemplos = []
    for base, _, archivos in os.walk(raiz):
        for f in archivos:
            if not f.lower().endswith(".dds"):
                continue
            n += 1
            ruta = os.path.join(base, f)
            try:
                e = leer(ruta)
            except Exception as exc:
                ilegible += 1
                if len(ejemplos) < 5:
                    ejemplos.append((os.path.relpath(ruta, raiz), str(exc)[:60]))
                continue
            if e["bytes_esperados"] is None:
                sin_formula += 1
            elif e["tamano_cuadra"]:
                ok += 1
            else:
                malo += 1
                if len(ejemplos) < 5:
                    ejemplos.append((
                        os.path.relpath(ruta, raiz),
                        "%s %dx%d mips=%d: esperado %d, real %d"
                        % (e["formato"], e["ancho"], e["alto"], e["mipmaps"],
                           e["bytes_esperados"], e["bytes"])))
    print("")
    print("  %d archivos DDS" % n)
    print("  %d con el tamano exacto que predice el encabezado" % ok)
    print("  %d con el tamano MAL" % malo)
    print("  %d sin formula de tamano (formato no cubierto)" % sin_formula)
    print("  %d ilegibles" % ilegible)
    for r, m in ejemplos:
        print("    %s\n      %s" % (r, m))
    if malo or ilegible:
        print("  El parser NO esta validado. Arreglar antes de censar.")
        return False
    print("  Parser validado sobre %d archivos. Ahora si, censar." % ok)
    return True


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "--autotest":
        sys.exit(0 if autotest(a[1]) else 1)
    if a[0] == "--censo":
        raiz = a[1]
        salida = a[a.index("--salida") + 1] if "--salida" in a else "censo_dds.jsonl"
        n_ok = n_err = 0
        with open(salida, "w", encoding="utf-8") as fh:
            for base, _, archivos in os.walk(raiz):
                for f in archivos:
                    if not f.lower().endswith(".dds"):
                        continue
                    ruta = os.path.join(base, f)
                    rel = os.path.relpath(ruta, raiz).replace(os.sep, "/")
                    try:
                        fila = leer(ruta)
                        fila["ruta"] = rel
                        n_ok += 1
                    except Exception as exc:
                        fila = {"ruta": rel, "error": "%s: %s"
                                % (type(exc).__name__, exc)}
                        n_err += 1
                    fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print("%s -> %d ok, %d con error" % (salida, n_ok, n_err))
        return
    for ruta in a:
        print(json.dumps(dict(leer(ruta), ruta=ruta), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
