#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dithering ordenado selectivo para MODE_PIXEL.

Todo el trabajo ocurre al codificar. La salida sigue siendo una matriz comun de
indices de paleta ASCL v1; el reader y los renderers no necesitan conocer este
modulo.
"""

from functools import cmp_to_key
import hashlib

import numpy as np


DITHER_MODES = ("off", "selective", "auto")
DITHER_MATRIX_SIZES = (2, 4)
DEFAULT_TILE_SIZE = 16
DEFAULT_PROXY_BLUR_SIZE = 5
DEFAULT_MAX_TEXTURE_RMS = 6.0
DEFAULT_AUTO_MIN_RANGE = 4
DEFAULT_MAX_CHANGED_FRACTION = 0.05
DEFAULT_MIN_PROXY_IMPROVEMENT = 0.08
DEFAULT_TEMPORAL_WINDOW = 10
DEFAULT_TEMPORAL_ACTIVATION = 0.70
DEFAULT_TEMPORAL_DEACTIVATION = 0.45

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


def _box_sum(values, size=DEFAULT_PROXY_BLUR_SIZE):
    """Suma box con borde extendido, entera y determinista.

    La integral evita una dependencia de scipy/OpenCV y hace que el costo sea
    lineal aun para cuadros grandes. Acepta HxW o HxWxC.
    """
    values = np.asarray(values)
    size = int(size)
    if size <= 0 or size % 2 == 0:
        raise ValueError("blur_size debe ser impar y > 0")
    if values.ndim not in (2, 3):
        raise ValueError("values debe tener forma HxW o HxWxC")
    radius = size // 2
    pad_width = ((radius, radius), (radius, radius))
    if values.ndim == 3:
        pad_width += ((0, 0),)
    padded = np.pad(values.astype(np.int64), pad_width, mode="edge")
    integral_width = ((1, 0), (1, 0))
    if values.ndim == 3:
        integral_width += ((0, 0),)
    integral = np.pad(padded, integral_width, mode="constant")
    integral = np.cumsum(np.cumsum(integral, axis=0), axis=1)
    return (integral[size:, size:] - integral[:-size, size:] -
            integral[size:, :-size] + integral[:-size, :-size])


def low_frequency_error_map(source, reconstructed,
                            blur_size=DEFAULT_PROXY_BLUR_SIZE):
    """Proxy perceptual de banding sobre la reconstruccion suavizada.

    Devuelve error por celda. Los pesos enteros priorizan verde/luminancia y
    mantienen el resultado reproducible entre plataformas. No es una metrica de
    vision artificial: solo compara promedios locales RGB.
    """
    source = _validate_rgb(source)
    reconstructed = _validate_rgb(reconstructed)
    if reconstructed.shape != source.shape:
        raise ValueError("reconstructed debe tener la misma forma que source")
    source_sum = _box_sum(source, blur_size)
    recon_sum = _box_sum(reconstructed, blur_size)
    delta = recon_sum - source_sum
    return (77 * delta[:, :, 0] * delta[:, :, 0] +
            150 * delta[:, :, 1] * delta[:, :, 1] +
            29 * delta[:, :, 2] * delta[:, :, 2])


def _exact_nonnegative_sum(values, chunk_size=65536):
    """Suma enteros no negativos sin overflow global de int64.

    Una grilla v1 teorica puede llegar a 65535x65535. Cada error individual cabe
    en int64, pero su suma completa no necesariamente. Los parciales acotados
    caben en int64 y se acumulan como ``int`` arbitrario de Python. En las grillas
    normales el costo adicional es despreciable frente al propio proxy offline.
    """
    flat = np.asarray(values, dtype=np.int64).reshape(-1)
    chunk_size = int(chunk_size)
    if chunk_size <= 0:
        raise ValueError("chunk_size debe ser > 0")
    if not len(flat):
        return 0
    minimum = int(flat.min())
    maximum = int(flat.max())
    if minimum < 0:
        raise ValueError("values debe contener enteros no negativos")
    # El tamano nominal se reduce automaticamente si los valores individuales
    # son tan grandes que incluso un parcial podria desbordar int64.
    if maximum > 0:
        chunk_size = min(chunk_size, max(1, int(np.iinfo(np.int64).max) // maximum))
    total = 0
    for start in range(0, len(flat), chunk_size):
        total += int(np.sum(flat[start:start + chunk_size], dtype=np.int64))
    return total


def rects_mask(shape, rects):
    """Convierte rects ``(x0, y0, w, h)`` en celdas a una mascara HxW (E-05).

    Un rect fuera de la grilla se rechaza: es el mismo criterio que aplicara
    el validador del sidecar de slots (INT-001 §6.3).
    """
    mask = np.zeros(shape, dtype=bool)
    height, width = shape
    for rect in rects:
        x0, y0, rect_w, rect_h = (int(value) for value in rect)
        if (x0 < 0 or y0 < 0 or rect_w <= 0 or rect_h <= 0 or
                x0 + rect_w > width or y0 + rect_h > height):
            raise ValueError("rect fuera de la grilla: %r" % (rect,))
        mask[y0:y0 + rect_h, x0:x0 + rect_w] = True
    return mask


def selective_tile_mask(rgb, baseline, palette, protected=None, tile_size=DEFAULT_TILE_SIZE,
                        min_range=8, max_protected_fraction=0.10,
                        max_mean_gradient=12.0, min_quantization_mse=2.0,
                        protected_rects=None):
    """Selecciona tiles suaves con variacion continua y error de cuantizacion.

    Es intencionalmente conservador: una region plana no necesita tramado y un tile
    con demasiados bordes se deja exactamente como la cuantizacion normal.
    ``protected_rects`` (E-05) suma rectangulos declarados a la mascara
    protegida: ninguna celda dentro de un rect puede ser tramada.
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
    if protected_rects:
        # copia deliberada: no mutar la mascara del caller
        protected = protected | rects_mask(baseline.shape, protected_rects)

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
    """LUT determinista de 5 bits/canal: color base, pareja y cobertura 0..4.

    ``base_quantizer`` permite construir la LUT con la misma regla que produjo
    ``baseline`` (por ejemplo, un ``PerceptualQuantizer.quantize`` Oklab). Debe
    aceptar un array Nx3 uint8 y devolver N indices. Si se omite se conserva
    exactamente el vecino euclideo RGB historico.
    """

    def __init__(self, palette, max_pair_distance=192, min_improvement=0.02,
                 base_quantizer=None):
        palette = np.asarray(palette, dtype=np.uint8)
        if palette.ndim != 2 or palette.shape[1] != 3 or not len(palette):
            raise ValueError("palette debe tener forma Nx3")
        if len(palette) > 256:
            raise ValueError("ASCL v1 admite hasta 256 colores")
        self.palette = np.ascontiguousarray(palette)
        self.base_quantizer = base_quantizer
        self.base, self.partner, self.level = self._build(
            int(max_pair_distance), float(min_improvement))
        # Firma semantica compacta para reiniciar la histeresis si cambia la
        # regla base aun cuando la paleta RGB siga siendo identica.
        self.base_signature = hashlib.sha256(self.base.tobytes()).digest()

    def _quantize_base(self, colors):
        quantize = self.base_quantizer
        if not callable(quantize) and callable(getattr(quantize, "quantize", None)):
            quantize = quantize.quantize
        if not callable(quantize):
            raise ValueError("base_quantizer debe ser callable o tener quantize(rgb)")
        indices = np.asarray(quantize(colors.astype(np.uint8))).reshape(-1)
        if indices.size != colors.shape[0]:
            raise ValueError("base_quantizer debe devolver un indice por color")
        if not np.issubdtype(indices.dtype, np.integer):
            try:
                valid_integers = (np.all(np.isfinite(indices)) and
                                  np.all(indices == np.floor(indices)))
            except (TypeError, ValueError):
                valid_integers = False
            if not valid_integers:
                raise ValueError("base_quantizer debe devolver indices enteros")
        indices = indices.astype(np.int32)
        if np.any(indices < 0) or np.any(indices >= len(self.palette)):
            raise ValueError("base_quantizer devolvio un indice fuera de palette")
        return indices

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
        quantized_base = (self._quantize_base(colors)
                          if self.base_quantizer is not None else None)

        # Bloques pequenos mantienen acotada la memoria aun con paletas de 256.
        chunk_size = 512
        for start in range(0, 32768, chunk_size):
            stop = min(start + chunk_size, 32768)
            src = colors[start:stop]
            nearest_delta = src[:, None, :] - pal[None, :, :]
            nearest_error = np.sum(nearest_delta * nearest_delta, axis=2)
            base = (quantized_base[start:stop] if quantized_base is not None
                    else np.argmin(nearest_error, axis=1).astype(np.int32))
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


