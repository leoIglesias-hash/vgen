"""INT-003-F: sidecar v2 de demo (parches genericos) sobre geometria real.

Contratos:
- el sidecar de demo valida ENTERO contra la geometria HQ (768x432) con los
  presupuestos v2 (5% por frame, 25% de RAM);
- estructura: 25 parches (11 panel + 11 grandes + 3 palabras), 47 slots
  (40 panel + 6 grandes + 1 palabra), 24 campos; ventanas de los numeros
  grandes por tercios del clip;
- el payload de ejemplo (48 digitos, con presencia) lo acepta la referencia
  del runtime (OverlayRef);
- la construccion es determinista y una grilla chica se rechaza completa.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_patch_pack  # noqa: E402
import make_slots  # noqa: E402
import overlay_palette  # noqa: E402
from overlay_ref import NONE, OverlayRef  # noqa: E402

COLS, ROWS, FRAMES = 768, 432, 231
EXPECTED32 = overlay_palette.reserved_rgb_bytes(32)


class DemoSidecarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = make_patch_pack.build_sidecar(COLS, ROWS, FRAMES)
        cls.meta = make_slots.validate(cls.data, COLS, ROWS, FRAMES,
                                       EXPECTED32)

    def test_structure(self):
        self.assertEqual(self.meta["pal_reserved"], 32)
        self.assertEqual(len(self.meta["patches"]), 25)
        self.assertEqual(len(self.meta["slots"]), 47)
        self.assertEqual(len(self.meta["fields"]), 24)
        for patch in self.meta["patches"]:
            for value in bytearray(patch["data"]):
                self.assertTrue(value == 255 or 224 <= value <= 254)
        # numeros grandes: tres ventanas por tercios, posiciones distintas
        third = FRAMES // 3
        big = self.meta["slots"][40:46]
        self.assertEqual((big[0]["start"], big[0]["end"]), (0, third - 1))
        self.assertEqual((big[2]["start"], big[2]["end"]),
                         (third, 2 * third - 1))
        self.assertEqual((big[4]["start"], big[4]["end"]),
                         (2 * third, FRAMES - 1))
        self.assertNotEqual((big[0]["x"], big[0]["y"]),
                            (big[2]["x"], big[2]["y"]))
        # campo de eleccion con las tres palabras
        word = self.meta["fields"][23]
        self.assertEqual(word["kind"], 1)
        self.assertEqual((word["min"], word["max"]), (0, 2))
        self.assertEqual(word["patch_base"], 22)

    def test_sample_payload_is_accepted_by_the_runtime(self):
        ref = OverlayRef(self.meta, COLS, ROWS)
        self.assertEqual(ref.digit_count, 48)
        self.assertEqual(len(make_patch_pack.SAMPLE_PAYLOAD), 48)
        self.assertTrue(ref.set_values(make_patch_pack.SAMPLE_PAYLOAD))
        # palabra presente, variante 1 -> parche 23
        self.assertEqual(ref.values[46], 23)
        # panel: primeros dos digitos "05"
        self.assertEqual(ref.values[:2], [0, 5])
        self.assertTrue(ref.set_values(
            make_patch_pack.SAMPLE_PAYLOAD[:46] + "00"))
        self.assertEqual(ref.values[46], NONE)

    def test_deterministic(self):
        self.assertEqual(self.data,
                         make_patch_pack.build_sidecar(COLS, ROWS, FRAMES))

    def test_small_grids_and_short_clips_are_rejected(self):
        with self.assertRaises(ValueError):
            make_patch_pack.build_sidecar(400, 240, FRAMES)
        with self.assertRaises(ValueError):
            make_patch_pack.build_sidecar(COLS, ROWS, 2)


if __name__ == "__main__":
    unittest.main()
