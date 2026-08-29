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

# E-20: dos pares con la MISMA distancia sRGB (8 por canal) pero en extremos
# opuestos del rango. Es el caso que separa las dos metricas.
CONTRAST_PALETTE = np.array([
    [0, 0, 0],
    [8, 8, 8],
    [247, 247, 247],
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
        # El trellis recibe la paleta YA en el espacio de la metrica (E-20); la
        # referencia historica sigue partiendo del uint8 crudo, a proposito.
        self.palette = trellis.build_threshold_palette(PALETTE, "rgb")

    def test_matches_historic_threshold_path(self):
        for threshold in (1, 4, 8, 16, 32, 64, 128, 255):
            expected = historic_threshold(self.cells, self.prev, PALETTE,
                                          threshold)
            result, _details = trellis.apply_threshold_trellis(
                self.cells, self.prev, self.palette, threshold)
            self.assertTrue(
                np.array_equal(result, expected),
                "el trellis degenerado difiere del camino historico en "
                "threshold %d" % threshold)

    def test_threshold_zero_is_a_no_op(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.palette, 0)
        self.assertTrue(np.array_equal(result, self.cells))
        self.assertEqual(details["reverted_cells"], 0)

    def test_missing_previous_frame_is_a_no_op(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, None, self.palette, 64)
        self.assertTrue(np.array_equal(result, self.cells))
        self.assertEqual(details["reverted_cells"], 0)

    def test_never_mutates_the_input(self):
        # Invariante 4: `cells` jamas queda a medias.
        before = self.cells.copy()
        trellis.apply_threshold_trellis(self.cells, self.prev, self.palette, 255)
        self.assertTrue(np.array_equal(self.cells, before))

    def test_other_columns_survive_the_revert(self):
        result, details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.palette, 255)
        self.assertGreater(details["reverted_cells"], 0)
        self.assertTrue(np.array_equal(result[:, 1], self.cells[:, 1]))

    def test_protected_cells_are_never_reverted(self):
        # E-18 expresado sobre la etapa nueva: lo que el dither movio no se
        # congela aunque el umbral lo alcance.
        plain, plain_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.palette, 255)
        self.assertGreater(plain_details["reverted_cells"], 0)

        protected = np.zeros(self.cells.shape[0], dtype=bool)
        protected[::2] = True
        guarded, guarded_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.palette, 255, protected_mask=protected)

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
            self.cells, self.prev, self.palette, 1)
        self.assertEqual(plain_details["reverted_cells"], 0)
        protected = np.ones(self.cells.shape[0], dtype=bool)
        _guarded, guarded_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.palette, 1, protected_mask=protected)
        self.assertEqual(guarded_details["protected_cells"], 0)


class ThresholdMetricTest(unittest.TestCase):
    """E-20: el umbral medido en Oklab en vez de euclidea sRGB."""

    def setUp(self):
        # Celda 0: negro -> casi negro. Celda 1: casi blanco -> blanco.
        # En sRGB los dos saltos son identicos (8 por canal).
        self.prev = make_cells([0, 2])
        self.cells = make_cells([1, 3])
        self.rgb = trellis.build_threshold_palette(CONTRAST_PALETTE, "rgb")
        self.lab = trellis.build_threshold_palette(CONTRAST_PALETTE, "oklab")

    def distances(self, palette):
        delta = palette[self.cells[:, 0]] - palette[self.prev[:, 0]]
        return np.sqrt(np.einsum("ij,ij->i", delta, delta))

    def test_unknown_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            trellis.build_threshold_palette(CONTRAST_PALETTE, "lab")

    def test_rgb_palette_is_wide_enough_for_squared_distance(self):
        # En int16 el einsum de la distancia al cuadrado desborda (195.075).
        self.assertEqual(self.rgb.dtype, np.int32)
        worst = np.array([[255, 255, 255]], dtype=np.int32)
        self.assertEqual(int(np.einsum("ij,ij->i", worst, worst)[0]), 195075)

    def test_srgb_cannot_tell_the_two_jumps_apart(self):
        dark, light = self.distances(self.rgb)
        self.assertAlmostEqual(float(dark), float(light), places=9)

    def test_oklab_sees_the_dark_jump_as_much_larger(self):
        # Este es el motivo entero de E-20: el mismo salto numerico en sRGB se
        # ve mucho mas en las sombras que en las luces.
        dark, light = self.distances(self.lab)
        self.assertGreater(float(dark), float(light) * 2.0)

    def test_metrics_disagree_on_what_to_freeze(self):
        dark, light = self.distances(self.lab)
        # Un umbral entre los dos: en Oklab congela solo el salto de las luces.
        between = float(light + dark) / 2.0
        lab_result, lab_details = trellis.apply_threshold_trellis(
            self.cells, self.prev, self.lab, between)
        self.assertEqual(lab_details["reverted_cells"], 1)
        self.assertEqual(int(lab_result[0, 0]), int(self.cells[0, 0]),
                         "Oklab no deberia congelar el salto en las sombras")
        self.assertEqual(int(lab_result[1, 0]), int(self.prev[1, 0]),
                         "Oklab deberia congelar el salto en las luces")

        # Con sRGB no hay umbral capaz de separarlos: o los congela a los dos o
        # a ninguno, porque para esa metrica son el mismo salto.
        rgb_dark, _rgb_light = self.distances(self.rgb)
        for threshold in (float(rgb_dark) - 0.5, float(rgb_dark) + 0.5):
            _result, details = trellis.apply_threshold_trellis(
                self.cells, self.prev, self.rgb, threshold)
            self.assertIn(details["reverted_cells"], (0, 2))


if __name__ == "__main__":
    unittest.main()
