# -*- coding: utf-8 -*-
"""El plugin terminado, leído de vuelta desde el disco.

POR QUÉ EXISTE ESTO. El `.esl` del hacha de Tencent salió con `formVersion = 0`
en sus tres records. El juego **no dio error**: cargó el plugin, el arma
apareció en el inventario y el VALOR se leyó bien — pero el PESO y el DAÑO
salieron en cero. El motor parsea el `DATA` de un `WEAP` con un layout distinto
según ese campo, y el único síntoma fue un número mal en una pantalla. Costó una
vuelta entera de "instalá y probá".

Ningún script del repo leía un plugin terminado para comprobarlo. `escritor_plugin`
pone 44 por defecto, que está bien, pero nada ataja al que escribe los bytes a
mano — que es exactamente lo que había pasado.

LA REGLA Y SU SUBCONJUNTO. Medir `formVersion` sobre el corpus entero da **7,65 %
en 44** e invita a la conclusión opuesta: que 44 es raro. Eso mezcla dos cosas.
Los masters de 2011 llevan, record por record, la versión de la última vez que
alguien lo tocó — hay records que nadie tocó desde la 14. Los 5 plugins que
Bethesda **autoró para SE** (Creation Club y `_ResourcePack`) están en 44 los
**10.273**, sin una excepción. La pregunta no era "qué hay en el corpus" sino
"qué escribe el CK de SE al crear un record", y ahí el subconjunto correcto es el
segundo. Es la tercera vez en el proyecto que un subconjunto mal elegido invierte
la respuesta (antes: `bhkRadius` y la máscara especular).
"""
import contextlib
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from _paths import preparar_path

preparar_path()

import escritor_plugin as ep  # noqa: E402
import plugin_sintetico  # noqa: E402
import verificar_plugin as vp  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "asset-nuevo-skyrim", "scripts", "verificar_plugin.py")


def _info(records=None, n_masters=0):
    """Un plugin descrito, sin tocar bytes: lo que `juzgar` recibe."""
    if records is None:
        records = [{"tipo": "STAT", "form_id": 0x00000801, "version": 44}]
    return {"records": records, "n_masters": n_masters, "error": None}


def _rec(version=44, form_id=0x00000801, tipo="STAT"):
    return {"tipo": tipo, "form_id": form_id, "version": version}


class ReglaVersionTests(unittest.TestCase):

    def test_un_plugin_en_44_no_tiene_fallas(self):
        self.assertEqual(vp.juzgar(_info())[0], [])

    def test_version_cero_reprueba(self):
        """El caso REAL. Es la regresión del hacha: sin esto, vuelve."""
        fallas, _ = vp.juzgar(_info([_rec(version=0)]))
        self.assertTrue(any("formVersion" in f for f in fallas),
                        "el 0 que costó una vuelta entera no reprobó: %r"
                        % fallas)

    def test_toda_version_anterior_a_la_actual_reprueba(self):
        """Enumerante, no escrito a mano para el 0: cualquier versión que no
        sea la actual describe un layout distinto del que realmente escribimos,
        y el motor va a leer los campos corridos. El 39 importa tanto como el 0
        — es la versión más común del corpus, así que es la que un donante mal
        copiado te deja puesta."""
        for v in range(0, vp.VERSION_ACTUAL):
            with self.subTest(version=v):
                fallas, _ = vp.juzgar(_info([_rec(version=v)]))
                self.assertTrue(
                    any("formVersion" in f for f in fallas),
                    "formVersion %d no reprobó" % v)

    def test_una_version_por_encima_de_la_actual_tambien_reprueba(self):
        """44 es el máximo de los 1.188.821 records del corpus: no existe un 45.
        Un número mayor no es "más nuevo", es un campo escrito mal."""
        fallas, _ = vp.juzgar(_info([_rec(version=vp.VERSION_ACTUAL + 1)]))
        self.assertTrue(any("formVersion" in f for f in fallas))

    def test_la_falla_dice_que_record_fue(self):
        """Un plugin tiene varios records y el mensaje tiene que servir para
        arreglarlo, no solo para reprobar.

        Los FormID son los del hacha, así que los masters también: 3. La
        primera versión de este test dejó `n_masters=0` y la REGLA 2 lo
        reprobó con razón -- índice 3 sin masters apunta a la nada--."""
        fallas, _ = vp.juzgar(_info(
            [_rec(tipo="STAT", form_id=0x03000801),
             _rec(tipo="WEAP", form_id=0x03000800, version=0)],
            n_masters=3))
        self.assertEqual(len(fallas), 1)
        self.assertIn("WEAP", fallas[0])
        self.assertIn("03000800", fallas[0].upper())

    def test_muchos_records_rotos_no_dan_una_falla_por_cada_uno(self):
        """`Skyrim.esm` tiene 1,1 millones de records fuera de 44 --
        legítimos, son de 2011--. Una falla por record son 1,1 M de strings.
        El detalle se corta, pero el TOTAL tiene que ser el verdadero: un
        resumen que cuenta de menos es otra forma de mentir.

        El 50 y el 11 van LITERALES y no `vp.LIMITE_DETALLE`. La primera
        versión armaba `n = LIMITE_DETALLE * 5` y acotaba con
        `LIMITE_DETALLE + 1`: mutar la constante a 99999 movía la sonda y el
        test seguía verde. Lo encontró una revisión; es el mismo patrón que
        test_proporciones_arma castiga con su 9e-5."""
        fallas, _ = vp.juzgar(_info(
            [_rec(version=0, form_id=0x800 + i) for i in range(50)]))
        self.assertLessEqual(len(fallas), 11,
                             "50 records rotos dieron %d fallas" % len(fallas))
        self.assertIn("50 records en total", fallas[-1])

    def test_el_TES4_tambien_esta_sujeto_a_la_regla(self):
        """El hacha tenía 0 también en el TES4, y los 10.273 records medidos
        incluyen los 5 TES4. Nada lo fijaba: el test de punta a punta pone
        TODOS en 0 y reprueba igual por el STAT, así que eximir al TES4 dejaba
        la suite y el --autotest en verde. Lo encontró una revisión."""
        fallas, _ = vp.juzgar(_info([_rec(tipo="TES4", form_id=0, version=0),
                                     _rec(tipo="STAT")]))
        self.assertEqual(len(fallas), 1, fallas)
        self.assertIn("TES4", fallas[0])

    def test_un_record_sano_entre_rotos_no_se_reporta(self):
        fallas, _ = vp.juzgar(_info(
            [_rec(tipo="STAT", version=0), _rec(tipo="WEAP", version=44)]))
        self.assertEqual(len(fallas), 1)
        self.assertNotIn("WEAP", fallas[0])


