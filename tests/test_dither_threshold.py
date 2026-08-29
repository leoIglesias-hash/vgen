# -*- coding: utf-8 -*-
"""E-18: interaccion dither/threshold.

El threshold corre DESPUES del dither y revierte celdas al valor del frame
anterior cuando el color apenas se movio. Sobre una celda tramada eso deshace
la decision del dither y rompe el patron Bayer de forma distinta en cada frame.
Desde E-18 el revert excluye las celdas que el dither movio.
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


# El frame tiene que dar para varios tiles de 16x16 DENTRO del presupuesto de
# celdas del dither: con 128x32 el 5 % (204 celdas) no llega a cubrir un tile
# (256) y el calibrado no acepta nada, dejando el test vacio.
WIDTH = 192
HEIGHT = 96
# Umbrales a barrer: la distancia entre grises vecinos depende de la paleta que
# elija kmeans, asi que el test busca el primero que realmente pise el dither en
# lugar de fijar un numero magico.
THRESHOLDS = (16, 32, 64, 96, 128, 160, 192, 224)


def gray_gradient_frame(shift):
    """Rampa gris (el sintetico que ya dispara el dither en las suites de F3)."""
    row = np.linspace(0.0, 255.0, WIDTH) + float(shift)
    gray = np.tile(np.clip(row, 0.0, 255.0).astype(np.uint8), (HEIGHT, 1))
    return np.repeat(gray[:, :, None], 3, axis=2), gray


FRAMES = [gray_gradient_frame(shift) for shift in (0, 2, 4, 6, 8, 10)]


def encode_synthetic(out_path, dump_path, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(FRAMES)

    defaults = dict(
        mode_name="pixel", cols=WIDTH, rows=HEIGHT, fps=15, pal_size=4,
        ramp_name="short", char_aspect=0.5, compress="auto",
        # El threshold solo existe con paleta global (pal_metric); keyint alto deja
        # un solo keyframe, asi los demas frames pasan por el revert.
        palette_mode="global", keyint=64, with_audio=False,
        palette_algorithm="kmeans-oklab", dump_cells=dump_path,
        # Lo que se prueba aca es la interaccion con el threshold, no los
        # frenos del calibrado: presupuesto amplio, sin piso de mejora y sin
        # histeresis temporal para que el dither se active desde el frame 0.
        dither_budget=0.5, dither_min_improvement=0.0, dither_window=1)
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size",
                           return_value=(WIDTH, HEIGHT)), \
            mock.patch.object(encoder, "iter_video_frames",
                              side_effect=fake_iter):
        return encoder.encode_video("synthetic.mp4", out_path, **defaults)


def indices_from_dump(dump_path):
    with np.load(dump_path) as data:
        return [np.asarray(data["frame_%04d" % idx][:, 0])
                for idx in range(len(FRAMES))]


class ThresholdDitherInteractionTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.directory = holder.name

    def run_encode(self, tag, **options):
        out_path = os.path.join(self.directory, "%s.ascl" % tag)
        dump_path = os.path.join(self.directory, "%s.npz" % tag)
        info = encode_synthetic(out_path, dump_path, **options)
        return info, indices_from_dump(dump_path)

    def test_threshold_never_reverts_a_dithered_cell(self):
        _, plain = self.run_encode("plain")
        dither_info, dithered = self.run_encode("dithered", dither_mode="auto")
        self.assertGreater(int(dither_info["dither_changed_cells"]), 0)
        self.assertEqual(
            int(dither_info["threshold_dither_protected_cells"]), 0,
            "sin threshold no hay nada que proteger")

        chosen = None
        for value in THRESHOLDS:
            info, mixed = self.run_encode("mixed_%d" % value,
                                          dither_mode="auto", threshold=value)
            if int(info["threshold_dither_protected_cells"]):
                chosen = (value, info, mixed)
                break
        self.assertIsNotNone(
            chosen, "ningun threshold del barrido llego a pisar celdas "
                    "tramadas: el test quedaria vacio")
        _value, info, mixed = chosen
        self.assertGreater(int(info["threshold_dither_protected_frames"]), 0)
        for idx in range(1, len(FRAMES)):
            # El dither no depende de prev_cells, asi que su salida es la misma
            # con y sin threshold: lo que movio se lee comparando contra plain.
            moved = dithered[idx] != plain[idx]
            self.assertTrue(
                np.array_equal(mixed[idx][moved], dithered[idx][moved]),
                "el threshold revirtio celdas tramadas en el frame %d" % idx)

    def test_threshold_without_dither_still_reverts(self):
        # E-18 no debe filtrarse al camino sin dither: ahi el revert sigue
        # siendo el historico y el contador queda en cero.
        _, plain = self.run_encode("bare")
        for value in THRESHOLDS:
            info, thresholded = self.run_encode("bare_%d" % value,
                                                threshold=value)
            self.assertEqual(
                int(info["threshold_dither_protected_cells"]), 0)
            self.assertEqual(
                int(info["threshold_dither_protected_frames"]), 0)
            if any(not np.array_equal(thresholded[idx], plain[idx])
                   for idx in range(1, len(FRAMES))):
                return
        self.fail("ningun threshold del barrido cambio la salida sin dither: "
                  "el test quedaria vacio")

    def test_protection_counters_are_reported(self):
        info, _ = self.run_encode("counters", dither_mode="auto")
        self.assertIn("threshold_dither_protected_cells", info)
        self.assertIn("threshold_dither_protected_frames", info)


if __name__ == "__main__":
    unittest.main()
