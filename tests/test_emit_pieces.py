import os
import shutil
import sys
import tempfile
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_pieces  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test_pixel.ascl")


class BuildCommandTest(unittest.TestCase):
    """H-9: la linea de ffmpeg ES la apuesta (docs/EMISION-V0.md S3-S4).
    Si estos flags cambian sin querer, la pieza deja de medir lo que dice."""

    def command(self, variant_id, width=1280, height=720, fps=15):
        variant = emit_pieces.variant_by_id(variant_id)
        return emit_pieces.build_command(
            "ffmpeg", variant, width, height, fps, "out.bin")

    def test_todas_las_piezas_declaradas_se_pueden_construir(self):
        ids = [variant["id"] for variant in emit_pieces.VARIANTS]
        self.assertEqual(ids, ["v0-h264-baseline", "v0-h264-main",
                               "v0-vp9", "v0-vp9-alpha"])
        for variant_id in ids:
            command = self.command(variant_id)
            self.assertEqual(command[0], "ffmpeg")
            self.assertEqual(command[-1], "out.bin")
            # Entrada cruda a resolucion y cadencia del master: el emisor no
            # reescala ni recuantiza el look decidido offline.
            self.assertIn("rawvideo", command)
            self.assertIn("1280x720", command)

    def test_baseline_lleva_el_dpb_mas_chico_posible(self):
        command = self.command("v0-h264-baseline")
        self.assertIn("baseline", command)
        params = command[command.index("-x264-params") + 1]
        self.assertIn("bframes=0", params)   # sin reordenamiento
        self.assertIn("ref=1", params)       # una sola referencia
        self.assertIn("keyint=15", params)   # GOP cerrado y corto
        self.assertIn("scenecut=0", params)  # cadencia de cuadro clave fija

    def test_main_es_el_detector_de_hardware(self):
        command = self.command("v0-h264-main")
        self.assertIn("main", command)
        params = command[command.index("-x264-params") + 1]
        self.assertIn("cabac=1", params)
        # Misma estructura que baseline: si no, la comparacion mide dos cosas.
        self.assertIn("bframes=0", params)
        self.assertIn("ref=1", params)
        self.assertIn("keyint=15", params)

    def test_vp9_alpha_pide_alfa_y_apaga_alt_ref(self):
        command = self.command("v0-vp9-alpha")
        self.assertIn("libvpx-vp9", command)
        self.assertIn("yuva420p", command)
        self.assertIn("rgba", command)
        self.assertEqual(command[command.index("-auto-alt-ref") + 1], "0")

    def test_todas_son_deterministas_y_bit_exactas(self):
        for variant in emit_pieces.VARIANTS:
            command = self.command(variant["id"])
            self.assertEqual(command[command.index("-threads") + 1], "1")
            self.assertIn("+bitexact", command)
            self.assertIn("-map_metadata", command)


class SegmentCommandTest(unittest.TestCase):
    """Los empaquetados HLS/DASH son un REMUX, no una segunda codificacion.
    Si alguna vez desaparece el `-c copy`, esta prueba lo detiene: con re-encode
    dejarian de medir lo mismo que las piezas progresivas."""

    def command(self, stream_id):
        stream = emit_pieces.stream_by_id(stream_id)
        return emit_pieces.build_segment_command(
            "ffmpeg", stream, "src.mp4", "out")

    def test_los_tres_empaquetados_existen(self):
        ids = [stream["id"] for stream in emit_pieces.STREAMS]
        self.assertEqual(ids, ["v0-hls-ts", "v0-hls-fmp4", "v0-dash"])

    def test_ninguno_recodifica(self):
        for stream in emit_pieces.STREAMS:
            command = self.command(stream["id"])
            self.assertEqual(command[command.index("-c") + 1], "copy")
            self.assertNotIn("libx264", command)
            self.assertNotIn("libvpx-vp9", command)

    def test_el_corte_cae_en_cuadro_clave(self):
        # GOP de 15 cuadros a 15 fps: un segmento de 1 s cae exactamente en un
        # cuadro clave. La estructura elegida en v0 es la que habilita esto.
        hls = self.command("v0-hls-ts")
        self.assertEqual(hls[hls.index("-hls_time") + 1], "1")
        dash = self.command("v0-dash")
        self.assertEqual(dash[dash.index("-seg_duration") + 1], "1")
        self.assertEqual(emit_pieces.GOP, 15)

    def test_salen_de_una_pieza_ya_emitida(self):
        for stream in emit_pieces.STREAMS:
            emit_pieces.variant_by_id(stream["source"])  # no debe levantar

    def test_hls_fmp4_separa_el_init(self):
        command = self.command("v0-hls-fmp4")
        self.assertIn("fmp4", command)
        self.assertEqual(command[command.index("-hls_fmp4_init_filename") + 1],
                         "init.mp4")


