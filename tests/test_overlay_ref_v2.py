#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INT-003-D: referencia Python del runtime v2 + fixtures cruzados.

Encodea un clip real con ``reserved=32`` (reserva canonica 224..255,
``pal_size=256``), construye un sidecar ASCLSLOT **v2** (parches
heterogeneos, campos de digitos y de eleccion, slots superpuestos en espacio
con ventanas disjuntas) y compone frame a frame con ``OverlayRef``. Deja en
``tests/fixtures/overlay-v2-generated/`` el clip, el sidecar, la linea de
tiempo de cargas (con digitos de presencia) y la matriz esperada para que
``test_overlay_v2_cross.js`` verifique que el runtime JavaScript produce
exactamente los mismos bytes.
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
import overlay_palette  # noqa: E402
from overlay_ref import EMPTY_GLYPH, NONE, OverlayRef  # noqa: E402

GENERATED_DIR = os.path.join(ROOT, "tests", "fixtures",
                             "overlay-v2-generated")

COLS, ROWS, FRAMES = 64, 32, 8
RESERVED_RGB_32 = overlay_palette.reserved_rgb_bytes(32)

# cargas con digitos de presencia (INT-003 §6): campos f1(2) f2(2) f3(2) f4(2)
TIMELINE = ((0, "05170012"), (3, "99001110"), (6, "40161200"))


def digit_patch(digit):
    """Digito d: celda 0 transparente, el resto recorre 224..254."""
    data = bytearray(20)
    for k in range(20):
        data[k] = 255 if k == 0 else 224 + ((digit + k) % 31)
    return {"w": 4, "h": 5, "data": bytes(data)}


def choice_patch(variant):
    data = bytearray(30)
    for k in range(30):
        data[k] = 255 if k == 0 else 224 + ((variant * 7 + k) % 31)
    return {"w": 6, "h": 5, "data": bytes(data)}


