# -*- coding: utf-8 -*-
"""E-17: presupuesto de dither en BYTES reales, junto al de celdas."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import zlib  # noqa: E402

import deflate_util  # noqa: E402
import dither  # noqa: E402
import encoder  # noqa: E402


PALETTE = np.asarray(((0, 0, 0), (85, 85, 85),
                      (170, 170, 170), (255, 255, 255)), dtype=np.uint8)


def gray_gradient(height=32, width=128):
    gray = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    return np.repeat(gray[:, :, None], 3, axis=2)


def nearest_indices(rgb, palette):
    source = rgb.astype(np.int32)
    colors = palette.astype(np.int32)
    delta = source[:, :, None, :] - colors[None, None, :, :]
    return np.argmin(np.sum(delta * delta, axis=3), axis=2).astype(np.uint8)


def cost_by_changes(baseline):
    """Costo monotono y determinista: bytes = celdas distintas del baseline."""
    reference = np.asarray(baseline)

    def cost(index_map):
        return int(np.count_nonzero(np.asarray(index_map) != reference))
    return cost


class ByteBudgetCalibratedTest(unittest.TestCase):
    def setUp(self):
        self.rgb = gray_gradient()
        self.baseline = nearest_indices(self.rgb, PALETTE)
        self.cost = cost_by_changes(self.baseline)

    def test_generous_budget_is_byte_identical_to_no_budget(self):
        plain, plain_details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            return_details=True)
        self.assertGreater(int(plain_details["changed_cells"]), 0)
        budgeted, details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            byte_cost=self.cost, max_extra_bytes=10 ** 9,
            return_details=True)
        self.assertEqual(budgeted.tobytes(), plain.tobytes())
        self.assertEqual(details["byte_budget"], 10 ** 9)
        self.assertEqual(details["byte_budget_dropped_tiles"], 0)
        # Con el costo "celdas cambiadas", el delta ES changed_cells.
        self.assertEqual(details["byte_budget_delta_bytes"],
                         int(details["changed_cells"]))
        self.assertEqual(details["byte_budget_evaluations"], 2)

    def test_zero_budget_reverts_to_baseline(self):
        result, details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            byte_cost=self.cost, max_extra_bytes=0, return_details=True)
        self.assertTrue(np.array_equal(result, self.baseline))
        self.assertEqual(int(details["changed_cells"]), 0)
        self.assertEqual(details["byte_budget_delta_bytes"], 0)
        self.assertGreater(details["byte_budget_dropped_tiles"], 0)

    def test_partial_budget_trims_prefix_and_respects_limit(self):
        _, plain_details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            return_details=True)
        full_delta = int(plain_details["changed_cells"])
        self.assertGreater(full_delta, 1)
        budget = full_delta // 2
        result, details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            byte_cost=self.cost, max_extra_bytes=budget, return_details=True)
        delta = int(details["byte_budget_delta_bytes"])
        self.assertLessEqual(delta, budget)
        self.assertEqual(delta, self.cost(result))
        self.assertEqual(delta, int(details["changed_cells"]))
        self.assertGreater(details["byte_budget_dropped_tiles"], 0)
        # Determinismo: la misma llamada produce los mismos bytes.
        again, _ = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_fraction=1.0,
            byte_cost=self.cost, max_extra_bytes=budget, return_details=True)
        self.assertEqual(result.tobytes(), again.tobytes())

    def test_cell_budget_still_applies_with_generous_byte_budget(self):
        # E-17: los dos presupuestos rigen JUNTOS; el de bytes no reemplaza
        # al de celdas. Un tope de celdas menor al tile mas chico sigue
        # dejando el frame en baseline aunque los bytes sobren.
        result, details = dither.apply_calibrated_dither(
            self.rgb, self.baseline, PALETTE, max_changed_cells=10,
            max_changed_fraction=1.0, byte_cost=self.cost,
            max_extra_bytes=10 ** 9, return_details=True)
        self.assertGreater(details["smallest_selectable_tile"], 10)
        self.assertTrue(np.array_equal(result, self.baseline))
        self.assertEqual(int(details["changed_cells"]), 0)

    def test_byte_budget_arguments_are_validated(self):
        with self.assertRaisesRegex(ValueError, "van juntos"):
            dither.apply_calibrated_dither(
                self.rgb, self.baseline, PALETTE, byte_cost=self.cost)
        with self.assertRaisesRegex(ValueError, "van juntos"):
            dither.apply_calibrated_dither(
                self.rgb, self.baseline, PALETTE, max_extra_bytes=16)
        with self.assertRaisesRegex(ValueError, ">= 0"):
            dither.apply_calibrated_dither(
                self.rgb, self.baseline, PALETTE,
                byte_cost=self.cost, max_extra_bytes=-1)


class ByteBudgetEncoderTest(unittest.TestCase):
    def test_validate_requires_dither_and_nonnegative_budget(self):
        base = dict(
            mode_name="pixel", cols=8, rows=8, fps=15, pal_size=8,
            char_aspect=0.5, palette_mode="adaptive",
            bake_smoothing="none", reconstruction="nearest")
        encoder.validate_encode_options(
            **dict(base, dither_mode="auto", dither_byte_budget=0))
        with self.assertRaisesRegex(ValueError, "E-17"):
            encoder.validate_encode_options(**dict(base, dither_byte_budget=64))
        with self.assertRaisesRegex(ValueError, ">= 0"):
            encoder.validate_encode_options(
                **dict(base, dither_mode="auto", dither_byte_budget=-1))

    def test_selective_mode_is_all_or_nothing(self):
        rgb = gray_gradient()
        baseline = nearest_indices(rgb, PALETTE)
        cells = baseline.reshape(-1, 1)
        cost = cost_by_changes(baseline)
        plain, plain_details = encoder.apply_dither_mode(
            rgb, cells, PALETTE, "selective", 4)
        self.assertIsNone(plain_details)
        changed = int(np.count_nonzero(plain[:, 0] != baseline.reshape(-1)))
        self.assertGreater(changed, 0)

        def flat_cost(index_map):
            return cost(np.asarray(index_map).reshape(baseline.shape))

        kept, kept_details = encoder.apply_dither_mode(
            rgb, cells, PALETTE, "selective", 4,
            dither_byte_budget=changed, byte_cost=flat_cost)
        self.assertEqual(kept.tobytes(), plain.tobytes())
        self.assertFalse(kept_details["byte_budget_rejected"])
        self.assertEqual(kept_details["byte_budget_delta_bytes"], changed)

        rejected, rejected_details = encoder.apply_dither_mode(
            rgb, cells, PALETTE, "selective", 4,
            dither_byte_budget=changed - 1, byte_cost=flat_cost)
        self.assertTrue(np.array_equal(rejected[:, 0], baseline.reshape(-1)))
        self.assertTrue(rejected_details["byte_budget_rejected"])
        self.assertEqual(rejected_details["byte_budget_delta_bytes"], 0)

    def test_encode_frame_fast_deflate_measures_with_pure_zlib(self):
        # E-17: la medicion del presupuesto usa zlib-9 puro, determinista
        # con o sin Zopfli instalado; la emision real conserva best_deflate.
        rgb = gray_gradient()
        cells = nearest_indices(rgb, PALETTE).reshape(-1, 1)
        tag, payload = encoder.encode_frame(
            cells, None, encoder.MODE_PIXEL, 0, True, "zlib", False,
            fast_deflate=True)
        self.assertEqual(tag, encoder.TAG_ZLIB)
        planes = encoder.cells_to_planes_bytes(cells, encoder.MODE_PIXEL)
        self.assertEqual(payload, zlib.compress(planes, 9))
        self.assertEqual(zlib.decompress(payload), planes)
        if not deflate_util.have_zopfli():
            normal_tag, normal_payload = encoder.encode_frame(
                cells, None, encoder.MODE_PIXEL, 0, True, "zlib", False)
            self.assertEqual((tag, payload), (normal_tag, normal_payload))


if __name__ == "__main__":
    unittest.main()
