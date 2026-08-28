#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encoder.py - Encoder offline ASCILINE -> contenedor .ascl (imagen Y video).

Relacion conceptual declarada con YusufB5/ASCILINE: este encoder standalone implementa
la rampa por luminancia, la correccion de aspecto del glifo y la estrategia adaptativa
de probar RAW / ZLIB / DELTA por frame. La auditoria de procedencia previa a una
publicacion publica se registra aparte. El char plane siempre es exacto.

  IMAGEN (Fase 1):  un frame, n_frames = 1.  -> python encoder.py foto.jpg out.ascl
  VIDEO  (Fase 3):  N frames + tabla de offsets + DELTA temporal + audio aparte.
                    -> python encoder.py clip.mp4 out.ascl --mode pixel --cols 320

Paleta (decision D3):
  --palette per-frame  (default): cada frame trae su paleta de 256 (maxima fidelidad).
                        DELTA de color NO aplica entre frames (paletas distintas);
                        cada frame es full (RAW/ZLIB). char plane si puede ir en DELTA.
  --palette global     : una paleta para todo el clip => habilita DELTA de indices.
  --palette block      : una paleta por bloque temporal => DELTA dentro del bloque.
                        La paleta se reemite en cada keyframe para permitir seek.
  --palette adaptive   : bloques variables por cambio numerico Oklab, sin IA.
                        Conserva el mismo layout v1 de paleta por escena.

Audio: se extrae a un .mp3 aparte (carril separado, reloj maestro). NUNCA dentro del .ascl.
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib

import numpy as np
from PIL import Image

import dither as selective_dither
import adaptive_palette
import overlay_panel
import perceptual_palette
from deflate_util import best_deflate

MAGIC          = b"ASCL"
VERSION        = 1
MODE_ASCII_BW, MODE_ASCII_PAL, MODE_ASCII_RGB, MODE_PIXEL = 0, 1, 2, 3
TAG_RAW, TAG_ZLIB, TAG_DELTA = 0, 1, 2
TAG_DELTA_MASK = 3
FLAG_LOSSY, FLAG_PAL_PER_SCENE, FLAG_PAL_GLOBAL, FLAG_HAS_OFFSET_TABLE = 1, 2, 4, 8
# Bit aditivo dentro de v1. Los readers anteriores conservan su comportamiento porque
# ya tratan flags como un bitfield y no rechazan bits desconocidos.
FLAG_RECON_SOFT = 16

HEADER_SIZE         = 32
UINT32_MAX          = (1 << 32) - 1
DEFAULT_FPS         = 15
DEFAULT_CHAR_ASPECT = 0.5
HEADER_FMT          = "<4sBBBBHHHIBBIHHI"
assert struct.calcsize(HEADER_FMT) == HEADER_SIZE

RAMPS = {
    "short": " .:-=+*#%@",
    "long":  " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
}
MODE_NAMES = {"ascii-bw": MODE_ASCII_BW, "ascii-pal": MODE_ASCII_PAL,
              "ascii-rgb": MODE_ASCII_RGB, "pixel": MODE_PIXEL}
BYTES_PER_CELL = {MODE_PIXEL: 1, MODE_ASCII_BW: 1, MODE_ASCII_PAL: 2, MODE_ASCII_RGB: 4}
CELL_FMT       = {MODE_ASCII_BW: 1, MODE_ASCII_PAL: 2, MODE_ASCII_RGB: 3, MODE_PIXEL: 3}
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".gif")

# Los perfiles solo completan opciones no indicadas por el usuario. No son formatos
# distintos ni cambian el decoder: producen el mismo ASCL v1 con otra relacion entre
# resolucion espacial y resolucion de color.
QUALITY_PROFILES = {
    "detail":   {"cols": 960, "pal_size": 64},
    "balanced": {"cols": 640, "pal_size": 128},
    "graphic":  {"cols": 640, "pal_size": 256},
    "graphic-hq": {"cols": 768, "pal_size": 256},
    "graphic-ultra": {"cols": 960, "pal_size": 256},
    "color":    {"cols": 320, "pal_size": 256},
}
QUALITY_PROFILE_NAMES = ("custom", "detail", "balanced", "graphic",
                         "graphic-hq", "graphic-ultra", "color")
BAKE_SMOOTHING_MODES = ("none", "soft")
RECONSTRUCTION_MODES = ("nearest", "soft")
PALETTE_MODES = ("per-frame", "global", "block", "adaptive")
PALETTE_ALGORITHMS = ("median-cut", "fast-octree", "kmeans-rgb", "kmeans-oklab")
DITHER_MODES = selective_dither.DITHER_MODES
DITHER_MATRIX_SIZES = selective_dither.DITHER_MATRIX_SIZES
# Reconstruccion offline 2x: una base de media resolucion se expande a la grilla
# almacenada. Los pixeles intermedios quedan dentro del archivo, no se calculan al reproducir.
SOFT_BAKE_SCALE = 0.5


def resolve_quality_options(profile, cols, pal_size, default_cols, default_pal_size=256):
    """Completa cols/pal_size respetando siempre los overrides manuales."""
    profile = profile or "custom"
    if profile not in QUALITY_PROFILE_NAMES:
        raise ValueError("profile desconocido: %s" % profile)
    preset = QUALITY_PROFILES.get(profile, {})
    if cols is None:
        cols = preset.get("cols", default_cols)
    if pal_size is None:
        pal_size = preset.get("pal_size", default_pal_size)
    return int(cols), int(pal_size)


def validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            palette_block_frames=0, dither_mode="off",
                            dither_matrix=4, palette_algorithm="median-cut",
                            adaptive_min_frames=5, adaptive_max_frames=10,
                            adaptive_change_threshold=0.20,
                            adaptive_hard_cut_threshold=0.58,
                            adaptive_stability_max=0.25,
                            perceptual_lut_bits=0,
                            dither_budget=selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                            dither_min_improvement=selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                            dither_window=selective_dither.DEFAULT_TEMPORAL_WINDOW,
                            reserved=0, palette_refit=0, palette_uint8_refine=0):
    """Valida limites del header v1 y opciones compartidas por todos los entrypoints."""
    if mode_name not in MODE_NAMES:
        raise ValueError("mode desconocido: %s" % mode_name)
    if not (1 <= int(cols) <= 65535):
        raise ValueError("cols debe estar entre 1 y 65535")
    if not (0 <= int(rows) <= 65535):
        raise ValueError("rows debe estar entre 0 (auto) y 65535")
    if not (1 <= int(fps) <= 255):
        raise ValueError("fps debe estar entre 1 y 255 (limite ASCL v1)")
    if not (1 <= int(pal_size) <= 256):
        raise ValueError("palette-size debe estar entre 1 y 256")
    if float(char_aspect) <= 0:
        raise ValueError("char-aspect debe ser > 0")
    if palette_mode not in PALETTE_MODES:
        raise ValueError("palette debe ser per-frame, global, block o adaptive")
    if int(palette_block_frames) < 0:
        raise ValueError("palette-block-frames debe ser >= 0")
    if bake_smoothing not in BAKE_SMOOTHING_MODES:
        raise ValueError("bake-smoothing debe ser none o soft")
    if reconstruction not in RECONSTRUCTION_MODES:
        raise ValueError("reconstruction debe ser nearest o soft")
    if dither_mode not in DITHER_MODES:
        raise ValueError("dither debe ser off, selective o auto")
    if int(dither_matrix) not in DITHER_MATRIX_SIZES:
        raise ValueError("dither-matrix debe ser 2 o 4")
    if dither_mode != "off" and mode_name != "pixel":
        raise ValueError("dither solo esta disponible en mode pixel")
    if palette_algorithm not in PALETTE_ALGORITHMS:
        raise ValueError("palette-algorithm desconocido: %s" % palette_algorithm)
    bits = int(perceptual_lut_bits)
    if bits != 0 and not (3 <= bits <= 7):
        raise ValueError("perceptual-lut-bits debe ser 0 (exacto) o 3..7")
    if not (0.0 <= float(dither_budget) <= 1.0):
        raise ValueError("dither-budget debe estar entre 0 y 1")
    if float(dither_min_improvement) < 0.0:
        raise ValueError("dither-min-improvement debe ser >= 0")
    if int(dither_window) <= 0:
        raise ValueError("dither-window debe ser > 0")
    if not (0 <= int(palette_refit) <= 10):
        raise ValueError("palette-refit debe estar entre 0 (off) y 10")
    if not (0 <= int(palette_uint8_refine) <= 10):
        raise ValueError("palette-uint8-refine debe estar entre 0 (off) y 10")
    if int(palette_uint8_refine) and palette_algorithm != "kmeans-oklab":
        raise ValueError("palette-uint8-refine solo aplica a kmeans-oklab (E-13)")
    if int(reserved) < 0:
        raise ValueError("reserved debe ser >= 0")
    if int(reserved) > 0 and int(pal_size) < int(reserved) + 22:
        raise ValueError("palette-size debe ser >= reserved + 22 (INT-001)")
    # Construir la configuracion tambien valida min/max, umbrales y estabilidad.
    adaptive_palette.AdaptivePaletteConfig(
        min_frames=adaptive_min_frames, max_frames=adaptive_max_frames,
        change_threshold=adaptive_change_threshold,
        hard_cut_threshold=adaptive_hard_cut_threshold,
        max_stability=adaptive_stability_max)