class TemporalDitherState(object):
    """Historial opcional por tile para evitar encendido/apagado entre frames.

    El estado no altera el patron Bayer. Solo aplica dos umbrales a la decision de
    calidad: se activa con evidencia sostenida y se conserva hasta cruzar el
    umbral inferior. Una mejora negativa siempre se rechaza en el frame actual.
    """

    def __init__(self, window=DEFAULT_TEMPORAL_WINDOW,
                 activation=DEFAULT_TEMPORAL_ACTIVATION,
                 deactivation=DEFAULT_TEMPORAL_DEACTIVATION):
        window = int(window)
        activation = float(activation)
        deactivation = float(deactivation)
        if window <= 0:
            raise ValueError("temporal_window debe ser > 0")
        if window > np.iinfo(np.uint32).max:
            raise ValueError("temporal_window excede el contador soportado")
        if not (0.0 <= deactivation <= activation <= 1.0):
            raise ValueError("se requiere 0 <= deactivation <= activation <= 1")
        self.window = window
        self._count_dtype = (np.uint8 if window <= np.iinfo(np.uint8).max else
                             (np.uint16 if window <= np.iinfo(np.uint16).max
                              else np.uint32))
        self.activation = activation
        self.deactivation = deactivation
        self._shape = None
        self._packed_history = None
        self._counts = None
        self._active = None
        self._cursor = 0
        self._frames = 0
        self._context = None
        self._has_context = False
        self.last_reset = False

    def reset(self):
        self._shape = None
        self._packed_history = None
        self._counts = None
        self._active = None
        self._cursor = 0
        self._frames = 0
        self._context = None
        self._has_context = False
        self.last_reset = False

    @property
    def nbytes(self):
        """Memoria NumPy del estado temporal (sin contar el objeto Python)."""
        return sum(array.nbytes for array in
                   (self._packed_history, self._counts, self._active)
                   if array is not None)

    def _clear_evidence(self):
        self._packed_history.fill(0)
        self._counts.fill(0)
        self._active.fill(False)
        self._cursor = 0
        self._frames = 0

    @staticmethod
    def _contexts_equal(left, right):
        if left is right:
            return True
        try:
            equal = left == right
            if isinstance(equal, np.ndarray):
                return bool(np.all(equal))
            return bool(equal)
        except (TypeError, ValueError):
            return False

    def update(self, qualified, context=None, force_reset=False):
        qualified = np.asarray(qualified, dtype=bool)
        if qualified.ndim != 2:
            raise ValueError("qualified debe tener forma tilesY x tilesX")
        if self._shape is None:
            self._shape = qualified.shape
            count = int(qualified.size)
            packed_size = (count + 7) // 8
            self._packed_history = np.zeros(
                (self.window, packed_size), dtype=np.uint8)
            self._counts = np.zeros(count, dtype=self._count_dtype)
            self._active = np.zeros(count, dtype=bool)
        elif self._shape != qualified.shape:
            raise ValueError("la grilla temporal cambio; reinicie TemporalDitherState")

        context_changed = (self._has_context and
                           not self._contexts_equal(self._context, context))
        self.last_reset = bool(force_reset or context_changed)
        if self.last_reset:
            self._clear_evidence()
        self._context = context
        self._has_context = True

        flat = qualified.reshape(-1)
        slot = self._cursor
        if self._frames >= self.window:
            previous = np.unpackbits(self._packed_history[slot])[:flat.size]
            self._counts -= previous.astype(self._count_dtype)
        else:
            self._frames += 1
        packed = np.packbits(flat)
        self._packed_history[slot].fill(0)
        self._packed_history[slot, :packed.size] = packed
        self._counts += flat.astype(self._count_dtype)
        self._cursor = (slot + 1) % self.window

        # Los frames aun no vistos cuentan como evidencia ausente: evita que un
        # unico frame aislado active el tramado al comienzo de un bloque.
        fraction = self._counts.astype(np.float64) / float(self.window)
        self._active |= fraction >= self.activation
        self._active &= fraction >= self.deactivation
        return (self._active.reshape(self._shape).copy(),
                fraction.reshape(self._shape))


