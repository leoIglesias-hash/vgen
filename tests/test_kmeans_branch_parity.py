# -*- coding: utf-8 -*-
"""E-01: ambas ramas de _kmeans_rgb_palette devuelven una paleta ordenada.

El bug corregido: la rama OpenCV devolvia los centros sin el lexsort que el
fallback NumPy si aplicaba, asi que el mismo input producia archivos distintos
segun hubiera cv2 completo o no.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
import encoder  # noqa: E402


def _sample_images(seed=7):
    rng = np.random.RandomState(seed)
    return [rng.randint(0, 256, size=(48, 64, 3), dtype=np.uint8)
            for _ in range(3)]


def _is_lexsorted(palette):
    keys = [tuple(int(v) for v in row) for row in palette]
    return keys == sorted(keys)


class KmeansBranchParity(unittest.TestCase):
    def test_default_branch_is_sorted(self):
        palette = encoder._kmeans_rgb_palette(_sample_images(), 16)
        self.assertEqual(palette.shape, (16, 3))
        self.assertTrue(_is_lexsorted(palette),
                        "la rama activa no devuelve la paleta ordenada")

    def test_numpy_fallback_is_sorted(self):
        samples = np.concatenate(
            [im.reshape(-1, 3) for im in _sample_images()], axis=0
        ).astype(np.float32)[:4096]
        palette = encoder._sort_palette_centers(
            encoder._kmeans_rgb_numpy(samples, 16))
        self.assertEqual(palette.shape, (16, 3))
        self.assertTrue(_is_lexsorted(palette))

    def test_sort_is_deterministic_permutation(self):
        base = np.array([[3, 2, 1], [1, 2, 3], [2, 2, 2], [1, 2, 2]],
                        dtype=np.uint8)
        shuffled = base[[2, 0, 3, 1]]
        a = encoder._sort_palette_centers(base)
        b = encoder._sort_palette_centers(shuffled)
        self.assertTrue(np.array_equal(a, b),
                        "el orden no es independiente de la enumeracion")

    def test_cv2_branch_matches_sorting_contract(self):
        try:
            import cv2  # noqa: F401
        except Exception:
            self.skipTest("sin OpenCV en este entorno")
        palette = encoder._kmeans_rgb_palette(_sample_images(11), 32)
        self.assertTrue(_is_lexsorted(palette),
                        "la rama OpenCV devuelve centros sin ordenar")


if __name__ == "__main__":
    unittest.main()
