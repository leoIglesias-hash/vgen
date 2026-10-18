# -*- coding: utf-8 -*-
"""2026-10-17: tools/emit_intro_loop.py arma intro + loop como piezas y como
archivo unico deduplicado. Sin ffmpeg: el plan de cortes (loop a cuadros
enteros), los filtros, las lineas de H.264/VP9 (un keyframe por pieza,
determinismo del proyecto), el pegado sin recodificar, el manifiesto y la
receta C3 que eligio el operador."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_intro_loop as eil  # noqa: E402


class RecetaTest(unittest.TestCase):
    def test_receta_c3_del_operador(self):
        # Elegida a ojo el 2026-10-17 (docs/INTRO-Y-LOOP.md); cambiarla es
        # una decision, no un retoque.
        self.assertEqual((eil.ANCHO, eil.FPS, eil.CRF_INTRO, eil.CRF_LOOP), (1280, 10, 24, 26))
        self.assertEqual(eil.PREFILTRO_C3,
                         "hqdn3d=3:2:4:3,deband=1thr=0.015:2thr=0.015:3thr=0.015"
                         ":range=24:blur=1")

    def test_c4_alisa_en_16_bits_y_vuelve_con_tramado_fijo(self):
        # 2026-10-18 (halo de los costados): mismo encoder que C3, el alisado
        # calcula tonos intermedios en 16 bits y vuelve a 8 con un tramado fijo.
        partes = eil.PREFILTRO_C4.split(",")
        self.assertEqual(partes[0], "format=yuv420p16le")
        self.assertEqual(partes[-2:], ["scale=sws_dither=bayer", "format=yuv420p"])
        self.assertIn("range=40", eil.PREFILTRO_C4)
        self.assertIn("range=64", eil.PREFILTRO_C4)

    def test_nombres_de_prefiltro(self):
        self.assertEqual(eil.resolver_prefiltro("c4"), eil.PREFILTRO_C4)
        self.assertEqual(eil.resolver_prefiltro("C3"), eil.PREFILTRO_C3)
        self.assertIsNone(eil.resolver_prefiltro("ninguno"))
        self.assertIsNone(eil.resolver_prefiltro(""))
        self.assertEqual(eil.resolver_prefiltro("hqdn3d"), "hqdn3d")


class PlanYFiltrosTest(unittest.TestCase):
    def setUp(self):
        self.p = eil.plan(197, 85, 24.0, 10)

    def test_plan_lleva_el_loop_a_cuadros_enteros(self):
        self.assertEqual(self.p["cuadros_loop"], 35)
        self.assertAlmostEqual(self.p["factor"], 3.5 / (85 / 24.0), places=9)

    def test_filtros_cortan_en_cuadros_de_la_fuente(self):
        intro = eil.filtro_intro(self.p)
        loop = eil.filtro_loop(self.p)
        self.assertTrue(intro.startswith("trim=start_frame=0:end_frame=197,"))
        self.assertTrue(loop.startswith("trim=start_frame=197:end_frame=282,"))
        self.assertIn("setpts=(PTS-STARTPTS)*0.988235294", loop)
        for filtro in (intro, loop):
            self.assertIn("fps=10,scale=1280:-2:flags=lanczos", filtro)
            self.assertIn("out_color_matrix=bt709:out_range=tv", filtro)

    def test_referencia_del_loop_con_cuadros_exactos(self):
        command = eil.build_ref_command("ffmpeg", "f.mp4", eil.filtro_loop(self.p),
                                        "ref-loop.y4m", 35)
        self.assertEqual(command[command.index("-frames:v") + 1], "35")
        self.assertEqual(command[-3:], ["-f", "yuv4mpegpipe", "ref-loop.y4m"])
        self.assertIn("+bitexact", command)


class EncoderTest(unittest.TestCase):
    def test_h264_un_keyframe_por_pieza_y_prefiltro(self):
        command = eil.build_h264_command("ffmpeg", "ref.y4m", "loop-h264.mp4", 26, 35)
        x264 = command[command.index("-x264-params") + 1]
        self.assertIn("keyint=35:min-keyint=35", x264)
        self.assertIn("threads=1:cpu-independent=1", x264)
        self.assertEqual(command[command.index("-crf") + 1], "26")
        self.assertEqual(command[command.index("-vf") + 1], eil.PREFILTRO_C4)
        self.assertEqual(command[command.index("-profile:v") + 1], "high")
        self.assertIn("+faststart", command)
        self.assertEqual(command[-1], "loop-h264.mp4")

    def test_la_referencia_entra_etiquetada_709(self):
        # 2026-10-18: el y4m no guarda la matriz; con la etiqueta solo en la
        # salida, ffmpeg 8 convertia 601->709 (rojos 3 a 5 tonos mas oscuros).
        h264 = eil.build_h264_command("ffmpeg", "ref.y4m", "o.mp4", 24, 82)
        for command in [h264] + eil.build_vp9_commands("ffmpeg", "ref.y4m", "o.webm", 14, 35, "l"):
            antes = command[:command.index("-i")]
            for flag, valor in (("-colorspace", "bt709"), ("-color_primaries", "bt709"),
                                ("-color_trc", "bt709"), ("-color_range", "tv")):
                self.assertEqual(antes[antes.index(flag) + 1], valor)
            self.assertEqual(command[command.index("-i") + 1], "ref.y4m")

    def test_sin_prefiltro_no_hay_vf(self):
        command = eil.build_h264_command("ffmpeg", "ref.y4m", "o.mp4", 24, 82, prefiltro=None)
        self.assertNotIn("-vf", command)

    def test_vp9_dos_pasadas(self):
        uno, dos = eil.build_vp9_commands("ffmpeg", "ref.y4m", "loop-vp9.webm", 14, 35, "log")
        self.assertEqual(uno[uno.index("-pass") + 1], "1")
        self.assertEqual(dos[dos.index("-pass") + 1], "2")
        self.assertEqual(dos[dos.index("-g") + 1], "35")
        self.assertEqual(dos[-1], "loop-vp9.webm")
        self.assertIn("null", uno)


class VistaYManifiestoTest(unittest.TestCase):
    def test_lista_concat(self):
        self.assertEqual(eil.lista_concat("../intro.mp4", "../loop.mp4", 2),
                         "file '../intro.mp4'\nfile '../loop.mp4'\nfile '../loop.mp4'\n")
        self.assertEqual(eil.lista_concat(None, "loop.mp4", 1), "file 'loop.mp4'\n")

    def test_el_pegado_no_recodifica(self):
        # Sin recodificar, las vueltas pegadas son bytes identicos: eso es lo
        # que mp4_dedup despues guarda una sola vez.
        command = eil.build_concat_command("ffmpeg", "lista.txt", "pegado.mp4")
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertIn("concat", command)

    def test_el_archivo_unico_es_mp4(self):
        self.assertTrue(eil.ARCHIVO_UNICO.endswith(".mp4"))
        self.assertEqual(eil.mp4_dedup.deduplicar.__module__, "mp4_dedup")

    def test_manifiesto(self):
        p = eil.plan(197, 85, 24.0, 10)
        fila = {"pieza": "loop", "file": "loop-h264.mp4", "bytes": 1, "sha256": "ab",
                "cuadros": 35, "codec": "h264", "crf": 26}
        lineas = eil.manifest_lines([fila], "f00", "f.mp4", p, "receta")
        self.assertIn("intro 197 cuadros de la fuente", lineas[2])
        self.assertIn("35 cuadros @ 10 fps", lineas[2])
        self.assertEqual(lineas[4], "\t".join(eil.MANIFEST_COLUMNS))
        self.assertTrue(lineas[5].startswith("loop\tloop-h264.mp4\t1\tab\t35\th264\t26"))


if __name__ == "__main__":
    unittest.main()
