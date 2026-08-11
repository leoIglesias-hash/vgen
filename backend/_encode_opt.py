#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Encoder optimizado A+B con checkpoint reanudable.
 A) DELTA con mascara de bits (tag 3) ademas del DELTA por indices (tag 2): el encoder
    elige el candidato mas chico por frame (RAW/ZLIB/DELTA-idx/DELTA-mask).
 B) Umbral perceptual T (Euclidiano RGB via paleta): un pixel se considera "sin cambio"
    si la distancia de color a lo ya emitido es <= T -> se mantiene el valor previo.
    T=0 => lossless. Se compara contra lo EMITIDO (no contra la fuente) para acotar drift.
Solo modo pixel (1 byte/celda). Checkpoint en /tmp. Llamar hasta que imprima DONE.
"""
import argparse, os, sys, time, pickle, zlib, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoder, ascl_bundle

TAG_RAW, TAG_ZLIB, TAG_DELTA, TAG_DELTA_MASK = 0, 1, 2, 3


def save_ckpt(path, st):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(st, f, protocol=4); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def build_candidates(emitted, prev_emitted, keyframe):
    planes = emitted.tobytes()
    full_z = zlib.compress(planes, 9)
    cands = [(TAG_ZLIB, full_z)] if len(full_z) < len(planes) else [(TAG_RAW, planes)]
    N = emitted.shape[0]
    if (not keyframe) and prev_emitted is not None:
        changed = emitted != prev_emitted
        kcnt = int(changed.sum())
        if kcnt < N:
            vals = emitted[changed].tobytes()
            ci = np.nonzero(changed)[0].astype("<u4")
            cands.append((TAG_DELTA, zlib.compress(ci.tobytes() + vals, 9)))
            mask = np.packbits(changed.astype(np.uint8), bitorder="little")
            cands.append((TAG_DELTA_MASK, zlib.compress(mask.tobytes() + vals, 9)))
    tag, payload = min(cands, key=lambda c: len(c[1]))
    if len(planes) < len(payload):
        tag, payload = TAG_RAW, planes
    return tag, payload


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input"); p.add_argument("out")
    p.add_argument("--cols", type=int, default=1920)
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--threshold", type=int, default=0, help="T Euclidiano RGB (0=lossless)")
    p.add_argument("--budget", type=float, default=30.0)
    a = p.parse_args()

    mode = encoder.MODE_PIXEL
    T2 = a.threshold * a.threshold
    ckpt = os.path.join("/tmp", os.path.basename(a.out) + ".ckpt.pkl")
    sw, sh = encoder.probe_size(a.input)
    cols, rows = encoder.compute_grid(sw, sh, a.cols, 0, mode, encoder.DEFAULT_CHAR_ASPECT)
    keyint = max(1, a.fps * 2)

    if os.path.exists(ckpt):
        with open(ckpt, "rb") as f:
            st = pickle.load(f)
    else:
        allf = list(encoder.iter_video_frames(a.input, cols, rows, a.fps))
        nfr = len(allf)
        step = max(1, nfr // 12)
        sample = [allf[k][0] for k in range(0, nfr, step)]
        pal_img, palette0 = encoder.make_global_palette(sample, 256)
        st = {"next_idx": 0, "nfr": nfr, "cols": cols, "rows": rows,
              "palette0": palette0, "pal_img": pal_img, "prev_emitted": None,
              "frames": [], "tags": {0: 0, 1: 0, 2: 0, 3: 0},
              "sqerr": 0.0, "npix": 0}
        save_ckpt(ckpt, st)

    nfr = st["nfr"]; cols = st["cols"]; rows = st["rows"]
    pal_img = st["pal_img"]; palette0 = st["palette0"]
    pal16 = palette0.astype(np.int16)
    prev_emitted = st["prev_emitted"]
    start_idx = st["next_idx"]; idx = 0
    t0 = time.time()

    for rgb, gray in encoder.iter_video_frames(a.input, cols, rows, a.fps):
        if idx < start_idx:
            idx += 1; continue
        keyframe = (idx == 0) or (idx % keyint == 0)
        cells, _pal, _pc = encoder.frame_to_cells(rgb, gray, mode, 0, 256, "global", pal_img)
        cur = cells[:, 0]                              # indices uint8 (N,)
        if keyframe or prev_emitted is None or T2 == 0:
            emitted = cur.copy()
        else:
            a3 = pal16[cur].astype(np.int32); b3 = pal16[prev_emitted].astype(np.int32)
            d = a3 - b3
            d2 = np.einsum("ij,ij->i", d, d)   # int32: evita overflow del cuadrado
            upd = d2 > T2
            emitted = prev_emitted.copy()
            emitted[upd] = cur[upd]
        # calidad vs fuente cuantizada (cur)
        ce = pal16[emitted].astype(np.int32); ct = pal16[cur].astype(np.int32)
        df = ce - ct
        st["sqerr"] += float(np.einsum("ij,ij->i", df, df).sum())
        st["npix"] += emitted.shape[0]

        tag, payload = build_candidates(emitted, prev_emitted, keyframe)
        st["tags"][tag] = st["tags"].get(tag, 0) + 1
        st["frames"].append({"tag": tag,
                             "pal_count": 256 if idx == 0 else 0,
                             "palette": palette0 if idx == 0 else None,
                             "payload": payload})
        prev_emitted = emitted
        idx += 1
        st["next_idx"] = idx
        st["prev_emitted"] = prev_emitted
        if time.time() - t0 > a.budget and idx < nfr:
            save_ckpt(ckpt, st)
            print("PROGRESS %d/%d (%.0f%%) en %.1fs" % (idx, nfr, 100.0*idx/nfr, time.time()-t0))
            return

    base = os.path.splitext(os.path.basename(a.out))[0]
    tmp_ascl = os.path.join("/tmp", base + ".ascl")
    total = encoder.write_ascl(tmp_ascl, mode, cols, rows, a.fps, "", st["frames"],
                               palette0, encoder.DEFAULT_CHAR_ASPECT, encoder.FLAG_PAL_GLOBAL)
    mp3 = os.path.join("/tmp", base + ".mp3")
    audio_ok = encoder.extract_audio(a.input, mp3)
    mp3 = mp3 if audio_ok and os.path.exists(mp3) else None
    tot, la, lau = ascl_bundle.pack(tmp_ascl, mp3, a.out)
    secs = nfr / float(a.fps) or 1
    mse = st["sqerr"] / max(1, st["npix"] * 3)
    psnr = float("inf") if mse <= 0 else 10.0 * math.log10((255.0**2) / mse)
    print("DONE %s" % a.out)
    print("  pixel %dx%d @ %dfps  T=%d  %d frames" % (cols, rows, a.fps, a.threshold, nfr))
    print("  bundle %.1f KB (video %.1f + audio %.1f) ~%.1f KB/s" %
          (tot/1024., la/1024., lau/1024., tot/1024./secs))
    print("  tags RAW/ZLIB/DELTA/MASK = %d/%d/%d/%d" %
          (st["tags"][0], st["tags"][1], st["tags"][2], st["tags"][3]))
    print("  PSNR vs fuente cuantizada = %s dB (inf = lossless)" %
          ("inf" if math.isinf(psnr) else "%.2f" % psnr))
    for x in (tmp_ascl, mp3, ckpt):
        try:
            if x and os.path.exists(x): os.remove(x)
        except OSError:
            pass


if __name__ == "__main__":
    main()
