import contextlib
import io
import os
import sys
import unittest
import zlib
from unittest import mock

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_v2  # noqa: E402
from tests.test_ascl_v2 import delta_payload, make_block, make_v1  # noqa: E402


class PredictorTransformV2Test(unittest.TestCase):
    @staticmethod
    def _payload(current, predictor, previous=None):
        residual = ascl_v2._predict_residual(current, predictor, previous)
        return bytes((predictor,)) + zlib.compress(residual.tobytes(), 9)

    def test_left_top_and_gradient_roundtrip_edges_and_wraparound(self):
        shapes = ((1, 1), (1, 17), (19, 1), (7, 11))
        predictors = (ascl_v2.PRED_LEFT, ascl_v2.PRED_TOP,
                      ascl_v2.PRED_GRADIENT)
        for rows, cols in shapes:
            y, x = np.indices((rows, cols))
            current = ((x * 193 + y * 241 + x * y * 37 + 250) & 255).astype(
                np.uint8)
            original = current.copy()
            for predictor in predictors:
                payload = self._payload(current, predictor)
                decoded = ascl_v2.decode_predictor_payload(
                    payload, rows, cols, keyframe=True)
                np.testing.assert_array_equal(decoded, current)
                np.testing.assert_array_equal(current, original)

    def test_previous_sub_and_xor_roundtrip_without_mutating_previous(self):
        rng = np.random.RandomState(221)
        for rows, cols in ((1, 1), (1, 23), (17, 1), (13, 21)):
            previous = rng.randint(0, 256, size=(rows, cols)).astype(np.uint8)
            current = rng.randint(0, 256, size=(rows, cols)).astype(np.uint8)
            before = previous.copy()
            for predictor in (ascl_v2.PRED_PREVIOUS_SUB,
                              ascl_v2.PRED_PREVIOUS_XOR):
                payload = self._payload(current, predictor, previous)
                decoded = ascl_v2.decode_predictor_payload(
                    payload, rows, cols, keyframe=False, previous=previous)
                np.testing.assert_array_equal(decoded, current)
                np.testing.assert_array_equal(previous, before)

    def test_encoder_selects_only_the_exact_shortest_payload(self):
        rows, cols = 32, 33
        y, x = np.indices((rows, cols))
        plane = ((x + 3 * y) % 251).astype(np.uint8)
        tag, payload, predictor = ascl_v2.encode_predictor_payload(
            plane, keyframe=True)
        self.assertEqual(tag, ascl_v2.TAG_PREDICT_KEY_ZLIB)
        self.assertEqual(predictor, ascl_v2.PRED_GRADIENT)
        self.assertEqual(payload[0], predictor)
        np.testing.assert_array_equal(
            ascl_v2.decode_predictor_payload(payload, rows, cols, True), plane)

        rng = np.random.RandomState(222)
        previous = rng.randint(0, 256, size=(rows, cols)).astype(np.uint8)
        for expected, current in (
                (ascl_v2.PRED_PREVIOUS_SUB,
                 np.add(previous, 1, dtype=np.uint8)),
                (ascl_v2.PRED_PREVIOUS_XOR,
                 np.bitwise_xor(previous, 0x55))):
            tag, payload, predictor = ascl_v2.encode_predictor_payload(
                current, keyframe=False, previous=previous)
            self.assertEqual(tag, ascl_v2.TAG_PREDICT_DELTA_ZLIB)
            self.assertEqual(predictor, expected)
            np.testing.assert_array_equal(
                ascl_v2.decode_predictor_payload(
                    payload, rows, cols, False, previous), current)

    def test_rejects_invalid_dimensions_predictor_ids_and_zlib_streams(self):
        valid_raw = bytes(6)
        valid_zlib = zlib.compress(valid_raw, 9)
        valid_payload = bytes((ascl_v2.PRED_LEFT,)) + valid_zlib
        for rows, cols in ((0, 6), (2, 0), (True, 6), (2.0, 3)):
            with self.assertRaisesRegex(ValueError, "dimensiones"):
                ascl_v2.decode_predictor_payload(
                    valid_payload, rows, cols, keyframe=True)
        oversized = ascl_v2.MAX_DECODE_BYTES // 5 + 1
        with self.assertRaisesRegex(ValueError, "limite PREDICT"):
            ascl_v2.decode_predictor_payload(
                valid_payload, 1, oversized, keyframe=True)
        for invalid in (bytes(6), np.zeros((2, 3), dtype=np.int16)):
            with self.assertRaisesRegex(ValueError, "numpy.ndarray|dtype uint8"):
                ascl_v2.encode_predictor_payload(invalid, keyframe=True)
        with self.assertRaisesRegex(ValueError, "desconocido"):
            ascl_v2._predict_residual(np.zeros((2, 3), np.uint8), 255)

        for payload in (b"", b"\x00"):
            with self.assertRaisesRegex(ValueError, "truncado"):
                ascl_v2.decode_predictor_payload(payload, 2, 3, True)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            ascl_v2.decode_predictor_payload(
                bytes((ascl_v2.PRED_PREVIOUS_SUB,)) + valid_zlib,
                2, 3, keyframe=True)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            ascl_v2.decode_predictor_payload(
                bytes((ascl_v2.PRED_LEFT,)) + valid_zlib,
                2, 3, keyframe=False, previous=np.zeros((2, 3), np.uint8))
        with self.assertRaisesRegex(ValueError, "zlib invalido"):
            ascl_v2.decode_predictor_payload(b"\x00no-es-zlib", 2, 3, True)
        with self.assertRaisesRegex(ValueError, "longitud"):
            ascl_v2.decode_predictor_payload(
                b"\x00" + zlib.compress(bytes(5)), 2, 3, True)
        with self.assertRaisesRegex(ValueError, "excede"):
            ascl_v2.decode_predictor_payload(
                b"\x00" + zlib.compress(bytes(7)), 2, 3, True)
        with self.assertRaisesRegex(ValueError, "truncado"):
            ascl_v2.decode_predictor_payload(
                b"\x00" + valid_zlib[:-1], 2, 3, True)
        for suffix in (b"basura", zlib.compress(b"otro-stream")):
            with self.assertRaisesRegex(ValueError, "stream extra"):
                ascl_v2.decode_predictor_payload(
                    b"\x00" + valid_zlib + suffix, 2, 3, True)

    def test_temporal_shape_error_is_transactional(self):
        previous = np.arange(6, dtype=np.uint8).reshape(2, 3)
        before = previous.copy()
        payload = (bytes((ascl_v2.PRED_PREVIOUS_SUB,)) +
                   zlib.compress(bytes(6), 9))
        with self.assertRaisesRegex(ValueError, "previous HxW compatible"):
            ascl_v2.decode_predictor_payload(
                payload, 3, 2, keyframe=False, previous=previous)
        np.testing.assert_array_equal(previous, before)


