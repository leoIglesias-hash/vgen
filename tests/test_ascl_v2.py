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

import ascl_bundle  # noqa: E402
import ascl_v2  # noqa: E402
import make_clip  # noqa: E402


def make_block(tag, palette, payload):
    palette = bytes(palette or b"")
    body = struct.pack("<BH", tag, len(palette) // 3) + palette + bytes(payload)
    return struct.pack("<I", len(body)) + body


def make_v1(frames, cols, rows, pal_size=16, flags=10):
    table_size = len(frames) * 4
    offset = 32 + table_size
    offsets = []
    for frame in frames:
        offsets.append(offset)
        offset += len(frame)
    body = struct.pack("<%dI" % len(frames), *offsets) + b"".join(frames)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    header = struct.pack(
        ascl_v2.HEADER_FMT, b"ASCL", 1, 3, flags, 15, cols, rows,
        pal_size, len(frames), 0, 3, 32, 1000, 0, crc)
    return header + body


def delta_payload(offsets, values):
    raw = struct.pack("<%dI" % len(offsets), *offsets) + bytes(values)
    return zlib.compress(raw, 9)


class ASCLV2TranscodeTest(unittest.TestCase):
    def setUp(self):
        self.cols, self.rows = 35, 19
        n = self.cols * self.rows
        self.palette = bytes(value for i in range(16)
                             for value in (i * 16, i * 16, i * 16))
        f0 = np.fromiter(((x // 8 + y // 5) & 3
                          for y in range(self.rows) for x in range(self.cols)),
                         dtype=np.uint8, count=n)
        f1 = f0.copy()
        changed = [0, 17, 331, n - 1]
        values = [7, 8, 9, 10]
        f1[changed] = values
        f2 = f1.copy()
        f3 = np.full(n, 12, dtype=np.uint8)
        self.expected = [f0, f1, f2, f3]
        self.source = make_v1([
            make_block(0, self.palette, f0.tobytes()),
            make_block(2, None, delta_payload(changed, values)),
            make_block(2, None, zlib.compress(b"", 9)),
            make_block(0, self.palette, f3.tobytes()),
        ], self.cols, self.rows)

    def test_transcode_is_exact_smaller_and_preserves_keyframes(self):
        converted, stats = ascl_v2.transcode_ascl_bytes(self.source)
        header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
        self.assertEqual(header["version"], 2)
        self.assertEqual(header["reserved"] & 255, 16)
        self.assertEqual(header["reserved"] >> 8, 1)
        self.assertLessEqual(len(converted), len(self.source))
        self.assertEqual(stats["saved_bytes"], len(self.source) - len(converted))
        self.assertGreater(stats["regional_frames"], 0)
        self.assertEqual([f["keyframe"] for f in frames],
                         [True, False, False, True])
        self.assertEqual([f["pal_count"] for f in frames], [16, 0, 0, 16])
        for actual, expected in zip(frames, self.expected):
            np.testing.assert_array_equal(actual["cells"].reshape(-1), expected)
            self.assertEqual(actual["palette"], self.palette)
        self.assertEqual(ascl_v2._crc_v2(converted), header["crc32"])

    def test_bundle_conversion_keeps_audio_byte_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "source.asclv")
            output_path = os.path.join(directory, "result.asclv")
            audio = bytes(range(251)) * 3
            ascl_bundle.pack_bytes(self.source, audio, source_path)
            stats = ascl_v2.transcode_path(source_path, output_path)
            video, restored_audio, version = ascl_bundle.read_parts_info(output_path)
            self.assertEqual(version, 2)
            self.assertEqual(restored_audio, audio)
            self.assertEqual(stats["bundle_bytes"], os.path.getsize(output_path))
            self.assertLessEqual(len(video), len(self.source))
            _, frames = ascl_v2.decode_ascl_v2_bytes(video)
            for actual, expected in zip(frames, self.expected):
                np.testing.assert_array_equal(actual["cells"].reshape(-1), expected)

    def test_rejects_crc_header_mutation_and_in_place_conversion(self):
        converted, _ = ascl_v2.transcode_ascl_bytes(self.source)
        corrupt = bytearray(converted)
        corrupt[26] = 8
        with self.assertRaisesRegex(ValueError, "tile_size"):
            ascl_v2.decode_ascl_v2_bytes(corrupt)
        corrupt = bytearray(converted)
        corrupt[8] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC32"):
            ascl_v2.decode_ascl_v2_bytes(corrupt)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "same.ascl")
            with open(path, "wb") as stream:
                stream.write(self.source)
            with self.assertRaisesRegex(ValueError, "sobrescribir"):
                ascl_v2.transcode_path(path, path)

    def test_rejects_reserved_or_conflicting_flags_before_transcoding(self):
        for flags in (0x28, 0x0E):  # reserved bit; scene+global simultaneos
            corrupt = bytearray(self.source)
            corrupt[6] = flags
            with self.assertRaises(ValueError):
                ascl_v2.transcode_ascl_bytes(corrupt)

    def test_enforces_global_scene_and_per_frame_palette_policies(self):
        n = self.cols * self.rows
        raw = bytes(n)
        two_keys = [
            make_block(0, self.palette, raw),
            make_block(0, self.palette, raw),
        ]
        with self.assertRaisesRegex(ValueError, "global reemitida"):
            ascl_v2.transcode_ascl_bytes(
                make_v1(two_keys, self.cols, self.rows, flags=12))

        missing_second_palette = [
            make_block(0, self.palette, raw),
            make_block(0, None, raw),
        ]
        with self.assertRaisesRegex(ValueError, "temporal sin paleta"):
            ascl_v2.transcode_ascl_bytes(
                make_v1(missing_second_palette, self.cols, self.rows, flags=10))
        with self.assertRaisesRegex(ValueError, "per-frame ausente"):
            ascl_v2.transcode_ascl_bytes(
                make_v1(missing_second_palette, self.cols, self.rows, flags=8))

    def test_rejects_invalid_delta_value_even_if_duplicate_overwrites_it(self):
        n = self.cols * self.rows
        source = make_v1([
            make_block(0, self.palette, bytes(n)),
            make_block(2, None, delta_payload([0, 0], [255, 1])),
        ], self.cols, self.rows)
        with self.assertRaisesRegex(ValueError, "indice de paleta fuera de rango"):
            ascl_v2.transcode_ascl_bytes(source)

    def test_rejects_dimensions_whose_decoder_bounds_exceed_tv_limit(self):
        source = make_v1(
            [make_block(0, self.palette, b"\x00")], 65535, 65535)
        with self.assertRaisesRegex(ValueError, "limite"):
            ascl_v2.transcode_ascl_bytes(source)

    def test_incompressible_key_keeps_smaller_v1_block(self):
        rng = np.random.RandomState(91)
        cols = rows = 32
        palette = bytes(component for value in range(256)
                        for component in (value, value, value))
        cells = rng.randint(0, 256, size=cols * rows).astype(np.uint8)
        source = make_v1(
            [make_block(0, palette, cells.tobytes())],
            cols, rows, pal_size=256, flags=12)
        converted, stats = ascl_v2.transcode_ascl_bytes(source)
        self.assertEqual(len(converted), len(source))
        self.assertEqual(stats["regional_frames"], 0)
        _header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
        self.assertEqual(frames[0]["tag"], ascl_v2.TAG_RAW)
        np.testing.assert_array_equal(frames[0]["cells"].reshape(-1), cells)

    def test_v2_crc_rejects_body_corruption_and_canonical_palette_policy(self):
        converted, _ = ascl_v2.transcode_ascl_bytes(self.source)
        corrupt = bytearray(converted)
        corrupt[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC32"):
            ascl_v2.decode_ascl_v2_bytes(corrupt)

        # Convertir el header temporal a global haria ilegal la segunda paleta.
        # Se recalcula CRC para probar la validacion semantica, no la checksum.
        corrupt = bytearray(converted)
        corrupt[6] = 12
        struct.pack_into("<I", corrupt, 28, 0)
        struct.pack_into("<I", corrupt, 28, ascl_v2._crc_v2(corrupt))
        with self.assertRaisesRegex(ValueError, "global v2 reemitida"):
            ascl_v2.decode_ascl_v2_bytes(corrupt)

    def test_make_clip_v2_uses_separate_source_and_final_ascl(self):
        info = {
            "mode": "pixel", "cols": 32, "rows": 18, "fps": 15,
            "n_frames": 2, "palette_mode": "global", "quality_profile": "custom",
            "pal_size": 16, "bake_smoothing": "none", "reconstruction": "nearest",
            "flags": 12, "palette_algorithm": "kmeans-rgb", "dither": "off",
            "dither_matrix": 4, "audio": None,
        }
        v2_stats = {
            "regional_frames": 1, "n_frames": 2, "saved_bytes": 50,
            "saved_percent": 5.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "clip.asclv")
            with mock.patch.object(make_clip.encoder, "encode_video",
                                   return_value=info) as encode_video, \
                    mock.patch.object(make_clip.ascl_v2, "transcode_path",
                                      return_value=v2_stats) as transcode, \
                    mock.patch.object(make_clip.ascl_bundle, "pack",
                                      return_value=(1000, 900, 100)) as pack, \
                    contextlib.redirect_stdout(io.StringIO()):
                result = make_clip.main([
                    "synthetic.mp4", "--out", output, "--format", "v2", "--keep"])
            self.assertEqual(result, 0)
            source_path = encode_video.call_args[0][1]
            self.assertTrue(source_path.endswith(".source-v1.ascl"))
            final_path = os.path.splitext(output)[0] + ".ascl"
            transcode.assert_called_once_with(source_path, final_path)
            self.assertEqual(pack.call_args[0][0], final_path)


if __name__ == "__main__":
    unittest.main()
