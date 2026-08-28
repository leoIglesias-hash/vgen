# -*- coding: utf-8 -*-
"""E-16: PairLUT exacto — base, partner y level por pixel real."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import dither  # noqa: E402
import perceptual_palette as perceptual  # noqa: E402


PALETTE = np.asarray(
    ((75, 55, 119), (39, 155, 150), (59, 114, 134),
     (229, 115, 189), (253, 76, 150), (223, 241, 156)), dtype=np.uint8)


def gradient_rgb():
    start = np.asarray((130, 3, 195), dtype=np.float64)
    stop = np.asarray((76, 176, 22), dtype=np.float64)
    alpha = np.linspace(0.0, 1.0, 128)[None, :, None]
    row = start * (1.0 - alpha) + stop * alpha
    return np.tile(row, (32, 1, 1)).astype(np.uint8)


def rgb555_centers():
    keys = np.arange(32768, dtype=np.int32)
    colors = np.empty((32768, 3), dtype=np.int32)
    colors[:, 0] = ((keys >> 10) & 31) * 8 + 4
    colors[:, 1] = ((keys >> 5) & 31) * 8 + 4
    colors[:, 2] = (keys & 31) * 8 + 4
    return np.minimum(colors, 255)


class PairLutExactTest(unittest.TestCase):
    def test_exact_pairs_reproduce_the_lut_on_555_centers(self):
        lut = dither.PairLUT(PALETTE)
        centers = rgb555_centers()
        partner, level = lut.exact_pairs(centers, lut.base.astype(np.int32))
        np.testing.assert_array_equal(partner, lut.partner)
        np.testing.assert_array_equal(level, lut.level)

    def test_silenced_pixels_now_dither_from_their_real_base(self):
        rgb = gradient_rgb()
        quantizer = perceptual.PerceptualQuantizer(PALETTE, lut_bits=5)
        baseline = quantizer.quantize(rgb)
        rgb_lut = dither.PairLUT(PALETTE)
        keys = dither.rgb555_keys(rgb)
        mismatch = rgb_lut.base[keys] != baseline
        # El escenario de la tarea existe: la base 555 discrepa del
        # cuantizador real en una fraccion sustancial de los pixeles.
        self.assertGreater(float(np.mean(mismatch)), 0.25)
        result, details = dither.apply_selective_dither(
            rgb, baseline, PALETTE, pair_lut=rgb_lut,
            min_gradient_range=4, return_details=True)
        changed = details["changed"]
        self.assertTrue(np.any(changed))
        # Antes de E-16 estos pixeles quedaban en Q0 por definicion.
        self.assertTrue(np.any(changed & mismatch))

    def test_accepted_mixtures_beat_their_real_base(self):
        rgb = gradient_rgb()
        quantizer = perceptual.PerceptualQuantizer(PALETTE, lut_bits=5)
        baseline = np.asarray(quantizer.quantize(rgb))
        lut = dither.PairLUT(PALETTE)
        flat_rgb = rgb.reshape(-1, 3)
        flat_base = baseline.reshape(-1).astype(np.int32)
        partner, level = lut.exact_pairs(flat_rgb, flat_base)
        active = level > 0
        self.assertTrue(np.any(active))
        pal = PALETTE.astype(np.int64)
        src = flat_rgb[active].astype(np.int64)
        a = pal[flat_base[active]]
        b = pal[partner[active].astype(np.int64)]
        mix_level = level[active].astype(np.int64)[:, None]
        mixed4 = a * (4 - mix_level) + b * mix_level
        mix_error = np.sum((src * 4 - mixed4) ** 2, axis=1)
        base_error = np.sum((src - a) ** 2, axis=1) * 16
        self.assertTrue(np.all(
            mix_error < base_error * (1.0 - lut.min_improvement)))

    def test_exact_pairs_are_validated(self):
        lut = dither.PairLUT(PALETTE)
        with self.assertRaisesRegex(ValueError, "mismo largo"):
            lut.exact_pairs(np.zeros((4, 3), dtype=np.uint8), np.zeros(3))
        with self.assertRaisesRegex(ValueError, "fuera de palette"):
            lut.exact_pairs(np.zeros((2, 3), dtype=np.uint8),
                            np.asarray((0, 9)))
        partner, level = lut.exact_pairs(
            np.zeros((0, 3), dtype=np.uint8), np.zeros(0, dtype=np.int32))
        self.assertEqual(len(partner), 0)
        self.assertEqual(len(level), 0)

    def test_selective_result_is_deterministic_and_chunk_independent(self):
        rgb = gradient_rgb()
        quantizer = perceptual.PerceptualQuantizer(PALETTE, lut_bits=5)
        baseline = np.asarray(quantizer.quantize(rgb))
        lut = dither.PairLUT(PALETTE)
        flat_rgb = rgb.reshape(-1, 3)
        flat_base = baseline.reshape(-1)
        small = lut.exact_pairs(flat_rgb, flat_base, chunk_size=97)
        large = lut.exact_pairs(flat_rgb, flat_base, chunk_size=100000)
        self.assertEqual(small[0].tobytes(), large[0].tobytes())
        self.assertEqual(small[1].tobytes(), large[1].tobytes())


if __name__ == "__main__":
    unittest.main()
