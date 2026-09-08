#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cuantizar_y4m.py - H-27: la referencia y4m llevada a una PALETA ADAPTATIVA de
N colores (512, 1024...) ANTES de codificar.

Por que existe: en la caja (Chromium 70, decodificador VP9 por hardware) el
pack v2 -la fuente a 1280@20- «se traba», y el de 256 colores (v1) no. El
operador (2026-09-08) pidio dos pruebas: 15 fps como v1, y una paleta de 512
colores («256 no porque ya sabemos como se ve»). Esta es la segunda.

Lo que hace, con las mismas piezas que la paleta de v1 (kmeans-oklab del
encoder ASCILINE), pero SIN pasar por el master indexado:

  1. muestrea pixeles de la referencia (cuadros repartidos, posiciones
     repartidas), los lleva a Oklab y corre K-means con K = colores, con la
     inicializacion determinista del backend (`_initial_centers`);
  2. arma una tabla 64x64x64 (6 bits por canal) que dice, para cada celda RGB,
     que color de la paleta le queda mas cerca EN OKLAB; con 512 colores la
     paleta es mucho mas gruesa que 4/255, asi que la tabla no agrega error
     visible y evita buscar el mas cercano pixel por pixel;
  3. pasa cada cuadro: Y'CbCr 4:2:0 (709 tv, que es como la escribio la
     referencia) -> RGB -> paleta -> Y'CbCr 4:2:0, y escribe otro y4m con la
     MISMA cabecera. La conversion es la de 709 en rango limitado, hecha aca
     en numpy para no depender de OpenCV (que usa 601).

El resultado sigue siendo un video de 24 bits: el <video> no sabe de paletas.
Lo que cambia son los BYTES que el encoder tiene que gastar (menos colores =
zonas planas = menos bits al mismo crf), que es lo unico que puede aliviar a
un decodificador de hardware. La hipotesis se prueba en la caja, no aca.

Determinismo: numpy en float32/float64 sobre la misma maquina da los mismos
bytes; entre CPUs no se afirma nada todavia (P-010 vale tambien para esto).

Uso:
  python tools/cuantizar_y4m.py work/ref.y4m work/ref-c512.y4m --colores 512
