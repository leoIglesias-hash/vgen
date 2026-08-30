#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P-03 — Medicion de referencia de un artefacto .asclv o .ascl.

Imprime una fila Markdown determinista con bytes, distribucion de tags,
keyframes, cadena delta maxima y SHA-256. Con --source calcula ademas
PSNR RGB y error Oklab medio contra el video original, mas las dos
columnas de E-24 que los promedios por pixel no ven:

- ``err_temporal``: magnitud Oklab media de la diferencia entre el delta
  temporal decodificado y el de la fuente (frame a frame). El arrastre del
  trellis temporal (celdas que se quedan en el valor viejo mientras la
  fuente se mueve) y el flicker aparecen aca, no en el PSNR.
- ``proxy_banding``: gradiente Oklab-L EXTRA del decodificado sobre zonas
  donde la fuente es suave, medido tras promediar bloques 2x2. El tramado
  del dither se anula en el promedio; el contorno de un plateau (banding)
  sobrevive. Por eso esta columna, a diferencia de ``err_oklab_medio``,
  NO castiga al dither por romper mesetas.

Uso:
    python tools/bench_ref.py outputs/synthetic.baseline.asclv
    python tools/bench_ref.py outputs/clip.asclv --source inputs/video.mp4
    python tools/bench_ref.py a.asclv --header    # imprime el encabezado de tabla
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))

import numpy as np  # noqa: E402

import ascl_bundle  # noqa: E402
import ascl_v2  # noqa: E402

TAG_NAMES = {
    0: "RAW", 1: "ZLIB", 2: "DELTA", 3: "DELTA_MASK",
    4: "RKEY_RAW", 5: "RKEY_ZLIB", 6: "RDELTA_RAW", 7: "RDELTA_ZLIB",
    8: "PKEY", 9: "PDELTA",
}

COLUMNS = ("archivo", "bytes_ascl", "bytes_asclv", "bytes_celda_frame",
           "frames", "keyframes", "cadena_delta_max", "tags",
           "psnr_rgb_db", "err_oklab_medio", "err_temporal", "proxy_banding",
           "sha256")

# E-24: umbral de "fuente suave" para el proxy de banding, en unidades L de
# Oklab (0..1) por paso de bloque 2x2. Un paso de gris adyacente de 8 bits
# mide ~0,003 L; un borde real de imagen esta muy por encima de 0,01.
BANDING_SMOOTH_T = 0.01
BANDING_BLOCK = 2


def temporal_error_oklab(lab_dec, lab_dec_prev, lab_src, lab_src_prev):
    """Magnitud Oklab media de (delta temporal decodificado - delta fuente).

    Un desplazamiento constante entre decodificado y fuente se cancela: solo
    cuenta el MOVIMIENTO mal reproducido (arrastre o flicker).
    """
    diff = ((np.asarray(lab_dec, dtype=np.float64)
             - np.asarray(lab_dec_prev, dtype=np.float64))
            - (np.asarray(lab_src, dtype=np.float64)
               - np.asarray(lab_src_prev, dtype=np.float64)))
    return float(np.mean(np.sqrt(np.sum(diff * diff, axis=-1))))


