# -*- coding: utf-8 -*-
"""E-19: orden canonico del pipeline y trellis en su caso degenerado.

El contrato que congela E-19 es cuantizar -> ditherear -> trellis -> emitir,
con el `--threshold` absorbido COMO trellis en vez de conviviendo con el. Estas
pruebas fijan las dos mitades: que el orden sea un dato importable (y no la
posicion accidental de unos bloques en el bucle) y que la etapa degenerada
reproduzca exactamente el camino historico.
"""
import os
import sys
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import trellis  # noqa: E402


PALETTE = np.array([
    [0, 0, 0],
    [4, 4, 4],
    [8, 8, 8],
    [80, 80, 80],
    [255, 255, 255],
], dtype=np.uint8)


def historic_threshold(cells, prev_cells, palette_rgb, threshold):
    """El revert tal como estaba escrito en el bucle antes de E-19 (sin E-18).

    Se reimplementa aparte a proposito: si el refactor cambiara la regla, esta
    copia independiente lo delata en vez de moverse con el.
    """
    current = cells[:, 0]
    delta = (palette_rgb[current].astype(np.int32)
             - palette_rgb[prev_cells[:, 0]].astype(np.int32))
    keep = np.einsum("ij,ij->i", delta, delta) <= threshold * threshold
    emitted = cells.copy()
    emitted[keep, 0] = prev_cells[keep, 0]
    return emitted


def make_cells(indices):
    """Celdas con una segunda columna arbitraria, para probar que se conserva."""
    indices = np.asarray(indices, dtype=np.uint8)
    extra = (indices.astype(np.uint16) * 7 % 251).astype(np.uint8)
    return np.stack([indices, extra], axis=1)


class CanonicalOrderTest(unittest.TestCase):
    def test_order_is_frozen_and_importable(self):
        self.assertEqual(trellis.CANONICAL_STAGES,
                         ("quantize", "dither", "trellis", "emit"))

    def test_trellis_runs_after_dither_and_before_emit(self):
        # Esta es la regla que E-18 violaba: el trellis leia celdas que el
        # dither ya habia decidido, pero corria como si fuera independiente.
        order = trellis.canonical_order_index
        self.assertLess(order("quantize"), order("dither"))
        self.assertLess(order("dither"), order("trellis"))
        self.assertLess(order("trellis"), order("emit"))

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            trellis.canonical_order_index("threshold")


class DegenerateTrellisTest(unittest.TestCase):
    def setUp(self):
        # Ninguna celda repite el indice del frame anterior: asi un revert
        # siempre es un cambio observable y los contadores no se inflan con
        # celdas que ya eran iguales.
        self.prev = make_cells([0, 1, 2, 3, 4, 0, 3, 2])
        self.cells = make_cells([1, 2, 1, 4, 3, 3, 0, 0])

    def test_matches_historic_threshold_path(self):
        for threshold in (1, 4, 8, 16, 32, 64, 128, 255):
            expected = historic_threshold(self.cells, self.prev, PALETTE,
                                          threshold)
            result, _details = trellis.apply_threshold_trellis(
                self.cells, self.prev, PALETTE, threshold)
            self.assertTrue(
                np.array_equal(result, expected),
                "el trellis degenerado difiere del camino historico en "
                "threshold %d" % threshold)

    def test_threshold_zero_is_a_no_op(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 0)
        self.assertTrue(np.array_equal(result, self.cells))
        self.assertEqual(details["reverted_cells"], 0)

    def test_missing_previous_frame_is_a_no_op(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, None, PALETTE, 64)
        self.assertTrue(np.array_equal(result, self.cells))
        self.assertEqual(details["reverted_cells"], 0)

    def test_never_mutates_the_input(self):
        # Invariante 4: `cells` jamas queda a medias.
        before = self.cells.copy()
        trellis.apply_threshold_trellis(self.cells, self.prev, PALETTE, 255)
        self.assertTrue(np.array_equal(self.cells, before))

    def test_other_columns_survive_the_revert(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 255)
        self.assertGreater(details["reverted_cells"], 0)
        self.assertTrue(np.array_equal(result[:, 1], self.cells[:, 1]))

    def test_protected_cells_are_never_reverted(self):
        # E-18 expresado sobre la etapa nueva: lo que el dither movio no se
        # congela aunque el umbral lo alcance.
        plain, plain_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 255)
        self.assertGreater(plain_details["reverted_cells"], 0)

        protected = np.zeros(self.cells.shape[0], dtype=bool)
        protected[::2] = True
        guarded, guarded_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 255, protected_mask=protected)

        self.assertGreater(guarded_details["protected_cells"], 0)
        self.assertTrue(
            np.array_equal(guarded[protected, 0], self.cells[protected, 0]),
            "una celda protegida fue revertida")
        self.assertTrue(
            np.array_equal(guarded[~protected], plain[~protected]),
            "proteger celdas cambio la decision sobre las demas")

    def test_protection_count_only_counts_rescued_cells(self):
        # Proteger celdas que el umbral no iba a revertir no debe inflar el
        # contador: si lo hiciera, las estadisticas de E-18 mentirian.
        _plain, plain_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 1)
        self.assertEqual(plain_details["reverted_cells"], 0)
        protected = np.ones(self.cells.shape[0], dtype=bool)
        _guarded, guarded_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, PALETTE, 1, protected_mask=protected)
        self.assertEqual(guarded_details["protected_cells"], 0)


if __name__ == "__main__":
    unittest.main()
