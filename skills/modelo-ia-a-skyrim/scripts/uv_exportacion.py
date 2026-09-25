"""Preparar UNA UV para exportacion, despues del bake y en Object Mode.

conservar_uv(mesh, nombre) modifica el Mesh recibido. Pasarle una copia de
exportacion: la fuente del bake puede necesitar las otras capas. No cambia
materiales ni exporta NIF; revisar sus nodos y releer el NIF sigue siendo
necesario. Se importa desde Blender; no requiere bpy para importar el modulo
(tests/test_uv_exportacion.py lo prueba en CI con una malla falsa).

Edit Mode: la guarda mira la malla que recibe. Si la copia se hizo con la
FUENTE en Edit Mode, `fuente.data.copy()` copia los datos de antes de esa
edicion (lo editado vive en el BMesh hasta salir) y la copia no esta en Edit
Mode: salir de Edit Mode ANTES de copiar.

montar.py no lo llama: PyNifly exporta la UV ACTIVA (trampa 40), asi que
varias capas no rompen el export por si solas, y elegir cual conservar es
una decision que el script no puede tomar por vos.
"""


def conservar_uv(mesh, nombre):
    """Deja solo la capa nombrada, activa y de render, sin cambiar sus UV.

    Devuelve avisos: nodos de los materiales de la malla que nombraban una
    capa borrada (en el juego esa entrada queda en (0, 0) o en otra capa).

    Rechaza ANTES de borrar: un nombre ausente, Edit Mode, y una malla con
    mas de un usuario (borrar capas ahi rompe tambien a los demas objetos).
    Las referencias RNA a capas pueden invalidarse al modificar la coleccion:
    conservar nombres/valores Python y buscar cada capa de nuevo.
    """
    if mesh.is_editmode:
        raise ValueError("salir de Edit Mode antes de preparar las UV")
    if mesh.users > 1:
        raise ValueError("la malla tiene %d usuarios: preparar una copia "
                         "unica (obj.data = obj.data.copy())" % mesh.users)
    if nombre not in mesh.uv_layers:
        raise ValueError("no existe la capa UV %r" % nombre)
    antes = [tuple(v.uv) for v in mesh.uv_layers[nombre].data]
    borradas = [otra for otra in mesh.uv_layers.keys() if otra != nombre]
    for otra in borradas:
        mesh.uv_layers.remove(mesh.uv_layers[otra])
    if list(mesh.uv_layers.keys()) != [nombre]:
        raise RuntimeError("la limpieza no conservo solamente %r" % nombre)
    mesh.uv_layers.active = mesh.uv_layers[nombre]
    mesh.uv_layers[nombre].active_render = True
    mesh.update()
    despues = [tuple(v.uv) for v in mesh.uv_layers[nombre].data]
    if antes != despues:
        distintas = [i for i, (a, b) in enumerate(zip(antes, despues)) if a != b]
        raise RuntimeError(
            "cambiaron las coordenadas de %r: %d de %d bucles distintos "
            "(%d antes, %d despues), el primero en el indice %s"
            % (nombre, len(distintas), len(antes), len(antes), len(despues),
               distintas[0] if distintas else "-"))
    return nodos_con_capas_borradas(mesh, borradas)


def nodos_con_capas_borradas(mesh, borradas):
    """["material / nodo -> capa"] de los nodos UV Map y Attribute que nombran
    una capa de `borradas`."""
    avisos = []
    borradas = set(borradas)
    for mat in mesh.materials:
        if mat is None or not getattr(mat, "use_nodes", False) or mat.node_tree is None:
            continue
        for nodo in mat.node_tree.nodes:
            capa = (getattr(nodo, "uv_map", None) if nodo.type == "UVMAP"
                    else getattr(nodo, "attribute_name", None)
                    if nodo.type == "ATTRIBUTE" else None)
            if capa in borradas:
                avisos.append("%s / %s -> %s" % (mat.name, nodo.name, capa))
    return avisos
