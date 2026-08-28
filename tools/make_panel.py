#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7: sidecar ASCLSLOT del panel canonico de 20 numeros para un clip dado.

Lee cols/rows/n_frames del ``.asclv`` (o ``.ascl``) indicado, toma la tabla
de glifos horneada por E-06 (``bake_glyphs.py``) y construye el panel de
referencia de INT-001 §1: veinte campos de dos digitos (00..99, con ceros a
la izquierda) en dos filas de diez, centrado sobre el borde inferior de la
grilla. El sidecar se valida ENTERO contra el clip antes de escribirse.

Uso:
    python tools/make_panel.py outputs/clip.asclv --glyphs outputs/glyphs.bin \
        --out outputs/clip.slots
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, HERE)

import ascl_bundle  # noqa: E402
import ascl_decode  # noqa: E402
import make_slots  # noqa: E402
from overlay_palette import reserved_rgb_bytes  # noqa: E402

GLYPH_W, GLYPH_H = 8, 12
N_FIELDS = 20
GROUPS_PER_ROW = 10
DIGIT_GAP = 2     # celdas entre los dos digitos de un numero
GROUP_GAP = 20    # celdas entre numeros de una misma fila
ROW_GAP = 8       # celdas entre las dos filas
BOTTOM_MARGIN = 16


def panel_spec(cols, rows, n_frames, glyph_table):
    """Layout determinista del panel; lanza ValueError si la grilla no alcanza."""
    group_w = GLYPH_W * 2 + DIGIT_GAP
    row_w = GROUPS_PER_ROW * group_w + (GROUPS_PER_ROW - 1) * GROUP_GAP
    if row_w > cols:
        raise ValueError("grilla de %d columnas no alcanza para el panel (%d)"
                         % (cols, row_w))
    x0 = (cols - row_w) // 2
    y_bottom = rows - GLYPH_H - BOTTOM_MARGIN
    y_top = y_bottom - GLYPH_H - ROW_GAP
    if y_top < 0:
        raise ValueError("grilla de %d filas no alcanza para el panel" % rows)
    slots, fields = [], []
    for number in range(N_FIELDS):
        row, column = divmod(number, GROUPS_PER_ROW)
        x = x0 + column * (group_w + GROUP_GAP)
        y = y_top if row == 0 else y_bottom
        first = len(slots)
        slots.append({"x": x, "y": y, "start": 0,
                      "end": n_frames - 1, "flags": 1})
        slots.append({"x": x + GLYPH_W + DIGIT_GAP, "y": y, "start": 0,
                      "end": n_frames - 1, "flags": 1})
        fields.append({"field_id": number + 1, "slot_ids": [first, first + 1],
                       "min": 0, "max": 99, "pad": 1})
    return {
        "glyph_w": GLYPH_W, "glyph_h": GLYPH_H, "glyph_table": glyph_table,
        "reserved_rgb": reserved_rgb_bytes(),
        "slots": slots, "fields": fields,
    }


def build_sidecar(cols, rows, n_frames, glyph_table):
    """Construye y valida el sidecar del panel; devuelve los bytes."""
    data = make_slots.build(panel_spec(cols, rows, n_frames, glyph_table))
    make_slots.validate(data, cols, rows, n_frames, reserved_rgb_bytes())
    return data


def clip_geometry(path):
    """(cols, rows, n_frames) del clip, sea .asclv (bundle) o .ascl pelado."""
    if path.lower().endswith(".asclv"):
        ascl, _audio, _version = ascl_bundle.read_parts_info(path)
    else:
        with open(path, "rb") as stream:
            ascl = stream.read()
    header = ascl_decode.parse_header(ascl)
    return header["cols"], header["rows"], header["n_frames"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", help=".asclv o .ascl del que tomar la geometria")
    parser.add_argument("--glyphs", required=True,
                        help="tabla horneada por bake_glyphs.py (11 glifos 8x12)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.glyphs, "rb") as stream:
        glyph_table = stream.read()
    expected = 11 * GLYPH_W * GLYPH_H
    if len(glyph_table) != expected:
        raise SystemExit("tabla de glifos de %d bytes; se esperaban %d"
                         % (len(glyph_table), expected))
    cols, rows, n_frames = clip_geometry(args.clip)
    data = build_sidecar(cols, rows, n_frames, glyph_table)
    with open(args.out, "wb") as stream:
        stream.write(data)
    print("OK %s: %d bytes, panel %d campos sobre %dx%d (%d frames)" %
          (args.out, len(data), N_FIELDS, cols, rows, n_frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
