# -*- coding: utf-8 -*-
"""E-23: trellis espacial - fusionar el valor mas raro de un tile cuando eso
cruza 17->16, 5->4 o 3->2 valores distintos (opcode regional v2 mas barato).

El cruce se fuerza en el ENCODER (etapa trellis): el transcodificador v2
sigue siendo lossless exacto respecto del v1 emitido. Con presupuesto 0 la
salida es byte-identica a la historica.
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


# Paleta de grises separados de a 10: las distancias son multiplos de
# 10*sqrt(3) y los presupuestos del test se calculan exactos.
PALETTE = np.arange(26, dtype=np.uint8)[:, None].repeat(3, axis=1) * 10
SQ3 = np.sqrt(3.0)


def make_cells(indices):
    indices = np.asarray(indices, dtype=np.uint8)
    extra = (indices.astype(np.uint16) * 7 % 251).astype(np.uint8)
    return np.stack([indices.reshape(-1), extra.reshape(-1)], axis=1)


def targets_for(indices):
    """Objetivos = el color exacto de la paleta elegida (dist_rare = 0)."""
    flat = np.asarray(indices, dtype=np.uint8).reshape(-1)
    return trellis.build_threshold_palette(PALETTE[flat], "rgb")


class SpatialTrellisUnitTest(unittest.TestCase):
    def setUp(self):
        self.pal = trellis.build_threshold_palette(PALETTE, "rgb")

    def apply(self, grid, budget, tile_size, protected=None):
        grid = np.asarray(grid, dtype=np.uint8)
        cells = make_cells(grid)
        result, details = trellis.apply_spatial_trellis(
            cells, targets_for(grid), self.pal, budget, grid.shape,
            tile_size, protected_mask=protected)
        return cells, result, details

    def test_crossing_5_to_4_merges_the_rare_value_to_its_nearest(self):
        # tile 4x4 con valores {0,1,2,3,4}; el 4 aparece UNA vez. Fusionarlo
        # al 3 (su vecino mas cercano) cuesta exactamente 10*sqrt(3).
        grid = np.array([[4, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2]])
        cost = 10.0 * SQ3
        _cells, result, details = self.apply(grid, cost + 0.01, 4)
        self.assertEqual(details["spatial_tiles"], 1)
        self.assertEqual(details["spatial_cells"], 1)
        self.assertEqual(int(result[0, 0]), 3, "el raro se fusiona al vecino")
        self.assertEqual(len(np.unique(result[:, 0])), 4)
        # presupuesto insuficiente: no se toca nada
        _cells, result, details = self.apply(grid, cost - 0.01, 4)
        self.assertEqual(details["spatial_tiles"], 0)
        self.assertEqual(int(result[0, 0]), 4)

    def test_non_crossing_counts_are_untouched(self):
        # 4 distintos (ya PACK2) y 2 distintos (ya PACK1): nunca candidatos
        for row in ([0, 1, 2, 3], [0, 1, 0, 1]):
            grid = np.tile(np.asarray(row, dtype=np.uint8), (4, 1))
            cells, result, details = self.apply(grid, 1000.0, 4)
            self.assertEqual(details["spatial_tiles"], 0)
            self.assertIs(result, cells)

    def test_crossing_3_to_2_breaks_rare_ties_by_lower_value(self):
        # {0 x14, 5 x1, 9 x1}: empate de rareza -> se fusiona el 5 (menor), y
        # su reemplazo mas barato es el 9 (40*sqrt(3) contra 50*sqrt(3) del 0)
        grid = np.zeros((4, 4), dtype=np.uint8)
        grid[0, 0] = 5
        grid[3, 3] = 9
        _cells, result, details = self.apply(grid, 40.0 * SQ3 + 0.01, 4)
        self.assertEqual(details["spatial_tiles"], 1)
        self.assertEqual(int(result[0, 0]), 9)
        self.assertEqual(int(result[15, 0]), 9, "el 9 no se toca")
        self.assertEqual(len(np.unique(result[:, 0])), 2)

    def test_crossing_17_to_16(self):
        # tile 5x5 con 17 valores distintos: 0..16 y los 8 lugares restantes
        # repiten 0. Los valores 1..16 empatan en rareza y el desempate elige
        # el MENOR (1), cuyo reemplazo mas barato es el 0.
        flat = list(range(17)) + [0] * 8
        grid = np.asarray(flat, dtype=np.uint8).reshape(5, 5)
        _cells, result, details = self.apply(grid, 10.0 * SQ3 + 0.01, 5)
        self.assertEqual(details["spatial_tiles"], 1)
        self.assertEqual(len(np.unique(result[:, 0])), 16)
        self.assertEqual(int(result[1, 0]), 0, "1 se fusiona al 0")
        self.assertEqual(int(result[16, 0]), 16, "el 16 no se toca")

    def test_protected_rare_cell_blocks_the_tile(self):
        grid = np.array([[4, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2]])
        protected = np.zeros(16, dtype=bool)
        protected[0] = True  # la celda del valor raro
        cells, result, details = self.apply(grid, 1000.0, 4,
                                            protected=protected)
        self.assertEqual(details["spatial_tiles"], 0)
        self.assertEqual(details["blocked_tiles"], 1)
        self.assertIs(result, cells)

    def test_budget_zero_is_a_noop_and_input_never_mutates(self):
        grid = np.array([[4, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2],
                         [3, 0, 1, 2]])
        cells, result, details = self.apply(grid, 0, 4)
        self.assertIs(result, cells)
        self.assertEqual(details["spatial_tiles"], 0)
        cells, result, _details = self.apply(grid, 1000.0, 4)
        self.assertTrue(np.array_equal(cells[:, 0].reshape(4, 4), grid),
                        "el argumento fue mutado")
        self.assertTrue(np.array_equal(result[:, 1], cells[:, 1]),
                        "las otras columnas deben sobrevivir")

    def test_grid_mismatch_is_rejected(self):
        cells = make_cells(np.zeros((4, 4), dtype=np.uint8))
        with self.assertRaisesRegex(ValueError, "grid_shape"):
            trellis.apply_spatial_trellis(
                cells, targets_for(np.zeros((4, 4))), self.pal, 10.0,
                (5, 5), 4)


# ---- integracion: gradiente con paleta 32 -> tiles de ~3 valores ----

WIDTH = 192
HEIGHT = 96
BUDGETS = (4, 8, 16, 32, 64)


def gray_gradient_frame(shift):
    row = np.linspace(0.0, 255.0, WIDTH) + float(shift)
    gray = np.tile(np.clip(row, 0.0, 255.0).astype(np.uint8), (HEIGHT, 1))
    return np.repeat(gray[:, :, None], 3, axis=2), gray


FRAMES = [gray_gradient_frame(shift) for shift in (0, 2, 4, 6)]


def encode_synthetic(out_path, dump_path, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(FRAMES)

    defaults = dict(
        mode_name="pixel", cols=WIDTH, rows=HEIGHT, fps=15, pal_size=32,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode="global", keyint=64, with_audio=False,
        palette_algorithm="kmeans-oklab", dump_cells=dump_path)
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


def tile_distinct_counts(flat):
    grid = flat.reshape(HEIGHT, WIDTH)
    counts = {}
    for ty in range(0, HEIGHT, 16):
        for tx in range(0, WIDTH, 16):
            counts[(ty, tx)] = len(np.unique(grid[ty:ty + 16, tx:tx + 16]))
    return counts


class SpatialTrellisEncodeTest(unittest.TestCase):
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
        _info, _dump, plain_bytes = self.run_encode("plain")
        info, _dump2, spatial_bytes = self.run_encode(
            "spatial0", trellis_spatial=0)
        self.assertEqual(plain_bytes, spatial_bytes)
        self.assertEqual(int(info["trellis_spatial_tiles"]), 0)

    def test_merges_only_cross_tiles_one_step_down(self):
        _plain_info, plain, _pb = self.run_encode("base")
        chosen = None
        for budget in BUDGETS:
            info, merged, _mb = self.run_encode(
                "spatial_%d" % budget, trellis_spatial=budget,
                trellis_spatial_tile=16)
            if int(info["trellis_spatial_tiles"]):
                chosen = (budget, info, merged)
                break
        self.assertIsNotNone(
            chosen, "ningun presupuesto del barrido fusiono tiles: el test "
                    "quedaria vacio")
        _budget, info, merged = chosen
        self.assertTrue(info["flags"] & encoder.FLAG_LOSSY)
        # contrato del cruce: todo tile tocado tenia 3/5/17 distintos y quedo
        # con exactamente uno menos
        touched = 0
        for idx in range(len(FRAMES)):
            before = tile_distinct_counts(plain[idx])
            after = tile_distinct_counts(merged[idx])
            for key in before:
                if after[key] == before[key]:
                    continue
                touched += 1
                self.assertIn(before[key], trellis.SPATIAL_CROSSINGS,
                              "se fusiono un tile fuera de los cruces")
                self.assertEqual(after[key], before[key] - 1,
                                 "un cruce debe bajar exactamente un valor")
        self.assertGreater(touched, 0)

    def test_negative_budget_and_bad_tile_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "trellis-spatial"):
            self.run_encode("bad", trellis_spatial=-1)
        with self.assertRaisesRegex(ValueError, "trellis-spatial-tile"):
            self.run_encode("badtile", trellis_spatial=4,
                            trellis_spatial_tile=3)


if __name__ == "__main__":
    unittest.main()
