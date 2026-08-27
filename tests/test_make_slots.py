"""E-07: sidecar ASCLSLOT — builder + validador Python y fixtures compartidos.

Construye el caso valido de referencia y un fixture negativo por cada
restriccion de §6.3 (mas el de reserved_rgb). Verifica que el validador
Python rechace cada uno con su motivo, y deja los binarios en
``tests/fixtures/slots-generated/`` para que ``test_slots_js.js`` pruebe que
``frontend/slots.js`` acepta y rechaza exactamente los mismos archivos.
"""
import os
import shutil
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_slots  # noqa: E402

GENERATED_DIR = os.path.join(ROOT, "tests", "fixtures", "slots-generated")

COLS, ROWS, FRAMES = 192, 108, 200
GLYPH_W, GLYPH_H = 8, 12
RESERVED_RGB = bytes(bytearray(
    [8, 8, 8, 40, 40, 40, 80, 80, 80, 120, 120, 120, 160, 160, 160,
     200, 200, 200, 255, 255, 255, 255, 200, 0, 0, 200, 0, 0, 0, 0]))
OTHER_RGB = bytes(bytearray([1, 2, 3] * 10))


def glyph_table(glyph_w=GLYPH_W, glyph_h=GLYPH_H):
    area = glyph_w * glyph_h
    return bytes(bytearray((246 + (i % 6)) for i in range(11 * area)))


def slot(x, y, start=0, end=FRAMES - 1, flags=1):
    return {"x": x, "y": y, "start": start, "end": end, "flags": flags}


def base_meta(**overrides):
    meta = {
        "glyph_w": GLYPH_W, "glyph_h": GLYPH_H,
        "glyph_table": glyph_table(),
        "reserved_rgb": RESERVED_RGB,
        "slots": [slot(4, 4), slot(13, 4), slot(30, 4), slot(39, 4)],
        "fields": [
            {"field_id": 1, "slot_ids": [0, 1], "min": 0, "max": 99, "pad": 1},
            {"field_id": 2, "slot_ids": [2, 3], "min": 0, "max": 99, "pad": 1},
        ],
    }
    meta.update(overrides)
    return meta


def build_cases():
    """(nombre, bytes, regex del motivo o None si es valido)."""
    cases = [("valid", make_slots.build(base_meta()), None)]

    cases.append(("bad-fuera-de-grilla", make_slots.build(base_meta(
        slots=[slot(186, 4)],
        fields=[{"field_id": 1, "slot_ids": [0], "min": 0, "max": 9,
                 "pad": 1}])), "fuera de la grilla"))

    cases.append(("bad-solape", make_slots.build(base_meta(
        slots=[slot(4, 4), slot(10, 4)],
        fields=[{"field_id": 1, "slot_ids": [0, 1], "min": 0, "max": 99,
                 "pad": 1}])), "se solapan"))

    many = [slot(i % 192, i // 192) for i in range(1025)]
    cases.append(("bad-n-slots", make_slots.build(base_meta(
        glyph_w=1, glyph_h=1, glyph_table=glyph_table(1, 1),
        slots=many, fields=[])), "n_slots supera"))

    wide = [slot(8 * i, 4) for i in range(12)]
    cases.append(("bad-area", make_slots.build(base_meta(
        slots=wide, fields=[])), "area activa"))

    corrupted = bytearray(make_slots.build(base_meta()))
    corrupted[make_slots.HEADER_SIZE + 5] = 200
    cases.append(("bad-glifo", make_slots.rewrite_crc(corrupted),
                  "fuera de 246"))

    cases.append(("bad-slot-inexistente", make_slots.build(base_meta(
        fields=[{"field_id": 1, "slot_ids": [0, 7], "min": 0, "max": 99,
                 "pad": 1}])), "inexistente"))

    cases.append(("bad-slot-duplicado", make_slots.build(base_meta(
        fields=[
            {"field_id": 1, "slot_ids": [0, 1], "min": 0, "max": 99, "pad": 1},
            {"field_id": 2, "slot_ids": [0, 2], "min": 0, "max": 99, "pad": 1},
        ])), "dos campos"))

    cases.append(("bad-reserved-rgb", make_slots.build(base_meta(
        reserved_rgb=OTHER_RGB)), "no coincide"))

    return cases


class MakeSlotsTest(unittest.TestCase):
    def test_valid_reference_roundtrip(self):
        data = make_slots.build(base_meta())
        parsed = make_slots.validate(data, COLS, ROWS, FRAMES, RESERVED_RGB)
        self.assertEqual(len(parsed["slots"]), 4)
        self.assertEqual(len(parsed["fields"]), 2)
        self.assertEqual(parsed["glyph_w"], GLYPH_W)
        self.assertEqual(parsed["reserved_rgb"], RESERVED_RGB)
        # determinismo del builder
        self.assertEqual(data, make_slots.build(base_meta()))

    def test_every_restriction_rejects_its_fixture(self):
        for name, data, reason in build_cases():
            if reason is None:
                make_slots.validate(data, COLS, ROWS, FRAMES, RESERVED_RGB)
                continue
            with self.assertRaisesRegex(ValueError, reason, msg=name):
                make_slots.validate(data, COLS, ROWS, FRAMES, RESERVED_RGB)

    def test_no_partial_load_on_corruption(self):
        data = bytearray(make_slots.build(base_meta()))
        data = data[:-4]  # campo final truncado
        with self.assertRaises(ValueError):
            make_slots.validate(bytes(data), COLS, ROWS, FRAMES)
        tampered = bytearray(make_slots.build(base_meta()))
        tampered[make_slots.HEADER_SIZE] ^= 1  # cuerpo mutado sin CRC nuevo
        with self.assertRaisesRegex(ValueError, "CRC"):
            make_slots.validate(bytes(tampered), COLS, ROWS, FRAMES)

    def test_fixtures_are_dumped_for_the_js_mirror(self):
        if os.path.isdir(GENERATED_DIR):
            shutil.rmtree(GENERATED_DIR)
        os.makedirs(GENERATED_DIR)
        for name, data, _reason in build_cases():
            with open(os.path.join(GENERATED_DIR, name + ".slots"), "wb") as f:
                f.write(data)
        with open(os.path.join(GENERATED_DIR, "context.bin"), "wb") as f:
            f.write(struct.pack("<HHI", COLS, ROWS, FRAMES) + RESERVED_RGB)
        self.assertTrue(os.path.exists(
            os.path.join(GENERATED_DIR, "valid.slots")))


if __name__ == "__main__":
    unittest.main()
