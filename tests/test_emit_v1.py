import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402


class RecipeTest(unittest.TestCase):
    """H-6: v1 sin argumentos tiene que ser "v0 con audio". Si los defaults
    se corrieran solos, la primera fila de v1 mediria dos cosas a la vez."""

    def test_sin_argumentos_es_v0_con_audio(self):
        vp9, h264 = emit_v1.recipe()
        v0_vp9 = emit_pieces.variant_by_id("v0-vp9")["args"]
        v0_h264 = emit_pieces.variant_by_id("v0-h264-baseline")["args"]
        self.assertEqual(vp9["args"], v0_vp9)
        self.assertEqual(h264["args"], v0_h264)
        self.assertEqual(vp9["id"], "v1-vp9")
        self.assertEqual(h264["id"], "v1-h264")
        self.assertIsNone(vp9["vf"])

    def test_la_receta_de_la_matriz_entra_por_argumentos(self):
        vp9, h264 = emit_v1.recipe(vp9_crf=38, vp9_extra=["-tune-content", "screen"],
                                   h264_profile="high", h264_crf=23,
                                   h264_bframes=3, h264_refs=4)
        self.assertEqual(vp9["args"][vp9["args"].index("-crf") + 1], "38")
        self.assertIn("screen", vp9["args"])
        self.assertEqual(h264["args"][h264["args"].index("-profile:v") + 1], "high")
        params = h264["args"][h264["args"].index("-x264-params") + 1]
        self.assertIn("bframes=3", params)
        self.assertIn("b-adapt=2", params)    # como X264_B3 en la matriz
        self.assertIn("ref=4", params)
        self.assertIn("8x8dct=1", params)
        self.assertIn("cabac=1", params)
        self.assertIn("cpu-independent=1", params)
        self.assertIn("keyint=15", params)
        self.assertIn("mp4a.40.2", h264["mime"])
        self.assertIn("avc1.6400", h264["mime"])

    def test_baseline_no_lleva_cabac_ni_8x8(self):
        params = emit_v1.x264_params("baseline", 0, 1)
        self.assertNotIn("cabac", params)
        self.assertNotIn("8x8dct", params)
        self.assertNotIn("b-adapt", params)

    def test_la_cadencia_variable_usa_el_mismo_filtro_que_la_matriz(self):
        vp9, h264 = emit_v1.recipe(vfr="exactos")
        self.assertEqual(vp9["vf"], emit_matrix.VFR_EXACTOS)
        self.assertEqual(h264["vf"], emit_matrix.VFR_EXACTOS)
        for variant in (vp9, h264):
            self.assertIn("-fps_mode", variant["args"])
            self.assertIn("-force_key_frames", variant["args"])
        with self.assertRaises(ValueError):
            emit_v1.recipe(vfr="otra")


class BuildCommandTest(unittest.TestCase):

    def command(self, variant):
        return emit_v1.build_command("ffmpeg", variant, "ref.y4m", "master.mp3",
                                     "out.bin")

    def test_video_de_la_referencia_y_audio_del_master(self):
        for variant in emit_v1.recipe():
            command = self.command(variant)
            inputs = [command[i + 1] for i, arg in enumerate(command) if arg == "-i"]
            self.assertEqual(inputs, ["ref.y4m", "master.mp3"])
            self.assertIn("0:v:0", command)
            self.assertIn("1:a:0", command)
            self.assertIn("-shortest", command)
            self.assertEqual(command[command.index("-threads") + 1], "1")
            self.assertIn("+bitexact", command)
            self.assertEqual(command[-1], "out.bin")

    def test_el_audio_va_en_el_codec_del_contenedor(self):
        vp9, h264 = emit_v1.recipe()
        webm = self.command(vp9)
        mp4 = self.command(h264)
        self.assertEqual(webm[webm.index("-c:a") + 1], "libopus")
        self.assertEqual(webm[webm.index("-ar") + 1], "48000")   # Opus solo 48 kHz
        self.assertEqual(mp4[mp4.index("-c:a") + 1], "aac")

    def test_el_filtro_de_cadencia_va_antes_del_encoder(self):
        vp9 = emit_v1.recipe(vfr="exactos")[0]
        command = self.command(vp9)
        self.assertLess(command.index("-vf"), command.index("-c:v"))

    def test_el_dash_vp9_es_un_remux_solo_video(self):
        command = emit_v1.build_dash_command("ffmpeg", "v1-vp9.webm", "dash-vp9")
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertNotIn("1:a:0", command)
        self.assertEqual(command[command.index("-dash_segment_type") + 1], "webm")
        self.assertEqual(command[command.index("-seg_duration") + 1], "1")
        self.assertEqual(command[command.index("-init_seg_name") + 1], "init.webm")
        self.assertTrue(command[-1].endswith("manifest.mpd"))


class ManifestTest(unittest.TestCase):

    def test_mismas_columnas_que_v0(self):
        """La pagina anexa MANIFEST-v1.tsv con el MISMO parser que el de v0."""
        self.assertEqual(emit_v1.MANIFEST_COLUMNS, emit_pieces.MANIFEST_COLUMNS)
        rows = [{"id": "v1-vp9", "role": "v1", "mime": emit_v1.VP9_MIME,
                 "file": "v1-vp9.webm", "bytes": 1, "sha256": "a", "note": "n"}]
        lines = emit_v1.manifest_lines(rows, "abc", 1280, 720, 15, 231, "--vp9-crf 38")
        self.assertTrue(all(line.startswith("#") for line in lines[:-1]))
        self.assertIn("# receta\t--vp9-crf 38", lines)
        self.assertEqual(lines[-1].split("\t"), ["v1-vp9", "v1", emit_v1.VP9_MIME,
                                                 "v1-vp9.webm", "1", "a", "n"])


if __name__ == "__main__":
    unittest.main()
