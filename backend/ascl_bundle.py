#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ascl_bundle.py - Empaqueta video (.ascl) + audio (.mp3) en UN archivo .asclv.

Asi cada clip es un solo archivo y no hay que andar emparejando .ascl con .mp3.

Formato .asclv (16 bytes de header + 2 cargas):
    magic     8 bytes  = b"ASCLVID1"
    ascl_len  uint32 LE
    audio_len uint32 LE  (0 = sin audio)
    [ascl bytes][audio bytes]

CLI:
    python ascl_bundle.py pack   video.ascl audio.mp3 salida.asclv
    python ascl_bundle.py unpack salida.asclv  [carpeta_destino]
    python ascl_bundle.py info   salida.asclv
"""
import os
import struct
import sys

MAGIC = b"ASCLVID1"
HEADER_FMT = "<8sII"          # magic, ascl_len, audio_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 16


def pack(ascl_path, audio_path, out_path):
    with open(ascl_path, "rb") as f:
        ascl = f.read()
    audio = b""
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio = f.read()
    with open(out_path, "wb") as f:
        f.write(struct.pack(HEADER_FMT, MAGIC, len(ascl), len(audio)))
        f.write(ascl)
        f.write(audio)
    return os.path.getsize(out_path), len(ascl), len(audio)


def read_parts(asclv_path):
    """Devuelve (ascl_bytes, audio_bytes). audio_bytes = b'' si no hay."""
    with open(asclv_path, "rb") as f:
        buf = f.read()
    magic, ascl_len, audio_len = struct.unpack_from(HEADER_FMT, buf, 0)
    if magic != MAGIC:
        raise ValueError("no es un .asclv (magic invalido)")
    o = HEADER_SIZE
    ascl = buf[o:o + ascl_len]
    audio = buf[o + ascl_len:o + ascl_len + audio_len]
    return ascl, audio


def unpack(asclv_path, out_dir=None):
    ascl, audio = read_parts(asclv_path)
    base = os.path.splitext(os.path.basename(asclv_path))[0]
    out_dir = out_dir or os.path.dirname(os.path.abspath(asclv_path))
    ascl_path = os.path.join(out_dir, base + ".ascl")
    with open(ascl_path, "wb") as f:
        f.write(ascl)
    audio_path = None
    if audio:
        audio_path = os.path.join(out_dir, base + ".mp3")
        with open(audio_path, "wb") as f:
            f.write(audio)
    return ascl_path, audio_path


def main(argv=None):
    a = (argv if argv is not None else sys.argv[1:])
    if not a:
        print(__doc__); return 2
    cmd = a[0]
    if cmd == "pack":
        ascl_p, audio_p, out_p = a[1], a[2], a[3]
        total, la, lau = pack(ascl_p, audio_p, out_p)
        print("OK %s  (%d B = ascl %d + audio %d)" % (out_p, total, la, lau))
    elif cmd == "unpack":
        out_dir = a[2] if len(a) > 2 else None
        ascl_p, audio_p = unpack(a[1], out_dir)
        print("OK -> %s%s" % (ascl_p, ("  +  " + audio_p) if audio_p else "  (sin audio)"))
    elif cmd == "info":
        ascl, audio = read_parts(a[1])
        print("ascl: %d B   audio: %d B%s" % (len(ascl), len(audio), "" if audio else " (sin audio)"))
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
