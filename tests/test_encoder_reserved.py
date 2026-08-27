"""E-03: parametro `reserved` cableado por la cadena de paleta, default 0.

Contrato de la tarea: con reserved=0 la salida es byte-identica a la firma
historica; pal_size debe cubrir reserved + 22; y hasta que E-04 implemente la
exclusion del rango reservado, reserved>0 falla explicito en vez de ser un
no-op silencioso (E-04 reemplaza ese guard y este test).
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import encoder  # noqa: E402
import perceptual_palette  # noqa: E402


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


def encode_fake_video(path, frames, palette_mode, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(frames)

    defaults = dict(
        mode_name="pixel", cols=24, rows=16, fps=15, pal_size=8,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode=palette_mode, keyint=4, with_audio=False,
        palette_algorithm="kmeans-oklab")
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size", return_value=(24, 16)), \
            mock.patch.object(encoder, "iter_video_frames", side_effect=fake_iter):
        return encoder.encode_video("synthetic.mp4", path, **defaults)


PALETTE_PATHS = (
    ("global", "kmeans-rgb"),
    ("adaptive", "kmeans-oklab"),
    ("per-frame", "median-cut"),
)


class ReservedParameterTest(unittest.TestCase):
    def _frames(self):
        return [color_frame((10 + 12 * i, 40 + 9 * i, 200 - 15 * i))
                for i in range(8)]

    def test_reserved_zero_is_byte_identical_in_the_three_palette_paths(self):
        frames = self._frames()
        for palette_mode, algorithm in PALETTE_PATHS:
            with tempfile.TemporaryDirectory() as directory:
                base_path = os.path.join(directory, "base.ascl")
                wired_path = os.path.join(directory, "wired.ascl")
                encode_fake_video(base_path, frames, palette_mode,
                                  palette_algorithm=algorithm)
                encode_fake_video(wired_path, frames, palette_mode,
                                  palette_algorithm=algorithm, reserved=0)
                with open(base_path, "rb") as stream:
                    base_bytes = stream.read()
                with open(wired_path, "rb") as stream:
                    wired_bytes = stream.read()
            self.assertEqual(base_bytes, wired_bytes,
                             "reserved=0 cambio bytes en %s/%s" %
                             (palette_mode, algorithm))

    def test_pal_size_must_cover_reserved_range(self):
        with self.assertRaises(ValueError):
            encoder.validate_encode_options(
                "pixel", 24, 16, 15, 16, 0.5, "global", "none", "nearest",
                reserved=10)
        with self.assertRaises(ValueError):
            encoder.validate_encode_options(
                "pixel", 24, 16, 15, 32, 0.5, "global", "none", "nearest",
                reserved=-1)
        encoder.validate_encode_options(
            "pixel", 24, 16, 15, 32, 0.5, "global", "none", "nearest",
            reserved=10)

    def test_reserved_positive_fails_loudly_until_e04(self):
        frames = self._frames()
        for palette_mode, algorithm in PALETTE_PATHS:
            with tempfile.TemporaryDirectory() as directory:
                out_path = os.path.join(directory, "reserved.ascl")
                with self.assertRaises(NotImplementedError):
                    encode_fake_video(out_path, frames, palette_mode,
                                      palette_algorithm=algorithm,
                                      pal_size=64, reserved=10)
        with self.assertRaises(NotImplementedError):
            perceptual_palette.build_perceptual_palette(
                [color_frame((10, 40, 200))[0]], 64, reserved=10)


if __name__ == "__main__":
    unittest.main()
