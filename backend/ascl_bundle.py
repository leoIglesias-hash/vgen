#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ascl_bundle.py - Empaqueta video (.ascl) + audio (.mp3) en UN archivo .asclv.

Asi cada clip es un solo archivo y no hay que andar emparejando .ascl con .mp3.

Formato .asclv (16 bytes de header + 2 cargas):
    magic     8 bytes  = b"ASCLVID1" o b"ASCLVID2"
    ascl_len  uint32 LE
    audio_len uint32 LE  (0 = sin audio)
    [ascl bytes][audio bytes]

CLI:
    python ascl_bundle.py pack   video.ascl audio.mp3 salida.asclv
    python ascl_bundle.py unpack salida.asclv  [carpeta_destino]
    python ascl_bundle.py info   salida.asclv
"""
import os
import stat
import struct
import sys
import tempfile

MAGIC_V1 = b"ASCLVID1"
MAGIC_V2 = b"ASCLVID2"
MAGIC = MAGIC_V1              # alias histórico para callers v1
MAGICS = {MAGIC_V1: 1, MAGIC_V2: 2}
HEADER_FMT = "<8sII"          # magic, ascl_len, audio_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 16


def _publish_mode(out_path):
    """Conserva permisos existentes o aplica 0666 limitado por el umask."""
    try:
        return stat.S_IMODE(os.stat(out_path).st_mode) & 0o777
    except (FileNotFoundError, PermissionError):
        # PermissionError: si os.stat falla por permisos, publicar con el modo
        # por defecto en vez de abortar todo el pack.
        current_umask = os.umask(0)
        os.umask(current_umask)
        return 0o666 & ~current_umask


def _inner_version(ascl):
    if len(ascl) < 5 or ascl[:4] != b"ASCL":
        raise ValueError("video interno invalido (magic ASCL ausente)")
    version = ascl[4]
    if version not in (1, 2):
        raise ValueError("version ASCL interna no soportada: %d" % version)
    return version


def pack_bytes(ascl, audio, out_path):
    """Empaqueta cargas ya leídas y selecciona ASCLVID1/2 por la versión interna."""
    ascl = bytes(ascl)
    audio = bytes(audio or b"")
    version = _inner_version(ascl)
    magic = MAGIC_V1 if version == 1 else MAGIC_V2
    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    publish_mode = _publish_mode(out_path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".asclv-", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(descriptor, "wb") as f:
            f.write(struct.pack(HEADER_FMT, magic, len(ascl), len(audio)))
            f.write(ascl)
            f.write(audio)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp crea 0600 en POSIX. Antes del replace se restaura el modo
        # publico esperado para que Apache/nginx pueda leer el artefacto.
        os.chmod(temporary, publish_mode)
        os.replace(temporary, out_path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return os.path.getsize(out_path), len(ascl), len(audio)


def pack(ascl_path, audio_path, out_path):
    with open(ascl_path, "rb") as f:
        ascl = f.read()
    audio = b""
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio = f.read()
    return pack_bytes(ascl, audio, out_path)


def read_parts_info(asclv_path):
    """Devuelve (ascl_bytes, audio_bytes, bundle_version) con validación exacta.

    El header se valida contra el tamaño real del archivo ANTES de cargarlo a
    memoria: un .asclv gigante o inconsistente falla con un error claro en vez
    de un MemoryError a mitad de lectura.
    """
    file_size = os.path.getsize(asclv_path)
    with open(asclv_path, "rb") as f:
        head = f.read(HEADER_SIZE)
        if len(head) < HEADER_SIZE:
            raise ValueError(".asclv truncado (falta header)")
        magic, ascl_len, audio_len = struct.unpack_from(HEADER_FMT, head, 0)
        if magic not in MAGICS:
            raise ValueError("no es un .asclv (magic invalido)")
        expected = HEADER_SIZE + ascl_len + audio_len
        if expected != file_size:
            raise ValueError(".asclv truncado o con bytes extra")
        buf = head + f.read()
    if len(buf) != file_size:
        raise ValueError(".asclv cambio de tamano durante la lectura")
    o = HEADER_SIZE
    ascl = buf[o:o + ascl_len]
    audio = buf[o + ascl_len:o + ascl_len + audio_len]
    version = _inner_version(ascl)
    if version != MAGICS[magic]:
        raise ValueError("version del bundle no coincide con el ASCL interno")
    return ascl, audio, version


def read_parts(asclv_path):
    """Devuelve (ascl_bytes, audio_bytes). audio_bytes = b'' si no hay."""
    ascl, audio, _version = read_parts_info(asclv_path)
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
        ascl, audio, version = read_parts_info(a[1])
        print("ASCLV%d  ascl: %d B   audio: %d B%s" %
              (version, len(ascl), len(audio), "" if audio else " (sin audio)"))
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
