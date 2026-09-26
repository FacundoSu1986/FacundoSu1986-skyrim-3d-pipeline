# -*- coding: utf-8 -*-
"""Un donante sintetico para exportar_nif.py: un NIF hecho con PyNifly, sin un
byte del juego, con lo que exportar_nif le exige a un donante vanilla.

    blender -b --python donante_sintetico.py -- <salida.nif> [--prn <nodo>] [--force]

PARA QUE SIRVE
--------------
exportar_nif.py copia la estructura de un donante vanilla de la clase: el
`Prn`, el `BSXFlags`, el marcador de inventario, el cuerpo rigido y el
material de la colision. Sin el juego extraido no hay donante, y sin donante
no hay export. Este archivo lo reemplaza para PROBAR el camino --la
falsificacion de exportar_nif.py y examples/escudo-minimo lo usan--, no para
hacer un asset: sus numeros no salen de medir nada vanilla, salen de que se
reconozcan al leerlos.

QUE TRAE
--------
  * tres recetas de shader: `Donante:0`, metal con SKINNED y
    MODEL_SPACE_NORMALS prendidos (exportar_nif los tiene que apagar);
    `Donante:1`, vidrio con alfa por vertice (4333 + VERTEX_ALPHA);
    `Donante:2`, panel con el alfa en la textura (4333 sin VERTEX_ALPHA);
  * `BSXFlags` 194, `Prn` (por defecto WeaponSword; `--prn SHIELD` para un
    escudo), `BSInvMarker`;
  * colision: `bhkRigidBodyT` con una `bhkBoxShape`, masa 10, capa 5 y la
    inercia que se le pida (una en cero sirve para probar que exportar_nif
    rechaza un donante sin inercia).

Como libreria (sin Blender a la vista, recibe PyNifly ya cargado):
`escribir(pynifly, nifdefs, ruta, inercia, prn)`.

Exit 0 si el NIF quedo escrito, 1 si revienta, 2 si los argumentos no sirven.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from correr_en_blender import correr  # noqa: E402
import exportar_puro as ep  # noqa: E402

INERCIA = (2.0, 0.4, 2.3)
PRN = "WeaponSword"

_CAJA_V = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
           (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_CAJA_T = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
           (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def escribir(pynifly, nifdefs, ruta, inercia=INERCIA, prn=PRN):
    """Escribe el donante en `ruta` y la devuelve."""
    uv = [(0.1 * i, 0.05 * i) for i in range(8)]
    n = [(0.0, 0.0, 1.0)] * 8
    nif = pynifly.NifFile()
    nif.initialize("SKYRIMSE", ruta, root_type="BSFadeNode", root_name="Donante")

    def pieza(nombre, f1, f2, texturas, alfa=None):
        sh = nif.createShapeFromData(nombre, _CAJA_V, _CAJA_T, uv, n, parent=nif.root)
        for r, v in texturas.items():
            sh.set_texture(r, v)
        p = sh.shader._properties
        p.Shader_Type = 1
        p.Shader_Flags_1, p.Shader_Flags_2 = f1, f2
        p.Glossiness = 77.0
        p.Env_Map_Scale = 0.55
        sh.save_shader_attributes()
        if alfa:
            sh.has_alpha_property = True
            sh.alpha_property.properties.flags = alfa
            sh.alpha_property.properties.threshold = 128
            sh.save_alpha_property()

    pieza("Donante:0", 0x82400381 | ep.SF1_SKINNED | ep.SF1_MODEL_SPACE_NORMALS,
          0x00008011, {"Diffuse": r"textures\donante\donante.dds",
                       "Normal": r"textures\donante\donante_n.dds",
                       "EnvMap": r"textures\cubemaps\prueba_e.dds",
                       "EnvMask": r"textures\donante\donante_m.dds"})
    pieza("Donante:1", 0x82400389, 0x00008021,
          {"Diffuse": r"textures\donante\lente.dds",
           "EnvMap": r"textures\cubemaps\hielo_e.dds"}, alfa=4333)
    pieza("Donante:2", 0x82400381, 0x00008001,
          {"Diffuse": r"textures\donante\panel.dds"}, alfa=4333)
    pynifly.BSXFlags.New(nif, "BSX", flags=194, parent=nif.root)
    pynifly.NiStringExtraData.New(nif, "Prn", string_value=prn, parent=nif.root)
    pynifly.BSInvMarker.New(nif, "INV", rotation=(4712, 0, 0), zoom=1.05,
                            parent=nif.root)
    cp = nifdefs.bhkBoxShapeProps()
    cp.bhkMaterial = 1060167844
    # El radio de la REGLA de colision_caja: min(semieje menor, 0,1).
    cp.bhkRadius = min(1.0 / ep.HAVOK, 0.1)
    for i in range(3):
        cp.bhkDimensions[i] = 1.0 / ep.HAVOK
    blk = nif.add_block("", cp, None)
    cuerpo = nifdefs.bhkRigidBodyProps()
    cuerpo.bufType = nifdefs.PynBufferTypes.bhkRigidBodyTBufType
    cuerpo.shapeID = blk.id
    cuerpo.mass = 10.0
    cuerpo.collisionFilter_layer = 5
    cuerpo.motionSystem = 3
    for k, v in zip((0, 5, 10), inercia):
        cuerpo.inertiaMatrix[k] = v
    co = nif.root.add_collision(None, flags=129)
    co.add_body(cuerpo)
    nif.save()
    return ruta


def _mal(msg):
    print("[donante] %s" % msg)
    print(__doc__)
    raise SystemExit(2)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    prn = PRN
    if "--prn" in args:
        i = args.index("--prn")
        if i + 1 >= len(args) or args[i + 1].startswith("--"):
            _mal("--prn necesita el nombre del nodo (WeaponSword, SHIELD...)")
        prn = args[i + 1]
        del args[i:i + 2]
    for a in args:
        if a.startswith("--"):
            _mal("opcion desconocida: %s" % a)
    if len(args) != 1:
        _mal("falta la ruta del NIF de salida")
    ruta = os.path.abspath(args[0])
    if os.path.exists(ruta) and not force:
        _mal("%s ya existe: usa --force para pisarlo" % ruta)
    import addon_utils
    addon_utils.enable("io_scene_nifly", default_set=True)
    from io_scene_nifly.pyn import nifdefs, pynifly
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    escribir(pynifly, nifdefs, ruta, prn=prn)
    print("[donante] %s escrito: Prn %s, inercia %s" % (ruta, prn, list(INERCIA)))


if __name__ == "__main__":
    correr(main)
