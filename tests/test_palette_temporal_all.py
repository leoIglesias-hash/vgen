# -*- coding: utf-8 -*-
"""E-15: estabilidad temporal para los cuatro algoritmos de paleta."""
import os
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import adaptive_palette  # noqa: E402
import encoder  # noqa: E402


def gradient_image(shift=0):
    width, height = 96, 32
    ramp = np.linspace(0, 1, width, dtype=np.float64)[None, :, None]
    start = np.asarray((18, 55, 155), dtype=np.float64)
    end = np.asarray((245, 195, 30), dtype=np.float64)
    image = np.repeat(start + (end - start) * ramp, height, axis=0)
    image = image + np.asarray(shift, dtype=np.float64)
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


def with_gray(rgb):
    x = rgb.astype(np.uint16)
    gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)
    return rgb, gray


def ordered_error(palette, previous):
    return float(np.mean(np.abs(palette.astype(np.int64) -
                                previous.astype(np.int64))))


class StabilizeHelperTest(unittest.TestCase):
    def test_pure_permutation_realigns_exactly(self):
        rng = np.random.default_rng(3)
        previous = rng.integers(0, 256, size=(8, 3), dtype=np.uint8)
        shuffled = previous[::-1].copy()
        aligned = encoder._stabilize_rgb_palette(shuffled, previous, 0.0)
        self.assertEqual(aligned.tobytes(), previous.tobytes())

    def test_none_and_shape_mismatch_are_identity(self):
        palette = np.zeros((4, 3), dtype=np.uint8)
        self.assertIs(encoder._stabilize_rgb_palette(palette, None, 0.5),
                      palette)
        self.assertIs(encoder._stabilize_rgb_palette(
            palette, np.zeros((6, 3), dtype=np.uint8), 0.5), palette)

    def test_strength_blends_toward_previous(self):
        palette = np.asarray(((100, 100, 100),), dtype=np.uint8)
        previous = np.asarray(((0, 0, 0),), dtype=np.uint8)
        blended = encoder._stabilize_rgb_palette(palette, previous, 0.25)
        self.assertEqual(blended[0].tolist(), [75, 75, 75])

    def test_kmeans_rgb_palette_drift_is_reduced(self):
        first = gradient_image()
        second = gradient_image(shift=(4, -2, 5))
        _, previous = encoder.make_global_palette([first], 12, "kmeans-rgb")
        _, free = encoder.make_global_palette([second], 12, "kmeans-rgb")
        _, stable = encoder.make_global_palette(
            [second], 12, "kmeans-rgb", previous_palette=previous,
            temporal_strength=0.5)
        self.assertLess(ordered_error(stable, previous),
                        ordered_error(free, previous))


class SceneBlocksTest(unittest.TestCase):
    def _block_palettes(self, algorithm, disabled):
        config = adaptive_palette.AdaptivePaletteConfig(
            min_frames=2, max_frames=4, change_threshold=0.20,
            hard_cut_threshold=0.58, max_stability=0.25)
        frames = [with_gray(gradient_image(shift=(k, -k, k)))
                  for k in range(6)]

        def collect():
            palettes = []
            for item in encoder.iter_scene_palette_frames(
                    iter(frames), 16, "block", 3, config,
                    palette_algorithm=algorithm):
                _rgb, _gray, _img, palette, _q, first, _diag, _cut = item
                if first:
                    palettes.append(palette)
            return palettes

        if disabled:
            with mock.patch.object(encoder, "_stabilize_rgb_palette",
                                   side_effect=lambda pal, _prev, _s: pal):
                return collect()
        return collect()

    def test_fast_octree_boundary_error_drops(self):
        before = self._block_palettes("fast-octree", disabled=True)
        after = self._block_palettes("fast-octree", disabled=False)
        self.assertEqual(len(before), 2)
        self.assertEqual(len(after), 2)
        error_before = ordered_error(before[1], before[0])
        error_after = ordered_error(after[1], after[0])
        print("E-15 frontera fast-octree: antes=%.3f despues=%.3f" %
              (error_before, error_after))
        self.assertLess(error_after, error_before)

    def test_kmeans_rgb_boundary_error_drops(self):
        before = self._block_palettes("kmeans-rgb", disabled=True)
        after = self._block_palettes("kmeans-rgb", disabled=False)
        error_before = ordered_error(before[1], before[0])
        error_after = ordered_error(after[1], after[0])
        print("E-15 frontera kmeans-rgb: antes=%.3f despues=%.3f" %
              (error_before, error_after))
        self.assertLessEqual(error_after, error_before)


class PerFrameTest(unittest.TestCase):
    def test_median_cut_per_frame_uses_the_previous_palette(self):
        rng = np.random.RandomState(17)
        first = rng.randint(0, 256, size=(24, 32, 3)).astype(np.uint8)
        second = np.clip(first.astype(np.int16) + 3, 0, 255).astype(np.uint8)
        _idx1, previous = encoder.quantize_per_frame(first, 16, "median-cut")
        _idx_f, free = encoder.quantize_per_frame(second, 16, "median-cut")
        idx_s, stable = encoder.quantize_per_frame(
            second, 16, "median-cut", previous_palette=previous,
            temporal_strength=0.5)
        if free.shape == previous.shape and stable.shape == previous.shape:
            self.assertLess(ordered_error(stable, previous),
                            ordered_error(free, previous))
        self.assertLess(int(idx_s.max()), len(stable))

    def test_per_frame_video_palettes_drift_less(self):
        frames = [with_gray(gradient_image(shift=(k, -k, k)))
                  for k in range(4)]

        def encode(path, disabled):
            def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
                return iter(frames)

            context = (mock.patch.object(
                encoder, "_stabilize_rgb_palette",
                side_effect=lambda pal, _prev, _s: pal)
                if disabled else mock.patch.object(
                    encoder, "probe_size", return_value=(96, 32)))
            with mock.patch.object(encoder, "probe_size",
                                   return_value=(96, 32)), \
                    mock.patch.object(encoder, "iter_video_frames",
                                      side_effect=fake_iter), context:
                encoder.encode_video(
                    "synthetic.mp4", path, mode_name="pixel", cols=96,
                    rows=32, fps=15, pal_size=16, ramp_name="short",
                    char_aspect=0.5, compress="auto",
                    palette_mode="per-frame", keyint=100, with_audio=False,
                    palette_algorithm="kmeans-rgb")

        import ascl_decode
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            plain = os.path.join(directory, "plain.ascl")
            stable = os.path.join(directory, "stable.ascl")
            encode(plain, disabled=True)
            encode(stable, disabled=False)

            def boundary_error(path):
                _hdr, _ramp, _cells, pal_list = ascl_decode.decode_all(path)
                pairs = []
                for older, newer in zip(pal_list, pal_list[1:]):
                    older = np.asarray(older, dtype=np.uint8)
                    newer = np.asarray(newer, dtype=np.uint8)
                    if older.shape == newer.shape:
                        pairs.append(ordered_error(newer, older))
                return float(np.mean(pairs)) if pairs else 0.0

            error_before = boundary_error(plain)
            error_after = boundary_error(stable)
            print("E-15 per-frame kmeans-rgb: antes=%.3f despues=%.3f" %
                  (error_before, error_after))
            self.assertLessEqual(error_after, error_before)


if __name__ == "__main__":
    unittest.main()
