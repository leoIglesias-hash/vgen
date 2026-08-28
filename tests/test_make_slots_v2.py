"""INT-003-B: ASCLSLOT v2 — escritor y validador Python.

Cubre DISENO-PARCHES-GENERICOS §5: parches heterogeneos, reserva parametrica,
slots con dimensiones propias, campos kind=0/1, presupuestos por frame (5%)
y de RAM (25%), solape espacial solo con ventanas disjuntas, y canonicidad
(§5.5). Cada regla tiene su rechazo probado; el corpus se comparte de forma
espejada con la suite JS de INT-003-C.
"""
import os
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
        data = build(base_meta())
        make_slots.validate(data, COLS, ROWS)

    def test_deterministic_build(self):
        self.assertEqual(build(base_meta()), build(base_meta()))

    def test_unreferenced_slots_and_patches_are_legal(self):
        meta = base_meta()
        meta["fields"] = meta["fields"][:1]
        make_slots.validate(build(meta), COLS, ROWS, FRAMES, RESERVED_RGB_32)


def reject(test, meta_or_data, message, cols=COLS, rows=ROWS,
           n_frames=FRAMES, expected=RESERVED_RGB_32):
    data = meta_or_data if isinstance(meta_or_data, (bytes, bytearray)) \
        else build(meta_or_data)
    with test.assertRaises(ValueError) as context:
        make_slots.validate(data, cols, rows, n_frames, expected)
    test.assertIn(message, str(context.exception))


class HeaderV2Test(unittest.TestCase):
    def test_version_dispatch_and_unknown_version(self):
        data = bytearray(build(base_meta()))
        data[8] = 3
        reject(self, bytes(data), "version no soportada")

    def test_reserved_byte_and_flags_are_canonical(self):
        data = bytearray(build(base_meta()))
        data[9] = 1
        reject(self, bytes(data), "byte reservado distinto de 0")
        data = bytearray(build(base_meta()))
        data[11] = 1
        reject(self, bytes(data), "flags distinto de 0")

    def test_pal_reserved_range(self):
        for bad in (9, 65, 0):
            meta = base_meta()
            meta["pal_reserved"] = bad
            meta["reserved_rgb"] = b"\x00" * (3 * bad)
            reject(self, meta, "pal_reserved fuera de 10..64",
                   expected=b"\x00" * (3 * bad))

    def test_crc_is_verified(self):
        data = bytearray(build(base_meta()))
        data[-1] ^= 0xff
        reject(self, bytes(data), "CRC32 invalido")

    def test_reserved_rgb_crosscheck(self):
        wrong = bytearray(RESERVED_RGB_32)
        wrong[0] ^= 1
        reject(self, base_meta(), "reserved_rgb no coincide con el bundle",
               expected=bytes(wrong))

    def test_truncated(self):
        data = build(base_meta())
        reject(self, data[:8], "sidecar truncado")
        reject(self, data[:21], "sidecar truncado")


class PatchTableTest(unittest.TestCase):
    def test_empty_and_too_many(self):
        meta = base_meta()
        meta["patches"] = []
        meta["fields"] = []
        reject(self, meta, "sin parches")

    def test_patch_dimensions(self):
        meta = base_meta()
        meta["patches"][0] = {"w": 0, "h": 5, "data": b""}
        reject(self, meta, "parche 0 con dimensiones invalidas")
        meta = base_meta()
        meta["patches"][0] = {"w": 65, "h": 64, "data": b"\xff" * (65 * 64)}
        reject(self, meta, "parche 0 con dimensiones invalidas")

    def test_total_patch_data_cap(self):
        meta = base_meta()
        # 65 parches de 64x64 = 266.240 B > 256 KiB (los base no alcanzan)
        meta["patches"] = [{"w": 64, "h": 64, "data": b"\xff" * 4096}
                           for _ in range(65)]
        meta["fields"] = []
        reject(self, meta, "datos de parches superan 256 KiB")

    def test_patch_bytes_must_live_in_the_reserve(self):
        meta = base_meta()
        bad = bytearray(meta["patches"][11]["data"])
        bad[7] = 223  # justo debajo de 256-32
        meta["patches"][11]["data"] = bytes(bad)
        reject(self, meta, "byte de parche fuera de la reserva")


