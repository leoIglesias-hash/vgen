# -*- coding: utf-8 -*-
"""E-21: jerarquia de costo del trellis.

El contrato: proxy barato para EXPLORAR, zlib-9 puro para comparar
FINALISTAS (misma decision con o sin Zopfli instalado, regla 5) y Zopfli
(best_deflate) UNA sola vez, sobre el GANADOR ya elegido. Estas pruebas
fijan la escalera en trellis.py y verifican que los tres puntos que
decidian con best_deflate por candidato (emisor v1, predictores v2 y la
interna regional/predictor del transcodificador) ahora eligen en zlib-9
y pagan un solo campeon.
"""
import os
import sys
import unittest
import zlib

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_v2  # noqa: E402
import deflate_util  # noqa: E402
import encoder  # noqa: E402
import regional_codec_v2  # noqa: E402
import trellis  # noqa: E402

from tests.test_ascl_v2 import delta_payload, make_block, make_v1  # noqa: E402


class CostLadderTest(unittest.TestCase):
    def test_ladder_is_frozen_and_importable(self):
        self.assertEqual(trellis.COST_LADDER, ("proxy", "zlib9", "zopfli"))

    def test_proxy_orders_by_compressibility_without_compressing(self):
        flat = b"\x00" * 4096
        mixed = bytes(range(256)) * 16
        self.assertEqual(trellis.proxy_cost(b""), 0.0)
        # un solo simbolo: entropia 0
        self.assertEqual(trellis.proxy_cost(flat), 0.0)
        # 256 simbolos uniformes: 8 bits por byte -> n bytes estimados
        self.assertAlmostEqual(trellis.proxy_cost(mixed), 4096.0)
        self.assertLess(trellis.proxy_cost(flat), trellis.proxy_cost(mixed))
        # determinista: mismo input, misma cota
        self.assertEqual(trellis.proxy_cost(mixed), trellis.proxy_cost(mixed))

    def test_finalist_is_pure_zlib9_in_every_environment(self):
        data = bytes(range(256)) * 7 + b"cola"
        self.assertEqual(trellis.finalist_deflate(data), zlib.compress(data, 9))

    def test_champion_is_best_deflate_and_never_worse_than_finalist(self):
        data = b"ASCILINE" * 500
        champ = trellis.champion_deflate(data)
        self.assertEqual(champ, deflate_util.best_deflate(data, 9))
        self.assertLessEqual(len(champ), len(trellis.finalist_deflate(data)))


def _delta_cells(seed=7):
    """Frame delta tipico: pocas celdas cambiadas sobre una base pseudoaleatoria."""
    rng = np.random.RandomState(seed)
    prev = rng.randint(0, 256, size=(4096, 1)).astype(np.uint8)
    cells = prev.copy()
    idx = rng.choice(4096, size=64, replace=False)
    cells[idx, 0] = (cells[idx, 0].astype(np.uint16) + 1).astype(np.uint8)
    return cells, prev


class EncodeFrameHierarchyTest(unittest.TestCase):
    def test_champion_runs_once_and_only_on_the_winner(self):
        cells, prev = _delta_cells()
        calls = []
        original = trellis.champion_deflate

        def spy(data):
            calls.append(bytes(data))
            return original(data)

        trellis.champion_deflate = spy
        try:
            _tag, payload = encoder.encode_frame(
                cells, prev, encoder.MODE_PIXEL, 1, False, "auto", True)
        finally:
            trellis.champion_deflate = original
        self.assertEqual(len(calls), 1,
                         "Zopfli debe pagarse una sola vez por frame")
        self.assertEqual(payload, original(calls[0]),
                         "el payload emitido es el campeon del ganador")

    def test_fast_deflate_is_the_selection_path_without_the_champion(self):
        cells, prev = _delta_cells()
        original = trellis.champion_deflate

        def bomb(_data):
            raise AssertionError("fast_deflate no debe pagar el campeon")

        trellis.champion_deflate = bomb
        try:
            tag_fast, payload_fast = encoder.encode_frame(
                cells, prev, encoder.MODE_PIXEL, 1, False, "auto", True,
                fast_deflate=True)
        finally:
            trellis.champion_deflate = original
        tag_full, payload_full = encoder.encode_frame(
            cells, prev, encoder.MODE_PIXEL, 1, False, "auto", True)
        # medir (E-17) y emitir eligen el MISMO candidato...
        self.assertEqual(tag_fast, tag_full)
        # ...y el campeon nunca empeora al ganador
        self.assertLessEqual(len(payload_full), len(payload_fast))

    def test_the_choice_cannot_depend_on_the_champion_compressor(self):
        # La eleccion del tag ocurre en zlib-9: un campeon que comprimiera
        # distinto (como Zopfli con otras iteraciones) no puede moverla.
        cells, prev = _delta_cells(11)
        original = trellis.champion_deflate
        trellis.champion_deflate = lambda _data: b"X"
        try:
            tag_weird, payload_weird = encoder.encode_frame(
                cells, prev, encoder.MODE_PIXEL, 1, False, "auto", True)
        finally:
            trellis.champion_deflate = original
        tag_fast, _payload = encoder.encode_frame(
            cells, prev, encoder.MODE_PIXEL, 1, False, "auto", True,
            fast_deflate=True)
        self.assertEqual(tag_weird, tag_fast)
        self.assertEqual(payload_weird, b"X")


