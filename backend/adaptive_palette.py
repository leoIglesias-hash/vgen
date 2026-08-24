#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Segmentacion temporal adaptativa para paletas ASCL.

Este modulo no intenta reconocer objetos ni escenas. Cada decision sale de medidas
numericas de color: una distribucion Oklab de baja resolucion, el desplazamiento del
color medio y un descriptor escalar de gradiente. El analisis es determinista y el
iterador solo retiene ``max_frames`` cuadros originales.

Un corte se hace *antes* del frame que disparo el cambio. Por eso un hard cut queda
exactamente en el primer frame de la nueva distribucion de color. ``min_frames`` se
respeta para deriva gradual, pero deliberadamente no retrasa un hard cut.
"""

from __future__ import division

import math

import numpy as np

from perceptual_palette import srgb_to_oklab


DEFAULT_HISTOGRAM_BINS = (12, 10, 10)


class AdaptivePaletteConfig(object):
    """Parametros del detector, separados del encoder y del formato ASCL.

    Los umbrales por defecto fueron elegidos para trabajar con scores normalizados
    0..1. ``change_threshold`` detecta deriva acumulada desde el inicio del bloque;
    ``hard_cut_threshold`` se aplica exclusivamente entre frames consecutivos.
    """

    def __init__(self, min_frames=5, max_frames=10, change_threshold=0.20,
                 hard_cut_threshold=0.58, sample_size=0,
                 histogram_bins=DEFAULT_HISTOGRAM_BINS,
                 distribution_weight=0.68, mean_weight=0.27,
                 gradient_weight=0.05, stability_below=0.06,
                 stability_free_above=0.42, max_stability=0.25):
        self.min_frames = int(min_frames)
        self.max_frames = int(max_frames)
        self.change_threshold = float(change_threshold)
        self.hard_cut_threshold = float(hard_cut_threshold)
        self.sample_size = int(sample_size)
        self.histogram_bins = tuple(int(value) for value in histogram_bins)
        self.distribution_weight = float(distribution_weight)
        self.mean_weight = float(mean_weight)
        self.gradient_weight = float(gradient_weight)
        self.stability_below = float(stability_below)
        self.stability_free_above = float(stability_free_above)
        self.max_stability = float(max_stability)
        self._validate()

    def _validate(self):
        if self.min_frames <= 0:
            raise ValueError("min_frames debe ser > 0")
        if self.max_frames < self.min_frames:
            raise ValueError("max_frames debe ser >= min_frames")
        if not (0.0 < self.change_threshold < self.hard_cut_threshold <= 1.0):
            raise ValueError("se requiere 0 < change_threshold < hard_cut_threshold <= 1")
        if self.sample_size < 0:
            raise ValueError("sample_size debe ser >= 0 (0 analiza todos los pixeles)")
        if len(self.histogram_bins) != 3 or min(self.histogram_bins) < 2:
            raise ValueError("histogram_bins debe contener tres valores >= 2")
        weights = (self.distribution_weight, self.mean_weight, self.gradient_weight)
        if min(weights) < 0.0 or sum(weights) <= 0.0:
            raise ValueError("los pesos deben ser positivos y sumar mas de cero")
        if not (0.0 <= self.stability_below < self.stability_free_above <= 1.0):
            raise ValueError("rango de estabilidad invalido")
        if not (0.0 <= self.max_stability <= 1.0):
            raise ValueError("max_stability debe estar entre 0 y 1")


class FrameColorDescriptor(object):
    """Descriptor compacto de un frame; no conserva la matriz de pixeles."""

    __slots__ = ("histogram", "mean_oklab", "gradient_energy")

    def __init__(self, histogram, mean_oklab, gradient_energy):
        self.histogram = np.asarray(histogram, dtype=np.float64)
        self.mean_oklab = np.asarray(mean_oklab, dtype=np.float64)
        self.gradient_energy = float(gradient_energy)


class AdaptivePaletteBlock(object):
    """Bloque listo para construir una paleta compartida.

    ``end_index`` es exclusivo. ``boundary_reason`` explica por que termino este
    bloque: ``hard-cut``, ``color-drift``, ``max-frames`` o ``end-of-stream``.
    ``entry_*`` describe la transicion que lo inicio y sirve para estabilizar su
    paleta respecto de la anterior.
    """

    __slots__ = ("frames", "start_index", "end_index", "boundary_reason",
                 "boundary_score", "entry_reason", "entry_change_score",
                 "stability_strength")

    def __init__(self, frames, start_index, boundary_reason, boundary_score,
                 entry_reason, entry_change_score, stability_strength):
        self.frames = tuple(frames)
        self.start_index = int(start_index)
        self.end_index = self.start_index + len(self.frames)
        self.boundary_reason = str(boundary_reason)
        self.boundary_score = float(boundary_score)
        self.entry_reason = str(entry_reason)
        self.entry_change_score = float(entry_change_score)
        self.stability_strength = float(stability_strength)

    def __len__(self):
        return len(self.frames)


def _validate_rgb(rgb):
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb debe tener forma HxWx3")
    if not np.issubdtype(rgb.dtype, np.number):
        raise ValueError("rgb debe ser numerico")
    return np.clip(rgb, 0, 255).astype(np.uint8, copy=False)


def _sample_grid(values, sample_size):
    """Muestreo regular opcional; cero conserva todos los pixeles.

    El modo predeterminado usa el frame completo para que su distribucion sea
    estrictamente invariante ante movimientos o permutaciones espaciales.
    """
    height, width = values.shape[:2]
    if int(sample_size) == 0:
        return values
    rows = min(int(sample_size), height)
    cols = min(int(sample_size), width)
    yy = np.linspace(0, height - 1, rows, dtype=np.int64)
    xx = np.linspace(0, width - 1, cols, dtype=np.int64)
    return values[yy[:, None], xx[None, :]]


def rgb_to_oklab(rgb):
    """Alias validado de la conversion Oklab compartida por el cuantizador."""
    return srgb_to_oklab(_validate_rgb(rgb))


def _soft_histogram_oklab(oklab, bins):
    """Histograma trilineal: evita saltos falsos al cruzar el borde de un bin."""
    bins_l, bins_a, bins_b = bins
    flat = np.asarray(oklab, dtype=np.float64).reshape(-1, 3)
    # Oklab valido ocupa L 0..1 y, para sRGB, aproximadamente a/b -0.4..0.4.
    normalized = np.empty_like(flat)
    normalized[:, 0] = np.clip(flat[:, 0], 0.0, 1.0)
    normalized[:, 1] = np.clip((flat[:, 1] + 0.4) / 0.8, 0.0, 1.0)
    normalized[:, 2] = np.clip((flat[:, 2] + 0.4) / 0.8, 0.0, 1.0)
    bin_counts = np.asarray((bins_l, bins_a, bins_b), dtype=np.int64)
    position = normalized * (bin_counts - 1)
    lower = np.floor(position).astype(np.int64)
    fraction = position - lower
    upper = np.minimum(lower + 1, bin_counts - 1)
    histogram = np.zeros(int(np.prod(bin_counts)), dtype=np.float64)

    for mask in range(8):
        use_upper_l = bool(mask & 1)
        use_upper_a = bool(mask & 2)
        use_upper_b = bool(mask & 4)
        il = upper[:, 0] if use_upper_l else lower[:, 0]
        ia = upper[:, 1] if use_upper_a else lower[:, 1]
        ib = upper[:, 2] if use_upper_b else lower[:, 2]
        weight = ((fraction[:, 0] if use_upper_l else 1.0 - fraction[:, 0]) *
                  (fraction[:, 1] if use_upper_a else 1.0 - fraction[:, 1]) *
                  (fraction[:, 2] if use_upper_b else 1.0 - fraction[:, 2]))
        index = (il * bins_a + ia) * bins_b + ib
        histogram += np.bincount(index, weights=weight,
                                 minlength=histogram.size)
    total = float(histogram.sum())
    if total:
        histogram /= total
    return histogram


def _gradient_energy(rgb, gray, sample_size):
    if gray is None:
        x = rgb.astype(np.uint16)
        gray = ((77 * x[..., 0] + 150 * x[..., 1] + 29 * x[..., 2]) >> 8)
    else:
        gray = np.asarray(gray)
        if gray.shape != rgb.shape[:2]:
            raise ValueError("gray debe tener las mismas dimensiones HxW que rgb")
    sampled = _sample_grid(gray, sample_size).astype(np.float64) / 255.0
    gradients = []
    if sampled.shape[1] > 1:
        gradients.append(np.abs(sampled[:, 1:] - sampled[:, :-1]).reshape(-1))
    if sampled.shape[0] > 1:
        gradients.append(np.abs(sampled[1:] - sampled[:-1]).reshape(-1))
    if not gradients:
        return 0.0
    return float(np.concatenate(gradients).mean())


def describe_frame_color(frame, config=None):
    """Obtiene el descriptor de ``rgb`` o de una tupla ``(rgb, gray)``."""
    config = config or AdaptivePaletteConfig()
    if isinstance(frame, (tuple, list)):
        if not frame:
            raise ValueError("frame no puede estar vacio")
        rgb = frame[0]
        gray = frame[1] if len(frame) > 1 else None
    else:
        rgb, gray = frame, None
    rgb = _validate_rgb(rgb)
    sampled = _sample_grid(rgb, config.sample_size)
    oklab = rgb_to_oklab(sampled)
    return FrameColorDescriptor(
        _soft_histogram_oklab(oklab, config.histogram_bins),
        oklab.reshape(-1, 3).mean(axis=0),
        _gradient_energy(rgb, gray, config.sample_size))


def color_change_metrics(first, second, config=None):
    """Distancia 0..1 entre dos descriptores y sus componentes auditables."""
    config = config or AdaptivePaletteConfig()
    if not isinstance(first, FrameColorDescriptor):
        first = describe_frame_color(first, config)
    if not isinstance(second, FrameColorDescriptor):
        second = describe_frame_color(second, config)
    if first.histogram.shape != second.histogram.shape:
        raise ValueError("los histogramas no son compatibles")
    # La forma ``sqrt(1 - coefficient)`` amplifica el ruido de redondeo cerca
    # de cero (por ejemplo, histogramas iguales acumulados en distinto orden).
    # Esta expresion es la misma distancia de Hellinger, pero resta primero y
    # mantiene estable el invariante de distribucion ante movimientos espaciales.
    histogram_delta = (np.sqrt(first.histogram) -
                       np.sqrt(second.histogram))
    distribution = min(1.0, float(np.linalg.norm(histogram_delta)) /
                       math.sqrt(2.0))
    # 0.55 cubre una diferencia perceptual muy grande dentro del gamut sRGB.
    mean_distance = min(1.0, float(np.linalg.norm(
        first.mean_oklab - second.mean_oklab)) / 0.55)
    # Un salto de energia de gradiente de 0.25 ya es extremo para la grilla muestreada.
    gradient = min(1.0, abs(first.gradient_energy - second.gradient_energy) / 0.25)
    weight_sum = (config.distribution_weight + config.mean_weight +
                  config.gradient_weight)
    score = ((config.distribution_weight * distribution +
              config.mean_weight * mean_distance +
              config.gradient_weight * gradient) / weight_sum)
    return {
        "score": min(1.0, max(0.0, float(score))),
        "distribution": distribution,
        "mean": mean_distance,
        "gradient": gradient,
    }


def temporal_stability_strength(change_score, hard_cut=False, config=None):
    """Fuerza 0..max para conservar/sembrar colores de la paleta anterior.

    Una escena estable devuelve fuerza alta; al crecer el cambio la fuerza cae de
    manera lineal. Un hard cut siempre devuelve cero para no contaminar la nueva
    paleta. La funcion no modifica paletas: es una politica reutilizable por K-means.
    """
    config = config or AdaptivePaletteConfig()
    if hard_cut:
        return 0.0
    score = min(1.0, max(0.0, float(change_score)))
    if score <= config.stability_below:
        return config.max_stability
    if score >= config.stability_free_above:
        return 0.0
    portion = ((score - config.stability_below) /
               (config.stability_free_above - config.stability_below))
    return config.max_stability * (1.0 - portion)


def iter_adaptive_palette_blocks(frames_iter, config=None):
    """Agrupa ``(rgb, gray)`` en bloques variables con memoria acotada.

    Retiene como maximo ``config.max_frames`` frames. El frame que dispara un corte
    nunca se pierde: pasa a ser el primero del bloque siguiente. El orden y los
    objetos originales se conservan.
    """
    config = config or AdaptivePaletteConfig()
    frames = []
    descriptors = []
    start_index = 0
    entry_reason = "start-of-stream"
    entry_score = 1.0
    entry_stability = 0.0

    def make_block(reason, score):
        return AdaptivePaletteBlock(
            frames, start_index, reason, score, entry_reason, entry_score,
            entry_stability)

    for frame in frames_iter:
        descriptor = describe_frame_color(frame, config)
        if not frames:
            frames.append(frame)
            descriptors.append(descriptor)
            continue

        adjacent = color_change_metrics(descriptors[-1], descriptor, config)
        anchor = color_change_metrics(descriptors[0], descriptor, config)
        hard_cut = adjacent["score"] >= config.hard_cut_threshold
        reason = None
        score = 0.0
        if hard_cut:
            reason, score = "hard-cut", adjacent["score"]
        elif len(frames) >= config.max_frames:
            reason, score = "max-frames", anchor["score"]
        elif (len(frames) >= config.min_frames and
              anchor["score"] >= config.change_threshold):
            reason, score = "color-drift", anchor["score"]

        if reason is not None:
            yield make_block(reason, score)
            start_index += len(frames)
            frames = []
            descriptors = []
            entry_reason = reason
            entry_score = score
            entry_stability = temporal_stability_strength(
                score, hard_cut=(reason == "hard-cut"), config=config)

        frames.append(frame)
        descriptors.append(descriptor)

    if frames:
        yield make_block("end-of-stream", 0.0)


__all__ = (
    "AdaptivePaletteBlock", "AdaptivePaletteConfig", "FrameColorDescriptor",
    "color_change_metrics", "describe_frame_color",
    "iter_adaptive_palette_blocks", "rgb_to_oklab",
    "temporal_stability_strength",
)
