# -*- coding: utf-8 -*-
"""2026-10-19: tools/probar_halo.py convierte en herramienta la evaluacion de
halo que el 2026-10-18 se hizo a mano (docs/INTRO-Y-LOOP.md s3). Sin ffmpeg:
la caja de suavizado contra la cuenta a mano, la mascara del fondo oscuro, la
ondulacion (escalones si, tramado fino y degrade liso no), el sesgo de luma y
su alarma, las variantes por nombre/texto/crf, la lamina PNG (bytes validos y
deterministas) y que las lineas de comando no conviertan el color."""
import os
import struct
import sys
import unittest
import zlib

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_intro_loop  # noqa: E402
import emit_matrix  # noqa: E402
import emit_v2  # noqa: E402
import probar_halo as ph  # noqa: E402


def caja_a_mano(a, r):
    alto, ancho = a.shape
    p = np.pad(a.astype(np.float64), r, mode="edge")
    out = np.zeros((alto, ancho))
    for y in range(alto):
        for x in range(ancho):
            out[y, x] = p[y:y + 2 * r + 1, x:x + 2 * r + 1].mean()
    return out


def fondo(alto=96, ancho=160, valor=28.0):
    return np.full((alto, ancho), valor)


class CajaTest(unittest.TestCase):
    def test_igual_a_la_cuenta_a_mano_con_borde_extendido(self):
        a = np.random.RandomState(7).randint(0, 255, size=(13, 17))
        for r in (1, 3):
            np.testing.assert_allclose(ph.caja(a, r), caja_a_mano(a, r), atol=1e-9)

    def test_una_imagen_pareja_queda_igual(self):
        np.testing.assert_allclose(ph.caja(fondo(), 20), fondo(), atol=1e-9)


class MascaraTest(unittest.TestCase):
    def test_fondo_oscuro_si_negro_no_brillante_ni_su_entorno_tampoco(self):
        y = fondo()
        y[:, :20] = 16                      # negro de video: no es fondo con halo
        y[40:50, 120:130] = 200             # una particula
        m = ph.mascara_fondo(y)
        self.assertTrue(m[10, 70])
        self.assertFalse(m[10, 5])          # negro
        self.assertFalse(m[45, 125])        # la particula
        self.assertFalse(m[45, 100])        # a 20 px de la particula: demasiado cerca
        self.assertFalse(ph.mascara_fondo(fondo(valor=60)).any())   # no es oscuro


class OndulacionTest(unittest.TestCase):
    def setUp(self):
        # Lejos de los bordes izquierdo y derecho: ahi el borde extendido
        # dobla la rampa y la caja grande la sigue peor.
        self.m = np.zeros((96, 160), dtype=bool)
        self.m[:, 45:115] = True
        self.liso = np.tile(np.linspace(20, 30, 160), (96, 1))

    def test_escalones_si_degrade_liso_no(self):
        escalonado = np.floor(self.liso / 2.5) * 2.5        # pocos tonos: el halo
        o_liso = ph.ondulacion(self.liso, self.m).mean()
        o_esc = ph.ondulacion(escalonado, self.m).mean()
        self.assertLess(o_liso, 0.05)
        self.assertGreater(o_esc, 4 * o_liso + 0.2)

    def test_el_tramado_fino_casi_no_cuenta(self):
        # Damero de +-1 tono sobre el degrade (como el tramado fijo de C4): lo
        # borra la caja de 7 px; los escalones de 2,5 tonos no.
        damero = (np.indices(self.liso.shape).sum(axis=0) % 2) * 2 - 1
        o_tram = ph.ondulacion(self.liso + damero, self.m).mean()
        o_esc = ph.ondulacion(np.floor(self.liso / 2.5) * 2.5, self.m).mean()
        self.assertLess(o_tram, o_esc / 3)

    def test_solo_mide_en_la_mascara(self):
        m = np.zeros((96, 160), dtype=bool)
        m[:10, :10] = True
        self.assertEqual(ph.ondulacion(self.liso, m).size, 100)


class AcumuladorTest(unittest.TestCase):
    def test_media_exacta_y_p95_con_paso_de_histograma(self):
        acum = ph.Acumulador()
        valores = np.linspace(0, 2, 2001)
        acum.sumar(valores[:1000])
        acum.sumar(valores[1000:])
        self.assertAlmostEqual(acum.media(), 1.0, places=9)
        self.assertLessEqual(abs(acum.percentil(95) - 1.9), 2.0 / ph.HIST_PASO)

    def test_vacio_da_nada(self):
        self.assertIsNone(ph.Acumulador().media())
        self.assertIsNone(ph.Acumulador().percentil(95))


