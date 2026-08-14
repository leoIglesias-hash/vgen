import os
import struct
import sys
import tempfile
import unittest
import zlib

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_bundle  # noqa: E402
import ascl_decode  # noqa: E402
import ascl_v2  # noqa: E402
import benchmark_quality_v1 as benchmark  # noqa: E402


def _block(tag, palette, payload):
    palette = bytes(palette or b"")
    body = struct.pack("<BH", tag, len(palette) // 3) + palette + bytes(payload)
    return struct.pack("<I", len(body)) + body


def tiny_v1_and_expected():
    cols = rows = 16
    count = cols * rows
    palette = bytes((0, 0, 0, 255, 255, 255))
    frame0 = np.zeros(count, dtype=np.uint8)
    frame1 = frame0.copy()
    frame1[17] = 1
    delta_raw = struct.pack("<I", 17) + bytes((1,))
    blocks = [
        _block(ascl_decode.TAG_RAW, palette, frame0.tobytes()),
        _block(ascl_decode.TAG_DELTA, None, zlib.compress(delta_raw, 9)),
    ]
    offset0 = ascl_decode.HEADER_SIZE + 2 * 4
    offset1 = offset0 + len(blocks[0])
    body = struct.pack("<2I", offset0, offset1) + b"".join(blocks)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    header = struct.pack(
        ascl_decode.HEADER_FMT,
        b"ASCL", 1, ascl_decode.MODE_PIXEL, 10, 15,
        cols, rows, 2, 2, 0, ascl_decode.MODE_PIXEL,
        ascl_decode.HEADER_SIZE, 1000, 0, crc)
    return header + body, (frame0, frame1), palette


def predictor_v2_and_expected():
    rows = cols = 32
    count = rows * cols
    y, x = np.indices((rows, cols))
    frame0 = ((x + 3 * y) % 251).astype(np.uint8).reshape(-1)
    frame1 = ((frame0.astype(np.uint16) + 1) % 251).astype(np.uint8)
    palette = bytes(component for value in range(256)
                    for component in (value, value, value))
    delta_raw = (struct.pack("<%dI" % count, *range(count)) +
                 frame1.tobytes())
    blocks = [
        _block(ascl_decode.TAG_RAW, palette, frame0.tobytes()),
        _block(ascl_decode.TAG_DELTA, None, zlib.compress(delta_raw, 9)),
    ]
    offset0 = ascl_decode.HEADER_SIZE + 2 * 4
    offset1 = offset0 + len(blocks[0])
    body = struct.pack("<2I", offset0, offset1) + b"".join(blocks)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    header = struct.pack(
        ascl_decode.HEADER_FMT,
        b"ASCL", 1, ascl_decode.MODE_PIXEL, 12, 15,
        cols, rows, 256, 2, 0, ascl_decode.MODE_PIXEL,
        ascl_decode.HEADER_SIZE, 1000, 0, crc)
    converted, stats = ascl_v2.transcode_ascl_bytes(header + body)
    return converted, (frame0, frame1), stats


class OfflineToolsV2Test(unittest.TestCase):
    def setUp(self):
        self.v1, self.expected, self.palette = tiny_v1_and_expected()
        self.v2, self.stats = ascl_v2.transcode_ascl_bytes(self.v1)

    def test_decode_all_dispatches_v1_and_v2_with_identical_public_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, data in (("source.ascl", self.v1), ("converted.ascl", self.v2)):
                path = os.path.join(directory, name)
                with open(path, "wb") as stream:
                    stream.write(data)
                paths.append(path)
            decoded_v1 = ascl_decode.decode_all(paths[0])
            decoded_v2 = ascl_decode.decode_all(paths[1])

        self.assertEqual(decoded_v1[0]["version"], 1)
        self.assertEqual(decoded_v2[0]["version"], 2)
        self.assertTrue(decoded_v1[0]["crc_ok"])
        self.assertTrue(decoded_v2[0]["crc_ok"])
        self.assertEqual(decoded_v2[0]["tile_size"], 16)
        self.assertEqual(decoded_v2[0]["codec_flags"], 1)
        self.assertEqual(decoded_v2[1], "")
        for index, expected in enumerate(self.expected):
            self.assertEqual(decoded_v2[2][index].shape, (256, 1))
            np.testing.assert_array_equal(decoded_v1[2][index], decoded_v2[2][index])
            np.testing.assert_array_equal(decoded_v2[2][index][:, 0], expected)
            np.testing.assert_array_equal(
                decoded_v2[3][index].reshape(-1),
                np.frombuffer(self.palette, dtype=np.uint8))

    def test_benchmark_loads_asclvid2_and_reports_exact_regional_changes(self):
        audio = b"audio-byte-exact"
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.asclv")
            ascl_bundle.pack_bytes(self.v2, audio, path)
            loaded = benchmark.load_artifact(path)
            result = benchmark.benchmark_artifact(
                "v2", path, sample_count=0, decode_repeats=0)

        self.assertEqual(loaded["kind"], "asclv")
        self.assertEqual(loaded["ascl_version"], 2)
        self.assertEqual(loaded["bundle_version"], 2)
        self.assertEqual(loaded["ascl_bytes_data"], self.v2)
        self.assertEqual(loaded["audio_bytes_data"], audio)
        self.assertEqual(result["ascl_version"], 2)
        self.assertEqual(result["bundle_version"], 2)
        structure = result["structure"]
        self.assertTrue(structure["crc"]["ok"])
        self.assertEqual(structure["crc"]["scope"],
                         "header_without_crc+body")
        self.assertEqual(structure["keyframes"], 1)
        self.assertEqual(structure["max_delta_chain"], 1)
        self.assertEqual(structure["mean_changed_cells"], 128.5)
        self.assertEqual(sum(structure["tags"].values()), 2)
        self.assertEqual(
            structure["tags"]["REGIONAL_KEY_RAW"] +
            structure["tags"]["REGIONAL_KEY_ZLIB"], 1)
        self.assertEqual(
            structure["tags"]["REGIONAL_DELTA_RAW"] +
            structure["tags"]["REGIONAL_DELTA_ZLIB"], 1)

    def test_decoder_and_benchmark_support_predictor_tags_8_and_9(self):
        converted, expected, stats = predictor_v2_and_expected()
        self.assertEqual(stats["predictor_frames"], 2)
        self.assertEqual(ascl_decode.TAG_LABEL[8], "PREDICT_KEY_ZLIB")
        self.assertEqual(ascl_decode.TAG_LABEL[9], "PREDICT_DELTA_ZLIB")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "predictors.ascl")
            with open(path, "wb") as stream:
                stream.write(converted)
            decoded = ascl_decode.decode_all(path)
            result = benchmark.benchmark_artifact(
                "predictors", path, sample_count=0, decode_repeats=0)

        self.assertTrue(decoded[0]["crc_ok"])
        for index, frame in enumerate(expected):
            np.testing.assert_array_equal(decoded[2][index][:, 0], frame)

        structure = result["structure"]
        self.assertEqual(structure["tags"]["PREDICT_KEY_ZLIB"], 1)
        self.assertEqual(structure["tags"]["PREDICT_DELTA_ZLIB"], 1)
        self.assertEqual(structure["keyframes"], 1)
        self.assertEqual(structure["max_delta_chain"], 1)
        self.assertEqual(structure["mean_changed_cells"], 1024.0)
        self.assertEqual(structure["max_inflate_bytes"], 1024)
        report = benchmark.markdown_report({"artifacts": [result]})
        self.assertIn("Tags predictor Kz/Dz", report)
        self.assertIn("| 1/1 |", report)


if __name__ == "__main__":
    unittest.main()
