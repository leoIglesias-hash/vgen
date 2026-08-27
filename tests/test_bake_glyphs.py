"""E-06: propiedades del horneado de glifos.

No se fija la forma exacta de los digitos (depende de la fuente instalada):
se verifica el contrato binario — solo indices reservados validos, texto
pleno presente en cada digito, glifo vacio transparente, y determinismo
byte a byte entre dos corridas.
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bake_glyphs  # noqa: E402


def _has_font():
    try:
        bake_glyphs.load_font(None, 24)
        return True
    except SystemExit:
        return False


@unittest.skipUnless(_has_font(), "sin fuente TrueType disponible")
class BakeGlyphsTest(unittest.TestCase):
    def test_table_contract_and_determinism(self):
        first = bake_glyphs.bake(8, 12)
        second = bake_glyphs.bake(8, 12)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first.shape, (11, 12, 8))

        allowed = {246, 247, 248, 249, 250, 251, 255}
        self.assertTrue(set(np.unique(first).tolist()) <= allowed)

        for digit in range(10):
            glyph = first[digit]
            self.assertTrue((glyph == 251).any(),
                            "digito %d sin texto pleno" % digit)
            self.assertTrue((glyph == 246).any(),
                            "digito %d sin fondo" % digit)
            self.assertFalse((glyph == 255).any(),
                             "digito %d usa transparente" % digit)
        self.assertTrue((first[10] == 255).all(), "glifo vacio no transparente")

    def test_quantize_coverage_bands(self):
        coverage = np.asarray([0, 21, 22, 74, 75, 127, 128, 180, 181, 233,
                               234, 255], dtype=np.uint32)
        expected = np.asarray([246, 246, 247, 247, 248, 248, 249, 249, 250,
                               250, 251, 251], dtype=np.uint8)
        np.testing.assert_array_equal(
            bake_glyphs.quantize_coverage(coverage), expected)


if __name__ == "__main__":
    unittest.main()