def _tile_bounds(shape, tile_size):
    h, w = shape
    for ty, y0 in enumerate(range(0, h, tile_size)):
        y1 = min(y0 + tile_size, h)
        for tx, x0 in enumerate(range(0, w, tile_size)):
            yield ty, tx, y0, y1, x0, min(x0 + tile_size, w)


def _resolve_pair_lut(palette, pair_lut=None, base_quantizer=None):
    if pair_lut is None:
        return PairLUT(palette, base_quantizer=base_quantizer)
    if base_quantizer is not None:
        raise ValueError("use pair_lut o base_quantizer, no ambos")
    if not np.array_equal(pair_lut.palette, palette):
        raise ValueError("pair_lut no corresponde a palette")
    return pair_lut


def apply_calibrated_dither(rgb, baseline, palette, matrix_size=4, pair_lut=None,
                            tile_size=DEFAULT_TILE_SIZE,
                            max_changed_cells=None,
                            max_changed_fraction=DEFAULT_MAX_CHANGED_FRACTION,
                            min_proxy_improvement=DEFAULT_MIN_PROXY_IMPROVEMENT,
                            blur_size=DEFAULT_PROXY_BLUR_SIZE,
                            max_texture_rms=DEFAULT_MAX_TEXTURE_RMS,
                            min_gradient_range=DEFAULT_AUTO_MIN_RANGE,
                            temporal_state=None,
                            temporal_window=DEFAULT_TEMPORAL_WINDOW,
                            activation=DEFAULT_TEMPORAL_ACTIVATION,
                            deactivation=DEFAULT_TEMPORAL_DEACTIVATION,
                            return_details=False, base_quantizer=None,
                            temporal_context=None, reset_temporal=False,
                            reset_on_palette_change=True,
                            protected_rects=None):
    """Dithering auto calibrado por calidad, bordes, presupuesto e historial.

    Primero produce el mismo candidato determinista que ``selective``. Despues
    acepta tiles solo cuando reducen el proxy RGB de baja frecuencia, los ordena
    por ganancia por celda y toma tiles completos hasta agotar el presupuesto.

    ``temporal_state`` puede ser un :class:`TemporalDitherState` persistente. Por
    comodidad, un diccionario vacio tambien es valido y guarda internamente el
    estado; asi el llamador no necesita conocer la clase. Sin estado no hay
    memoria entre frames y el resto de la seleccion es identico. Por defecto una
    paleta/LUT nueva reinicia la ventana; en video con bloques cortos conviene
    ``reset_on_palette_change=False`` y reiniciar solo en hard cuts mediante
    ``reset_temporal`` o ``TemporalDitherState.reset()``.
    """
    rgb = _validate_rgb(rgb)
    baseline = np.asarray(baseline, dtype=np.uint8)
    palette = np.asarray(palette, dtype=np.uint8)
    tile_size = int(tile_size)
    if tile_size <= 0:
        raise ValueError("tile_size debe ser > 0")
    if baseline.shape != rgb.shape[:2]:
        raise ValueError("baseline debe tener forma HxW")
    if max_changed_cells is not None and int(max_changed_cells) < 0:
        raise ValueError("max_changed_cells debe ser >= 0")
    if max_changed_fraction is not None and not \
            (0.0 <= float(max_changed_fraction) <= 1.0):
        raise ValueError("max_changed_fraction debe estar entre 0 y 1")
    if float(min_proxy_improvement) < 0.0:
        raise ValueError("min_proxy_improvement debe ser >= 0")
    if float(max_texture_rms) < 0.0:
        raise ValueError("max_texture_rms debe ser >= 0")
    if int(min_gradient_range) < 0:
        raise ValueError("min_gradient_range debe ser >= 0")

    pair_lut = _resolve_pair_lut(palette, pair_lut, base_quantizer)
    # E-05/F7: los rects protegidos entran por el candidato selectivo, que ya
    # conserva Q0 exacto dentro de ellos; asi ninguna celda protegida puede
    # aparecer como "cambiada" en la seleccion calibrada.
    candidate, candidate_details = apply_selective_dither(
        rgb, baseline, palette, matrix_size=matrix_size, pair_lut=pair_lut,
        tile_size=tile_size, return_details=True,
        min_gradient_range=min_gradient_range,
        protected_rects=protected_rects)
    baseline_rgb = palette[baseline]
    candidate_rgb = palette[candidate]
    baseline_error = low_frequency_error_map(rgb, baseline_rgb, blur_size)
    candidate_error = low_frequency_error_map(rgb, candidate_rgb, blur_size)

    h, w = baseline.shape
    tiles_y = (h + tile_size - 1) // tile_size
    tiles_x = (w + tile_size - 1) // tile_size
    improvements = np.zeros((tiles_y, tiles_x), dtype=np.float64)
    gains = np.zeros((tiles_y, tiles_x), dtype=np.int64)
    changed_counts = np.zeros((tiles_y, tiles_x), dtype=np.int32)
    quality_qualified = np.zeros((tiles_y, tiles_x), dtype=bool)
    smooth_qualified = np.zeros((tiles_y, tiles_x), dtype=bool)
    candidate_changed = candidate != baseline
    luminance = _luminance(rgb)
    smooth_luminance = (_box_sum(luminance, blur_size).astype(np.float64) /
                        float(int(blur_size) * int(blur_size)))

    for ty, tx, y0, y1, x0, x1 in _tile_bounds(baseline.shape, tile_size):
        changed = int(np.count_nonzero(candidate_changed[y0:y1, x0:x1]))
        changed_counts[ty, tx] = changed
        if not changed:
            continue
        before = int(np.sum(baseline_error[y0:y1, x0:x1], dtype=np.int64))
        after = int(np.sum(candidate_error[y0:y1, x0:x1], dtype=np.int64))
        gain = before - after
        gains[ty, tx] = gain
        improvement = (float(gain) / float(before)) if before > 0 else 0.0
        improvements[ty, tx] = improvement
        texture_delta = (luminance[y0:y1, x0:x1].astype(np.float64) -
                         smooth_luminance[y0:y1, x0:x1])
        texture_rms = float(np.sqrt(np.mean(texture_delta * texture_delta)))
        smooth_qualified[ty, tx] = texture_rms <= float(max_texture_rms)
        quality_qualified[ty, tx] = (gain > 0 and
                                     smooth_qualified[ty, tx] and
                                     improvement >= float(min_proxy_improvement))

    temporal_active = quality_qualified.copy()
    temporal_fraction = quality_qualified.astype(np.float64)
    state = temporal_state
    if isinstance(state, dict):
        stored = state.get("state")
        if stored is None:
            stored = TemporalDitherState(temporal_window, activation, deactivation)
            state["state"] = stored
        state = stored
    if state is not None:
        if not isinstance(state, TemporalDitherState):
            raise ValueError("temporal_state debe ser TemporalDitherState o dict")
        # La evidencia depende tanto de la paleta como de la regla que produjo
        # los indices base. Una renovacion de paleta no debe heredar decisiones
        # tomadas con otra reconstruccion aunque no coincida con un hard cut.
        automatic_context = ((palette.shape, palette.tobytes(),
                              pair_lut.base_signature, temporal_context)
                             if reset_on_palette_change else temporal_context)
        temporal_active, temporal_fraction = state.update(
            quality_qualified, context=automatic_context,
            force_reset=bool(reset_temporal))

    # La histeresis puede conservar un tile bajo el umbral de activacion, pero
    # jamas autoriza un frame donde el proxy empeora o el candidato desaparecio.
    selectable = (temporal_active & smooth_qualified &
                  (gains > 0) & (changed_counts > 0))
    candidates = []
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            if selectable[ty, tx]:
                # Sin division flotante en el orden primario: se compara una
                # razon equivalente y se rompen empates por coordenada estable.
                candidates.append((ty, tx))
    def compare_scores(left, right):
        # Compara gain/cost por productos cruzados enteros. Asi no hay empates
        # distintos por redondeo de float entre versiones de NumPy/plataformas.
        lhs = int(gains[left]) * int(changed_counts[right])
        rhs = int(gains[right]) * int(changed_counts[left])
        if lhs != rhs:
            return -1 if lhs > rhs else 1
        if left < right:
            return -1
        if left > right:
            return 1
        return 0

    candidates.sort(key=cmp_to_key(compare_scores))

    total_cells = int(baseline.size)
    budgets = []
    if max_changed_cells is not None:
        budgets.append(int(max_changed_cells))
    if max_changed_fraction is not None:
        budgets.append(int(np.floor(total_cells * float(max_changed_fraction))))
    budget = min(budgets) if budgets else total_cells
    accepted_tiles = np.zeros((tiles_y, tiles_x), dtype=bool)
    result = baseline.copy()
    used = 0
    skipped_by_budget = 0
    for ty, tx in candidates:
        cost = int(changed_counts[ty, tx])
        if used + cost > budget:
            skipped_by_budget += 1
            continue
        y0 = ty * tile_size
        y1 = min(y0 + tile_size, h)
        x0 = tx * tile_size
        x1 = min(x0 + tile_size, w)
        result[y0:y1, x0:x1] = candidate[y0:y1, x0:x1]
        accepted_tiles[ty, tx] = True
        used += cost

    result_error = low_frequency_error_map(rgb, palette[result], blur_size)
    baseline_total = _exact_nonnegative_sum(baseline_error)
    result_total = _exact_nonnegative_sum(result_error)
    # Interacciones del blur entre tiles pueden, en casos patologicos, volver
    # peor a la combinacion aunque cada score local haya mejorado. El guard final
    # hace que el modo auto sea estrictamente no-regresivo.
    if result_total >= baseline_total:
        result = baseline.copy()
        accepted_tiles[:] = False
        used = 0
        result_total = baseline_total

    if return_details:
        unused_budget = max(0, budget - used)
        return result, {
            "protected": candidate_details["protected"],
            "eligible": candidate_details["eligible"],
            "candidate_changed": candidate_changed,
            "changed": result != baseline,
            "accepted_tiles": accepted_tiles,
            "quality_qualified": quality_qualified,
            "smooth_qualified": smooth_qualified,
            "temporal_active": temporal_active,
            "temporal_fraction": temporal_fraction,
            "tile_improvements": improvements,
            "tile_gains": gains,
            "tile_changed_counts": changed_counts,
            "change_budget": budget,
            "changed_cells": used,
            "unused_change_budget": unused_budget,
            "budget_utilization": ((float(used) / float(budget))
                                   if budget > 0 else 0.0),
            "budget_limited_tiles": skipped_by_budget,
            "smallest_selectable_tile": (min(
                (int(changed_counts[item]) for item in candidates),
                default=0)),
            "temporal_reset": (state.last_reset if state is not None else False),
            "temporal_state_nbytes": (state.nbytes if state is not None else 0),
            "baseline_proxy_error": baseline_total,
            "result_proxy_error": result_total,
            "proxy_improvement": ((float(baseline_total - result_total) /
                                   float(baseline_total))
                                  if baseline_total > 0 else 0.0),
        }
    return result