def soft_base_size(cols, rows):
    """Tamano de la matriz base usada por la reconstruccion offline 2x."""
    return (max(1, int(round(cols * SOFT_BAKE_SCALE))),
            max(1, int(round(rows * SOFT_BAKE_SCALE))))


def resize_pil_for_grid(src, cols, rows, bake_smoothing):
    """Muestrea una imagen directamente a la grilla final o a una base 1/2 + 2x.

    En `soft`, los pixeles bilineales quedan almacenados antes de cuantizar. El player
    no ejecuta el filtro y Canvas/WebGL reciben exactamente la misma matriz horneada.
    """
    if bake_smoothing == "none":
        return src.resize((cols, rows), Image.LANCZOS)
    if bake_smoothing != "soft":
        raise ValueError("bake-smoothing debe ser none o soft")
    base = src.resize(soft_base_size(cols, rows), Image.LANCZOS)
    return base.resize((cols, rows), Image.BILINEAR)


def compute_grid(src_w, src_h, cols, rows, mode, char_aspect):
    if cols <= 0:
        raise ValueError("cols debe ser > 0")
    if src_w <= 0 or src_h <= 0:
        raise ValueError("dimensiones de fuente invalidas: %dx%d" % (src_w, src_h))
    factor = 1.0 if mode == MODE_PIXEL else char_aspect
    out_rows = rows if (rows and rows > 0) else max(1, int(round(cols * (src_h / src_w) * factor)))
    if cols > 65535 or out_rows > 65535:
        raise ValueError("la grilla excede el limite 65535x65535 de ASCL v1")
    return int(cols), int(out_rows)


def _palette_image(palette):
    """Crea una imagen P que limita quantize_with a los colores declarados.

    Pillow siempre guarda 256 entradas RGB en una paleta. Los indices sobrantes se
    rellenan con el ultimo color, pero no se marcan como usados en la imagen P; asi
    `quantize(palette=...)` nunca produce un indice fuera de ASCL `pal_count`.
    """
    palette = np.asarray(palette, dtype=np.uint8)
    if palette.ndim != 2 or palette.shape[1] != 3 or not (1 <= len(palette) <= 256):
        raise ValueError("palette debe tener forma Nx3, con 1..256 colores")
    pal_img = Image.new("P", (len(palette), 1))
    pal_img.putdata(list(range(len(palette))))
    raw = palette.reshape(-1).tolist()
    raw.extend(palette[-1].tolist() * (256 - len(palette)))
    pal_img.putpalette(raw)
    return pal_img


def _kmeans_rgb_numpy(samples, pal_size, max_iter=30, tolerance=0.25):
    """Fallback K-means RGB determinista y acotado cuando OpenCV no esta completo."""
    values = np.asarray(samples, dtype=np.float64).reshape(-1, 3)
    count = int(pal_size)
    weights = np.ones(len(values), dtype=np.float64)
    centers = perceptual_palette._initial_centers(values, weights, count, 4096)
    for _iteration in range(int(max_iter)):
        labels, minimum = perceptual_palette._nearest_indices(
            values, centers, chunk_size=4096, return_distance=True)
        counts = np.bincount(labels, minlength=count)
        updated = centers.copy()
        occupied = counts > 0
        for channel in range(3):
            sums = np.bincount(labels, weights=values[:, channel],
                               minlength=count)
            updated[occupied, channel] = sums[occupied] / counts[occupied]
        empty = np.flatnonzero(~occupied)
        if len(empty):
            candidates = np.argsort(-minimum, kind="mergesort")
            used = set()
            cursor = 0
            for center_index in empty:
                while cursor < len(candidates) and int(candidates[cursor]) in used:
                    cursor += 1
                sample_index = int(candidates[min(cursor, len(candidates) - 1)])
                used.add(sample_index)
                updated[center_index] = values[sample_index]
                cursor += 1
        shift = float(np.max(np.sqrt(np.sum((updated - centers) ** 2, axis=1))))
        centers = updated
        if shift <= float(tolerance):
            break
    return np.clip(np.rint(centers), 0, 255).astype(np.uint8)


def _sort_palette_centers(centers):
    """Orden explicito comun a ambas ramas de K-means RGB.

    El color reconstruido no cambia y los bytes quedan estables aunque una
    implementacion (OpenCV o el fallback NumPy) enumere clusters en otro orden.
    """
    centers = np.asarray(centers, dtype=np.uint8)
    return centers[np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))]


def _validate_reserved_colors(reserved, reserved_colors):
    """RGB fijos del operador para las entradas reservadas (INT-001, INV-4)."""
    if reserved_colors is None:
        raise ValueError(
            "reserved>0 requiere reserved_colors: los RGB fijos de las "
            "entradas reservadas los declara el operador")
    colors = np.asarray(reserved_colors, dtype=np.uint8)
    if colors.shape != (int(reserved), 3):
        raise ValueError("reserved_colors debe tener forma (reserved, 3)")
    return colors


def _kmeans_rgb_palette(sample_imgs, pal_size, max_samples=65536, seed=20260811,
                        reserved=0):
    """Paleta RGB K-means: OpenCV completo o fallback NumPy determinista."""
    if int(reserved) > 0:
        raise ValueError(
            "reserved se resuelve en make_global_palette; los builders "
            "reciben pal_size ya reducido")
    cv2 = None
    try:
        import cv2
    except (ImportError, OSError):
        pass
    pixels = np.concatenate([np.asarray(im, dtype=np.uint8).reshape(-1, 3)
                             for im in sample_imgs], axis=0)
    if not len(pixels):
        raise ValueError("no hay pixeles para construir la paleta")
    sample_count = min(int(max_samples), len(pixels))
    positions = np.linspace(0, len(pixels) - 1, sample_count, dtype=np.int64)
    samples = np.ascontiguousarray(pixels[positions], dtype=np.float32)
    # kmeans requiere al menos K observaciones. En imagenes diminutas conservamos
    # el contrato de pal_size repitiendo muestras de forma determinista.
    if len(samples) < int(pal_size):
        samples = np.ascontiguousarray(np.resize(samples, (int(pal_size), 3)),
                                       dtype=np.float32)
    complete_cv2 = (cv2 is not None and
                    all(hasattr(cv2, name) for name in (
                        "setRNGSeed", "kmeans", "TERM_CRITERIA_EPS",
                        "TERM_CRITERIA_MAX_ITER", "KMEANS_PP_CENTERS")))
    if complete_cv2:
        cv2.setRNGSeed(int(seed))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                    30, 0.25)
        _compactness, _labels, centers = cv2.kmeans(
            samples, int(pal_size), None, criteria, 1,
            cv2.KMEANS_PP_CENTERS)
        centers = np.clip(np.rint(centers), 0, 255).astype(np.uint8)
        return _sort_palette_centers(centers)
    return _sort_palette_centers(
        _kmeans_rgb_numpy(samples, pal_size, max_iter=30, tolerance=0.25))


def make_global_palette(sample_imgs, pal_size, palette_algorithm="median-cut",
                        previous_palette=None, temporal_strength=0.0, reserved=0,
                        reserved_colors=None, uint8_refine=0):
    """Construye una paleta ASCL y su imagen Pillow compatible.

    Los parametros temporales solo afectan ``kmeans-oklab``. Se agregan al final
    para preservar las llamadas historicas de tres argumentos.

    Con ``reserved>0`` (INT-001) construye ``pal_size - reserved`` colores base
    y estampa ``reserved_colors`` al final, bit-identicos en toda epoca (INV-4).
    La ``pal_img`` devuelta contiene SOLO la parte base: es el objeto de
    cuantizacion, y el video base nunca puede elegir un indice reservado
    (INV-3). La paleta devuelta si es completa (base + reservadas).
    """
    if not sample_imgs:
        raise ValueError("sample_imgs no puede estar vacio")
    reserved = int(reserved)
    if reserved > 0:
        stamped = _validate_reserved_colors(reserved, reserved_colors)
        base_size = int(pal_size) - reserved
        if base_size < 22:
            raise ValueError("palette-size debe ser >= reserved + 22 (INT-001)")
        base_previous = None
        if previous_palette is not None:
            base_previous = np.asarray(previous_palette)
            if len(base_previous) == int(pal_size):
                # la paleta previa llega completa: la parte reservada no se
                # estabiliza ni se alinea, solo se vuelve a estampar
                base_previous = base_previous[:base_size]
        base_img, base_palette = make_global_palette(
            sample_imgs, base_size, palette_algorithm,
            previous_palette=base_previous,
            temporal_strength=temporal_strength, uint8_refine=uint8_refine)
        palette = np.concatenate(
            [np.asarray(base_palette, dtype=np.uint8), stamped], axis=0)
        return base_img, palette
    if palette_algorithm == "kmeans-oklab":
        palette = perceptual_palette.build_perceptual_palette(
            sample_imgs, pal_size, previous_palette=previous_palette,
            temporal_strength=temporal_strength, uint8_refine=uint8_refine)
        return _palette_image(palette), palette
    if int(uint8_refine):
        raise ValueError("uint8_refine solo aplica a kmeans-oklab (E-13)")
    if palette_algorithm == "kmeans-rgb":
        palette = _kmeans_rgb_palette(sample_imgs, pal_size)
        return _palette_image(palette), palette
    h = sum(im.shape[0] for im in sample_imgs)
    w = sample_imgs[0].shape[1]
    stack = np.zeros((h, w, 3), np.uint8)
    y = 0
    for im in sample_imgs:
        stack[y:y + im.shape[0]] = im
        y += im.shape[0]
    methods = {
        "median-cut": Image.MEDIANCUT,
        "fast-octree": Image.FASTOCTREE,
    }
    if palette_algorithm not in methods:
        raise ValueError("palette-algorithm desconocido: %s" % palette_algorithm)
    pal_img = Image.fromarray(stack, "RGB").quantize(
        colors=pal_size, method=methods[palette_algorithm], dither=Image.NONE)
    palette = np.array(pal_img.getpalette()[: pal_size * 3],
                       dtype=np.uint8).reshape(-1, 3)
    return pal_img, palette


