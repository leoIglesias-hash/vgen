import os
import sys
import unittest
from unittest import mock

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import perceptual_palette as perceptual  # noqa: E402


def rgb_kmeans_reference(rgb, count, iterations=40):
    """Misma inicializacion determinista, pero optimizando distancia RGB."""
    samples = rgb.reshape(-1, 3).astype(np.float64) / 255.0
    weights = np.ones(len(samples), dtype=np.float64)
    centers = perceptual._initial_centers(samples, weights, count, 4096)
    for _ in range(iterations):
        labels = perceptual._nearest_indices(samples, centers, 4096)
        updated = centers.copy()
        counts = np.bincount(labels, minlength=count)
        for channel in range(3):
            sums = np.bincount(labels, weights=samples[:, channel], minlength=count)
            occupied = counts > 0
            updated[occupied, channel] = sums[occupied] / counts[occupied]
        if np.max(np.abs(updated - centers)) <= 1e-7:
            centers = updated
            break
        centers = updated
    return np.clip(np.rint(centers * 255), 0, 255).astype(np.uint8)


def perceptual_mse(rgb, palette):
    quantizer = perceptual.PerceptualQuantizer(palette, lut_bits=None)
    indices = quantizer.quantize(rgb)
    source = perceptual.srgb_to_oklab(rgb)
    reconstructed = perceptual.srgb_to_oklab(palette[indices])
    return float(np.mean(np.sum((source - reconstructed) ** 2, axis=2)))


