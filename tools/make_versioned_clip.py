#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CACHE-001 (F6-4): instala el clip con nombre versionado por contenido.

Dado un ``clip.asclv`` valido, escribe en el mismo directorio (o en ``--out-dir``):

  clip.<sha12>.asclv    copia BYTE-IDENTICA, nombrada por su SHA-256 (12 hex)
  clip.current.txt      puntero de texto plano; primera linea no-comentario =
                        el nombre versionado (formato que valida
                        frontend/cache-refresh.js::parseClipPointer)

El nombre versionado es inmutable por construccion (contenido nuevo => nombre
nuevo) y puede servirse con ``Cache-Control: public, max-age=31536000,
immutable``. El puntero es el UNICO recurso mutable y se sirve con
no-cache/ETag. Los players caen a ``clip.asclv`` si el puntero no existe.

CLI:
    python tools/make_versioned_clip.py outputs/clip.asclv [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import ascl_bundle  # noqa: E402

SHORT_HEX = 12
POINTER_NAME = "clip.current.txt"


def install_versioned(asclv_path, out_dir=None):
    """Devuelve ``(nombre_versionado, sha256_hex)``; escritura atomica."""
    with open(asclv_path, "rb") as stream:
        payload = stream.read()
    if payload[:8] not in ascl_bundle.MAGICS:
        raise ValueError("la entrada no es un .asclv (magic invalido)")
    digest = hashlib.sha256(payload).hexdigest()
    name = "clip.%s.asclv" % digest[:SHORT_HEX]
    out_dir = out_dir or os.path.dirname(os.path.abspath(asclv_path))
    os.makedirs(out_dir, exist_ok=True)

    def atomic_write(path, data):
        temporary = path + ".tmp"
        with open(temporary, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)

    atomic_write(os.path.join(out_dir, name), payload)
    pointer = ("# ASCILINE CACHE-001; sha256=%s\n%s\n" % (digest, name))
    atomic_write(os.path.join(out_dir, POINTER_NAME),
                 pointer.encode("ascii"))
    return name, digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="ruta al clip.asclv")
    parser.add_argument("--out-dir", default=None,
                        help="directorio destino (default: el del input)")
    args = parser.parse_args(argv)
    try:
        name, digest = install_versioned(args.input, args.out_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("OK %s  (sha256 %s)" % (name, digest))
    print("puntero: %s -> %s" % (POINTER_NAME, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
