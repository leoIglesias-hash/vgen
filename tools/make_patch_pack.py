#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INT-003-F: sidecar ASCLSLOT v2 de demo (parches genericos) para un clip.

Construye, sobre la geometria del clip dado (``reserved=32``), un sidecar v2
que demuestra la via corta de DISENO-PARCHES-GENERICOS:

- el panel canonico de 20 numeros (kind 0), con digitos monoespaciados 8x12
  horneados con tipografia libre sobre fondo transparente;
- tres numeros GRANDES de dos digitos (kind 0, 26x36 por digito, serif dorada
  por defecto) en tres posiciones distintas con ventanas temporales
  disjuntas (tercios del clip): el dato elige que numero se ve y donde/cuando
  cambia el archivo de datos;
- un campo de ELECCION (kind 1) con tres palabras pre-horneadas: el dato
  selecciona una variante o ninguna (digito de presencia), el mecanismo de la
  ruleta a escala chica.

El sidecar se valida ENTERO (presupuestos por frame y de RAM incluidos)
antes de escribirse. ``--sample-data`` escribe un ``data.txt`` de ejemplo con
el payload completo (48 digitos).

Uso:
    python tools/make_patch_pack.py outputs/clip.asclv --out outputs/clip.slots \
        [--font-panel TTF] [--font-big TTF] [--sample-data outputs/data.txt]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, HERE)

import bake_patches  # noqa: E402
import make_slots  # noqa: E402
import overlay_panel  # noqa: E402
from make_panel import clip_geometry  # noqa: E402
from overlay_palette import reserved_rgb_bytes  # noqa: E402

PANEL_W, PANEL_H = overlay_panel.GLYPH_W, overlay_panel.GLYPH_H
BIG_W, BIG_H = 26, 36
BIG_GAP = 3
WORD_W, WORD_H = 64, 14
WORDS = ("GANA", "SUERTE", "HOY")
GOLD = (255, 215, 0)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)

SERIF_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/georgia.ttf",
)


def default_big_font():
    for candidate in SERIF_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None  # cae en la monoespaciada de load_font


def demo_meta(cols, rows, n_frames, font_panel=None, font_big=None):
    """Metadata v2 completa de la demo; ``make_slots.validate`` la audita."""
    if n_frames < 3:
        raise ValueError("la demo necesita al menos 3 frames (tercios)")
    if font_big is None:
        font_big = default_big_font()

    patches = bake_patches.bake_digit_patches(
        PANEL_W, PANEL_H, font_panel, WHITE)                 # 0..10
    patches += bake_patches.bake_digit_patches(
        BIG_W, BIG_H, font_big, GOLD)                        # 11..21
    for word in WORDS:                                       # 22..24
        patches.append(bake_patches.bake_text(
            word, WORD_W, WORD_H, font_big, GREEN))

    slots, fields = [], []
    for rect in overlay_panel.panel_rects(cols, rows):
        slots.append({"x": rect[0], "y": rect[1],
                      "w": PANEL_W, "h": PANEL_H,
                      "start": 0, "end": n_frames - 1, "flags": 1})
    for number in range(overlay_panel.N_FIELDS):
        fields.append({"field_id": number + 1, "kind": 0,
                       "slot_ids": [number * 2, number * 2 + 1],
                       "min": 0, "max": 99, "pad": 1, "patch_base": 0})

    # tres numeros grandes: posiciones distintas, ventanas por tercios
    big_w_total = BIG_W * 2 + BIG_GAP
    third = n_frames // 3
    windows = ((0, third - 1), (third, 2 * third - 1),
               (2 * third, n_frames - 1))
    positions = (
        (cols // 8, rows // 6),
        (cols // 2 - big_w_total // 2, rows // 3),
        (cols - cols // 8 - big_w_total, rows // 6),
    )
    for index in range(3):
        x, y = positions[index]
        start, end = windows[index]
        first = len(slots)
        slots.append({"x": x, "y": y, "w": BIG_W, "h": BIG_H,
                      "start": start, "end": end, "flags": 1})
        slots.append({"x": x + BIG_W + BIG_GAP, "y": y,
                      "w": BIG_W, "h": BIG_H,
                      "start": start, "end": end, "flags": 1})
        fields.append({"field_id": 21 + index, "kind": 0,
                       "slot_ids": [first, first + 1],
                       "min": 0, "max": 99, "pad": 1, "patch_base": 11})

    # campo de eleccion: una palabra entre tres, o ninguna (presencia)
    word_slot = len(slots)
    slots.append({"x": cols // 2 - WORD_W // 2, "y": rows // 2,
                  "w": WORD_W, "h": WORD_H,
                  "start": 0, "end": n_frames - 1, "flags": 1})
    fields.append({"field_id": 24, "kind": 1, "slot_ids": [word_slot],
                   "min": 0, "max": 2, "pad": 0, "patch_base": 22})

    return {"pal_reserved": 32, "reserved_rgb": reserved_rgb_bytes(32),
            "patches": patches, "slots": slots, "fields": fields}


def build_sidecar(cols, rows, n_frames, font_panel=None, font_big=None):
    """Construye y valida el sidecar v2 de demo; devuelve los bytes."""
    data = make_slots.build_v2(
        demo_meta(cols, rows, n_frames, font_panel, font_big))
    make_slots.validate(data, cols, rows, n_frames, reserved_rgb_bytes(32))
    return data


# payload de ejemplo: panel (40) + tres numeros grandes (6) + palabra (2)
SAMPLE_PAYLOAD = ("0512273481904465328917650342887201559634"
                  "070842" "11")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", help=".asclv o .ascl del que tomar la geometria")
    parser.add_argument("--out", required=True)
    parser.add_argument("--font-panel", default=None,
                        help="TTF para los digitos del panel (8x12)")
    parser.add_argument("--font-big", default=None,
                        help="TTF para numeros grandes y palabras "
                        "(default: serif del sistema)")
    parser.add_argument("--sample-data", default=None,
                        help="escribir un data.txt de ejemplo (serial 1)")
    args = parser.parse_args(argv)

    cols, rows, n_frames = clip_geometry(args.clip)
    data = build_sidecar(cols, rows, n_frames, args.font_panel, args.font_big)
    with open(args.out, "wb") as stream:
        stream.write(data)
    print("OK %s: %d bytes, 24 campos (20 panel + 3 grandes + 1 eleccion) "
          "sobre %dx%d (%d frames)" %
          (args.out, len(data), cols, rows, n_frames))
    if args.sample_data:
        with open(args.sample_data, "wb") as stream:
            stream.write(("00000001|" + SAMPLE_PAYLOAD + "\n")
                         .encode("ascii"))
        print("data de ejemplo: %s (%d digitos)" %
              (args.sample_data, len(SAMPLE_PAYLOAD)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