"""

import argparse
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import perceptual_palette  # noqa: E402

FRAME_HEADER = b"FRAME\n"
BITS = 6                      # niveles por canal de la tabla: 64^3 = 262.144 celdas
NIVELES = 1 << BITS

# BT.709, rango limitado (tv): Y' 16..235, Cb/Cr 16..240. Es la matriz que la
# referencia declara (`out_color_matrix=bt709:out_range=tv`), asi que la ida y
# la vuelta se hacen con la misma.
KR, KB = 0.2126, 0.0722
KG = 1.0 - KR - KB
ESCALA_Y = 255.0 / 219.0
ESCALA_C = 255.0 / 224.0


# --------------------------------------------------------------------------
# y4m

def cabecera_y4m(path):
    """(linea de cabecera en bytes, ancho, alto, cuadros). Solo 4:2:0 de 8
    bits y dimensiones pares: otra cosa es un error, no una suposicion."""
    with open(path, "rb") as stream:
        line = stream.readline()
    fields = line.decode("ascii", "replace").split()
    if not fields or fields[0] != "YUV4MPEG2":
        raise ValueError("no es un y4m: %s" % path)
    width = height = None
    chroma = "420"
    for token in fields[1:]:
        if token[0] == "W":
            width = int(token[1:])
        elif token[0] == "H":
            height = int(token[1:])
        elif token[0] == "C":
            chroma = token[1:]
    if not width or not height:
        raise ValueError("cabecera y4m incompleta: %r" % line)
    if not chroma.startswith("420") or "p10" in chroma or "p12" in chroma:
        raise ValueError("la referencia tiene que ser 4:2:0 de 8 bits, no C%s" % chroma)
    if width % 2 or height % 2:
        raise ValueError("4:2:0 necesita ancho y alto pares, no %dx%d" % (width, height))
    frame_bytes = len(FRAME_HEADER) + width * height * 3 // 2
    frames = (os.path.getsize(path) - len(line)) // frame_bytes
    return line, width, height, frames


def planos(buffer, width, height):
    """Los tres planos de un cuadro I420: Y (h, w), Cb y Cr (h/2, w/2)."""
    luma = width * height
    croma = (width // 2) * (height // 2)
    data = np.frombuffer(buffer, dtype=np.uint8)
    if len(data) != luma + 2 * croma:
        raise ValueError("cuadro incompleto: %d bytes, se esperaban %d"
                         % (len(data), luma + 2 * croma))
    return (data[:luma].reshape(height, width),
            data[luma:luma + croma].reshape(height // 2, width // 2),
            data[luma + croma:].reshape(height // 2, width // 2))


def leer_cuadro(stream, width, height):
    """El siguiente cuadro del y4m como (Y, Cb, Cr), o None al final."""
    head = stream.read(len(FRAME_HEADER))
    if not head:
        return None
    if head != FRAME_HEADER:
        raise ValueError("se esperaba FRAME y llego %r" % head)
    return planos(stream.read(width * height * 3 // 2), width, height)


# --------------------------------------------------------------------------
# Color: 709 tv, ida y vuelta.

def yuv_a_rgb(y, cb, cr):
    """I420 (709 tv) -> RGB uint8 (h, w, 3). El croma se repite 2x2 (vecino
    mas cercano): la paleta se elige por color, no por borde."""
    luma = (y.astype(np.float32) - 16.0) * ESCALA_Y
    u = (np.repeat(np.repeat(cb, 2, axis=0), 2, axis=1).astype(np.float32) - 128.0) * ESCALA_C
    v = (np.repeat(np.repeat(cr, 2, axis=0), 2, axis=1).astype(np.float32) - 128.0) * ESCALA_C
    r = luma + 2.0 * (1.0 - KR) * v
    g = luma - (2.0 * KB * (1.0 - KB) / KG) * u - (2.0 * KR * (1.0 - KR) / KG) * v
    b = luma + 2.0 * (1.0 - KB) * u
    rgb = np.stack((r, g, b), axis=-1)
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def rgb_a_yuv(rgb):
    """RGB uint8 (h, w, 3) -> I420 (709 tv). El croma se promedia 2x2."""
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    luma = KR * r + KG * g + KB * b
    u = (b - luma) / (2.0 * (1.0 - KB))
    v = (r - luma) / (2.0 * (1.0 - KR))
    height, width = luma.shape
    y = np.clip(np.rint(16.0 + luma / ESCALA_Y), 0, 255).astype(np.uint8)
    cb = u.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
    cr = v.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
    cb = np.clip(np.rint(128.0 + cb / ESCALA_C), 0, 255).astype(np.uint8)
    cr = np.clip(np.rint(128.0 + cr / ESCALA_C), 0, 255).astype(np.uint8)
    return y, cb, cr


# --------------------------------------------------------------------------
# La paleta.

def mas_cercano(lab, centros, chunk=8192, con_distancia=False):
    """Indice (int32) del centro mas cercano a cada fila de `lab`. Misma
    formula que `perceptual_palette._nearest_indices`, que se queda en 256."""
    values = np.asarray(lab, dtype=np.float64).reshape(-1, 3)
    palette = np.asarray(centros, dtype=np.float64).reshape(-1, 3)
    result = np.empty(len(values), dtype=np.int32)
    minimum = np.empty(len(values), dtype=np.float64) if con_distancia else None
    cuadrados = np.sum(palette * palette, axis=1)[None, :]
    for start in range(0, len(values), int(chunk)):
        stop = min(start + int(chunk), len(values))
        current = values[start:stop]
        distance = -2.0 * np.dot(current, palette.T)
        distance += np.sum(current * current, axis=1)[:, None]
        distance += cuadrados
        np.maximum(distance, 0.0, out=distance)
        indices = np.argmin(distance, axis=1)
        result[start:stop] = indices
        if con_distancia:
            minimum[start:stop] = distance[np.arange(stop - start), indices]
    if con_distancia:
        return result, minimum
    return result


def paleta_oklab(muestras_rgb, colores, iteraciones=20, tolerancia=1e-5):
    """K-means en Oklab sobre muestras RGB uint8 (M, 3): devuelve (centros en
    Oklab float64 (K, 3), etiquetas de las muestras). Determinista: la
    inicializacion es la del backend (farthest-point), sin azar."""
    colores = int(colores)
    if colores < 2:
        raise ValueError("colores tiene que ser >= 2")
    samples = np.asarray(muestras_rgb, dtype=np.uint8).reshape(-1, 3)
    if len(samples) < colores:
        samples = np.resize(samples, (colores, 3))
    lab = perceptual_palette.srgb_to_oklab(samples)
    weights = np.ones(len(lab), dtype=np.float64)
    centers = perceptual_palette._initial_centers(lab, weights, colores, 4096)
    labels = np.zeros(len(lab), dtype=np.int32)
    for _ in range(int(iteraciones)):
        labels, minimum = mas_cercano(lab, centers, con_distancia=True)
        counts = np.bincount(labels, minlength=colores)
        updated = centers.copy()
        occupied = counts > 0
        for channel in range(3):
            sums = np.bincount(labels, weights=lab[:, channel], minlength=colores)
            updated[occupied, channel] = sums[occupied] / counts[occupied]
        empty = np.flatnonzero(~occupied)
        if len(empty):
            candidates = np.argsort(-minimum, kind="mergesort")
            for offset, center_index in enumerate(empty):
                updated[center_index] = lab[candidates[min(offset, len(candidates) - 1)]]
        shift = float(np.max(np.sqrt(np.sum((updated - centers) ** 2, axis=1))))
        centers = updated
        if shift <= float(tolerancia):
            break
    return centers, labels


def tabla_de(centros_lab):
    """La tabla RGB (NIVELES^3, 3) uint8: cada celda de 6 bits por canal ->
    el color de la paleta mas cercano en Oklab. Indice = r6 << 12 | g6 << 6 | b6."""
    paso = 255.0 / (NIVELES - 1)
    niveles = np.clip(np.rint(np.arange(NIVELES) * paso), 0, 255).astype(np.uint8)
    r, g, b = np.meshgrid(niveles, niveles, niveles, indexing="ij")
    celdas = np.stack((r, g, b), axis=-1).reshape(-1, 3)
    indices = mas_cercano(perceptual_palette.srgb_to_oklab(celdas), centros_lab)
    paleta_rgb = perceptual_palette.oklab_to_srgb(np.asarray(centros_lab))
    return paleta_rgb[indices]


def aplicar(rgb, tabla):
    """RGB uint8 (h, w, 3) -> el RGB de la paleta, via la tabla."""
    corr = 8 - BITS
    r = rgb[..., 0].astype(np.int32) >> corr
    g = rgb[..., 1].astype(np.int32) >> corr
    b = rgb[..., 2].astype(np.int32) >> corr
    return tabla[(r << (2 * BITS)) | (g << BITS) | b]


def muestrear(path, width, height, frames, cuadros=32, pixeles=240000):
    """Pixeles RGB de hasta `cuadros` cuadros repartidos, posiciones
    repartidas, hasta `pixeles` en total."""
    elegidos = np.unique(np.linspace(0, max(frames - 1, 0), min(max(frames, 1), cuadros))
                         .astype(np.int64))
    por_cuadro = max(int(pixeles) // max(len(elegidos), 1), 1)
    frame_bytes = len(FRAME_HEADER) + width * height * 3 // 2
    partes = []
    with open(path, "rb") as stream:
        offset = len(stream.readline())
        for index in elegidos:
            stream.seek(offset + int(index) * frame_bytes)
            cuadro = leer_cuadro(stream, width, height)
            if cuadro is None:
                break
            rgb = yuv_a_rgb(*cuadro).reshape(-1, 3)
            posiciones = np.linspace(0, len(rgb) - 1, min(por_cuadro, len(rgb)),
                                     dtype=np.int64)
            partes.append(rgb[posiciones])
    if not partes:
        raise ValueError("la referencia no tiene cuadros: %s" % path)
    return np.concatenate(partes, axis=0)


# --------------------------------------------------------------------------

def cuantizar(entrada, salida, colores, log=None):
    """Escribe `salida` = `entrada` con la paleta adaptativa de `colores`.
    Devuelve un resumen (colores, usados en las muestras, cuadros, segundos)."""
    log = log or (lambda message: None)
    started = time.time()
    line, width, height, frames = cabecera_y4m(entrada)
    muestras = muestrear(entrada, width, height, frames)
    centros, etiquetas = paleta_oklab(muestras, colores)
    usados = int(len(np.unique(etiquetas)))
    tabla = tabla_de(centros)
    log("  paleta %d colores (Oklab, %d muestras, %d usados) en %.0f s"
        % (colores, len(muestras), usados, time.time() - started))
    escritos = 0
    with open(entrada, "rb") as origen, open(salida, "wb") as destino:
        origen.readline()
        destino.write(line)
        while True:
            cuadro = leer_cuadro(origen, width, height)
            if cuadro is None:
                break
            y, cb, cr = rgb_a_yuv(aplicar(yuv_a_rgb(*cuadro), tabla))
            destino.write(FRAME_HEADER)
            destino.write(y.tobytes())
            destino.write(cb.tobytes())
            destino.write(cr.tobytes())
            escritos += 1
    return {"colores": int(colores), "usados": usados, "muestras": int(len(muestras)),
            "cuadros": escritos, "segundos": time.time() - started,
            "paleta_rgb": perceptual_palette.oklab_to_srgb(centros)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("entrada", help="la referencia y4m (4:2:0, 8 bits)")
    parser.add_argument("salida", help="el y4m con la paleta")
    parser.add_argument("--colores", type=int, default=512)
    args = parser.parse_args(argv)
    resumen = cuantizar(args.entrada, args.salida, args.colores,
                        log=lambda message: print(message, flush=True))
    print("%d cuadros, %d colores (%d usados), %.0f s" % (
        resumen["cuadros"], resumen["colores"], resumen["usados"], resumen["segundos"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
