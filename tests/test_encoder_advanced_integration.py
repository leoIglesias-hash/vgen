import os
import contextlib
import io
import struct
import sys
import tempfile
import unittest
import zlib
from unittest import mock

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_decode  # noqa: E402
import encoder  # noqa: E402
import make_clip  # noqa: E402


def color_frame(base, width=24, height=16):
    yy, xx = np.indices((height, width))
    values = np.empty((height, width, 3), dtype=np.int16)
    values[:, :, 0] = int(base[0]) + xx * 2
    values[:, :, 1] = int(base[1]) + yy * 2
    values[:, :, 2] = int(base[2]) + (xx + yy) // 2
    rgb = np.clip(values, 0, 255).astype(np.uint8)
    x = rgb.astype(np.uint16)
    gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)
    return rgb, gray


def encode_fake_video(path, frames, palette_mode, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(frames)

    defaults = dict(
        mode_name="pixel", cols=24, rows=16, fps=15, pal_size=8,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode=palette_mode, keyint=4, with_audio=False,
        palette_algorithm="kmeans-oklab")
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size", return_value=(24, 16)), \
            mock.patch.object(encoder, "iter_video_frames", side_effect=fake_iter):
        return encoder.encode_video("synthetic.mp4", path, **defaults)


def frame_headers(path):
    with open(path, "rb") as stream:
        data = stream.read()
    header = ascl_decode.parse_header(data)
    offsets = struct.unpack_from("<%dI" % header["n_frames"],
                                 data, header["data_off"])
    result = []
    for offset in offsets:
        block_length = struct.unpack_from("<I", data, offset)[0]
        tag = data[offset + 4]
        palette_count = struct.unpack_from("<H", data, offset + 5)[0]
        result.append((offset, block_length, tag, palette_count))
    return data, header, result


class AdvancedEncoderIntegrationTest(unittest.TestCase):
    def test_adaptive_oklab_auto_is_v1_seekable_and_reports_boundaries(self):
        blue = color_frame((18, 65, 150))
        orange = color_frame((185, 50, 12))
        frames = [blue for _ in range(6)] + [orange for _ in range(6)]
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "adaptive.ascl")
            info = encode_fake_video(
                output, frames, "adaptive", adaptive_min_frames=3,
                adaptive_max_frames=5, adaptive_change_threshold=0.20,
                adaptive_hard_cut_threshold=0.58,
                adaptive_stability_max=0.25, perceptual_lut_bits=0,
                dither_mode="auto", dither_budget=0.10,
                dither_min_improvement=0.01, dither_window=2)

            header, _ramp, decoded, palettes = ascl_decode.decode_all(output)
            data, raw_header, metadata = frame_headers(output)
            self.assertEqual(header["version"], 1)
            self.assertTrue(header["crc_ok"])
            self.assertTrue(header["flags"] & encoder.FLAG_PAL_PER_SCENE)
            self.assertFalse(header["flags"] & encoder.FLAG_PAL_GLOBAL)
            self.assertEqual(raw_header["flags"], info["flags"])
            self.assertEqual(len(decoded), len(frames))
            self.assertEqual(sum(info["palette_block_sizes"]), len(frames))
            self.assertIn("hard-cut", info["palette_block_reasons"])
            self.assertEqual(info["perceptual_lut_bits"], 0)
            # Hay varias renovaciones de paleta, pero la historia de dithering se
            # reinicia unicamente en el cambio cromatico fuerte.
            self.assertGreater(len(info["palette_blocks"]), 2)
            self.assertEqual(info["dither_temporal_resets"], 1)

            starts = [block["start"] for block in info["palette_blocks"]]
            for frame_index in starts:
                _offset, _length, tag, palette_count = metadata[frame_index]
                self.assertIn(tag, (encoder.TAG_RAW, encoder.TAG_ZLIB))
                self.assertGreater(palette_count, 0)

            # Todo full frame puede decodificarse por si solo con la paleta que
            # contiene: es la propiedad usada por seek en el reader v1.
            for frame_index, (offset, block_length, tag, palette_count) in enumerate(metadata):
                if tag not in (encoder.TAG_RAW, encoder.TAG_ZLIB):
                    continue
                self.assertGreater(palette_count, 0)
                payload_start = offset + 7 + palette_count * 3
                payload = data[payload_start:offset + 4 + block_length]
                planes = payload if tag == encoder.TAG_RAW else zlib.decompress(payload)
                direct = ascl_decode.planes_to_cells(
                    planes, header["mode"], header["cols"] * header["rows"])
                np.testing.assert_array_equal(direct, decoded[frame_index])
                self.assertIsNotNone(palettes[frame_index])
                self.assertLess(int(direct[:, 0].max()), len(palettes[frame_index]))

    def test_oklab_works_with_global_fixed_block_and_per_frame_lut(self):
        frames = [color_frame((25 + index * 2, 80, 145 - index))
                  for index in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            for palette_mode in ("global", "block", "per-frame"):
                output = os.path.join(directory, palette_mode + ".ascl")
                info = encode_fake_video(
                    output, frames, palette_mode, palette_block_frames=2,
                    perceptual_lut_bits=3, dither_mode="off")
                header, _ramp, decoded, palettes = ascl_decode.decode_all(output)
                self.assertTrue(header["crc_ok"])
                self.assertEqual(len(decoded), 5)
                self.assertEqual(info["palette_algorithm"], "kmeans-oklab")
                self.assertEqual(info["perceptual_lut_bits"], 3)
                self.assertTrue(all(palette is not None for palette in palettes))
                if palette_mode == "global":
                    self.assertTrue(header["flags"] & encoder.FLAG_PAL_GLOBAL)
                elif palette_mode == "block":
                    self.assertTrue(header["flags"] & encoder.FLAG_PAL_PER_SCENE)
                    self.assertEqual(info["palette_block_sizes"], [2, 2, 1])
                else:
                    self.assertFalse(header["flags"] &
                                     (encoder.FLAG_PAL_GLOBAL |
                                      encoder.FLAG_PAL_PER_SCENE))

    def test_new_options_validate_and_video_per_frame_rejects_both_dithers(self):
        base = dict(
            mode_name="pixel", cols=8, rows=8, fps=15, pal_size=8,
            char_aspect=0.5, palette_mode="adaptive",
            bake_smoothing="none", reconstruction="nearest",
            palette_algorithm="kmeans-oklab")
        encoder.validate_encode_options(**base)
        with self.assertRaisesRegex(ValueError, r"0 \(exacto\) o 3..7"):
            encoder.validate_encode_options(
                **dict(base, perceptual_lut_bits=2))
        with self.assertRaisesRegex(ValueError, "max_frames"):
            encoder.validate_encode_options(
                **dict(base, adaptive_min_frames=9, adaptive_max_frames=4))

        frames = [color_frame((20, 60, 140), 8, 8)]
        with tempfile.TemporaryDirectory() as directory:
            for dither_mode in ("selective", "auto"):
                with self.assertRaisesRegex(ValueError, "global o block"):
                    encode_fake_video(
                        os.path.join(directory, dither_mode + ".ascl"), frames,
                        "per-frame", cols=8, rows=8, pal_size=4,
                        dither_mode=dither_mode)

    def test_make_clip_cli_forwards_all_advanced_options(self):
        diagnostic = dict(index=0, start=0, end=3, size=3,
                          reason="end-of-stream", score=0.0,
                          entry_reason="start-of-stream", entry_score=1.0,
                          stability=0.0)
        info = dict(
            mode="pixel", cols=24, rows=16, fps=12, n_frames=3,
            palette_mode="adaptive", quality_profile="graphic-hq", pal_size=16,
            bake_smoothing="soft", reconstruction="soft",
            flags=encoder.FLAG_HAS_OFFSET_TABLE | encoder.FLAG_PAL_PER_SCENE,
            palette_algorithm="kmeans-oklab", dither="auto", dither_matrix=4,
            palette_blocks=[diagnostic], palette_block_sizes=[3],
            dither_budget=0.07, dither_min_improvement=0.11,
            dither_window=6, dither_changed_cells=12, audio=None)
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "clip.asclv")
            argv = [
                "synthetic.mp4", "--out", output, "--profile", "graphic-hq",
                "--cols", "24", "--rows", "16", "--fps", "12",
                "--palette-size", "16", "--palette", "adaptive",
                "--palette-algorithm", "kmeans-oklab",
                "--adaptive-min-frames", "4", "--adaptive-max-frames", "18",
                "--adaptive-change-threshold", "0.17",
                "--adaptive-hard-cut-threshold", "0.61",
                "--adaptive-stability-max", "0.19",
                "--perceptual-lut-bits", "5", "--dither", "auto",
                "--dither-budget", "0.07", "--dither-min-improvement", "0.11",
                "--dither-window", "6", "--bake-smoothing", "soft",
                "--reconstruction", "soft", "--keep"]
            with mock.patch.object(make_clip.encoder, "encode_video",
                                   return_value=info) as encode_video, \
                    mock.patch.object(make_clip.ascl_bundle, "pack",
                                      return_value=(300, 240, 60)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(make_clip.main(argv), 0)
            positional, keywords = encode_video.call_args
            self.assertEqual(positional[10], "adaptive")
            self.assertEqual(keywords["palette_algorithm"], "kmeans-oklab")
            self.assertEqual(keywords["adaptive_min_frames"], 4)
            self.assertEqual(keywords["adaptive_max_frames"], 18)
            self.assertAlmostEqual(keywords["adaptive_change_threshold"], 0.17)
            self.assertAlmostEqual(keywords["adaptive_hard_cut_threshold"], 0.61)
            self.assertAlmostEqual(keywords["adaptive_stability_max"], 0.19)
            self.assertEqual(keywords["perceptual_lut_bits"], 5)
            self.assertAlmostEqual(keywords["dither_budget"], 0.07)
            self.assertAlmostEqual(keywords["dither_min_improvement"], 0.11)
            self.assertEqual(keywords["dither_window"], 6)


if __name__ == "__main__":
    unittest.main()
