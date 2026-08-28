# -*- coding: utf-8 -*-
"""E-12: refit de paleta a la asignacion real (Lloyd acotado y monotono)."""
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import adaptive_palette  # noqa: E402
import encoder  # noqa: E402
import overlay_palette  # noqa: E402
import perceptual_palette  # noqa: E402


def clustered_image(seed=20260828, centers=((40, 40, 40), (128, 32, 200),
                                            (220, 180, 60)),
                    jitter=6, per_cluster=432):
    """Imagen sintetica con clusters compactos y centros conocidos."""
    rng = np.random.default_rng(seed)
    blobs = []
    for center in centers:
        noise = rng.integers(-jitter, jitter + 1, size=(per_cluster, 3))
        blobs.append(np.clip(np.asarray(center, dtype=np.int64) + noise, 0, 255))
    pixels = np.concatenate(blobs, axis=0).astype(np.uint8)
    side = int(np.sqrt(len(pixels)))
    return np.ascontiguousarray(pixels[: side * side].reshape(side, side, 3))


def assignment_and_error(pixels, palette, palette_algorithm):
    """Misma regla de asignacion y metrica que usa el refit."""
    flat = pixels.reshape(-1, 3)
    indices = encoder._refit_assignment(flat, palette, palette_algorithm, 0)
    if palette_algorithm == "kmeans-oklab":
        diff = (perceptual_palette.srgb_to_oklab(flat) -
                perceptual_palette.srgb_to_oklab(palette)[indices])
    else:
        diff = flat.astype(np.float64) - palette[indices].astype(np.float64)
    return indices, float(np.mean(np.sum(diff * diff, axis=1)))