class ReglaIndiceDeModTests(unittest.TestCase):
    """El byte alto del FormID dice de qué plugin de la lista de carga sale el
    record. Con N masters, el índice N es *este* plugin y todo índice menor
    apunta a un master. Un índice mayor apunta a un master que no existe."""

    def test_el_indice_igual_a_los_masters_es_el_record_propio(self):
        self.assertEqual(
            vp.juzgar(_info([_rec(form_id=0x03000800)], n_masters=3))[0], [])

    def test_un_indice_menor_es_override_y_pasa(self):
        for i in range(0, 3):
            with self.subTest(indice=i):
                self.assertEqual(
                    vp.juzgar(_info([_rec(form_id=(i << 24) | 0x800)],
                                    n_masters=3))[0], [])

    def test_un_indice_por_encima_de_los_masters_reprueba(self):
        for i in range(4, 9):
            with self.subTest(indice=i):
                fallas, _ = vp.juzgar(
                    _info([_rec(form_id=(i << 24) | 0x800)], n_masters=3))
                self.assertTrue(any("índice de mod" in f for f in fallas),
                                "índice %d con 3 masters no reprobó" % i)

    def test_sin_masters_solo_el_indice_cero_pasa(self):
        self.assertEqual(vp.juzgar(_info([_rec(form_id=0x00000801)],
                                         n_masters=0))[0], [])
        fallas, _ = vp.juzgar(_info([_rec(form_id=0x01000801)], n_masters=0))
        self.assertTrue(any("índice de mod" in f for f in fallas))


class LecturaTests(unittest.TestCase):
    """`leer` sobre bytes de verdad, no sobre un dict escrito a mano."""

    def _escribir(self, datos):
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, datos)
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        return ruta

    def test_lee_el_sintetico_sano(self):
        datos, esperado = plugin_sintetico.construir()
        info = vp.leer(self._escribir(datos))
        self.assertIsNone(info["error"])
        self.assertEqual(len(info["records"]), 3)   # TES4 + STAT + ACTI
        self.assertEqual(set(r["version"] for r in info["records"]), {44})
        self.assertEqual(vp.juzgar(info)[0], [])

    def test_cuenta_los_masters_del_TES4(self):
        datos, _ = plugin_sintetico.construir(
            masters=("Skyrim.esm", "Update.esm"))
        self.assertEqual(vp.leer(self._escribir(datos))["n_masters"], 2)

    def test_un_sintetico_en_version_cero_lo_agarra_de_punta_a_punta(self):
        """El camino completo: bytes -> leer -> juzgar. Los tests de `juzgar`
        solos no prueban que `leer` saque el campo del offset correcto."""
        datos, _ = plugin_sintetico.construir(version=0)
        info = vp.leer(self._escribir(datos))
        self.assertIsNone(info["error"])
        fallas, _ = vp.juzgar(info)
        self.assertTrue(any("formVersion" in f for f in fallas), fallas)

    def test_un_archivo_truncado_da_error_y_no_pasa(self):
        """Si el recorrido no embaldosa el archivo, no hay nada que juzgar: eso
        ya es una falla, no un 'no se pudo medir'."""
        datos, _ = plugin_sintetico.construir()
        info = vp.leer(self._escribir(datos[:-40]))
        self.assertIsNotNone(info["error"])
        self.assertTrue(vp.juzgar(info)[0])

    def test_un_archivo_que_no_es_plugin_da_error(self):
        info = vp.leer(self._escribir(b"no soy un plugin" * 40))
        self.assertIsNotNone(info["error"])
        self.assertTrue(vp.juzgar(info)[0])

    def test_embaldosa_perfecto_pero_sin_TES4_da_error_por_el_TES4(self):
        """El test de arriba no alcanza: a esa basura la ataja el RECORRIDO, que
        no cierra, así que sacar el chequeo del TES4 lo dejaba verde. Lo probó
        una mutación. Hace falta el caso que SOLO ese guard ataja: los mismos
        bytes de un plugin sano, con el TES4 renombrado. Los tamaños no cambian,
        el recorrido cierra, y sin el TES4 el motor no lo carga.

        Se afirma la RAZÓN, no solo que haya error."""
        datos, _ = plugin_sintetico.construir()
        torcido = b"WEAP" + datos[4:]
        info = vp.leer(self._escribir(torcido))
        self.assertIsNotNone(info["error"], "un plugin sin TES4 pasó")
        self.assertIn("TES4", info["error"])


