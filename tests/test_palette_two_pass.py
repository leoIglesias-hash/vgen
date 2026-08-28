# -*- coding: utf-8 -*-
"""E-14: paleta sobre todos los pixeles, en dos pasadas (sin materializar)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_decode  # noqa: E402
import encoder  # noqa: E402
import perceptual_palette as perceptual  # noqa: E402


WIDTH, HEIGHT = 24, 16


def with_gray(rgb):
    x = rgb.astype(np.uint16)
    gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)
    return rgb, gray


def noise_frames(count, seed=99):
    rng = np.random.RandomState(seed)
    frames = []
    for _ in range(count):
        rgb = rng.randint(0, 256, size=(HEIGHT, WIDTH, 3)).astype(np.uint8)
        frames.append(with_gray(rgb))
    return frames


def encode(path, frames, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(frames)

    defaults = dict(
        mode_name="pixel", cols=WIDTH, rows=HEIGHT, fps=15, pal_size=32,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode="global", keyint=100, with_audio=False,
        palette_algorithm="fast-octree")
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size",
                           return_value=(WIDTH, HEIGHT)), \
            mock.patch.object(encoder, "iter_video_frames",
                              side_effect=fake_iter) as fake:
        info = encoder.encode_video("synthetic.mp4", path, **defaults)
    return info, fake.call_count


class StreamingAggregateTest(unittest.TestCase):
    def test_mass_is_conserved_and_colors_collapse(self):
        frames = [frame[0] for frame in noise_frames(2, seed=5)]
        shared = frames[0].copy()  # el segundo frame repite colores del primero
        aggregate = perceptual.StreamingColorAggregate()
        aggregate.add_frame(frames[0])
        aggregate.add_frame(shared)
        colors, mass = aggregate.result()
        expected_mass = sum(
            float(perceptual.smooth_gradient_weights(f).sum())
            for f in (frames[0], shared))
        self.assertAlmostEqual(float(mass.sum()), expected_mass, places=6)
        # Colores identicos entre frames quedan colapsados en una sola fila.
        packed = perceptual._packed_rgb(colors)
        self.assertEqual(len(np.unique(packed)), len(colors))
        self.assertEqual(aggregate.frame_count, 2)
        self.assertEqual(aggregate.pixel_count, 2 * WIDTH * HEIGHT)

    def test_compaction_threshold_does_not_change_the_result(self):
        frames = [frame[0] for frame in noise_frames(4, seed=6)]
        plain = perceptual.StreamingColorAggregate()
        compact = perceptual.StreamingColorAggregate(compact_threshold=8)
        for frame in frames:
            plain.add_frame(frame)
            compact.add_frame(frame)
        colors_a, mass_a = plain.result()
        colors_b, mass_b = compact.result()
        self.assertEqual(colors_a.tobytes(), colors_b.tobytes())
        np.testing.assert_allclose(mass_a, mass_b, rtol=0, atol=1e-9)

    def test_empty_aggregate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "frame"):
            perceptual.StreamingColorAggregate().result()


class SampleAggregateTest(unittest.TestCase):
    def test_single_frame_aggregate_matches_uncapped_weighted_samples(self):
        rng = np.random.default_rng(31)
        image = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
        direct = perceptual.build_perceptual_palette(
            [image], 8, max_samples=16 * 16)
        aggregate = perceptual.StreamingColorAggregate()
        aggregate.add_frame(image)
        colors, mass = aggregate.result()
        from_aggregate = perceptual.build_perceptual_palette(
            None, 8, sample_aggregate=(colors, mass))
        self.assertEqual(from_aggregate.tobytes(), direct.tobytes())

    def test_sample_aggregate_is_validated(self):
        colors = np.zeros((4, 3), dtype=np.uint8)
        good = np.ones(4, dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "desalineados"):
            perceptual.build_perceptual_palette(
                None, 2, sample_aggregate=(colors, np.ones(3)))
        with self.assertRaisesRegex(ValueError, "masa"):
            perceptual.build_perceptual_palette(
                None, 2, sample_aggregate=(colors, np.zeros(4)))
        with self.assertRaisesRegex(ValueError, "excluye"):
            perceptual.build_perceptual_palette(
                [colors.reshape(2, 2, 3)], 2,
                sample_aggregate=(colors, good))


class WeightedRefitTest(unittest.TestCase):
    def test_unit_weights_match_the_historic_path(self):
        rng = np.random.default_rng(41)
        image = rng.integers(0, 256, size=(18, 18, 3), dtype=np.uint8)
        _, palette = encoder.make_global_palette([image], 8, "kmeans-rgb")
        plain = encoder.refit_palette(palette, [image], "kmeans-rgb", 4)
        weighted = encoder.refit_palette(
            palette, [image], "kmeans-rgb", 4,
            sample_weights=np.ones(18 * 18, dtype=np.float64))
        self.assertEqual(plain.tobytes(), weighted.tobytes())

    def test_mass_shifts_the_refitted_entry(self):
        pixels = np.asarray(((0, 0, 0), (10, 10, 10)),
                            dtype=np.uint8).reshape(2, 1, 3)
        palette = np.asarray(((200, 200, 200),), dtype=np.uint8)
        light = encoder.refit_palette(
            palette, [pixels], "kmeans-rgb", 1,
            sample_weights=np.asarray((1.0, 1.0)))
        heavy = encoder.refit_palette(
            palette, [pixels], "kmeans-rgb", 1,
            sample_weights=np.asarray((1.0, 999.0)))
        self.assertEqual(light[0].tolist(), [5, 5, 5])
        self.assertEqual(heavy[0].tolist(), [10, 10, 10])

    def test_misaligned_weights_are_rejected(self):
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        palette = np.zeros((2, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "alinear"):
            encoder.refit_palette(palette, [image], "kmeans-rgb", 1,
                                  sample_weights=np.ones(3))


class GlobalTwoPassTest(unittest.TestCase):
    def test_pillow_sampling_reproduces_the_historic_selection(self):
        frames = noise_frames(8, seed=7)
        stepS = max(1, len(frames) // 12)
        sample = [frames[k][0] for k in range(0, len(frames), stepS)]
        _img, expected = encoder.make_global_palette(sample, 32, "fast-octree")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.ascl")
            _info, calls = encode(path, frames)
            # conteo + muestreo + encode: tres lecturas del stream, cero listas
            self.assertEqual(calls, 3)
            _hdr, _ramp, _cells, pal_list = ascl_decode.decode_all(path)
            stored = np.asarray(pal_list[0], dtype=np.uint8)
            np.testing.assert_array_equal(stored[:len(expected)], expected)

    def test_kmeans_oklab_uses_two_passes_and_is_deterministic(self):
        frames = noise_frames(6, seed=8)
        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "a.ascl")
            second = os.path.join(directory, "b.ascl")
            _info_a, calls = encode(first, frames,
                                    palette_algorithm="kmeans-oklab")
            self.assertEqual(calls, 2)
            encode(second, frames, palette_algorithm="kmeans-oklab")
            with open(first, "rb") as fa, open(second, "rb") as fb:
                self.assertEqual(fa.read(), fb.read())
            hdr, _ramp, cells_list, pal_list = ascl_decode.decode_all(first)
            self.assertEqual(hdr["n_frames"], len(frames))
            palette = np.asarray(pal_list[0], dtype=np.uint8)
            for cells in cells_list:
                self.assertLess(int(np.asarray(cells).max()), len(palette))

    def test_refit_composes_with_the_aggregate_path(self):
        frames = noise_frames(6, seed=9)
        with tempfile.TemporaryDirectory() as directory:
            plain = os.path.join(directory, "plain.ascl")
            refit = os.path.join(directory, "refit.ascl")
            encode(plain, frames, palette_algorithm="kmeans-oklab")
            info, _calls = encode(refit, frames,
                                  palette_algorithm="kmeans-oklab",
                                  palette_refit=3)
            self.assertEqual(info["palette_refit"], 3)
            self.assertGreater(os.path.getsize(refit), 0)

    def test_empty_stream_still_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            for algorithm in ("kmeans-oklab", "fast-octree"):
                path = os.path.join(directory, algorithm + ".ascl")
                with self.assertRaisesRegex(RuntimeError, "sin frames"):
                    encode(path, [], palette_algorithm=algorithm)


if __name__ == "__main__":
    unittest.main()