class PerceptualPaletteTest(unittest.TestCase):
    def test_oklab_known_primaries_and_uint8_roundtrip(self):
        rgb = np.asarray(((255, 0, 0), (0, 255, 0), (0, 0, 255),
                          (128, 128, 128)), dtype=np.uint8)
        expected = np.asarray((
            (0.62795536, 0.22486306, 0.12584630),
            (0.86643961, -0.23388757, 0.17949848),
            (0.45201372, -0.03245698, -0.31152815),
        ))
        lab = perceptual.srgb_to_oklab(rgb)
        np.testing.assert_allclose(lab[:3], expected, atol=1e-7)
        reconstructed = perceptual.oklab_to_srgb(lab)
        np.testing.assert_array_equal(reconstructed, rgb)

    def test_smooth_gradient_sampling_is_numeric_and_ignores_hard_edge(self):
        flat = np.full((32, 96, 3), 96, dtype=np.uint8)
        ramp_values = np.linspace(64, 176, 96, dtype=np.uint8)
        ramp = np.repeat(ramp_values[None, :, None], 32, axis=0)
        ramp = np.repeat(ramp, 3, axis=2)
        edge = np.zeros((32, 96, 3), dtype=np.uint8)
        edge[:, :48] = 64
        edge[:, 48:] = 176
        flat_weight = perceptual.smooth_gradient_weights(flat)
        ramp_weight = perceptual.smooth_gradient_weights(ramp)
        edge_weight = perceptual.smooth_gradient_weights(edge)
        np.testing.assert_array_equal(flat_weight, np.ones((32, 96)))
        self.assertGreater(float(ramp_weight.mean()), 1.25)
        self.assertGreater(float(ramp_weight.mean()), float(edge_weight.mean()) + 0.15)

    def test_palette_is_byte_deterministic_with_weighted_subsampling(self):
        rng = np.random.default_rng(20260812)
        images = [rng.integers(0, 256, size=(31, 47, 3), dtype=np.uint8)
                  for _ in range(3)]
        first, first_info = perceptual.build_perceptual_palette(
            images, 16, max_samples=777, gradient_boost=3.5, return_info=True)
        second, second_info = perceptual.build_perceptual_palette(
            images, 16, max_samples=777, gradient_boost=3.5, return_info=True)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first_info, second_info)
        self.assertEqual(first.shape, (16, 3))
        self.assertEqual(first.dtype, np.uint8)
        self.assertEqual(first_info["sample_count"], 777)
        self.assertEqual(first_info["palette_unique_count"], 16)
        self.assertEqual(len(np.unique(perceptual._packed_rgb(first))), 16)

    def test_weighted_sampling_deduplicates_and_preserves_palette_coverage(self):
        source = np.zeros((80, 128, 3), dtype=np.uint8)
        colors = np.linspace(0, 255, 128, dtype=np.uint8)
        source[-2:, :, 0] = colors
        source[-2:, :, 1] = colors[::-1]
        source[-2:, :, 2] = (colors.astype(np.uint16) * 37 % 256).astype(np.uint8)
        samples, weights, info = perceptual._weighted_samples(
            [source], max_samples=64, gradient_boost=3.0, min_unique=16)
        sampled_rgb = perceptual.oklab_to_srgb(samples)
        self.assertEqual(info["sample_draw_count"], 64)
        self.assertGreaterEqual(info["unique_sample_count"], 16)
        self.assertLessEqual(info["unique_sample_count"], 64)
        self.assertEqual(len(np.unique(perceptual._packed_rgb(sampled_rgb))),
                         len(sampled_rgb))
        self.assertTrue(np.all(weights > 0.0))
        expected_mass = float(perceptual.smooth_gradient_weights(source).sum())
        self.assertAlmostEqual(float(weights.sum()), expected_mass, places=8)

    def test_max_samples_cannot_be_smaller_than_requested_palette(self):
        source = np.zeros((8, 8, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "max_samples"):
            perceptual.build_perceptual_palette(
                [source], pal_size=32, max_samples=16)

    def test_inputs_are_validated_instead_of_wrapping_to_uint8(self):
        invalid = np.full((4, 4, 3), 300, dtype=np.int16)
        with self.assertRaisesRegex(ValueError, "0 y 255"):
            perceptual.build_perceptual_palette([invalid], 2)
        with self.assertRaisesRegex(ValueError, "0 y 255"):
            perceptual.PerceptualQuantizer(
                np.asarray(((0, 0, 0), (300, 0, 0)), dtype=np.int16))

        normalized = np.zeros((4, 4, 3), dtype=np.float64)
        normalized[:, :2] = (1.0, 0.0, 0.0)
        normalized[:, 2:] = (0.0, 0.0, 1.0)
        palette = perceptual.build_perceptual_palette(
            [normalized], 2, max_samples=8)
        self.assertEqual(set(perceptual._packed_rgb(palette).tolist()),
                         {0xFF0000, 0x0000FF})

    def test_temporal_strength_reduces_palette_drift(self):
        height, width = 40, 128
        ramp = np.linspace(0, 1, width, dtype=np.float64)[None, :, None]
        start = np.asarray((18, 55, 155), dtype=np.float64)
        end = np.asarray((245, 195, 30), dtype=np.float64)
        first_image = np.repeat(start + (end - start) * ramp, height, axis=0)
        first_image = np.clip(np.rint(first_image), 0, 255).astype(np.uint8)
        second_image = np.clip(first_image.astype(np.int16) + (4, -2, 5), 0, 255).astype(np.uint8)
        previous = perceptual.build_perceptual_palette([first_image], 12)
        free = perceptual.build_perceptual_palette([second_image], 12)
        stable = perceptual.build_perceptual_palette(
            [second_image], 12, previous_palette=previous, temporal_strength=0.65)
        previous_lab = perceptual.srgb_to_oklab(previous)
        free_lab = perceptual.srgb_to_oklab(free)
        stable_lab = perceptual.srgb_to_oklab(stable)
        free_nearest = np.min(np.sum(
            (previous_lab[:, None] - free_lab[None, :]) ** 2, axis=2), axis=1)
        stable_ordered = np.sum((previous_lab - stable_lab) ** 2, axis=1)
        self.assertLess(float(stable_ordered.mean()), float(free_nearest.mean()))

    def test_duplicate_temporal_palette_is_reseeded_after_rgb_rounding(self):
        red = np.linspace(0, 255, 96, dtype=np.uint8)
        green = np.linspace(255, 0, 96, dtype=np.uint8)
        source = np.stack((red, green, np.full(96, 91, dtype=np.uint8)), axis=1)
        source = np.repeat(source[None, :, :], 24, axis=0)
        duplicate_previous = np.full((8, 3), 128, dtype=np.uint8)
        palette, info = perceptual.build_perceptual_palette(
            [source], 8, previous_palette=duplicate_previous,
            temporal_strength=1.0, max_samples=512, return_info=True)
        repeated = perceptual.build_perceptual_palette(
            [source], 8, previous_palette=duplicate_previous,
            temporal_strength=1.0, max_samples=512)
        np.testing.assert_array_equal(palette, repeated)
        self.assertEqual(len(np.unique(perceptual._packed_rgb(palette))), 8)
        self.assertEqual(info["palette_unique_count"], 8)
        self.assertEqual(info["repaired_duplicates"], 7)

    def test_uniform_source_does_not_invent_unseen_palette_colors(self):
        source = np.full((19, 23, 3), (17, 81, 203), dtype=np.uint8)
        palette, info = perceptual.build_perceptual_palette(
            [source], 16, max_samples=256, return_info=True)
        np.testing.assert_array_equal(
            palette, np.repeat(source[0, 0][None, :], 16, axis=0))
        self.assertEqual(info["palette_unique_count"], 1)
        self.assertEqual(info["repaired_duplicates"], 0)

    def test_gamut_mapping_preserves_lightness_and_hue_direction(self):
        outside = np.asarray(((0.68, 0.52, 0.31),
                              (0.55, -0.43, 0.38)), dtype=np.float64)
        self.assertTrue(np.any((perceptual._oklab_to_linear_srgb(outside) < 0.0) |
                               (perceptual._oklab_to_linear_srgb(outside) > 1.0)))
        mapped = perceptual.gamut_map_oklab(outside)
        linear = perceptual._oklab_to_linear_srgb(mapped)
        self.assertTrue(np.all(linear >= -1e-9))
        self.assertTrue(np.all(linear <= 1.0 + 1e-9))
        np.testing.assert_allclose(mapped[:, 0], outside[:, 0], atol=0.0)
        original_chroma = np.sqrt(np.sum(outside[:, 1:] ** 2, axis=1))
        mapped_chroma = np.sqrt(np.sum(mapped[:, 1:] ** 2, axis=1))
        self.assertTrue(np.all(mapped_chroma < original_chroma))
        np.testing.assert_allclose(
            mapped[:, 1] * outside[:, 2],
            mapped[:, 2] * outside[:, 1], atol=1e-12)

    def test_exact_and_lut_quantizers_have_bounded_indices(self):
        rng = np.random.default_rng(77)
        source = rng.integers(0, 256, size=(43, 59, 3), dtype=np.uint8)
        palette = perceptual.build_perceptual_palette([source], 9, max_samples=1200)
        exact = perceptual.PerceptualQuantizer(palette, lut_bits=None).quantize(source)
        fast_quantizer = perceptual.PerceptualQuantizer(palette, lut_bits=5)
        fast = fast_quantizer.quantize(source)
        self.assertEqual(exact.shape, source.shape[:2])
        self.assertEqual(fast.shape, source.shape[:2])
        self.assertEqual(exact.dtype, np.uint8)
        self.assertEqual(fast.dtype, np.uint8)
        self.assertLess(int(exact.max()), len(palette))
        self.assertLess(int(fast.max()), len(palette))
        self.assertEqual(fast_quantizer.lut.nbytes, 32 ** 3)
        source_lab = perceptual.srgb_to_oklab(source)
        exact_error = np.mean(np.sum(
            (source_lab - perceptual.srgb_to_oklab(palette[exact])) ** 2, axis=2))
        fast_error = np.mean(np.sum(
            (source_lab - perceptual.srgb_to_oklab(palette[fast])) ** 2, axis=2))
        self.assertLessEqual(float(exact_error), float(fast_error) + 1e-15)

    def test_exact_quantizer_converts_and_compares_only_one_chunk_at_a_time(self):
        rng = np.random.default_rng(991)
        source = rng.integers(0, 256, size=(37, 53, 3), dtype=np.uint8)
        palette = rng.integers(0, 256, size=(13, 3), dtype=np.uint8)
        quantizer = perceptual.PerceptualQuantizer(
            palette, lut_bits=None, chunk_size=127)
        original_conversion = perceptual.srgb_to_oklab
        conversion_sizes = []

        def measured_conversion(values):
            conversion_sizes.append(np.asarray(values).reshape(-1, 3).shape[0])
            return original_conversion(values)

        with mock.patch.object(perceptual, "srgb_to_oklab",
                               side_effect=measured_conversion):
            actual = quantizer.quantize(source)
        self.assertTrue(conversion_sizes)
        self.assertLessEqual(max(conversion_sizes), 127)

        source_lab = original_conversion(source)
        palette_lab = original_conversion(palette)
        brute_distance = np.sum(
            (source_lab[:, :, None, :] - palette_lab[None, None, :, :]) ** 2,
            axis=3)
        expected = np.argmin(brute_distance, axis=2).astype(np.uint8)
        np.testing.assert_array_equal(actual, expected)

    def test_lut_builder_does_not_materialize_meshgrids(self):
        palette = np.asarray(((0, 0, 0), (255, 255, 255)), dtype=np.uint8)
        with mock.patch.object(np, "meshgrid", side_effect=AssertionError("meshgrid")):
            lut = perceptual.build_perceptual_lut(palette, bits=3, chunk_size=37)
        self.assertEqual(lut.shape, (8 ** 3,))

    def test_six_bit_lut_does_not_overflow_rgb_key(self):
        palette = np.asarray(((0, 0, 0), (255, 0, 0), (0, 255, 0),
                              (0, 0, 255), (255, 255, 255)), dtype=np.uint8)
        source = palette.reshape(1, 5, 3)
        quantizer = perceptual.PerceptualQuantizer(palette, lut_bits=6)
        indices = quantizer.quantize(source)
        np.testing.assert_array_equal(indices, np.arange(5, dtype=np.uint8)[None, :])
        self.assertEqual(quantizer.lut.nbytes, 64 ** 3)

    def test_six_bit_lut_has_small_measured_penalty_against_exact(self):
        rng = np.random.default_rng(8821)
        source = rng.integers(0, 256, size=(64, 96, 3), dtype=np.uint8)
        palette = perceptual.build_perceptual_palette(
            [source], 64, max_samples=4096)
        exact = perceptual.PerceptualQuantizer(
            palette, lut_bits=None).quantize(source)
        lut6 = perceptual.PerceptualQuantizer(
            palette, lut_bits=6).quantize(source)
        source_lab = perceptual.srgb_to_oklab(source)
        exact_error = np.mean(np.sum(
            (source_lab - perceptual.srgb_to_oklab(palette[exact])) ** 2, axis=2))
        lut_error = np.mean(np.sum(
            (source_lab - perceptual.srgb_to_oklab(palette[lut6])) ** 2, axis=2))
        self.assertLess(float(lut_error), float(exact_error) * 1.03)

    def test_oklab_kmeans_reduces_perceptual_error_against_rgb_kmeans(self):
        # Cubo de colores con mas densidad en sombras, donde una distancia numerica
        # RGB asigna demasiada capacidad a cambios que el ojo percibe poco.
        levels = np.asarray((0, 20, 42, 70, 105, 150, 205, 255), dtype=np.uint8)
        red, green, blue = np.meshgrid(levels, levels, levels, indexing="ij")
        source = np.stack((red, green, blue), axis=-1).reshape(32, 16, 3)
        perceptual_palette = perceptual.build_perceptual_palette(
            [source], 16, gradient_boost=0.0)
        rgb_palette = rgb_kmeans_reference(source, 16)
        perceptual_error = perceptual_mse(source, perceptual_palette)
        rgb_error = perceptual_mse(source, rgb_palette)
        self.assertLess(perceptual_error, rgb_error * 0.92)


if __name__ == "__main__":
    unittest.main()
