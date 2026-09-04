import inspect
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

    def test_las_dos_h264_son_independientes_de_la_cpu(self):
        """H-14b (adoptado 2026-09-04): `threads=1` hace que una maquina repita
        sus bytes; `cpu-independent=1` hace que DOS maquinas coincidan. Sin esto
        la residencia (H-15) pierde sentido: una re-emision sin cambios cambiaria
        la huella y el aparato bajaria de nuevo lo que ya tiene."""
        for variant_id in ("v0-h264-baseline", "v0-h264-main"):
            command = self.command(variant_id)
            params = command[command.index("-x264-params") + 1]
            self.assertIn("cpu-independent=1", params)
            self.assertIn("threads=1", params)
        # Las dos comparten base: la comparacion baseline/main sigue midiendo
        # solo CABAC, no una diferencia de determinismo.
        self.assertTrue(emit_pieces.X264_MAIN.startswith(emit_pieces.X264_COMMON))
        self.assertEqual(emit_pieces.X264_BASELINE, emit_pieces.X264_COMMON)

    def test_no_se_le_pide_cpu_independent_al_carril_vp9(self):
        """libvpx es entero y ya repite bytes entre maquinas; la opcion es de
        x264 y ffmpeg la rechazaria en el otro carril."""
        for variant_id in ("v0-vp9", "v0-vp9-alpha"):
            command = self.command(variant_id)
            self.assertNotIn("cpu-independent=1", " ".join(command))
            self.assertNotIn("-x264-params", command)

    def test_x264_extra_se_pega_solo_a_las_piezas_h264(self):
        """H-14: la palanca de CI para probar una opcion del encoder no puede
        tocar la receta ni filtrarse al carril VP9."""
        for variant_id in ("v0-h264-baseline", "v0-h264-main"):
            variant = emit_pieces.variant_by_id(variant_id)
            command = emit_pieces.build_command(
                "ffmpeg", variant, 1280, 720, 15, "out.mp4",
                x264_extra="no-mbtree=1")
            params = command[command.index("-x264-params") + 1]
            self.assertTrue(params.endswith(":no-mbtree=1"), params)
            self.assertIn("threads=1", params)
            self.assertNotIn("no-mbtree", " ".join(self.command(variant_id)))
        vp9 = emit_pieces.build_command(
            "ffmpeg", emit_pieces.variant_by_id("v0-vp9"), 1280, 720, 15,
            "out.webm", x264_extra="no-mbtree=1")
        self.assertNotIn("no-mbtree=1", " ".join(vp9))
        self.assertNotIn("-x264-params", vp9)


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
    """H-18b: la pieza con alfa prueba COMPOSICION, no arte. Lleva CONTENIDO
    QUE NO EXISTE ABAJO -papelitos- sobre transparencia total, porque la version
    anterior copiaba el RGB del master y, superpuesta exacta, era indistinguible
    de lo que ya se veia: no contestaba la pregunta."""

    def test_el_cuadro_es_rgba_y_deterministico(self):
        first = emit_pieces.confetti_rgba(64, 48, 5)
        again = emit_pieces.confetti_rgba(64, 48, 5)
        self.assertEqual(first.shape, (48, 64, 4))
        self.assertTrue(np.array_equal(first, again))

    def test_el_alfa_es_binario(self):
        frame = emit_pieces.confetti_rgba(128, 96, 3)
        self.assertEqual(sorted(np.unique(frame[:, :, 3]).tolist()), [0, 255])

    def test_el_fondo_es_transparente_y_los_papelitos_son_pocos(self):
        """Un efecto tapa poco: si cubriera el cuadro no se veria el de abajo,
        que es justamente lo que la prueba tiene que poder ver."""
        frame = emit_pieces.confetti_rgba(320, 180, 7)
        cubierto = float(np.count_nonzero(frame[:, :, 3])) / (320 * 180)
        self.assertGreater(cubierto, 0.002)
        self.assertLess(cubierto, 0.25)

    def test_donde_no_hay_papelito_el_color_es_negro(self):
        """Nada del master se filtra: fuera de los papelitos no hay imagen."""
        frame = emit_pieces.confetti_rgba(160, 120, 11)
        fuera = frame[:, :, 3] == 0
        self.assertTrue(fuera.any())
        self.assertEqual(int(frame[:, :, :3][fuera].max()), 0)

    def test_los_papelitos_caen(self):
        """UN solo papelito, no el promedio de los 160: con todos, el promedio
        no baja de forma monotona porque los que salen por abajo vuelven a
        entrar por arriba (fallo real en CI la primera vez). Con uno, lo unico
        que puede interrumpir la bajada es su propia vuelta, y en doce cuadros
        no entra mas de una."""
        original = emit_pieces.CONFETTI_COUNT
        emit_pieces.CONFETTI_COUNT = 1
        try:
            techos = []
            for index in range(12):
                frame = emit_pieces.confetti_rgba(1024, 720, index)
                filas = np.nonzero(frame[:, :, 3].any(axis=1))[0]
                techos.append(int(filas[0]) if filas.size else None)
        finally:
            emit_pieces.CONFETTI_COUNT = original
        vistos = [valor for valor in techos if valor is not None]
        self.assertGreater(len(vistos), 6, "el papelito tiene que verse")
        bajadas = 0
        for antes, despues in zip(vistos, vistos[1:]):
            if despues > antes:
                bajadas += 1
        # No se exige que bajen LAS ONCE transiciones: entrando por arriba el
        # borde superior queda clavado en 0 un par de cuadros, y una vuelta
        # completa lo devuelve arriba. Lo que se afirma es la caida, no una
        # monotonia que el propio ciclo no puede cumplir.
        self.assertGreaterEqual(bajadas, 7)

    def test_no_se_usan_trascendentes(self):
        """Invariante 7: dos maquinas tienen que emitir el MISMO archivo. Un
        seno que difiere en 1 ULP entre dos libm mueve un borde y cambia los
        bytes, asi que el generador se escribe con enteros y se verifica aca."""
        fuente = "".join(inspect.getsource(objeto) for objeto in
                         (emit_pieces.confetti_rgba, emit_pieces._sorteo,
                          emit_pieces._triangulo))
        for prohibido in ("sin(", "cos(", "sqrt(", "random", "float("):
            self.assertNotIn(prohibido, fuente)


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
