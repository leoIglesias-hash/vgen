#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diag_white_frames.py - DIAG-002: buscar cuadros blancos DENTRO de los bytes.

El operador ve pantallazos blancos entre las imagenes al reproducir en un
WebView de TV box. Antes de tocar una linea del player hay que contestar la
pregunta que parte el problema en dos:

    el blanco, esta en los datos o lo pone el reproductor?

Este script decodifica el clip con el decoder de referencia (el mismo que
verifica byte a byte contra el encoder) y mide, cuadro por cuadro:

  - luma media del cuadro (Rec.601 sobre el color de cada celda),
  - fraccion de celdas casi blancas (luma >= --white-level),
  - salto de luma media contra el cuadro anterior.

Si en los datos hay cuadros blancos, aparecen aca y el player es inocente.
Si NO los hay, el blanco lo esta poniendo el frontend o el WebView, y el
diagnostico sigue del lado del navegador. Cualquiera de las dos respuestas
descarta la mitad del espacio de busqueda; suponer no descarta nada.

Uso:
  python tools/diag_white_frames.py clip.asclv
  python tools/diag_white_frames.py clip.ascl --white-level 235 --jump 40
"""

import argparse
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import ascl_bundle          # noqa: E402
import ascl_decode          # noqa: E402


def _as_ascl_path(path, tmpdir):
    """Devuelve la ruta de un .ascl: desempaqueta si le dan un .asclv."""
    with open(path, "rb") as fh:
        magic = fh.read(8)
    if magic not in (ascl_bundle.MAGIC_V1, ascl_bundle.MAGIC_V2, ascl_bundle.MAGIC_V3):
        return path
    ascl = ascl_bundle.read_parts(path)[0]
    inner = os.path.join(tmpdir, "inner.ascl")
    with open(inner, "wb") as fh:
        fh.write(ascl)
    return inner


def analyze(path, white_level, jump, top):
    tmpdir = tempfile.mkdtemp(prefix="diag002-")
    ascl_path = _as_ascl_path(path, tmpdir)
    hdr, _ramp, cells_list, palette_list = ascl_decode.decode_all(ascl_path)

    print("clip: %s" % os.path.basename(path))
    print("  %dx%d celdas, %d cuadros, %d fps, ASCL v%d, modo %s"
          % (hdr["cols"], hdr["rows"], len(cells_list), hdr["fps"],
             hdr["version"], ascl_decode.MODE_LABEL.get(hdr["mode"], "?")))
    print("  umbral de casi-blanco: luma >= %d" % white_level)

    means = np.zeros(len(cells_list), dtype=np.float64)
    whites = np.zeros(len(cells_list), dtype=np.float64)

    for i, cells in enumerate(cells_list):
        rgb = ascl_decode.cells_to_rgb(hdr, cells, palette_list[i])
        rgb = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)
        luma = 0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2]
        means[i] = luma.mean()
        whites[i] = float((luma >= white_level).mean())

    deltas = np.zeros_like(means)
    deltas[1:] = means[1:] - means[:-1]

    print("")
    print("  luma media: min %.1f  mediana %.1f  max %.1f"
          % (means.min(), np.median(means), means.max()))
    print("  casi-blanco: max %.1f %% del cuadro (cuadro %d)"
          % (whites.max() * 100.0, int(np.argmax(whites))))

    flagged = np.nonzero(np.abs(deltas) >= jump)[0]
    print("")
    if flagged.size == 0:
        print("  SIN saltos de luma >= %.1f entre cuadros consecutivos." % jump)
    else:
        print("  %d cuadro/s con salto de luma >= %.1f:" % (flagged.size, jump))
        for i in flagged[:top]:
            print("    cuadro %5d  t=%6.2fs  luma %6.1f (%+6.1f)  casi-blanco %5.1f %%"
                  % (i, i / float(hdr["fps"] or 1), means[i], deltas[i],
                     whites[i] * 100.0))
        if flagged.size > top:
            print("    ... y %d mas (limite --top)" % (flagged.size - top))

    order = np.argsort(-whites)[:top]
    print("")
    print("  cuadros mas blancos:")
    for i in order:
        print("    cuadro %5d  t=%6.2fs  casi-blanco %5.1f %%  luma media %6.1f"
              % (i, i / float(hdr["fps"] or 1), whites[i] * 100.0, means[i]))

    # Veredicto explicito: un cuadro "pantallazo" es mayoritariamente blanco.
    flash = np.nonzero(whites >= 0.60)[0]
    print("")
    if flash.size:
        print("VEREDICTO: hay %d cuadro/s con >= 60 %% de celdas casi blancas."
              % flash.size)
        print("           El blanco ESTA en los datos: %s"
              % ", ".join(str(int(i)) for i in flash[:20]))
        return 1
    print("VEREDICTO: ningun cuadro llega al 60 %% de celdas casi blancas.")
    print("           El blanco NO esta en los datos decodificados.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="DIAG-002: cuadros blancos en el clip")
    ap.add_argument("clip", help=".asclv (bundle) o .ascl")
    ap.add_argument("--white-level", type=float, default=235.0,
                    help="luma a partir de la cual una celda cuenta como casi blanca")
    ap.add_argument("--jump", type=float, default=40.0,
                    help="salto de luma media que se reporta como transicion brusca")
    ap.add_argument("--top", type=int, default=20, help="cuantas filas listar")
    args = ap.parse_args(argv)
    return analyze(args.clip, args.white_level, args.jump, args.top)


if __name__ == "__main__":
    sys.exit(main())
