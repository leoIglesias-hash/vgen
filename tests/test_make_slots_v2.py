"""INT-003-B: ASCLSLOT v2 — escritor y validador Python.

Cubre DISENO-PARCHES-GENERICOS §5: parches heterogeneos, reserva parametrica,
slots con dimensiones propias, campos kind=0/1, presupuestos por frame (5%)
y de RAM (25%), solape espacial solo con ventanas disjuntas, y canonicidad
(§5.5). El corpus negativo (una entrada por regla) se construye una sola vez
y se vuelca a ``tests/fixtures/slots-v2-generated/`` para que la suite JS
(test_slots_v2.js) verifique los MISMOS bytes con el MISMO veredicto.
"""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_slots  # noqa: E402
import overlay_palette  # noqa: E402

COLS, ROWS, FRAMES = 64, 32, 10
RESERVED_RGB_32 = overlay_palette.reserved_rgb_bytes(32)


def digit_patch(digit):
    return {"w": 4, "h": 5, "data": bytes([224 + digit]) * 20}


def base_meta():
    patches = [digit_patch(d) for d in range(10)]
    patches.append({"w": 4, "h": 5, "data": b"\xff" * 20})       # vacio (10)
    patches.append({"w": 6, "h": 5, "data": b"\xe1" * 30})       # 11: 225
    patches.append({"w": 6, "h": 5, "data": b"\xe8" * 30})       # 12: 232
    patches.append({"w": 6, "h": 5, "data": b"\xed" * 30})       # 13: 237
    return {
        "pal_reserved": 32,
        "reserved_rgb": RESERVED_RGB_32,
        "patches": patches,
        "slots": [
            {"x": 10, "y": 2, "w": 4, "h": 5, "start": 0, "end": 9},
            {"x": 16, "y": 2, "w": 4, "h": 5, "start": 0, "end": 9},
            {"x": 30, "y": 10, "w": 6, "h": 5, "start": 0, "end": 4},
            # mismo lugar que el slot 2, ventana disjunta (D4)
            {"x": 30, "y": 10, "w": 6, "h": 5, "start": 5, "end": 9},
            {"x": 50, "y": 20, "w": 6, "h": 5, "start": 0, "end": 9},
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


def build(meta):
    return make_slots.build_v2(meta)


def _mut_field(index, **changes):
    meta = base_meta()
    meta["fields"][index] = dict(meta["fields"][index], **changes)
    return build(meta)


def _corpus():
    """name -> (bytes, fragmento del mensaje esperado o None si es valido).

    Cada entrada cubre una regla distinta de §5; los bytes van a fixtures
    para que la suite JS emita el mismo veredicto sobre el mismo archivo.
    """
    corpus = {}

    corpus["valid"] = (build(base_meta()), None)

    meta = base_meta()
    # pico de area activa exactamente en el 5% (102 de 2048/20): se acepta
    meta["slots"].append({"x": 2, "y": 20, "w": 1, "h": 2,
                          "start": 0, "end": 9})
    corpus["valid-borde-5pc"] = (build(meta), None)

    meta = base_meta()
    meta["fields"] = meta["fields"][:1]  # slots y parches sin referenciar
    corpus["valid-sin-referencias"] = (build(meta), None)

    data = bytearray(build(base_meta()))
    data[8] = 3
    corpus["bad-version"] = (bytes(data), "version no soportada")

    data = bytearray(build(base_meta()))
    data[9] = 1
    corpus["bad-reservado"] = (bytes(data), "byte reservado distinto de 0")

    meta = base_meta()
    meta["pal_reserved"] = 9
    meta["reserved_rgb"] = b"\x00" * 27
    corpus["bad-pal-reserved"] = (build(meta), "pal_reserved fuera de 10..64")

    data = bytearray(build(base_meta()))
    data[11] = 1
    corpus["bad-flags"] = (bytes(data), "flags distinto de 0")

    data = bytearray(build(base_meta()))
    data[-1] ^= 0xff
    corpus["bad-crc"] = (bytes(data), "CRC32 invalido")

    meta = base_meta()
    rgb = bytearray(RESERVED_RGB_32)
    rgb[0] ^= 1
    meta["reserved_rgb"] = bytes(rgb)
    corpus["bad-rgb"] = (build(meta), "reserved_rgb no coincide con el bundle")

    meta = base_meta()
    meta["patches"] = []
    meta["fields"] = []
    corpus["bad-sin-parches"] = (build(meta), "sin parches")

    meta = base_meta()
    meta["patches"][0] = {"w": 65, "h": 64, "data": b"\xff" * (65 * 64)}
    corpus["bad-parche-dims"] = (build(meta),
                                 "parche 0 con dimensiones invalidas")

    meta = base_meta()
    # 65 parches de 64x64 = 266.240 B > 256 KiB
    meta["patches"] = [{"w": 64, "h": 64, "data": b"\xff" * 4096}
                       for _ in range(65)]
    meta["fields"] = []
    corpus["bad-parche-total"] = (build(meta),
                                  "datos de parches superan 256 KiB")

    meta = base_meta()
    bad = bytearray(meta["patches"][11]["data"])
    bad[7] = 223  # justo debajo de 256-32
    meta["patches"][11]["data"] = bytes(bad)
    corpus["bad-parche-byte"] = (build(meta),
                                 "byte de parche fuera de la reserva")

    meta = base_meta()
    meta["slots"][4]["w"] = 0
    corpus["bad-slot-dims"] = (build(meta),
                               "slot 4 con dimensiones invalidas")

    meta = base_meta()
    meta["slots"][4]["x"] = COLS - 5
    corpus["bad-slot-grilla"] = (build(meta), "slot 4 fuera de la grilla")

    meta = base_meta()
    meta["slots"][4]["start"], meta["slots"][4]["end"] = 6, 2
    corpus["bad-slot-ventana"] = (build(meta),
                                  "slot 4 con end_frame < start_frame")

    meta = base_meta()
    meta["slots"][4]["end"] = FRAMES
    corpus["bad-slot-frames"] = (build(meta),
                                 "slot 4 activo mas alla del ultimo frame")

    meta = base_meta()
    meta["slots"][3]["start"] = 4  # pisa el frame 4 del slot 2
    corpus["bad-solape"] = (build(meta), "slots 2 y 3 se solapan")

    meta = base_meta()
    meta["slots"].append({"x": 2, "y": 20, "w": 6, "h": 5,
                          "start": 0, "end": 4})  # pico 130 > 102
    corpus["bad-area-frame"] = (build(meta),
                                "area activa supera el 5% de la grilla")

    meta = base_meta()
    meta["slots"] = [{"x": 2, "y": 2, "w": 8, "h": 8,
                      "start": f, "end": f} for f in range(9)]
    meta["fields"] = []  # 9*64 = 576 > 2048/4, con 64 activas por frame
    corpus["bad-area-total"] = (
        build(meta), "area total de slots supera el 25% de la grilla")

    corpus["bad-kind"] = (_mut_field(1, kind=2), "campo 2 con kind invalido")

    meta = base_meta()
    meta["fields"] = [meta["fields"][0],
                      dict(meta["fields"][1], slot_ids=[2, 3])]
    corpus["bad-eleccion-multislot"] = (
        build(meta), "campo 2 de eleccion debe tener un solo slot")

    corpus["bad-eleccion-pad"] = (
        _mut_field(1, pad=1), "campo 2 de eleccion con pad distinto de 0")

    corpus["bad-pad"] = (_mut_field(0, pad=2), "campo 1 con pad invalido")

    corpus["bad-max-min"] = (_mut_field(1, min=8, max=7),
                             "campo 2 con max < min")

    corpus["bad-digitos"] = (
        _mut_field(0, max=100),
        "campo 1 no puede representar max con 2 digitos")

    corpus["bad-span"] = (_mut_field(1, min=0, max=512),
                          "campo 2 de eleccion supera 512 variantes")

    corpus["bad-parche-inexistente"] = (
        _mut_field(1, patch_base=12),
        "campo 2 referencia un parche inexistente")

    corpus["bad-parche-dims-slot"] = (
        _mut_field(1, patch_base=0),
        "campo 2 con parches de dimensiones distintas al slot")

    corpus["bad-slot-inexistente"] = (
        _mut_field(1, slot_ids=[9]),
        "campo 2 referencia un slot inexistente")

    meta = base_meta()
    meta["fields"][2] = dict(meta["fields"][2], slot_ids=[2])
    corpus["bad-slot-duplicado"] = (build(meta),
                                    "slot 2 aparece en dos campos")

    corpus["bad-slots-dims"] = (
        _mut_field(0, slot_ids=[0, 2]),
        "campo 1 con slots de dimensiones distintas")

    corpus["bad-digitos-parches"] = (
        _mut_field(0, patch_base=4),
        "campo 1 referencia un parche inexistente")

    data = build(base_meta()) + b"\x00"
    corpus["bad-sobrantes"] = (make_slots.rewrite_crc_v2(data),
                               "bytes sobrantes al final del sidecar")

    full = build(base_meta())
    corpus["bad-truncado-campos"] = (
        make_slots.rewrite_crc_v2(full[:len(full) - 4]),
        "tabla de campos truncada")

    corpus["bad-truncado-header"] = (full[:15], "sidecar truncado")

    # count=0 en el primer campo (build_v2 lo rechaza; se muta el byte)
    header_end = make_slots.HEADER_SIZE_V2 + 96
    dir_end = header_end + 14 * 4
    data_end = dir_end + sum(p["w"] * p["h"] for p in base_meta()["patches"])
    slots_end = data_end + 5 * make_slots.SLOT_SIZE_V2
    data = bytearray(full)
    data[slots_end + 3] = 0
    corpus["bad-campo-sin-slots"] = (
        make_slots.rewrite_crc_v2(bytes(data)), "campo 0 sin slots")

    return corpus


class ValidV2Test(unittest.TestCase):
    def test_roundtrip_and_crosscheck(self):
        data = build(base_meta())
        parsed = make_slots.validate(data, COLS, ROWS, FRAMES, RESERVED_RGB_32)
        self.assertEqual(parsed["version"], 2)
        self.assertEqual(parsed["pal_reserved"], 32)
        self.assertEqual(parsed["reserved_rgb"], RESERVED_RGB_32)
        self.assertEqual(len(parsed["patches"]), 14)
        self.assertEqual(parsed["patches"][11],
                         {"w": 6, "h": 5, "data": b"\xe1" * 30})
        self.assertEqual(len(parsed["slots"]), 5)
        self.assertEqual(parsed["slots"][3],
                         {"x": 30, "y": 10, "w": 6, "h": 5,
                          "start": 5, "end": 9, "flags": 1})
        self.assertEqual(parsed["fields"][0]["kind"], 0)
        self.assertEqual(parsed["fields"][1],
                         {"field_id": 2, "kind": 1, "slot_ids": [2],
                          "min": 5, "max": 7, "pad": 0, "patch_base": 11})

    def test_validates_without_expected_rgb_and_without_n_frames(self):
        meta = base_meta()
        meta["slots"][4]["end"] = FRAMES  # invalido con n_frames, valido sin
        data = build(meta)
        make_slots.validate(data, COLS, ROWS, None)
        with self.assertRaises(ValueError):
            make_slots.validate(data, COLS, ROWS, FRAMES)

    def test_deterministic_build(self):
        self.assertEqual(build(base_meta()), build(base_meta()))

    def test_truncated_header_and_tables(self):
        full = build(base_meta())
        with self.assertRaises(ValueError):
            make_slots.validate(full[:8], COLS, ROWS)
        with self.assertRaises(ValueError):
            make_slots.validate(full[:21], COLS, ROWS)
        parsed = make_slots.validate(full, COLS, ROWS, FRAMES,
                                     RESERVED_RGB_32)
        header_end = make_slots.HEADER_SIZE_V2 + 96
        dir_end = header_end + len(parsed["patches"]) * 4
        data_end = dir_end + sum(p["w"] * p["h"] for p in parsed["patches"])
        slots_end = data_end + len(parsed["slots"]) * make_slots.SLOT_SIZE_V2
        for cut, message in ((dir_end - 2, "tabla de parches truncada"),
                             (data_end - 3, "tabla de parches truncada"),
                             (slots_end - 5, "tabla de slots truncada")):
            with self.assertRaises(ValueError) as context:
                make_slots.validate(make_slots.rewrite_crc_v2(full[:cut]),
                                    COLS, ROWS, FRAMES, RESERVED_RGB_32)
            self.assertIn(message, str(context.exception))


class CorpusTest(unittest.TestCase):
    def test_every_rule_has_its_rejection(self):
        for name, (data, message) in sorted(_corpus().items()):
            if message is None:
                make_slots.validate(data, COLS, ROWS, FRAMES,
                                    RESERVED_RGB_32)
                continue
            with self.assertRaises(ValueError) as context:
                make_slots.validate(data, COLS, ROWS, FRAMES,
                                    RESERVED_RGB_32)
            self.assertIn(message, str(context.exception),
                          "%s rechazado por otra regla" % name)


class FixtureDumpTest(unittest.TestCase):
    """Vuelca el corpus para la verificacion cruzada JS (test_slots_v2.js):
    mismos bytes, mismo veredicto (mecanismo E-07)."""

    def test_dump_corpus_for_js(self):
        out_dir = os.path.join(ROOT, "tests", "fixtures",
                               "slots-v2-generated")
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        lines = []
        for name, (data, message) in sorted(_corpus().items()):
            with open(os.path.join(out_dir, name + ".slots"), "wb") as stream:
                stream.write(data)
            lines.append("%s\t%s" % (name, message or ""))
        with open(os.path.join(out_dir, "corpus.txt"), "w") as stream:
            stream.write("\n".join(lines) + "\n")
        with open(os.path.join(out_dir, "context.bin"), "wb") as stream:
            stream.write(struct.pack("<HHI", COLS, ROWS, FRAMES) +
                         RESERVED_RGB_32)


class V1StillWorksTest(unittest.TestCase):
    def test_v1_roundtrip_untouched(self):
        glyphs = bytes(bytearray([246] * (2 * 3 * 11)))
        meta = {
            "glyph_w": 2, "glyph_h": 3, "glyph_table": glyphs,
            "reserved_rgb": overlay_palette.reserved_rgb_bytes(),
            "slots": [{"x": 0, "y": 0, "start": 0, "end": 9}],
            "fields": [{"field_id": 1, "slot_ids": [0],
                        "min": 0, "max": 9, "pad": 1}],
        }
        data = make_slots.build(meta)
        parsed = make_slots.validate(
            data, COLS, ROWS, FRAMES, overlay_palette.reserved_rgb_bytes())
        self.assertEqual(parsed["glyph_w"], 2)
        self.assertNotIn("version", parsed)


if __name__ == "__main__":
    unittest.main()
