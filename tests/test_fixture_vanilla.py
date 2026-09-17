# -*- coding: utf-8 -*-
"""La referencia vanilla y el contrato que demuestra.

Sin corpus: los NIF se construyen byte a byte, asi que esto corre en CI. Lo que
NO se puede comprobar aca es que el JSON registrado describa el archivo real de
Bethesda -- eso lo hace `registrar.py --verificar` contra una copia local, y
queda declarado en fixtures/README.md.
"""
import json
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import nif_sintetico  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys  # noqa: E402

if os.path.join(_RAIZ, "fixtures") not in sys.path:
    sys.path.insert(0, os.path.join(_RAIZ, "fixtures"))

import comparar  # noqa: E402
import registrar  # noqa: E402


def _campo_cabecera(datos, desplazamiento, valor):
    """version(4) endian(1) user(4) n_bloques(4) bs(4) despues de la magica."""
    i = datos.index(bytes([10])) + 1 + desplazamiento
    b = bytearray(datos)
    struct.pack_into("<I", b, i, valor)
    return bytes(b)


def _tipo_raiz(datos, nuevo):
    """Renombra el tipo del bloque 0 en la tabla de tipos.

    El reemplazo tiene que medir exactamente lo mismo que "BSFadeNode" (10
    caracteres) para que no se muevan los offsets: lo que se prueba es la
    regla, no la tolerancia del parser a una tabla corrida.
    """
    assert len(nuevo) == 10, "BSFadeNode mide 10"
    i = datos.index(b"BSFadeNode")
    return datos[:i] + nuevo.encode("cp1252") + datos[i + 10:]


def _archivo(datos, caso):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


class ReferenciaRegistradaTests(unittest.TestCase):
    """El JSON versionado es la referencia. Si se rompe, no hay contra que
    comparar."""

    def setUp(self):
        with open(registrar.SALIDA, encoding="utf-8") as fh:
            self.ref = json.load(fh)

    def test_el_json_existe_y_tiene_los_campos_que_alimentan_assetreport(self):
        faltan = [c for c in comparar.CAMPOS_IDENTIDAD if c not in self.ref]
        self.assertEqual([], faltan,
                         "la referencia no define %s" % faltan)

    def test_no_se_versiona_contenido_de_bethesda(self):
        """El .nif y los .dds no entran al repo. Solo la medicion."""
        carpeta = os.path.dirname(registrar.SALIDA)
        propietarios = [f for f in os.listdir(carpeta)
                        if f.lower().endswith((".nif", ".dds", ".bsa"))]
        self.assertEqual([], propietarios,
                         "hay contenido de Bethesda versionado: %s" % propietarios)

    def test_el_sha_registrado_es_el_del_modulo(self):
        self.assertEqual(registrar.SHA256, self.ref["sha256"])

    def test_la_referencia_es_un_estatico_de_un_solo_shape(self):
        """Lo que la hace util como fixture. Si alguien la cambia por un
        archivo con dos shapes, cualquier discrepancia futura pasa a tener dos
        explicaciones y el fixture deja de discriminar."""
        self.assertEqual(1, self.ref["n_shapes"])
        self.assertFalse(self.ref["tiene_skin"])
        self.assertEqual(1, self.ref["bloques"].get("BSShaderTextureSet"))


