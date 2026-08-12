import os
import struct
import sys
import tempfile
import types
import unittest
import zlib
from unittest import mock

import numpy as np
from PIL import Image


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import encoder  # noqa: E402
import dither  # noqa: E402


def nearest_indices(rgb, palette):
    source = rgb.astype(np.int32)
    colors = palette.astype(np.int32)
    delta = source[:, :, None, :] - colors[None, None, :, :]
    return np.argmin(np.sum(delta * delta, axis=3), axis=2).astype(np.uint8)


def block_means(reconstructed, block=4):
    values = []
    h, w = reconstructed.shape[:2]
    for y in range(0, h, block):
        for x in range(0, w, block):
            values.append(float(reconstructed[y:y + block, x:x + block].mean()))
    return np.asarray(values)


class QualityOptionsTest(unittest.TestCase):
    def test_writer_rejects_ramp_beyond_v1_uint8_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "rampa excede 255"):
                encoder.write_ascl(
                    os.path.join(directory, "too-long-ramp.ascl"),
                    encoder.MODE_ASCII_BW, 1, 1, 15, "x" * 256, [], None,
                    encoder.DEFAULT_CHAR_ASPECT, 0)

    def test_kmeans_rgb_falls_back_when_cv2_namespace_is_incomplete(self):
        rng = np.random.default_rng(91)
        source = rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)
        incomplete = types.ModuleType("cv2")
        with mock.patch.dict(sys.modules, {"cv2": incomplete}):
            first = encoder._kmeans_rgb_palette([source], 8, max_samples=500)
            second = encoder._kmeans_rgb_palette([source], 8, max_samples=500)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first.shape, (8, 3))
        self.assertEqual(first.dtype, np.uint8)

    def test_selective_dither_reduces_gradient_banding(self):
        height, width = 32, 128
        gray = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        palette = np.asarray(((0, 0, 0), (85, 85, 85),
                              (170, 170, 170), (255, 255, 255)), dtype=np.uint8)
        baseline = nearest_indices(rgb, palette)
        result, details = dither.apply_selective_dither(
            rgb, baseline, palette, matrix_size=4, return_details=True)

        normal_means = block_means(palette[baseline])
        dither_means = block_means(palette[result])
        source_means = block_means(rgb)
        self.assertGreater(len(np.unique(dither_means)), len(np.unique(normal_means)))
        self.assertLess(np.mean(np.abs(dither_means - source_means)),
                        np.mean(np.abs(normal_means - source_means)))
        self.assertTrue(np.any(details["changed"]))

    def test_selective_dither_preserves_dilated_edges(self):
        height, width = 32, 64
        gray = np.tile(np.linspace(32, 220, width, dtype=np.uint8), (height, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        rgb[8:24, 30:34] = 255
        palette = np.asarray(((0, 0, 0), (85, 85, 85),
                              (170, 170, 170), (255, 255, 255)), dtype=np.uint8)
        baseline = nearest_indices(rgb, palette)
        result, details = dither.apply_selective_dither(
            rgb, baseline, palette, matrix_size=4, return_details=True)
        self.assertTrue(np.any(details["protected"]))
        self.assertTrue(np.array_equal(result[details["protected"]],
                                       baseline[details["protected"]]))

    def test_selective_dither_is_deterministic_and_bayer_is_absolute(self):
        height, width = 32, 128
        gray = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        palette = np.asarray(((0, 0, 0), (85, 85, 85),
                              (170, 170, 170), (255, 255, 255)), dtype=np.uint8)
        baseline = nearest_indices(rgb, palette)
        first = dither.apply_selective_dither(rgb, baseline, palette, matrix_size=4)
        second = dither.apply_selective_dither(rgb, baseline, palette, matrix_size=4)
        self.assertEqual(first.tobytes(), second.tobytes())

        # El patron no depende del numero de frame ni de una semilla. En una franja
        # interior uniforme con cobertura fija se repite exactamente cada 4 filas.
        _, details = dither.apply_selective_dither(
            rgb, baseline, palette, matrix_size=4, return_details=True)
        stable = details["changed"]
        self.assertTrue(np.any(stable[8:12, 40:80]))
        self.assertTrue(np.array_equal(stable[8:12, 40:80], stable[12:16, 40:80]))

    def test_dithered_ascl_v1_is_byte_reproducible(self):
        height, width = 32, 128
        gray = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        with tempfile.TemporaryDirectory() as td:
            source = os.path.join(td, "gradient.png")
            first = os.path.join(td, "first.ascl")
            second = os.path.join(td, "second.ascl")
            Image.fromarray(rgb, "RGB").save(source)
            options = dict(
                mode_name="pixel", cols=width, rows=height, fps=15,
                pal_size=4, ramp_name="short", char_aspect=0.5,
                compress="auto", palette_mode="per-frame",
                dither_mode="selective", dither_matrix=4)
            encoder.encode_image(source, first, **options)
            encoder.encode_image(source, second, **options)
            with open(first, "rb") as fh:
                first_data = fh.read()
            with open(second, "rb") as fh:
                second_data = fh.read()
            self.assertEqual(first_data, second_data)
            header = struct.unpack_from(encoder.HEADER_FMT, first_data, 0)
            self.assertEqual(header[1], 1)
            self.assertEqual(header[3], encoder.FLAG_HAS_OFFSET_TABLE)

    def test_video_per_frame_dither_is_rejected_explicitly(self):
        with self.assertRaisesRegex(ValueError, "global o block"):
            encoder.encode_video(
                "unused.mp4", "unused.ascl", "pixel", 8, 8, 15, 16,
                "short", 0.5, "auto", "per-frame", 30, False,
                dither_mode="selective")

    def test_profiles_and_manual_overrides(self):
        self.assertEqual(
            encoder.resolve_quality_options("detail", None, None, 320), (960, 64))
        self.assertEqual(
            encoder.resolve_quality_options("balanced", 777, None, 320), (777, 128))
        self.assertEqual(
            encoder.resolve_quality_options("color", None, 32, 320), (320, 32))
        self.assertEqual(
            encoder.resolve_quality_options("graphic", None, None, 320), (640, 256))
        self.assertEqual(
            encoder.resolve_quality_options("graphic-hq", None, None, 320), (768, 256))
        self.assertEqual(
            encoder.resolve_quality_options("graphic-ultra", None, None, 320), (960, 256))
        self.assertEqual(
            encoder.resolve_quality_options("custom", None, None, 320), (320, 256))

    def test_palette_algorithm_validation(self):
        base = ("pixel", 64, 0, 15, 128, 0.5, "block", "none", "nearest")
        for algorithm in encoder.PALETTE_ALGORITHMS:
            encoder.validate_encode_options(*base, palette_algorithm=algorithm)
        with self.assertRaisesRegex(ValueError, "palette-algorithm"):
            encoder.validate_encode_options(*base, palette_algorithm="unknown")

    def test_kmeans_palette_is_deterministic_and_indices_are_bounded(self):
        rng = np.random.default_rng(2026)
        samples = [rng.integers(0, 256, size=(32, 48, 3), dtype=np.uint8)
                   for _ in range(3)]
        first_img, first = encoder.make_global_palette(
            samples, 16, "kmeans-rgb")
        second_img, second = encoder.make_global_palette(
            samples, 16, "kmeans-rgb")
        self.assertEqual(first.tobytes(), second.tobytes())
        idx = encoder.quantize_with(first_img, samples[0])
        self.assertLess(int(idx.max()), 16)
        self.assertEqual(first_img.getpalette(), second_img.getpalette())

    def test_kmeans_improves_synthetic_multimodal_color_error(self):
        # Muchos tonos azules continuos y tres acentos poco frecuentes. Es el caso
        # donde una particion por poblacion desperdicia colores en gradientes densos.
        width, height = 256, 96
        x = np.linspace(0, 1, width, dtype=np.float32)[None, :, None]
        left = np.array([8, 72, 170], dtype=np.float32)
        right = np.array([30, 210, 250], dtype=np.float32)
        rgb = np.repeat(left + (right - left) * x, height, axis=0)
        rgb[8:28, 10:30] = (250, 160, 5)
        rgb[35:55, 40:60] = (245, 245, 240)
        rgb[62:82, 70:90] = (20, 200, 60)
        rgb = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)

        median_img, median_pal = encoder.make_global_palette(
            [rgb], 16, "median-cut")
        kmeans_img, kmeans_pal = encoder.make_global_palette(
            [rgb], 16, "kmeans-rgb")
        median_recon = median_pal[encoder.quantize_with(median_img, rgb)]
        kmeans_recon = kmeans_pal[encoder.quantize_with(kmeans_img, rgb)]
        median_mse = np.mean((rgb.astype(np.float32) - median_recon) ** 2)
        kmeans_mse = np.mean((rgb.astype(np.float32) - kmeans_recon) ** 2)
        self.assertLess(kmeans_mse, median_mse * 0.90)

    def test_exact_cfr_mapping_preserves_duration(self):
        cases = (
            (500, 25.0, 15, 300),
            (500, 25.0, 10, 200),
            (300, 15.0, 25, 500),
        )
        for source_frames, source_fps, target_fps, expected in cases:
            output = 0
            while encoder.output_source_index(output, source_fps, target_fps) < source_frames:
                output += 1
            self.assertEqual(output, expected)
            self.assertAlmostEqual(
                output / float(target_fps), source_frames / float(source_fps), places=6)

    def test_baked_soft_reconstruction_changes_pixels_but_not_dimensions(self):
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        rgb[:, 4:] = 255
        src = Image.fromarray(rgb, "RGB")
        normal = np.asarray(encoder.resize_pil_for_grid(src, 16, 16, "none"))
        soft = np.asarray(encoder.resize_pil_for_grid(src, 16, 16, "soft"))
        self.assertEqual(normal.shape, soft.shape)
        self.assertEqual(soft.shape, (16, 16, 3))
        self.assertFalse(np.array_equal(normal, soft))

    def test_soft_flag_keeps_v1_and_crc(self):
        rgb = np.zeros((12, 16, 3), dtype=np.uint8)
        rgb[:, :8] = (255, 40, 20)
        rgb[:, 8:] = (20, 60, 255)
        with tempfile.TemporaryDirectory() as td:
            source = os.path.join(td, "source.png")
            output = os.path.join(td, "output.ascl")
            Image.fromarray(rgb, "RGB").save(source)
            encoder.encode_image(
                source, output, "pixel", 16, 12, 15, 16, "short", 0.5,
                "auto", "per-frame", bake_smoothing="soft",
                reconstruction="soft")
            with open(output, "rb") as fh:
                data = fh.read()
            header = struct.unpack_from(encoder.HEADER_FMT, data, 0)
            self.assertEqual(header[0], encoder.MAGIC)
            self.assertEqual(header[1], 1)
            self.assertTrue(header[3] & encoder.FLAG_HAS_OFFSET_TABLE)
            self.assertTrue(header[3] & encoder.FLAG_RECON_SOFT)
            self.assertEqual(zlib.crc32(data[encoder.HEADER_SIZE:]) & 0xFFFFFFFF,
                             header[-1])

    def test_block_palette_makes_every_actual_keyframe_self_contained(self):
        rng = np.random.default_rng(1234)
        frames = []
        for _ in range(6):
            rgb = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
            gray = ((rgb[:, :, 0].astype(np.uint16) * 77 +
                     rgb[:, :, 1].astype(np.uint16) * 150 +
                     rgb[:, :, 2].astype(np.uint16) * 29) >> 8).astype(np.uint8)
            frames.append((rgb, gray))

        def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
            return iter(frames)

        with tempfile.TemporaryDirectory() as td:
            output = os.path.join(td, "block.ascl")
            with mock.patch.object(encoder, "probe_size", return_value=(8, 8)), \
                    mock.patch.object(encoder, "iter_video_frames", side_effect=fake_iter):
                info = encoder.encode_video(
                    "synthetic.mp4", output, "pixel", 8, 8, 3, 16, "short", 0.5,
                    "auto", "block", 2, False, palette_block_frames=3)

            self.assertEqual(info["n_frames"], 6)
            self.assertEqual(info["palette_block_frames"], 3)
            self.assertTrue(info["flags"] & encoder.FLAG_PAL_PER_SCENE)
            with open(output, "rb") as fh:
                data = fh.read()
            header = struct.unpack_from(encoder.HEADER_FMT, data, 0)
            n_frames = header[8]
            data_off = header[11]
            offsets = struct.unpack_from("<%dI" % n_frames, data, data_off)
            for offset in offsets:
                tag = data[offset + 4]
                pal_count = struct.unpack_from("<H", data, offset + 5)[0]
                if tag in (encoder.TAG_RAW, encoder.TAG_ZLIB):
                    self.assertGreater(pal_count, 0)

    def test_audio_extraction_uses_portable_ffmpeg_fallback(self):
        portable = types.SimpleNamespace(
            get_ffmpeg_exe=lambda: "portable-ffmpeg.exe")
        completed = types.SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as td:
            output = os.path.join(td, "audio.mp3")
            with open(output, "wb") as fh:
                fh.write(b"mp3")
            with mock.patch("shutil.which", return_value=None), \
                    mock.patch.dict(sys.modules, {"imageio_ffmpeg": portable}), \
                    mock.patch.object(encoder.subprocess, "run", return_value=completed) as run:
                self.assertTrue(encoder.extract_audio("source.mp4", output))
            self.assertEqual(run.call_args[0][0][0], "portable-ffmpeg.exe")


if __name__ == "__main__":
    unittest.main()