class AlphaTest(unittest.TestCase):
    """La pieza con alfa prueba COMPOSICION, no arte: mascara deterministica,
    borde duro (el caso que mas sufre) y movimiento derivado del indice."""

    def test_mascara_es_binaria_y_deterministica(self):
        first = emit_pieces.alpha_channel(64, 32, 5, 20)
        again = emit_pieces.alpha_channel(64, 32, 5, 20)
        self.assertTrue(np.array_equal(first, again))
        self.assertEqual(sorted(np.unique(first).tolist()), [0, 255])

    def test_el_disco_cruza_el_cuadro(self):
        width, height, count = 64, 32, 20
        centers = []
        for index in range(count):
            mask = emit_pieces.alpha_channel(width, height, index, count)
            columns = np.nonzero(mask.any(axis=0))[0]
            centers.append(float(columns.mean()) if columns.size else None)
        visibles = [value for value in centers if value is not None]
        self.assertGreater(len(visibles), 2)
        self.assertLess(visibles[0], visibles[-1])

    def test_rgba_conserva_el_color_del_master(self):
        rgb = np.random.RandomState(7).randint(0, 256, (8, 8, 3)).astype(np.uint8)
        frame = emit_pieces.rgba_frame(rgb, 0, 4)
        self.assertEqual(frame.shape, (8, 8, 4))
        self.assertTrue(np.array_equal(frame[:, :, :3], rgb))


class ManifestTest(unittest.TestCase):
    """El manifiesto de runtime NO puede ser JSON: el gate ES5 prohibe `JSON`.
    Va en texto tabulado y se parte con split (DISENO-FORMATO-VGEN.md S10)."""

    def rows(self):
        return [{"id": "v0-vp9", "role": "base", "mime": 'video/webm; codecs="vp9"',
                 "file": "v0-vp9.webm", "bytes": 123, "sha256": "ab" * 32,
                 "note": "banda"}]

    def test_texto_tabulado_con_cabecera_comentada(self):
        lines = emit_pieces.manifest_lines(self.rows(), "cd" * 32, 1280, 720, 15, 225)
        comments = [line for line in lines if line.startswith("#")]
        data = [line for line in lines if not line.startswith("#")]
        self.assertTrue(comments)
        self.assertEqual(len(data), 1)
        fields = data[0].split("\t")
        self.assertEqual(len(fields), len(emit_pieces.MANIFEST_COLUMNS))
        self.assertEqual(fields[0], "v0-vp9")
        self.assertEqual(fields[3], "v0-vp9.webm")
        self.assertEqual(fields[4], "123")

    def test_no_hay_json_en_ninguna_linea(self):
        lines = emit_pieces.manifest_lines(self.rows(), "cd" * 32, 1280, 720, 15, 225)
        blob = "\n".join(lines)
        self.assertNotIn("{", blob)
        self.assertNotIn("[", blob)

    def test_declara_la_procedencia_del_master(self):
        master = "cd" * 32
        lines = emit_pieces.manifest_lines(self.rows(), master, 1280, 720, 15, 225)
        self.assertTrue(any(master in line for line in lines))


class ResolveMasterTest(unittest.TestCase):
    def test_ascl_pelado_pasa_derecho(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.ascl")
            with open(path, "wb") as stream:
                stream.write(b"ASCL" + bytes(32))
            self.assertEqual(
                emit_pieces.resolve_master(path, os.path.join(directory, "work")),
                path)


class EmitSmokeTest(unittest.TestCase):
    """Prueba de humo de punta a punta. Se saltea si no hay ffmpeg: la maquina
    de trabajo no tiene toolchain y la emision real corre en el workflow."""

    def ffmpeg(self):
        return shutil.which("ffmpeg")

    def test_emite_una_pieza_y_su_fila_de_manifiesto(self):
        ffmpeg = self.ffmpeg()
        if not ffmpeg:
            self.skipTest("ffmpeg no esta en PATH")
        if not os.path.exists(FIXTURE):
            self.skipTest("falta el fixture .ascl")
        from ascl_decode import decode_all
        header = decode_all(FIXTURE)[0]
        if header["cols"] % 2 or header["rows"] % 2:
            self.skipTest("el fixture tiene lados impares (yuv420p pide pares)")
        with tempfile.TemporaryDirectory() as directory:
            result = emit_pieces.emit(FIXTURE, directory,
                                      only=["v0-h264-baseline"], max_frames=2,
                                      ffmpeg=ffmpeg, segment=False)
            self.assertEqual(len(result["rows"]), 1)
            row = result["rows"][0]
            self.assertGreater(row["bytes"], 0)
            self.assertEqual(len(row["sha256"]), 64)
            self.assertTrue(os.path.exists(result["manifest"]))
            with open(result["manifest"]) as stream:
                self.assertIn("v0-h264-baseline", stream.read())


if __name__ == "__main__":
    unittest.main()