def sidecar_meta():
    patches = [digit_patch(d) for d in range(10)]
    patches.append({"w": 4, "h": 5, "data": b"\xff" * 20})  # vacio (10)
    patches += [choice_patch(v) for v in range(3)]          # 11..13
    return {
        "pal_reserved": 32,
        "reserved_rgb": RESERVED_RGB_32,
        "patches": patches,
        "slots": [
            {"x": 10, "y": 2, "w": 4, "h": 5, "start": 0, "end": FRAMES - 1},
            {"x": 16, "y": 2, "w": 4, "h": 5, "start": 0, "end": FRAMES - 1},
            {"x": 30, "y": 10, "w": 6, "h": 5, "start": 0, "end": 3},
            # mismo lugar que el slot 2, ventana disjunta (D4)
            {"x": 30, "y": 10, "w": 6, "h": 5, "start": 4, "end": FRAMES - 1},
            {"x": 50, "y": 20, "w": 6, "h": 5, "start": 0, "end": FRAMES - 1},
        ],
        "fields": [
            {"field_id": 1, "kind": 0, "slot_ids": [0, 1],
             "min": 0, "max": 99, "pad": 1, "patch_base": 0},
            {"field_id": 2, "kind": 1, "slot_ids": [2],
             "min": 5, "max": 7, "pad": 0, "patch_base": 11},
            {"field_id": 3, "kind": 1, "slot_ids": [3],
             "min": 0, "max": 2, "pad": 0, "patch_base": 11},
            {"field_id": 4, "kind": 1, "slot_ids": [4],
             "min": 0, "max": 2, "pad": 0, "patch_base": 11},
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
            reserved=32, reserved_colors=overlay_palette.RESERVED_RGB_32)


class OverlayRefV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        cls.clip_path = os.path.join(cls.directory, "clip.ascl")
        encode_clip(cls.clip_path)
        _hdr, _ramp, cls.cells_list, cls.pal_list = \
            ascl_decode.decode_all(cls.clip_path)
        cls.sidecar = make_slots.build_v2(sidecar_meta())
        cls.meta = make_slots.validate(cls.sidecar, COLS, ROWS, FRAMES,
                                       RESERVED_RGB_32)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def fresh(self):
        return OverlayRef(self.meta, COLS, ROWS)

    def test_bundle_honors_the_extended_reserve(self):
        self.assertEqual(len(self.cells_list), FRAMES)
        reserved = np.frombuffer(RESERVED_RGB_32,
                                 dtype=np.uint8).reshape(32, 3)
        for index, (cells, palette) in enumerate(
                zip(self.cells_list, self.pal_list)):
            self.assertEqual(len(palette), 256, "paleta completa")
            np.testing.assert_array_equal(
                palette[224:], reserved,
                "cola reservada de 32 alterada en frame %d" % index)
            np.testing.assert_array_equal(
                palette[246:], overlay_palette.RESERVED_RGB,
                "cola F7 (10) alterada en frame %d" % index)
            self.assertLess(int(cells.max()), 224,
                            "INV-3 parametrico roto en frame %d" % index)

    def test_field_semantics_with_presence(self):
        ref = self.fresh()
        self.assertEqual(ref.digit_count, 8)
        self.assertEqual(ref.values, [EMPTY_GLYPH, EMPTY_GLYPH,
                                      NONE, NONE, NONE])
        self.assertTrue(ref.set_values("05170012"))
        self.assertEqual(ref.values, [0, 5, 13, NONE, 13])
        # invalidas: todo-o-nada, el estado no cambia
        self.assertFalse(ref.set_values("0517001"), "longitud")
        self.assertFalse(ref.set_values("05270012"), "presencia > 1")
        self.assertFalse(ref.set_values("05180012"), "eleccion fuera de rango")
        self.assertFalse(ref.set_values("05010012"),
                         "presencia 0 exige valor 0 (canonico)")
        self.assertEqual(ref.values, [0, 5, 13, NONE, 13])
        # set_field sirve para ambos kinds; clear_field vuelve al default
        self.assertTrue(ref.set_field(2, 5))
        self.assertEqual(ref.values[2], 11)
        self.assertFalse(ref.set_field(2, 8))
        self.assertTrue(ref.clear_field(2))
        self.assertEqual(ref.values[2], NONE)
        self.assertTrue(ref.clear_field(1))
        self.assertEqual(ref.values[:2], [EMPTY_GLYPH, EMPTY_GLYPH])

    def test_compose_choice_windows_and_none(self):
        ref = self.fresh()
        self.assertTrue(ref.set_values("05170012"))
        flat2 = np.asarray(self.cells_list[2], dtype=np.uint8).reshape(-1)
        composed2 = ref.compose(self.cells_list[2], 2)
        s2 = self.meta["slots"][2]
        cell = (s2["y"] + 1) * COLS + s2["x"] + 1
        self.assertEqual(composed2[cell], 224 + ((2 * 7 + 7) % 31),
                         "frame 2: parche 13 (variante 2) en el slot 2")
        # transparencia: la celda 0 del parche deja pasar el video
        corner = s2["y"] * COLS + s2["x"]
        self.assertEqual(composed2[corner], flat2[corner])
        # slot 3 (ventana 4..7) todavia no se pinta
        flat5 = np.asarray(self.cells_list[5], dtype=np.uint8).reshape(-1)
        composed5 = ref.compose(self.cells_list[5], 5)
        self.assertEqual(composed5[cell], flat5[cell],
                         "frame 5: el slot 2 ya no esta en ventana y el 3 "
                         "sigue NONE: la zona queda video base")
        self.assertTrue(ref.set_field(3, 1))
        composed5b = ref.compose(self.cells_list[5], 5)
        self.assertEqual(composed5b[cell], 224 + ((1 * 7 + 7) % 31),
                         "frame 5: parche 12 (variante 1) en el slot 3")
        ref.clear()
        np.testing.assert_array_equal(
            ref.compose(self.cells_list[5], 5), flat5,
            "clear: byte-identico al video base")

    def test_fixtures_for_the_js_mirror(self):
        ref = self.fresh()
        timeline = dict(TIMELINE)
        expected = bytearray()
        for index in range(FRAMES):
            if index in timeline:
                self.assertTrue(ref.set_values(timeline[index]),
                                "carga del frame %d" % index)
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
                    RESERVED_RGB_32)
        self.assertEqual(len(expected), FRAMES * COLS * ROWS)


if __name__ == "__main__":
    unittest.main()
