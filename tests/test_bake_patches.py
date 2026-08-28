"""INT-003-E: horneado de parches arbitrarios a la reserva de 32.

Contratos (DISENO-PARCHES-GENERICOS §4/§7 y runbook INT-003-E):
- todo byte horneado esta en [224..254] o es 255 (transparente);
- la cuantizacion Oklab es determinista (dos corridas -> bytes identicos) y
  cada color reservado pintable mapea a su propio indice;
- el alpha bajo el umbral se vuelve transparencia;
- el texto se hornea con cualquier fuente TrueType y color, sobre fondo
  transparente;
- los parches salidos del horneado alimentan un sidecar v2 valido.
"""
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bake_patches  # noqa: E402
import make_slots  # noqa: E402
import overlay_palette  # noqa: E402

RESERVE = overlay_palette.RESERVED_RGB_32


def assert_in_reserve(test, data):
    for value in bytearray(data):
        test.assertTrue(value == 255 or 224 <= value <= 254,
                        "byte %d fuera de la reserva" % value)


class NearestReservedTest(unittest.TestCase):
    def test_each_paintable_color_maps_to_itself(self):
        indices = bake_patches.nearest_reserved(RESERVE[:31])
        self.assertEqual(list(indices), list(range(224, 255)))

    def test_black_maps_to_the_panel_background(self):
        # el RGB de la entrada 255 es transparencia: el negro pleno cae en
        # su vecino mas cercano, el fondo del panel (246: 16,16,30)
        self.assertEqual(
            int(bake_patches.nearest_reserved([[0, 0, 0]])[0]), 246)

    def test_quantize_rgba_alpha_threshold(self):
        rgba = np.zeros((2, 2, 4), dtype=np.uint8)
        rgba[0, 0] = (255, 215, 0, 255)   # oro opaco
        rgba[0, 1] = (255, 215, 0, 127)   # bajo el umbral
        rgba[1, 0] = (255, 255, 255, 128) # justo en el umbral
        rgba[1, 1] = (10, 10, 10, 0)
        grid = bake_patches.quantize_rgba(rgba)
        self.assertEqual(grid[0, 0], 245)
        self.assertEqual(grid[0, 1], 255)
        self.assertEqual(grid[1, 0], 251)
        self.assertEqual(grid[1, 1], 255)
        with self.assertRaises(ValueError):
            bake_patches.quantize_rgba(np.zeros((2, 2, 3), dtype=np.uint8))


class BakeImageTest(unittest.TestCase):
    def _half_and_half(self):
        rgba = np.zeros((24, 40, 4), dtype=np.uint8)
        rgba[:, :20, 0] = 255  # mitad izquierda: rojo opaco
        rgba[:, :20, 3] = 255
        return rgba

    def test_box_average_and_transparency(self):
        patch = bake_patches.bake_image_array(self._half_and_half(), 10, 6)
        self.assertEqual((patch["w"], patch["h"]), (10, 6))
        grid = np.frombuffer(patch["data"], dtype=np.uint8).reshape(6, 10)
        np.testing.assert_array_equal(grid[:, :5], 225)  # rojo puro
        np.testing.assert_array_equal(grid[:, 5:], 255)  # transparente
        assert_in_reserve(self, patch["data"])

    def test_deterministic(self):
        first = bake_patches.bake_image_array(self._half_and_half(), 10, 6)
        second = bake_patches.bake_image_array(self._half_and_half(), 10, 6)
        self.assertEqual(first, second)


class BakeTextTest(unittest.TestCase):
    def test_text_paints_the_color_over_transparency(self):
        patch = bake_patches.bake_text("7", 8, 12)
        self.assertEqual(len(patch["data"]), 96)
        values = set(bytearray(patch["data"]))
        self.assertEqual(values, {251, 255},
                         "texto blanco (251) sobre transparencia")
        assert_in_reserve(self, patch["data"])

    def test_color_is_quantized_in_oklab(self):
        patch = bake_patches.bake_text("7", 8, 12, color=(255, 0, 0))
        self.assertIn(225, set(bytearray(patch["data"])))

    def test_deterministic_and_digits(self):
        self.assertEqual(bake_patches.bake_text("3", 8, 12),
                         bake_patches.bake_text("3", 8, 12))
        patches = bake_patches.bake_digit_patches(6, 8)
        self.assertEqual(len(patches), 11)
        self.assertEqual(patches[10]["data"], b"\xff" * 48)
        seen = set()
        for patch in patches[:10]:
            self.assertEqual((patch["w"], patch["h"]), (6, 8))
            assert_in_reserve(self, patch["data"])
            seen.add(patch["data"])
        self.assertEqual(len(seen), 10, "los diez digitos son distintos")


class CliAndSidecarTest(unittest.TestCase):
    def test_cli_writes_raw_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            out = os.path.join(directory, "siete.bin")
            bake_patches.main(["text", "7", "--w", "8", "--h", "12",
                               "--out", out])
            self.assertEqual(os.path.getsize(out), 96)
            out_digits = os.path.join(directory, "digitos.bin")
            bake_patches.main(["digits", "--w", "4", "--h", "5",
                               "--out", out_digits])
            self.assertEqual(os.path.getsize(out_digits), 11 * 20)

    def test_baked_patches_feed_a_valid_v2_sidecar(self):
        patches = bake_patches.bake_digit_patches(4, 5)
        patches.append(bake_patches.bake_text("A", 6, 5,
                                              color=(255, 215, 0)))
        patches.append(bake_patches.bake_text("B", 6, 5,
                                              color=(0, 255, 255)))
        meta = {
            "pal_reserved": 32,
            "reserved_rgb": overlay_palette.reserved_rgb_bytes(32),
            "patches": patches,
            "slots": [
                {"x": 10, "y": 2, "w": 4, "h": 5, "start": 0, "end": 9},
                {"x": 16, "y": 2, "w": 4, "h": 5, "start": 0, "end": 9},
                {"x": 30, "y": 10, "w": 6, "h": 5, "start": 0, "end": 9},
            ],
            "fields": [
                {"field_id": 1, "kind": 0, "slot_ids": [0, 1],
                 "min": 0, "max": 99, "pad": 1, "patch_base": 0},
                {"field_id": 2, "kind": 1, "slot_ids": [2],
                 "min": 0, "max": 1, "pad": 0, "patch_base": 11},
            ],
        }
        data = make_slots.build_v2(meta)
        parsed = make_slots.validate(
            data, 64, 32, 10, overlay_palette.reserved_rgb_bytes(32))
        self.assertEqual(len(parsed["patches"]), 13)


if __name__ == "__main__":
    unittest.main()
