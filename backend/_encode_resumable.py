#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Encode .ascl por tandas con checkpoint (entornos con limite de tiempo por llamada).
Llamar repetidamente hasta que imprima DONE. Checkpoint en /tmp."""
import argparse, os, sys, time, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoder, ascl_bundle


def save_ckpt(path, st):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(st, f, protocol=4)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input"); p.add_argument("out")
    p.add_argument("--cols", type=int, default=1920)
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--palette", default="global")
    p.add_argument("--mode", default="pixel")
    p.add_argument("--budget", type=float, default=30.0)
    a = p.parse_args()

    mode = encoder.MODE_NAMES[a.mode]
    ckpt = os.path.join("/tmp", os.path.basename(a.out) + ".ckpt.pkl")
    sw, sh = encoder.probe_size(a.input)
    cols, rows = encoder.compute_grid(sw, sh, a.cols, 0, mode, encoder.DEFAULT_CHAR_ASPECT)
    keyint = max(1, a.fps * 2)
    use_global = (a.palette == "global")

    if os.path.exists(ckpt):
        with open(ckpt, "rb") as f:
            st = pickle.load(f)
    else:
        allf = list(encoder.iter_video_frames(a.input, cols, rows, a.fps))
        nfr = len(allf)
        palette0 = None; pal_img = None
        if use_global:
            step = max(1, nfr // 12)
            sample = [allf[k][0] for k in range(0, nfr, step)]
            pal_img, palette0 = encoder.make_global_palette(sample, 256)
        st = {"next_idx": 0, "nfr": nfr, "cols": cols, "rows": rows,
              "palette0": palette0, "pal_img": pal_img, "prev_cells": None,
              "frames": [], "tags": {0: 0, 1: 0, 2: 0}}
        save_ckpt(ckpt, st)

    nfr = st["nfr"]; cols = st["cols"]; rows = st["rows"]
    pal_img = st["pal_img"]; palette0 = st["palette0"]
    t0 = time.time(); start_idx = st["next_idx"]; idx = 0
    prev_cells = st["prev_cells"]
    delta_allowed = use_global or (mode not in (3, 1))

    for rgb, gray in encoder.iter_video_frames(a.input, cols, rows, a.fps):
        if idx < start_idx:
            idx += 1; continue
        keyframe = (idx == 0) or (keyint > 0 and idx % keyint == 0)
        cells, palette, pal_count = encoder.frame_to_cells(
            rgb, gray, mode, 0, 256, a.palette, pal_img)
        if use_global:
            pal_count = 256 if idx == 0 else 0
            palette = palette0 if idx == 0 else None
        tag, payload = encoder.encode_frame(cells, prev_cells, mode, idx, keyframe,
                                            "auto", delta_allowed)
        st["tags"][tag] = st["tags"].get(tag, 0) + 1
        st["frames"].append({"tag": tag, "pal_count": pal_count,
                             "palette": palette, "payload": payload})
        prev_cells = cells
        idx += 1
        st["next_idx"] = idx
        st["prev_cells"] = prev_cells
        if time.time() - t0 > a.budget and idx < nfr:
            save_ckpt(ckpt, st)
            print("PROGRESS %d/%d (%.0f%%) en %.1fs" %
                  (idx, nfr, 100.0 * idx / nfr, time.time() - t0))
            return

    flags_extra = encoder.FLAG_PAL_GLOBAL if use_global else 0
    base = os.path.splitext(os.path.basename(a.out))[0]
    tmp_ascl = os.path.join("/tmp", base + ".ascl")
    total = encoder.write_ascl(tmp_ascl, mode, cols, rows, a.fps, "", st["frames"],
                               palette0, encoder.DEFAULT_CHAR_ASPECT, flags_extra)
    mp3 = os.path.join("/tmp", base + ".mp3")
    audio_ok = encoder.extract_audio(a.input, mp3)
    mp3 = mp3 if audio_ok and os.path.exists(mp3) else None
    tot, la, lau = ascl_bundle.pack(tmp_ascl, mp3, a.out)
    secs = nfr / float(a.fps) or 1
    print("DONE %s" % a.out)
    print("  pixel %dx%d @ %dfps - %d frames - paleta %s" %
          (cols, rows, a.fps, nfr, a.palette))
    print("  bundle %.1f KB (video %.1f + audio %.1f) ~%.1f KB/s  tags=%s" %
          (tot / 1024., la / 1024., lau / 1024., tot / 1024. / secs, st["tags"]))
    for x in (tmp_ascl, mp3, ckpt):
        try:
            if x and os.path.exists(x):
                os.remove(x)
        except OSError:
            pass


if __name__ == "__main__":
    main()
