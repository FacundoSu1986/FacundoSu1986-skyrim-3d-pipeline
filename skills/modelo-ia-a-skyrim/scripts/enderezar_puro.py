# -*- coding: utf-8 -*-
"""Lo del enderezado que no necesita Blender: la matematica, con --autotest.

POR QUE EXISTE ESTE ARCHIVO, Y POR QUE NO ALCANZA CON EL PASE PLANAR.

`preparar_parte.py --planar` DISUELVE geometria redundante: junta en una cara
lo que ya es el mismo panel. Lo que NO hace es colocar un vertice sobre una
recta. Si la linea de un filo ondula porque sus vertices estan fisicamente
desplazados, despues de disolver sigue ondulando --y con menos vertices encima,
a veces se ve peor--. Enderezar es otra operacion: ajustar una recta y
PROYECTAR los vertices interiores sobre ella.

La recta es la CUERDA: el segmento entre el primer y el ultimo vertice de la
cadena. No es una comodidad, son dos decisiones:

  * los extremos NO se mueven, asi que una cadena enderezada sigue empezando y
    terminando donde empezaba y terminaba. No hace falta decidir donde corta;
  * la desviacion contra la cuerda es la que distingue las dos cosas que este
    dominio confunde todo el tiempo:

      - una linea de diseno con ondulacion  -> se aparta POCO de su cuerda
      - una curva de diseno (un arco)       -> se aparta MUCHO

Por eso el tope es fail-closed: si la cadena se aparta mas que el tope, NO se
endereza y se informa el motivo. Confundir un arco con una linea ondulada
arruina la pieza, y lo hace en silencio: la malla sigue sana, `salud_malla.py`
no tiene nada que decir, y el error solo se ve en el render. En una pieza
Dwemer, que tiene curvas legitimas al lado de lineas mecanicas, esto es la
diferencia entre arreglarla y destrozarla.

Todavia NO esta resuelto, y por eso no se promete: CUALES cadenas hay que
enderezar. `enderezar.py` propone las aristas duras (crestas y bordes) y las
agrupa en cadenas; el tope decide despues, cadena por cadena. Un detector de
intencion de diseno no existe aca.

Uso:
  python enderezar_puro.py --autotest
"""

import math

# Debajo de esto una cadena es un punto: no hay direccion que ajustar.
EPS = 1e-12


