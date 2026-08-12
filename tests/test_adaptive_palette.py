import os
import sys
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import adaptive_palette  # noqa: E402


def solid_frame(red, green, blue, size=16):
    rgb = np.empty((size, size, 3), dtype=np.uint8)
    rgb[:] = (red, green, blue)
    gray = ((rgb[:, :, 0].astype(np.uint16) * 77 +
             rgb[:, :, 1].astype(np.uint16) * 150 +
             rgb[:, :, 2].astype(np.uint16) * 29) >> 8).astype(np.uint8)
    return rgb, gray


class AdaptivePaletteTest(unittest.TestCase):
    def test_quality_first_default_has_ten_frame_safety_cap(self):
        config = adaptive_palette.AdaptivePaletteConfig()
        self.assertEqual(config.min_frames, 5)
        self.assertEqual(config.max_frames, 10)

    def test_stable_color_makes_one_long_block(self):
        config = adaptive_palette.AdaptivePaletteConfig(min_frames=4, max_frames=30)
        frames = [solid_frame(30, 100, 180) for _ in range(24)]
        blocks = list(adaptive_palette.iter_adaptive_palette_blocks(frames, config))
        self.assertEqual([len(block) for block in blocks], [24])
        self.assertEqual(blocks[0].boundary_reason, "end-of-stream")

    def test_hard_color_change_cuts_before_exact_changed_frame(self):
        # El hard cut puede romper min_frames: retrasarlo mezclaria dos escenas.
        config = adaptive_palette.AdaptivePaletteConfig(min_frames=6, max_frames=30)
        red = [solid_frame(230, 20, 15) for _ in range(4)]
        blue = [solid_frame(10, 30, 240) for _ in range(5)]
        blocks = list(adaptive_palette.iter_adaptive_palette_blocks(red + blue, config))
        self.assertEqual([(b.start_index, b.end_index) for b in blocks],
                         [(0, 4), (4, 9)])
        self.assertEqual(blocks[0].boundary_reason, "hard-cut")
        self.assertGreaterEqual(blocks[0].boundary_score,
                                config.hard_cut_threshold)
        self.assertIs(blocks[1].frames[0], blue[0])

    def test_gradual_color_drift_shortens_block_without_ai_or_hard_cut(self):
        config = adaptive_palette.AdaptivePaletteConfig(
            min_frames=4, max_frames=40, change_threshold=0.16,
            hard_cut_threshold=0.75)
        frames = [solid_frame(20 + step * 5, 70 + step * 3, 150 - step * 2)
                  for step in range(30)]
        blocks = list(adaptive_palette.iter_adaptive_palette_blocks(frames, config))
        self.assertGreater(len(blocks), 1)
        self.assertLess(len(blocks[0]), config.max_frames)
        self.assertIn("color-drift", [block.boundary_reason for block in blocks])
        self.assertNotIn("hard-cut", [block.boundary_reason for block in blocks])

    def test_results_are_deterministic(self):
        config = adaptive_palette.AdaptivePaletteConfig(
            min_frames=3, max_frames=11, change_threshold=0.18)
        frames = [solid_frame((i * 11) % 256, 80, 210 - i * 3) for i in range(22)]

        def signature():
            return [(b.start_index, b.end_index, b.boundary_reason,
                     round(b.boundary_score, 12), round(b.stability_strength, 12))
                    for b in adaptive_palette.iter_adaptive_palette_blocks(frames, config)]

        self.assertEqual(signature(), signature())

    def test_never_exceeds_max_frames(self):
        config = adaptive_palette.AdaptivePaletteConfig(min_frames=3, max_frames=7)
        frames = [solid_frame(25, 50, 75) for _ in range(23)]
        blocks = list(adaptive_palette.iter_adaptive_palette_blocks(frames, config))
        self.assertEqual([len(block) for block in blocks], [7, 7, 7, 2])
        self.assertTrue(all(len(block) <= 7 for block in blocks))
        self.assertEqual([block.boundary_reason for block in blocks[:-1]],
                         ["max-frames", "max-frames", "max-frames"])

    def test_does_not_lose_reorder_or_copy_frames(self):
        config = adaptive_palette.AdaptivePaletteConfig(min_frames=3, max_frames=8)
        frames = [solid_frame(i * 13, 30 + i, 220 - i * 4) for i in range(18)]
        blocks = list(adaptive_palette.iter_adaptive_palette_blocks(frames, config))
        flattened = [frame for block in blocks for frame in block.frames]
        self.assertEqual(len(flattened), len(frames))
        for expected, actual in zip(frames, flattened):
            self.assertIs(actual, expected)
        self.assertEqual(blocks[0].start_index, 0)
        self.assertEqual(blocks[-1].end_index, len(frames))

    def test_temporal_stability_is_monotonic_and_zero_on_hard_cut(self):
        config = adaptive_palette.AdaptivePaletteConfig()
        strengths = [adaptive_palette.temporal_stability_strength(
            value, config=config) for value in (0.0, 0.10, 0.25, 0.60)]
        self.assertGreater(strengths[0], strengths[1])
        self.assertGreater(strengths[1], strengths[2])
        self.assertEqual(strengths[-1], 0.0)
        self.assertEqual(adaptive_palette.temporal_stability_strength(
            0.0, hard_cut=True, config=config), 0.0)

    def test_color_distribution_is_invariant_to_spatial_movement(self):
        # Una permutacion extrema cambia por completo la ubicacion de los pixeles,
        # pero no los colores presentes. El histograma y la media deben ser iguales.
        rng = np.random.RandomState(123)
        rgb = rng.randint(0, 256, size=(18, 24, 3)).astype(np.uint8)
        moved = rgb.reshape(-1, 3)[rng.permutation(18 * 24)].reshape(rgb.shape)
        config = adaptive_palette.AdaptivePaletteConfig(sample_size=0)
        metrics = adaptive_palette.color_change_metrics(rgb, moved, config)
        self.assertAlmostEqual(metrics["distribution"], 0.0, places=12)
        self.assertAlmostEqual(metrics["mean"], 0.0, places=12)
        # Solo puede quedar la energia escalar de bordes, limitada al peso menor.
        self.assertLessEqual(metrics["score"], config.gradient_weight + 1e-12)


if __name__ == "__main__":
    unittest.main()