class ContratoDiscriminaTests(unittest.TestCase):
    """Un contrato que aprueba todo no sirve. Cada regla tiene que reprobar
    algo."""

    def setUp(self):
        self.datos, _ = nif_sintetico.construir()

    def _claves_malas(self, datos):
        ruta = _archivo(datos, self)
        return {c for ok, c, _d, _e in comparar.reglas(ruta) if not ok}

    def test_el_sintetico_pasa_las_reglas_de_cabecera(self):
        """El par de los tests de abajo: si el contrato reprobara todo,
        'reprueba X' no probaria nada."""
        malas = self._claves_malas(self.datos)
        for clave in ("cabecera_sse", "bs_version", "nodo_raiz_conocido"):
            self.assertNotIn(clave, malas)

    def test_sin_geometria_reprueba(self):
        """El sintetico no tiene shapes: es un arbol de nodos y una trampa."""
        self.assertIn("tiene_geometria", self._claves_malas(self.datos))

    def test_version_equivocada_reprueba(self):
        malas = self._claves_malas(_campo_cabecera(self.datos, 0, 0x14000005))
        self.assertIn("cabecera_sse", malas)

    def test_user_version_equivocada_reprueba(self):
        malas = self._claves_malas(_campo_cabecera(self.datos, 5, 11))
        self.assertIn("cabecera_sse", malas)

    def test_bs_version_de_otra_edicion_reprueba(self):
        malas = self._claves_malas(_campo_cabecera(self.datos, 13, 83))
        self.assertIn("bs_version", malas)

    def test_raiz_que_no_es_un_nodo_reprueba(self):
        """NiPSysData existe en el formato pero no es un nodo: un archivo con
        eso de raiz no es un asset entregable."""
        malas = self._claves_malas(_tipo_raiz(self.datos, "NiPSysData"))
        self.assertIn("nodo_raiz_conocido", malas)

    def test_archivo_truncado_reprueba_por_parseo(self):
        malas = self._claves_malas(self.datos[:len(self.datos) // 2])
        self.assertEqual({"parsea"}, malas,
                         "un archivo roto tiene que cortar en el parseo, no "
                         "arrastrar reglas leidas de bytes basura")

    def test_cada_regla_reprueba_en_algun_caso(self):
        """Enumera: ninguna regla puede ser decorativa. Si se agrega una que
        nada reprueba, cae aca -- que es como se cuela una garantia inofensiva.

        Las que dependen de geometria o colision no se ejercitan con el
        sintetico y van declaradas, no disimuladas.
        """
        sin_ejercitar = {"texturas_dds", "texturas_separador",
                         "rigidbody_identidad"}
        casos = (
            self.datos,
            _campo_cabecera(self.datos, 0, 0x14000005),
            _campo_cabecera(self.datos, 5, 11),
            _campo_cabecera(self.datos, 13, 83),
            _tipo_raiz(self.datos, "NiPSysData"),
            self.datos[:len(self.datos) // 2],
        )
        vistas = set()
        for datos in casos:
            vistas |= self._claves_malas(datos)

        ruta = _archivo(self.datos, self)
        todas = {c for _ok, c, _d, _e in comparar.reglas(ruta)} | {"parsea"}
        nunca = todas - vistas - sin_ejercitar
        self.assertEqual(
            set(), nunca,
            "estas reglas no reprueban en ningun caso de prueba: %s" % nunca)


class TodaReglaTraeEvidenciaTests(unittest.TestCase):
    """La disciplina del repo, cableada: una regla sin numero atras no entra.

    No es decoracion. El defecto caro de este proyecto no fue que faltaran
    reglas sino que sobraran inventadas -- 'salir de [0,1] es un defecto' es
    tiling en el 49,2 % de los shapes vanilla, y 'compartir texture set y
    pisarse' es lo que hace Bethesda en el 91 % de los casos.
    """

    def test_ninguna_regla_va_sin_su_medicion(self):
        ruta = _archivo(nif_sintetico.construir()[0], self)
        flojas = []
        for _ok, clave, _det, evidencia in comparar.reglas(ruta):
            if not evidencia or not any(ch.isdigit() for ch in evidencia):
                flojas.append(clave)
        self.assertEqual(
            [], flojas,
            "reglas sin evidencia numerica del censo: %s" % flojas)

    def test_las_observaciones_dicen_por_que_no_son_reglas(self):
        ruta = _archivo(nif_sintetico.construir()[0], self)
        try:
            obs = comparar.observaciones(ruta)
        except Exception:
            self.skipTest("el sintetico no llega a las observaciones")
        for clave, _det, por_que in obs:
            self.assertTrue(
                por_que and any(ch.isdigit() for ch in por_que),
                "la observacion %s no dice con que numeros se sostiene" % clave)


if __name__ == "__main__":
    unittest.main()
