#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encoder.py - Encoder offline ASCILINE -> contenedor .ascl (imagen Y video).

Fork conceptual de YusufB5/ASCILINE: reusa la rampa por luminancia, la correccion
de aspecto del glifo y la estrategia del codec adaptativo (probar por frame
RAW / ZLIB / DELTA y quedarse con el mas chico). El char plane siempre es exacto.

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
    "color":    {"cols": 320, "pal_size": 256},
}
QUALITY_PROFILE_NAMES = ("custom", "detail", "balanced", "graphic", "color")
BAKE_SMOOTHING_MODES = ("none", "soft")
RECONSTRUCTION_MODES = ("nearest", "soft")
PALETTE_ALGORITHMS = ("median-cut", "fast-octree", "kmeans-rgb")
DITHER_MODES = selective_dither.DITHER_MODES
DITHER_MATRIX_SIZES = selective_dither.DITHER_MATRIX_SIZES
# Reconstruccion offline 2x: una base de media resolucion se expande a la grilla
# almacenada. Los pixeles intermedios quedan dentro del archivo, no se calculan al reproducir.
SOFT_BAKE_SCALE = 0.5


def resolve_quality_options(profile, cols, pal_size, default_cols, default_pal_size=256):
    """Completa cols/pal_size respetando siempre los overrides manuales."""
    profile = profile or "custom"
    if profile not in QUALITY_PROFILE_NAMES:
        raise ValueError("profile debe ser custom/detail/balanced/color")
    preset = QUALITY_PROFILES.get(profile, {})
    if cols is None:
        cols = preset.get("cols", default_cols)
    if pal_size is None:
        pal_size = preset.get("pal_size", default_pal_size)
    return int(cols), int(pal_size)


def validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            palette_block_frames=0, dither_mode="off",
                            dither_matrix=4, palette_algorithm="median-cut"):
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
    if palette_mode not in ("per-frame", "global", "block"):
        raise ValueError("palette debe ser per-frame, global o block")
    if int(palette_block_frames) < 0:
        raise ValueError("palette-block-frames debe ser >= 0")
    if bake_smoothing not in BAKE_SMOOTHING_MODES:
        raise ValueError("bake-smoothing debe ser none o soft")
    if reconstruction not in RECONSTRUCTION_MODES:
        raise ValueError("reconstruction debe ser nearest o soft")
    if dither_mode not in DITHER_MODES:
        raise ValueError("dither debe ser off o selective")
    if int(dither_matrix) not in DITHER_MATRIX_SIZES:
        raise ValueError("dither-matrix debe ser 2 o 4")
    if dither_mode != "off" and mode_name != "pixel":
        raise ValueError("dither selective solo esta disponible en mode pixel")
    if palette_algorithm not in PALETTE_ALGORITHMS:
        raise ValueError("palette-algorithm debe ser median-cut, fast-octree o kmeans-rgb")


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


