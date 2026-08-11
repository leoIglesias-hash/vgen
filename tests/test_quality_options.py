import os
import struct
import sys
import tempfile
import unittest
import zlib
from unittest import mock

import numpy as np
from PIL import Image


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import encoder  # noqa: E402


class QualityOptionsTest(unittest.TestCase):
    def test_profiles_and_manual_overrides(self):
        self.assertEqual(
            encoder.resolve_quality_options("detail", None, None, 320), (960, 64))
        self.assertEqual(
            encoder.resolve_quality_options("balanced", 777, None, 320), (777, 128))
        self.assertEqual(
            encoder.resolve_quality_options("color", None, 32, 320), (320, 32))
        self.assertEqual(
            encoder.resolve_quality_options("custom", None, None, 320), (320, 256))

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


if __name__ == "__main__":
    unittest.main()
