# -*- coding: utf-8 -*-
"""E-22: trellis temporal - el indice del frame anterior como segundo candidato.

Si emitir el indice previo saca la celda del DELTA y el error EXTRA contra el
pixel objetivo no supera el presupuesto, la celda se mueve. Con presupuesto 0
la salida es byte-identica a la historica; las celdas tramadas por el dither
nunca se mueven (la misma proteccion de E-18).
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
import trellis  # noqa: E402


PALETTE = np.array([
    [0, 0, 0],
    [10, 10, 10],
    [40, 40, 40],
    [200, 200, 200],
], dtype=np.uint8)

SQ3 = np.sqrt(3.0)


def make_cells(indices):
    indices = np.asarray(indices, dtype=np.uint8)
    extra = (indices.astype(np.uint16) * 7 % 251).astype(np.uint8)
    return np.stack([indices, extra], axis=1)


class TemporalTrellisUnitTest(unittest.TestCase):
    def setUp(self):
        self.pal = trellis.build_threshold_palette(PALETTE, "rgb")
        # celda 0: el indice previo esta MAS cerca del objetivo (extra < 0);
        # celda 1: moverla cuesta exactamente 30*sqrt(3) ~ 51,96;
        # celda 2: no cambio respecto del frame previo (no es candidata);
        # celda 3: moverla cuesta 200*sqrt(3) ~ 346 (nunca entra en presupuesto).
        self.cells = make_cells([2, 1, 3, 0])
        self.prev = make_cells([1, 2, 3, 3])
        targets = np.array([
            [12, 12, 12],
            [10, 10, 10],
            [200, 200, 200],
            [0, 0, 0],
        ], dtype=np.uint8)
        self.target = trellis.build_threshold_palette(targets, "rgb")

    def apply(self, budget, protected=None):
        return trellis.apply_temporal_trellis(
            self.cells, self.prev, self.target, self.pal, budget,
            protected_mask=protected)

    def test_budget_zero_and_missing_inputs_are_noops(self):
        for args in ((self.cells, self.prev, self.target, self.pal, 0),
                     (self.cells, None, self.target, self.pal, 50),
                     (self.cells, self.prev, self.target, None, 50)):
            result, details = trellis.apply_temporal_trellis(*args)
            self.assertIs(result, self.cells)
            self.assertEqual(details["temporal_cells"], 0)

    def test_negative_extra_is_a_free_win_even_with_tiny_budget(self):
        result, details = self.apply(0.001)
        self.assertEqual(details["temporal_cells"], 1)
        self.assertEqual(int(result[0, 0]), 1, "la celda 0 va al indice previo")
        self.assertEqual(int(result[1, 0]), 1, "la celda 1 excede el presupuesto")
        self.assertEqual(int(result[3, 0]), 0)

    def test_budget_bounds_the_extra_error_exactly(self):
        cost = 30.0 * SQ3  # celda 1: d(objetivo, prev) - d(objetivo, actual)
        _result, details = self.apply(cost - 0.01)
        self.assertEqual(details["temporal_cells"], 1)
        result, details = self.apply(cost + 0.01)
        self.assertEqual(details["temporal_cells"], 2)
        self.assertEqual(int(result[1, 0]), 2)
        # la celda sin cambio y la carisima quedan como estaban
        self.assertEqual(int(result[2, 0]), 3)
        self.assertEqual(int(result[3, 0]), 0)

    def test_protected_cells_are_never_moved_and_counted(self):
        protected = np.array([True, False, False, False])
        result, details = self.apply(0.001, protected=protected)
        self.assertEqual(details["temporal_cells"], 0)
        self.assertEqual(details["protected_cells"], 1)
        self.assertEqual(int(result[0, 0]), 2, "una celda protegida se movio")
        # proteger una celda que no iba a moverse no infla el contador
        elsewhere = np.array([False, False, True, True])
        _result, details = self.apply(0.001, protected=elsewhere)
        self.assertEqual(details["protected_cells"], 0)
        self.assertEqual(details["temporal_cells"], 1)

    def test_never_mutates_input_and_preserves_other_columns(self):
        before = self.cells.copy()
        result, details = self.apply(1000.0)
        self.assertGreater(details["temporal_cells"], 0)
        self.assertTrue(np.array_equal(self.cells, before))
        self.assertTrue(np.array_equal(result[:, 1], self.cells[:, 1]))


# ---- integracion: el mismo sintetico de E-18 (rampa gris que se corre) ----

WIDTH = 192
HEIGHT = 96


def gray_gradient_frame(shift):
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
        palette_mode="global", keyint=64, with_audio=False,
        palette_algorithm="kmeans-oklab", dump_cells=dump_path,
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


class TemporalTrellisEncodeTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.directory = holder.name

    def run_encode(self, tag, **options):
        out_path = os.path.join(self.directory, "%s.ascl" % tag)
        dump_path = os.path.join(self.directory, "%s.npz" % tag)
        info = encode_synthetic(out_path, dump_path, **options)
        with open(out_path, "rb") as handle:
            payload = handle.read()
        return info, indices_from_dump(dump_path), payload

    def test_budget_zero_is_byte_identical(self):
        plain_info, _plain, plain_bytes = self.run_encode("plain")
        info, _dump, temporal_bytes = self.run_encode(
            "temporal0", trellis_temporal=0)
        self.assertEqual(plain_bytes, temporal_bytes)
        self.assertEqual(int(info["trellis_temporal_cells"]), 0)
        self.assertFalse(plain_info["flags"] & encoder.FLAG_LOSSY)

    def test_generous_budget_moves_cells_shrinks_bytes_and_marks_lossy(self):
        _plain_info, plain, plain_bytes = self.run_encode("base")
        info, moved_dump, moved_bytes = self.run_encode(
            "temporal", trellis_temporal=255.0)
        self.assertGreater(int(info["trellis_temporal_cells"]), 0)
        self.assertGreater(int(info["trellis_temporal_frames"]), 0)
        self.assertTrue(info["flags"] & encoder.FLAG_LOSSY)
        self.assertLess(len(moved_bytes), len(plain_bytes),
                        "sacar celdas del DELTA debe achicar el archivo")
        # cada celda movida quedo EXACTAMENTE en el indice emitido del frame
        # anterior: eso es lo que la borra del DELTA
        for idx in range(1, len(FRAMES)):
            moved = moved_dump[idx] != plain[idx]
            if not np.any(moved):
                continue
            self.assertTrue(
                np.array_equal(moved_dump[idx][moved],
                               moved_dump[idx - 1][moved]),
                "una celda movida no coincide con el frame previo (frame %d)"
                % idx)

    def test_dithered_cells_survive_the_temporal_trellis(self):
        # E-18 sobre la etapa nueva: lo que el dither tramo no se mueve aunque
        # el presupuesto alcance. La salida del dither no depende de
        # prev_cells, asi que se lee comparando contra el encode sin trellis.
        _info, plain, _b = self.run_encode("ref")
        dither_info, dithered, _b2 = self.run_encode("dith", dither_mode="auto")
        self.assertGreater(int(dither_info["dither_changed_cells"]), 0)
        info, mixed, _b3 = self.run_encode(
            "dith_temporal", dither_mode="auto", trellis_temporal=255.0)
        self.assertGreater(int(info["trellis_temporal_protected_cells"]), 0,
                           "con presupuesto generoso el trellis debio chocar "
                           "con celdas tramadas")
        for idx in range(1, len(FRAMES)):
            tramadas = dithered[idx] != plain[idx]
            self.assertTrue(
                np.array_equal(mixed[idx][tramadas], dithered[idx][tramadas]),
                "el trellis temporal piso celdas tramadas en el frame %d" % idx)

    def test_negative_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "trellis-temporal"):
            self.run_encode("bad", trellis_temporal=-1)


if __name__ == "__main__":
    unittest.main()