class SlotTableV2Test(unittest.TestCase):
    def test_dimensions_grid_and_window(self):
        meta = base_meta()
        meta["slots"][4]["w"] = 0
        reject(self, meta, "slot 4 con dimensiones invalidas")
        meta = base_meta()
        meta["slots"][4]["x"] = COLS - 5
        reject(self, meta, "slot 4 fuera de la grilla")
        meta = base_meta()
        meta["slots"][4]["start"], meta["slots"][4]["end"] = 6, 2
        reject(self, meta, "slot 4 con end_frame < start_frame")
        meta = base_meta()
        meta["slots"][4]["end"] = FRAMES
        reject(self, meta, "slot 4 activo mas alla del ultimo frame")
        make_slots.validate(build(meta), COLS, ROWS, None, RESERVED_RGB_32)

    def test_spatial_overlap_needs_disjoint_windows(self):
        meta = base_meta()
        meta["slots"][3]["start"] = 4  # pisa el frame 4 del slot 2
        reject(self, meta, "slots 2 y 3 se solapan")

    def test_per_frame_budget(self):
        meta = base_meta()
        # frames 0..4 ya suman 100 celdas; 6x5 mas los lleva a 130 > 102
        meta["slots"].append({"x": 2, "y": 20, "w": 6, "h": 5,
                              "start": 0, "end": 4})
        reject(self, meta, "area activa supera el 5% de la grilla")

    def test_per_frame_budget_counts_only_concurrent_windows(self):
        meta = base_meta()
        # cada mitad del clip ya suma 100 celdas activas; 1x2 mas en todo el
        # clip lleva el pico a 102, exactamente el 5% de 64x32: se acepta
        meta["slots"].append({"x": 2, "y": 20, "w": 1, "h": 2,
                              "start": 0, "end": 9})
        make_slots.validate(build(meta), COLS, ROWS, FRAMES, RESERVED_RGB_32)

    def test_total_ram_budget(self):
        meta = base_meta()
        meta["slots"] = [{"x": 2, "y": 2, "w": 8, "h": 8,
                          "start": f, "end": f} for f in range(9)]
        meta["fields"] = []
        # 9 * 64 = 576 > 2048/4 = 512, con 64 celdas activas por frame
        reject(self, meta, "area total de slots supera el 25% de la grilla")


class FieldTableV2Test(unittest.TestCase):
    def _mutate(self, **changes):
        meta = base_meta()
        meta["fields"][1] = dict(meta["fields"][1], **changes)
        return meta

    def test_kind_must_be_known(self):
        reject(self, self._mutate(kind=2), "campo 2 con kind invalido")

    def test_choice_needs_single_slot_and_pad_zero(self):
        meta = base_meta()
        meta["fields"] = [meta["fields"][0],
                          dict(meta["fields"][1], slot_ids=[2, 3])]
        reject(self, meta, "campo 2 de eleccion debe tener un solo slot")
        reject(self, self._mutate(pad=1),
               "campo 2 de eleccion con pad distinto de 0")

    def test_digits_pad_is_binary(self):
        meta = base_meta()
        meta["fields"][0] = dict(meta["fields"][0], pad=2)
        reject(self, meta, "campo 1 con pad invalido")

    def test_ranges(self):
        reject(self, self._mutate(min=8, max=7), "campo 2 con max < min")
        meta = base_meta()
        meta["fields"][0] = dict(meta["fields"][0], max=100)
        reject(self, meta, "campo 1 no puede representar max con 2 digitos")
        reject(self, self._mutate(min=0, max=512),
               "campo 2 de eleccion supera 512 variantes")

    def test_patch_references(self):
        reject(self, self._mutate(patch_base=12, max=7, min=5),
               "campo 2 referencia un parche inexistente")
        reject(self, self._mutate(patch_base=0),
               "campo 2 con parches de dimensiones distintas al slot")

    def test_slot_references(self):
        reject(self, self._mutate(slot_ids=[9]),
               "campo 2 referencia un slot inexistente")
        meta = base_meta()
        meta["fields"][2] = dict(meta["fields"][2], slot_ids=[2])
        reject(self, meta, "slot 2 aparece en dos campos")
        meta = base_meta()
        meta["fields"][0] = dict(meta["fields"][0], slot_ids=[0, 2])
        reject(self, meta, "campo 1 con slots de dimensiones distintas")

    def test_digit_field_needs_the_eleven_patches(self):
        meta = base_meta()
        meta["fields"] = [dict(meta["fields"][0], patch_base=4)]
        reject(self, meta, "campo 1 referencia un parche inexistente")


class TrailingAndTruncationTest(unittest.TestCase):
    def test_trailing_bytes(self):
        data = build(base_meta()) + b"\x00"
        reject(self, make_slots.rewrite_crc_v2(data), "bytes sobrantes")

    def test_truncated_tables(self):
        full = build(base_meta())
        parsed = make_slots.validate(full, COLS, ROWS, FRAMES,
                                     RESERVED_RGB_32)
        header_end = make_slots.HEADER_SIZE_V2 + 96
        dir_end = header_end + len(parsed["patches"]) * 4
        data_end = dir_end + sum(p["w"] * p["h"] for p in parsed["patches"])
        slots_end = data_end + len(parsed["slots"]) * make_slots.SLOT_SIZE_V2
        for cut, message in ((dir_end - 2, "tabla de parches truncada"),
                             (data_end - 3, "tabla de parches truncada"),
                             (slots_end - 5, "tabla de slots truncada"),
                             (len(full) - 4, "tabla de campos truncada")):
            reject(self, make_slots.rewrite_crc_v2(full[:cut]), message)


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