def _resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _producto_vectorial(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norma(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _producto_punto(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalizar(a, largo):
    return (a[0] / largo, a[1] / largo, a[2] / largo)


def desviacion(puntos):
    """(desviacion maxima, largo de la cuerda) de una cadena.

    La desviacion es la distancia PERPENDICULAR de cada punto interior a la
    recta que pasa por los dos extremos. Es la medida de "cuanto ondula", y
    tambien la de "cuanto se arquea": el mismo numero sirve para las dos y por
    eso hace falta el tope.
    """
    if len(puntos) < 2:
        return None, 0.0
    a, b = puntos[0], puntos[-1]
    v = _resta(b, a)
    largo = _norma(v)
    if largo <= EPS:
        return None, 0.0
    u = _normalizar(v, largo)
    maxima = 0.0
    for p in puntos[1:-1]:
        w = _resta(p, a)
        # Distancia al infinito de la recta (no al segmento): un punto que se
        # pasa de largo se detecta aparte, con el parametro t.
        d = _norma(_producto_vectorial(w, u))
        maxima = max(maxima, d)
    return maxima, largo


def enderezar(puntos, tope):
    """Proyecta los puntos interiores sobre la cuerda. Fail-closed.

    Devuelve (nuevos, informe). Si la cadena no califica, `nuevos` es None y el
    informe dice por que --no se devuelve una lista a medio tocar.
    """
    if len(puntos) < 3:
        return None, {"motivo": "cadena de %d puntos: hacen falta 3 o mas"
                                % len(puntos)}
    desvio, largo = desviacion(puntos)
    if desvio is None:
        return None, {"motivo": "los extremos coinciden: no hay recta"}
    if desvio > tope:
        return None, {"motivo": ("desvio %.6f > tope %.6f: se aparta de su "
                                 "cuerda como una curva, no como una linea "
                                 "ondulada" % (desvio, tope)),
                      "desvio": desvio, "largo": largo}
    a, b = puntos[0], puntos[-1]
    u = _normalizar(_resta(b, a), largo)
    nuevos = [a]
    for p in puntos[1:-1]:
        t = _producto_punto(_resta(p, a), u)
        # Un punto que proyecta fuera del segmento significa que la cadena se
        # dobla hacia atras: enderezar eso la da vuelta, no la alinea.
        if t <= EPS or t >= largo - EPS:
            return None, {"motivo": ("la cadena se dobla hacia atras: un punto "
                                     "proyecta en t=%.6f de %.6f" % (t, largo)),
                          "desvio": desvio, "largo": largo}
        nuevos.append((a[0] + u[0] * t, a[1] + u[1] * t, a[2] + u[2] * t))
    nuevos.append(b)
    # Dos puntos que caen en el mismo lugar dejan una cara degenerada, que el
    # exportador escribe igual y el juego dibuja como un parpadeo.
    piso = largo * 1e-6
    for i in range(1, len(nuevos)):
        if _norma(_resta(nuevos[i], nuevos[i - 1])) <= piso and i > 1:
            return None, {"motivo": ("quedaria degenerada: los puntos %d y %d "
                                     "caen en el mismo lugar" % (i - 1, i)),
                          "desvio": desvio, "largo": largo}
    movimiento = max(_norma(_resta(n, p)) for n, p in zip(nuevos, puntos))
    return nuevos, {"desvio_antes": desvio,
                    "desvio_despues": desviacion(nuevos)[0],
                    "movimiento_max": movimiento,
                    "largo": largo,
                    "puntos": len(puntos)}


TOPES_SUGERIDOS = (0.0005, 0.001, 0.002, 0.005, 0.01)


def calibracion(desvios, alto, topes=TOPES_SUGERIDOS):
    """Cuantas cadenas calificarian con cada tope, y como se reparten.

    Es lo que convierte "elegi un tope" en un numero. Si las cadenas se parten
    en dos grupos --las casi rectas y las curvas de diseno--, el tope que los
    separa esta a la vista en los percentiles. Sin esto habria que adivinar el
    tope, y adivinar es como se aplana un arco decorativo.

    `desvios` viene en unidades del modelo; la fraccion se calcula aca contra
    `alto`, que es como lo pide `--tope`.
    """
    if alto <= 0 or not desvios:
        return None
    fracciones = sorted(d / alto for d in desvios)
    n = len(fracciones)

    def p(q):
        return fracciones[min(n - 1, int(n * q))]

    return {"n_cadenas": n,
            "min": round(fracciones[0], 6),
            "p50": round(p(0.50), 6),
            "p90": round(p(0.90), 6),
            "max": round(fracciones[-1], 6),
            "por_tope": {"%.4f" % t: sum(1 for f in fracciones if f <= t)
                         for t in topes}}


def encadenar(aristas):
    """Parte el grafo de aristas duras en CAMINOS que no comparten aristas.

    Un vertice donde las lineas se cruzan o se bifurcan (grado distinto de 2)
    es EXTREMO de los caminos que salen de el, nunca un punto interior. Eso no
    es un detalle de implementacion: es lo que garantiza que un vertice de
    cruce no lo muevan dos cuerdas distintas, cada una hacia su recta, con el
    resultado dependiendo del orden. Los cruces se quedan quietos, y cada
    arista pertenece a un solo camino.

    Se descarta el enfoque de "un componente con grado > 2 se rechaza entero",
    que fue el primero: en una pieza dura las crestas se cruzan, y con eso no
    se enderezaba nada. Los caminos cortos que salen de un cruce --de 2
    vertices-- los filtra despues el minimo de la cadena.

    Los CICLOS cerrados (componentes donde todo vertice tiene grado 2) se
    rechazan: no tienen extremos que fijar, y una cuerda ahi endereza el
    circulo en una recta. Devuelve (caminos, motivos).
    """
    adyacencia = {}
    for a, b in aristas:
        if a == b:
            continue
        adyacencia.setdefault(a, set()).add(b)
        adyacencia.setdefault(b, set()).add(a)

    def arista(x, y):
        return frozenset((x, y))

    usadas, caminos, motivos = set(), [], []
    cruces = sorted(v for v, vecinos in adyacencia.items() if len(vecinos) != 2)
    for inicio in cruces:
        for vecino in sorted(adyacencia[inicio]):
            if arista(inicio, vecino) in usadas:
                continue
            usadas.add(arista(inicio, vecino))
            camino = [inicio, vecino]
            previo, actual = inicio, vecino
            # Se avanza solo por vertices de grado 2: el primer cruce corta.
            while len(adyacencia[actual]) == 2:
                siguientes = [v for v in sorted(adyacencia[actual]) if v != previo]
                if not siguientes or arista(actual, siguientes[0]) in usadas:
                    break
                usadas.add(arista(actual, siguientes[0]))
                camino.append(siguientes[0])
                previo, actual = actual, siguientes[0]
            caminos.append(camino)

    # Lo que quedo sin usar no toca ningun cruce: es un ciclo. Se marca el
    # componente entero antes de informar: sin eso, un triangulo daba TRES
    # motivos --uno por vertice-- y el informe contaba ciclos de mas (lo
    # encontro `test_las_aristas_no_se_repiten_entre_caminos`).
    vistas = set()
    for inicio in sorted(adyacencia):
        if inicio in vistas:
            continue
        if all(arista(inicio, v) in usadas for v in adyacencia[inicio]):
            continue
        componente, pila = set(), [inicio]
        while pila:
            v = pila.pop()
            if v in componente:
                continue
            componente.add(v)
            pila.extend(adyacencia[v])
        vistas |= componente
        motivos.append("ciclo cerrado de %d vertices: sin extremos que fijar"
                       % len(componente))
    return caminos, motivos


# --- autotest ---------------------------------------------------------------
#
# Figuras de respuesta conocida. Se cuentan, no se declaran: cuantas
# comprobaciones corrieron lo imprime el banco.

def _linea(n, amplitud=0.0):
    """n puntos sobre X, con ondulacion perpendicular de amplitud dada."""
    return [(float(i), (amplitud if i % 2 else -amplitud), 0.0)
            for i in range(n)]


def _arco(n, flecha):
    """Un arco de diseno: se aparta de su cuerda de forma monotona."""
    return [(float(i), -flecha * (1.0 - ((2.0 * i / (n - 1)) - 1.0) ** 2), 0.0)
            for i in range(n)]


def autotest():
    fallas = []
    n = 0

    def comprobacion(condicion, texto):
        nonlocal n
        n += 1
        if not condicion:
            fallas.append(texto)

    # 1. Una recta se deja como esta: la proyeccion no mueve nada.
    recta = _linea(5)
    nuevos, info = enderezar(recta, 0.05)
    comprobacion(nuevos is not None, "una recta tiene que calificar")
    comprobacion(max(_norma(_resta(a, b)) for a, b in zip(nuevos, recta))
                 < 1e-12, "enderezar una recta la movio")
    comprobacion(desviacion(recta)[0] < 1e-12,
                 "una recta no tiene que tener desviacion")

    # 2. Una linea ondulada: se acepta, se endereza, y los extremos no se mueven.
    #    `_linea(n, amplitud)` alterna +-amplitud, asi que el pico a pico --que
    #    es la desviacion contra la cuerda-- vale 2*amplitud.
    ondulada = _linea(9, amplitud=0.01)
    nuevos, info = enderezar(ondulada, 0.05)
    comprobacion(nuevos is not None, "la ondulada de 0,01 con tope 0,05 tiene "
                                     "que calificar")
    comprobacion(desviacion(nuevos)[0] < 1e-12,
                 "despues de enderezar, el desvio no es cero: %r"
                 % (desviacion(nuevos)[0],))
    comprobacion(nuevos[0] == ondulada[0] and nuevos[-1] == ondulada[-1],
                 "los extremos se movieron")
    comprobacion(abs(info["movimiento_max"] - 0.02) < 1e-9,
                 "el movimiento tiene que ser el pico a pico de la ondulacion: %r"
                 % (info["movimiento_max"],))
    comprobacion(abs(info["desvio_antes"] - 0.02) < 1e-9,
                 "el informe tiene que decir de donde venia: %r"
                 % (info["desvio_antes"],))

    # 3. Un arco de diseno: se RECHAZA, y los puntos no se tocan.
    arco = _arco(9, flecha=0.5)
    nuevos, info = enderezar(arco, 0.05)
    comprobacion(nuevos is None, "un arco de flecha 0,5 con tope 0,05 no se "
                                 "puede enderezar")
    comprobacion("tope" in info["motivo"],
                 "el motivo tiene que nombrar el tope: %r" % (info["motivo"],))

    # 4. Cadena corta.
    nuevos, info = enderezar([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], 0.5)
    comprobacion(nuevos is None, "dos puntos no son una cadena")

    # 5. Un solo vertice fuera de lugar: se rechaza, no se lo lleva a la fuerza.
    con_pico = _linea(9)
    con_pico[4] = (4.0, 0.9, 0.0)
    nuevos, info = enderezar(con_pico, 0.05)
    comprobacion(nuevos is None, "un pico de 0,9 con tope 0,05 tiene que "
                                 "rechazarse")

    # 6. El tope es un tope. Se lo prueba con margen a los dos lados y no en el
    #    borde exacto: 0,03 calculado en punto flotante puede dar
    #    0,030000000000000002, y exigir la igualdad exacta seria probar el
    #    redondeo, no la regla.
    apenas = _linea(5, amplitud=0.015)   # desvio = 0,03
    desvio_apenas = desviacion(apenas)[0]
    comprobacion(enderezar(apenas, desvio_apenas * 0.999)[0] is None,
                 "con el tope por debajo del desvio tiene que rechazar")
    comprobacion(enderezar(apenas, desvio_apenas * 1.001)[0] is not None,
                 "con el tope por encima del desvio tiene que aceptar")

    # 7. Cadena que se dobla hacia atras: rechazada.
    #
    #    2 ----- 3
    #    |     /
    #    0 -- 1
    #
    doblada = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 1.0, 0.0),
               (1.5, 0.02, 0.0)]
    nuevos, info = enderezar(doblada, 10.0)
    comprobacion(nuevos is None and "dobla" in info["motivo"],
                 "una cadena que se dobla tiene que rechazarse: %r"
                 % (info.get("motivo"),))

    # 8. Degeneracion: dos puntos que proyectan al mismo lugar.
    #
    #    0 -- (1, +d) -- (1, -d) -- 2   con d chico: los dos del medio
    #    caen en el mismo punto de la cuerda.
    pegados = [(0.0, 0.0, 0.0), (1.0, 0.01, 0.0), (1.0, -0.01, 0.0),
               (2.0, 0.0, 0.0)]
    nuevos, info = enderezar(pegados, 0.05)
    comprobacion(nuevos is None and "degenerada" in info["motivo"],
                 "dos puntos que caen juntos tienen que rechazarse: %r"
                 % (info.get("motivo"),))

    # 9. Determinismo: la misma entrada da la misma salida.
    a1, _ = enderezar(ondulada, 0.05)
    a2, _ = enderezar(ondulada, 0.05)
    comprobacion(a1 == a2, "dos corridas dieron distinto")

    # 10. Encadenar: tres aristas desordenadas forman un camino de 4 en orden.
    cadenas, _ = encadenar([(2, 3), (0, 1), (1, 2)])
    comprobacion(cadenas == [[0, 1, 2, 3]], "camino mal ordenado: %r"
                 % (cadenas,))

    # 11. Encadenar: una Y da tres caminos que COMPARTEN el vertice del cruce
    #     como extremo. Ninguno llega a 3 vertices, asi que ninguno se
    #     endereza: el cruce nunca queda en el interior de una cuerda.
    cadenas, motivos = encadenar([(0, 1), (1, 2), (1, 3)])
    comprobacion(sorted(cadenas) == [[0, 1], [1, 2], [1, 3]],
                 "una Y tendria que dar tres caminos de 2: %r" % (cadenas,))
    comprobacion(all(c[0] == 1 or c[-1] == 1 for c in cadenas),
                 "el cruce tiene que quedar en un extremo de TODOS los "
                 "caminos: %r" % (cadenas,))
    comprobacion(motivos == [], "una Y no es un motivo de rechazo: %r"
                 % (motivos,))

    # 11b. Cruce en cruz: el vertice central tampoco se mueve.
    cadenas, _ = encadenar([(0, 5), (5, 1), (2, 5), (5, 3)])
    comprobacion(len(cadenas) == 4, "cuatro ramas: %r" % (cadenas,))
    comprobacion(all(len(c) == 2 for c in cadenas),
                 "las cuatro son de 2 vertices: %r" % (cadenas,))

    # 11c. Cruzados los dos sentidos: la misma arista no puede salir dos veces.
    cadenas, _ = encadenar([(0, 1), (1, 2), (2, 3), (3, 4), (2, 5)])
    todas = [tuple(sorted((c[i], c[i + 1])))
             for c in cadenas for i in range(len(c) - 1)]
    comprobacion(len(todas) == len(set(todas)),
                 "una arista quedo en dos caminos: %r" % (cadenas,))

    # 12. Encadenar: dos caminos separados dan dos cadenas.
    cadenas, _ = encadenar([(0, 1), (1, 2), (10, 11)])
    comprobacion(sorted(cadenas) == [[0, 1, 2], [10, 11]],
                 "dos caminos: %r" % (cadenas,))

    # 13. Encadenar: un ciclo cerrado se informa, no se endereza.
    cadenas, motivos = encadenar([(0, 1), (1, 2), (2, 0)])
    comprobacion(cadenas == [] and any("ciclo" in m for m in motivos),
                 "un triangulo cerrado no es una linea: %r %r"
                 % (cadenas, motivos))

    # 14. Entrada vacia: nada, sin excepcion.
    comprobacion(encadenar([]) == ([], []), "sin aristas tiene que dar vacio")

    # 15. Calibracion: cuenta por tope y percentiles, con numeros a mano.
    #     Desvios 0 / 1 / 2 / 4 sobre un alto de 4 -> fracciones 0 / 0,25 /
    #     0,5 / 1,0.
    cal = calibracion([0.0, 1.0, 2.0, 4.0], 4.0, topes=(0.3, 0.5, 1.0))
    comprobacion(cal["n_cadenas"] == 4, "cuatro cadenas: %r" % (cal,))
    comprobacion(cal["min"] == 0.0 and cal["max"] == 1.0,
                 "min y max: %r" % (cal,))
    comprobacion(cal["por_tope"] == {"0.3000": 2, "0.5000": 3, "1.0000": 4},
                 "el conteo por tope: %r" % (cal["por_tope"],))
    # Un tope mas chico que todo el mundo no califica a nadie.
    comprobacion(calibracion([1.0], 4.0, topes=(0.1,))["por_tope"]
                 == {"0.1000": 0}, "nadie califica con tope chico")
    # Sin datos o sin escala no hay informe: se devuelve None, no un dict vacio.
    comprobacion(calibracion([], 4.0) is None, "sin desvios, None")
    comprobacion(calibracion([1.0], 0.0) is None, "sin alto, None")

    # 16. Los puntos intermedios quedan ordenados a lo largo (no se cruzan).
    escalonada = [(0.0, 0.0, 0.0), (1.0, 0.02, 0.0), (2.0, 0.0, 0.0),
                  (3.0, -0.02, 0.0), (4.0, 0.0, 0.0)]
    nuevos, _ = enderezar(escalonada, 0.05)
    xs = [p[0] for p in nuevos]
    comprobacion(xs == sorted(xs) and len(set(xs)) == len(xs),
                 "los puntos intermedios se desordenaron: %r" % (xs,))

    print("autotest: %d comprobaciones, %d fallas" % (n, len(fallas)))
    for f in fallas:
        print("  FALLA %s" % f)
    return len(fallas)


def main():
    import sys
    if "--autotest" in sys.argv:
        raise SystemExit(1 if autotest() else 0)
    print(__doc__)


if __name__ == "__main__":
    main()