class ReglasWeapTests(unittest.TestCase):
    """Lo que mide el corpus sobre las 3.359 WEAP vanilla: DATA de 10 bytes y
    DNAM de 100 en todas, y el WNAM de las 463 armas base que lo tienen
    apunta siempre a un STAT. Se prueba sobre BYTES, no sobre dicts: la
    regla vale lo que vale la lectura del subrecord."""

    def _juzgar(self, **kw):
        datos, esperado = plugin_sintetico.construir_weap(**kw)
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, datos)
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        info = vp.leer(ruta)
        self.assertIsNone(info["error"])
        return vp.juzgar(info), esperado

    def test_un_arma_sana_no_tiene_fallas(self):
        (fallas, notas), _ = self._juzgar()
        self.assertEqual(fallas, [])
        self.assertTrue(any("1 WEAP" in n for n in notas), notas)

    def test_un_data_que_no_mide_10_reprueba(self):
        for n in (8, 12, 14):
            with self.subTest(data=n):
                (fallas, _), _ = self._juzgar(data_len=n)
                self.assertTrue(any("REGLA WEAP DATA" in f for f in fallas),
                                fallas)

    def test_un_dnam_que_no_mide_100_reprueba(self):
        for n in (96, 104):
            with self.subTest(dnam=n):
                (fallas, _), _ = self._juzgar(dnam_len=n)
                self.assertTrue(any("REGLA WEAP DNAM" in f for f in fallas),
                                fallas)

    def test_un_wnam_propio_que_no_existe_reprueba(self):
        """Se afirma la RAZON. Sin la rama de "no existe", el caso caia en la
        de "no es un STAT" y reprobaba igual diciendo "es un None": el test
        que solo pedia el marcador lo dejaba pasar. Lo encontro una mutacion."""
        (fallas, _), _ = self._juzgar(wnam="roto")
        self.assertTrue(any("REGLA WEAP WNAM" in f and "no existe" in f
                            for f in fallas), fallas)

    def test_un_wnam_propio_que_no_es_un_stat_reprueba(self):
        (fallas, _), _ = self._juzgar(wnam="a_si_mismo")
        self.assertTrue(any("REGLA WEAP WNAM" in f and "STAT" in f
                            for f in fallas), fallas)

    def test_un_wnam_a_un_master_no_se_puede_juzgar_y_lo_dice(self):
        (fallas, notas), _ = self._juzgar(wnam="master")
        self.assertEqual(fallas, [])
        self.assertTrue(any("master" in n and "WNAM" in n for n in notas),
                        notas)

    def test_sin_wnam_es_observacion_no_falla(self):
        """Las 9 armas vanilla sin WNAM son conjuradas, maniquies o de mision:
        no hay base para reprobar, pero se avisa."""
        (fallas, notas), esperado = self._juzgar(wnam=None)
        self.assertEqual(fallas, [])
        fid = "%08X" % esperado["fid_weap"]
        self.assertTrue(any("sin WNAM" in n and fid in n for n in notas),
                        "ninguna nota nombra al arma %s: %r" % (fid, notas))

    def test_subrecords_que_no_embaldosan_el_record_no_se_juzgan(self):
        """La identidad del repo, un nivel mas abajo: si los subrecords no
        cierran exacto en el fin del record, un tamano declarado miente y
        cualquier lectura de DATA o DNAM es de bytes corridos. Eso es un
        error de lectura, no un arma que pasa."""
        for n in (1, 3, 5):
            with self.subTest(basura=n):
                datos, _ = plugin_sintetico.construir_weap(basura=n)
                fd, ruta = tempfile.mkstemp(suffix=".esp")
                os.write(fd, datos)
                os.close(fd)
                self.addCleanup(os.unlink, ruta)
                info = vp.leer(ruta)
                self.assertIsNotNone(info["error"],
                                     "%d bytes sueltos pasaron" % n)
                self.assertIn("embaldosan", info["error"])
                self.assertTrue(vp.juzgar(info)[0])

    def test_la_regla_ve_adentro_de_un_record_comprimido(self):
        (fallas, _), _ = self._juzgar(data_len=12, comprimir=True)
        self.assertTrue(any("REGLA WEAP DATA" in f for f in fallas), fallas)

    def test_la_regla_sobrevive_al_escape_xxxx(self):
        (fallas, _), _ = self._juzgar(con_escape=True)
        self.assertEqual(fallas, [])
        (fallas, _), _ = self._juzgar(con_escape=True, dnam_len=96)
        self.assertTrue(any("REGLA WEAP DNAM" in f for f in fallas), fallas)


