import os
import struct
import sys
import unittest
import zlib

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import regional_codec_v2 as codec  # noqa: E402


class RegionalCodecV2Test(unittest.TestCase):
    def roundtrip(self, current, previous=None, tile_size=16):
        encoded = codec.encode_payload(current, previous, tile_size=tile_size)
        decoded = codec.decode_payload(
            encoded.payload, current.shape[0], current.shape[1], tile_size,
            encoded.keyframe, previous, compressed=encoded.compressed)
        self.assertTrue(np.array_equal(current, decoded.matrix))
        self.assertEqual(encoded.dirty_tiles, decoded.dirty_tiles)
        self.assertEqual(encoded.command_counts, decoded.command_counts)
        return encoded, decoded

    def test_keyframe_and_delta_roundtrip_with_edge_tiles(self):
        rng = np.random.RandomState(812)
        previous = rng.randint(0, 256, size=(19, 35)).astype(np.uint8)
        current = previous.copy()
        current[0, 0] ^= 0x55
        current[2:14, 17:31] = 7
        current[18, 34] = 222
        key, _ = self.roundtrip(current, tile_size=16)
        delta, _ = self.roundtrip(current, previous, tile_size=16)
        self.assertTrue(key.keyframe)
        self.assertFalse(delta.keyframe)
        self.assertEqual(key.dirty_tiles, tuple(range(6)))
        self.assertEqual(delta.dirty_tiles, (0, 1, 5))

    def test_repeat_is_explicit_single_skip_run(self):
        frame = np.arange(17 * 33, dtype=np.uint16).astype(np.uint8).reshape(17, 33)
        encoded, decoded = self.roundtrip(frame, frame.copy(), tile_size=16)
        self.assertEqual(encoded.raw_payload, b"\x00\x06")
        self.assertTrue(encoded.repeat)
        self.assertTrue(decoded.repeat)
        self.assertEqual(encoded.dirty_tiles, ())
        self.assertEqual(encoded.ascl_tag,
                         codec.TAG_REGIONAL_DELTA_RAW)

    def test_skip_runs_cover_unchanged_tiles_at_both_ends(self):
        previous = np.zeros((16, 48), dtype=np.uint8)
        current = previous.copy()
        current[:, 16:32] = 9
        encoded, _ = self.roundtrip(current, previous)
        self.assertEqual(encoded.raw_payload,
                         b"\x00\x01\x01\x09\x00\x01")
        self.assertEqual(encoded.command_counts,
                         (("SKIP_RUN", 2), ("SOLID", 1)))
        self.assertEqual(encoded.dirty_tiles, (1,))

    def test_dense_mode_selection_is_by_materialized_binary_length(self):
        solid = np.full((16, 16), 19, dtype=np.uint8)
        pack1 = (np.indices((16, 16)).sum(axis=0) & 1).astype(np.uint8)
        pack2 = (np.arange(256, dtype=np.uint8).reshape(16, 16) & 3)
        pal4 = (np.arange(256, dtype=np.uint8).reshape(16, 16) & 15)
        pal8 = np.arange(256, dtype=np.uint8).reshape(16, 16)
        cases = [
            (solid, codec.OP_SOLID, 2),
            (pack1, codec.OP_PACK1, 35),
            (pack2, codec.OP_PACK2, 70),
            (pal4, codec.OP_PAL4, 146),
            (pal8, codec.OP_PAL8, 257),
        ]
        for matrix, opcode, expected_length in cases:
            encoded, _ = self.roundtrip(matrix)
            self.assertEqual(encoded.raw_payload[0], opcode)
            self.assertEqual(len(encoded.raw_payload), expected_length)

    def test_sparse_and_mask_are_selected_from_exact_delta_bytes(self):
        rng = np.random.RandomState(33)
        previous = rng.randint(0, 256, size=(16, 16)).astype(np.uint8)

        sparse = previous.copy()
        sparse[0, 1] ^= 0xFF
        sparse_encoded, _ = self.roundtrip(sparse, previous)
        self.assertEqual(sparse_encoded.raw_payload[0], codec.OP_SPARSE)
        self.assertEqual(len(sparse_encoded.raw_payload), 4)

        masked = previous.copy()
        # Offsets altos hacen que SPARSE pague uvarints de dos bytes. MASK gana.
        flat = masked.reshape(-1)
        for offset in range(180, 220):
            flat[offset] ^= 0x80
        mask_encoded, _ = self.roundtrip(masked, previous)
        self.assertEqual(mask_encoded.raw_payload[0], codec.OP_MASK)
        self.assertEqual(len(mask_encoded.raw_payload), 1 + 32 + 40)

    def test_raw_and_zlib_payloads_are_both_decodable(self):
        frame = np.tile(np.arange(16, dtype=np.uint8), (64, 1))
        encoded = codec.encode_payload(frame, tile_size=16)
        self.assertLess(len(encoded.zlib_payload), len(encoded.raw_payload))
        self.assertTrue(encoded.compressed)
        self.assertEqual(encoded.ascl_tag, codec.TAG_REGIONAL_KEY_ZLIB)
        for payload, compressed in ((encoded.raw_payload, False),
                                    (encoded.zlib_payload, True)):
            decoded = codec.decode_payload(payload, 64, 16, 16, True,
                                           compressed=compressed)
            self.assertTrue(np.array_equal(frame, decoded.matrix))

    def test_laboratory_packet_roundtrip_raw_and_zlib(self):
        rng = np.random.RandomState(2)
        noisy = rng.randint(0, 256, size=(16, 16)).astype(np.uint8)
        compressible = np.tile(np.arange(16, dtype=np.uint8), (64, 1))
        for matrix in (noisy, compressible):
            packet = codec.encode_frame(matrix)
            decoded = codec.decode_frame(packet)
            self.assertTrue(np.array_equal(matrix, decoded.matrix))
            self.assertEqual(packet[:4], codec.PACKET_MAGIC)

    def test_random_sequences_are_exact_and_deterministic(self):
        rng = np.random.RandomState(20260814)
        for rows, cols, tile_size in ((1, 1, 1), (7, 9, 2),
                                      (17, 31, 7), (35, 19, 16),
                                      (12, 13, 32)):
            previous = rng.randint(0, 256, size=(rows, cols)).astype(np.uint8)
            self.roundtrip(previous, tile_size=tile_size)
            for _ in range(12):
                current = previous.copy()
                count = int(rng.randint(0, rows * cols + 1))
                offsets = rng.choice(rows * cols, count, replace=False)
                current.reshape(-1)[offsets] = rng.randint(
                    0, 256, size=count).astype(np.uint8)
                first = codec.encode_payload(current, previous, tile_size)
                second = codec.encode_payload(current, previous, tile_size)
                self.assertEqual(first.raw_payload, second.raw_payload)
                self.assertEqual(first.zlib_payload, second.zlib_payload)
                self.roundtrip(current, previous, tile_size)
                previous = current

    def test_decoder_never_mutates_previous_on_success_or_failure(self):
        previous = np.arange(256, dtype=np.uint8).reshape(16, 16)
        snapshot = previous.copy()
        current = previous.copy()
        current[3, 7] = 200
        encoded = codec.encode_payload(current, previous)
        codec.decode_payload(encoded.raw_payload, 16, 16, 16, False, previous)
        self.assertTrue(np.array_equal(previous, snapshot))
        with self.assertRaises(codec.RegionalCodecError):
            codec.decode_payload(encoded.raw_payload + b"\xff", 16, 16, 16,
                                 False, previous)
        self.assertTrue(np.array_equal(previous, snapshot))

    def test_rejects_missing_state_truncation_trailing_and_bad_coverage(self):
        previous = np.zeros((16, 32), dtype=np.uint8)
        invalid = [
            b"",
            b"\x00",              # run truncada
            b"\x00\x01",          # falta cubrir segundo tile
            b"\x00\x03",          # run excede tiles
            b"\x00\x02\xff",      # trailing byte
            b"\xff",              # opcode desconocido
        ]
        for payload in invalid:
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_payload(payload, 16, 32, 16, False, previous)
        with self.assertRaises(codec.RegionalCodecError):
            codec.decode_payload(b"\x00\x02", 16, 32, 16, False)
        with self.assertRaises(codec.RegionalCodecError):
            codec.decode_payload(b"\x00\x02", 16, 32, 16, True)

    def test_rejects_noncanonical_sparse_mask_and_packed_payloads(self):
        previous = np.zeros((2, 2), dtype=np.uint8)
        invalid_delta = [
            b"\x02\x02\x01\x05\x01\x06",  # offset duplicado
            b"\x02\x01\x04\x05",          # offset fuera del tile
            b"\x02\x01\x01\x00",          # cambio nulo
            b"\x03\x00",                    # mascara vacia
            b"\x03\xf0\x01\x02\x03\x04", # padding no nulo
            b"\x03\x01\x00",                # valor MASK sin cambio
        ]
        for payload in invalid_delta:
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_payload(payload, 2, 2, 2, False, previous)

        invalid_key = [
            b"\x04\x09\x09\x00",             # paleta no creciente
            b"\x04\x00\x01\xf0",             # padding PACK1 no nulo
            b"\x05\x02\x00\x01\x00",         # PACK2 exige 3..4
            b"\x05\x03\x00\x01\x02\xff",     # indice local 3 invalido
            b"\x06\x04\x00\x01\x02\x03\x00\x00",  # PAL4 exige 5..16
        ]
        for payload in invalid_key:
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_payload(payload, 2, 2, 2, True)

    def test_active_palette_rejects_even_unused_local_map_entries(self):
        # Una celda usa el codigo local 0; la entrada 250 queda sin usar, pero
        # sigue siendo un indice declarado de la paleta RGB activa y es invalida.
        payload = bytes((codec.OP_PACK1, 0, 250, 0))
        with self.assertRaisesRegex(codec.RegionalCodecError,
                                    "fuera de paleta activa"):
            codec.decode_payload(payload, 1, 1, 1, True,
                                 palette_entries=2)

        for invalid_count in (0, 257, True):
            with self.assertRaisesRegex(codec.RegionalCodecError,
                                        "cantidad de paleta activa"):
                codec.decode_payload(bytes((codec.OP_SOLID, 0)), 1, 1, 1,
                                     True, palette_entries=invalid_count)

    def test_rejects_noncanonical_and_overflowing_uvarints(self):
        previous = np.zeros((1, 1), dtype=np.uint8)
        for payload in (b"\x00\x81\x00", b"\x00\x80\x80\x80\x80\x10",
                        b"\x00\x80\x80\x80\x80\x80\x00"):
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_payload(payload, 1, 1, 1, False, previous)

    def test_zlib_is_bounded_and_rejects_extra_or_truncated_streams(self):
        previous = np.zeros((1, 1), dtype=np.uint8)
        bomb = zlib.compress(b"\x00" * 1000)
        bad = [bomb, zlib.compress(b"\x00\x01") + b"extra",
               zlib.compress(b"\x00\x01")[:-1]]
        for payload in bad:
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_payload(payload, 1, 1, 1, False, previous,
                                     compressed=True)

    def test_packet_detects_header_length_crc_and_payload_corruption(self):
        matrix = np.arange(256, dtype=np.uint8).reshape(16, 16)
        packet = codec.encode_frame(matrix)
        corruptions = []
        changed_magic = bytearray(packet)
        changed_magic[0] ^= 1
        corruptions.append(bytes(changed_magic))
        corruptions.append(packet[:-1])
        changed_crc = bytearray(packet)
        changed_crc[codec.PACKET_HEADER.size - 1] ^= 1
        corruptions.append(bytes(changed_crc))
        changed_payload = bytearray(packet)
        changed_payload[-1] ^= 1
        corruptions.append(bytes(changed_payload))
        for corrupted in corruptions:
            with self.assertRaises(codec.RegionalCodecError):
                codec.decode_frame(corrupted)

    def test_invalid_inputs_are_rejected_instead_of_silently_converted(self):
        with self.assertRaises(TypeError):
            codec.encode_payload([[1, 2], [3, 4]])
        with self.assertRaises(TypeError):
            codec.encode_payload(np.zeros((2, 2), dtype=np.uint16))
        with self.assertRaises(ValueError):
            codec.encode_payload(np.zeros((2, 2), dtype=np.uint8),
                                 np.zeros((3, 2), dtype=np.uint8))
        with self.assertRaises(codec.RegionalCodecError):
            codec.decode_payload(b"\x01\x00", 2, 2, 0, True)


if __name__ == "__main__":
    unittest.main()
