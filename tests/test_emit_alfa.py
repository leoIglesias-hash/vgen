# -*- coding: utf-8 -*-
"""2026-10-19 (H-28): tools/emit_alfa.py emite VP9+alfa y VP8+alfa desde una
fuente con canal alfa y aprovecha el alfa. Sin ffmpeg: la deteccion del
alfa, el decoder de libvpx, el lienzo, el analisis del canal, las palancas
sobre cuadros de numpy, las lineas de los encoders (yuva420p, sin alt-ref,
etiquetas 709 ANTES del `-i`), la medicion del compuesto y el manifiesto."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import emit_alfa as ea  # noqa: E402


def cuadro(alto=8, ancho=10, alfa=0, rgb=(200, 10, 50)):
    rgba = np.zeros((alto, ancho, 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = alfa
    return rgba


class FuenteTest(unittest.TestCase):
    def test_pix_fmt_con_y_sin_alfa(self):
        for pix in ("yuva444p12le", "yuva420p", "rgba", "bgra", "argb", "gbrap", "ya8",
                    "rgba64le"):
            self.assertTrue(ea.tiene_alfa(pix), pix)
        for pix in ("yuv420p", "yuv444p10le", "rgb24", "gbrp", "gray", "nv12"):
            self.assertFalse(ea.tiene_alfa(pix), pix)

    def test_webm_con_alfa_dice_yuv420p_y_alpha_mode(self):
        # El alfa de un WebM viaja aparte; ffprobe dice yuv420p + ALPHA_MODE=1.
        self.assertTrue(ea.tiene_alfa("yuv420p", "1"))
        self.assertEqual(ea.decoder_de("vp9", "1"), ["-c:v", "libvpx-vp9"])
        self.assertEqual(ea.decoder_de("vp8", "1"), ["-c:v", "libvpx"])
        self.assertEqual(ea.decoder_de("vp9", ""), [])
        self.assertEqual(ea.decoder_de("prores", ""), [])

    def test_parse_probe_con_tags(self):
        texto = ("codec_name=vp9\npix_fmt=yuv420p\nwidth=898\nheight=360\n"
                 "r_frame_rate=15/1\nTAG:alpha_mode=1\n")
        valores = ea.parse_probe(texto)
        self.assertEqual(valores["alpha_mode"], "1")
        self.assertEqual(valores["width"], "898")


class LienzoTest(unittest.TestCase):
    def test_lienzo_par_y_proporcional(self):
        self.assertEqual(ea.lienzo(1920, 1080, 1280), (1280, 720))
        self.assertEqual(ea.lienzo(898, 360, 1280), (1280, 514))
        self.assertEqual(ea.lienzo(1921, 1081, 0), (1920, 1080))

    def test_escalado_sobre_alfa_premultiplicado(self):
        filtro = ea.filtro_base(1920, 1080, 1280, 720, 15)
        partes = filtro.split(",")
        self.assertEqual(partes[0], "fps=15")
        self.assertLess(partes.index("premultiply=inplace=1"),
                        partes.index("scale=1280:720:flags=lanczos"))
        self.assertLess(partes.index("scale=1280:720:flags=lanczos"),
                        partes.index("unpremultiply=inplace=1"))
        self.assertEqual(partes[-1], "format=rgba")

    def test_sin_escalado_no_premultiplica(self):
        self.assertEqual(ea.filtro_base(1280, 720, 1280, 720, 15), "fps=15,format=rgba")

    def test_lectura_con_decoder_antes_del_i(self):
        command = ea.build_rgba_command("ffmpeg", "e.webm", ["-c:v", "libvpx-vp9"], "fps=15", 30)
        self.assertEqual(command[command.index("-i") - 1], "libvpx-vp9")
        self.assertEqual(command[command.index("-frames:v") + 1], "30")
        self.assertEqual(command[-5:], ["-f", "rawvideo", "-pix_fmt", "rgba", "-"])


class AnalisisTest(unittest.TestCase):
    def analizar(self, cuadros):
        alto, ancho = cuadros[0].shape[:2]
        analisis = ea.Analisis(ancho, alto)
        for c in cuadros:
            analisis.cuadro(c)
        return analisis.resumen()

    def test_rect_hueco_y_alfa_suave(self):
        vacio = cuadro(alfa=0)
        a = cuadro(alfa=0)
        a[2:4, 3:6, 3] = 255
        b = cuadro(alfa=0)
        b[5, 7, 3] = 128
        r = self.analizar([vacio, a, vacio, b, vacio])
        self.assertFalse(r["siempre_opaco"])
        # union [3, 2) .. (8, 6) llevada a pares: x 2 y 2, 6x4
        self.assertEqual(r["rect"], (2, 2, 6, 4))
        self.assertEqual((r["desde"], r["hasta"]), (1, 4))
        self.assertEqual(r["huecos"], [(2, 1)])
        self.assertEqual(r["vacios"], 3)
        self.assertAlmostEqual(r["semi"], 1 / 7.0)
        self.assertEqual(r["color_medio"], (200, 10, 50))

    def test_siempre_opaco(self):
        r = self.analizar([cuadro(alfa=255), cuadro(alfa=255)])
        self.assertTrue(r["siempre_opaco"])
        self.assertEqual(r["rect"], (0, 0, 10, 8))
        self.assertEqual(r["area_rect"], 1.0)

    def test_rect_par_no_se_sale_del_lienzo(self):
        self.assertEqual(ea.rect_par([3, 1, 9, 7], 10, 8), (2, 0, 8, 8))
        self.assertEqual(ea.rect_par([0, 0, 10, 8], 10, 8), (0, 0, 10, 8))

    def test_tramos_vacios(self):
        self.assertEqual(ea.tramos_vacios([0, 1, 4, 5, 6, 9], 10), (2, 9, [(4, 3)]))
        self.assertEqual(ea.tramos_vacios([], 3), (0, 3, []))
        self.assertEqual(ea.tramos_vacios([0, 1], 2), (0, 0, []))


class PalancasTest(unittest.TestCase):
    def test_limpiar_plano_pinta_solo_lo_invisible(self):
        rgba = cuadro(alfa=0, rgb=(1, 2, 3))
        rgba[0, 0] = (90, 91, 92, 10)
        ea.limpiar(rgba, "plano", (50, 60, 70))
        self.assertEqual(tuple(rgba[0, 0]), (90, 91, 92, 10))
        self.assertEqual(tuple(rgba[5, 5]), (50, 60, 70, 0))

    def test_limpiar_no_deja_todo(self):
        rgba = cuadro(alfa=0, rgb=(1, 2, 3))
        ea.limpiar(rgba, "no", (50, 60, 70))
        self.assertEqual(tuple(rgba[5, 5]), (1, 2, 3, 0))

    def test_sangrado_extiende_el_borde_y_despues_plano(self):
        rgba = cuadro(alto=4, ancho=20, alfa=0, rgb=(0, 0, 0))
        rgba[:, 0] = (100, 150, 200, 255)
        ea.limpiar(rgba, "sangrado", (7, 7, 7))
        self.assertEqual(tuple(rgba[1, ea.SANGRADO_PASOS, :3]), (100, 150, 200))
        self.assertEqual(tuple(rgba[1, ea.SANGRADO_PASOS + 1, :3]), (7, 7, 7))
        self.assertEqual(int(rgba[1, 5, 3]), 0)    # el alfa no se toca

    def test_el_default_es_plano(self):
        # Medido el 2026-10-19: plano -21 % contra sangrado, mismo compuesto.
        self.assertEqual(ea.LIMPIAR, "plano")

    def test_binarizar(self):
        rgba = cuadro(alfa=0)
        rgba[0, :4, 3] = (0, 127, 128, 255)
        ea.binarizar(rgba, 128)
        self.assertEqual(list(rgba[0, :4, 3]), [0, 0, 255, 255])

    def test_recortar(self):
        rgba = cuadro()
        self.assertEqual(ea.recortar(rgba, (2, 2, 6, 4)).shape, (4, 6, 4))

    def test_luma_709_rango_tv(self):
        rgb = np.array([[[0, 0, 0], [255, 255, 255], [255, 0, 0]]], dtype=np.uint8)
        y = ea.luma_709(rgb)[0]
        self.assertAlmostEqual(y[0], 16.0)
        self.assertAlmostEqual(y[1], 235.0)
        self.assertAlmostEqual(y[2], 16.0 + 219.0 * 0.2126)

    def test_variantes_de_palancas(self):
        resumen = {"area_rect": 0.35, "desde": 15, "hasta": 60, "cuadros": 60, "semi": 0.2}
        opciones = {"limpiar_modo": "plano", "recorte": True, "tiempo": True, "umbral": 0}
        nombres = [n for n, _ in ea.variantes_palancas(opciones, resumen)]
        self.assertEqual(nombres, ["receta", "sin-limpiar", "con-sangrado", "sin-recorte",
                                   "sin-hueco", "alfa-binario-128"])
        lleno = {"area_rect": 1.0, "desde": 0, "hasta": 60, "cuadros": 60, "semi": 0.0}
        self.assertEqual([n for n, _ in ea.variantes_palancas(opciones, lleno)],
                         ["receta", "sin-limpiar", "con-sangrado"])


class RecetaTest(unittest.TestCase):
    def test_alfa_vp9_y_vp8(self):
        vp9, vp8 = ea.recipe(fps=15)
        self.assertEqual([vp9["id"], vp8["id"]], ["alfa-vp9", "alfa-vp8"])
        for pieza in (vp9, vp8):
            args = pieza["args"]
            self.assertEqual(args[args.index("-pix_fmt") + 1], "yuva420p")
            # libvpx no codifica alfa con cuadros alt-ref.
            self.assertEqual(args[args.index("-auto-alt-ref") + 1], "0")
            self.assertEqual(args[args.index("-g") + 1], "15")
            self.assertEqual(args[args.index("-colorspace") + 1], "bt709")
            self.assertTrue(pieza["alfa"])
        self.assertEqual(vp9["args"][vp9["args"].index("-c:v") + 1], "libvpx-vp9")
        self.assertEqual(vp8["args"][vp8["args"].index("-c:v") + 1], "libvpx")
        self.assertEqual(vp9["args"][vp9["args"].index("-crf") + 1], str(ea.VP9_CRF))
        # VP8 con crf necesita un tope de bitrate (con 0 no hace crf).
        self.assertEqual(vp8["args"][vp8["args"].index("-b:v") + 1], ea.VP8_TOPE)
        self.assertEqual(vp9["decoder"], ["-c:v", "libvpx-vp9"])
        self.assertEqual(vp8["decoder"], ["-c:v", "libvpx"])

    def test_no_hay_h265(self):
        # Operador, 2026-10-19: "h265 no lo vamos a usar".
        for opaco in (False, True):
            for pieza in ea.recipe(opaco=opaco):
                self.assertNotIn("libx265", pieza["args"])
                self.assertNotIn("hevc", pieza["mime"])

    def test_opaco_es_pieza_normal(self):
        vp9, h264 = ea.recipe(opaco=True)
        self.assertEqual([vp9["id"], h264["id"]], ["opaco-vp9", "opaco-h264"])
        self.assertEqual(vp9["args"][vp9["args"].index("-pix_fmt") + 1], "yuv420p")
        self.assertIn("cpu-independent=1", h264["args"][h264["args"].index("-x264-params") + 1])
        self.assertFalse(vp9["alfa"])

    def test_mime_con_y_sin_opus(self):
        self.assertEqual(ea.recipe(audio=True)[0]["mime"], 'video/webm; codecs="vp9, opus"')
        self.assertEqual(ea.recipe(audio=False)[1]["mime"], 'video/webm; codecs="vp8"')
        self.assertNotIn("mp4a", ea.recipe(opaco=True, audio=False)[1]["mime"])
        self.assertIn("mp4a", ea.recipe(opaco=True, audio=True)[1]["mime"])

    def test_solo(self):
        self.assertEqual([p["id"] for p in ea.recipe(solo="vp8")], ["alfa-vp8"])


class ComandosTest(unittest.TestCase):
    def setUp(self):
        self.vp9 = ea.recipe(audio=True)[0]

    def test_la_referencia_entra_etiquetada_709(self):
        # Lecciones del 2026-10-18: la etiqueta va ANTES del `-i`.
        command = ea.build_commands("ffmpeg", self.vp9, "ref.yuva", 898, 360, 15, "o.webm", "l")[-1]
        antes = command[:command.index("-i")]
        for flag, valor in (("-colorspace", "bt709"), ("-color_primaries", "bt709"),
                            ("-color_trc", "bt709"), ("-color_range", "tv")):
            self.assertEqual(antes[antes.index(flag) + 1], valor)
        self.assertEqual(antes[antes.index("-pix_fmt") + 1], "yuva420p")
        self.assertEqual(antes[antes.index("-s") + 1], "898x360")
        self.assertEqual(command[command.index("-i") + 1], "ref.yuva")
        self.assertIn("+bitexact", command)
        self.assertEqual(command[command.index("-threads") + 1], "1")
        self.assertEqual(command[-1], "o.webm")

    def test_audio_desde_el_primer_cuadro_emitido(self):
        command = ea.build_commands("ffmpeg", self.vp9, "ref.yuva", 898, 360, 15, "o.webm", "l",
                                    "f.mov", 1.0, 3.0)[-1]
        segunda = [i for i, x in enumerate(command) if x == "-i"][1]
        self.assertEqual(command[segunda + 1], "f.mov")
        self.assertEqual(command[command.index("-ss") + 1], "1.000000")
        self.assertEqual(command[command.index("-t") + 1], "3.000000")
        self.assertIn("1:a:0", command)
        self.assertEqual(command[command.index("-c:a") + 1], "libopus")

    def test_sin_audio_es_mudo(self):
        command = ea.build_commands("ffmpeg", self.vp9, "r", 2, 2, 15, "o.webm", "l")[-1]
        self.assertIn("-an", command)
        self.assertNotIn("-c:a", command)

    def test_dos_pasadas(self):
        vp9 = ea.recipe(vp9_2pass=True)[0]
        uno, dos = ea.build_commands("ffmpeg", vp9, "r", 2, 2, 15, "o.webm", "log")
        self.assertEqual(uno[uno.index("-pass") + 1], "1")
        self.assertEqual(dos[dos.index("-pass") + 1], "2")

    def test_referencia_rgba_a_yuva_709(self):
        command = ea.build_ref_command("ffmpeg", 898, 360, 15, "ref.yuva")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "rgba")
        self.assertIn("scale=out_color_matrix=bt709:out_range=tv,format=yuva420p", command)
        self.assertEqual(command[-3:], ["-pix_fmt", "yuva420p", "ref.yuva"])

    def test_la_medicion_decodifica_con_libvpx(self):
        # El decoder nativo de ffmpeg descarta el alfa: la medicion lo veria opaco.
        command = ea.build_decode_command("ffmpeg", self.vp9, "o.webm")
        self.assertEqual(command[command.index("-i") - 1], "libvpx-vp9")
        self.assertIn("yuva420p", command)

    def test_sintetico(self):
        command = ea.build_sintetico_command("ffmpeg", "s.mov")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuva444p10le")
        self.assertEqual(command[command.index("-profile:v") + 1], "4444")


class MedicionTest(unittest.TestCase):
    def planos(self, y, a, alto=4, ancho=4):
        return (np.full((alto, ancho), y, np.uint8), np.full((alto // 2, ancho // 2), 128, np.uint8),
                np.full((alto // 2, ancho // 2), 128, np.uint8), np.full((alto, ancho), a, np.uint8))

    def test_lo_invisible_no_cuenta_en_el_compuesto(self):
        sse, n = ea.sse_compuesto(self.planos(10, 0), self.planos(200, 0))
        self.assertEqual((sse, n), (0.0, 0))

    def test_el_compuesto_pesa_con_el_alfa(self):
        # Opaco: 16 lumas con error 10, croma igual (4 + 4 muestras).
        self.assertEqual(ea.sse_compuesto(self.planos(138, 255), self.planos(128, 255)),
                         (1600.0, 24))
        # Medio transparente: el error se ve a medias (20 * 128/255 por luma).
        medio, n = ea.sse_compuesto(self.planos(148, 128), self.planos(128, 128))
        self.assertAlmostEqual(medio, 16 * (20 * 128 / 255.0) ** 2, places=6)
        self.assertEqual(n, 24)

    def test_psnr(self):
        self.assertIsNone(ea.psnr_de(0, 0))
        self.assertEqual(ea.psnr_de(0, 10), 99.0)
        self.assertAlmostEqual(ea.psnr_de(255.0 ** 2, 1), 0.0)

    def test_alarma_de_alfa(self):
        self.assertIn("ALARMA DE ALFA", ea.alarma_alfa(False, True))
        self.assertEqual(ea.alarma_alfa(True, True), "")
        self.assertEqual(ea.alarma_alfa(False, False), "")


class ManifiestoTest(unittest.TestCase):
    def test_manifiesto_con_lienzo_rect_y_tiempo(self):
        fuente = {"nombre": "e.mov", "codec": "prores", "pix_fmt": "yuva444p12le",
                  "width": 1920, "height": 1080, "fps": "30/1", "alpha_mode": ""}
        resumen = {"lienzo": (1280, 720), "siempre_opaco": False, "cobertura": 0.083,
                   "area_rect": 0.351, "semi": 0.212, "huecos": [(20, 3)]}
        ref = {"rect": (258, 180, 898, 360), "desde": 15, "hasta": 60}
        fila = {"id": "alfa-vp9", "role": "alfa", "mime": "m", "file": "alfa-vp9.webm",
                "bytes": 1, "sha256": "ab", "note": "n"}
        lineas = ea.manifest_lines([fila], "f00", fuente, resumen, ref, 15, "receta")
        self.assertIn("# lienzo\t1280x720\t15 fps", lineas)
        self.assertTrue(lineas[4].startswith("# rect\t258\t180\t898\t360\t"))
        self.assertTrue(lineas[5].startswith("# tiempo\t15\t60\t"))
        self.assertIn("(1.000 s)", lineas[5])
        self.assertIn("huecos 20+3", lineas[6])
        self.assertEqual(lineas[-2], "# " + "\t".join(ea.MANIFEST_COLUMNS))
        self.assertEqual(lineas[-1], "alfa-vp9\talfa\tm\talfa-vp9.webm\t1\tab\tn")

    def test_receta_canonica(self):
        args = ea.argparse.Namespace(ancho=1280, fps=15, vp9_crf=30, vp8_crf=24, vp8_tope="4M",
                                     limpiar="plano", tiempo="auto", vp9_2pass=False,
                                     sin_recorte=False, alfa_binario=0, solo=None, frames=None)
        self.assertEqual(ea.receta_de(args),
                         "--ancho 1280 --fps 15 --vp9-crf 30 --vp8-crf 24 --vp8-tope 4M "
                         "--limpiar plano --tiempo auto")


if __name__ == "__main__":
    unittest.main()