def _block_mean(plane, block=BANDING_BLOCK):
    plane = np.asarray(plane, dtype=np.float64)
    rows = plane.shape[0] // block * block
    cols = plane.shape[1] // block * block
    if not rows or not cols:
        return plane[:0, :0]
    return plane[:rows, :cols].reshape(rows // block, block,
                                       cols // block, block).mean(axis=(1, 3))


def banding_stats(l_dec, l_src, smooth_t=BANDING_SMOOTH_T,
                  block=BANDING_BLOCK):
    """(suma de gradiente extra, posiciones medidas) de un plano L Oklab.

    Se promedia en bloques 2x2 antes de derivar: el patron del dither se
    anula, el escalon de un plateau persiste. Solo se mira donde la fuente
    es suave (|gradiente| <= smooth_t): un borde real queda fuera aunque el
    decodificado lo exagere.
    """
    dec = _block_mean(l_dec, block)
    src = _block_mean(l_src, block)
    total = 0.0
    positions = 0
    for axis in (0, 1):
        grad_dec = np.abs(np.diff(dec, axis=axis))
        grad_src = np.abs(np.diff(src, axis=axis))
        mask = grad_src <= smooth_t
        positions += int(mask.sum())
        total += float(np.clip(grad_dec - grad_src, 0.0, None)[mask].sum())
    return total, positions


def _iter_frames(ascl):
    version = ascl[4]
    if version == ascl_v2.VERSION_V2:
        header = ascl_v2._header_fields(ascl, ascl_v2.VERSION_V2)
        frames = ascl_v2.iter_decoded_v2(ascl)
    elif version == ascl_v2.VERSION_V1:
        header = ascl_v2._header_fields(ascl, ascl_v2.VERSION_V1)
        ascl_v2._validate_crc(ascl, header)
        frames = ascl_v2._frame_blocks_v1(ascl, header)
    else:
        raise SystemExit("version ASCL desconocida: %d" % version)
    return header, frames


def _load(path):
    with open(path, "rb") as handle:
        magic = handle.read(8)
    if magic.startswith(b"ASCLVID"):
        ascl, _audio, _version = ascl_bundle.read_parts_info(path)
        return bytes(ascl), os.path.getsize(path)
    with open(path, "rb") as handle:
        ascl = handle.read()
    return ascl, len(ascl)


def _quality_metrics(frames_rgb, source_path, header):
    import perceptual_palette
    sys.path.insert(0, os.path.dirname(os.path.abspath(perceptual_palette.__file__)))
    import encoder as enc
    src = list(enc.iter_video_frames(source_path, header["cols"], header["rows"],
                                     header["fps"]))
    count = min(len(src), len(frames_rgb))
    if not count:
        return None, None, None, None
    mse_total = 0.0
    oklab_total = 0.0
    temporal_total = 0.0
    band_sum = 0.0
    band_positions = 0
    prev_dec = prev_src = None
    for i in range(count):
        a = frames_rgb[i].astype(np.float64)
        b = src[i][0].astype(np.float64)
        mse_total += float(np.mean((a - b) ** 2))
        la = perceptual_palette.srgb_to_oklab(
            frames_rgb[i].reshape(-1, 3).astype(np.uint8))
        lb = perceptual_palette.srgb_to_oklab(
            src[i][0].reshape(-1, 3).astype(np.uint8))
        oklab_total += float(np.mean(np.sqrt(np.sum((la - lb) ** 2, axis=1))))
        if prev_dec is not None:
            temporal_total += temporal_error_oklab(la, prev_dec, lb, prev_src)
        rows, cols = frames_rgb[i].shape[:2]
        extra, positions = banding_stats(la[:, 0].reshape(rows, cols),
                                         lb[:, 0].reshape(rows, cols))
        band_sum += extra
        band_positions += positions
        prev_dec, prev_src = la, lb
    mse = mse_total / count
    psnr = float("inf") if mse == 0 else 10.0 * np.log10(255.0 ** 2 / mse)
    temporal = (temporal_total / (count - 1)) if count > 1 else None
    banding = (band_sum / band_positions) if band_positions else 0.0
    return psnr, oklab_total / count, temporal, banding


def measure(path, source=None):
    ascl, total = _load(path)
    header, frames = _iter_frames(ascl)
    n = header["cols"] * header["rows"]
    tag_counts = {}
    keyframes = 0
    chain = 0
    chain_max = 0
    frames_rgb = [] if source else None
    for frame in frames:
        tag = frame["tag"]
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if frame["keyframe"]:
            keyframes += 1
            chain = 0
        else:
            chain += 1
            if chain > chain_max:
                chain_max = chain
        if frames_rgb is not None:
            cells = np.asarray(frame["cells"]).reshape(-1)
            palette = np.frombuffer(frame.get("palette") or b"",
                                    dtype=np.uint8)
            if not palette.size:
                palette = measure._last_palette
            measure._last_palette = palette
            pal = palette.reshape(-1, 3)
            frames_rgb.append(pal[cells].reshape(header["rows"],
                                                 header["cols"], 3))
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    tags = ";".join("%s:%d" % (TAG_NAMES.get(t, str(t)), c)
                    for t, c in sorted(tag_counts.items()))
    psnr = oklab = temporal = banding = None
    if source:
        psnr, oklab, temporal, banding = _quality_metrics(
            frames_rgb, source, header)
    per_cell = float(len(ascl)) / (n * max(1, header["n_frames"]))
    return {
        "archivo": os.path.basename(path),
        "bytes_ascl": len(ascl),
        "bytes_asclv": total,
        "bytes_celda_frame": "%.4f" % per_cell,
        "frames": header["n_frames"],
        "keyframes": keyframes,
        "cadena_delta_max": chain_max,
        "tags": tags,
        "psnr_rgb_db": ("%.2f" % psnr) if psnr is not None else "-",
        "err_oklab_medio": ("%.5f" % oklab) if oklab is not None else "-",
        "err_temporal": ("%.5f" % temporal) if temporal is not None else "-",
        "proxy_banding": ("%.6f" % banding) if banding is not None else "-",
        "sha256": digest,
    }


measure._last_palette = np.zeros((0,), dtype=np.uint8)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--source", default=None,
                        help="video original para PSNR/Oklab")
    parser.add_argument("--header", action="store_true",
                        help="imprime tambien el encabezado de la tabla")
    args = parser.parse_args(argv)
    row = measure(args.path, args.source)
    if args.header:
        print("| " + " | ".join(COLUMNS) + " |")
        print("|" + "---|" * len(COLUMNS))
    print("| " + " | ".join(str(row[c]) for c in COLUMNS) + " |")


if __name__ == "__main__":
    main()
