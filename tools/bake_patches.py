#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INT-003-E: horneado de parches arbitrarios a la reserva ampliada (32).

Convierte offline (a) texto con CUALQUIER fuente TrueType o (b) una imagen
PNG con alpha, en parches de celdas cuantizados a las entradas reservadas
224..254 de ``overlay_palette.RESERVED_RGB_32`` (la 255 es transparente y
nunca se pinta: el alpha bajo el umbral se vuelve 255).

La cuantizacion elige la entrada reservada mas cercana en **Oklab**
(``perceptual_palette.srgb_to_oklab``, la misma metrica del encoder); los
empates se resuelven por indice menor (argmin), asi dos corridas con la misma
entrada producen bytes identicos. El negro pleno no existe como color de
parche (el RGB de la entrada 255 esta reservado a la transparencia): su
vecino mas cercano es el fondo 246 (16,16,30).

Salida CLI: bytes crudos ``w*h`` por parche (el modo ``digits`` concatena los
11 parches: digitos 0..9 + vacio, como la tabla E-06), listos para el campo
``patches`` del spec v2 de ``make_slots``.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, HERE)

import overlay_palette  # noqa: E402
import perceptual_palette  # noqa: E402
from bake_glyphs import SUPERSAMPLE, load_font  # noqa: E402

TRANSPARENT = 255
ALPHA_THRESHOLD = 128
N_DIGIT_PATCHES = 11  # 0..9 + vacio

# entradas pintables: 224..254 (la 255 es transparente)
_PAINTABLE = overlay_palette.RESERVED_RGB_32[:31]
_PAINTABLE_LAB = perceptual_palette.srgb_to_oklab(_PAINTABLE)


def nearest_reserved(rgb):
    """(n, 3) uint8 -> (n,) uint8 con el indice reservado 224..254 mas
    cercano en Oklab. Empates: el indice menor (determinista)."""
    rgb = np.asarray(rgb, dtype=np.uint8).reshape(-1, 3)
    lab = perceptual_palette.srgb_to_oklab(rgb)
    distances = ((lab[:, None, :] - _PAINTABLE_LAB[None, :, :]) ** 2).sum(-1)
    return (224 + distances.argmin(axis=1)).astype(np.uint8)


def quantize_rgba(rgba):
    """(h, w, 4) uint8 -> (h, w) uint8 de indices reservados; alpha bajo el
    umbral -> 255 (transparente)."""
    rgba = np.asarray(rgba, dtype=np.uint8)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("se espera una imagen RGBA (h, w, 4)")
    height, width = rgba.shape[:2]
    out = np.full((height, width), TRANSPARENT, dtype=np.uint8)
    opaque = rgba[:, :, 3] >= ALPHA_THRESHOLD
    if opaque.any():
        out[opaque] = nearest_reserved(rgba[:, :, :3][opaque])
    return out


def bake_image_array(rgba, cell_w, cell_h):
    """Reduce una imagen RGBA a ``cell_w x cell_h`` celdas (promedio de area,
    Image.BOX: determinista) y cuantiza. Devuelve {w, h, data}."""
    image = Image.fromarray(np.asarray(rgba, dtype=np.uint8), "RGBA")
    small = image.resize((int(cell_w), int(cell_h)), Image.BOX)
    grid = quantize_rgba(np.asarray(small, dtype=np.uint8))
    return {"w": int(cell_w), "h": int(cell_h), "data": grid.tobytes()}


def bake_image(path, cell_w, cell_h):
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    return bake_image_array(rgba, cell_w, cell_h)


def _render_coverage(text, cell_w, cell_h, font):
    """Cobertura entera 0..255 por celda, promediada de un render
    supersampleado y normalizada al pico (como E-06)."""
    from PIL import ImageDraw
    width = cell_w * SUPERSAMPLE
    height = cell_h * SUPERSAMPLE
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), text, font=font)
    x = (width - (box[2] - box[0])) // 2 - box[0]
    y = (height - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), text, fill=255, font=font)
    data = np.asarray(image, dtype=np.uint32)
    cells = data.reshape(cell_h, SUPERSAMPLE, cell_w, SUPERSAMPLE)
    total = cells.sum(axis=(1, 3)) // (SUPERSAMPLE * SUPERSAMPLE)
    peak = int(total.max())
    if peak == 0:
        raise SystemExit("el texto %r se rendereo vacio; "
                         "fuente o tamano inadecuados" % text)
    return (total * 255 // peak).astype(np.uint32)


def bake_text(text, cell_w, cell_h, font_path=None, color=(255, 255, 255)):
    """Parche de texto sobre fondo TRANSPARENTE: cobertura >= umbral pinta el
    color (cuantizado a la reserva), el resto queda 255. Sin antialias: el
    parche se apoya directo sobre el video (el panel v1 conserva el suyo)."""
    if cell_w < 3 or cell_h < 5:
        raise SystemExit("parches de texto minimos: 3x5 celdas")
    font = load_font(font_path, cell_h * SUPERSAMPLE)
    coverage = _render_coverage(text, cell_w, cell_h, font)
    index = int(nearest_reserved(
        np.array([color], dtype=np.uint8))[0])
    grid = np.where(coverage >= ALPHA_THRESHOLD, index,
                    TRANSPARENT).astype(np.uint8)
    return {"w": int(cell_w), "h": int(cell_h), "data": grid.tobytes()}


def bake_digit_patches(cell_w, cell_h, font_path=None,
                       color=(255, 255, 255)):
    """Los 11 parches de un campo de digitos v2 (0..9 + vacio), con la
    tipografia y el color pedidos. Devuelve la lista para ``make_slots``."""
    patches = [bake_text(str(digit), cell_w, cell_h, font_path, color)
               for digit in range(10)]
    patches.append({"w": int(cell_w), "h": int(cell_h),
                    "data": b"\xff" * (int(cell_w) * int(cell_h))})
    return patches


def _parse_color(text):
    parts = [int(part) for part in text.split(",")]
    if len(parts) != 3 or any(not 0 <= part <= 255 for part in parts):
        raise argparse.ArgumentTypeError("color R,G,B en 0..255")
    return tuple(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    text_parser = sub.add_parser("text", help="hornear un texto")
    text_parser.add_argument("text")
    image_parser = sub.add_parser("image", help="hornear un PNG con alpha")
    image_parser.add_argument("image")
    digits_parser = sub.add_parser(
        "digits", help="los 11 parches de digitos (0..9 + vacio), "
        "concatenados como la tabla E-06")

    for p in (text_parser, image_parser, digits_parser):
        p.add_argument("--w", type=int, required=True, help="celdas de ancho")
        p.add_argument("--h", type=int, required=True, help="celdas de alto")
        p.add_argument("--out", required=True)
    for p in (text_parser, digits_parser):
        p.add_argument("--font", default=None,
                       help="ruta a una fuente TrueType (cualquiera)")
        p.add_argument("--color", type=_parse_color, default=(255, 255, 255))
    args = parser.parse_args(argv)

    if args.mode == "text":
        patches = [bake_text(args.text, args.w, args.h, args.font,
                             args.color)]
    elif args.mode == "image":
        patches = [bake_image(args.image, args.w, args.h)]
    else:
        patches = bake_digit_patches(args.w, args.h, args.font, args.color)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(args.out, "wb") as stream:
        for patch in patches:
            stream.write(patch["data"])
    print("OK %s: %d parche(s) de %dx%d, %d bytes" %
          (args.out, len(patches), args.w, args.h,
           sum(len(p["data"]) for p in patches)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
