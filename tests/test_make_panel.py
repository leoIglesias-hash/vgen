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
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ascl_bundle  # noqa: E402
import ascl_decode  # noqa: E402
import dither as selective_dither  # noqa: E402
import encoder  # noqa: E402
import make_panel  # noqa: E402
import make_slots  # noqa: E402
import overlay_panel  # noqa: E402
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

    def test_panel_rects_match_the_sidecar(self):
        rects = overlay_panel.panel_rects(COLS, ROWS)
        parsed = make_slots.validate(
            make_panel.build_sidecar(COLS, ROWS, FRAMES, glyph_table()),
            COLS, ROWS, FRAMES, reserved_rgb_bytes())
        self.assertEqual(len(rects), len(parsed["slots"]))
        for rect, slot in zip(rects, parsed["slots"]):
            self.assertEqual((rect[0], rect[1]), (slot["x"], slot["y"]))
            self.assertEqual((rect[2], rect[3]),
                             (make_panel.GLYPH_W, make_panel.GLYPH_H))

    def test_clip_geometry_reads_the_bundle(self):
        header = struct.pack("<4sBBBBHHHIBBIHHI",
                             b"ASCL", 1, 3, 0, 15, COLS, ROWS, 256, FRAMES,
                             0, 3, 32, 500, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.asclv")
            ascl_bundle.pack_bytes(header, b"", path)
            self.assertEqual(make_panel.clip_geometry(path),
                             (COLS, ROWS, FRAMES))


class PanelDitherProtectionTest(unittest.TestCase):
    """INT-001 §11/§13: el dither no toca celdas dentro de un rect de slot."""

    D_COLS, D_ROWS = 400, 120

    def _frames(self, count):
        frames = []
        yy, xx = np.indices((self.D_ROWS, self.D_COLS))
        for index in range(count):
            values = np.empty((self.D_ROWS, self.D_COLS, 3), dtype=np.int32)
            values[:, :, 0] = (xx * 255) // (self.D_COLS - 1)
            values[:, :, 1] = (yy * 255) // (self.D_ROWS - 1)
            values[:, :, 2] = ((xx + yy + index * 9) * 255) // \
                (self.D_COLS + self.D_ROWS - 2)
            rgb = np.clip(values, 0, 255).astype(np.uint8)
            x = rgb.astype(np.uint16)
            gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
                     29 * x[:, :, 2]) >> 8).astype(np.uint8)
            frames.append((rgb, gray))
        return frames

    def _encode(self, path, frames, **options):
        def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
            return iter(frames)

        defaults = dict(
            mode_name="pixel", cols=self.D_COLS, rows=self.D_ROWS, fps=5,
            pal_size=8, ramp_name="short", char_aspect=0.5, compress="auto",
            palette_mode="global", keyint=2, with_audio=False,
            palette_algorithm="fast-octree")
        defaults.update(options)
        with mock.patch.object(encoder, "probe_size",
                               return_value=(self.D_COLS, self.D_ROWS)), \
                mock.patch.object(encoder, "iter_video_frames",
                                  side_effect=fake_iter):
            encoder.encode_video("synthetic.mp4", path, **defaults)
        _hdr, _ramp, cells_list, _pal = ascl_decode.decode_all(path)
        return [np.asarray(cells, np.uint8).reshape(-1)
                for cells in cells_list]

    def _panel_mask(self):
        mask = np.zeros(self.D_COLS * self.D_ROWS, dtype=bool)
        for x, y, w, h in overlay_panel.panel_rects(self.D_COLS, self.D_ROWS):
            for gy in range(h):
                row = (y + gy) * self.D_COLS + x
                mask[row:row + w] = True
        return mask

    def test_protect_panel_keeps_q0_inside_the_rects(self):
        frames = self._frames(3)
        mask = self._panel_mask()
        with tempfile.TemporaryDirectory() as directory:
            off = self._encode(os.path.join(directory, "off.ascl"), frames,
                               dither_mode="off")
            protected = self._encode(
                os.path.join(directory, "prot.ascl"), frames,
                dither_mode="selective", protect_panel=True)
            unprotected = self._encode(
                os.path.join(directory, "libre.ascl"), frames,
                dither_mode="selective")
        touched = False
        for index, (a, b, c) in enumerate(zip(off, protected, unprotected)):
            np.testing.assert_array_equal(
                a[mask], b[mask],
                "frame %d: el dither protegido tramo el panel" % index)
            touched = touched or bool((a[mask] != c[mask]).any())
        self.assertTrue(touched, "fixture vacuo: sin proteccion el dither "
                        "deberia tramar dentro del panel")

    def test_calibrated_dither_honors_protected_rects(self):
        # mismo fixture que test_calibrated_dither: gradiente gris continuo
        # sobre 4 niveles, donde el modo auto SI acepta tiles por proxy
        gray = np.tile(np.linspace(0, 255, self.D_COLS, dtype=np.uint8),
                       (self.D_ROWS, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        palette = np.asarray(((0, 0, 0), (85, 85, 85), (170, 170, 170),
                              (255, 255, 255)), dtype=np.uint8)
        diff = rgb[:, :, None, :].astype(np.int32) - \
            palette[None, None, :, :].astype(np.int32)
        baseline = np.argmin(np.sum(diff * diff, axis=3),
                             axis=2).astype(np.uint8)
        rects = overlay_panel.panel_rects(self.D_COLS, self.D_ROWS)
        # presupuesto sin limite: que el ranking de tiles no esconda el panel
        free = selective_dither.apply_calibrated_dither(
            rgb, baseline, palette, max_changed_fraction=1.0)
        guarded = selective_dither.apply_calibrated_dither(
            rgb, baseline, palette, max_changed_fraction=1.0,
            protected_rects=rects)
        mask2d = selective_dither.rects_mask(baseline.shape, rects)
        np.testing.assert_array_equal(guarded[mask2d], baseline[mask2d],
                                      "auto no debe tocar rects protegidos")
        self.assertTrue(bool((free[mask2d] != baseline[mask2d]).any()),
                        "fixture vacuo: sin proteccion, auto deberia tramar "
                        "dentro del panel")


if __name__ == "__main__":
    unittest.main()

