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

MAGIC          = b"ASCL"
VERSION        = 1
MODE_ASCII_BW, MODE_ASCII_PAL, MODE_ASCII_RGB, MODE_PIXEL = 0, 1, 2, 3
TAG_RAW, TAG_ZLIB, TAG_DELTA = 0, 1, 2
TAG_DELTA_MASK = 3
FLAG_LOSSY, FLAG_PAL_PER_SCENE, FLAG_PAL_GLOBAL, FLAG_HAS_OFFSET_TABLE = 1, 2, 4, 8

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


def compute_grid(src_w, src_h, cols, rows, mode, char_aspect):
    if cols <= 0:
        raise ValueError("cols debe ser > 0")
    factor = 1.0 if mode == MODE_PIXEL else char_aspect
    out_rows = rows if (rows and rows > 0) else max(1, int(round(cols * (src_h / src_w) * factor)))
    return int(cols), int(out_rows)


def make_global_palette(sample_imgs, pal_size):
    h = sum(im.shape[0] for im in sample_imgs)
    w = sample_imgs[0].shape[1]
    stack = np.zeros((h, w, 3), np.uint8)
    y = 0
    for im in sample_imgs:
        stack[y:y + im.shape[0]] = im
        y += im.shape[0]
    pal_img = Image.fromarray(stack, "RGB").quantize(colors=pal_size,
                                                     method=Image.MEDIANCUT, dither=Image.NONE)
    palette = np.array(pal_img.getpalette()[: pal_size * 3], dtype=np.uint8).reshape(-1, 3)
    return pal_img, palette


def quantize_with(pal_img, rgb):
    im = Image.fromarray(rgb, "RGB").quantize(palette=pal_img, dither=Image.NONE)
    return np.asarray(im, dtype=np.uint8)


def quantize_per_frame(rgb, pal_size):
    h, w, _ = rgb.shape
    im = Image.fromarray(rgb, "RGB").quantize(colors=pal_size, method=Image.MEDIANCUT,
                                              dither=Image.NONE)
    idx = np.asarray(im, dtype=np.uint8).reshape(h, w)
    pal_count = max(int(idx.max()) + 1, 1)
    palette = np.array(im.getpalette()[: pal_count * 3], dtype=np.uint8).reshape(-1, 3)
    return idx, palette


def gray_to_char_idx(gray, ramp_len):
    idx = (gray.astype(np.uint16) * ramp_len) // 256
    return np.clip(idx, 0, ramp_len - 1).astype(np.uint8)


def frame_to_cells(rgb, gray, mode, ramp_len, pal_size, palette_mode, pal_img):
    h, w = gray.shape
    N = h * w
    if mode == MODE_PIXEL:
        if palette_mode == "global":
            idx = quantize_with(pal_img, rgb)
            return idx.reshape(N, 1), None, 0
        idx, pal = quantize_per_frame(rgb, pal_size)
        return idx.reshape(N, 1), pal, pal.shape[0]
    char_idx = gray_to_char_idx(gray, ramp_len).reshape(N, 1)
    if mode == MODE_ASCII_BW:
        return char_idx, None, 0
    if mode == MODE_ASCII_PAL:
        if palette_mode == "global":
            color = quantize_with(pal_img, rgb).reshape(N, 1)
            return np.concatenate([char_idx, color], axis=1), None, 0
        color, pal = quantize_per_frame(rgb, pal_size)
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
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-vn", "-acodec", "libmp3lame",
             "-q:a", "4", mp3_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0 and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
    except Exception:
        return False


