#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
medir_banding.py - cuanto escalon (halo, anillos, banding) agrega una pieza de
video sobre los degrades suaves de su referencia.

Usa la MISMA metrica que `proxy_banding` de tools/bench_ref.py (E-24): luma
Oklab, promedio en bloques 2x2 (un tramado se anula, el borde de una meseta
sobrevive) y gradiente EXTRA del decodificado solo donde la referencia es
suave. Aca se aplica a piezas de video (mp4/webm) contra una referencia y4m o
cualquier video que ffmpeg lea, y se informa ademas la parte OSCURA (luma
Oklab < 0,35), que es donde vive el halo de un fondo negro->rojo oscuro.

Mas bajo = menos escalones. 0 = no agrega nada sobre la referencia.

Limite (medido en tests/test_medir_banding.py): el numero es RELATIVO a la
referencia. Si la referencia ya trae mesetas (una fuente de 8 bits con pocos
tonos), un resultado MAS liso que ella -lo que hace un deband- tambien suma
un poco, porque sube el gradiente donde la referencia era plana. O sea: este
numero detecta escalones nuevos, pero no puede premiar ir mas alla de la
fuente; para eso estan los recortes con gamma realzada y el ojo en el aparato.
Y suma el salto total: sobre una rampa, pocos escalones grandes o muchos
chicos dan parecido (el desnivel total es el mismo); un contorno NUEVO sobre
una zona plana (la mancha de un bloque) si crece con su altura.

Por que existe (2026-10-17, docs/INTRO-Y-LOOP.md): el halo de intro_D era un
resplandor de 8 tonos de luma (16..23); la paleta de 128 lo escalonaba y el
compresor lo manchaba. Este numero, junto con recortes con gamma realzada,
fue lo que permitio comparar remedios sin adivinar.

Uso:
  python tools/medir_banding.py referencia.y4m pieza1.mp4 pieza2.mp4 ...
  python tools/medir_banding.py ref.y4m pieza.mp4 --ancho 1280 --alto 720
"""

import argparse
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import bench_ref  # noqa: E402
import perceptual_palette  # noqa: E402

# Luma Oklab por debajo de esto = zona oscura (el negro es 0, el blanco 1).
OSCURO = 0.35


def luma_oklab(rgb):
    """RGB uint8 (alto, ancho, 3) -> luma Oklab (alto, ancho) float."""
    alto, ancho = rgb.shape[:2]
    lab = perceptual_palette.srgb_to_oklab(rgb.reshape(-1, 3))
    return np.asarray(lab).reshape(alto, ancho, 3)[..., 0]


def banding_cuadro(l_dec, l_ref, oscuro=OSCURO):
    """(suma, posiciones, suma_oscura, posiciones_oscuras) de un cuadro: la
    suma de bench_ref.banding_stats, y la misma restringida a donde la
    referencia (promediada 2x2) es oscura."""
    total, posiciones = bench_ref.banding_stats(l_dec, l_ref)
    ref = bench_ref._block_mean(l_ref)
    dec = bench_ref._block_mean(l_dec)
    es_oscuro = ref < oscuro
    total_osc = 0.0
    pos_osc = 0
    for axis in (0, 1):
        grad_ref = np.abs(np.diff(ref, axis=axis))
        grad_dec = np.abs(np.diff(dec, axis=axis))
        mascara = grad_ref <= bench_ref.BANDING_SMOOTH_T
        mascara &= es_oscuro[:-1, :] if axis == 0 else es_oscuro[:, :-1]
        pos_osc += int(mascara.sum())
        total_osc += float(np.clip(grad_dec - grad_ref, 0.0, None)[mascara].sum())
    return total, posiciones, total_osc, pos_osc


def banding(cuadros_dec, cuadros_ref, oscuro=OSCURO):
    """Dos iterables de RGB uint8 -> (banding, banding_oscuros), ambos x1000
    (gradiente extra medio por posicion medida). Compara hasta el mas corto."""
    total = posiciones = total_osc = pos_osc = 0.0
    for dec, ref in zip(cuadros_dec, cuadros_ref):
        t, p, to, po = banding_cuadro(luma_oklab(dec), luma_oklab(ref), oscuro)
        total += t
        posiciones += p
        total_osc += to
        pos_osc += po
    return (1000.0 * total / max(posiciones, 1),
            1000.0 * total_osc / max(pos_osc, 1))


def decode_command(ffmpeg, path, ancho, alto):
    """Cualquier video -> RGB24 crudo por stdout, con la MISMA conversion para
    referencia y piezas (709 rango tv), escalado a ancho x alto si hiciera falta."""
    return [ffmpeg, "-v", "error", "-nostdin", "-i", path, "-map", "0:v:0", "-vf",
            "scale=%d:%d:in_color_matrix=bt709:in_range=tv,format=rgb24" % (ancho, alto),
            "-f", "rawvideo", "-"]


def cuadros_rgb(ffmpeg, path, ancho, alto):
    proc = subprocess.Popen(decode_command(ffmpeg, path, ancho, alto),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    tam = ancho * alto * 3
    try:
        while True:
            buf = proc.stdout.read(tam)
            if len(buf) < tam:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(alto, ancho, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("referencia", help="la referencia (y4m o video) contra la que se mide")
    parser.add_argument("piezas", nargs="+", help="las piezas a medir")
    parser.add_argument("--ancho", type=int, default=1280)
    parser.add_argument("--alto", type=int, default=720)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args(argv)
    print("%-36s %11s  %9s  %9s" % ("pieza", "bytes", "banding", "oscuros"))
    for pieza in args.piezas:
        b, bo = banding(cuadros_rgb(args.ffmpeg, pieza, args.ancho, args.alto),
                        cuadros_rgb(args.ffmpeg, args.referencia, args.ancho, args.alto))
        print("%-36s %11d  %9.4f  %9.4f" % (os.path.basename(pieza), os.path.getsize(pieza), b, bo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