def _kmeans_rgb_palette(sample_imgs, pal_size, max_samples=65536, seed=20260811):
    """Paleta RGB k-means determinista; todo el costo queda en el encoder offline."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("kmeans-rgb requiere opencv-python-headless en el backend") from exc
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
    cv2.setRNGSeed(int(seed))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.25)
    _compactness, _labels, centers = cv2.kmeans(
        samples, int(pal_size), None, criteria, 1, cv2.KMEANS_PP_CENTERS)
    return np.clip(np.rint(centers), 0, 255).astype(np.uint8)


def make_global_palette(sample_imgs, pal_size, palette_algorithm="median-cut"):
    if not sample_imgs:
        raise ValueError("sample_imgs no puede estar vacio")
    h = sum(im.shape[0] for im in sample_imgs)
    w = sample_imgs[0].shape[1]
    stack = np.zeros((h, w, 3), np.uint8)
    y = 0
    for im in sample_imgs:
        stack[y:y + im.shape[0]] = im
        y += im.shape[0]
    if palette_algorithm == "kmeans-rgb":
        palette = _kmeans_rgb_palette(sample_imgs, pal_size)
        pal_img = _palette_image(palette)
        return pal_img, palette
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
                              palette_algorithm="median-cut"):
    """Anota cada frame con la paleta temporal de su bloque.

    Solo conserva `block_frames` RGB/grises y el pequeno conjunto usado para crear
    la paleta. El booleano final marca el primer frame, donde DELTA debe reiniciarse.
    """
    for block in iter_frame_blocks(frames_iter, block_frames):
        samples = sample_palette_frames(block, max_samples)
        pal_img, palette = make_global_palette(samples, pal_size, palette_algorithm)
        for block_index, (rgb, gray) in enumerate(block):
            yield rgb, gray, pal_img, palette, block_index == 0


def quantize_with(pal_img, rgb):
    im = Image.fromarray(rgb, "RGB").quantize(palette=pal_img, dither=Image.NONE)
    return np.asarray(im, dtype=np.uint8)


def quantize_per_frame(rgb, pal_size, palette_algorithm="median-cut"):
    h, w, _ = rgb.shape
    if palette_algorithm != "median-cut":
        pal_img, palette = make_global_palette([rgb], pal_size, palette_algorithm)
        idx = quantize_with(pal_img, rgb).reshape(h, w)
        return idx, palette
    im = Image.fromarray(rgb, "RGB").quantize(colors=pal_size, method=Image.MEDIANCUT,
                                              dither=Image.NONE)
    idx = np.asarray(im, dtype=np.uint8).reshape(h, w)
    pal_count = max(int(idx.max()) + 1, 1)
    palette = np.array(im.getpalette()[: pal_count * 3], dtype=np.uint8).reshape(-1, 3)
    return idx, palette


def gray_to_char_idx(gray, ramp_len):
    idx = (gray.astype(np.uint16) * ramp_len) // 256
    return np.clip(idx, 0, ramp_len - 1).astype(np.uint8)


def frame_to_cells(rgb, gray, mode, ramp_len, pal_size, palette_mode, pal_img,
                   palette_algorithm="median-cut"):
    h, w = gray.shape
    N = h * w
    if mode == MODE_PIXEL:
        if palette_mode == "global":
            idx = quantize_with(pal_img, rgb)
            return idx.reshape(N, 1), None, 0
        idx, pal = quantize_per_frame(rgb, pal_size, palette_algorithm)
        return idx.reshape(N, 1), pal, pal.shape[0]
    char_idx = gray_to_char_idx(gray, ramp_len).reshape(N, 1)
    if mode == MODE_ASCII_BW:
        return char_idx, None, 0
    if mode == MODE_ASCII_PAL:
        if palette_mode == "global":
            color = quantize_with(pal_img, rgb).reshape(N, 1)
            return np.concatenate([char_idx, color], axis=1), None, 0
        color, pal = quantize_per_frame(rgb, pal_size, palette_algorithm)
        return np.concatenate([char_idx, color.reshape(N, 1)], axis=1), pal, pal.shape[0]
    if mode == MODE_ASCII_RGB:
        return np.concatenate([char_idx, rgb.reshape(N, 3)], axis=1), None, 0
    raise ValueError("modo desconocido")


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
    full_z = zlib.compress(planes, 9)
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
            delta_z = zlib.compress(ci.tobytes() + vals.tobytes(), 9)
            candidates.append((TAG_DELTA, delta_z))
            mask = np.packbits(changed.astype(np.uint8), bitorder="little")
            mask_z = zlib.compress(mask.tobytes() + vals.tobytes(), 9)
            candidates.append((TAG_DELTA_MASK, mask_z))
    tag, payload = min(candidates, key=lambda c: len(c[1]))
    if len(planes) < len(payload):
        tag, payload = TAG_RAW, planes
    return tag, payload


def write_ascl(path, mode, cols, rows, fps, ramp, frames, palette0, char_aspect, flags_extra):
    ramp_bytes = ramp.encode("ascii") if ramp else b""
    ramp_len   = len(ramp_bytes)
    pal_size   = palette0.shape[0] if palette0 is not None else 0
    if pal_size == 0:
        for fr in frames:
            if fr["pal_count"]:
                pal_size = max(pal_size, fr["pal_count"])
    n_frames = len(frames)
    flags    = FLAG_HAS_OFFSET_TABLE | flags_extra
    blocks = []
    for fr in frames:
        body = struct.pack("<BH", fr["tag"], fr["pal_count"])
        if fr["pal_count"] > 0:
            body += fr["palette"].astype(np.uint8).tobytes()
        body += fr["payload"]
        blocks.append(struct.pack("<I", len(body)) + body)
    data_off = HEADER_SIZE + ramp_len
    off = data_off + n_frames * 4
    offs = []
    for b in blocks:
        offs.append(off)
        off += len(b)
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
                 palette_algorithm="median-cut"):
    validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            dither_mode=dither_mode, dither_matrix=dither_matrix,
                            palette_algorithm=palette_algorithm)
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    src = Image.open(in_path).convert("RGB")
    sw, sh = src.size
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    small = resize_pil_for_grid(src, cols, rows, bake_smoothing)
    rgb = np.ascontiguousarray(np.asarray(small, np.uint8))
    gray = np.asarray(Image.fromarray(rgb, "RGB").convert("L"), np.uint8)
    cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                               "per-frame", None, palette_algorithm)
    if dither_mode == "selective":
        baseline = cells[:, 0].reshape(rows, cols)
        dithered = selective_dither.apply_selective_dither(
            rgb, baseline, palette, matrix_size=dither_matrix)
        cells = dithered.reshape(-1, 1)
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
            "dither": dither_mode, "dither_matrix": int(dither_matrix),
            "flags": FLAG_HAS_OFFSET_TABLE | flags_extra}


def encode_video(in_path, out_path, mode_name, cols, rows, fps, pal_size, ramp_name,
                 char_aspect, compress, palette_mode, keyint, with_audio, threshold=0,
                 dump_cells=None, bake_smoothing="none", reconstruction="nearest",
                 quality_profile="custom", palette_block_frames=0,
                 dither_mode="off", dither_matrix=4,
                 palette_algorithm="median-cut"):
    validate_encode_options(mode_name, cols, rows, fps, pal_size, char_aspect,
                            palette_mode, bake_smoothing, reconstruction,
                            palette_block_frames, dither_mode, dither_matrix,
                            palette_algorithm)
    if int(keyint) < 0:
        raise ValueError("keyint debe ser >= 0")
    if int(threshold) < 0:
        raise ValueError("threshold debe ser >= 0")
    if dither_mode == "selective" and palette_mode == "per-frame":
        raise ValueError("dither selective en video requiere palette global o block")
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    sw, sh = probe_size(in_path)
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    has_palette = mode in (MODE_PIXEL, MODE_ASCII_PAL)
    use_global = has_palette and palette_mode == "global"
    use_block = has_palette and palette_mode == "block"
    effective_block_frames = (int(palette_block_frames) if int(palette_block_frames) > 0
                              else max(1, int(fps) * 2)) if use_block else 0
    pal_img = None
    palette0 = None
    if use_global:
        allf = list(iter_video_frames(in_path, cols, rows, fps, bake_smoothing))
        if not allf:
            raise RuntimeError("video sin frames")
        stepS = max(1, len(allf) // 12)
        sample = [allf[k][0] for k in range(0, len(allf), stepS)]
        pal_img, palette0 = make_global_palette(sample, pal_size, palette_algorithm)
        frames_iter = allf
    elif use_block:
        source_iter = iter_video_frames(in_path, cols, rows, fps, bake_smoothing)
        frames_iter = iter_block_palette_frames(source_iter, pal_size,
                                                effective_block_frames,
                                                palette_algorithm=palette_algorithm)
    else:
        frames_iter = iter_video_frames(in_path, cols, rows, fps, bake_smoothing)
    delta_allowed = (not has_palette) or use_global or use_block
    flags_extra = (FLAG_PAL_GLOBAL if use_global else
                   (FLAG_PAL_PER_SCENE if use_block else 0))
    if mode == MODE_PIXEL and threshold > 0 and (use_global or use_block):
        flags_extra |= FLAG_LOSSY
    if reconstruction == "soft":
        flags_extra |= FLAG_RECON_SOFT
    pal16 = palette0.astype(np.int16) if (use_global and palette0 is not None) else None
    dither_lut = (selective_dither.PairLUT(palette0)
                  if dither_mode == "selective" and use_global else None)
    frames = []
    prev_cells = None
    idx = 0
    dump = {} if dump_cells else None
    tag_counts = {TAG_RAW: 0, TAG_ZLIB: 0, TAG_DELTA: 0, TAG_DELTA_MASK: 0}
    for frame_data in frames_iter:
        block_start = False
        active_pal_img = pal_img
        active_palette = palette0
        if use_block:
            rgb, gray, active_pal_img, active_palette, block_start = frame_data
            if block_start:
                # Los indices de dos paletas distintas nunca comparten una cadena DELTA.
                prev_cells = None
                pal16 = active_palette.astype(np.int16)
                if dither_mode == "selective":
                    dither_lut = selective_dither.PairLUT(active_palette)
        else:
            rgb, gray = frame_data
        keyframe = (idx == 0) or block_start or (keyint > 0 and idx % keyint == 0)
        cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                                   ("global" if use_block else palette_mode),
                                                   active_pal_img, palette_algorithm)
        if dither_mode == "selective":
            baseline = cells[:, 0].reshape(rows, cols)
            dithered = selective_dither.apply_selective_dither(
                rgb, baseline, active_palette, matrix_size=dither_matrix,
                pair_lut=dither_lut)
            cells = dithered.reshape(-1, 1)
        if use_global:
            pal_count = pal_size if idx == 0 else 0
            palette = palette0 if idx == 0 else None
        elif use_block:
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
        if use_block and tag in (TAG_RAW, TAG_ZLIB) and pal_count == 0:
            # El codec adaptativo puede elegir un full aunque no fuera forzado. Para
            # el reader ese tag tambien es keyframe y debe traer su paleta activa.
            pal_count = active_palette.shape[0]
            palette = active_palette
        tag_counts[tag] += 1
        frames.append({"tag": tag, "pal_count": pal_count, "palette": palette, "payload": payload})
        if dump is not None:
            dump["frame_%04d" % idx] = cells
        prev_cells = cells
        idx += 1
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
            "dither": dither_mode, "dither_matrix": int(dither_matrix),
            "palette_block_frames": effective_block_frames,
            "flags": FLAG_HAS_OFFSET_TABLE | flags_extra}


def main(argv=None):
    p = argparse.ArgumentParser(description="Encoder ASCILINE -> .ascl (imagen y video).")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--mode", choices=list(MODE_NAMES), default="pixel")
    p.add_argument("--profile", "--quality-profile", choices=QUALITY_PROFILE_NAMES,
                   default="custom", dest="quality_profile",
                   help="custom/detail/balanced/graphic/color; overrides prevalecen")
    p.add_argument("--cols", type=int, default=None,
                   help="columnas; default 200 o valor del perfil")
    p.add_argument("--rows", type=int, default=0, help="0 = auto con correccion de aspecto")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="fps de playback (default 15)")
    p.add_argument("--palette-size", type=int, default=None, dest="pal_size",
                   help="1..256; default 256 o valor del perfil")
    p.add_argument("--palette", choices=["per-frame", "global", "block"], default="per-frame")
    p.add_argument("--palette-algorithm", choices=PALETTE_ALGORITHMS,
                   default="median-cut",
                   help="constructor offline; no cambia formato ni costo de playback")
    p.add_argument("--palette-block-frames", type=int, default=0,
                   help="frames por paleta en modo block (0 = fps*2)")
    p.add_argument("--ramp", default="short", help="'short', 'long' o cadena propia")
    p.add_argument("--char-aspect", type=float, default=DEFAULT_CHAR_ASPECT)
    p.add_argument("--compress", choices=["auto", "none", "zlib"], default="auto")
    p.add_argument("--keyint", type=int, default=0, help="keyframe cada N frames (0 = fps*2)")
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
    args = p.parse_args(argv)
    args.cols, args.pal_size = resolve_quality_options(
        args.quality_profile, args.cols, args.pal_size, default_cols=200)
    try:
        validate_encode_options(args.mode, args.cols, args.rows, args.fps, args.pal_size,
                                args.char_aspect, args.palette, args.bake_smoothing,
                                args.reconstruction, args.palette_block_frames,
                                args.dither, args.dither_matrix,
                                args.palette_algorithm)
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
                            palette_algorithm=args.palette_algorithm)
        secs = info["n_frames"] / float(info["fps"]) or 1
        print("OK %s  (video, %s, paleta %s)" % (args.output, info["mode"], info["palette_mode"]))
        print("  fuente   : %dx%d px" % info["src"])
        print("  grilla   : %dx%d celdas @ %d fps" % (info["cols"], info["rows"], info["fps"]))
        print("  calidad  : perfil %s, hasta %d colores" %
              (info["quality_profile"], info["pal_size"]))
        print("  algoritmo: %s" % info["palette_algorithm"])
        if info["palette_mode"] == "block":
            print("  paleta   : bloque de %d frames" % info["palette_block_frames"])
        print("  imagen   : bake %s, reconstruccion %s, flags 0x%02X" %
              (info["bake_smoothing"], info["reconstruction"], info["flags"]))
        print("  dither   : %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
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
                            palette_algorithm=args.palette_algorithm)
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