class SesgoTest(unittest.TestCase):
    def test_medir_cuadros_da_el_sesgo_y_la_ondulacion(self):
        ref = [fondo(valor=32.0), fondo(valor=30.0)]
        pieza = [r - 4 for r in ref]                 # el corrimiento del 2026-10-18
        m = np.ones(ref[0].shape, dtype=bool)
        medida = ph.medir_cuadros((p.astype(np.uint8), int(r.sum()), m)
                                  for p, r in zip(pieza, ref))
        self.assertEqual(medida["sesgo_luma"], -4.0)
        self.assertEqual(medida["cuadros"], 2)
        self.assertAlmostEqual(medida["ondulacion"], 0.0, places=9)

    def test_la_alarma_salta_con_el_bug_601_709_y_no_con_ruido(self):
        # 2026-10-18: el corrimiento bajaba la luma 3 a 5 tonos y SSIM/PSNR no
        # lo veian. Con este umbral se habria visto al primer emitir.
        self.assertEqual(emit_v2.UMBRAL_SESGO_LUMA, 1.0)
        self.assertIn("ALARMA DE COLOR", emit_v2.alarma_color(-3.2))
        self.assertIn("ALARMA DE COLOR", emit_v2.alarma_color(4.7))
        self.assertEqual(emit_v2.alarma_color(-0.4), "")
        self.assertEqual(emit_v2.alarma_color(None), "")

    def test_sesgo_de_es_la_media_de_la_diferencia(self):
        self.assertEqual(emit_v2.sesgo_de(-4 * 1000, 1000), -4.0)
        self.assertEqual(emit_v2.sesgo_de(123, 1000), 0.12)
        self.assertIsNone(emit_v2.sesgo_de(0, 0))

    def test_anotar_color_grita_y_deja_la_nota(self):
        gritos = []
        nota = emit_v2.anotar_color(-4.12, gritos.append)
        self.assertTrue(nota.startswith("luma -4.12; ALARMA DE COLOR"))
        self.assertTrue(any("!!! ALARMA DE COLOR" in g for g in gritos))
        gritos = []
        self.assertEqual(emit_v2.anotar_color(0.05, gritos.append), "luma +0.05")
        self.assertEqual(gritos, [])
        self.assertEqual(emit_v2.anotar_color(None), "luma -")

    def test_la_lectura_de_luma_no_convierte_el_color(self):
        pieza = emit_v2.build_luma_command("ffmpeg", "p.mp4", 10)
        ref = emit_v2.build_luma_command("ffmpeg", "ref.y4m")
        for cmd in (pieza, ref):
            filtro = cmd[cmd.index("-vf") + 1]
            self.assertTrue(filtro.endswith(emit_matrix.MISMAS_ETIQUETAS))
            self.assertNotIn("-colorspace", cmd)          # ninguna etiqueta de salida
            self.assertEqual(cmd[cmd.index("-pix_fmt") + 1], "yuv420p")
        self.assertTrue(pieza[pieza.index("-vf") + 1].startswith("fps=10,"))
        self.assertFalse(ref[ref.index("-vf") + 1].startswith("fps="))


class VariantesTest(unittest.TestCase):
    def test_nombres_crf_y_texto_libre(self):
        v = ph.variantes(["c3", "c4@22", "ninguno", "hqdn3d=3:2:4:3@26", "deband=range=40"], 24)
        self.assertEqual([x["nombre"] for x in v], ["c3", "c4", "ninguno", "f1", "f2"])
        self.assertEqual([x["crf"] for x in v], [24, 22, 24, 26, 24])
        self.assertEqual(v[0]["prefiltro"], emit_intro_loop.PREFILTRO_C3)
        self.assertEqual(v[1]["prefiltro"], emit_intro_loop.PREFILTRO_C4)
        self.assertIsNone(v[2]["prefiltro"])
        self.assertEqual(v[3]["prefiltro"], "hqdn3d=3:2:4:3")
        self.assertEqual([x["fila"] for x in v], [1, 2, 3, 4, 5])
        self.assertEqual(v[1]["file"], "02-c4-crf22.mp4")

    def test_sin_variantes_compara_c3_y_c4(self):
        self.assertEqual([x["nombre"] for x in ph.variantes(None, 24)], ["c3", "c4"])

    def test_una_arroba_que_no_es_crf_queda_en_el_filtro(self):
        v = ph.parse_variante("deband@x", 24)
        self.assertEqual((v["prefiltro"], v["crf"]), ("deband@x", 24))

    def test_recorte(self):
        self.assertEqual(ph.parse_recorte("0,180,640,360"), (0, 180, 640, 360))
        for malo in ("0,0,0,10", "1,2,3", "-1,0,10,10"):
            with self.assertRaises(ValueError):
                ph.parse_recorte(malo)


