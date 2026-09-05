import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402


class VariantTableTest(unittest.TestCase):
    """H-6: la tabla de variantes ES la pregunta. Cada fila tiene que ser
    unica, pertenecer a un eje que corre en CI y comparar contra una
    referencia de su codec; si no, la tabla no se puede leer."""

    def test_ids_unicos_y_en_un_grupo_conocido(self):
        ids = [variant["id"] for variant in emit_matrix.VARIANTS]
        self.assertEqual(len(ids), len(set(ids)))
        for variant in emit_matrix.VARIANTS:
            self.assertIn(variant["eje"], emit_matrix.GRUPOS)
            self.assertIn(variant["codec"], emit_matrix.REFERENCIA_DE)
            self.assertIn(variant["ext"], ("webm", "mp4"))

    def test_todos_los_grupos_tienen_filas(self):
        for grupo in emit_matrix.GRUPOS:
            self.assertTrue(emit_matrix.variants_of(grupo), grupo)

    def test_las_referencias_existen_y_son_las_v0(self):
        for codec, ref_id in emit_matrix.REFERENCIA_DE.items():
            variant = emit_matrix.variant_by_id(ref_id)
            self.assertEqual(variant["codec"], codec)
            self.assertEqual(variant["eje"], "referencia")
            self.assertIn(ref_id, emit_matrix.V0_SHA256)

    def test_las_filas_v0_llevan_los_argumentos_de_v0_sin_tocar(self):
        """Autocontrol: si `ref-v0-*` no lleva EXACTAMENTE la receta v0, la
        corrida compara contra otra cosa y la fila 'IDENTICA' seria falsa."""
        pares = (("ref-v0-vp9", "v0-vp9"),
                 ("ref-v0-h264-baseline", "v0-h264-baseline"),
                 ("ref-v0-h264-main", "v0-h264-main"))
        for ref_id, v0_id in pares:
            self.assertEqual(emit_matrix.variant_by_id(ref_id)["args"],
                             emit_pieces.variant_by_id(v0_id)["args"])

    def test_los_sha_esperados_son_los_del_pack_publicado(self):
        self.assertEqual(emit_matrix.V0_SHA256["ref-v0-vp9"][:12], "5be4650747fd")
        self.assertEqual(emit_matrix.V0_SHA256["ref-v0-h264-baseline"][:12],
                         "cf927d578ab9")