class LectorDeSubrecordsTests(unittest.TestCase):
    """El script de la skill no puede importar census/ (build_skill.py no lo
    empaqueta), asi que lleva su propio lector de subrecords. Este test lo
    ata al de census/parser_esm.py sobre los mismos bytes: si uno cambia y el
    otro no, se entera aca, no en el juego."""

    def test_coincide_con_parser_esm(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        from census.parser_esm import Plugin
        for kw in ({}, {"comprimir": True}, {"con_escape": True},
                   {"con_escape": True, "comprimir": True}):
            with self.subTest(**kw):
                datos, _ = plugin_sintetico.construir_weap(**kw)
                fd, ruta = tempfile.mkstemp(suffix=".esp")
                os.write(fd, datos)
                os.close(fd)
                try:
                    p = Plugin(ruta)
                    for tipo, off, _tam, _prof in p.recorrer():
                        if tipo in ("GRUP",):
                            continue
                        censo = [(t, bytes(b)) for t, b
                                 in Plugin.subrecords(p.datos(off))]
                        mio = [(t, bytes(b)) for t, b
                               in vp.subrecords(datos, off)]
                        self.assertEqual(mio, censo, tipo)
                finally:
                    os.unlink(ruta)


class ReglasDelMundoTests(unittest.TestCase):
    """REGLAS 5, 6 y 7 sobre BYTES, con la anidacion de grupos de un plugin
    real: el tipo de grupo sale del recorrido, no de un dict escrito a mano.

    Medido el 2026-09-25 sobre los 10 plugins oficiales: 59.240 referencias
    en grupos 8, todas con 0x400; 820.513 en grupos 9, ninguna. El REFR de
    RetreteVIP v1.1 (grupo 8, banderas 0) no aparecio en el juego."""

    def _juzgar(self, **kw):
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, plugin_sintetico.construir_mundo(**kw))
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        info = vp.leer(ruta)
        self.assertIsNone(info["error"])
        return vp.juzgar(info)

    def test_el_v12_pasa(self):
        fallas, notas = self._juzgar()
        self.assertEqual(fallas, [])
        self.assertTrue(any("1 referencia" in n for n in notas), notas)

    def test_el_v11_reprueba_por_cada_una_de_sus_tres_razones(self):
        fallas, notas = self._juzgar(banderas_ref=0, ofst=[57966, 393059],
                                     rnam=40, full=b" L\x00\x00")
        for marca in ("REGLA referencia persistente", "REGLA WRLD OFST",
                      "REGLA FULL"):
            with self.subTest(regla=marca):
                self.assertTrue(any(marca in f for f in fallas), fallas)
        self.assertTrue(any("40 RNAM" in n for n in notas), notas)

    def test_refr_en_grupo_8_sin_la_bandera_reprueba_y_dice_cual(self):
        fallas, _ = self._juzgar(banderas_ref=0)
        self.assertEqual(len(fallas), 1, fallas)
        self.assertIn("01000801", fallas[0])
        self.assertIn("grupo 8", fallas[0])

    def test_refr_en_grupo_9_con_la_bandera_reprueba(self):
        fallas, _ = self._juzgar(grupo_ref=9, banderas_ref=0x400)
        self.assertTrue(any("grupo 9" in f for f in fallas), fallas)

    def test_refr_en_grupo_9_sin_la_bandera_pasa(self):
        """El par de los dos de arriba."""
        self.assertEqual(self._juzgar(grupo_ref=9, banderas_ref=0)[0], [])

    def test_el_ofst_dentro_del_archivo_es_observacion(self):
        fallas, notas = self._juzgar(ofst=[24])
        self.assertEqual(fallas, [])
        self.assertTrue(any("OFST" in n for n in notas), notas)

    def test_un_ofst_que_no_mide_multiplo_de_4_no_se_lee(self):
        """Los 94 OFST oficiales miden multiplo de 4. Con 1 a 3 bytes de
        sobra, `len // 4` los tiraba y el OFST pasaba "todo adentro".
        Lo encontro la revision de Codex en el PR #92."""
        for sobra in (1, 2, 3):
            with self.subTest(sobra=sobra):
                crudo = bytearray(plugin_sintetico.construir_mundo(ofst=[24]))
                i = crudo.index(b"OFST")
                struct.pack_into("<H", crudo, i + 4, 4 + sobra)
                crudo[i + 10:i + 10] = b"\xAA" * sobra
                # el WRLD y el GRUP que lo contiene crecen lo mismo
                w = crudo.rindex(b"WRLD", 0, i)
                g = crudo.rindex(b"GRUP", 0, w)
                for o in (w, g):
                    struct.pack_into("<I", crudo, o + 4, struct.unpack_from(
                        "<I", crudo, o + 4)[0] + sobra)
                fd, ruta = tempfile.mkstemp(suffix=".esp")
                os.write(fd, bytes(crudo))
                os.close(fd)
                self.addCleanup(os.unlink, ruta)
                info = vp.leer(ruta)
                self.assertIsNotNone(info["error"], "OFST +%d paso" % sobra)
                self.assertIn("OFST", info["error"])
                self.assertTrue(vp.juzgar(info)[0])

    def test_full_de_cuatro_bytes_sin_nul_reprueba(self):
        fallas, _ = self._juzgar(full=b"\x20\x4C\x01\x02")
        self.assertTrue(any("REGLA FULL" in f for f in fallas), fallas)

    def test_la_misma_full_en_un_plugin_localizado_pasa(self):
        self.assertEqual(self._juzgar(full=b" L\x00\x00",
                                      localizado=True)[0], [])

    def test_la_regla_ve_la_full_de_un_record_comprimido(self):
        """La FULL no se busca en los bytes crudos: comprimida no aparece."""
        datos = plugin_sintetico.construir_mundo(full=b"\x20\x4C\x01\x02")
        import zlib
        crudo = bytearray(datos)
        i = crudo.index(b"WRLD", crudo.index(b"WRLD") + 4)
        tam = struct.unpack_from("<I", crudo, i + 4)[0]
        cuerpo = bytes(crudo[i + 24:i + 24 + tam])
        nuevo = struct.pack("<I", len(cuerpo)) + zlib.compress(cuerpo)
        cab = bytearray(crudo[i:i + 24])
        struct.pack_into("<II", cab, 4, len(nuevo),
                         struct.unpack_from("<I", cab, 8)[0] | 0x00040000)
        delta = len(nuevo) - tam
        resto = crudo[:i] + cab + nuevo + crudo[i + 24 + tam:]
        # el GRUP WRLD de nivel superior crece lo mismo que el record
        g = resto.rindex(b"GRUP", 0, i)
        struct.pack_into("<I", resto, g + 4,
                         struct.unpack_from("<I", resto, g + 4)[0] + delta)
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, bytes(resto))
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        info = vp.leer(ruta)
        self.assertIsNone(info["error"], info["error"])
        fallas, _ = vp.juzgar(info)
        self.assertTrue(any("REGLA FULL" in f for f in fallas), fallas)


