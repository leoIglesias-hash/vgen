#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7: panel canonico de 20 numeros (tools/make_panel.py).

El sidecar del panel se construye determinista desde la geometria del clip,
pasa entero el validador de E-07 (incluida la verificacion cruzada de
``reserved_rgb`` contra la paleta canonica) y rechaza grillas chicas.
"""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ascl_bundle  # noqa: E402
import make_panel  # noqa: E402
import make_slots  # noqa: E402
from overlay_palette import reserved_rgb_bytes  # noqa: E402

COLS, ROWS, FRAMES = 768, 432, 231


def glyph_table():
    area = make_panel.GLYPH_W * make_panel.GLYPH_H
    return bytes(bytearray(246 + (i % 10) for i in range(11 * area)))


class MakePanelTest(unittest.TestCase):
    def test_panel_is_deterministic_and_valid(self):
        table = glyph_table()
        first = make_panel.build_sidecar(COLS, ROWS, FRAMES, table)
        second = make_panel.build_sidecar(COLS, ROWS, FRAMES, table)
        self.assertEqual(first, second, "el panel debe ser determinista")
        parsed = make_slots.validate(first, COLS, ROWS, FRAMES,
                                     reserved_rgb_bytes())
        self.assertEqual(len(parsed["slots"]), 40)
        self.assertEqual(len(parsed["fields"]), 20)
        for index, field in enumerate(parsed["fields"]):
            self.assertEqual(field["field_id"], index + 1)
            self.assertEqual(field["slot_ids"], [index * 2, index * 2 + 1])
            self.assertEqual((field["min"], field["max"], field["pad"]),
                             (0, 99, 1))
        rows_y = sorted(set(slot["y"] for slot in parsed["slots"]))
        self.assertEqual(len(rows_y), 2, "dos filas de diez numeros")
        for slot in parsed["slots"]:
            self.assertEqual(slot["start"], 0)
            self.assertEqual(slot["end"], FRAMES - 1)
            self.assertEqual(slot["flags"], 1)

    def test_small_grids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no alcanza"):
            make_panel.build_sidecar(320, 180, 10, glyph_table())
        with self.assertRaisesRegex(ValueError, "no alcanza"):
            make_panel.build_sidecar(768, 30, 10, glyph_table())

    def test_clip_geometry_reads_the_bundle(self):
        header = struct.pack("<4sBBBBHHHIBBIHHI",
                             b"ASCL", 1, 3, 0, 15, COLS, ROWS, 256, FRAMES,
                             0, 3, 32, 500, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.asclv")
            ascl_bundle.pack_bytes(header, b"", path)
            self.assertEqual(make_panel.clip_geometry(path),
                             (COLS, ROWS, FRAMES))


if __name__ == "__main__":
    unittest.main()