class BuildCommandTest(unittest.TestCase):

    def command(self, variant_id):
        return emit_matrix.build_command(
            "ffmpeg", emit_matrix.variant_by_id(variant_id), "ref.y4m", "out.bin")

    def test_toda_variante_es_determinista_y_bit_exacta(self):
        for variant in emit_matrix.VARIANTS:
            command = self.command(variant["id"])
            self.assertEqual(command[command.index("-threads") + 1], "1")
            self.assertIn("+bitexact", command)
            self.assertIn("-map_metadata", command)
            self.assertEqual(command[-1], "out.bin")
            self.assertEqual(command[command.index("-i") + 1], "ref.y4m")

    def test_las_h264_son_independientes_de_la_cpu(self):
        """H-14b vale para toda la matriz: una fila que dependiera de la CPU
        del runner no seria comparable con la corrida siguiente."""
        for variant in emit_matrix.VARIANTS:
            if variant["codec"] != "h264":
                continue
            command = self.command(variant["id"])
            params = command[command.index("-x264-params") + 1]
            self.assertIn("cpu-independent=1", params, variant["id"])
            self.assertIn("threads=1", params, variant["id"])

    def test_las_vp9_no_llevan_opciones_de_x264(self):
        for variant in emit_matrix.VARIANTS:
            if variant["codec"] != "vp9":
                continue
            command = self.command(variant["id"])
            self.assertIn("libvpx-vp9", command)
            self.assertNotIn("-x264-params", command)

    def test_el_gop_de_un_segundo_se_conserva_en_cadencia_fija(self):
        """El corte de segmentos a 1 s cae en cuadro clave solo si el GOP
        sigue siendo 15 cuadros a 15 fps (emit_pieces.GOP)."""
        for variant in emit_matrix.VARIANTS:
            if variant.get("vf") or variant["id"] == "ref-defaults-h264":
                continue
            command = " ".join(self.command(variant["id"]))
            self.assertTrue("-g 15" in command or "keyint=15" in command,
                            variant["id"])

    def test_la_cadencia_variable_fuerza_el_cuadro_clave_por_tiempo(self):
        """Con cuadros omitidos, `-g 15` ya no es un segundo: el cuadro clave
        se fuerza por tiempo para que el segmento siga cortando ahi."""
        for variant in emit_matrix.variants_of("cadencia"):
            command = self.command(variant["id"])
            self.assertIn("mpdecimate", command[command.index("-vf") + 1])
            self.assertEqual(command[command.index("-fps_mode") + 1], "vfr")
            self.assertIn("-force_key_frames", command)
            # El filtro decide QUE cuadros entran: va antes del encoder.
            self.assertLess(command.index("-vf"), command.index("-c:v"))

    def test_exactos_solo_omite_cuadros_identicos(self):
        self.assertEqual(emit_matrix.VFR_EXACTOS, "mpdecimate=hi=0:lo=0:frac=1")

    def test_la_referencia_convierte_como_v0(self):
        """La referencia y4m se escribe con la MISMA conversion rgb24 ->
        yuv420p que v0 hacia dentro del comando del encoder."""
        command = emit_matrix.build_reference_command("ffmpeg", 1280, 720, 15,
                                                      "ref.y4m")
        self.assertIn("rawvideo", command)
        self.assertEqual(command[command.index("-pix_fmt") + 1], "rgb24")
        self.assertEqual(command[command.index("-s") + 1], "1280x720")
        self.assertEqual(command[command.index("-r") + 1], "15")
        self.assertEqual(command[-4], "yuv420p")
        self.assertEqual(command[-2], "yuv4mpegpipe")
        self.assertEqual(command[-1], "ref.y4m")

    def test_las_metricas_re_expanden_a_15_fps_y_miden_ssim_y_psnr(self):
        command = emit_matrix.build_metrics_command("ffmpeg", "out.webm", "ref.y4m")
        graph = command[command.index("-lavfi") + 1]
        self.assertTrue(graph.startswith("[0:v]fps=15"))
        self.assertIn("ssim", graph)
        self.assertIn("psnr", graph)
        self.assertEqual(command[-2:], ["null", "-"])


class MetricsParseTest(unittest.TestCase):

    STDERR = ("frame=  231 fps=0.0 q=-0.0 Lsize=N/A time=00:00:15.40\n"
              "[Parsed_ssim_4 @ 0x1] SSIM Y:0.987654 (19.1) U:0.99 (20.0) "
              "V:0.99 (20.0) All:0.988012 (19.2)\n"
              "[Parsed_psnr_5 @ 0x2] PSNR y:41.12 u:45.00 v:45.10 "
              "average:42.05 min:38.0 max:50.0\n")

    def test_lee_ssim_psnr_y_cuadros(self):
        metrics = emit_matrix.parse_metrics(self.STDERR)
        self.assertEqual(metrics["ssim_y"], "0.987654")
        self.assertEqual(metrics["ssim_all"], "0.988012")
        self.assertEqual(metrics["psnr_avg"], "42.05")
        self.assertEqual(metrics["cuadros_comparados"], 231)

    def test_sin_datos_no_inventa(self):
        metrics = emit_matrix.parse_metrics("nada util aca\n")
        self.assertEqual(metrics["ssim_all"], "-")
        self.assertEqual(metrics["psnr_avg"], "-")
        self.assertEqual(metrics["cuadros_comparados"], 0)


