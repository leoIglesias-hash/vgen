#!/usr/bin/env python3
"""E-06: horneado de glifos de digitos para la intervencion matricial.

Renderiza los digitos 0..9 desde una fuente monoespaciada, los reduce a una
grilla de glyph_w x glyph_h celdas por promedio de cobertura y cuantiza el
antialias a los indices reservados de INT-001 (DISENO-INTERVENCION-MATRICIAL
§4.3 y §5):

    246  fondo del panel        (cobertura ~0)
    247..250  cuatro niveles de antialias
    251  texto base             (cobertura ~1)
    255  transparente           (solo el glifo vacio, posicion 10)

Salida: tabla binaria de ``n_glyphs * glyph_w * glyph_h`` bytes con
``n_glyphs = 11`` (digitos 0..9 mas el glifo vacio) y, opcionalmente, un PNG
de inspeccion visual. Dos corridas con la misma fuente producen bytes
identicos: no hay aleatoriedad y el promedio es aritmetica entera.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

IDX_BACKGROUND = 246
IDX_ANTIALIAS_FIRST = 247   # 247..250
IDX_TEXT = 251
IDX_TRANSPARENT = 255
N_GLYPHS = 11               # 0..9 + vacio en la posicion 10
SUPERSAMPLE = 8

# Grises de inspeccion para el PNG (uno por indice reservado usado).
PREVIEW_RGB = {
    IDX_BACKGROUND: (20, 20, 30),
    247: (66, 66, 78),
    248: (118, 118, 130),
    249: (170, 170, 182),
    250: (214, 214, 224),
    IDX_TEXT: (255, 255, 255),
    IDX_TRANSPARENT: (128, 0, 128),  # nunca deberia verse en digitos
}


def load_font(font_path, pixel_height):
    candidates = ([font_path] if font_path else
                  ["DejaVuSansMono.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                   "C:/Windows/Fonts/consola.ttf"])
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, pixel_height)
        except Exception:
            continue
    raise SystemExit("no se encontro una fuente TrueType; use --font RUTA")


def render_digit(digit, glyph_w, glyph_h, font):
    """Cobertura entera 0..255 por celda, promediada de un render supersampled."""
    width = glyph_w * SUPERSAMPLE
    height = glyph_h * SUPERSAMPLE
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    text = str(digit)
    box = draw.textbbox((0, 0), text, font=font)
    text_w = box[2] - box[0]
    text_h = box[3] - box[1]
    x = (width - text_w) // 2 - box[0]
    y = (height - text_h) // 2 - box[1]
    draw.text((x, y), text, fill=255, font=font)
    data = np.asarray(image, dtype=np.uint32)
    cells = data.reshape(glyph_h, SUPERSAMPLE, glyph_w, SUPERSAMPLE)
    total = cells.sum(axis=(1, 3))
    return (total // (SUPERSAMPLE * SUPERSAMPLE)).astype(np.uint32)


def quantize_coverage(coverage):
    """Cobertura 0..255 -> indices reservados 246..251.

    Umbrales enteros fijos: [0..21]=fondo, luego cuatro bandas de antialias
    parejas y [234..255]=texto. Deterministas y sin flotantes.
    """
    idx = np.full(coverage.shape, IDX_BACKGROUND, dtype=np.uint8)
    idx[coverage > 21] = IDX_ANTIALIAS_FIRST
    idx[coverage > 74] = IDX_ANTIALIAS_FIRST + 1
    idx[coverage > 127] = IDX_ANTIALIAS_FIRST + 2
    idx[coverage > 180] = IDX_ANTIALIAS_FIRST + 3
    idx[coverage > 233] = IDX_TEXT
    return idx


def bake(glyph_w, glyph_h, font_path=None):
    """Devuelve la tabla completa: bytes de N_GLYPHS * glyph_h * glyph_w."""
    if glyph_w < 3 or glyph_h < 5:
        raise SystemExit("glifos minimos: 3x5 celdas")
    font = load_font(font_path, glyph_h * SUPERSAMPLE)
    glyphs = []
    for digit in range(10):
        coverage = render_digit(digit, glyph_w, glyph_h, font)
        peak = int(coverage.max())
        if peak == 0:
            raise SystemExit("el digito %d se rendereo vacio; "
                             "fuente o tamano inadecuados" % digit)
        # Normalizar al pico del glifo (entera, determinista): el trazo
        # principal siempre alcanza "texto" aunque sea mas fino que una celda.
        coverage = (coverage * 255) // peak
        quantized = quantize_coverage(coverage)
        if not (quantized == IDX_TEXT).any():
            raise SystemExit("el digito %d no produjo texto pleno; "
                             "fuente o tamano inadecuados" % digit)
        glyphs.append(quantized)
    glyphs.append(np.full((glyph_h, glyph_w), IDX_TRANSPARENT, dtype=np.uint8))
    return np.stack(glyphs)


def preview_png(table, path, scale=12):
    n, glyph_h, glyph_w = table.shape
    strip = np.zeros((glyph_h, glyph_w * n, 3), dtype=np.uint8)
    for g in range(n):
        for value, rgb in PREVIEW_RGB.items():
            mask = table[g] == value
            strip[:, g * glyph_w:(g + 1) * glyph_w][mask] = rgb
    image = Image.fromarray(strip, "RGB").resize(
        (glyph_w * n * scale, glyph_h * scale), Image.NEAREST)
    image.save(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glyph-w", type=int, default=8)
    parser.add_argument("--glyph-h", type=int, default=12)
    parser.add_argument("--font", default=None,
                        help="ruta a una fuente TrueType monoespaciada")
    parser.add_argument("--out", default="outputs/glyphs.bin")
    parser.add_argument("--png", default=None,
                        help="PNG de inspeccion visual (opcional)")
    args = parser.parse_args(argv)

    table = bake(args.glyph_w, args.glyph_h, args.font)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(args.out, "wb") as stream:
        stream.write(table.tobytes())
    print("OK %s: %d glifos de %dx%d, %d bytes" %
          (args.out, table.shape[0], args.glyph_w, args.glyph_h,
           table.size))
    if args.png:
        preview_png(table, args.png)
        print("preview: %s" % args.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
