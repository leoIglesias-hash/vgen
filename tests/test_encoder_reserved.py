"""E-03/E-04: parametro `reserved` cableado y exclusion del rango reservado.

Contratos cubiertos (INT-001, DISENO-INTERVENCION-MATRICIAL §4):
- reserved=0 es byte-identico a la firma historica;
- pal_size debe cubrir reserved + 22;
- con reserved>0 las `reserved` entradas finales de cada epoca son bit-identicas
  a los RGB declarados por el operador (INV-4) y ninguna celda del video base
  usa un indice reservado (INV-3), en las cuatro estrategias de paleta y los
  cuatro modos, con y sin dither;
- los builders de bajo nivel rechazan reserved>0: la reserva se resuelve en
  make_global_palette con pal_size ya reducido.
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
import perceptual_palette  # noqa: E402


RESERVED_RGB = np.array(
    [[8, 8, 8], [40, 40, 40], [80, 80, 80], [120, 120, 120],
     [160, 160, 160], [200, 200, 200], [255, 255, 255], [255, 200, 0],
     [0, 200, 0], [0, 0, 0]], dtype=np.uint8)

ALGORITHMS = ("median-cut", "fast-octree", "kmeans-rgb", "kmeans-oklab")
PALETTE_MODES = ("global", "block", "adaptive", "per-frame")


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


def encode_reserved(path, palette_mode, algorithm, **options):
    defaults = dict(
        palette_algorithm=algorithm, pal_size=32, keyint=3,
        reserved=10, reserved_colors=RESERVED_RGB,
        adaptive_min_frames=2, adaptive_max_frames=4,
        palette_block_frames=4)
    defaults.update(options)
    return encode_fake_video(path, scene_frames(), palette_mode, **defaults)


def assert_reserved_respected(test, path):
    _hdr, _ramp, cells_list, pal_list = ascl_decode.decode_all(path)
    test.assertGreater(len(cells_list), 0)
    for frame_index, (cells, palette) in enumerate(zip(cells_list, pal_list)):
        test.assertIsNotNone(palette, "frame %d sin paleta" % frame_index)
        np.testing.assert_array_equal(
            palette[-len(RESERVED_RGB):], RESERVED_RGB,
            "reservadas alteradas en frame %d" % frame_index)
        base_count = len(palette) - len(RESERVED_RGB)
        test.assertLess(
            int(cells.max()), base_count,
            "una celda base usa un indice reservado en frame %d" % frame_index)
    return pal_list


class ReservedParameterTest(unittest.TestCase):
    def _frames(self):
        return [color_frame((10 + 12 * i, 40 + 9 * i, 200 - 15 * i))
                for i in range(8)]

    def test_reserved_zero_is_byte_identical_in_the_three_palette_paths(self):
        frames = self._frames()
        for palette_mode, algorithm in (("global", "kmeans-rgb"),
                                        ("adaptive", "kmeans-oklab"),
                                        ("per-frame", "median-cut")):
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

    def test_reserved_requires_operator_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "sin-colores.ascl")
            with self.assertRaises(ValueError):
                encode_fake_video(out_path, scene_frames(), "global",
                                  palette_algorithm="kmeans-rgb",
                                  pal_size=32, reserved=10)

    def test_reserved_range_excluded_in_all_strategies_and_modes(self):
        for algorithm in ALGORITHMS:
            for palette_mode in PALETTE_MODES:
                with tempfile.TemporaryDirectory() as directory:
                    out_path = os.path.join(directory, "reservado.ascl")
                    encode_reserved(out_path, palette_mode, algorithm)
                    pal_list = assert_reserved_respected(self, out_path)
                if palette_mode == "adaptive":
                    # el clip tiene un corte duro: la parte base debe cambiar
                    # entre epocas mientras las reservadas quedan identicas
                    base_first = pal_list[0][:-len(RESERVED_RGB)]
                    base_last = pal_list[-1][:-len(RESERVED_RGB)]
                    self.assertFalse(
                        np.array_equal(base_first, base_last),
                        "%s/adaptive no genero mas de una epoca" % algorithm)

    def test_dither_never_introduces_reserved_indices(self):
        for palette_mode in ("global", "adaptive"):
            with tempfile.TemporaryDirectory() as directory:
                out_path = os.path.join(directory, "dither.ascl")
                encode_reserved(out_path, palette_mode, "kmeans-oklab",
                                dither_mode="auto")
                assert_reserved_respected(self, out_path)

    def test_low_level_builders_reject_reserved(self):
        sample = [color_frame((10, 40, 200))[0]]
        with self.assertRaises(ValueError):
            perceptual_palette.build_perceptual_palette(sample, 64, reserved=10)
        with self.assertRaises(ValueError):
            encoder._kmeans_rgb_palette(sample, 64, reserved=10)


if __name__ == "__main__":
    unittest.main()
