# -*- coding: utf-8 -*-
"""2026-10-17: tools/emit_loop_zona.py configura H.264 para aprovechar un
loop en una parte de la pantalla. Sin ffmpeg: la tabla de niveles contra los
limites del estandar (DPB por resolucion), la eleccion de referencias y
nivel con y sin tope, el GOP frente al periodo, la linea de x264 y el
manifiesto."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_loop_zona as elz  # noqa: E402


class NivelesTest(unittest.TestCase):
    def test_cuadros_que_entran_en_la_dpb(self):
        # 1280x720 = 3600 macrobloques; 1920x1080 = 8160.
        self.assertEqual(elz.refs_maximas(1280, 720, "3.1"), 5)
        self.assertEqual(elz.refs_maximas(1280, 720, "4.1"), 9)
        self.assertEqual(elz.refs_maximas(1280, 720, "5.0"), 16)
        self.assertEqual(elz.refs_maximas(1920, 1080, "4.1"), 4)
        self.assertEqual(elz.refs_maximas(1920, 1080, "5.0"), 13)
        self.assertEqual(elz.refs_maximas(1920, 1080, "5.1"), 16)

    def test_nivel_minimo(self):
        self.assertEqual(elz.nivel_h264(1280, 720, 10, 16), "5.0")
        self.assertEqual(elz.nivel_h264(1280, 720, 10, 9), "4.0")
        self.assertEqual(elz.nivel_h264(1280, 720, 10, 4), "3.1")
        self.assertEqual(elz.nivel_h264(1920, 1080, 10, 16), "5.1")
        self.assertEqual(elz.nivel_h264(1920, 1080, 30, 4), "4.0")

    def test_tope_de_nivel_baja_las_referencias(self):
        self.assertEqual(elz.elegir_refs_y_nivel(1280, 720, 10), (16, "5.0"))
        self.assertEqual(elz.elegir_refs_y_nivel(1280, 720, 10, 16, "4.1"), (9, "4.0"))
        self.assertEqual(elz.elegir_refs_y_nivel(1920, 1080, 10, 16, "4.1"), (4, "4.0"))

    def test_nivel_desconocido(self):
        with self.assertRaises(ValueError):
            elz.refs_maximas(1280, 720, "9.9")


class EncoderTest(unittest.TestCase):
    def test_gop_largo_frente_al_periodo(self):
        self.assertEqual(elz.gop_para(10), 100)
        self.assertEqual(elz.gop_para(10, 12), 100)
        self.assertEqual(elz.gop_para(10, 40), 160)

    def test_linea_h264_con_las_referencias_y_el_nivel(self):
        command = elz.build_h264_command("ffmpeg", "ref.y4m", "zona.mp4", 26, 16, "5.0", 100)
        x264 = command[command.index("-x264-params") + 1]
        self.assertIn("ref=16", x264)
        self.assertIn("bframes=3", x264)
        self.assertIn("keyint=100:min-keyint=100", x264)
        self.assertIn("threads=1:cpu-independent=1", x264)
        self.assertEqual(command[command.index("-level") + 1], "5.0")
        self.assertNotIn("-vf", command)
        con = elz.build_h264_command("ffmpeg", "r.y4m", "z.mp4", 26, 9, "4.0", 100, "hqdn3d")
        self.assertEqual(con[con.index("-vf") + 1], "hqdn3d")

    def test_la_referencia_entra_etiquetada_709(self):
        # 2026-10-18: sin la etiqueta ANTES del -i, ffmpeg 8 re-convierte 601->709.
        command = elz.build_h264_command("ffmpeg", "ref.y4m", "zona.mp4", 26, 16, "5.0", 100)
        antes = command[:command.index("-i")]
        self.assertEqual(antes[antes.index("-colorspace") + 1], "bt709")
        self.assertEqual(antes[antes.index("-color_range") + 1], "tv")

    def test_manifiesto_con_mapa_de_zonas(self):
        zona = {"area": 0.5, "periodo": 12,
                "mascara": np.array([[True, True], [False, False]])}
        lineas = elz.manifest_lines([{"pieza": "zona", "file": "zona-h264.mp4", "bytes": 1,
                                      "refs": 16, "nivel": "5.0"}], "ab", "f.mp4", zona, "r")
        self.assertIn("50 % de la pantalla (##/..) repite cada 12 cuadros", lineas[2])
        self.assertEqual(lineas[4], "\t".join(elz.MANIFEST_COLUMNS))
        self.assertIn("ninguna", elz.manifest_lines([], "ab", "f.mp4", None, "r")[2])


if __name__ == "__main__":
    unittest.main()