class PredictorIntegrationV2Test(unittest.TestCase):
    def test_transcode_uses_key_and_delta_predictors_preserving_palette(self):
        rows = cols = 32
        n = rows * cols
        y, x = np.indices((rows, cols))
        first = ((x + 3 * y) % 251).astype(np.uint8).reshape(-1)
        second = ((first.astype(np.uint16) + 1) % 251).astype(np.uint8)
        palette = bytes(component for value in range(256)
                        for component in (value, value, value))
        source = make_v1([
            make_block(ascl_v2.TAG_RAW, palette, first.tobytes()),
            make_block(ascl_v2.TAG_DELTA, None,
                       delta_payload(range(n), second.tolist())),
        ], cols, rows, pal_size=256, flags=12)

        converted, stats = ascl_v2.transcode_ascl_bytes(source)
        _header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
        self.assertLess(len(converted), len(source))
        self.assertEqual(stats["saved_bytes"], len(source) - len(converted))
        self.assertEqual(stats["regional_frames"], 0)
        self.assertEqual(stats["predictor_frames"], 2)
        self.assertEqual(stats["output_tags"][ascl_v2.TAG_PREDICT_KEY_ZLIB], 1)
        self.assertEqual(stats["output_tags"][ascl_v2.TAG_PREDICT_DELTA_ZLIB], 1)
        self.assertEqual([frame["tag"] for frame in frames], [
            ascl_v2.TAG_PREDICT_KEY_ZLIB,
            ascl_v2.TAG_PREDICT_DELTA_ZLIB,
        ])
        self.assertEqual([frame["keyframe"] for frame in frames], [True, False])
        self.assertEqual([frame["pal_count"] for frame in frames], [256, 0])
        self.assertEqual([frame["palette"] for frame in frames],
                         [palette, palette])
        np.testing.assert_array_equal(frames[0]["cells"].reshape(-1), first)
        np.testing.assert_array_equal(frames[1]["cells"].reshape(-1), second)

    def test_incompressible_frame_keeps_v1_payload_and_never_grows(self):
        rng = np.random.RandomState(223)
        rows = cols = 32
        cells = rng.randint(0, 256, size=rows * cols).astype(np.uint8)
        palette = bytes(component for value in range(256)
                        for component in (value, value, value))
        source = make_v1([
            make_block(ascl_v2.TAG_RAW, palette, cells.tobytes()),
        ], cols, rows, pal_size=256, flags=12)
        converted, stats = ascl_v2.transcode_ascl_bytes(source)
        _header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
        self.assertEqual(len(converted), len(source))
        self.assertEqual(stats["predictor_frames"], 0)
        self.assertEqual(frames[0]["tag"], ascl_v2.TAG_RAW)
        np.testing.assert_array_equal(frames[0]["cells"].reshape(-1), cells)

    def test_full_decoder_rejects_predictor_result_outside_active_palette(self):
        rows, cols = 2, 3
        palette = bytes(component for value in range(4)
                        for component in (value * 40,) * 3)
        source = make_v1([
            make_block(ascl_v2.TAG_RAW, palette, bytes(rows * cols)),
        ], cols, rows, pal_size=4, flags=12)
        header = ascl_v2._header_fields(source, ascl_v2.VERSION_V1)
        bad_residual = bytes((255, 0, 0, 0, 0, 0))
        payload = (bytes((ascl_v2.PRED_LEFT,)) +
                   zlib.compress(bad_residual, 9))
        converted = ascl_v2._build_v2(header, [{
            "tag": ascl_v2.TAG_PREDICT_KEY_ZLIB,
            "pal_count": 4,
            "palette": palette,
            "payload": payload,
        }], ascl_v2.DEFAULT_TILE_SIZE, ascl_v2.CODEC_FLAG_REGIONAL)
        with self.assertRaisesRegex(ValueError, "fuera de paleta"):
            ascl_v2.decode_ascl_v2_bytes(converted)

    def test_cli_reports_predictor_and_regional_counts_separately(self):
        stats = {
            "regional_frames": 3,
            "predictor_frames": 4,
            "n_frames": 10,
            "input_bytes": 1000,
            "output_bytes": 800,
            "saved_percent": 20.0,
            "bundle": False,
        }
        output = io.StringIO()
        with mock.patch.object(ascl_v2, "transcode_path", return_value=stats), \
                contextlib.redirect_stdout(output):
            self.assertEqual(ascl_v2.main(["in.ascl", "out.ascl"]), 0)
        self.assertIn("3 regionales + 4 predictores de 10 frames", output.getvalue())


if __name__ == "__main__":
    unittest.main()