class PaletteRefitTest(unittest.TestCase):
    def test_zero_iterations_is_identity(self):
        image = clustered_image()
        palette = np.asarray(((0, 0, 0), (128, 128, 128), (255, 255, 255)),
                             dtype=np.uint8)
        result = encoder.refit_palette(palette, [image], "kmeans-rgb", 0)
        self.assertEqual(result.tobytes(), palette.tobytes())
        pal_img = encoder._palette_image(palette)
        same_img, same_pal = encoder.refit_block_palette(
            pal_img, palette, [image], "kmeans-rgb", 0)
        self.assertIs(same_img, pal_img)
        self.assertIs(same_pal, palette)

    def test_rejects_out_of_range_iterations(self):
        image = clustered_image()
        palette = np.zeros((4, 3), dtype=np.uint8)
        for bad in (-1, 11):
            with self.assertRaisesRegex(ValueError, "palette-refit"):
                encoder.refit_palette(palette, [image], "kmeans-rgb", bad)
            with self.assertRaisesRegex(ValueError, "palette-refit"):
                encoder.validate_encode_options(
                    "pixel", 32, 0, 15, 256, 0.5, "global", "none", "nearest",
                    palette_refit=bad)
        encoder.validate_encode_options(
            "pixel", 32, 0, 15, 256, 0.5, "global", "none", "nearest",
            palette_refit=10)

    def test_rejects_empty_samples(self):
        palette = np.zeros((4, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "pixeles"):
            encoder.refit_palette(
                palette, [np.zeros((0, 3), dtype=np.uint8)], "kmeans-rgb", 2)

    def test_refit_reduces_rgb_error_of_offset_palette(self):
        centers = ((40, 40, 40), (128, 32, 200), (220, 180, 60))
        image = clustered_image(centers=centers)
        offset = np.clip(np.asarray(centers, dtype=np.int64) + 25,
                         0, 255).astype(np.uint8)
        _, before = assignment_and_error(image, offset, "kmeans-rgb")
        refit = encoder.refit_palette(offset, [image], "kmeans-rgb", 5)
        _, after = assignment_and_error(image, refit, "kmeans-rgb")
        self.assertLess(after, before)
        # Cada entrada refiteada queda cerca del centro real de su cluster.
        for center, entry in zip(centers, refit):
            self.assertLess(np.max(np.abs(entry.astype(np.int64) -
                                          np.asarray(center))), 8)

    def test_refit_never_degrades_any_algorithm(self):
        image = clustered_image(seed=91, jitter=18)
        for algorithm in encoder.PALETTE_ALGORITHMS:
            _, palette = encoder.make_global_palette([image], 8, algorithm)
            _, before = assignment_and_error(image, palette, algorithm)
            refit = encoder.refit_palette(palette, [image], algorithm, 3)
            _, after = assignment_and_error(image, refit, algorithm)
            self.assertLessEqual(after, before + 1e-9,
                                 "refit degrado %s" % algorithm)

    def test_reserved_rows_stay_byte_identical(self):
        table = overlay_palette.reserved_table(10)
        image = clustered_image(seed=7, jitter=20)
        _, palette = encoder.make_global_palette(
            [image], 64, "kmeans-oklab", reserved=10, reserved_colors=table)
        refit = encoder.refit_palette(
            palette, [image], "kmeans-oklab", 3, reserved=10)
        self.assertEqual(refit.shape, palette.shape)
        self.assertEqual(refit[-10:].tobytes(), table.tobytes())
        pal_img, full = encoder.refit_block_palette(
            encoder._palette_image(palette[:-10]), palette, [image],
            "kmeans-oklab", 3, reserved=10)
        # La pal_img reconstruida sigue siendo solo-base (INV-3).
        self.assertEqual(pal_img.size[0], len(full) - 10)
        self.assertEqual(full[-10:].tobytes(), table.tobytes())

    def test_refit_is_deterministic(self):
        image = clustered_image(seed=13, jitter=14)
        _, palette = encoder.make_global_palette([image], 8, "kmeans-rgb")
        first = encoder.refit_palette(palette, [image], "kmeans-rgb", 5)
        second = encoder.refit_palette(palette, [image], "kmeans-rgb", 5)
        self.assertEqual(first.tobytes(), second.tobytes())

    def test_quantize_per_frame_median_cut_refit(self):
        image = clustered_image(seed=29, jitter=22)
        base_idx, base_pal = encoder.quantize_per_frame(image, 16, "median-cut")
        idx, pal = encoder.quantize_per_frame(image, 16, "median-cut",
                                              palette_refit=3)
        self.assertEqual(len(pal), len(base_pal))
        self.assertLess(int(idx.max()), len(pal))
        # El error se mide con la misma regla de asignacion que uso el refit:
        # la aceptacion monotona garantiza que nunca empeora.
        _, error_base = assignment_and_error(image, base_pal, "median-cut")
        _, error_refit = assignment_and_error(image, pal, "median-cut")
        self.assertLessEqual(error_refit, error_base + 1e-6)
        reconstruction = float(np.mean(np.sum(
            (image.astype(np.float64) - pal[idx]) ** 2, axis=2)))
        self.assertLessEqual(reconstruction, error_refit + 1e-6)

    def test_scene_palette_frames_apply_refit(self):
        config = adaptive_palette.AdaptivePaletteConfig(
            min_frames=2, max_frames=4, change_threshold=0.20,
            hard_cut_threshold=0.58, max_stability=0.25)
        frames = []
        for seed in (1, 2, 3, 4, 5, 6):
            rgb = clustered_image(seed=seed, jitter=16)
            gray = np.asarray(Image.fromarray(rgb, "RGB").convert("L"), np.uint8)
            frames.append((rgb, gray))

        def collect(refit):
            out = []
            for item in encoder.iter_scene_palette_frames(
                    iter(frames), 8, "block", 3, config,
                    palette_algorithm="kmeans-rgb", palette_refit=refit):
                rgb, _gray, pal_img, palette, _q, first, _diag, _cut = item
                out.append((first, palette, pal_img))
            return out

        plain = collect(0)
        refit = collect(2)
        self.assertEqual(len(plain), len(refit))
        self.assertEqual([f for f, _p, _i in plain], [f for f, _p, _i in refit])
        # Con bloques de 3 frames las muestras del refit son el bloque entero:
        # el error por bloque es exactamente la metrica de aceptacion monotona.
        starts = [k for k, (first, _p, _i) in enumerate(plain) if first]
        self.assertGreater(len(starts), 1)
        bounds = starts + [len(plain)]
        for b in range(len(starts)):
            lo, hi = bounds[b], bounds[b + 1]
            block_pixels = np.concatenate(
                [frames[k][0].reshape(-1, 3) for k in range(lo, hi)])
            self.assertEqual(refit[lo][1].shape, plain[lo][1].shape)
            _, before = assignment_and_error(block_pixels, plain[lo][1],
                                             "kmeans-rgb")
            _, after = assignment_and_error(block_pixels, refit[lo][1],
                                            "kmeans-rgb")
            self.assertLessEqual(after, before + 1e-6)
            self.assertEqual(refit[lo][2].size[0], len(refit[lo][1]))

    def test_encode_image_threads_palette_refit(self):
        image = clustered_image(seed=41, jitter=12)
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "in.png")
            Image.fromarray(image, "RGB").save(source)
            out = os.path.join(directory, "out.ascl")
            info = encoder.encode_image(
                source, out, "pixel", 32, 0, 15, 32, "short", 0.5, "auto",
                "per-frame", palette_algorithm="kmeans-rgb", palette_refit=3)
            self.assertEqual(info["palette_refit"], 3)
            self.assertGreater(os.path.getsize(out), 0)


if __name__ == "__main__":
    unittest.main()
