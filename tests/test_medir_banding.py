# -*- coding: utf-8 -*-
"""2026-10-17: tools/medir_banding.py aplica el proxy_banding de bench_ref a
piezas de video. Un degrade oscuro y liso contra la misma imagen escalonada
(pocos tonos, como el halo de intro_D) tiene que dar escalon, sobre todo en
la parte oscura; la imagen identica da 0; mas area escalonada da mas numero;
la parte clara no cuenta como oscura."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import medir_banding  # noqa: E402


def degrade(alto=32, ancho=128, desde=4, hasta=60):
    """Rojo oscuro horizontal, liso (un valor distinto cada pocos pixeles)."""
    rojo = np.linspace(desde, hasta, ancho).astype(np.float64)
    rgb = np.zeros((alto, ancho, 3), dtype=np.uint8)
    rgb[..., 0] = np.rint(rojo).astype(np.uint8)
    rgb[..., 1] = np.rint(rojo * 0.15).astype(np.uint8)
    rgb[..., 2] = np.rint(rojo * 0.1).astype(np.uint8)
    return rgb


def escalonado(rgb, paso=16):
    return ((rgb.astype(np.int32) // paso) * paso).astype(np.uint8)


class BandingTest(unittest.TestCase):
    def test_identico_da_cero(self):
        ref = degrade()
        b, bo = medir_banding.banding([ref] * 3, [ref] * 3)
        self.assertEqual(b, 0.0)
        self.assertEqual(bo, 0.0)

    def test_escalonado_da_escalon_en_lo_oscuro(self):
        ref = degrade()
        b, bo = medir_banding.banding([escalonado(ref)] * 2, [ref] * 2)
        self.assertGreater(b, 0.0)
        self.assertGreater(bo, 0.0)

    def test_un_contorno_mas_alto_da_mas(self):
        # Fondo oscuro plano; el decodificado le agrega el borde de un bloque
        # (lo que se ve como mancha). Un borde mas alto tiene que medir mas.
        plano = np.zeros((32, 64, 3), dtype=np.uint8)
        plano[..., 0] = 30
        resultados = []
        for alto_borde in (2, 6, 12):
            dec = plano.copy()
            dec[:, 32:, 0] = 30 + alto_borde
            resultados.append(medir_banding.banding([dec], [plano]))
        self.assertTrue(all(r[0] > 0 and r[1] > 0 for r in resultados))
        self.assertLess(resultados[0][0], resultados[1][0])
        self.assertLess(resultados[1][0], resultados[2][0])

    def test_la_parte_clara_no_cuenta_como_oscura(self):
        claro = degrade(desde=200, hasta=250)
        _, bo = medir_banding.banding([escalonado(claro, 16)], [claro])
        self.assertEqual(bo, 0.0)

    def test_comando_de_decodificacion(self):
        command = medir_banding.decode_command("ffmpeg", "p.mp4", 1280, 720)
        vf = command[command.index("-vf") + 1]
        self.assertIn("in_color_matrix=bt709:in_range=tv", vf)
        self.assertIn("format=rgb24", vf)
        self.assertEqual(command[-2:], ["rawvideo", "-"])


if __name__ == "__main__":
    unittest.main()
