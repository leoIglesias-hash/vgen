#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-09 — tile_size parametrizado en el transcodificador v2 + barrido."""
import os
import struct
import sys
import unittest
import zlib

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_v2  # noqa: E402
from tests.test_ascl_v2 import delta_payload, make_block, make_v1  # noqa: E402


def build_source(cols=37, rows=29):
    """v1 sintetico con keyframe estructurado, delta chico y frame repetido."""
    n = cols * rows
    palette = bytes(value for i in range(16)
                    for value in (i * 16, (i * 7) & 255, 255 - i * 16))
    f0 = np.fromiter(((x // 6 + y // 4) & 7
                      for y in range(rows) for x in range(cols)),
                     dtype=np.uint8, count=n)
    f1 = f0.copy()
    changed = [0, 41, n - 1]
    values = [9, 10, 11]
    f1[changed] = values
    frames = [
        make_block(0, palette, f0.tobytes()),
        make_block(2, None, delta_payload(changed, values)),
        make_block(2, None, zlib.compress(b"", 9)),
    ]
    return make_v1(frames, cols, rows), [f0, f1, f1.copy()]


class TileSizeTranscodeTest(unittest.TestCase):
    def test_all_sweep_sizes_roundtrip_exact_and_stamp_header(self):
        source, expected = build_source()
        for tile_size in ascl_v2.SWEEP_TILE_SIZES:
            converted, stats = ascl_v2.transcode_ascl_bytes(
                source, tile_size=tile_size)
            self.assertEqual(stats["tile_size"], tile_size)
            header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
            self.assertEqual(header["reserved"] & 255, tile_size,
                             "byte 26 debe declarar el tile usado")
            self.assertEqual(header["reserved"] >> 8, 1)
            self.assertLessEqual(len(converted), len(source))
            for actual, cells in zip(frames, expected):
                np.testing.assert_array_equal(
                    actual["cells"].reshape(-1), cells)

    def test_out_of_range_tile_sizes_are_rejected(self):
        source, _expected = build_source()
        for tile_size in (0, 1, 3, 33, 255):
            with self.assertRaisesRegex(ValueError, "tile_size"):
                ascl_v2.transcode_ascl_bytes(source, tile_size=tile_size)

    def test_header_v2_rejects_tile_out_of_range(self):
        source, _expected = build_source()
        converted, _stats = ascl_v2.transcode_ascl_bytes(source, tile_size=8)
        for bad in (3, 33):
            corrupt = bytearray(converted)
            corrupt[26] = bad
            struct.pack_into("<I", corrupt, 28, 0)
            struct.pack_into("<I", corrupt, 28, ascl_v2._crc_v2(corrupt))
            with self.assertRaisesRegex(ValueError, "tile_size"):
                ascl_v2.decode_ascl_v2_bytes(bytes(corrupt))

    def test_sweep_returns_the_smallest_deterministically(self):
        source, expected = build_source()
        best, stats = ascl_v2.transcode_ascl_bytes_sweep(source)
        self.assertEqual(len(stats["sweep"]), len(ascl_v2.SWEEP_TILE_SIZES))
        sizes = [pair[0] for pair in stats["sweep"]]
        self.assertEqual(sizes, list(ascl_v2.SWEEP_TILE_SIZES))
        smallest = min(pair[1] for pair in stats["sweep"])
        self.assertEqual(len(best), smallest)
        winner_sizes = [pair[0] for pair in stats["sweep"]
                        if pair[1] == smallest]
        self.assertEqual(stats["tile_size"], winner_sizes[0],
                         "empate: gana el primer tile del barrido")
        again, again_stats = ascl_v2.transcode_ascl_bytes_sweep(source)
        self.assertEqual(best, again, "el barrido debe ser determinista")
        self.assertEqual(stats["sweep"], again_stats["sweep"])
        header, frames = ascl_v2.decode_ascl_v2_bytes(best)
        self.assertEqual(header["reserved"] & 255, stats["tile_size"])
        for actual, cells in zip(frames, expected):
            np.testing.assert_array_equal(actual["cells"].reshape(-1), cells)

    def test_sweep_rejects_empty_list(self):
        source, _expected = build_source()
        with self.assertRaisesRegex(ValueError, "barrido"):
            ascl_v2.transcode_ascl_bytes_sweep(source, tile_sizes=())


if __name__ == "__main__":
    unittest.main()