class RecorridoConGruposTests(unittest.TestCase):
    """esl.recorrer_con_grupos contra census/parser_esm.py, que valida la
    anidacion: el tipo de grupo de cada record tiene que ser el del GRUP
    que el censo ve como su padre."""

    def test_coincide_con_parser_esm(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        from census.parser_esm import Plugin
        import esl
        for g in (8, 9):
            datos = plugin_sintetico.construir_mundo(grupo_ref=g)
            fd, ruta = tempfile.mkstemp(suffix=".esp")
            os.write(fd, datos)
            os.close(fd)
            try:
                pila, censo = [], []
                for tipo, off, tam, prof in Plugin(ruta).recorrer():
                    del pila[prof:]
                    if tipo == "GRUP":
                        pila.append(struct.unpack_from("<i", datos,
                                                       off + 12)[0])
                    else:
                        censo.append((tipo.encode(), off,
                                      pila[-1] if pila else None))
            finally:
                os.unlink(ruta)
            mio, cerro = esl.recorrer_con_grupos(datos)
            self.assertTrue(cerro)
            self.assertEqual(mio, censo)
            self.assertIn((b"REFR", censo[-1][1], g), mio)

    def test_recorrer_records_no_cambio(self):
        import esl
        datos = plugin_sintetico.construir_mundo()
        con, _ = esl.recorrer_con_grupos(datos)
        sin, cerro = esl.recorrer_records(datos)
        self.assertTrue(cerro)
        self.assertEqual(sin, [(t, o) for t, o, _g in con])

    def test_un_record_que_cruza_el_borde_de_su_grupo_no_cierra(self):
        """El recorrido plano embaldosa igual; el anidado no: el grupo 8
        declara 8 bytes menos y el REFR queda mitad adentro."""
        import esl
        datos = bytearray(plugin_sintetico.construir_mundo())
        i = datos.rindex(b"GRUP")
        struct.pack_into("<I", datos, i + 4,
                         struct.unpack_from("<I", datos, i + 4)[0] - 8)
        self.assertFalse(esl.recorrer_con_grupos(bytes(datos))[1])


def _juzgar_bytes(caso, datos):
    """bytes -> archivo -> leer -> juzgar: el camino de un plugin de verdad."""
    fd, ruta = tempfile.mkstemp(suffix=".esl")
    os.write(fd, datos)
    os.close(fd)
    caso.addCleanup(os.unlink, ruta)
    info = vp.leer(ruta)
    caso.assertIsNone(info["error"], info["error"])
    return vp.juzgar(info)


class ReglaLayoutTests(unittest.TestCase):
    """REGLA 8: MODT, MO2T..MO5T y DMDT, y el DNAM de un STAT, con el layout
    de la version del record. Sobre BYTES: la regla vale lo que vale la
    lectura.

    El ESL de la issue #31 copio los subrecords de 8 STAT de Skyrim.esm, que
    son version 39, y los escribio con 44. El motor leyo el primer hash del
    MODT como encabezado y la extension "dds" como cantidad de texturas, y el
    juego se cerraba en la pantalla de Bethesda. Este verificador lo aprobaba:
    su unica regla sobre la version era la 1, que pide 44, y el v1 tenia 44."""

    V1 = dict(version=39, cabecera=44)     # los bytes de un 39, con 44

    def test_el_v1_de_la_31_reprueba_y_dice_cual(self):
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            **self.V1))
        capa = [f for f in fallas if "REGLA layout" in f]
        self.assertEqual(len(capa), 1, fallas)
        self.assertIn("STAT 01000800", capa[0])
        self.assertIn("su MODT ", capa[0])
        self.assertIn("su DNAM ", capa[0])

    def test_el_v1_pasaba_la_regla_1_y_ese_era_el_hueco(self):
        """"formVersion" a secas, y no "REGLA formVersion": es la marca con
        que los tests de la REGLA 1 la buscan, y ningun otro mensaje la puede
        llevar. La primera version del de la REGLA 8 la llevaba, y con eso
        sacar la REGLA 1 dejaba en verde test_un_plugin_en_version_cero_sale_uno:
        el sintetico en 0 reprueba tambien la 8."""
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            **self.V1))
        self.assertFalse(any("formVersion" in f for f in fallas), fallas)

    def test_el_mensaje_dice_lo_que_lee_el_motor(self):
        """Con los triples leidos como encabezado, "dds" es la cantidad de
        texturas: 7562340, los "unos 7,5 millones" de la trampa 26."""
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            **self.V1))
        self.assertTrue(any("7562340 texturas" in f for f in fallas), fallas)

    def test_el_v2_de_la_31_pasa_la_regla_8(self):
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=39))
        self.assertFalse(any("REGLA layout" in f for f in fallas), fallas)

    def test_la_conversion_de_bethesda_pasa_todo_y_la_nota_cuenta(self):
        """(2, n, 0) con los mismos triples y un DNAM de 12: como Update.esm y
        los DLC pasaron a 44 records 39 (trampa 26). La nota dice cuanto se
        comprobo, para que cero no pase por exito."""
        fallas, notas = _juzgar_bytes(
            self, plugin_sintetico.construir_estatico(version=44))
        self.assertEqual(fallas, [])
        self.assertTrue(any("2 subrecord(s) de layout" in n for n in notas),
                        notas)
        # la nota de las copias es para los de antes de la 44
        self.assertFalse(any("pasan la REGLA 8" in n for n in notas), notas)

    def test_cada_subrecord_de_hashes_se_juzga(self):
        """Enumerante sobre la familia, en un ACTI: su DNAM no es el de un
        STAT, asi que la falla es del subrecord de hashes y de nada mas."""
        for sub in vp.TEXTURAS_DEL_MODELO:
            with self.subTest(subrecord=sub):
                fallas, _ = _juzgar_bytes(
                    self, plugin_sintetico.construir_estatico(
                        sub_modelo=sub.encode("ascii"), tipo=b"ACTI",
                        **self.V1))
                capa = [f for f in fallas if "REGLA layout" in f]
                self.assertEqual(len(capa), 1, fallas)
                self.assertIn("su %s " % sub, capa[0])
                self.assertNotIn("su DNAM", capa[0])

    def test_el_dnam_se_juzga_solo_en_un_stat(self):
        """8 bytes con 44 reprueba en un STAT; en otro tipo el DNAM es otra
        cosa (el de un WEAP mide 100) y no se mira."""
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=44, dnam=b"\x00" * 8))
        self.assertTrue(any("su DNAM " in f for f in fallas), fallas)
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=44, dnam=b"\x00" * 8, tipo=b"ACTI"))
        self.assertFalse(any("REGLA layout" in f for f in fallas), fallas)

    def test_un_encabezado_con_m_no_multiplo_de_3_reprueba_con_39(self):
        """La otra direccion, cuando se ve: (2, 2, 1) mide 40 bytes, que no
        es multiplo de 12."""
        modt = plugin_sintetico.modt_con_encabezado(extra=(7,))
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=39, modt=modt))
        self.assertTrue(any("REGLA layout" in f and "su MODT " in f
                            for f in fallas), fallas)

    def test_los_16_del_v1_dan_diez_con_detalle_y_el_total(self):
        """El v1 de la #31 tenia 16 STAT: el detalle se corta en 10, y el
        total tiene que ser el verdadero."""
        datos = plugin_sintetico.construir_estaticos([
            (b"STAT", plugin_sintetico.record_estatico(0x01000800 + i,
                                                        **self.V1))
            for i in range(16)])
        fallas, _ = _juzgar_bytes(self, datos)
        self.assertEqual(len([f for f in fallas if "REGLA layout" in f]),
                         10, fallas)
        self.assertIn("16 records en total", fallas[-1])

    def test_la_regla_ve_adentro_de_un_record_comprimido(self):
        """Comprimido, el MODT no aparece en los bytes crudos. El ACTI es el
        caso que importa: un STAT se abre siempre, por su tipo."""
        for tipo in (b"STAT", b"ACTI"):
            with self.subTest(tipo=tipo):
                fallas, _ = _juzgar_bytes(
                    self, plugin_sintetico.construir_estatico(
                        comprimir=True, tipo=tipo, **self.V1))
                self.assertTrue(any("REGLA layout" in f and "su MODT " in f
                                    for f in fallas), fallas)

    def test_un_stat_sin_modt_tambien_se_juzga(self):
        """118 STAT vanilla son EDID+OBND+MODL+DNAM, sin MODT (hallazgo 3 de
        census/hallazgos_plugins.md): el STAT se abre por su tipo, no porque
        sus bytes nombren un MODT."""
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=44, modt=None, dnam=b"\x00" * 8))
        self.assertTrue(any("REGLA layout" in f and "su DNAM " in f
                            for f in fallas), fallas)


