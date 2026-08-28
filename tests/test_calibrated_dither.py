import os
import sys
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import dither  # noqa: E402
import perceptual_palette as perceptual  # noqa: E402


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


class CalibratedDitherTest(unittest.TestCase):
    def test_exact_proxy_sum_does_not_overflow_int64_total(self):
        values = np.asarray([2 ** 62, 2 ** 62, 17], dtype=np.int64)
        self.assertEqual(dither._exact_nonnegative_sum(values), 2 ** 63 + 17)

    def test_pair_lut_accepts_same_perceptual_quantizer_as_baseline(self):
        palette = np.asarray(
            ((75, 55, 119), (39, 155, 150), (59, 114, 134),
             (229, 115, 189), (253, 76, 150), (223, 241, 156)),
            dtype=np.uint8)
        start = np.asarray((130, 3, 195), dtype=np.float64)
        stop = np.asarray((76, 176, 22), dtype=np.float64)
        alpha = np.linspace(0.0, 1.0, 128)[None, :, None]
        row = start * (1.0 - alpha) + stop * alpha
        rgb = np.tile(row, (32, 1, 1)).astype(np.uint8)
        quantizer = perceptual.PerceptualQuantizer(palette, lut_bits=5)
        baseline = quantizer.quantize(rgb)

        rgb_lut = dither.PairLUT(palette)
        calls = []

        def quantize_once(colors):
            calls.append(colors.shape)
            return quantizer.quantize(colors)

        perceptual_lut = dither.PairLUT(
            palette, base_quantizer=quantize_once)
        keys = dither.rgb555_keys(rgb)
        rgb_match = float(np.mean(rgb_lut.base[keys] == baseline))
        perceptual_match = float(np.mean(
            perceptual_lut.base[keys] == baseline))
        legacy = dither.apply_selective_dither(
            rgb, baseline, palette, pair_lut=rgb_lut,
            min_gradient_range=4)
        compatible = dither.apply_selective_dither(
            rgb, baseline, palette, pair_lut=perceptual_lut,
            min_gradient_range=4)
        direct_callback = dither.apply_selective_dither(
            rgb, baseline, palette, base_quantizer=quantizer,
            min_gradient_range=4)
        calibrated, calibrated_details = dither.apply_calibrated_dither(
            rgb, baseline, palette, pair_lut=perceptual_lut,
            max_changed_fraction=1.0, return_details=True)

        self.assertLess(rgb_match, 0.70)
        self.assertEqual(perceptual_match, 1.0)
        self.assertEqual(calls, [(32768, 3)])
        # E-16: la mezcla se calcula exacta por pixel desde la base real
        # (baseline); la base 555 de la LUT ya no gatea el tramado, asi que
        # ambas LUT producen el MISMO resultado y ningun pixel elegible se
        # apaga en silencio por discrepancia 555 vs cuantizador.
        self.assertEqual(compatible.tobytes(), legacy.tobytes())
        self.assertGreater(np.count_nonzero(compatible != baseline), 0)
        self.assertEqual(compatible.tobytes(), direct_callback.tobytes())
        self.assertTrue(np.any(calibrated != baseline))
        self.assertLess(calibrated_details["result_proxy_error"],
                        calibrated_details["baseline_proxy_error"])
        self.assertTrue(np.array_equal(
            dither.PairLUT(palette, base_quantizer=quantizer).base,
            perceptual_lut.base))

    def test_pair_lut_rejects_invalid_quantizer_output(self):
        with self.assertRaisesRegex(ValueError, "un indice por color"):
            dither.PairLUT(PALETTE, base_quantizer=lambda colors: [0])
        with self.assertRaisesRegex(ValueError, "fuera de palette"):
            dither.PairLUT(
                PALETTE,
                base_quantizer=lambda colors: np.full(len(colors), 9))

    def test_temporal_history_is_packed_and_bounded(self):
        shape = (23, 40)  # grilla de tiles de un cuadro 640x360 con tiles 16
        state = dither.TemporalDitherState(window=10)
        for frame in range(15):
            qualified = ((np.indices(shape).sum(axis=0) + frame) % 3) == 0
            state.update(qualified)

        unpacked_boolean_history = 10 * shape[0] * shape[1]
        self.assertLess(state.nbytes, unpacked_boolean_history // 2)
        self.assertEqual(state._packed_history.shape,
                         (10, (shape[0] * shape[1] + 7) // 8))

    def test_whole_tile_budget_reports_unused_capacity(self):
        rgb = gray_gradient()
        baseline = nearest_indices(rgb, PALETTE)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, max_changed_cells=10,
            max_changed_fraction=1.0, return_details=True)

        self.assertGreater(details["smallest_selectable_tile"], 10)
        self.assertEqual(details["changed_cells"], 0)
        self.assertEqual(details["unused_change_budget"], 10)
        self.assertGreater(details["budget_limited_tiles"], 0)
        self.assertTrue(np.array_equal(result, baseline))

    def test_temporal_state_resets_on_palette_change_and_explicit_cut(self):
        rgb = gray_gradient()
        first_palette = PALETTE
        second_palette = np.asarray(
            ((0, 0, 0), (80, 80, 80), (175, 175, 175),
             (255, 255, 255)), dtype=np.uint8)
        first_baseline = nearest_indices(rgb, first_palette)
        second_baseline = nearest_indices(rgb, second_palette)
        state = dither.TemporalDitherState(
            window=2, activation=1.0, deactivation=0.5)
        options = dict(max_changed_fraction=1.0, temporal_state=state,
                       return_details=True)

        initial, _ = dither.apply_calibrated_dither(
            rgb, first_baseline, first_palette, **options)
        active, active_details = dither.apply_calibrated_dither(
            rgb, first_baseline, first_palette, **options)
        after_palette, palette_details = dither.apply_calibrated_dither(
            rgb, second_baseline, second_palette, **options)
        after_cut, cut_details = dither.apply_calibrated_dither(
            rgb, second_baseline, second_palette, reset_temporal=True,
            **options)

        self.assertTrue(np.array_equal(initial, first_baseline))
        self.assertTrue(np.any(active != first_baseline))
        self.assertFalse(active_details["temporal_reset"])
        self.assertTrue(palette_details["temporal_reset"])
        self.assertTrue(np.array_equal(after_palette, second_baseline))
        self.assertTrue(cut_details["temporal_reset"])
        self.assertTrue(np.array_equal(after_cut, second_baseline))

    def test_temporal_state_can_cross_short_palette_blocks(self):
        rgb = gray_gradient()
        second_palette = np.asarray(
            ((0, 0, 0), (80, 80, 80), (175, 175, 175),
             (255, 255, 255)), dtype=np.uint8)
        first_baseline = nearest_indices(rgb, PALETTE)
        second_baseline = nearest_indices(rgb, second_palette)
        state = dither.TemporalDitherState(
            window=2, activation=1.0, deactivation=0.5)
        options = dict(max_changed_fraction=1.0, temporal_state=state,
                       temporal_context="same-clip",
                       reset_on_palette_change=False, return_details=True)

        dither.apply_calibrated_dither(
            rgb, first_baseline, PALETTE, **options)
        active, _ = dither.apply_calibrated_dither(
            rgb, first_baseline, PALETTE, **options)
        next_block, details = dither.apply_calibrated_dither(
            rgb, second_baseline, second_palette, **options)

        self.assertTrue(np.any(active != first_baseline))
        self.assertFalse(details["temporal_reset"])
        self.assertTrue(np.any(next_block != second_baseline))

    def test_changed_cell_budget_is_exact_upper_bound(self):
        rgb = gray_gradient()
        baseline = nearest_indices(rgb, PALETTE)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, max_changed_cells=100,
            max_changed_fraction=1.0, return_details=True)

        changed = int(np.count_nonzero(result != baseline))
        self.assertGreater(changed, 0)
        self.assertLessEqual(changed, 100)
        self.assertEqual(changed, details["changed_cells"])
        self.assertEqual(details["change_budget"], 100)
        self.assertLess(details["result_proxy_error"],
                        details["baseline_proxy_error"])

    def test_calibrated_mode_never_changes_protected_edges(self):
        rgb = gray_gradient(32, 64)
        rgb[8:24, 30:34] = 255
        baseline = nearest_indices(rgb, PALETTE)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, max_changed_fraction=1.0,
            return_details=True)

        self.assertTrue(np.any(details["protected"]))
        self.assertTrue(np.array_equal(result[details["protected"]],
                                       baseline[details["protected"]]))

    def test_calibrated_mode_is_deterministic(self):
        rgb = gray_gradient()
        baseline = nearest_indices(rgb, PALETTE)
        options = dict(max_changed_cells=400, max_changed_fraction=1.0,
                       return_details=True)
        first, first_details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, **options)
        second, second_details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, **options)

        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first_details["accepted_tiles"].tobytes(),
                         second_details["accepted_tiles"].tobytes())
        self.assertEqual(first_details["result_proxy_error"],
                         second_details["result_proxy_error"])

    def test_temporal_hysteresis_does_not_flicker_at_quality_threshold(self):
        rgb = gray_gradient()
        baseline = nearest_indices(rgb, PALETTE)
        state = dither.TemporalDitherState(
            window=4, activation=0.75, deactivation=0.25)
        base_options = dict(max_changed_fraction=1.0, temporal_state=state)

        # Tres frames aptos son necesarios para activar (75% de una ventana de 4).
        first = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, **base_options)
        second = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, **base_options)
        active = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, **base_options)
        self.assertTrue(np.array_equal(first, baseline))
        self.assertTrue(np.array_equal(second, baseline))
        self.assertTrue(np.any(active != baseline))

        # Un frame que cae bajo el umbral de aceptacion conserva exactamente el
        # mismo patron: la calidad todavia mejora, solo dejo de superar el 99%.
        borderline = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, min_proxy_improvement=0.99,
            **base_options)
        self.assertEqual(active.tobytes(), borderline.tobytes())

        # Tras evidencia sostenida por debajo del umbral inferior se desactiva.
        for _ in range(3):
            last = dither.apply_calibrated_dither(
                rgb, baseline, PALETTE, min_proxy_improvement=0.99,
                **base_options)
        self.assertTrue(np.array_equal(last, baseline))

    def test_candidate_is_rejected_when_proxy_does_not_improve(self):
        # Fuente representada exactamente: no hay banding que corregir ni error
        # perceptual que pueda reducirse.
        indices = np.tile(np.arange(4, dtype=np.uint8), (32, 32))
        rgb = PALETTE[indices]
        baseline = indices.copy()
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, max_changed_fraction=1.0,
            return_details=True)

        self.assertTrue(np.array_equal(result, baseline))
        self.assertFalse(np.any(details["accepted_tiles"]))
        self.assertEqual(details["proxy_improvement"], 0.0)

    def test_changed_candidate_tile_is_rejected_when_its_proxy_gets_worse(self):
        palette = np.asarray(
            ((21, 9, 36), (47, 70, 58), (67, 117, 192),
             (87, 140, 195), (88, 242, 211), (103, 251, 216)),
            dtype=np.uint8)
        yy, xx = np.indices((32, 32))
        origin = np.asarray((193, 230, 39), dtype=np.float64)
        slope_x = np.asarray((7, 8, 1), dtype=np.float64) / 31.0
        slope_y = np.asarray((-55, -3, -8), dtype=np.float64) / 31.0
        rgb = np.clip(origin + xx[:, :, None] * slope_x +
                      yy[:, :, None] * slope_y, 0, 255).astype(np.uint8)
        baseline = nearest_indices(rgb, palette)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, palette, min_proxy_improvement=0.0,
            max_changed_fraction=1.0, return_details=True)

        self.assertGreater(details["tile_changed_counts"][0, 0], 0)
        self.assertLessEqual(details["tile_gains"][0, 0], 0)
        self.assertFalse(details["accepted_tiles"][0, 0])
        self.assertTrue(np.array_equal(result[:16, :16], baseline[:16, :16]))

    def test_textured_tiles_are_rejected_even_with_a_dither_candidate(self):
        height, width = 32, 128
        x = np.arange(width, dtype=np.float64)[None, :]
        base = np.tile(np.linspace(30, 220, width), (height, 1))
        textured = np.clip(base + 8.0 * np.sin(2.0 * np.pi * x / 4.0),
                           0, 255).astype(np.uint8)
        rgb = np.repeat(textured[:, :, None], 3, axis=2)
        baseline = nearest_indices(rgb, PALETTE)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, max_changed_fraction=1.0,
            return_details=True)

        # La LUT/Bayer podria modificarla, pero el residuo contra box 5x5 indica
        # textura repetitiva, no un gradiente suave con banding.
        self.assertTrue(np.any(details["candidate_changed"]))
        self.assertFalse(np.any(details["smooth_qualified"]))
        self.assertTrue(np.array_equal(result, baseline))

    def test_temporal_history_never_overrides_current_texture_guard(self):
        smooth = gray_gradient()
        smooth_baseline = nearest_indices(smooth, PALETTE)
        state = dither.TemporalDitherState(
            window=2, activation=1.0, deactivation=0.5)
        options = dict(max_changed_fraction=1.0, temporal_state=state)
        for _ in range(2):
            dither.apply_calibrated_dither(
                smooth, smooth_baseline, PALETTE, **options)

        height, width = smooth.shape[:2]
        x = np.arange(width, dtype=np.float64)[None, :]
        base = np.tile(np.linspace(30, 220, width), (height, 1))
        textured = np.clip(base + 8.0 * np.sin(2.0 * np.pi * x / 4.0),
                           0, 255).astype(np.uint8)
        rgb = np.repeat(textured[:, :, None], 3, axis=2)
        baseline = nearest_indices(rgb, PALETTE)
        result, details = dither.apply_calibrated_dither(
            rgb, baseline, PALETTE, return_details=True, **options)

        self.assertTrue(np.any(details["temporal_active"]))
        self.assertFalse(np.any(details["smooth_qualified"]))
        self.assertFalse(np.any(details["accepted_tiles"]))
        self.assertTrue(np.array_equal(result, baseline))


if __name__ == "__main__":
    unittest.main()
