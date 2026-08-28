# -*- coding: utf-8 -*-
"""E-13: cierre de Lloyd en dominio uint8 (perceptual_palette)."""
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import encoder  # noqa: E402
import overlay_palette  # noqa: E402
import perceptual_palette as perceptual  # noqa: E402


def noisy_source(seed, shape=(31, 47, 3)):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=shape, dtype=np.uint8)


def gradient_source():
    width = 128
    ramp = np.linspace(0, 1, width, dtype=np.float64)[None, :, None]
    start = np.asarray((12, 40, 160), dtype=np.float64)
    end = np.asarray((250, 200, 40), dtype=np.float64)
    image = np.repeat(start + (end - start) * ramp, 40, axis=0)
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


class Uint8RefineTest(unittest.TestCase):
    def test_zero_iterations_is_identity(self):
        source = noisy_source(11)
        baseline, base_info = perceptual.build_perceptual_palette(
            [source], 16, max_samples=777, return_info=True)
        explicit, info = perceptual.build_perceptual_palette(
            [source], 16, max_samples=777, return_info=True, uint8_refine=0)
        self.assertEqual(explicit.tobytes(), baseline.tobytes())
        self.assertEqual(info["uint8_refine_accepted"], 0)
        self.assertEqual(base_info["uint8_refine_accepted"], 0)

    def test_out_of_range_is_rejected(self):
        source = noisy_source(12)
        for bad in (-1, 11):
            with self.assertRaisesRegex(ValueError, "uint8_refine"):
                perceptual.build_perceptual_palette(
                    [source], 8, max_samples=256, uint8_refine=bad)
            with self.assertRaisesRegex(ValueError, "palette-uint8-refine"):
                encoder.validate_encode_options(
                    "pixel", 32, 0, 15, 256, 0.5, "global", "none", "nearest",
                    palette_algorithm="kmeans-oklab", palette_uint8_refine=bad)

    def test_only_kmeans_oklab_accepts_the_refine(self):
        with self.assertRaisesRegex(ValueError, "kmeans-oklab"):
            encoder.validate_encode_options(
                "pixel", 32, 0, 15, 256, 0.5, "global", "none", "nearest",
                palette_algorithm="median-cut", palette_uint8_refine=2)
        with self.assertRaisesRegex(ValueError, "kmeans-oklab"):
            encoder.make_global_palette(
                [noisy_source(13)], 8, "kmeans-rgb", uint8_refine=2)
        encoder.validate_encode_options(
            "pixel", 32, 0, 15, 256, 0.5, "global", "none", "nearest",
            palette_algorithm="median-cut", palette_uint8_refine=0)

    def test_inertia_never_increases_and_is_deterministic(self):
        for source in (noisy_source(21), noisy_source(22, (24, 64, 3)),
                       gradient_source()):
            baseline, base_info = perceptual.build_perceptual_palette(
                [source], 16, max_samples=900, return_info=True)
            refined, info = perceptual.build_perceptual_palette(
                [source], 16, max_samples=900, return_info=True,
                uint8_refine=4)
            repeated, repeated_info = perceptual.build_perceptual_palette(
                [source], 16, max_samples=900, return_info=True,
                uint8_refine=4)
            self.assertLessEqual(info["weighted_inertia"],
                                 base_info["weighted_inertia"] + 1e-12)
            self.assertEqual(refined.tobytes(), repeated.tobytes())
            self.assertEqual(info, repeated_info)
            self.assertEqual(info["palette_unique_count"],
                             base_info["palette_unique_count"])

    def test_refine_improves_at_least_one_reference(self):
        improved = 0
        for source in (noisy_source(31), noisy_source(32), gradient_source()):
            _, base_info = perceptual.build_perceptual_palette(
                [source], 12, max_samples=700, return_info=True)
            _, info = perceptual.build_perceptual_palette(
                [source], 12, max_samples=700, return_info=True,
                uint8_refine=5)
            if (info["uint8_refine_accepted"] > 0 and
                    info["weighted_inertia"] < base_info["weighted_inertia"]):
                improved += 1
        self.assertGreater(improved, 0)

    def test_uniform_source_is_untouched(self):
        source = np.full((19, 23, 3), (17, 81, 203), dtype=np.uint8)
        baseline = perceptual.build_perceptual_palette(
            [source], 16, max_samples=256)
        refined, info = perceptual.build_perceptual_palette(
            [source], 16, max_samples=256, return_info=True, uint8_refine=4)
        self.assertEqual(refined.tobytes(), baseline.tobytes())
        self.assertEqual(info["uint8_refine_accepted"], 0)

    def test_temporal_path_stays_deterministic_and_unique(self):
        first = gradient_source()
        second = np.clip(first.astype(np.int16) + (4, -2, 5),
                         0, 255).astype(np.uint8)
        previous = perceptual.build_perceptual_palette([first], 12)
        stable_a = perceptual.build_perceptual_palette(
            [second], 12, previous_palette=previous, temporal_strength=0.4,
            uint8_refine=3)
        stable_b = perceptual.build_perceptual_palette(
            [second], 12, previous_palette=previous, temporal_strength=0.4,
            uint8_refine=3)
        self.assertEqual(stable_a.tobytes(), stable_b.tobytes())
        self.assertEqual(stable_a.shape, (12, 3))
        self.assertEqual(len(np.unique(perceptual._packed_rgb(stable_a))), 12)

    def test_reserved_rows_stay_byte_identical(self):
        table = overlay_palette.reserved_table(10)
        source = noisy_source(41, (36, 36, 3))
        _, palette = encoder.make_global_palette(
            [source], 64, "kmeans-oklab", reserved=10, reserved_colors=table,
            uint8_refine=3)
        self.assertEqual(palette.shape, (64, 3))
        self.assertEqual(palette[-10:].tobytes(), table.tobytes())

    def test_quantize_per_frame_threads_the_refine(self):
        source = noisy_source(51, (32, 48, 3))
        idx, pal = encoder.quantize_per_frame(
            source, 32, "kmeans-oklab", palette_uint8_refine=3)
        self.assertEqual(pal.shape, (32, 3))
        self.assertLess(int(idx.max()), len(pal))

    def test_encode_image_reports_the_refine(self):
        source = noisy_source(61, (24, 32, 3))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "in.png")
            Image.fromarray(source, "RGB").save(path)
            out = os.path.join(directory, "out.ascl")
            info = encoder.encode_image(
                path, out, "pixel", 32, 0, 15, 32, "short", 0.5, "auto",
                "per-frame", palette_algorithm="kmeans-oklab",
                palette_uint8_refine=2)
            self.assertEqual(info["palette_uint8_refine"], 2)
            self.assertGreater(os.path.getsize(out), 0)


if __name__ == "__main__":
    unittest.main()
