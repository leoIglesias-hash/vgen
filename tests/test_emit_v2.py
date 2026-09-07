# -*- coding: utf-8 -*-
"""H-26: la emision v2 sale de la FUENTE (no del master indexado), a 1280@20,
con color 709 declarado y VP9 de dos pasadas, bajo un techo de bytes. Estas
pruebas no corren ffmpeg: verifican las lineas de comando, la cabecera y4m,
el manifiesto y el techo, que es lo que el CI puede afirmar sin la fuente."""
import argparse
import os
import shutil
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402
import emit_v2  # noqa: E402


def after(command, flag):
    return command[command.index(flag) + 1]


class ReferenciaTest(unittest.TestCase):

    def test_la_base_es_1280_a_20_con_lanczos_y_709_tv(self):
        vf = emit_v2.escala()
        self.assertTrue(vf.startswith("fps=20,"), "la cadencia se decide ANTES de escalar")
        self.assertIn("scale=1280:-2:flags=lanczos", vf)
        self.assertIn("out_color_matrix=bt709", vf)
        self.assertIn("out_range=tv", vf)
        self.assertIn("in_color_matrix=auto", vf)
        self.assertTrue(vf.endswith(",format=yuv420p"))
        self.assertIn("in_color_matrix=bt709", emit_v2.escala(matriz_fuente="bt709"))

    def test_el_comando_de_referencia_escribe_un_y4m_etiquetado_y_bit_exacto(self):
        command = emit_v2.build_reference_command("ffmpeg", "fuente.mp4", "ref.y4m",
                                                  max_frames=40)
        self.assertEqual(after(command, "-i"), "fuente.mp4")
        self.assertEqual(after(command, "-threads"), "1")
        self.assertEqual(after(command, "-map"), "0:v:0")
        self.assertEqual(after(command, "-vf"), emit_v2.escala())
        self.assertEqual(after(command, "-frames:v"), "40")
        for flag, value in (("-colorspace", "bt709"), ("-color_primaries", "bt709"),
                            ("-color_trc", "bt709"), ("-color_range", "tv")):
            self.assertEqual(after(command, flag), value)
        self.assertIn("+bitexact", command)
        self.assertEqual(after(command, "-f"), "yuv4mpegpipe")
        self.assertEqual(command[-1], "ref.y4m")
        sin_corte = emit_v2.build_reference_command("ffmpeg", "f.mp4", "r.y4m")
        self.assertNotIn("-frames:v", sin_corte)

    def test_la_cabecera_y4m_da_base_y_cuadros(self):
        tmp = tempfile.mkdtemp(prefix="v2-y4m-")
        try:
            path = os.path.join(tmp, "ref.y4m")
            header = b"YUV4MPEG2 W16 H8 F20:1 Ip A1:1 C420jpeg XYSCSS=420JPEG XCOLORRANGE=LIMITED\n"
            frame = b"FRAME\n" + b"\x80" * (16 * 8 * 3 // 2)
            with open(path, "wb") as f:
                f.write(header + frame * 3)
            self.assertEqual(emit_v2.read_y4m_header(path), (16, 8, 20, 3))
            with open(path, "wb") as f:
                f.write(b"YUV4MPEG2 W16 H8 F24000:1001 C420\n" + frame)
            width, height, fps, frames = emit_v2.read_y4m_header(path)
            self.assertEqual((width, height, frames), (16, 8, 1))
            self.assertAlmostEqual(fps, 23.976, places=3)
            with open(path, "wb") as f:
                f.write(b"YUV4MPEG2 W16 H8 F20:1 C444\n" + frame)
            with self.assertRaises(ValueError):
                emit_v2.read_y4m_header(path)
            with open(path, "wb") as f:
                f.write(b"no es y4m\n")
            with self.assertRaises(ValueError):
                emit_v2.read_y4m_header(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RecetaTest(unittest.TestCase):

    def test_vp9_lleva_las_herramientas_de_calidad_y_el_gop_de_un_segundo(self):
        vp9, h264 = emit_v2.recipe()
        self.assertEqual(vp9["id"], "v2-vp9")
        self.assertEqual(after(vp9["args"], "-c:v"), "libvpx-vp9")
        self.assertEqual(after(vp9["args"], "-crf"), "34")
        self.assertEqual(after(vp9["args"], "-b:v"), "0")
        self.assertEqual(after(vp9["args"], "-g"), "20")            # 1 s a 20 fps
        self.assertEqual(after(vp9["args"], "-keyint_min"), "20")
        self.assertEqual(after(vp9["args"], "-auto-alt-ref"), "1")
        self.assertEqual(after(vp9["args"], "-lag-in-frames"), "25")
        self.assertEqual(after(vp9["args"], "-arnr-maxframes"), "7")
        self.assertEqual(after(vp9["args"], "-arnr-strength"), "4")
        self.assertEqual(after(vp9["args"], "-enable-tpl"), "1")
        self.assertEqual(vp9["pasadas"], 2)
        self.assertEqual(vp9["audio"], emit_v1.AUDIO_WEBM)
        self.assertEqual(vp9["mime"], emit_v1.VP9_MIME)
        self.assertEqual(after(emit_v2.recipe(fps=15)[0]["args"], "-g"), "15")
        self.assertEqual(emit_v2.recipe(vp9_2pass=False)[0]["pasadas"], 1)
        extra = emit_v2.recipe(vp9_extra=["-aq-mode", "1"])[0]["args"]
        self.assertEqual(after(extra, "-aq-mode"), "1")

    def test_h264_es_high_con_el_gop_de_la_cadencia_y_cpu_independent(self):
        h264 = emit_v2.recipe()[1]
        self.assertEqual(h264["id"], "v2-h264")
        self.assertEqual(after(h264["args"], "-profile:v"), "high")
        self.assertEqual(after(h264["args"], "-crf"), "21")
        params = after(h264["args"], "-x264-params")
        self.assertIn("keyint=20:min-keyint=20", params)
        self.assertIn("bframes=3", params)
        self.assertIn("ref=4", params)
        self.assertIn("cpu-independent=1", params)
        self.assertIn("8x8dct=1", params)
        self.assertEqual(h264["pasadas"], 1)
        self.assertIn("avc1.6400", h264["mime"])
        # v1 no cambia por el parametro nuevo: sigue con su GOP de 15.
        self.assertIn("keyint=15:min-keyint=15", emit_v1.x264_params("high", 3, 4))

    def test_las_dos_piezas_declaran_709_tv(self):
        for variant in emit_v2.recipe():
            for flag, value in (("-colorspace", "bt709"), ("-color_primaries", "bt709"),
                                ("-color_trc", "bt709"), ("-color_range", "tv")):
                self.assertEqual(after(variant["args"], flag), value, variant["id"])
            self.assertEqual(after(variant["args"], "-pix_fmt"), "yuv420p")

    def test_el_audio_del_mp4_se_copia_si_la_fuente_es_aac(self):
        self.assertEqual(emit_v2.recipe(audio_codec="aac")[1]["audio"], ["-c:a", "copy"])
        self.assertEqual(emit_v2.recipe(audio_codec="mp3")[1]["audio"], emit_v1.AUDIO_MP4)
        self.assertEqual(emit_v2.recipe(audio_codec="pcm_s16le")[1]["audio"], emit_v1.AUDIO_MP4)
        self.assertEqual(emit_v2.recipe(audio_codec=None)[1]["audio"], emit_v1.AUDIO_MP4)

    def test_la_radio_es_la_pista_de_la_fuente_tal_cual_cuando_se_puede(self):
        self.assertEqual(emit_v2.radio_plan("mp3")["ext"], "mp3")
        self.assertEqual(emit_v2.radio_plan("mp3")["args"], ["-c:a", "copy"])
        self.assertEqual(emit_v2.radio_plan("aac")["ext"], "m4a")
        self.assertEqual(emit_v2.radio_plan("aac")["mime"], "audio/mp4")
        self.assertEqual(after(emit_v2.radio_plan("flac")["args"], "-c:a"), "aac")
        self.assertIsNone(emit_v2.radio_plan(None))
        command = emit_v2.build_radio_command("ffmpeg", "fuente.mp4",
                                              emit_v2.radio_plan("aac"), "v2-ambiente.m4a")
        self.assertEqual(after(command, "-map"), "0:a:0")
        self.assertIn("-vn", command)
        self.assertEqual(after(command, "-c:a"), "copy")
        self.assertIn("+bitexact", command)
        self.assertEqual(command[-1], "v2-ambiente.m4a")


class ComandosTest(unittest.TestCase):

    def test_dos_pasadas_de_vp9_comparten_el_log_y_la_segunda_lleva_el_audio(self):
        vp9 = emit_v2.recipe()[0]
        commands = emit_v2.build_commands("ffmpeg", vp9, "ref.y4m", "fuente.mp4",
                                          "v2-vp9.webm", "work/v2-vp9")
        self.assertEqual(len(commands), 2)
        primera, segunda = commands
        self.assertEqual(after(primera, "-pass"), "1")
        self.assertEqual(after(primera, "-passlogfile"), "work/v2-vp9")
        self.assertIn("-an", primera)
        self.assertNotIn("1:a:0", primera)
        self.assertEqual(after(primera, "-f"), "null")
        self.assertEqual(after(segunda, "-pass"), "2")
        self.assertEqual(after(segunda, "-passlogfile"), "work/v2-vp9")
        self.assertNotIn("-an", segunda)
        self.assertEqual([segunda[i + 1] for i, a in enumerate(segunda) if a == "-map"],
                         ["0:v:0", "1:a:0"])
        self.assertEqual(after(segunda, "-c:a"), "libopus")
        self.assertIn("-shortest", segunda)
        self.assertEqual(segunda[-1], "v2-vp9.webm")
        for command in commands:
            inputs = [command[i + 1] for i, a in enumerate(command) if a == "-i"]
            self.assertEqual(inputs, ["ref.y4m", "fuente.mp4"])
            self.assertEqual(after(command, "-threads"), "1")
            self.assertIn("+bitexact", command)
            self.assertEqual(after(command, "-crf"), "34")

    def test_una_pasada_es_un_solo_comando_sin_pass(self):
        vp9 = emit_v2.recipe(vp9_2pass=False)[0]
        commands = emit_v2.build_commands("ffmpeg", vp9, "ref.y4m", "fuente.mp4",
                                          "v2-vp9.webm", "work/v2-vp9")
        self.assertEqual(len(commands), 1)
        self.assertNotIn("-pass", commands[0])
        self.assertIn("-auto-alt-ref", commands[0])

    def test_sin_audio_en_la_fuente_las_piezas_salen_mudas(self):
        h264 = emit_v2.recipe(audio_codec=None)[1]
        (command,) = emit_v2.build_commands("ffmpeg", h264, "ref.y4m", None,
                                            "v2-h264.mp4", "work/v2-h264")
        inputs = [command[i + 1] for i, a in enumerate(command) if a == "-i"]
        self.assertEqual(inputs, ["ref.y4m"])
        self.assertIn("-an", command)
        self.assertNotIn("-c:a", command)
        self.assertEqual(after(command, "-profile:v"), "high")

    def test_el_dash_v2_no_pisa_al_de_v1(self):
        self.assertNotEqual(emit_v2.DASH_DIR, "dash-vp9")
        command = emit_v2.build_dash_command("ffmpeg", "v2-vp9.webm", "out\\dash-v2-vp9")
        self.assertEqual(after(command, "-c"), "copy")
        self.assertEqual(command[-1], "out/dash-v2-vp9/manifest.mpd")

    def test_la_medicion_reexpande_a_la_cadencia_de_la_base(self):
        command = emit_matrix.build_metrics_command("ffmpeg", "p.webm", "ref.y4m", fps=20)
        self.assertIn("[0:v]fps=20,", after(command, "-lavfi"))
        # v1 y la matriz H-6 siguen midiendo a 15 sin decirlo.
        self.assertIn("[0:v]fps=15,", after(emit_matrix.build_metrics_command(
            "ffmpeg", "p.webm", "ref.y4m"), "-lavfi"))


class TechoYManifiestoTest(unittest.TestCase):

    def rows(self):
        return [
            {"id": "v2-vp9", "role": "v2", "mime": emit_v2.VP9_MIME, "file": "v2-vp9.webm",
             "bytes": 4000000, "sha256": "a", "cuadros": 300, "note": "vp9"},
            {"id": "v2-h264", "role": "v2", "mime": emit_v2.H264_MIME, "file": "v2-h264.mp4",
             "bytes": 25000000, "sha256": "b", "cuadros": 300, "note": "h264"},
            {"id": "v2-ambiente", "role": "radio", "mime": "audio/mp4", "file": "v2-ambiente.m4a",
             "bytes": 30000000, "sha256": "c", "cuadros": 0, "note": "radio"},
        ]

    def test_el_techo_marca_solo_las_piezas_de_video_que_lo_pasan(self):
        rows = self.rows()
        fuera = emit_v2.marcar_techo(rows, emit_v2.TECHO_BYTES)
        self.assertEqual([row["id"] for row in fuera], ["v2-h264"])
        self.assertIn("SUPERA EL TECHO (20000000 B)", rows[1]["note"])
        self.assertNotIn("TECHO", rows[0]["note"])
        self.assertNotIn("TECHO", rows[2]["note"], "la radio no es una pieza de video")
        self.assertEqual(emit_v2.marcar_techo(self.rows(), 0), [], "techo 0 = sin techo")
        self.assertEqual(emit_v2.TECHO_BYTES, 20000000)
        self.assertEqual(emit_v2.CODIGO_TECHO, 4)

    def test_el_manifiesto_tiene_las_columnas_de_v0_y_declara_fuente_color_y_techo(self):
        self.assertEqual(emit_v2.MANIFEST_COLUMNS, emit_pieces.MANIFEST_COLUMNS)
        lines = emit_v2.manifest_lines(self.rows()[:1], "abc", "TKN.mp4", "bt709 tv bt709 bt709",
                                       1280, 720, 20, 300, "--vp9-crf 34", 20000000)
        self.assertTrue(all(line.startswith("#") for line in lines[:-1]))
        self.assertIn("# fuente\tabc\tTKN.mp4", lines)
        self.assertIn("# fuente_color\tbt709 tv bt709 bt709", lines)
        self.assertIn("# base\t1280x720\t20 fps\t300 cuadros", lines)
        self.assertIn("# receta\t--vp9-crf 34", lines)
        self.assertIn("# techo\t20000000", lines)
        self.assertEqual(lines[-1].split("\t"),
                         ["v2-vp9", "v2", emit_v2.VP9_MIME, "v2-vp9.webm", "4000000", "a", "vp9"])
        self.assertEqual(emit_v2.MANIFEST_NAME, "MANIFEST-v2.tsv")

    def test_la_receta_canonica_no_lleva_rutas(self):
        args = argparse.Namespace(
            ancho=1280, fps=20, vp9_crf=34, vp9_cpu=2, vp9_1pass=False, vp9_extra="",
            h264_crf=21, h264_bframes=3, h264_refs=4, techo=20000000,
            matriz_fuente="auto", frames=None)
        receta = emit_v2.receta_de(args)
        self.assertEqual(receta, "--ancho 1280 --fps 20 --vp9-crf 34 --vp9-cpu 2 "
                                 "--h264-crf 21 --h264-bframes 3 --h264-refs 4 --techo 20000000")
        args.vp9_1pass = True
        args.frames = 40
        args.matriz_fuente = "bt709"
        receta = emit_v2.receta_de(args)
        self.assertIn("--vp9-1pass", receta)
        self.assertIn("--matriz-fuente bt709", receta)
        self.assertTrue(receta.endswith("--frames 40"))
        self.assertNotIn("out", receta)


class BarridoTest(unittest.TestCase):

    def test_el_barrido_reemplaza_el_crf_y_conserva_la_receta(self):
        variants = emit_v2.barrido_variants([30, 38], [20], vp9_crf=34, h264_crf=21,
                                            fps=20, audio_codec="aac")
        self.assertEqual([v["id"] for v in variants],
                         ["v2-vp9-crf30", "v2-vp9-crf38", "v2-h264-crf20"])
        self.assertEqual([v["eje"] for v in variants], ["vp9-crf", "vp9-crf", "h264-crf"])
        self.assertTrue(all(v["role"] == "barrido" for v in variants))
        self.assertEqual(after(variants[0]["args"], "-crf"), "30")
        self.assertEqual(after(variants[1]["args"], "-crf"), "38")
        self.assertEqual(after(variants[2]["args"], "-crf"), "20")
        self.assertEqual(variants[0]["pasadas"], 2)
        self.assertIn("-enable-tpl", variants[1]["args"])
        self.assertEqual(emit_v2.parse_lista("28, 32,36"), [28, 32, 36])
        self.assertEqual(emit_v2.parse_lista(""), [])

    def test_la_tabla_del_barrido_dice_techo_y_ssim(self):
        row = {"id": "v2-vp9-crf30", "eje": "vp9-crf", "bytes": 21000000, "techo": "SUPERA",
               "ssim_all": "0.98", "psnr_avg": "42.1", "cuadros": 300, "seg_encode": "90.0",
               "perfil": "vp9 Profile 0 -"}
        self.assertTrue(emit_v2.supera_techo({"role": "barrido", "bytes": 21000000}, 20000000))
        self.assertFalse(emit_v2.supera_techo({"role": "radio", "bytes": 21000000}, 20000000))
        text = emit_v2.resumen_markdown([row], 20000000)
        self.assertIn("| `v2-vp9-crf30` | vp9-crf | 21.000.000 | SUPERA | 0.98 | 42.1 |", text)
        self.assertIn("techo = 20000000 B", text)
        for column in ("techo", "ssim_all", "psnr_avg", "seg_encode"):
            self.assertIn(column, emit_v2.MATRIZ_COLUMNS)


if __name__ == "__main__":
    unittest.main()
