#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ascl_decode.py - Decoder / verificador de referencia para .ascl (imagen y video).

Roles:
  1. Parsear header + rampa + tabla de offsets (espejo del reader, spec 10).
  2. Decodificar todos los frames ASCL v1/v2 manteniendo estado previo.
  3. Reconstruir un preview: PNG (imagen) o MP4 (video) del mosaico de color, y
     un PNG con glifos del primer frame en modos ASCII.
  4. VERIFICAR fidelidad pixel-perfect contra el volcado --dump-cells del encoder.

Uso:
  python ascl_decode.py out.ascl
  python ascl_decode.py out.ascl --verify-cells dump.npz
  python ascl_decode.py out.ascl --mp4 preview.mp4 --scale 4
"""

import argparse
import struct
import subprocess
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HEADER_FMT  = "<4sBBBBHHHIBBIHHI"
HEADER_SIZE = 32
MODE_ASCII_BW, MODE_ASCII_PAL, MODE_ASCII_RGB, MODE_PIXEL = 0, 1, 2, 3
TAG_RAW, TAG_ZLIB, TAG_DELTA = 0, 1, 2
TAG_DELTA_MASK = 3
TAG_REGIONAL_KEY_RAW = 4
TAG_REGIONAL_KEY_ZLIB = 5
TAG_REGIONAL_DELTA_RAW = 6
TAG_REGIONAL_DELTA_ZLIB = 7
TAG_PREDICT_KEY_ZLIB = 8
TAG_PREDICT_DELTA_ZLIB = 9
BYTES_PER_CELL = {MODE_PIXEL: 1, MODE_ASCII_BW: 1, MODE_ASCII_PAL: 2, MODE_ASCII_RGB: 4}
MODE_LABEL = {0: "ASCII_BW", 1: "ASCII_PAL", 2: "ASCII_RGB", 3: "PIXEL"}
TAG_LABEL = {
    TAG_RAW: "RAW",
    TAG_ZLIB: "ZLIB",
    TAG_DELTA: "DELTA",
    TAG_DELTA_MASK: "DELTA_MASK",
    TAG_REGIONAL_KEY_RAW: "REGIONAL_KEY_RAW",
    TAG_REGIONAL_KEY_ZLIB: "REGIONAL_KEY_ZLIB",
    TAG_REGIONAL_DELTA_RAW: "REGIONAL_DELTA_RAW",
    TAG_REGIONAL_DELTA_ZLIB: "REGIONAL_DELTA_ZLIB",
    TAG_PREDICT_KEY_ZLIB: "PREDICT_KEY_ZLIB",
    TAG_PREDICT_DELTA_ZLIB: "PREDICT_DELTA_ZLIB",
}


def parse_header(buf):
    if len(buf) < HEADER_SIZE:
        raise ValueError("ASCL truncado")
    f = struct.unpack_from(HEADER_FMT, buf, 0)
    magic, version, mode, flags, fps, cols, rows, pal_size, n_frames = f[:9]
    ramp_len, cell_fmt, data_off, ca, reserved, crc32 = f[9:]
    if magic != b"ASCL":
        raise ValueError("no es .ascl (magic invalido)")
    return dict(version=version, mode=mode, flags=flags, fps=fps, cols=cols, rows=rows,
                pal_size=pal_size, n_frames=n_frames, ramp_len=ramp_len, cell_fmt=cell_fmt,
                data_off=data_off, char_aspect=ca / 1000.0, reserved=reserved,
                tile_size=(reserved & 255 if version == 2 else 0),
                codec_flags=(reserved >> 8 if version == 2 else 0), crc32=crc32)


def compute_crc(buf, header=None):
    """Calcula el CRC con el alcance definido por la version del ASCL.

    v1 protege el cuerpo desde el byte 32. v2 protege tambien los metadatos del
    header (bytes 0..27) y salta solamente el campo que contiene el propio CRC.
    """
    if header is None:
        header = parse_header(buf)
    version = int(header["version"])
    if version == 1:
        return zlib.crc32(buf[HEADER_SIZE:]) & 0xFFFFFFFF
    if version == 2:
        value = zlib.crc32(buf[:28])
        return zlib.crc32(buf[HEADER_SIZE:], value) & 0xFFFFFFFF
    raise ValueError("version ASCL no soportada: %d" % version)


def planes_to_cells(planes, mode, n):
    bpc = BYTES_PER_CELL[mode]
    cells = np.empty((n, bpc), np.uint8)
    if mode in (MODE_PIXEL, MODE_ASCII_BW):
        cells[:, 0] = np.frombuffer(planes, np.uint8, n, 0)
    elif mode == MODE_ASCII_PAL:
        cells[:, 0] = np.frombuffer(planes, np.uint8, n, 0)
        cells[:, 1] = np.frombuffer(planes, np.uint8, n, n)
    elif mode == MODE_ASCII_RGB:
        cells[:, 0] = np.frombuffer(planes, np.uint8, n, 0)
        cells[:, 1:4] = np.frombuffer(planes, np.uint8, n * 3, n).reshape(n, 3)
    return cells


def _decode_all_v1(buf, hdr):
    ramp = buf[HEADER_SIZE: HEADER_SIZE + hdr["ramp_len"]].decode("ascii", "replace")
    offs = list(struct.unpack_from("<%dI" % hdr["n_frames"], buf, hdr["data_off"]))
    mode, cols, rows = hdr["mode"], hdr["cols"], hdr["rows"]
    n = cols * rows
    bpc = BYTES_PER_CELL[mode]
    cells_list, pal_list = [], []
    cur_pal, prev = None, None
    for o in offs:
        block_len = struct.unpack_from("<I", buf, o)[0]
        p = o + 4
        tag = struct.unpack_from("<B", buf, p)[0]; p += 1
        pal_count = struct.unpack_from("<H", buf, p)[0]; p += 2
        if pal_count > 0:
            cur_pal = np.frombuffer(buf, np.uint8, pal_count * 3, p).reshape(-1, 3).copy()
            p += pal_count * 3
        payload = buf[p: o + 4 + block_len]
        if tag == TAG_RAW:
            cells = planes_to_cells(bytes(payload), mode, n)
        elif tag == TAG_ZLIB:
            cells = planes_to_cells(zlib.decompress(payload), mode, n)
        elif tag == TAG_DELTA:
            raw = zlib.decompress(payload)
            k = len(raw) // (4 + bpc)
            ci = np.frombuffer(raw, "<u4", k, 0)
            vals = np.frombuffer(raw, np.uint8, k * bpc, 4 * k).reshape(k, bpc)
            cells = prev.copy()
            cells[ci] = vals
        elif tag == TAG_DELTA_MASK:
            raw = zlib.decompress(payload)
            mask_len = (n + 7) // 8
            changed = np.unpackbits(np.frombuffer(raw, np.uint8, mask_len, 0),
                                    count=n, bitorder="little").astype(bool)
            k = int(changed.sum())
            vals = np.frombuffer(raw, np.uint8, k * bpc, mask_len).reshape(k, bpc)
            cells = prev.copy()
            cells[changed] = vals
        else:
            raise ValueError("tag desconocido %d" % tag)
        cells_list.append(cells)
        pal_list.append(cur_pal)
        prev = cells
    return hdr, ramp, cells_list, pal_list


def _decode_all_v2(buf, hdr):
    # Import diferido: mantiene al decoder v1 utilizable de forma aislada y evita
    # duplicar el parser/validador transaccional del codec regional.
    import ascl_v2

    frames = list(ascl_v2.iter_decoded_v2(buf))
    cells_list = [frame["cells"].reshape(-1, 1).copy() for frame in frames]
    pal_list = [np.frombuffer(frame["palette"], np.uint8).reshape(-1, 3).copy()
                for frame in frames]
    return hdr, "", cells_list, pal_list


def decode_all(path):
    """Decodifica un archivo ASCL v1 o v2 conservando la API historica.

    Devuelve ``(header, ramp, cells_list, palette_list)``. Las matrices v2 se
    normalizan a ``(cols*rows, 1)``, igual que mode=PIXEL v1, para que previews,
    verificadores y benchmarks existentes no necesiten rutas especiales.
    """
    with open(path, "rb") as fh:
        buf = fh.read()
    hdr = parse_header(buf)
    hdr["crc_ok"] = compute_crc(buf, hdr) == hdr["crc32"]
    if hdr["version"] == 1:
        return _decode_all_v1(buf, hdr)
    if hdr["version"] == 2:
        return _decode_all_v2(buf, hdr)
    raise ValueError("version ASCL no soportada: %d" % hdr["version"])


def cells_to_rgb(hdr, cells, palette):
    mode, cols, rows = hdr["mode"], hdr["cols"], hdr["rows"]
    if mode == MODE_PIXEL:
        return palette[cells[:, 0]].reshape(rows, cols, 3)
    if mode == MODE_ASCII_PAL:
        return palette[cells[:, 1]].reshape(rows, cols, 3)
    if mode == MODE_ASCII_RGB:
        return cells[:, 1:4].reshape(rows, cols, 3)
    g = (cells[:, 0].astype(np.float32) / max(1, hdr["ramp_len"] - 1) * 255).astype(np.uint8)
    return np.dstack([g, g, g]).reshape(rows, cols, 3)


def render_glyph_png(hdr, ramp, cells, palette, png_path, scale):
    cols, rows, mode = hdr["cols"], hdr["rows"], hdr["mode"]
    cw = max(6, scale)
    ch = int(round(cw / max(0.1, hdr["char_aspect"])))
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", ch)
    except Exception:
        font = ImageFont.load_default()
    img = Image.new("RGB", (cols * cw, rows * ch), (0, 0, 0))
    d = ImageDraw.Draw(img)
    char_idx = cells[:, 0].reshape(rows, cols)
    if mode == MODE_ASCII_PAL:
        colors = palette[cells[:, 1]].reshape(rows, cols, 3)
    elif mode == MODE_ASCII_RGB:
        colors = cells[:, 1:4].reshape(rows, cols, 3)
    else:
        colors = None
    for r in range(rows):
        for c in range(cols):
            ch_ = ramp[min(int(char_idx[r, c]), len(ramp) - 1)] if ramp else "#"
            if ch_ == " ":
                continue
            col = (220, 220, 220) if colors is None else tuple(int(x) for x in colors[r, c])
            d.text((c * cw, r * ch), ch_, fill=col, font=font)
    img.save(png_path)
    return img.size


def write_mp4(frames_rgb, cols, rows, fps, scale, out_path):
    W, H = cols * scale, rows * scale
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for rgb in frames_rgb:
        big = np.asarray(Image.fromarray(rgb, "RGB").resize((W, H), Image.NEAREST))
        pr.stdin.write(big.tobytes())
    pr.stdin.close()
    pr.wait()
    return pr.returncode == 0


def verify_cells(cells_list, npz_path):
    exp = np.load(npz_path)
    keys = sorted(exp.files)
    ok, n = True, 0
    for i, key in enumerate(keys):
        if i >= len(cells_list):
            break
        ok = ok and np.array_equal(cells_list[i], exp[key])
        n += 1
    return ok, n


def main(argv=None):
    p = argparse.ArgumentParser(description="Decoder/verificador .ascl (ASCILINE).")
    p.add_argument("input")
    p.add_argument("--mp4", default=None)
    p.add_argument("--png", default=None)
    p.add_argument("--glyph-png", default=None)
    p.add_argument("--scale", type=int, default=4)
    p.add_argument("--verify-cells", default=None)
    p.add_argument("--no-preview", action="store_true")
    args = p.parse_args(argv)

    hdr, ramp, cells_list, pal_list = decode_all(args.input)
    print("-- HEADER --")
    print("  modo     : %s   v%d   fps %d   crc ASCL %s" %
          (MODE_LABEL[hdr["mode"]], hdr["version"], hdr["fps"],
           "OK" if hdr["crc_ok"] else "MISMATCH"))
    print("  grilla   : %dx%d   paleta %d   n_frames %d   rampa(%d)" %
          (hdr["cols"], hdr["rows"], hdr["pal_size"], hdr["n_frames"], hdr["ramp_len"]))

    if args.verify_cells:
        ok, n = verify_cells(cells_list, args.verify_cells)
        verdict = "FIDELIDAD PIXEL-PERFECT OK" if ok else "DIFERENCIAS"
        print("-- VERIFICACION (%d frames vs encoder) --  => %s" % (n, verdict))

    if args.no_preview:
        return 0

    if hdr["n_frames"] > 1:
        mp4 = args.mp4 or (args.input + ".preview.mp4")
        frames_rgb = (cells_to_rgb(hdr, cells_list[i], pal_list[i]) for i in range(len(cells_list)))
        ok = write_mp4(frames_rgb, hdr["cols"], hdr["rows"], hdr["fps"], args.scale, mp4)
        print("-- PREVIEW --  %s  (%s)" % (mp4, "ok" if ok else "ffmpeg fallo"))
        if hdr["mode"] in (MODE_ASCII_BW, MODE_ASCII_PAL, MODE_ASCII_RGB):
            gp = args.glyph_png or (args.input + ".frame0.glyphs.png")
            sz = render_glyph_png(hdr, ramp, cells_list[0], pal_list[0], gp, max(6, args.scale))
            print("  glifos f0: %s (%dx%d)" % (gp, sz[0], sz[1]))
    else:
        png = args.png or (args.input + ".decoded.png")
        rgb = cells_to_rgb(hdr, cells_list[0], pal_list[0])
        if hdr["mode"] == MODE_PIXEL:
            Image.fromarray(rgb, "RGB").resize(
                (hdr["cols"] * args.scale, hdr["rows"] * args.scale), Image.NEAREST).save(png)
        else:
            render_glyph_png(hdr, ramp, cells_list[0], pal_list[0], png, max(6, args.scale))
        print("-- PREVIEW --  %s" % png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