def iter_video_frames(in_path, cols, rows, target_fps):
    import cv2
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise RuntimeError("no se pudo abrir el video: %s" % in_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
    step = max(1, int(round(src_fps / float(target_fps))))
    i = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if i % step != 0:
            continue
        small = cv2.resize(frame, (cols, rows), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        yield np.ascontiguousarray(rgb), np.ascontiguousarray(gray)
    cap.release()


def probe_size(in_path):
    import cv2
    cap = cv2.VideoCapture(in_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return w, h


def encode_image(in_path, out_path, mode_name, cols, rows, fps, pal_size,
                 ramp_name, char_aspect, compress, palette_mode, dump_cells=None):
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    src = Image.open(in_path).convert("RGB")
    sw, sh = src.size
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    small = src.resize((cols, rows), Image.LANCZOS)
    rgb = np.asarray(small, np.uint8)
    gray = np.asarray(small.convert("L"), np.uint8)
    cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                               "per-frame", None)
    tag, payload = encode_frame(cells, None, mode, 0, True, compress, False)
    frames = [{"tag": tag, "pal_count": pal_count, "palette": palette, "payload": payload}]
    if dump_cells:
        np.savez(dump_cells, frame_0000=cells)
    total = write_ascl(out_path, mode, cols, rows, fps, ramp, frames, None, char_aspect, 0)
    return {"kind": "image", "mode": mode_name, "cols": cols, "rows": rows,
            "n_frames": 1, "bytes_total": total, "src": (sw, sh)}


def encode_video(in_path, out_path, mode_name, cols, rows, fps, pal_size, ramp_name,
                 char_aspect, compress, palette_mode, keyint, with_audio, threshold=0, dump_cells=None):
    mode = MODE_NAMES[mode_name]
    ramp = "" if mode == MODE_PIXEL else RAMPS.get(ramp_name, ramp_name)
    sw, sh = probe_size(in_path)
    cols, rows = compute_grid(sw, sh, cols, rows, mode, char_aspect)
    has_palette = mode in (MODE_PIXEL, MODE_ASCII_PAL)
    use_global = has_palette and palette_mode == "global"
    pal_img = None
    palette0 = None
    if use_global:
        allf = list(iter_video_frames(in_path, cols, rows, fps))
        if not allf:
            raise RuntimeError("video sin frames")
        stepS = max(1, len(allf) // 12)
        sample = [allf[k][0] for k in range(0, len(allf), stepS)]
        pal_img, palette0 = make_global_palette(sample, pal_size)
        frames_iter = allf
    else:
        frames_iter = iter_video_frames(in_path, cols, rows, fps)
    delta_allowed = (not has_palette) or use_global
    flags_extra = FLAG_PAL_GLOBAL if use_global else 0
    pal16 = palette0.astype(np.int16) if (use_global and palette0 is not None) else None
    frames = []
    prev_cells = None
    idx = 0
    dump = {} if dump_cells else None
    tag_counts = {TAG_RAW: 0, TAG_ZLIB: 0, TAG_DELTA: 0, TAG_DELTA_MASK: 0}
    for rgb, gray in frames_iter:
        keyframe = (idx == 0) or (keyint > 0 and idx % keyint == 0)
        cells, palette, pal_count = frame_to_cells(rgb, gray, mode, len(ramp), pal_size,
                                                   palette_mode, pal_img)
        if use_global:
            pal_count = pal_size if idx == 0 else 0
            palette = palette0 if idx == 0 else None
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
            "audio": (mp3_path if audio_ok else None)}


def main(argv=None):
    p = argparse.ArgumentParser(description="Encoder ASCILINE -> .ascl (imagen y video).")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--mode", choices=list(MODE_NAMES), default="pixel")
    p.add_argument("--cols", type=int, default=200)
    p.add_argument("--rows", type=int, default=0, help="0 = auto con correccion de aspecto")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="fps de playback (default 15)")
    p.add_argument("--palette-size", type=int, default=256, dest="pal_size")
    p.add_argument("--palette", choices=["per-frame", "global"], default="per-frame")
    p.add_argument("--ramp", default="short", help="'short', 'long' o cadena propia")
    p.add_argument("--char-aspect", type=float, default=DEFAULT_CHAR_ASPECT)
    p.add_argument("--compress", choices=["auto", "none", "zlib"], default="auto")
    p.add_argument("--keyint", type=int, default=0, help="keyframe cada N frames (0 = fps*2)")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--force-video", action="store_true")
    p.add_argument("--force-image", action="store_true")
    p.add_argument("--dump-cells", default=None)
    args = p.parse_args(argv)
    if not (1 <= args.pal_size <= 256):
        p.error("--palette-size 1..256")
    ext = os.path.splitext(args.input)[1].lower()
    is_video = args.force_video or (ext in VIDEO_EXTS and not args.force_image)
    keyint = args.keyint if args.keyint > 0 else max(1, args.fps * 2)
    if is_video:
        info = encode_video(args.input, args.output, args.mode, args.cols, args.rows,
                            args.fps, args.pal_size, args.ramp, args.char_aspect,
                            args.compress, args.palette, keyint, not args.no_audio,
                            dump_cells=args.dump_cells)
        secs = info["n_frames"] / float(info["fps"]) or 1
        print("OK %s  (video, %s, paleta %s)" % (args.output, info["mode"], info["palette_mode"]))
        print("  fuente   : %dx%d px" % info["src"])
        print("  grilla   : %dx%d celdas @ %d fps" % (info["cols"], info["rows"], info["fps"]))
        print("  frames   : %d   tags RAW/ZLIB/DELTA = %d/%d/%d" %
              (info["n_frames"], info["tags"][0], info["tags"][1], info["tags"][2]))
        print("  .ascl    : %d B  (%.1f KB, %.1f KB/s)" %
              (info["bytes_total"], info["bytes_total"] / 1024.0,
               info["bytes_total"] / 1024.0 / secs))
        print("  audio    : %s" % (info["audio"] or "(sin audio)"))
    else:
        info = encode_image(args.input, args.output, args.mode, args.cols, args.rows,
                            args.fps, args.pal_size, args.ramp, args.char_aspect,
                            args.compress, args.palette, dump_cells=args.dump_cells)
        print("OK %s  (imagen, %s)" % (args.output, info["mode"]))
        print("  grilla   : %dx%d celdas" % (info["cols"], info["rows"]))
        print("  .ascl    : %d B" % info["bytes_total"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