def _fila(variant_id, size, ssim, sha="x" * 64):
    variant = emit_matrix.variant_by_id(variant_id)
    return {"id": variant_id, "eje": variant["eje"], "codec": variant["codec"],
            "file": variant_id + "." + variant["ext"], "bytes": str(size),
            "sha256": sha, "cuadros": "231", "ssim_y": str(ssim),
            "ssim_all": str(ssim), "psnr_avg": "40.0", "seg_encode": "10.0",
            "perfil": "-", "note": variant["note"]}


class TsvAndResumenTest(unittest.TestCase):

    def test_tsv_ida_y_vuelta(self):
        rows = [_fila("ref-v0-vp9", 4411693, 0.99), _fila("vp9-crf38", 3000000, 0.98)]
        lines = emit_matrix.tsv_lines(rows, "abc", 1280, 720, 15, 231, "prueba")
        self.assertTrue(lines[0].startswith("#"))
        self.assertIn("grupo prueba", lines[2])
        path = os.path.join(tempfile.mkdtemp(), "MATRIZ-prueba.tsv")
        with open(path, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        back = emit_matrix.read_tsv(path)
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0]["id"], "ref-v0-vp9")
        self.assertEqual(back[1]["bytes"], "3000000")

    def test_una_fila_rota_se_rechaza(self):
        path = os.path.join(tempfile.mkdtemp(), "MATRIZ-rota.tsv")
        with open(path, "w") as stream:
            stream.write("# cabecera\nsolo\tdos\n")
        with self.assertRaises(ValueError):
            emit_matrix.read_tsv(path)

    def test_el_resumen_compara_contra_la_referencia_del_codec(self):
        ref_sha = emit_matrix.V0_SHA256["ref-v0-vp9"]
        rows = [_fila("ref-v0-vp9", 4000000, 0.990, sha=ref_sha),
                _fila("vp9-crf38", 2000000, 0.987),     # -0.003: conserva
                _fila("vp9-crf46", 1000000, 0.970),     # -0.020: pierde
                _fila("ref-v0-h264-baseline", 9000000, 0.995),
                _fila("h264-baseline-crf26", 4500000, 0.992)]
        out = emit_matrix.resumen(rows)
        by_id = dict((row["id"], row) for row in out)
        self.assertEqual(by_id["ref-v0-vp9"]["pct_ref"], "100.0")
        self.assertEqual(by_id["ref-v0-vp9"]["autocontrol"], "v0 IDENTICA")
        self.assertEqual(by_id["ref-v0-h264-baseline"]["autocontrol"], "v0 DISTINTA")
        self.assertEqual(by_id["vp9-crf38"]["pct_ref"], "50.0")
        self.assertEqual(by_id["vp9-crf38"]["look"], "=")
        self.assertEqual(by_id["vp9-crf46"]["look"], "-")
        # La h264 compara contra la baseline v0, no contra la vp9.
        self.assertEqual(by_id["h264-baseline-crf26"]["pct_ref"], "50.0")
        self.assertEqual(by_id["h264-baseline-crf26"]["look"], "=")
        # Orden de lectura = orden de la tabla de variantes.
        self.assertEqual([row["id"] for row in out],
                         ["ref-v0-vp9", "ref-v0-h264-baseline", "vp9-crf38",
                          "vp9-crf46", "h264-baseline-crf26"])

    def test_sin_referencia_no_hay_porcentaje(self):
        out = emit_matrix.resumen([_fila("vp9-crf38", 2000000, 0.987)])
        self.assertEqual(out[0]["pct_ref"], "-")
        self.assertEqual(out[0]["look"], "-")

    def test_el_markdown_lleva_todas_las_filas_y_la_definicion_de_look(self):
        rows = [_fila("ref-v0-vp9", 4000000, 0.990), _fila("vp9-crf38", 2000000, 0.987)]
        text = emit_matrix.resumen_markdown(rows)
        self.assertIn("| ref-v0-vp9 |", text)
        self.assertIn("| vp9-crf38 |", text)
        self.assertIn("ojo del operador", text)


if __name__ == "__main__":
    unittest.main()
