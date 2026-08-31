# -*- coding: utf-8 -*-
"""E-24 (paso 1): columnas err_temporal y proxy_banding en tools/bench_ref.py.

Las columnas historicas del bench (psnr_rgb_db, err_oklab_medio) son promedios
por pixel ciegos al arrastre temporal y al banding — por eso las decisiones de
E-17 y E-22 tuvieron que ser visuales. Estas dos columnas miden exactamente lo
que el criterio de cierre de E-24 exige comparar contra el baseline:

- err_temporal ve el movimiento mal reproducido (arrastre/flicker) y un
  corrimiento estatico no lo infla;
- proxy_banding ve el contorno de un plateau sobre zonas suaves de la fuente
  y NO castiga al dither (el promedio 2x2 anula el tramado);
- integracion: sobre el sintetico de E-22, el encode con trellis temporal
  generoso debe medir MAS err_temporal que el encode pelado — la columna ve
  lo que el PSNR no vio.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import encoder  # noqa: E402
import bench_ref  # noqa: E402


class ColumnsContractTest(unittest.TestCase):
    def test_new_columns_sit_between_oklab_and_sha(self):
        self.assertEqual(
            bench_ref.COLUMNS,
            ("archivo", "bytes_ascl", "bytes_asclv", "bytes_celda_frame",
             "frames", "keyframes", "cadena_delta_max", "tags",
             "psnr_rgb_db", "err_oklab_medio", "err_temporal",
             "proxy_banding", "sha256"))


class TemporalErrorTest(unittest.TestCase):
    def test_static_offset_between_decode_and_source_cancels(self):
        src_prev = np.zeros((6, 3))
        src = np.full((6, 3), 0.25)
        offset = np.array([0.1, -0.05, 0.02])
        # decodificado = fuente + offset en AMBOS frames -> deltas iguales
        err = bench_ref.temporal_error_oklab(
            src + offset, src_prev + offset, src, src_prev)
        self.assertAlmostEqual(err, 0.0)

    def test_frozen_decode_measures_exactly_the_source_motion(self):
        src_prev = np.zeros((4, 3))
        src = np.tile([0.3, 0.0, 0.0], (4, 1))
        frozen = np.full((4, 3), 0.7)
        err = bench_ref.temporal_error_oklab(frozen, frozen, src, src_prev)
        self.assertAlmostEqual(err, 0.3)

    def test_flicker_counts_symmetrically(self):
        still = np.zeros((4, 3))
        blinked = np.tile([0.0, 0.2, 0.0], (4, 1))
        err = bench_ref.temporal_error_oklab(blinked, still, still, still)
        self.assertAlmostEqual(err, 0.2)


def ramp_plane(rows=16, cols=64, step=0.002):
    return np.tile(np.arange(cols) * step, (rows, 1))


def bayer_dither(plane, quantum):
    thresholds = np.array([[0.125, 0.625], [0.875, 0.375]])
    rows, cols = plane.shape
    tiles = np.tile(thresholds,
                    ((rows + 1) // 2, (cols + 1) // 2))[:rows, :cols]
    low = np.floor(plane / quantum) * quantum
    frac = (plane - low) / quantum
    return low + quantum * (frac > tiles)


class BandingProxyTest(unittest.TestCase):
    def test_identical_smooth_ramp_scores_zero(self):
        ramp = ramp_plane()
        total, positions = bench_ref.banding_stats(ramp, ramp)
        self.assertGreater(positions, 0)
        self.assertEqual(total, 0.0)

    def test_quantized_plateaus_on_a_smooth_ramp_score_positive(self):
        ramp = ramp_plane()
        quantized = np.floor(ramp / 0.02) * 0.02
        total, positions = bench_ref.banding_stats(quantized, ramp)
        self.assertGreater(positions, 0)
        self.assertGreater(total, 0.0)

    def test_dither_scores_well_below_hard_quantization(self):
        # La razon de ser de la columna: err_oklab_medio castiga al dither,
        # el proxy no debe hacerlo (el promedio 2x2 anula el tramado).
        ramp = ramp_plane()
        quantized = np.floor(ramp / 0.02) * 0.02
        dithered = bayer_dither(ramp, 0.02)
        quant_total, positions = bench_ref.banding_stats(quantized, ramp)
        dith_total, dith_positions = bench_ref.banding_stats(dithered, ramp)
        self.assertEqual(positions, dith_positions)
        self.assertLess(dith_total, quant_total / 2.0)

    def test_real_edges_are_masked_even_if_decode_exaggerates_them(self):
        rows, cols = 16, 64
        src = np.zeros((rows, cols))
        src[:, cols // 2:] = 0.5   # borde real, muy por encima del umbral
        dec = np.zeros((rows, cols))
        dec[:, cols // 2:] = 0.6   # el decodificado lo exagera
        total, _positions = bench_ref.banding_stats(dec, src)
        self.assertEqual(total, 0.0)

    def test_block_mean_crops_odd_sizes_deterministically(self):
        plane = np.arange(15.0).reshape(3, 5)
        reduced = bench_ref._block_mean(plane, 2)
        self.assertEqual(reduced.shape, (1, 2))
        self.assertAlmostEqual(float(reduced[0, 0]), (0 + 1 + 5 + 6) / 4.0)


# ---- integracion: barra blanca que se mueve sobre fondo negro ----
#
# Blanco y negro son exactamente representables, asi que el encode pelado
# reconstruye el movimiento EXACTO (err_temporal = 0) y su PSNR es perfecto.
# Con presupuesto temporal generoso el trellis congela la barra (la celda
# revierte al indice previo) y SOLO la columna nueva ve el arrastre.

WIDTH = 192
HEIGHT = 96
BAR_W = 24


def moving_bar_frame(left):
    gray = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    gray[:, left:left + BAR_W] = 255
    return np.repeat(gray[:, :, None], 3, axis=2), gray


FRAMES = [moving_bar_frame(left) for left in (0, 32, 64, 96, 128, 160)]


def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
    return iter(FRAMES)


class BenchRowIntegrationTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.directory = holder.name

    def encode_and_measure(self, tag, **options):
        out_path = os.path.join(self.directory, "%s.ascl" % tag)
        defaults = dict(
            mode_name="pixel", cols=WIDTH, rows=HEIGHT, fps=15, pal_size=4,
            ramp_name="short", char_aspect=0.5, compress="auto",
            palette_mode="global", keyint=64, with_audio=False,
            palette_algorithm="kmeans-oklab")
        defaults.update(options)
        with mock.patch.object(encoder, "probe_size",
                               return_value=(WIDTH, HEIGHT)), \
                mock.patch.object(encoder, "iter_video_frames",
                                  side_effect=fake_iter):
            encoder.encode_video("synthetic.mp4", out_path, **defaults)
            return bench_ref.measure(out_path, source="synthetic.mp4")

    def test_temporal_trellis_smearing_is_visible_in_the_new_column(self):
        plain = self.encode_and_measure("plain")
        # blanco->negro cuesta 255*sqrt(3) ~ 442: el presupuesto debe superarlo
        smeared = self.encode_and_measure("smeared", trellis_temporal=500.0)
        for row in (plain, smeared):
            self.assertNotEqual(row["err_temporal"], "-")
            self.assertNotEqual(row["proxy_banding"], "-")
            self.assertGreaterEqual(float(row["err_temporal"]), 0.0)
            self.assertGreaterEqual(float(row["proxy_banding"]), 0.0)
        self.assertGreater(float(smeared["err_temporal"]),
                           float(plain["err_temporal"]),
                           "el arrastre del trellis temporal debe subir "
                           "err_temporal respecto del encode pelado")

    def test_v3_is_measured_and_matches_v2_quality_columns(self):
        # F6-2/F6-3: bench_ref debe aceptar ASCL v3 (antes cortaba con
        # "version ASCL desconocida: 3" y dejaba la fila vacia). v3 es
        # lossless respecto de v2: solo pueden moverse las columnas de bytes.
        import ascl_v2
        out_path = os.path.join(self.directory, "forv3.ascl")
        with mock.patch.object(encoder, "probe_size",
                               return_value=(WIDTH, HEIGHT)), \
                mock.patch.object(encoder, "iter_video_frames",
                                  side_effect=fake_iter):
            encoder.encode_video("synthetic.mp4", out_path,
                                 mode_name="pixel", cols=WIDTH, rows=HEIGHT,
                                 fps=15, pal_size=4, ramp_name="short",
                                 char_aspect=0.5, compress="auto",
                                 palette_mode="global", keyint=64,
                                 with_audio=False,
                                 palette_algorithm="kmeans-oklab")
            with open(out_path, "rb") as stream:
                v1 = stream.read()
            rows = {}
            for version in (2, 3):
                converted, _ = ascl_v2.transcode_ascl_bytes(
                    v1, emit_version=version)
                path = os.path.join(self.directory, "conv%d.ascl" % version)
                with open(path, "wb") as stream:
                    stream.write(converted)
                rows[version] = bench_ref.measure(path, source="synthetic.mp4")
        self.assertNotEqual(rows[3]["err_temporal"], "-")
        for column in ("psnr_rgb_db", "err_oklab_medio", "err_temporal",
                       "proxy_banding", "frames", "keyframes"):
            self.assertEqual(rows[2][column], rows[3][column],
                             "v3 es lossless: la columna %s no puede moverse"
                             % column)

    def test_without_source_the_new_columns_stay_dashes(self):
        out_path = os.path.join(self.directory, "nosrc.ascl")
        with mock.patch.object(encoder, "probe_size",
                               return_value=(WIDTH, HEIGHT)), \
                mock.patch.object(encoder, "iter_video_frames",
                                  side_effect=fake_iter):
            encoder.encode_video("synthetic.mp4", out_path,
                                 mode_name="pixel", cols=WIDTH, rows=HEIGHT,
                                 fps=15, pal_size=4, ramp_name="short",
                                 char_aspect=0.5, compress="auto",
                                 palette_mode="global", keyint=64,
                                 with_audio=False,
                                 palette_algorithm="kmeans-oklab")
        row = bench_ref.measure(out_path)
        self.assertEqual(row["err_temporal"], "-")
        self.assertEqual(row["proxy_banding"], "-")


if __name__ == "__main__":
    unittest.main()
