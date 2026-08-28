#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-08 — best_deflate: fallback, minimo real, y simetria en los cinco puntos."""
import os
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))

import numpy as np  # noqa: E402

import ascl_v2  # noqa: E402
import deflate_util  # noqa: E402
import encoder  # noqa: E402
import regional_codec_v2  # noqa: E402


PAYLOAD = (b"ASCILINE" * 512) + bytes(range(256)) * 8


class _FakeZopfli(object):
    """Doble de zopfli.zlib con salida controlable."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def compress(self, data, numiterations=15):
        self.calls += 1
        return self.result


class BestDeflateTest(unittest.TestCase):
    def test_sin_zopfli_devuelve_zlib_exacto(self):
        original = deflate_util._zopfli_zlib
        deflate_util._zopfli_zlib = None
        try:
            out = deflate_util.best_deflate(PAYLOAD, 9)
        finally:
            deflate_util._zopfli_zlib = original
        self.assertEqual(out, zlib.compress(PAYLOAD, 9))

    def test_gana_el_candidato_menor_y_empate_conserva_zlib(self):
        reference = zlib.compress(PAYLOAD, 9)
        original = deflate_util._zopfli_zlib

        shorter = zlib.compress(PAYLOAD, 9)[:-1]  # solo para comparar longitud
        deflate_util._zopfli_zlib = _FakeZopfli(shorter)
        try:
            self.assertEqual(deflate_util.best_deflate(PAYLOAD, 9), shorter)
        finally:
            deflate_util._zopfli_zlib = original

        deflate_util._zopfli_zlib = _FakeZopfli(reference + b"x")
        try:
            self.assertEqual(deflate_util.best_deflate(PAYLOAD, 9), reference)
        finally:
            deflate_util._zopfli_zlib = original

        deflate_util._zopfli_zlib = _FakeZopfli(bytes(reference))  # empate
        try:
            self.assertEqual(deflate_util.best_deflate(PAYLOAD, 9), reference)
        finally:
            deflate_util._zopfli_zlib = original

    def test_stream_siempre_es_zlib_valido(self):
        out = deflate_util.best_deflate(PAYLOAD, 9)
        self.assertEqual(zlib.decompress(out), PAYLOAD)

    @unittest.skipUnless(deflate_util.have_zopfli(), "zopfli no instalado")
    def test_zopfli_real_no_empeora_y_roundtrip_exacto(self):
        out = deflate_util.best_deflate(PAYLOAD, 9)
        self.assertLessEqual(len(out), len(zlib.compress(PAYLOAD, 9)))
        self.assertEqual(zlib.decompress(out), PAYLOAD)

    def test_simetria_los_cinco_puntos_comparten_el_mismo_compresor(self):
        # La trampa de E-08: transcode_ascl_bytes compara el payload v1 heredado
        # contra los candidatos v2. Si encoder y transcodificador usaran
        # compresores distintos, la comparacion seria asimetrica. Verificacion
        # explicita: los tres modulos referencian el MISMO objeto funcion.
        self.assertIs(encoder.best_deflate, deflate_util.best_deflate)
        self.assertIs(ascl_v2.best_deflate, deflate_util.best_deflate)
        self.assertIs(regional_codec_v2.best_deflate, deflate_util.best_deflate)

    def test_encode_frame_pasa_por_best_deflate(self):
        calls = []

        def spy(data, level=9, iterations=None):
            calls.append(len(data))
            return deflate_util.best_deflate(data, level, iterations)

        cells = np.arange(64, dtype=np.uint8).reshape(64, 1) % 7
        prev = cells.copy()
        prev[3, 0] = 200
        original = encoder.best_deflate
        encoder.best_deflate = spy
        try:
            encoder.encode_frame(cells, prev, encoder.MODE_PIXEL, 1,
                                 False, "auto", True)
        finally:
            encoder.best_deflate = original
        # full + delta + mask = tres compresiones por frame delta
        self.assertEqual(len(calls), 3)

    def test_predictor_y_regional_pasan_por_best_deflate(self):
        calls = []

        def spy(data, level=9, iterations=None):
            calls.append(len(data))
            return deflate_util.best_deflate(data, level, iterations)

        matrix = (np.arange(32 * 32, dtype=np.uint16) % 11).astype(np.uint8)
        matrix = matrix.reshape(32, 32)

        original = ascl_v2.best_deflate
        ascl_v2.best_deflate = spy
        try:
            ascl_v2.encode_predictor_payload(matrix, True, zlib_level=9)
        finally:
            ascl_v2.best_deflate = original
        self.assertEqual(len(calls), 3)  # LEFT, TOP, GRADIENT

        del calls[:]
        original = regional_codec_v2.best_deflate
        regional_codec_v2.best_deflate = spy
        try:
            regional_codec_v2.encode_payload(matrix, previous=None,
                                             tile_size=16, zlib_level=9)
        finally:
            regional_codec_v2.best_deflate = original
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