class LaRegla1SeQuedaTests(unittest.TestCase):
    """La decision (docstring de verificar_plugin.py, REGLA 1): un record
    anterior a la 44 que pasa la REGLA 8 -- los 16 STAT del mod de la #31 --
    sigue reprobando la REGLA 1. La 8 no alcanza para eximirlo: solo ve
    MODT..DMDT y el DNAM de un STAT, y lo que no ve, pasa. Estos tests son
    ese porque. Si alguien relaja la REGLA 1 confiando en la 8, se ponen
    rojos."""

    def test_el_hacha_del_20_9_pasa_la_regla_8(self):
        """La forma del ESL del hacha del 20/9, medida: el WEAP en version 0
        con un MODT (2, 0, 0) -- el encabezado de la 44 sin texturas --, que
        con 0 mide lo que un triple. Su DATA, que el juego leyo con peso y
        dano 0, mide 10 bytes con los dos layouts. La REGLA 8 lo pasa; la
        unica que lo agarra es la 1. Y la nota no dice que se lea bien: la
        primera version decia "tienen el layout de su propia version"."""
        datos, esperado = plugin_sintetico.construir_weap(
            version=0, modt=struct.pack("<III", 2, 0, 0))
        fallas, notas = _juzgar_bytes(self, datos)
        self.assertFalse(any("REGLA layout" in f for f in fallas), fallas)
        fid = "%08X" % esperado["fid_weap"]
        self.assertTrue(any("REGLA formVersion" in f and fid in f
                            for f in fallas), fallas)
        nota = [n for n in notas if "pasan la REGLA 8" in n]
        self.assertEqual(len(nota), 1, notas)
        self.assertIn("No prueba que se lean bien", nota[0])

    def test_un_modt_de_44_escrito_con_39_pasa_la_regla_8(self):
        """(2, n, 0) mide 12 + 12n, multiplo de 12, y con 39 se lee como
        triples: la REGLA 8 no lo distingue. Son 23.563 de los 23.815 MODT de
        version >= 40 de los 10 plugins (m multiplo de 3)."""
        fallas, _ = _juzgar_bytes(self, plugin_sintetico.construir_estatico(
            version=39, modt=plugin_sintetico.modt_con_encabezado(),
            tipo=b"ACTI"))
        self.assertFalse(any("REGLA layout" in f for f in fallas), fallas)
        self.assertTrue(any("formVersion" in f for f in fallas), fallas)

    def test_el_v2_de_la_31_reprueba_la_1_y_la_nota_dice_por_que(self):
        """Reprueba por la REGLA 1, no por la 8, y la nota lo distingue del
        v1: que no se confunda la copia bien hecha con la que cerraba el
        juego."""
        fallas, notas = _juzgar_bytes(
            self, plugin_sintetico.construir_estatico(version=39))
        self.assertTrue(any("formVersion" in f for f in fallas), fallas)
        self.assertTrue(any(n.startswith("OBS 1 record(s) de version "
                                         "anterior a la 44 pasan la REGLA 8")
                            and "REGLA 1" in n for n in notas), notas)

    def test_la_nota_no_cuenta_un_record_sin_nada_que_ver(self):
        """Un WEAP sin MODT no tiene subrecords de layout: la REGLA 8 no lo
        comprobo, y la nota no lo cuenta como que la pasa."""
        datos, _ = plugin_sintetico.construir_weap(version=0)
        _, notas = _juzgar_bytes(self, datos)
        self.assertFalse(any("pasan la REGLA 8" in n for n in notas), notas)


