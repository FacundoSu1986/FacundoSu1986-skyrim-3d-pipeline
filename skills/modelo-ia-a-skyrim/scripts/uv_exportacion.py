"""Preparar UNA UV para exportacion, despues del bake y en Object Mode.

conservar_uv(mesh, nombre) modifica el Mesh recibido. Pasarle una copia de
exportacion: la fuente del bake puede necesitar las otras capas. No cambia
materiales ni exporta NIF; revisar sus nodos y releer el NIF sigue siendo
necesario. Se importa desde Blender; no requiere bpy para importar el modulo.
"""


def conservar_uv(mesh, nombre):
    """Deja solo la capa nombrada, activa y de render, sin cambiar sus UV.

    Un nombre ausente o Edit Mode se rechazan ANTES de borrar capas.
    Las referencias RNA a capas pueden invalidarse al modificar la coleccion:
    conservar nombres/valores Python y buscar cada capa de nuevo.
    """
    if mesh.is_editmode:
        raise ValueError("salir de Edit Mode antes de preparar las UV")
    if nombre not in mesh.uv_layers:
        raise ValueError("no existe la capa UV %r" % nombre)
    antes = tuple(tuple(v.uv) for v in mesh.uv_layers[nombre].data)
    for otra in list(mesh.uv_layers.keys()):
        if otra != nombre:
            mesh.uv_layers.remove(mesh.uv_layers[otra])
    if list(mesh.uv_layers.keys()) != [nombre]:
        raise RuntimeError("la limpieza no conservo solamente %r" % nombre)
    mesh.uv_layers.active_index = 0
    mesh.uv_layers[nombre].active_render = True
    mesh.update()
    despues = tuple(tuple(v.uv) for v in mesh.uv_layers[nombre].data)
    if antes != despues:
        raise RuntimeError("cambiaron las coordenadas de %r" % nombre)
