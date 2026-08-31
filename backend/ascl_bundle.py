#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ascl_bundle.py - Empaqueta video (.ascl) + audio (.mp3) en UN archivo .asclv.

Asi cada clip es un solo archivo y no hay que andar emparejando .ascl con .mp3.

Formato .asclv v1/v2 (16 bytes de header + 2 cargas):
    magic     8 bytes  = b"ASCLVID1" o b"ASCLVID2"
    ascl_len  uint32 LE
    audio_len uint32 LE  (0 = sin audio)
    [ascl bytes][audio bytes]

Formato .asclv v3 (F6-3; 20 bytes de header + 3 cargas):
    magic     8 bytes  = b"ASCLVID3"
    ascl_len  uint32 LE
    audio_len uint32 LE  (0 = sin audio)
    meta_len  uint32 LE  (0 = sin overlay; sidecar ASCLSLOT embebido, bytes exactos)
    [ascl bytes][audio bytes][meta bytes]

La version del envelope y la del ASCL interior deben coincidir (1<->1, 2<->2,
3<->3); `meta` solo existe en v3 — el sidecar externo `clip.slots` queda como
via de transicion. Readers viejos rechazan ASCLVID3 por magic, limpiamente.

CLI:
    python ascl_bundle.py pack   video.ascl audio.mp3 salida.asclv [meta.slots]
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
MAGIC_V3 = b"ASCLVID3"
MAGIC = MAGIC_V1              # alias histórico para callers v1
MAGICS = {MAGIC_V1: 1, MAGIC_V2: 2, MAGIC_V3: 3}
HEADER_FMT = "<8sII"          # magic, ascl_len, audio_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 16
HEADER_V3_FMT = "<8sIII"      # magic, ascl_len, audio_len, meta_len
HEADER_V3_SIZE = struct.calcsize(HEADER_V3_FMT)  # 20


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
    if version not in (1, 2, 3):
        raise ValueError("version ASCL interna no soportada: %d" % version)
    return version


def pack_bytes(ascl, audio, out_path, meta=b""):
    """Empaqueta cargas ya leídas y selecciona ASCLVID1/2/3 por la versión interna.

    ``meta`` (sidecar ASCLSLOT embebido, bytes exactos) solo es válido con un
    interior ASCL v3; con v1/v2 el header no tiene dónde declararlo.
    """
    ascl = bytes(ascl)
    audio = bytes(audio or b"")
    meta = bytes(meta or b"")
    version = _inner_version(ascl)
    if meta and version != 3:
        raise ValueError("meta embebida requiere interior ASCL v3 (ASCLVID3)")
    magic = {1: MAGIC_V1, 2: MAGIC_V2, 3: MAGIC_V3}[version]
    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    publish_mode = _publish_mode(out_path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".asclv-", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(descriptor, "wb") as f:
            if version == 3:
                f.write(struct.pack(HEADER_V3_FMT, magic, len(ascl),
                                    len(audio), len(meta)))
            else:
                f.write(struct.pack(HEADER_FMT, magic, len(ascl), len(audio)))
            f.write(ascl)
            f.write(audio)
            f.write(meta)
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


def pack(ascl_path, audio_path, out_path, meta_path=None):
    with open(ascl_path, "rb") as f:
        ascl = f.read()
    audio = b""
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio = f.read()
    meta = b""
    if meta_path:
        with open(meta_path, "rb") as f:
            meta = f.read()
    return pack_bytes(ascl, audio, out_path, meta=meta)


def read_parts_meta(asclv_path):
    """Devuelve (ascl, audio, meta, bundle_version) con validación exacta.

    El header se valida contra el tamaño real del archivo ANTES de cargarlo a
    memoria: un .asclv gigante o inconsistente falla con un error claro en vez
    de un MemoryError a mitad de lectura. ``meta`` es b"" en v1/v2 y en un v3
    sin overlay.
    """
    file_size = os.path.getsize(asclv_path)
    with open(asclv_path, "rb") as f:
        head = f.read(HEADER_V3_SIZE)
        if len(head) < HEADER_SIZE:
            raise ValueError(".asclv truncado (falta header)")
        magic = head[:8]
        if magic not in MAGICS:
            raise ValueError("no es un .asclv (magic invalido)")
        if magic == MAGIC_V3:
            if len(head) < HEADER_V3_SIZE:
                raise ValueError(".asclv v3 truncado (falta header)")
            _magic, ascl_len, audio_len, meta_len = struct.unpack_from(
                HEADER_V3_FMT, head, 0)
            header_size = HEADER_V3_SIZE
        else:
            _magic, ascl_len, audio_len = struct.unpack_from(
                HEADER_FMT, head, 0)
            meta_len = 0
            header_size = HEADER_SIZE
        expected = header_size + ascl_len + audio_len + meta_len
        if expected != file_size:
            raise ValueError(".asclv truncado o con bytes extra")
        buf = head + f.read()
    if len(buf) != file_size:
        raise ValueError(".asclv cambio de tamano durante la lectura")
    o = header_size
    ascl = buf[o:o + ascl_len]
    audio = buf[o + ascl_len:o + ascl_len + audio_len]
    meta = buf[o + ascl_len + audio_len:o + ascl_len + audio_len + meta_len]
    version = _inner_version(ascl)
    if version != MAGICS[magic]:
        raise ValueError("version del bundle no coincide con el ASCL interno")
    return ascl, audio, meta, version


def read_parts_info(asclv_path):
    """Devuelve (ascl_bytes, audio_bytes, bundle_version); la meta v3 se valida
    igual pero no se devuelve (compat con callers previos a F6-3)."""
    ascl, audio, _meta, version = read_parts_meta(asclv_path)
    return ascl, audio, version


def read_parts(asclv_path):
    """Devuelve (ascl_bytes, audio_bytes). audio_bytes = b'' si no hay."""
    ascl, audio, _version = read_parts_info(asclv_path)
    return ascl, audio


def unpack(asclv_path, out_dir=None):
    ascl, audio, meta, _version = read_parts_meta(asclv_path)
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
    meta_path = None
    if meta:
        meta_path = os.path.join(out_dir, base + ".slots")
        with open(meta_path, "wb") as f:
            f.write(meta)
    return ascl_path, audio_path, meta_path


def main(argv=None):
    a = (argv if argv is not None else sys.argv[1:])
    if not a:
        print(__doc__); return 2
    cmd = a[0]
    if cmd == "pack":
        ascl_p, audio_p, out_p = a[1], a[2], a[3]
        meta_p = a[4] if len(a) > 4 else None
        total, la, lau = pack(ascl_p, audio_p, out_p, meta_path=meta_p)
        print("OK %s  (%d B = ascl %d + audio %d%s)" %
              (out_p, total, la, lau,
               (" + meta %d" % (total - HEADER_V3_SIZE - la - lau))
               if meta_p else ""))
    elif cmd == "unpack":
        out_dir = a[2] if len(a) > 2 else None
        ascl_p, audio_p, meta_p = unpack(a[1], out_dir)
        extras = "".join("  +  " + p for p in (audio_p, meta_p) if p)
        print("OK -> %s%s" % (ascl_p, extras or "  (sin audio)"))
    elif cmd == "info":
        ascl, audio, meta, version = read_parts_meta(a[1])
        print("ASCLV%d  ascl: %d B   audio: %d B%s   meta: %d B" %
              (version, len(ascl), len(audio),
               "" if audio else " (sin audio)", len(meta)))
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