class ComandosTest(unittest.TestCase):
    def test_la_variante_se_emite_como_emit_intro_loop(self):
        # La misma linea: referencia etiquetada 709 ANTES del -i (s4 fila 11).
        cmd = emit_intro_loop.build_h264_command("ffmpeg", "ref.y4m", "o.mp4", 24, 82,
                                                 emit_intro_loop.PREFILTRO_C4)
        i = cmd.index("-i")
        self.assertEqual(cmd[i - 2:i], ["-f", "yuv4mpegpipe"])
        self.assertEqual(cmd[3:3 + len(emit_v2.COLOR_709_ENTRADA)], emit_v2.COLOR_709_ENTRADA)

    def test_la_lamina_lee_el_cuadro_con_709_declarado(self):
        cmd = ph.build_rgb_command("ffmpeg", "p.mp4", 4, 10)
        filtro = cmd[cmd.index("-vf") + 1]
        self.assertTrue(filtro.startswith("fps=10,format=yuv420p," + emit_matrix.MISMAS_ETIQUETAS))
        self.assertIn("trim=start_frame=4:end_frame=5", filtro)
        self.assertIn("scale=in_color_matrix=bt709:in_range=tv", filtro)
        self.assertNotIn("-colorspace", cmd)


class LaminaTest(unittest.TestCase):
    def leer_png(self, datos):
        self.assertEqual(datos[:8], b"\x89PNG\r\n\x1a\n")
        largo, = struct.unpack(">I", datos[8:12])
        self.assertEqual(datos[12:16], b"IHDR")
        ancho, alto, bits, tipo = struct.unpack(">IIBB", datos[16:26])
        self.assertEqual((bits, tipo), (8, 2))
        i = 8 + 12 + largo
        largo_idat, = struct.unpack(">I", datos[i:i + 4])
        self.assertEqual(datos[i + 4:i + 8], b"IDAT")
        crudo = zlib.decompress(datos[i + 8:i + 8 + largo_idat])
        filas = [crudo[y * (1 + 3 * ancho):(y + 1) * (1 + 3 * ancho)] for y in range(alto)]
        self.assertTrue(all(f[0] == 0 for f in filas))
        self.assertTrue(datos.endswith(b"IEND\xaeB`\x82"))
        return np.frombuffer(b"".join(f[1:] for f in filas), np.uint8).reshape(alto, ancho, 3)

    def test_png_ida_y_vuelta_y_mismos_bytes(self):
        rgb = np.random.RandomState(3).randint(0, 255, size=(9, 11, 3)).astype(np.uint8)
        datos = ph.png_bytes(rgb)
        np.testing.assert_array_equal(self.leer_png(datos), rgb)
        self.assertEqual(datos, ph.png_bytes(rgb.copy()))

    def test_lamina_normal_y_realzada_por_fila(self):
        cuadros = [np.full((20, 30, 3), 10 * (k + 1), np.uint8) for k in range(3)]
        lam = ph.armar_lamina(cuadros, ganancia=3, separacion=4)
        self.assertEqual(lam.shape, (3 * (20 + 4) + 4, 2 * 30 + 3 * 4, 3))
        # fila 1: normal = 20, x3 = 60 (lejos del rotulo de la esquina)
        y = 4 + 24 + 15
        self.assertEqual(int(lam[y, 4 + 25, 0]), 20)
        self.assertEqual(int(lam[y, 2 * 4 + 30 + 25, 0]), 60)
        self.assertEqual(int(lam[2, 2, 0]), ph.GRIS)

    def test_realzar_satura_en_255(self):
        self.assertEqual(int(ph.realzar(np.array([[[100, 10, 0]]], np.uint8), 3)[0, 0, 0]), 255)

    def test_recorte_acotado_al_cuadro(self):
        rgb = np.zeros((720, 1280, 3), np.uint8)
        self.assertEqual(ph.recortar(rgb, (0, 180, 640, 360)).shape, (360, 640, 3))
        self.assertEqual(ph.recortar(rgb, (1000, 600, 640, 360)).shape, (120, 280, 3))

    def test_rotulo_dibuja_el_numero(self):
        base = np.full((40, 60, 3), 30, np.uint8)
        con = ph.rotular(base, 12)
        self.assertTrue((con == 255).any())
        self.assertFalse(np.array_equal(ph.rotular(base, 1), ph.rotular(base, 7)))
        self.assertEqual(int(con[39, 59, 0]), 30)       # fuera del rotulo no toca


class TablaTest(unittest.TestCase):
    def test_columnas_y_formato(self):
        medida = {"ondulacion": 0.3412, "ondulacion_p95": 1.0, "sesgo_luma": -0.04,
                  "cuadros": 82}
        f = ph.fila_tabla(2, "c4", 24, 1000349, "424f6f07dd60", medida,
                          {"ssim_all": "0.99", "psnr_avg": "45.5"}, "x")
        lineas = ph.tabla_lineas([f], ["fuente abc"])
        self.assertEqual(lineas[2], "\t".join(ph.COLUMNAS))
        self.assertEqual(lineas[3].split("\t")[:9],
                         ["2", "c4", "24", "1000349", "424f6f07dd60", "82", "0.341", "1.000",
                          "-0.04"])
        self.assertEqual(len(ph.tabla_pantalla([f])), 2)


if __name__ == "__main__":
    unittest.main()