class LayoutComoElEscritorTests(unittest.TestCase):
    """verificar_plugin.py no puede importar census/ (build_skill.py no lo
    empaqueta): lleva su copia de las leyes de
    census/escritor_plugin.comprobar_layout. Este test ata las dos -- las
    mismas constantes, y el mismo veredicto sobre los mismos bytes --, para
    que no haya un plugin que el escritor acepta y el verificador reprueba,
    ni al reves."""

    def test_la_familia_es_exactamente_la_medida(self):
        """El ancla. Los 6 subrecords de hashes y los dos umbrales, LITERALES
        y en las dos copias: son los medidos (11.526 + 23.815 subrecords, 711
        + 11.915 DNAM de STAT, census/hallazgos_plugins.md entrada 19).
        Compararlas entre si no alcanzaba: un septimo agregado a las dos
        pasaba sin que nadie lo midiera.

        Romperlo no se arregla agregando el nombre aca. Un subrecord nuevo en
        la familia pide medirlo en los 10 plugins (--falsificar reimprime los
        conteos), escribir su ley en las DOS copias -- comprobar_layout y
        layout_ajeno -- y recien entonces sumarlo a esta lista."""
        familia = ("MODT", "MO2T", "MO3T", "MO4T", "MO5T", "DMDT")
        self.assertEqual(vp.TEXTURAS_DEL_MODELO, familia)
        self.assertEqual(ep.TEXTURAS_DEL_MODELO,
                         tuple(t.encode("ascii") for t in familia))
        for copia in (vp, ep):
            with self.subTest(copia=copia.__name__):
                self.assertEqual(copia.VERSION_MODT_CON_ENCABEZADO, 40)
                self.assertEqual(copia.VERSION_DNAM_STAT_DE_12, 44)

    def test_el_mismo_veredicto_sobre_los_mismos_bytes(self):
        t = plugin_sintetico.MODT_TRIPLES
        enc = plugin_sintetico.modt_con_encabezado
        cargas = [b"", b"\x00" * 4, b"\x00" * 8, b"\x00" * 12, t[:12], t,
                  t + b"\x00" * 4, enc(), enc(extra=(7,)),
                  enc(extra=(7, 8, 9)), enc(t[:12]), enc(b""),
                  struct.pack("<III", 3, 0, 0),
                  struct.pack("<III", 2, 3, 0) + t, b"\x00" * 100]
        veredictos = {True: 0, False: 0}
        # Ademas de la familia, subrecords que NO la son y que todo STAT o
        # WEAP lleva: una ley nueva en una sola copia, como la del DNAM, se ve
        # como un veredicto distinto.
        otros = ("DNAM", "OBND", "MNAM", "DATA", "EDID", "MODL", "MODS")
        for version in list(range(0, 46)) + [0xFFFF]:
            for tipo in ("STAT", "ACTI", "WEAP"):
                for sub in vp.TEXTURAS_DEL_MODELO + otros:
                    for datos in cargas:
                        mio = vp.layout_ajeno(tipo, sub, datos,
                                              version) is None
                        try:
                            ep.comprobar_layout(tipo.encode("ascii"),
                                                ep.sub(sub, datos), version)
                            suyo = True
                        except ep.ErrorPlugin:
                            suyo = False
                        if mio != suyo:
                            self.fail("%s %s de %d bytes con version %d: el "
                                      "verificador %s y el escritor %s"
                                      % (tipo, sub, len(datos), version,
                                         "pasa" if mio else "reprueba",
                                         "pasa" if suyo else "reprueba"))
                        veredictos[mio] += 1
        # El par: una enumeracion que diera siempre lo mismo no ataria nada.
        self.assertGreater(veredictos[True], 1000, veredictos)
        self.assertGreater(veredictos[False], 1000, veredictos)


