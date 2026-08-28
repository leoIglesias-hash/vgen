"""INT-003-A: reserva ampliada a 32 entradas (224..255).

Contratos cubiertos (DISENO-PARCHES-GENERICOS §4, D1):
- ``RESERVED_RGB_32`` tiene 32 filas y sus ultimas diez son bit-identicas a
  ``RESERVED_RGB``: los glifos F7 (246..255) y el sidecar v1 siguen validos
  sobre un clip encodeado con reserva de 32;
- ``reserved_table``/``reserved_rgb_bytes`` solo aceptan las reservas
  canonicas (10 y 32);
- con ``reserved=32`` el encoder estampa las 32 entradas al final de CADA
  epoca (INV-4 parametrico) y ninguna celda base usa un indice >= 224
  (INV-3 parametrico), tambien con dither;
- ``make_clip`` rechaza una reserva no canonica antes de tocar el archivo.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_decode  # noqa: E402
import encoder  # noqa: E402
import make_clip  # noqa: E402
import overlay_palette  # noqa: E402


def color_frame(base, width=24, height=16):
    yy, xx = np.indices((height, width))
    values = np.empty((height, width, 3), dtype=np.int16)
    values[:, :, 0] = int(base[0]) + xx * 2
    values[:, :, 1] = int(base[1]) + yy * 2
    values[:, :, 2] = int(base[2]) + (xx + yy) // 2
    rgb = np.clip(values, 0, 255).astype(np.uint8)
    x = rgb.astype(np.uint16)
    gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)
    return rgb, gray


def scene_frames():
    """12 frames con un corte duro en el medio: fuerza mas de una epoca."""
    warm = [color_frame((30 + 14 * i, 20 + 6 * i, 10 + 4 * i)) for i in range(6)]
    cold = [color_frame((10 + 4 * i, 60 + 8 * i, 170 + 12 * i)) for i in range(6)]
    return warm + cold


def encode_reserved32(path, palette_mode, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(scene_frames())

    defaults = dict(
        mode_name="pixel", cols=24, rows=16, fps=15, pal_size=64,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode=palette_mode, keyint=3, with_audio=False,
        palette_algorithm="kmeans-oklab", reserved=32,
        reserved_colors=overlay_palette.RESERVED_RGB_32,
        adaptive_min_frames=2, adaptive_max_frames=4,
        palette_block_frames=4)
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size", return_value=(24, 16)), \
            mock.patch.object(encoder, "iter_video_frames", side_effect=fake_iter):
        return encoder.encode_video("synthetic.mp4", path, **defaults)


class ReservedTableContractTest(unittest.TestCase):
    def test_last_ten_rows_are_bit_identical_to_f7(self):
        table = overlay_palette.RESERVED_RGB_32
        self.assertEqual(table.shape, (32, 3))
        self.assertEqual(table.dtype, np.uint8)
        np.testing.assert_array_equal(table[-10:], overlay_palette.RESERVED_RGB)

    def test_all_entries_are_distinct(self):
        # el horneado por color mas cercano exige entradas sin duplicados
        rows = {tuple(int(v) for v in row)
                for row in overlay_palette.RESERVED_RGB_32}
        self.assertEqual(len(rows), 32)

    def test_helpers_only_accept_canonical_counts(self):
        self.assertEqual(overlay_palette.reserved_rgb_bytes(),
                         overlay_palette.RESERVED_RGB.tobytes())
        self.assertEqual(len(overlay_palette.reserved_rgb_bytes()), 30)
        self.assertEqual(overlay_palette.reserved_rgb_bytes(32),
                         overlay_palette.RESERVED_RGB_32.tobytes())
        self.assertEqual(len(overlay_palette.reserved_rgb_bytes(32)), 96)
        self.assertIs(overlay_palette.reserved_table(10),
                      overlay_palette.RESERVED_RGB)
        self.assertIs(overlay_palette.reserved_table(32),
                      overlay_palette.RESERVED_RGB_32)
        self.assertEqual(overlay_palette.reserved_first(10), 246)
        self.assertEqual(overlay_palette.reserved_first(32), 224)
        for bad in (0, 7, 16, 33, 256):
            with self.assertRaises(ValueError):
                overlay_palette.reserved_table(bad)


class Reserved32EncodeTest(unittest.TestCase):
    def assert_reserved32_respected(self, path):
        _hdr, _ramp, cells_list, pal_list = ascl_decode.decode_all(path)
        self.assertGreater(len(cells_list), 0)
        for frame_index, (cells, palette) in enumerate(zip(cells_list, pal_list)):
            self.assertIsNotNone(palette, "frame %d sin paleta" % frame_index)
            self.assertEqual(len(palette), 64)
            np.testing.assert_array_equal(
                palette[-32:], overlay_palette.RESERVED_RGB_32,
                "reservadas alteradas en frame %d" % frame_index)
            # compat v1: la cola de 10 sigue siendo la reserva de F7
            np.testing.assert_array_equal(
                palette[-10:], overlay_palette.RESERVED_RGB,
                "cola F7 alterada en frame %d" % frame_index)
            self.assertLess(
                int(cells.max()), len(palette) - 32,
                "una celda base usa un indice reservado en frame %d"
                % frame_index)
        return pal_list

    def test_adaptive_epochs_keep_the_32_stamped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "r32.ascl")
            encode_reserved32(path, "adaptive")
            pal_list = self.assert_reserved32_respected(path)
        # el corte duro debe producir mas de una epoca con base distinta
        base_first = pal_list[0][:-32]
        base_last = pal_list[-1][:-32]
        self.assertFalse(np.array_equal(base_first, base_last),
                         "adaptive no genero mas de una epoca")

    def test_dither_never_introduces_reserved_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "r32-dither.ascl")
            encode_reserved32(path, "global", dither_mode="auto")
            self.assert_reserved32_respected(path)


class MakeClipReservedArgTest(unittest.TestCase):
    def test_non_canonical_reserved_is_rejected_before_any_io(self):
        for bad in ("7", "16", "33"):
            with self.assertRaises(SystemExit):
                make_clip.main(["no-existe.mp4", "--reserved", bad,
                                "--palette-size", "64"])


if __name__ == "__main__":
    unittest.main()