def iter_frame_blocks(frames_iter, block_frames):
    """Agrupa un stream en bloques acotados sin materializar el video completo."""
    block_frames = int(block_frames)
    if block_frames <= 0:
        raise ValueError("block_frames debe ser > 0")
    block = []
    for frame in frames_iter:
        block.append(frame)
        if len(block) >= block_frames:
            yield block
            block = []
    if block:
        yield block


def sample_palette_frames(frame_block, max_samples=12):
    """Selecciona RGBs repartidos por todo un bloque, incluyendo sus extremos."""
    max_samples = int(max_samples)
    if max_samples <= 0:
        raise ValueError("max_samples debe ser > 0")
    n = len(frame_block)
    if n <= max_samples:
        return [frame[0] for frame in frame_block]
    if max_samples == 1:
        return [frame_block[n // 2][0]]
    indices = [(i * (n - 1)) // (max_samples - 1) for i in range(max_samples)]
    return [frame_block[i][0] for i in indices]


def iter_block_palette_frames(frames_iter, pal_size, block_frames, max_samples=12,
                              palette_algorithm="median-cut", reserved=0,
                              reserved_colors=None):
    """Anota cada frame con la paleta temporal de su bloque.

    Solo conserva `block_frames` RGB/grises y el pequeno conjunto usado para crear
    la paleta. El booleano final marca el primer frame, donde DELTA debe reiniciarse.
    """
    for block in iter_frame_blocks(frames_iter, block_frames):
        samples = sample_palette_frames(block, max_samples)
        pal_img, palette = make_global_palette(samples, pal_size, palette_algorithm,
                                               reserved=reserved,
                                               reserved_colors=reserved_colors)
        for block_index, (rgb, gray) in enumerate(block):
            yield rgb, gray, pal_img, palette, block_index == 0


def iter_scene_palette_frames(frames_iter, pal_size, palette_mode, block_frames,
                              adaptive_config, max_samples=12,
                              palette_algorithm="median-cut",
                              perceptual_lut_bits=0, reserved=0,
                              reserved_colors=None, palette_refit=0,
                              palette_uint8_refine=0):
    """Anota frames de bloques fijos o adaptativos con recursos de cuantizacion.

    La salida extiende internamente la tupla historica con cuantizador Oklab y un
    diagnostico por bloque. El API publico anterior ``iter_block_palette_frames``
    permanece sin cambios para callers externos.
    """
    previous_palette = None
    previous_last_descriptor = None
    absolute_start = 0
    if palette_mode == "adaptive":
        block_source = adaptive_palette.iter_adaptive_palette_blocks(
            frames_iter, adaptive_config)
    else:
        block_source = iter_frame_blocks(frames_iter, block_frames)

    for block_number, source_block in enumerate(block_source):
        if palette_mode == "adaptive":
            block = list(source_block.frames)
            entry_reason = source_block.entry_reason
            entry_score = float(source_block.entry_change_score)
            stability = float(source_block.stability_strength)
            boundary_reason = source_block.boundary_reason
            boundary_score = float(source_block.boundary_score)
            absolute_start = source_block.start_index
        else:
            block = source_block
            first_descriptor = adaptive_palette.describe_frame_color(
                block[0], adaptive_config)
            if previous_last_descriptor is None:
                entry_reason = "start-of-stream"
                entry_score = 1.0
                stability = 0.0
            else:
                transition = adaptive_palette.color_change_metrics(
                    previous_last_descriptor, first_descriptor, adaptive_config)
                entry_score = float(transition["score"])
                is_hard_cut = entry_score >= adaptive_config.hard_cut_threshold
                entry_reason = "hard-cut" if is_hard_cut else "fixed-boundary"
                stability = adaptive_palette.temporal_stability_strength(
                    entry_score, hard_cut=is_hard_cut, config=adaptive_config)
            final_descriptor = adaptive_palette.describe_frame_color(
                block[-1], adaptive_config)
            within = adaptive_palette.color_change_metrics(
                first_descriptor, final_descriptor, adaptive_config)
            boundary_reason = "fixed-size"
            boundary_score = float(within["score"])

        samples = sample_palette_frames(block, max_samples)
        pal_img, palette = make_global_palette(
            samples, pal_size, palette_algorithm,
            previous_palette=previous_palette,
            temporal_strength=stability, reserved=reserved,
            reserved_colors=reserved_colors,
            uint8_refine=palette_uint8_refine)
        pal_img, palette = refit_block_palette(
            pal_img, palette, samples, palette_algorithm, palette_refit,
            reserved=reserved, perceptual_lut_bits=perceptual_lut_bits)
        # El cuantizador solo ve la parte base: el video nunca elige una
        # entrada reservada (INV-3).
        quantizer = make_perceptual_quantizer(
            palette[:len(palette) - int(reserved)] if int(reserved) else palette,
            palette_algorithm, perceptual_lut_bits)
        diagnostic = {
            "index": int(block_number),
            "start": int(absolute_start),
            "end": int(absolute_start + len(block)),
            "size": int(len(block)),
            "reason": str(boundary_reason),
            "score": float(boundary_score),
            "entry_reason": str(entry_reason),
            "entry_score": float(entry_score),
            "stability": float(stability),
        }
        hard_cut_start = entry_reason == "hard-cut"
        for block_index, (rgb, gray) in enumerate(block):
            yield (rgb, gray, pal_img, palette, quantizer,
                   block_index == 0, diagnostic if block_index == 0 else None,
                   hard_cut_start and block_index == 0)
        previous_palette = palette
        previous_last_descriptor = adaptive_palette.describe_frame_color(
            block[-1], adaptive_config)
        absolute_start += len(block)


def quantize_with(pal_img, rgb):
    im = Image.fromarray(rgb, "RGB").quantize(palette=pal_img, dither=Image.NONE)
    return np.asarray(im, dtype=np.uint8)


def make_perceptual_quantizer(palette, palette_algorithm, perceptual_lut_bits=0):
    """Devuelve cuantizador Oklab o ``None`` para los algoritmos Pillow/RGB."""
    if palette_algorithm != "kmeans-oklab":
        return None
    bits = int(perceptual_lut_bits)
    return perceptual_palette.PerceptualQuantizer(
        palette, lut_bits=(None if bits == 0 else bits))


def make_dither_pair_lut(palette, quantizer=None):
    """Usa la misma regla base de cuantizacion que produjo los indices."""
    return selective_dither.PairLUT(
        palette, base_quantizer=(quantizer if quantizer is not None else None))


def quantize_palette_rgb(pal_img, rgb, quantizer=None):
    if quantizer is not None:
        return np.asarray(quantizer.quantize(rgb), dtype=np.uint8)
    return quantize_with(pal_img, rgb)


def _refit_assignment(pixels, base_palette, palette_algorithm, perceptual_lut_bits):
    """Asigna pixeles (N, 3) con la MISMA regla de cuantizacion del encode."""
    if palette_algorithm == "kmeans-oklab":
        bits = int(perceptual_lut_bits)
        quantizer = perceptual_palette.PerceptualQuantizer(
            base_palette, lut_bits=(None if bits == 0 else bits))
        return np.asarray(quantizer.quantize(pixels), dtype=np.uint8).reshape(-1)
    return np.asarray(quantize_with(_palette_image(base_palette),
                                    pixels.reshape(-1, 1, 3)),
                      dtype=np.uint8).reshape(-1)


def refit_palette(palette, sample_imgs, palette_algorithm="median-cut",
                  iterations=0, reserved=0, perceptual_lut_bits=0,
                  sample_weights=None):
    """E-12: refit de paleta a la asignacion real (Lloyd acotado y monotono).

    Reasigna los pixeles de ``sample_imgs`` con la misma regla de cuantizacion
    que usara el encode y reemplaza cada entrada base por la media
    (``np.bincount``) de sus pixeles asignados. Una iteracion se acepta solo si
    baja el error en la metrica del algoritmo (Oklab para kmeans-oklab, RGB
    para el resto): el refit nunca degrada la paleta de la que parte. Las
    entradas reservadas (INV-4) no se tocan y la asignacion solo ve la parte
    base, asi ninguna media converge hacia una reservada (INV-3).
    """
    iterations = int(iterations)
    if not (0 <= iterations <= 10):
        raise ValueError("palette-refit debe estar entre 0 (off) y 10")
    palette = np.asarray(palette, dtype=np.uint8)
    if iterations == 0:
        return palette
    reserved = int(reserved)
    if reserved:
        base = palette[:len(palette) - reserved]
        stamped = palette[len(palette) - reserved:]
    else:
        base, stamped = palette, None
    if not len(base):
        raise ValueError("refit requiere al menos una entrada base")
    pixels = np.concatenate([np.asarray(im, dtype=np.uint8).reshape(-1, 3)
                             for im in sample_imgs], axis=0)
    if not len(pixels):
        raise ValueError("no hay pixeles para el refit de paleta")
    if sample_weights is not None:
        # E-14: el refit tambien acepta agregados (color unico, masa) para no
        # re-expandir el stream; con None el camino historico queda intacto.
        sample_weights = np.asarray(sample_weights, dtype=np.float64).reshape(-1)
        if len(sample_weights) != len(pixels):
            raise ValueError("sample_weights debe alinear con los pixeles")
        if not np.all(np.isfinite(sample_weights)) or \
                not np.all(sample_weights > 0.0):
            raise ValueError("sample_weights debe ser finito y > 0")
    perceptual = palette_algorithm == "kmeans-oklab"
    metric_pixels = (perceptual_palette.srgb_to_oklab(pixels) if perceptual
                     else pixels.astype(np.float64))

    def assignment_error(candidate, indices):
        centers = (perceptual_palette.srgb_to_oklab(candidate) if perceptual
                   else candidate.astype(np.float64))
        diff = metric_pixels - centers[indices]
        squared = np.einsum("ij,ij->i", diff, diff)
        if sample_weights is None:
            return float(np.mean(squared))
        return float(np.sum(squared * sample_weights) /
                     np.sum(sample_weights))

    current = base
    indices = _refit_assignment(pixels, current, palette_algorithm,
                                perceptual_lut_bits)
    error = assignment_error(current, indices)
    for _ in range(iterations):
        if sample_weights is None:
            counts = np.bincount(indices, minlength=len(current))
        else:
            counts = np.bincount(indices, weights=sample_weights,
                                 minlength=len(current))
        used = counts > 0
        refit = current.astype(np.float64).copy()
        for channel in range(3):
            channel_weights = (pixels[:, channel] if sample_weights is None
                               else sample_weights * pixels[:, channel])
            sums = np.bincount(indices, weights=channel_weights,
                               minlength=len(current))
            refit[used, channel] = sums[used] / counts[used]
        candidate = np.clip(np.rint(refit), 0, 255).astype(np.uint8)
        if np.array_equal(candidate, current):
            break
        candidate_indices = _refit_assignment(pixels, candidate,
                                              palette_algorithm,
                                              perceptual_lut_bits)
        candidate_error = assignment_error(candidate, candidate_indices)
        if candidate_error >= error:
            break
        current, indices, error = candidate, candidate_indices, candidate_error
    if stamped is not None:
        return np.concatenate([current, stamped], axis=0)
    return current


def refit_block_palette(pal_img, palette, sample_imgs, palette_algorithm,
                        iterations, reserved=0, perceptual_lut_bits=0):
    """Aplica el refit E-12 y reconstruye la ``pal_img`` solo-base (INV-3)."""
    if not int(iterations):
        return pal_img, palette
    palette = refit_palette(palette, sample_imgs, palette_algorithm,
                            iterations, reserved=reserved,
                            perceptual_lut_bits=perceptual_lut_bits)
    reserved = int(reserved)
    base = palette[:len(palette) - reserved] if reserved else palette
    return _palette_image(base), palette


def global_palette_from_aggregate(colors, weights, pal_size,
                                  reserved=0, reserved_colors=None,
                                  uint8_refine=0):
    """E-14: paleta global kmeans-oklab desde el agregado de TODO el video.

    Espejo de ``make_global_palette`` para el camino de dos pasadas: resuelve
    la reserva igual (base ``pal_size - reserved`` + estampadas al final,
    INV-4) y la ``pal_img`` devuelta es solo-base (INV-3).
    """
    reserved = int(reserved)
    if reserved:
        stamped = _validate_reserved_colors(reserved, reserved_colors)
        base_size = int(pal_size) - reserved
        if base_size < 22:
            raise ValueError("palette-size debe ser >= reserved + 22 (INT-001)")
    else:
        stamped = None
        base_size = int(pal_size)
    base = perceptual_palette.build_perceptual_palette(
        None, base_size, sample_aggregate=(colors, weights),
        uint8_refine=uint8_refine)
    palette = (np.concatenate([np.asarray(base, dtype=np.uint8), stamped],
                              axis=0)
               if stamped is not None else base)
    return _palette_image(base), palette


def quantize_per_frame(rgb, pal_size, palette_algorithm="median-cut",
                       perceptual_lut_bits=0, previous_palette=None,
                       temporal_strength=0.0, reserved=0, reserved_colors=None,
                       palette_refit=0, palette_uint8_refine=0):
    h, w, _ = rgb.shape
    reserved = int(reserved)
    if palette_algorithm != "median-cut":
        pal_img, palette = make_global_palette(
            [rgb], pal_size, palette_algorithm,
            previous_palette=previous_palette,
            temporal_strength=temporal_strength, reserved=reserved,
            reserved_colors=reserved_colors,
            uint8_refine=palette_uint8_refine)
        pal_img, palette = refit_block_palette(
            pal_img, palette, [rgb], palette_algorithm, palette_refit,
            reserved=reserved, perceptual_lut_bits=perceptual_lut_bits)
        quantizer = make_perceptual_quantizer(
            palette[:len(palette) - reserved] if reserved else palette,
            palette_algorithm, perceptual_lut_bits)
        idx = quantize_palette_rgb(pal_img, rgb, quantizer).reshape(h, w)
        return idx, palette
    if reserved:
        stamped = _validate_reserved_colors(reserved, reserved_colors)
        base_size = int(pal_size) - reserved
        if base_size < 22:
            raise ValueError("palette-size debe ser >= reserved + 22 (INT-001)")
    else:
        stamped = None
        base_size = int(pal_size)
    im = Image.fromarray(rgb, "RGB").quantize(colors=base_size, method=Image.MEDIANCUT,
                                              dither=Image.NONE)
    idx = np.asarray(im, dtype=np.uint8).reshape(h, w)
    pal_count = max(int(idx.max()) + 1, 1)
    palette = np.array(im.getpalette()[: pal_count * 3], dtype=np.uint8).reshape(-1, 3)
    if int(palette_refit):
        # El refit no agrega entradas: los indices reasignados siguen < pal_count.
        palette = refit_palette(palette, [rgb], "median-cut", palette_refit)
        idx = np.asarray(quantize_with(_palette_image(palette), rgb),
                         dtype=np.uint8).reshape(h, w)
    if stamped is not None:
        # median-cut per-frame conserva su paleta recortada a los colores
        # usados; las reservadas se estampan siempre como las ultimas entradas
        palette = np.concatenate([palette, stamped], axis=0)
    return idx, palette


def gray_to_char_idx(gray, ramp_len):
    idx = (gray.astype(np.uint16) * ramp_len) // 256
    return np.clip(idx, 0, ramp_len - 1).astype(np.uint8)


def frame_to_cells(rgb, gray, mode, ramp_len, pal_size, palette_mode, pal_img,
                   palette_algorithm="median-cut", quantizer=None,
                   perceptual_lut_bits=0, previous_palette=None,
                   temporal_strength=0.0, reserved=0, reserved_colors=None,
                   palette_refit=0, palette_uint8_refine=0):
    h, w = gray.shape
    N = h * w
    if mode == MODE_PIXEL:
        if palette_mode == "global":
            idx = quantize_palette_rgb(pal_img, rgb, quantizer)
            return idx.reshape(N, 1), None, 0
        idx, pal = quantize_per_frame(
            rgb, pal_size, palette_algorithm, perceptual_lut_bits,
            previous_palette, temporal_strength, reserved, reserved_colors,
            palette_refit, palette_uint8_refine)
        return idx.reshape(N, 1), pal, pal.shape[0]
    char_idx = gray_to_char_idx(gray, ramp_len).reshape(N, 1)
    if mode == MODE_ASCII_BW:
        return char_idx, None, 0
    if mode == MODE_ASCII_PAL:
        if palette_mode == "global":
            color = quantize_palette_rgb(pal_img, rgb, quantizer).reshape(N, 1)
            return np.concatenate([char_idx, color], axis=1), None, 0
        color, pal = quantize_per_frame(
            rgb, pal_size, palette_algorithm, perceptual_lut_bits,
            previous_palette, temporal_strength, reserved, reserved_colors,
            palette_refit, palette_uint8_refine)
        return np.concatenate([char_idx, color.reshape(N, 1)], axis=1), pal, pal.shape[0]
    if mode == MODE_ASCII_RGB:
        return np.concatenate([char_idx, rgb.reshape(N, 3)], axis=1), None, 0
    raise ValueError("modo desconocido")


def apply_dither_mode(rgb, cells, palette, dither_mode="off", dither_matrix=4,
                      pair_lut=None, temporal_state=None,
                      dither_budget=selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                      dither_min_improvement=selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                      dither_window=selective_dither.DEFAULT_TEMPORAL_WINDOW,
                      protected_rects=None):
    """Hornea el modo de dithering elegido y conserva el shape de ``cells``."""
    if dither_mode == "off":
        return cells, None
    baseline = cells[:, 0].reshape(rgb.shape[:2])
    if dither_mode == "selective":
        result = selective_dither.apply_selective_dither(
            rgb, baseline, palette, matrix_size=dither_matrix,
            pair_lut=pair_lut, protected_rects=protected_rects)
        return result.reshape(-1, 1), None
    if dither_mode == "auto":
        result, details = selective_dither.apply_calibrated_dither(
            rgb, baseline, palette, matrix_size=dither_matrix,
            pair_lut=pair_lut, max_changed_fraction=dither_budget,
            min_proxy_improvement=dither_min_improvement,
            temporal_state=temporal_state, temporal_window=dither_window,
            protected_rects=protected_rects,
            # La paleta puede renovarse sin que cambie la escena. La evidencia se
            # conserva entre bloques y el encoder resetea el estado solo en hard cut.
            temporal_context="ascl-video", reset_on_palette_change=False,
            return_details=True)
        return result.reshape(-1, 1), details
    raise ValueError("dither desconocido: %s" % dither_mode)


def cells_to_planes_bytes(cells, mode):
    if mode in (MODE_PIXEL, MODE_ASCII_BW):
        return cells[:, 0].tobytes()
    if mode == MODE_ASCII_PAL:
        return cells[:, 0].tobytes() + cells[:, 1].tobytes()
    if mode == MODE_ASCII_RGB:
        return cells[:, 0].tobytes() + cells[:, 1:4].tobytes()
    raise ValueError


def encode_frame(cells, prev_cells, mode, frame_index, keyframe, compress, delta_allowed):
    planes = cells_to_planes_bytes(cells, mode)
    candidates = []
    full_z = best_deflate(planes, 9)
    if compress == "none":
        candidates.append((TAG_RAW, planes))
    elif compress == "zlib":
        candidates.append((TAG_ZLIB, full_z))
    else:
        candidates.append((TAG_ZLIB, full_z) if len(full_z) < len(planes) else (TAG_RAW, planes))
    if delta_allowed and (not keyframe) and prev_cells is not None:
        changed = np.any(cells != prev_cells, axis=1)
        ci = np.nonzero(changed)[0].astype("<u4")
        if ci.size < cells.shape[0]:
            vals = cells[changed]
            delta_z = best_deflate(ci.tobytes() + vals.tobytes(), 9)
            candidates.append((TAG_DELTA, delta_z))
            mask = np.packbits(changed.astype(np.uint8), bitorder="little")
            mask_z = best_deflate(mask.tobytes() + vals.tobytes(), 9)
            candidates.append((TAG_DELTA_MASK, mask_z))
    tag, payload = min(candidates, key=lambda c: len(c[1]))
    if len(planes) < len(payload):
        tag, payload = TAG_RAW, planes
    return tag, payload


def write_ascl(path, mode, cols, rows, fps, ramp, frames, palette0, char_aspect, flags_extra):
    ramp_bytes = ramp.encode("ascii") if ramp else b""
    ramp_len   = len(ramp_bytes)
    if ramp_len > 255:
        raise ValueError("la rampa excede 255 bytes (limite ASCL v1)")
    pal_size   = palette0.shape[0] if palette0 is not None else 0
    if pal_size == 0:
        for fr in frames:
            if fr["pal_count"]:
                pal_size = max(pal_size, fr["pal_count"])
    n_frames = len(frames)
    if n_frames > UINT32_MAX:
        raise ValueError("n_frames excede uint32 (limite ASCL v1)")
    flags    = FLAG_HAS_OFFSET_TABLE | flags_extra
    blocks = []
    for fr in frames:
        body = struct.pack("<BH", fr["tag"], fr["pal_count"])
        if fr["pal_count"] > 0:
            body += fr["palette"].astype(np.uint8).tobytes()
        body += fr["payload"]
        if len(body) > UINT32_MAX:
            raise ValueError("un frame excede uint32 bytes (limite ASCL v1)")
        blocks.append(struct.pack("<I", len(body)) + body)
    data_off = HEADER_SIZE + ramp_len
    off = data_off + n_frames * 4
    if off > UINT32_MAX:
        raise ValueError("la tabla de offsets excede uint32 (limite ASCL v1)")
    offs = []
    for b in blocks:
        if off > UINT32_MAX:
            raise ValueError("un offset excede uint32 (limite ASCL v1)")
        offs.append(off)
        off += len(b)
        if off > UINT32_MAX + 1:
            raise ValueError("el archivo excede 4 GiB (limite de offsets ASCL v1)")
    offset_table = struct.pack("<%dI" % n_frames, *offs)
    body = ramp_bytes + offset_table + b"".join(blocks)
    crc  = zlib.crc32(body) & 0xFFFFFFFF
    char_aspect_x1000 = int(round((char_aspect if mode != MODE_PIXEL else 1.0) * 1000))
    header = struct.pack(HEADER_FMT, MAGIC, VERSION, mode, flags, fps,
                         cols, rows, pal_size, n_frames, ramp_len,
                         CELL_FMT[mode], data_off, char_aspect_x1000, 0, crc)
    with open(path, "wb") as f:
        f.write(header)
        f.write(body)
    return len(header) + len(body)


def extract_audio(in_path, mp3_path):
    ffmpeg = "ffmpeg"
    try:
        import shutil
        ffmpeg = shutil.which("ffmpeg") or ffmpeg
    except Exception:
        pass
    if ffmpeg == "ffmpeg":
        try:
            # Alternativa autocontenida para Windows/entornos de procesamiento donde
            # FFmpeg no esta instalado globalmente. No afecta al player ni al formato.
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-i", in_path, "-vn", "-acodec", "libmp3lame",
             "-q:a", "4", mp3_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0 and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
    except Exception:
        return False


def output_source_index(output_index, src_fps, target_fps):
    """Devuelve el frame fuente para el instante output_index/target_fps.

    El sample-and-hold conserva la duracion cuando las tasas no son divisibles
    (por ejemplo 25 -> 15) y tambien permite duplicar al convertir 15 -> 25.
    """
    if output_index < 0 or src_fps <= 0 or target_fps <= 0:
        raise ValueError("indices y fps deben ser positivos")
    return int((float(output_index) * float(src_fps)) / float(target_fps))


def iter_video_frames(in_path, cols, rows, target_fps, bake_smoothing="none"):
    import cv2
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise RuntimeError("no se pudo abrir el video: %s" % in_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
    # Contenedores mal indexados reportan NaN o valores absurdos; int(NaN) en
    # output_source_index aborta el encode con un error opaco a mitad de camino.
    if not (0 < src_fps < 1000):
        src_fps = target_fps
    i = -1
    output_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        repeats = 0
        while output_source_index(output_index, src_fps, target_fps) == i:
            repeats += 1
            output_index += 1
        if repeats == 0:
            continue
        if bake_smoothing == "soft":
            base = cv2.resize(frame, soft_base_size(cols, rows), interpolation=cv2.INTER_AREA)
            small = cv2.resize(base, (cols, rows), interpolation=cv2.INTER_LINEAR)
        else:
            small = cv2.resize(frame, (cols, rows), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        # Derivar luminancia despues del horneado mantiene char/color sincronizados.
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        rgb = np.ascontiguousarray(rgb)
        gray = np.ascontiguousarray(gray)
        for _ in range(repeats):
            yield rgb, gray
    cap.release()


def probe_size(in_path):
    import cv2
    cap = cv2.VideoCapture(in_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return w, h


def encode_image(in_path, out_path, mode_name, cols, rows, fps, pal_size,
                 ramp_name, char_aspect, compress, palette_mode, dump_cells=None,
                 bake_smoothing="none", reconstruction="nearest",
                 quality_profile="custom", dither_mode="off", dither_matrix=4,
                 palette_algorithm="median-cut", perceptual_lut_bits=0,
                 dither_budget=selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                 dither_min_improvement=selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                 dither_window=selective_dither.DEFAULT_TEMPORAL_WINDOW,
                 palette_refit=0, palette_uint8_refine=0):
    validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            dither_mode=dither_mode, dither_matrix=dither_matrix,
                            palette_algorithm=palette_algorithm,
                            perceptual_lut_bits=perceptual_lut_bits,
                            dither_budget=dither_budget,
                            dither_min_improvement=dither_min_improvement,
                            dither_window=dither_window,
                            palette_refit=palette_refit,
                            palette_uint8_refine=palette_uint8_refine)
    if palette_mode != "per-frame":
        raise ValueError(
            "encode_image solo admite --palette per-frame: una imagen no tiene "
            "bloques temporales (recibido: %r)" % (palette_mode,))
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    src = Image.open(in_path).convert("RGB")
    sw, sh = src.size
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    small = resize_pil_for_grid(src, cols, rows, bake_smoothing)
    rgb = np.ascontiguousarray(np.asarray(small, np.uint8))
    gray = np.asarray(Image.fromarray(rgb, "RGB").convert("L"), np.uint8)
    cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                               "per-frame", None, palette_algorithm,
                                               perceptual_lut_bits=perceptual_lut_bits,
                                               palette_refit=palette_refit,
                                               palette_uint8_refine=palette_uint8_refine)
    dither_details = None
    if dither_mode != "off":
        image_quantizer = make_perceptual_quantizer(
            palette, palette_algorithm, perceptual_lut_bits)
        pair_lut = make_dither_pair_lut(palette, image_quantizer)
        cells, dither_details = apply_dither_mode(
            rgb, cells, palette, dither_mode, dither_matrix,
            pair_lut=pair_lut, dither_budget=dither_budget,
            dither_min_improvement=dither_min_improvement,
            dither_window=dither_window)
    tag, payload = encode_frame(cells, None, mode, 0, True, compress, False)
    frames = [{"tag": tag, "pal_count": pal_count, "palette": palette, "payload": payload}]
    if dump_cells:
        np.savez(dump_cells, frame_0000=cells)
    flags_extra = FLAG_RECON_SOFT if reconstruction == "soft" else 0
    total = write_ascl(out_path, mode, cols, rows, fps, ramp, frames, None,
                       char_aspect, flags_extra)
    return {"kind": "image", "mode": mode_name, "cols": cols, "rows": rows,
            "n_frames": 1, "bytes_total": total, "src": (sw, sh),
            "pal_size": pal_size, "quality_profile": quality_profile,
            "bake_smoothing": bake_smoothing, "reconstruction": reconstruction,
            "palette_algorithm": palette_algorithm,
            "palette_refit": int(palette_refit),
            "palette_uint8_refine": int(palette_uint8_refine),
            "perceptual_lut_bits": int(perceptual_lut_bits),
            "dither": dither_mode, "dither_matrix": int(dither_matrix),
            "dither_budget": float(dither_budget),
            "dither_min_improvement": float(dither_min_improvement),
            "dither_window": int(dither_window),
            "dither_changed_cells": (int(dither_details["changed_cells"])
                                     if dither_details is not None else 0),
            "flags": FLAG_HAS_OFFSET_TABLE | flags_extra}


def encode_video(in_path, out_path, mode_name, cols, rows, fps, pal_size, ramp_name,
                 char_aspect, compress, palette_mode, keyint, with_audio, threshold=0,
                 dump_cells=None, bake_smoothing="none", reconstruction="nearest",
                 quality_profile="custom", palette_block_frames=0,
                 dither_mode="off", dither_matrix=4,
                 palette_algorithm="median-cut",
                 adaptive_min_frames=5, adaptive_max_frames=10,
                 adaptive_change_threshold=0.20,
                 adaptive_hard_cut_threshold=0.58,
                 adaptive_stability_max=0.25,
                 perceptual_lut_bits=0,
                 dither_budget=selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                 dither_min_improvement=selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                 dither_window=selective_dither.DEFAULT_TEMPORAL_WINDOW,
                 reserved=0, reserved_colors=None, scene_keyframes=False,
                 protect_panel=False, palette_refit=0, palette_uint8_refine=0):
    validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            palette_block_frames, dither_mode, dither_matrix,
                            palette_algorithm, adaptive_min_frames,
                            adaptive_max_frames, adaptive_change_threshold,
                            adaptive_hard_cut_threshold,
                            adaptive_stability_max, perceptual_lut_bits,
                            dither_budget, dither_min_improvement,
                            dither_window, reserved=reserved,
                            palette_refit=palette_refit,
                            palette_uint8_refine=palette_uint8_refine)
    reserved = int(reserved)
    if reserved:
        reserved_colors = _validate_reserved_colors(reserved, reserved_colors)
    if int(keyint) < 0:
        raise ValueError("keyint debe ser >= 0")
    if int(threshold) < 0:
        raise ValueError("threshold debe ser >= 0")
    if dither_mode in ("selective", "auto") and palette_mode == "per-frame":
        raise ValueError("dither %s en video requiere palette global o block; "
                         "tambien admite adaptive" %
                         dither_mode)
    adaptive_config = adaptive_palette.AdaptivePaletteConfig(
        min_frames=adaptive_min_frames, max_frames=adaptive_max_frames,
        change_threshold=adaptive_change_threshold,
        hard_cut_threshold=adaptive_hard_cut_threshold,
        max_stability=adaptive_stability_max)
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    sw, sh = probe_size(in_path)
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    # F7 / INT-001 §11: con overlay, los rects del panel quedan fuera del
    # dither (mecanismo protected de E-05). La geometria es la misma que la
    # del sidecar, por construccion (overlay_panel).
    panel_protected = (overlay_panel.panel_rects(cols, rows)
                       if protect_panel else None)
    has_palette = mode in (MODE_PIXEL, MODE_ASCII_PAL)
    use_global = has_palette and palette_mode == "global"
    use_block = has_palette and palette_mode == "block"
    use_adaptive = has_palette and palette_mode == "adaptive"
    use_scene_palette = use_block or use_adaptive
    effective_block_frames = (int(palette_block_frames) if int(palette_block_frames) > 0
                              else max(1, int(fps) * 2)) if use_block else 0
    pal_img = None
    palette0 = None
    global_quantizer = None
    if use_global:
        # E-14: el video completo ya no se materializa en RAM (antes:
        # allf = list(...)); la paleta global se resuelve en pasadas de
        # streaming y el encode relee el stream al final.
        if palette_algorithm == "kmeans-oklab":
            # Pasada 1: agregado de color de TODOS los pixeles del video,
            # sin el limite de 65.536 muestras de _weighted_samples.
            aggregate = perceptual_palette.StreamingColorAggregate()
            for frame_rgb, _frame_gray in iter_video_frames(
                    in_path, cols, rows, fps, bake_smoothing):
                aggregate.add_frame(frame_rgb)
            if not aggregate.frame_count:
                raise RuntimeError("video sin frames")
            aggregate_colors, aggregate_mass = aggregate.result()
            pal_img, palette0 = global_palette_from_aggregate(
                aggregate_colors, aggregate_mass, pal_size,
                reserved=reserved, reserved_colors=reserved_colors,
                uint8_refine=palette_uint8_refine)
            if int(palette_refit):
                # El refit E-12 consume el mismo agregado (color unico, masa):
                # equivale a refitear contra todos los pixeles del video.
                palette0 = refit_palette(
                    palette0, [aggregate_colors.reshape(-1, 1, 3)],
                    palette_algorithm, palette_refit, reserved=reserved,
                    perceptual_lut_bits=perceptual_lut_bits,
                    sample_weights=aggregate_mass)
                pal_img = _palette_image(
                    palette0[:len(palette0) - reserved] if reserved
                    else palette0)
        else:
            # Los algoritmos Pillow/RGB muestrean 12 frames como siempre: la
            # pasada de conteo + la de muestreo reproducen exactamente la
            # seleccion historica (bytes identicos), sin materializar.
            total_frames = 0
            for _frame in iter_video_frames(in_path, cols, rows, fps,
                                            bake_smoothing):
                total_frames += 1
            if not total_frames:
                raise RuntimeError("video sin frames")
            stepS = max(1, total_frames // 12)
            wanted = frozenset(range(0, total_frames, stepS))
            sample = []
            for index, (frame_rgb, _frame_gray) in enumerate(
                    iter_video_frames(in_path, cols, rows, fps,
                                      bake_smoothing)):
                if index in wanted:
                    sample.append(frame_rgb)
            pal_img, palette0 = make_global_palette(
                sample, pal_size, palette_algorithm, reserved=reserved,
                reserved_colors=reserved_colors,
                uint8_refine=palette_uint8_refine)
            pal_img, palette0 = refit_block_palette(
                pal_img, palette0, sample, palette_algorithm, palette_refit,
                reserved=reserved, perceptual_lut_bits=perceptual_lut_bits)
        # Solo la parte base cuantiza: el video no puede elegir reservadas (INV-3)
        global_quantizer = make_perceptual_quantizer(
            palette0[:len(palette0) - reserved] if reserved else palette0,
            palette_algorithm, perceptual_lut_bits)
        frames_iter = iter_video_frames(in_path, cols, rows, fps,
                                        bake_smoothing)
    elif use_scene_palette:
        source_iter = iter_video_frames(in_path, cols, rows, fps, bake_smoothing)
        frames_iter = iter_scene_palette_frames(
            source_iter, pal_size, palette_mode, effective_block_frames,
            adaptive_config, palette_algorithm=palette_algorithm,
            perceptual_lut_bits=perceptual_lut_bits, reserved=reserved,
            reserved_colors=reserved_colors, palette_refit=palette_refit,
            palette_uint8_refine=palette_uint8_refine)
    else:
        frames_iter = iter_video_frames(in_path, cols, rows, fps, bake_smoothing)
    delta_allowed = (not has_palette) or use_global or use_scene_palette
    flags_extra = (FLAG_PAL_GLOBAL if use_global else
                   (FLAG_PAL_PER_SCENE if use_scene_palette else 0))
    if mode == MODE_PIXEL and threshold > 0 and (use_global or use_scene_palette):
        flags_extra |= FLAG_LOSSY
    if reconstruction == "soft":
        flags_extra |= FLAG_RECON_SOFT
    pal16 = palette0.astype(np.int16) if (use_global and palette0 is not None) else None
    # El dither tampoco puede introducir indices reservados: su LUT de pares se
    # construye solo con la parte base de la paleta.
    dither_lut = (make_dither_pair_lut(
                      palette0[:len(palette0) - reserved] if reserved else palette0,
                      global_quantizer)
                  if dither_mode != "off" and use_global else None)
    dither_state = (selective_dither.TemporalDitherState(window=dither_window)
                    if dither_mode == "auto" else None)
    frames = []
    prev_cells = None
    previous_frame_palette = None
    previous_color_descriptor = None
    idx = 0
    dump = {} if dump_cells else None
    tag_counts = {TAG_RAW: 0, TAG_ZLIB: 0, TAG_DELTA: 0, TAG_DELTA_MASK: 0}
    block_diagnostics = []
    dither_changed_cells = 0
    dither_proxy_before = 0
    dither_proxy_after = 0
    dither_temporal_resets = 0
    scene_cut_keyframes = 0
    for frame_data in frames_iter:
        block_start = False
        active_pal_img = pal_img
        active_palette = palette0
        active_quantizer = global_quantizer
        if use_scene_palette:
            (rgb, gray, active_pal_img, active_palette, active_quantizer,
             block_start, block_diagnostic, _hard_cut_start) = frame_data
            if block_start:
                # Los indices de dos paletas distintas nunca comparten una cadena DELTA.
                prev_cells = None
                pal16 = active_palette.astype(np.int16)
                if dither_mode != "off":
                    dither_lut = make_dither_pair_lut(
                        (active_palette[:len(active_palette) - reserved]
                         if reserved else active_palette),
                        active_quantizer)
                if block_diagnostic is not None:
                    block_diagnostics.append(block_diagnostic)
        else:
            rgb, gray = frame_data

        # La memoria del dithering atraviesa cambios normales de paleta. Solo un
        # corte cromatico fuerte entre frames consecutivos la reinicia.
        # E-10: con keyframes por corte, el descriptor se calcula siempre;
        # sin esto hard_cut es constante False en --palette global y block.
        need_color_descriptor = (dither_state is not None or
                                 scene_keyframes or
                                 (palette_algorithm == "kmeans-oklab" and
                                  has_palette and palette_mode == "per-frame"))
        current_descriptor = (adaptive_palette.describe_frame_color(
            (rgb, gray), adaptive_config) if need_color_descriptor else None)
        transition_score = 1.0 if previous_color_descriptor is None else 0.0
        hard_cut = False
        if current_descriptor is not None and previous_color_descriptor is not None:
            transition = adaptive_palette.color_change_metrics(
                previous_color_descriptor, current_descriptor, adaptive_config)
            transition_score = float(transition["score"])
            hard_cut = transition_score >= adaptive_config.hard_cut_threshold
            if hard_cut and dither_state is not None:
                dither_state.reset()
                dither_temporal_resets += 1

        scene_cut_keyframe = bool(scene_keyframes and hard_cut and idx > 0)
        keyframe = ((idx == 0) or block_start or scene_cut_keyframe or
                    (keyint > 0 and idx % keyint == 0))
        if scene_cut_keyframe and not block_start:
            scene_cut_keyframes += 1
        per_frame_stability = 0.0
        if (palette_algorithm == "kmeans-oklab" and has_palette and
                palette_mode == "per-frame" and previous_frame_palette is not None):
            per_frame_stability = adaptive_palette.temporal_stability_strength(
                transition_score, hard_cut=hard_cut, config=adaptive_config)
        cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                                   ("global" if use_scene_palette
                                                    else palette_mode),
                                                   active_pal_img, palette_algorithm,
                                                   quantizer=active_quantizer,
                                                   perceptual_lut_bits=perceptual_lut_bits,
                                                   previous_palette=previous_frame_palette,
                                                   temporal_strength=per_frame_stability,
                                                   reserved=reserved,
                                                   reserved_colors=reserved_colors,
                                                   palette_refit=palette_refit,
                                                   palette_uint8_refine=palette_uint8_refine)
        if dither_mode != "off":
            # La misma paleta base que construyo el PairLUT: el dither no ve
            # ni propone entradas reservadas (INV-3).
            cells, dither_details = apply_dither_mode(
                rgb, cells,
                (active_palette[:len(active_palette) - reserved]
                 if reserved else active_palette),
                dither_mode, dither_matrix,
                pair_lut=dither_lut, temporal_state=dither_state,
                dither_budget=dither_budget,
                dither_min_improvement=dither_min_improvement,
                dither_window=dither_window,
                protected_rects=panel_protected)
            if dither_details is not None:
                dither_changed_cells += int(dither_details["changed_cells"])
                dither_proxy_before += int(dither_details["baseline_proxy_error"])
                dither_proxy_after += int(dither_details["result_proxy_error"])
        if use_global:
            pal_count = palette0.shape[0] if idx == 0 else 0
            palette = palette0 if idx == 0 else None
        elif use_scene_palette:
            # Todo keyframe debe ser autocontenido: al hacer seek el reader empieza
            # alli y necesita conocer la paleta aunque este a mitad de un bloque.
            pal_count = active_palette.shape[0] if keyframe else 0
            palette = active_palette if keyframe else None
        if (pal16 is not None and mode == MODE_PIXEL and threshold > 0
                and not keyframe and prev_cells is not None):
            cur = cells[:, 0]
            d = pal16[cur].astype(np.int32) - pal16[prev_cells[:, 0]].astype(np.int32)
            keep = np.einsum("ij,ij->i", d, d) <= threshold * threshold
            emitted = cells.copy()
            emitted[keep, 0] = prev_cells[keep, 0]
            cells = emitted
        tag, payload = encode_frame(cells, prev_cells, mode, idx, keyframe,
                                    compress, delta_allowed)
        if use_scene_palette and tag in (TAG_RAW, TAG_ZLIB) and pal_count == 0:
            # El codec adaptativo puede elegir un full aunque no fuera forzado. Para
            # el reader ese tag tambien es keyframe y debe traer su paleta activa.
            pal_count = active_palette.shape[0]
            palette = active_palette
        tag_counts[tag] += 1
        frames.append({"tag": tag, "pal_count": pal_count, "palette": palette, "payload": payload})
        if dump is not None:
            dump["frame_%04d" % idx] = cells
        prev_cells = cells
        if palette_mode == "per-frame" and palette is not None:
            previous_frame_palette = palette
        if current_descriptor is not None:
            previous_color_descriptor = current_descriptor
        idx += 1
    if idx == 0:
        raise RuntimeError("video sin frames")
    if dump is not None:
        np.savez(dump_cells, **dump)
    total = write_ascl(out_path, mode, cols, rows, fps, ramp, frames, palette0,
                       char_aspect, flags_extra)
    audio_ok = False
    mp3_path = None
    if with_audio:
        mp3_path = os.path.splitext(out_path)[0] + ".mp3"
        audio_ok = extract_audio(in_path, mp3_path)
    return {"kind": "video", "mode": mode_name, "cols": cols, "rows": rows,
            "n_frames": len(frames), "bytes_total": total, "src": (sw, sh),
            "fps": fps, "tags": tag_counts, "palette_mode": palette_mode,
            "audio": (mp3_path if audio_ok else None), "pal_size": pal_size,
            "quality_profile": quality_profile, "bake_smoothing": bake_smoothing,
            "reconstruction": reconstruction,
            "palette_algorithm": palette_algorithm,
            "palette_refit": int(palette_refit),
            "palette_uint8_refine": int(palette_uint8_refine),
            "perceptual_lut_bits": int(perceptual_lut_bits),
            "dither": dither_mode, "dither_matrix": int(dither_matrix),
            "dither_budget": float(dither_budget),
            "dither_min_improvement": float(dither_min_improvement),
            "dither_window": int(dither_window),
            "dither_changed_cells": int(dither_changed_cells),
            "dither_temporal_resets": int(dither_temporal_resets),
            "scene_keyframes": bool(scene_keyframes),
            "scene_cut_keyframes": int(scene_cut_keyframes),
            "dither_proxy_improvement": (
                (float(dither_proxy_before - dither_proxy_after) /
                 float(dither_proxy_before)) if dither_proxy_before else 0.0),
            "palette_block_frames": effective_block_frames,
            "palette_blocks": block_diagnostics,
            "palette_block_sizes": [item["size"] for item in block_diagnostics],
            "palette_block_reasons": [item["reason"] for item in block_diagnostics],
            "palette_block_scores": [item["score"] for item in block_diagnostics],
            "adaptive_min_frames": int(adaptive_min_frames),
            "adaptive_max_frames": int(adaptive_max_frames),
            "adaptive_change_threshold": float(adaptive_change_threshold),
            "adaptive_hard_cut_threshold": float(adaptive_hard_cut_threshold),
            "adaptive_stability_max": float(adaptive_stability_max),
            "flags": FLAG_HAS_OFFSET_TABLE | flags_extra}


def main(argv=None):
    p = argparse.ArgumentParser(description="Encoder ASCILINE -> .ascl (imagen y video).")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--mode", choices=list(MODE_NAMES), default="pixel")
    p.add_argument("--profile", "--quality-profile", choices=QUALITY_PROFILE_NAMES,
                   default="custom", dest="quality_profile",
                   help="perfil de grilla/color; overrides manuales prevalecen")
    p.add_argument("--cols", type=int, default=None,
                   help="columnas; default 200 o valor del perfil")
    p.add_argument("--rows", type=int, default=0, help="0 = auto con correccion de aspecto")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="fps de playback (default 15)")
    p.add_argument("--palette-size", type=int, default=None, dest="pal_size",
                   help="1..256; default 256 o valor del perfil")
    p.add_argument("--palette", choices=PALETTE_MODES, default="per-frame")
    p.add_argument("--palette-algorithm", choices=PALETTE_ALGORITHMS,
                   default="median-cut",
                   help="constructor offline; no cambia formato ni costo de playback")
    p.add_argument("--palette-block-frames", type=int, default=0,
                   help="frames por paleta en modo block (0 = fps*2)")
    p.add_argument("--adaptive-min-frames", type=int, default=5,
                   help="minimo antes de cortar por deriva de color")
    p.add_argument("--adaptive-max-frames", type=int, default=10,
                   help="maximo absoluto de frames por paleta adaptativa")
    p.add_argument("--adaptive-change-threshold", type=float, default=0.20,
                   help="umbral numerico Oklab para deriva gradual")
    p.add_argument("--adaptive-hard-cut-threshold", type=float, default=0.58,
                   help="umbral entre frames para corte cromatico exacto")
    p.add_argument("--adaptive-stability-max", "--temporal-stability-max",
                   type=float, default=0.25, dest="adaptive_stability_max",
                   help="retencion maxima de paleta previa (0..1)")
    p.add_argument("--perceptual-lut-bits", type=int, default=0,
                   help="0=cuantizacion Oklab exacta; 3..7=LUT offline")
    p.add_argument("--palette-refit", type=int, default=0,
                   help="E-12: iteraciones de refit de paleta a la asignacion "
                        "real (0=off, 3..5 tipico, max 10)")
    p.add_argument("--palette-uint8-refine", type=int, default=0,
                   help="E-13: iteraciones del cierre de Lloyd en dominio "
                        "uint8, solo kmeans-oklab (0=off, 2..5 tipico, max 10)")
    p.add_argument("--ramp", default="short", help="'short', 'long' o cadena propia")
    p.add_argument("--char-aspect", type=float, default=DEFAULT_CHAR_ASPECT)
    p.add_argument("--compress", choices=["auto", "none", "zlib"], default="auto")
    p.add_argument("--keyint", type=int, default=0, help="keyframe cada N frames (0 = fps*2)")
    p.add_argument("--scene-keyframes", action="store_true",
                   help="E-10: keyframe en cada corte de escena detectado; "
                        "permite --keyint largos sin cadenas DELTA que crucen cortes")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--force-video", action="store_true")
    p.add_argument("--force-image", action="store_true")
    p.add_argument("--dump-cells", default=None)
    p.add_argument("--bake-smoothing", choices=BAKE_SMOOTHING_MODES, default="none",
                   help="suavizado horneado antes de cuantizar (costo solo offline)")
    p.add_argument("--reconstruction", choices=RECONSTRUCTION_MODES, default="nearest",
                   help="filtro de presentacion sugerido al player")
    p.add_argument("--dither", choices=DITHER_MODES, default="off",
                   help="tramado selectivo offline para mode pixel")
    p.add_argument("--dither-matrix", choices=DITHER_MATRIX_SIZES, type=int, default=4,
                   help="Bayer 2 compacto o Bayer 4 equilibrado")
    p.add_argument("--dither-budget", "--dither-max-changed-fraction", type=float,
                   default=selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                   dest="dither_budget",
                   help="fraccion maxima de celdas modificadas por frame")
    p.add_argument("--dither-min-improvement", type=float,
                   default=selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                   help="mejora minima del proxy para aceptar un tile")
    p.add_argument("--dither-window", "--dither-temporal-window", type=int,
                   default=selective_dither.DEFAULT_TEMPORAL_WINDOW,
                   dest="dither_window", help="ventana temporal de histeresis")
    args = p.parse_args(argv)
    args.cols, args.pal_size = resolve_quality_options(
        args.quality_profile, args.cols, args.pal_size, default_cols=200)
    try:
        validate_encode_options(args.mode, args.cols, args.rows, args.fps, args.pal_size,
                                args.char_aspect, args.palette, args.bake_smoothing,
                                args.reconstruction, args.palette_block_frames,
                                args.dither, args.dither_matrix,
                                args.palette_algorithm,
                                adaptive_min_frames=args.adaptive_min_frames,
                                adaptive_max_frames=args.adaptive_max_frames,
                                adaptive_change_threshold=args.adaptive_change_threshold,
                                adaptive_hard_cut_threshold=args.adaptive_hard_cut_threshold,
                                adaptive_stability_max=args.adaptive_stability_max,
                                perceptual_lut_bits=args.perceptual_lut_bits,
                                dither_budget=args.dither_budget,
                                dither_min_improvement=args.dither_min_improvement,
                                dither_window=args.dither_window,
                                palette_refit=args.palette_refit,
                                palette_uint8_refine=args.palette_uint8_refine)
    except ValueError as exc:
        p.error(str(exc))
    ext = os.path.splitext(args.input)[1].lower()
    is_video = args.force_video or (ext in VIDEO_EXTS and not args.force_image)
    keyint = args.keyint if args.keyint > 0 else max(1, args.fps * 2)
    if is_video:
        info = encode_video(args.input, args.output, args.mode, args.cols, args.rows,
                            args.fps, args.pal_size, args.ramp, args.char_aspect,
                            args.compress, args.palette, keyint, not args.no_audio,
                            dump_cells=args.dump_cells,
                            bake_smoothing=args.bake_smoothing,
                            reconstruction=args.reconstruction,
                            quality_profile=args.quality_profile,
                            palette_block_frames=args.palette_block_frames,
                            dither_mode=args.dither,
                            dither_matrix=args.dither_matrix,
                            palette_algorithm=args.palette_algorithm,
                            adaptive_min_frames=args.adaptive_min_frames,
                            adaptive_max_frames=args.adaptive_max_frames,
                            adaptive_change_threshold=args.adaptive_change_threshold,
                            adaptive_hard_cut_threshold=args.adaptive_hard_cut_threshold,
                            adaptive_stability_max=args.adaptive_stability_max,
                            perceptual_lut_bits=args.perceptual_lut_bits,
                            dither_budget=args.dither_budget,
                            dither_min_improvement=args.dither_min_improvement,
                            dither_window=args.dither_window,
                            scene_keyframes=args.scene_keyframes,
                            palette_refit=args.palette_refit,
                            palette_uint8_refine=args.palette_uint8_refine)
        secs = info["n_frames"] / float(info["fps"]) or 1
        print("OK %s  (video, %s, paleta %s)" % (args.output, info["mode"], info["palette_mode"]))
        print("  fuente   : %dx%d px" % info["src"])
        print("  grilla   : %dx%d celdas @ %d fps" % (info["cols"], info["rows"], info["fps"]))
        print("  calidad  : perfil %s, hasta %d colores" %
              (info["quality_profile"], info["pal_size"]))
        print("  algoritmo: %s" % info["palette_algorithm"])
        if info["palette_mode"] == "block":
            print("  paleta   : bloque de %d frames" % info["palette_block_frames"])
        elif info["palette_mode"] == "adaptive":
            print("  paleta   : %d bloques adaptativos; tamanos %s" %
                  (len(info["palette_blocks"]), info["palette_block_sizes"]))
            for block in info["palette_blocks"]:
                print("    #%d [%d,%d) n=%d fin=%s score=%.3f entrada=%s estable=%.3f" %
                      (block["index"], block["start"], block["end"], block["size"],
                       block["reason"], block["score"], block["entry_reason"],
                       block["stability"]))
        print("  imagen   : bake %s, reconstruccion %s, flags 0x%02X" %
              (info["bake_smoothing"], info["reconstruction"], info["flags"]))
        print("  dither   : %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
        if info["dither"] == "auto":
            print("             presupuesto %.3f, mejora min %.3f, ventana %d; "
                  "%d celdas cambiadas" %
                  (info["dither_budget"], info["dither_min_improvement"],
                   info["dither_window"], info["dither_changed_cells"]))
        print("  frames   : %d   tags RAW/ZLIB/DELTA = %d/%d/%d" %
              (info["n_frames"], info["tags"][0], info["tags"][1], info["tags"][2]))
        print("  .ascl    : %d B  (%.1f KB, %.1f KB/s)" %
              (info["bytes_total"], info["bytes_total"] / 1024.0,
               info["bytes_total"] / 1024.0 / secs))
        print("  audio    : %s" % (info["audio"] or "(sin audio)"))
    else:
        info = encode_image(args.input, args.output, args.mode, args.cols, args.rows,
                            args.fps, args.pal_size, args.ramp, args.char_aspect,
                            args.compress, args.palette, dump_cells=args.dump_cells,
                            bake_smoothing=args.bake_smoothing,
                            reconstruction=args.reconstruction,
                            quality_profile=args.quality_profile,
                            dither_mode=args.dither,
                            dither_matrix=args.dither_matrix,
                            palette_algorithm=args.palette_algorithm,
                            perceptual_lut_bits=args.perceptual_lut_bits,
                            dither_budget=args.dither_budget,
                            dither_min_improvement=args.dither_min_improvement,
                            dither_window=args.dither_window,
                            palette_refit=args.palette_refit,
                            palette_uint8_refine=args.palette_uint8_refine)
        print("OK %s  (imagen, %s)" % (args.output, info["mode"]))
        print("  grilla   : %dx%d celdas" % (info["cols"], info["rows"]))
        print("  calidad  : perfil %s, hasta %d colores" %
              (info["quality_profile"], info["pal_size"]))
        print("  algoritmo: %s" % info["palette_algorithm"])
        print("  imagen   : bake %s, reconstruccion %s, flags 0x%02X" %
              (info["bake_smoothing"], info["reconstruction"], info["flags"]))
        print("  dither   : %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
        print("  .ascl    : %d B" % info["bytes_total"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
