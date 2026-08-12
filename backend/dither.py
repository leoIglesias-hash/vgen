#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dithering ordenado selectivo para MODE_PIXEL.

Todo el trabajo ocurre al codificar. La salida sigue siendo una matriz comun de
indices de paleta ASCL v1; el reader y los renderers no necesitan conocer este
modulo.
"""

import numpy as np


DITHER_MODES = ("off", "selective")
DITHER_MATRIX_SIZES = (2, 4)
DEFAULT_TILE_SIZE = 16

BAYER_MATRICES = {
    2: np.array(((0, 2),
                 (3, 1)), dtype=np.uint8),
    4: np.array(((0, 8, 2, 10),
                 (12, 4, 14, 6),
                 (3, 11, 1, 9),
                 (15, 7, 13, 5)), dtype=np.uint8),
}


def _validate_rgb(rgb):
    rgb = np.asarray(rgb, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb debe tener forma HxWx3")
    return rgb


def _dilate(mask, radius=1):
    """Dilatacion booleana chica sin depender de scipy/OpenCV."""
    out = np.asarray(mask, dtype=bool)
    radius = int(radius)
    for _ in range(max(0, radius)):
        padded = np.pad(out, ((1, 1), (1, 1)), mode="constant")
        expanded = np.zeros_like(out)
        for dy in range(3):
            for dx in range(3):
                expanded |= padded[dy:dy + out.shape[0], dx:dx + out.shape[1]]
        out = expanded
    return out


def edge_mask(rgb, gradient_threshold=24, laplacian_threshold=18, dilation=1):
    """Detecta bordes RGB/luminancia y los dilata para proteger texto y lineas.

    El maximo entre canales evita perder contornos cromaticos de luminancia similar.
    La luminancia usa la formula entera documentada y no depende de plataforma.
    """
    rgb = _validate_rgb(rgb)
    # int32 tambien evita overflow en la suma ponderada, cuyo maximo es 65280.
    x = rgb.astype(np.int32)
    h, w = x.shape[:2]
    protected = np.zeros((h, w), dtype=bool)

    if w > 1:
        horizontal = np.max(np.abs(x[:, 1:] - x[:, :-1]), axis=2)
        strong = horizontal >= int(gradient_threshold)
        protected[:, 1:] |= strong
        protected[:, :-1] |= strong
    if h > 1:
        vertical = np.max(np.abs(x[1:] - x[:-1]), axis=2)
        strong = vertical >= int(gradient_threshold)
        protected[1:] |= strong
        protected[:-1] |= strong

    if h > 2 and w > 2:
        lum = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
                29 * x[:, :, 2]) >> 8).astype(np.int16)
        lap = np.abs(4 * lum[1:-1, 1:-1] - lum[:-2, 1:-1] -
                     lum[2:, 1:-1] - lum[1:-1, :-2] - lum[1:-1, 2:])
        protected[1:-1, 1:-1] |= lap >= int(laplacian_threshold)

    return _dilate(protected, dilation)


def _luminance(rgb):
    x = np.asarray(rgb, dtype=np.uint16)
    return ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)


def selective_tile_mask(rgb, baseline, palette, protected=None, tile_size=DEFAULT_TILE_SIZE,
                        min_range=8, max_protected_fraction=0.10,
                        max_mean_gradient=12.0, min_quantization_mse=2.0):
    """Selecciona tiles suaves con variacion continua y error de cuantizacion.

    Es intencionalmente conservador: una region plana no necesita tramado y un tile
    con demasiados bordes se deja exactamente como la cuantizacion normal.
    """
    rgb = _validate_rgb(rgb)
    baseline = np.asarray(baseline, dtype=np.uint8)
    palette = np.asarray(palette, dtype=np.uint8)
    if baseline.shape != rgb.shape[:2]:
        raise ValueError("baseline debe tener forma HxW")
    if palette.ndim != 2 or palette.shape[1] != 3 or not len(palette):
        raise ValueError("palette debe tener forma Nx3")
    if int(baseline.max()) >= len(palette):
        raise ValueError("baseline referencia un indice fuera de palette")
    tile_size = int(tile_size)
    if tile_size <= 0:
        raise ValueError("tile_size debe ser > 0")
    if protected is None:
        protected = edge_mask(rgb)
    else:
        protected = np.asarray(protected, dtype=bool)
    if protected.shape != baseline.shape:
        raise ValueError("protected debe tener forma HxW")

    lum = _luminance(rgb)
    recon = palette[baseline]
    sq_error = (rgb.astype(np.int16) - recon.astype(np.int16)).astype(np.int32)
    sq_error = np.sum(sq_error * sq_error, axis=2)
    selected = np.zeros(baseline.shape, dtype=bool)
    h, w = baseline.shape

    for y0 in range(0, h, tile_size):
        y1 = min(y0 + tile_size, h)
        for x0 in range(0, w, tile_size):
            x1 = min(x0 + tile_size, w)
            tile_protected = protected[y0:y1, x0:x1]
            if float(tile_protected.mean()) >= float(max_protected_fraction):
                continue
            values = np.sort(lum[y0:y1, x0:x1], axis=None)
            count = values.size
            lo = int(values[(count - 1) * 5 // 100])
            hi = int(values[(count - 1) * 95 // 100])
            if hi - lo < int(min_range):
                continue

            tile_rgb = rgb[y0:y1, x0:x1].astype(np.int16)
            gradients = []
            if tile_rgb.shape[1] > 1:
                gradients.append(np.max(np.abs(tile_rgb[:, 1:] - tile_rgb[:, :-1]),
                                        axis=2).reshape(-1))
            if tile_rgb.shape[0] > 1:
                gradients.append(np.max(np.abs(tile_rgb[1:] - tile_rgb[:-1]),
                                        axis=2).reshape(-1))
            mean_gradient = (float(np.concatenate(gradients).mean())
                             if gradients else 0.0)
            if mean_gradient > float(max_mean_gradient):
                continue
            if float(sq_error[y0:y1, x0:x1].mean()) < float(min_quantization_mse):
                continue
            selected[y0:y1, x0:x1] = True

    # Esta resta es la garantia fuerte: Q1 siempre equivale a Q0 en los bordes.
    selected &= ~protected
    return selected


class PairLUT(object):
    """LUT determinista de 5 bits/canal: color base, pareja y cobertura 0..4."""

    def __init__(self, palette, max_pair_distance=192, min_improvement=0.02):
        palette = np.asarray(palette, dtype=np.uint8)
        if palette.ndim != 2 or palette.shape[1] != 3 or not len(palette):
            raise ValueError("palette debe tener forma Nx3")
        if len(palette) > 256:
            raise ValueError("ASCL v1 admite hasta 256 colores")
        self.palette = np.ascontiguousarray(palette)
        self.base, self.partner, self.level = self._build(
            int(max_pair_distance), float(min_improvement))

    def _build(self, max_pair_distance, min_improvement):
        # Centro de las 32768 celdas RGB555. La LUT se calcula offline una vez por
        # paleta (global o bloque), no una vez por frame.
        keys = np.arange(32768, dtype=np.int32)
        colors = np.empty((32768, 3), dtype=np.int32)
        colors[:, 0] = ((keys >> 10) & 31) * 8 + 4
        colors[:, 1] = ((keys >> 5) & 31) * 8 + 4
        colors[:, 2] = (keys & 31) * 8 + 4
        colors = np.minimum(colors, 255)
        pal = self.palette.astype(np.int32)
        base_out = np.empty(32768, dtype=np.uint8)
        partner_out = np.empty(32768, dtype=np.uint8)
        level_out = np.zeros(32768, dtype=np.uint8)
        max_pair_sq = max_pair_distance * max_pair_distance

        # Bloques pequenos mantienen acotada la memoria aun con paletas de 256.
        chunk_size = 512
        for start in range(0, 32768, chunk_size):
            stop = min(start + chunk_size, 32768)
            src = colors[start:stop]
            nearest_delta = src[:, None, :] - pal[None, :, :]
            nearest_error = np.sum(nearest_delta * nearest_delta, axis=2)
            base = np.argmin(nearest_error, axis=1).astype(np.int32)
            a = pal[base]
            vector = pal[None, :, :] - a[:, None, :]
            pair_sq = np.sum(vector * vector, axis=2)
            rel = src - a
            projection = np.sum(rel[:, None, :] * vector, axis=2)
            safe_pair_sq = np.maximum(pair_sq, 1)
            fraction = projection.astype(np.float64) / safe_pair_sq.astype(np.float64)
            levels = np.floor(np.clip(fraction, 0.0, 1.0) * 4.0 + 0.5).astype(np.int16)
            mixed4 = a[:, None, :] * (4 - levels[:, :, None]) + \
                     pal[None, :, :] * levels[:, :, None]
            mix_delta4 = src[:, None, :] * 4 - mixed4
            mix_error4 = np.sum(mix_delta4 * mix_delta4, axis=2)
            invalid = ((pair_sq == 0) | (pair_sq > max_pair_sq) | (levels == 0))
            mix_error4[invalid] = np.iinfo(np.int32).max
            partner = np.argmin(mix_error4, axis=1).astype(np.int32)
            row = np.arange(stop - start)
            chosen_error4 = mix_error4[row, partner]
            baseline_error4 = nearest_error[row, base] * 16
            improves = chosen_error4 < baseline_error4 * (1.0 - min_improvement)
            chosen_level = levels[row, partner]
            chosen_level[~improves] = 0
            partner[~improves] = base[~improves]
            base_out[start:stop] = base.astype(np.uint8)
            partner_out[start:stop] = partner.astype(np.uint8)
            level_out[start:stop] = chosen_level.astype(np.uint8)
        return base_out, partner_out, level_out


def rgb555_keys(rgb):
    rgb = _validate_rgb(rgb)
    x = (rgb >> 3).astype(np.uint16)
    return ((x[:, :, 0] << 10) | (x[:, :, 1] << 5) | x[:, :, 2]).astype(np.uint16)


def apply_selective_dither(rgb, baseline, palette, matrix_size=4, pair_lut=None,
                           tile_size=DEFAULT_TILE_SIZE, return_details=False):
    """Aplica Bayer solo en gradientes aptos y conserva Q0 en bordes protegidos."""
    rgb = _validate_rgb(rgb)
    baseline = np.asarray(baseline, dtype=np.uint8)
    palette = np.asarray(palette, dtype=np.uint8)
    matrix_size = int(matrix_size)
    if matrix_size not in DITHER_MATRIX_SIZES:
        raise ValueError("dither-matrix debe ser 2 o 4")
    if baseline.shape != rgb.shape[:2]:
        raise ValueError("baseline debe tener forma HxW")
    if pair_lut is None:
        pair_lut = PairLUT(palette)
    elif not np.array_equal(pair_lut.palette, palette):
        raise ValueError("pair_lut no corresponde a palette")

    protected = edge_mask(rgb)
    eligible = selective_tile_mask(rgb, baseline, palette, protected,
                                    tile_size=tile_size)
    keys = rgb555_keys(rgb)
    lut_base = pair_lut.base[keys]
    partner = pair_lut.partner[keys]
    level = pair_lut.level[keys]
    bayer = BAYER_MATRICES[matrix_size]
    yy, xx = np.indices(baseline.shape)
    threshold = bayer[yy % matrix_size, xx % matrix_size]
    cells_per_quarter = (matrix_size * matrix_size) // 4
    # PIL es quien produce Q0. Si su cuantizador eligio otro color que el RGB555
    # usado para la LUT, conservamos Q0: nunca mezclamos desde una base incorrecta.
    choose_partner = (eligible & (lut_base == baseline) &
                      (threshold < level * cells_per_quarter))
    result = baseline.copy()
    result[choose_partner] = partner[choose_partner]
    if return_details:
        return result, {"protected": protected, "eligible": eligible,
                        "changed": result != baseline, "level": level}
    return result
