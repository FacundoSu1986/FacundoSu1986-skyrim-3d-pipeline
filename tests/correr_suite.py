# -*- coding: utf-8 -*-
"""La suite entera, y en CI un ancla sobre lo que se saltea.

Corre lo mismo que `python -m unittest discover -s tests -v` desde la raiz, y
sale con el mismo codigo. En CI (`CI` o `GITHUB_ACTIONS`), ademas, compara los
tests salteados contra SALTEADOS_EN_CI, por IGUALDAD: el id de cada test y el
motivo del salteo.

Por que existe: un test salteado no pone rojo nada. La comparacion del
frontmatter contra PyYAML se salteo en CI sin que nadie se enterara --la suite
decia "OK (skipped=11)"-- hasta que alguien leyo el log (PR #90 del repo). Los
guards por dependencia (numpy, Pillow, PyYAML) atajan a su hermano, no al
proximo. Esta lista ataja a cualquiera: un salteo nuevo, en cualquier archivo
y por cualquier motivo, pone rojo el paso.

Romperlo no se arregla agregando el test a la lista. Pide una decision:
  - una EXENCION CONSCIENTE, algo que el runner de CI no puede tener (hoy,
    solo Blender): va a la lista, con su motivo;
  - o un HUECO que el CI tiene que cerrar: instalar lo que falta en
    requirements-dev.txt, o arreglar la condicion que saltea.
Un test de la lista que deja de saltearse tambien rompe (si ahora corre, sale
de la lista), y un motivo distinto tambien (se saltea por otra cosa).

Fuera de CI no se compara: ahi se saltean ademas los test_en_ci_* y, en
Windows sin permiso para crear symlinks, tres de test_pipeline_staging.py.

    python tests/correr_suite.py
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(TESTS)

BLENDER = "requiere BLENDER_EXE; no se valido la API de Blender"
BLENDER_Y_PYNIFLY = "requiere BLENDER_EXE y PyNifly; no se valido"

# id del test -> motivo del salteo. Escrita a mano, copiada del log del CI de
# main (ubuntu, 3.11 y 3.12 dan los mismos 13): todos necesitan Blender, que el
# runner de CI no tiene.
SALTEADOS_EN_CI = {
    "test_al_marco_blender.AlMarcoEnBlenderTests.test_escudo_baja_y_alta_con_la_misma_matriz": BLENDER,
    "test_al_marco_blender.AlMarcoEnBlenderTests.test_falsificar": BLENDER,
    "test_al_marco_blender.AlMarcoEnBlenderTests.test_plan_sin_fijar_y_escala_negativa_reprueban": BLENDER,
    "test_desplegar_uv_blender.DesplegarUVEnBlenderTests.test_argumento_que_no_sirve_sale_con_2": BLENDER,
    "test_desplegar_uv_blender.DesplegarUVEnBlenderTests.test_falsificar": BLENDER,
    "test_desplegar_uv_blender.DesplegarUVEnBlenderTests.test_tres_mallas_un_atlas": BLENDER,
    "test_ejemplo_escudo_minimo.ConBlenderTests.test_cada_comprobacion_del_paso_6_puede_fallar": BLENDER_Y_PYNIFLY,
    "test_ejemplo_escudo_minimo.ConBlenderTests.test_de_cero_a_un_nif_verificado": BLENDER_Y_PYNIFLY,
    "test_ejemplo_escudo_minimo.ConBlenderTests.test_un_paso_que_falla_corta_la_cadena_con_1": BLENDER_Y_PYNIFLY,
    "test_exportar_nif_blender.ExportarNifEnBlenderTests.test_argumento_que_no_sirve_sale_con_2": BLENDER_Y_PYNIFLY,
    "test_exportar_nif_blender.ExportarNifEnBlenderTests.test_falsificar": BLENDER_Y_PYNIFLY,
    "test_uv_exportacion_blender.UVEnBlenderTests.test_conserva_atlas_en_mesh_real": BLENDER,
    "test_uv_exportacion_blender.UVEnBlenderTests.test_la_limpieza_vieja_falla": BLENDER,
}


def en_ci():
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def diferencias(salteados, esperados):
    """Una linea por cada test en que {id: motivo} salteado y esperado no
    coinciden. Vacia si son iguales."""
    lineas = ["sobra   %s: %r" % (i, salteados[i])
              for i in sorted(set(salteados) - set(esperados))]
    lineas += ["falta   %s: %r" % (i, esperados[i])
               for i in sorted(set(esperados) - set(salteados))]
    lineas += ["motivo  %s: %r, y en la lista %r" % (i, salteados[i], esperados[i])
               for i in sorted(set(salteados) & set(esperados))
               if salteados[i] != esperados[i]]
    return lineas


def correr(directorio=TESTS, esperados=None, comparar=None, flujo=None):
    """Corre los tests de `directorio` y devuelve el codigo de salida: 0 si
    pasaron y, cuando se compara, si ademas lo salteado es `esperados`."""
    esperados = SALTEADOS_EN_CI if esperados is None else esperados
    comparar = en_ci() if comparar is None else comparar
    flujo = sys.stderr if flujo is None else flujo
    suite = unittest.TestLoader().discover(directorio)
    # Los avisos como los deja `python -m unittest`: "default" si no hay -W.
    resultado = unittest.TextTestRunner(
        stream=flujo, verbosity=2,
        warnings=None if sys.warnoptions else "default").run(suite)
    codigo = 0 if resultado.wasSuccessful() else 1
    if not resultado.testsRun:
        flujo.write("Cero tests: no es verde.\n")
        codigo = 1
    salteados = {test.id(): motivo for test, motivo in resultado.skipped}
    if not comparar:
        flujo.write("Ancla de salteados: fuera de CI no se compara "
                    "(%d salteados).\n" % len(salteados))
        return codigo
    lineas = diferencias(salteados, esperados)
    if lineas:
        flujo.write("\nFAILED: los salteados no son los de SALTEADOS_EN_CI "
                    "(tests/correr_suite.py):\n  %s\n"
                    "Por cada uno: exencion consciente (va a la lista, con su "
                    "motivo) o hueco que el CI tiene que cerrar.\n"
                    % "\n  ".join(lineas))
        return 1
    flujo.write("Ancla de salteados: los %d son exactamente los de "
                "SALTEADOS_EN_CI.\n" % len(salteados))
    return codigo


if __name__ == "__main__":
    # `python -m unittest` corrido desde la raiz la deja en sys.path, detras
    # de tests/: los test_pipeline_* importan `pipeline` contando con eso.
    if RAIZ not in sys.path:
        sys.path.insert(1, RAIZ)
    sys.exit(correr())
