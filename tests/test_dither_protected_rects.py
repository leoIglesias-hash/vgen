"""E-05: rects protegidos en el dither selectivo.

Ninguna celda dentro de un rect declarado puede ser modificada por el dither;
fuera de los rects el comportamiento es identico al historico, y sin rects
declarados la salida no cambia en absoluto (Δbytes: no).
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import dither  # noqa: E402


def nearest_indices(rgb, palette):
    source = rgb.astype(np.int32)
    colors = palette.astype(np.int32)
    delta = source[:, :, None, :] - colors[None, None, :, :]
    return np.argmin(np.sum(delta * delta, axis=3), axis=2).astype(np.uint8)


def gray_gradient(height=32, width=128):
    gray = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    return np.repeat(gray[:, :, None], 3, axis=2)


PALETTE = np.asarray(((0, 0, 0), (85, 85, 85),
                      (170, 170, 170), (255, 255, 255)), dtype=np.uint8)


class ProtectedRectsTest(unittest.TestCase):
    def setUp(self):
        self.rgb = gray_gradient()
        self.baseline = nearest_indices(self.rgb, PALETTE)

    def test_no_cell_inside_a_declared_rect_is_dithered(self):
        rect = (40, 8, 32, 16)  # x0, y0, w, h
        free = dither.apply_selective_dither(
            self.rgb, self.baseline, PALETTE, min_gradient_range=4)
        fenced = dither.apply_selective_dither(
            self.rgb, self.baseline, PALETTE, min_gradient_range=4,
            protected_rects=[rect])
        changed_free = np.count_nonzero(free != self.baseline)
        self.assertGreater(changed_free, 0, "el escenario no trama nada")

        x0, y0, w, h = rect
        inside = fenced[y0:y0 + h, x0:x0 + w]
        np.testing.assert_array_equal(
            inside, self.baseline[y0:y0 + h, x0:x0 + w],
            "una celda dentro del rect fue modificada por el dither")
        # fuera del rect el dither sigue activo
        outside_changed = np.count_nonzero(fenced != self.baseline)
        self.assertGreater(outside_changed, 0)

    def test_without_rects_output_is_byte_identical(self):
        legacy = dither.apply_selective_dither(
            self.rgb, self.baseline, PALETTE, min_gradient_range=4)
        wired = dither.apply_selective_dither(
            self.rgb, self.baseline, PALETTE, min_gradient_range=4,
            protected_rects=None)
        empty = dither.apply_selective_dither(
            self.rgb, self.baseline, PALETTE, min_gradient_range=4,
            protected_rects=[])
        self.assertEqual(legacy.tobytes(), wired.tobytes())
        self.assertEqual(legacy.tobytes(), empty.tobytes())

    def test_selective_tile_mask_excludes_rect_cells(self):
        rect = (0, 0, 64, 32)
        mask = dither.selective_tile_mask(
            self.rgb, self.baseline, PALETTE, min_range=4,
            protected_rects=[rect])
        self.assertFalse(bool(mask[:32, :64].any()))

    def test_out_of_grid_rect_is_rejected(self):
        for bad in ((0, 0, 200, 8), (-1, 0, 4, 4), (0, 0, 0, 4),
                    (120, 28, 16, 8)):
            with self.assertRaises(ValueError):
                dither.apply_selective_dither(
                    self.rgb, self.baseline, PALETTE, min_gradient_range=4,
                    protected_rects=[bad])

    def test_caller_protected_mask_is_not_mutated(self):
        protected = np.zeros(self.baseline.shape, dtype=bool)
        snapshot = protected.copy()
        dither.selective_tile_mask(
            self.rgb, self.baseline, PALETTE, protected=protected,
            min_range=4, protected_rects=[(8, 8, 8, 8)])
        np.testing.assert_array_equal(protected, snapshot)


if __name__ == "__main__":
    unittest.main()