class PredictorHierarchyTest(unittest.TestCase):
    ROWS, COLS = 32, 33

    def _plane(self):
        y, x = np.indices((self.ROWS, self.COLS))
        return ((x + 3 * y) % 251).astype(np.uint8)

    def test_selection_in_zlib9_champion_only_on_the_winner(self):
        plane = self._plane()
        # referencia independiente del ganador por zlib-9 (con el mismo
        # desempate por id de predictor)
        expected = min(
            (len(zlib.compress(
                ascl_v2._predict_residual(plane, p).tobytes(), 9)), p)
            for p in (ascl_v2.PRED_LEFT, ascl_v2.PRED_TOP,
                      ascl_v2.PRED_GRADIENT))[1]
        _tag, payload, predictor = ascl_v2.encode_predictor_payload(
            plane, keyframe=True)
        self.assertEqual(predictor, expected)
        residual = ascl_v2._predict_residual(plane, predictor)
        self.assertEqual(
            payload,
            bytes((predictor,)) +
            deflate_util.best_deflate(residual.tobytes(), 9))

    def test_fast_deflate_returns_the_winners_zlib9_payload(self):
        plane = self._plane()
        _tag, payload, predictor = ascl_v2.encode_predictor_payload(
            plane, keyframe=True, fast_deflate=True)
        residual = ascl_v2._predict_residual(plane, predictor)
        self.assertEqual(
            payload,
            bytes((predictor,)) + zlib.compress(residual.tobytes(), 9))


class TranscodeHierarchyTest(unittest.TestCase):
    def test_one_champion_per_frame_and_exact_roundtrip(self):
        rows = cols = 32
        n = rows * cols
        y, x = np.indices((rows, cols))
        first = ((x + 3 * y) % 251).astype(np.uint8).reshape(-1)
        second = ((first.astype(np.uint16) + 1) % 251).astype(np.uint8)
        palette = bytes(component for value in range(256)
                        for component in (value, value, value))
        source = make_v1([
            make_block(ascl_v2.TAG_RAW, palette, first.tobytes()),
            make_block(ascl_v2.TAG_DELTA, None,
                       delta_payload(range(n), second.tolist())),
        ], cols, rows, pal_size=256, flags=12)

        counts = {"n": 0}
        original = deflate_util.best_deflate

        def spy(data, level=9, iterations=None):
            counts["n"] += 1
            return original(data, level, iterations)

        # los modulos importaron el simbolo por nombre: se parchea en cada uno
        ascl_v2.best_deflate = spy
        regional_codec_v2.best_deflate = spy
        try:
            converted, stats = ascl_v2.transcode_ascl_bytes(source)
        finally:
            ascl_v2.best_deflate = original
            regional_codec_v2.best_deflate = original

        self.assertEqual(counts["n"], stats["n_frames"],
                         "un campeon por frame: ni mas (candidatos "
                         "descartados) ni menos (el ganador siempre cierra)")
        _header, frames = ascl_v2.decode_ascl_v2_bytes(converted)
        np.testing.assert_array_equal(frames[0]["cells"].reshape(-1), first)
        np.testing.assert_array_equal(frames[1]["cells"].reshape(-1), second)

    def test_regional_fast_mode_only_changes_the_compressor(self):
        rng = np.random.RandomState(31)
        current = rng.randint(0, 4, size=(40, 40)).astype(np.uint8)
        fast = regional_codec_v2.encode_payload(current, tile_size=16,
                                                fast_deflate=True)
        slow = regional_codec_v2.encode_payload(current, tile_size=16)
        # mismos comandos y mismo stream crudo: solo cambia el compresor
        self.assertEqual(fast.raw_payload, slow.raw_payload)
        self.assertEqual(fast.command_counts, slow.command_counts)
        self.assertEqual(fast.zlib_payload,
                         zlib.compress(fast.raw_payload, 9))
        self.assertLessEqual(len(slow.zlib_payload), len(fast.zlib_payload))


if __name__ == "__main__":
    unittest.main()
