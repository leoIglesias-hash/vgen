#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7-4: referencia Python del overlay + fixtures cruzados Python/JS.

Encodea un clip real con ``reserved=10`` (reservadas en 246..255 con
``pal_size=256``), construye un sidecar ASCLSLOT y compone frame a frame con
``backend/overlay_ref.OverlayRef``. Deja en ``tests/fixtures/overlay-generated/``
el clip, el sidecar, la linea de tiempo de cargas y la matriz esperada para
que ``test_overlay_cross.js`` verifique que el runtime JavaScript produce
exactamente los mismos bytes (gate de cierre de S-5).
"""
import os
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ascl_decode  # noqa: E402
import encoder  # noqa: E402
import make_slots  # noqa: E402
from overlay_ref import EMPTY_GLYPH, OverlayRef  # noqa: E402

GENERATED_DIR = os.path.join(ROOT, "tests", "fixtures", "overlay-generated")

COLS, ROWS, FRAMES = 64, 32, 8
GLYPH_W, GLYPH_H = 4, 5
RESERVED_RGB = np.array(
    [[8, 8, 8], [40, 40, 40], [80, 80, 80], [120, 120, 120],
     [160, 160, 160], [200, 200, 200], [255, 255, 255], [255, 200, 0],
     [0, 200, 0], [0, 0, 0]], dtype=np.uint8)
RESERVED_RGB_BYTES = RESERVED_RGB.tobytes()

# la carga "0512" entra en el frame 0 y "9934" en el 3 (cruza el keyframe 4)
TIMELINE = ((0, "0512"), (3, "9934"))


def glyph_table():
    """Digito d: celda 0 transparente, el resto 246+((d+k)%10); el glifo 10
    (vacio) es 100% transparente, como el horneado de E-06."""
    area = GLYPH_W * GLYPH_H
    table = bytearray(11 * area)
    for digit in range(10):
        for k in range(area):
            table[digit * area + k] = 255 if k == 0 else 246 + ((digit + k) % 10)
    for k in range(area):
        table[EMPTY_GLYPH * area + k] = 255
    return bytes(table)


def sidecar_spec():
    return {
        "glyph_w": GLYPH_W, "glyph_h": GLYPH_H, "glyph_table": glyph_table(),
        "reserved_rgb": RESERVED_RGB_BYTES,
        "slots": [
            {"x": 10, "y": 8, "start": 0, "end": FRAMES - 1, "flags": 1},
            {"x": 16, "y": 8, "start": 0, "end": FRAMES - 1, "flags": 1},
            {"x": 22, "y": 8, "start": 0, "end": FRAMES - 1, "flags": 1},
            # se desactiva tras el frame 1: el runtime debe restaurarlo
            {"x": 28, "y": 8, "start": 0, "end": 1, "flags": 1},
        ],
        "fields": [
            {"field_id": 7, "slot_ids": [0, 1], "min": 0, "max": 99, "pad": 1},
            {"field_id": 9, "slot_ids": [2, 3], "min": 0, "max": 42, "pad": 0},
        ],
    }


def clip_frames():
    """Gradiente que deriva por frame, con corte duro en el frame 4 (coincide
    con el keyint): hay keyframes y deltas reales en la cadena."""
    frames = []
    yy, xx = np.indices((ROWS, COLS))
    for index in range(FRAMES):
        base = (10, 40, 200) if index < 4 else (180, 60, 20)
        values = np.empty((ROWS, COLS, 3), dtype=np.int16)
        values[:, :, 0] = base[0] + xx * 2 + index * 3
        values[:, :, 1] = base[1] + yy * 3 + index * 2
        values[:, :, 2] = base[2] + ((xx + yy) // 2) - index * 4
        rgb = np.clip(values, 0, 255).astype(np.uint8)
        x = rgb.astype(np.uint16)
        gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
                 29 * x[:, :, 2]) >> 8).astype(np.uint8)
        frames.append((rgb, gray))
    return frames


def encode_clip(path):
    frames = clip_frames()

    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(frames)

    with mock.patch.object(encoder, "probe_size", return_value=(COLS, ROWS)), \
            mock.patch.object(encoder, "iter_video_frames",
                              side_effect=fake_iter):
        return encoder.encode_video(
            "synthetic.mp4", path, mode_name="pixel", cols=COLS, rows=ROWS,
            fps=15, pal_size=256, ramp_name="short", char_aspect=0.5,
            compress="auto", palette_mode="global", keyint=4,
            with_audio=False, palette_algorithm="fast-octree",
            reserved=10, reserved_colors=RESERVED_RGB)


class OverlayRefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        cls.clip_path = os.path.join(cls.directory, "clip.ascl")
        encode_clip(cls.clip_path)
        _hdr, _ramp, cls.cells_list, cls.pal_list = \
            ascl_decode.decode_all(cls.clip_path)
        cls.sidecar = make_slots.build(sidecar_spec())
        cls.meta = make_slots.validate(cls.sidecar, COLS, ROWS, FRAMES,
                                       RESERVED_RGB_BYTES)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def fresh(self):
        return OverlayRef(self.meta, COLS, ROWS)

    def test_bundle_honors_the_reserve(self):
        self.assertEqual(len(self.cells_list), FRAMES)
        for index, (cells, palette) in enumerate(
                zip(self.cells_list, self.pal_list)):
            self.assertEqual(len(palette), 256, "paleta completa")
            np.testing.assert_array_equal(
                palette[246:], RESERVED_RGB,
                "cola reservada alterada en frame %d" % index)
            self.assertLess(int(cells.max()), 246,
                            "INV-3 roto en frame %d" % index)

    def test_field_semantics_mirror_the_runtime(self):
        ref = self.fresh()
        self.assertTrue(ref.set_values("0512"))
        self.assertEqual(ref.values, [0, 5, 1, 2])
        self.assertFalse(ref.set_values("0599"), "campo 9 fuera de rango")
        self.assertFalse(ref.set_values("051"), "longitud")
        self.assertFalse(ref.set_values("05a2"), "caracter")
        self.assertEqual(ref.values, [0, 5, 1, 2],
                         "dato invalido conserva el estado")
        self.assertTrue(ref.set_field(9, 7))
        self.assertEqual(ref.values, [0, 5, EMPTY_GLYPH, 7],
                         "sin pad, el cero a la izquierda queda vacio")
        self.assertFalse(ref.set_field(9, 43))
        self.assertFalse(ref.set_field(8, 1))
        self.assertTrue(ref.clear_field(7))
        self.assertEqual(ref.values[:2], [EMPTY_GLYPH, EMPTY_GLYPH])

    def test_compose_only_touches_active_slots(self):
        ref = self.fresh()
        self.assertTrue(ref.set_values("0512"))
        base = self.cells_list[0]
        composed = ref.compose(base, 0)
        flat = np.asarray(base, dtype=np.uint8).reshape(-1)
        mask = np.zeros(COLS * ROWS, dtype=bool)
        for slot in self.meta["slots"]:
            for gy in range(GLYPH_H):
                row = (slot["y"] + gy) * COLS + slot["x"]
                mask[row:row + GLYPH_W] = True
        np.testing.assert_array_equal(composed[~mask], flat[~mask],
                                      "fuera de los slots nada cambia")
        self.assertTrue((composed[mask] != flat[mask]).any(),
                        "dentro de los slots hay glifos")
        # transparencia: la celda 0 de cada glifo deja pasar el video
        slot0 = self.meta["slots"][0]
        cell = slot0["y"] * COLS + slot0["x"]
        self.assertEqual(composed[cell], flat[cell])
        # el frame base no se muta
        np.testing.assert_array_equal(
            np.asarray(base, dtype=np.uint8).reshape(-1), flat)

    def test_clear_and_slot_windows(self):
        ref = self.fresh()
        self.assertTrue(ref.set_values("0512"))
        composed = ref.compose(self.cells_list[2], 2)
        slot3 = self.meta["slots"][3]
        cell = (slot3["y"] + 1) * COLS + slot3["x"] + 1
        flat = np.asarray(self.cells_list[2], dtype=np.uint8).reshape(-1)
        self.assertEqual(composed[cell], flat[cell],
                         "slot desactivado (end=1) no se pinta en el frame 2")
        ref.clear()
        np.testing.assert_array_equal(ref.compose(self.cells_list[2], 2), flat,
                                      "clear: byte-identico al video base")

    def test_fixtures_for_the_js_mirror(self):
        ref = self.fresh()
        timeline = dict(TIMELINE)
        expected = bytearray()
        for index in range(FRAMES):
            if index in timeline:
                self.assertTrue(ref.set_values(timeline[index]))
            expected += ref.compose(self.cells_list[index], index).tobytes()

        if os.path.isdir(GENERATED_DIR):
            shutil.rmtree(GENERATED_DIR)
        os.makedirs(GENERATED_DIR)
        shutil.copyfile(self.clip_path,
                        os.path.join(GENERATED_DIR, "clip.ascl"))
        with open(os.path.join(GENERATED_DIR, "valid.slots"), "wb") as f:
            f.write(self.sidecar)
        with open(os.path.join(GENERATED_DIR, "expected.bin"), "wb") as f:
            f.write(bytes(expected))
        with open(os.path.join(GENERATED_DIR, "timeline.txt"), "w") as f:
            for frame, digits in TIMELINE:
                f.write("%d:%s\n" % (frame, digits))
        with open(os.path.join(GENERATED_DIR, "context.bin"), "wb") as f:
            f.write(struct.pack("<HHI", COLS, ROWS, FRAMES) +
                    RESERVED_RGB_BYTES)
        self.assertEqual(len(expected), FRAMES * COLS * ROWS)


if __name__ == "__main__":
    unittest.main()