class FalsificarLayoutTests(unittest.TestCase):
    """--falsificar sobre una carpeta Data SINTETICA. El CI no tiene el
    juego: sin esto, la parte de la REGLA 8 de --falsificar no corre nunca
    ahi. La corrida sobre los 10 plugins esta en
    census/hallazgos_plugins.md, entrada 19."""

    def _data(self, extra=None):
        ps = plugin_sintetico
        archivos = {
            "Mundo.esp": ps.construir_mundo(),
            # autorado para SE: sirve de patron entero
            "Nuevo.esl": ps.construir_estaticos([
                (b"STAT", ps.record_estatico(0x01000800 + i, version=44))
                for i in range(2)]),
            # como un master de 2011: la REGLA 1 no vale, la 8 si. La rotura
            # de la #31 cae en el del medio de los tres de version 39, el STAT
            # 803, que con 44 reprueba por el MODT y por el DNAM: como el
            # 0007219F de Skyrim.esm en la corrida sobre el juego
            "Viejo.esm": ps.construir_estaticos([
                (b"STAT", ps.record_estatico(0x800, version=39)),
                (b"STAT", ps.record_estatico(
                    0x801, version=43,
                    modt=ps.modt_con_encabezado(extra=(7,)))),
                (b"STAT", ps.record_estatico(0x803, version=39)),
                (b"ACTI", ps.record_estatico(0x802, version=39,
                                             tipo=b"ACTI"))], masters=()),
        }
        archivos.update(extra or {})
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for nombre, datos in archivos.items():
            with open(os.path.join(tmp, nombre), "wb") as fh:
                fh.write(datos)
        return tmp

    def _falsificar(self, data):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = vp.falsificar(data)
        return codigo, salida.getvalue()

    def test_los_plugins_sanos_pasan_y_cada_rotura_reprueba(self):
        codigo, salida = self._falsificar(self._data())
        self.assertEqual(codigo, 0, salida)
        linea = next((x for x in salida.splitlines()
                      if x.strip().startswith("layout:")), None)
        self.assertIsNotNone(linea, salida)
        self.assertIn("0 excepciones", linea)

    def test_una_regla_8_muerta_no_pasa(self):
        """Por los dos caminos: el patron, que la corre dentro de juzgar
        como un plugin de verdad, y la pasada sola sobre todos."""
        with mock.patch.object(vp, "layout_ajeno", lambda *a: None):
            codigo, salida = self._falsificar(self._data())
        self.assertEqual(codigo, 1, salida)
        for rotura in ("Nuevo.esl / MODT..DMDT sin su encabezado",
                       "Nuevo.esl / DNAM de STAT de 8 bytes",
                       "Viejo.esm / STAT 00000803, de version < 40"):
            self.assertIn(rotura, salida)

    def test_sin_nada_que_torcer_no_es_exito(self):
        """Sin MODT..DMDT ni DNAM de STAT, la REGLA 8 no se comprobo: cero
        roturas no es exito."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "Mundo.esp"), "wb") as fh:
            fh.write(plugin_sintetico.construir_mundo())
        codigo, salida = self._falsificar(tmp)
        self.assertEqual(codigo, 1, salida)
        self.assertIn("MODT..DMDT o DNAM de STAT", salida)

    def test_cada_mitad_de_la_regla_tiene_su_rotura(self):
        """Sin el DNAM, las roturas del DNAM no reprueban; sin los hashes, la
        de la #31 no reprueba POR su MODT -- aunque reprueba igual, por el
        DNAM del STAT 803: el v1 de la #31 caia por los dos. Con "alguna
        falla" a secas esa rotura pasaba, y la mitad de los hashes podia
        estar muerta (lo encontro un mutante)."""
        real = vp.layout_ajeno
        esperadas = {
            "DNAM": "STAT de 40 a 43 escrito con 44: no reprobo por su DNAM",
            "MODT": "Viejo.esm / STAT 00000803, de version < 40, escrito con "
                    "44 (el ESL de la #31): no reprobo por su MODT"}
        for apagado, linea in esperadas.items():
            def parcial(tipo, sub, datos, version, apagado=apagado):
                if (sub == "DNAM") == (apagado == "DNAM"):
                    return None
                return real(tipo, sub, datos, version)
            with self.subTest(apagado=apagado), \
                    mock.patch.object(vp, "layout_ajeno", parcial):
                codigo, salida = self._falsificar(self._data())
                self.assertEqual(codigo, 1, salida)
                self.assertIn(linea, salida)

    def test_un_plugin_que_reprueba_tal_cual_no_pasa(self):
        """El v1 de la #31 en la carpeta: ahi la ley no vale, y medirla asi
        no es exito."""
        v1 = plugin_sintetico.construir_estatico(version=39, cabecera=44)
        codigo, salida = self._falsificar(self._data({"Prueba31.esl": v1}))
        self.assertEqual(codigo, 1, salida)
        self.assertIn("REGLA 8 tal cual", salida)


class LineaDeComandosTests(unittest.TestCase):

    def _correr(self, *args):
        p = subprocess.run([sys.executable, SCRIPT] + list(args),
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_autotest_pasa(self):
        codigo, salida = self._correr("--autotest")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("0 fallas", salida)

    def test_argumentos_que_no_sirven_dan_dos(self):
        self.assertEqual(self._correr()[0], 2)

    def test_un_plugin_sano_sale_cero(self):
        datos, _ = plugin_sintetico.construir()
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, datos)
        os.close(fd)
        try:
            codigo, salida = self._correr(ruta)
            self.assertEqual(codigo, 0, salida)
        finally:
            os.unlink(ruta)

    def test_un_plugin_en_version_cero_sale_uno(self):
        datos, _ = plugin_sintetico.construir(version=0)
        fd, ruta = tempfile.mkstemp(suffix=".esp")
        os.write(fd, datos)
        os.close(fd)
        try:
            codigo, salida = self._correr(ruta)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("formVersion", salida)
        finally:
            os.unlink(ruta)

    def test_el_v1_de_la_31_sale_uno(self):
        """El ESL que cerraba el juego en la pantalla de Bethesda: este
        script lo daba por bueno y salia con 0."""
        fd, ruta = tempfile.mkstemp(suffix=".esl")
        os.write(fd, plugin_sintetico.construir_estatico(version=39,
                                                         cabecera=44))
        os.close(fd)
        try:
            codigo, salida = self._correr(ruta)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA layout", salida)
        finally:
            os.unlink(ruta)

    def test_un_archivo_que_no_existe_no_sale_cero(self):
        codigo, _ = self._correr(os.path.join(tempfile.gettempdir(),
                                              "no-existe-jamas.esp"))
        self.assertNotEqual(codigo, 0)

    def test_falsificar_sobre_una_carpeta_vacia_no_es_exito(self):
        """Cero plugins utilizables = cero comprobaciones. Salir 0 ahí es
        exactamente el verde que no prueba nada."""
        vacia = tempfile.mkdtemp()
        try:
            codigo, salida = self._correr("--falsificar", vacia)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("no comprobar nada no es", salida)
        finally:
            os.rmdir(vacia)


if __name__ == "__main__":
    unittest.main()