def apply_selective_dither(rgb, baseline, palette, matrix_size=4, pair_lut=None,
                           tile_size=DEFAULT_TILE_SIZE, return_details=False,
                           min_gradient_range=8, base_quantizer=None,
                           protected_rects=None):
    """Aplica Bayer solo en gradientes aptos y conserva Q0 en bordes protegidos.

    ``protected_rects`` (E-05): rectangulos ``(x0, y0, w, h)`` en celdas que se
    suman a la mascara protegida; sus celdas conservan Q0 exactamente.
    """
    rgb = _validate_rgb(rgb)
    baseline = np.asarray(baseline, dtype=np.uint8)
    palette = np.asarray(palette, dtype=np.uint8)
    matrix_size = int(matrix_size)
    if matrix_size not in DITHER_MATRIX_SIZES:
        raise ValueError("dither-matrix debe ser 2 o 4")
    if baseline.shape != rgb.shape[:2]:
        raise ValueError("baseline debe tener forma HxW")
    pair_lut = _resolve_pair_lut(palette, pair_lut, base_quantizer)

    protected = edge_mask(rgb)
    if protected_rects:
        protected = protected | rects_mask(baseline.shape, protected_rects)
    eligible = selective_tile_mask(rgb, baseline, palette, protected,
                                    tile_size=tile_size,
                                    min_range=min_gradient_range)
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
