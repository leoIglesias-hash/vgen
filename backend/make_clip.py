#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_clip.py - Un solo comando: video -> UN archivo .asclv (video ASCII + audio juntos).

Encodea el video a .ascl, extrae el audio a .mp3 y empaqueta ambos en outputs/<nombre>.asclv,
borrando los intermedios (salvo --keep). Asi cada clip queda en un unico archivo.

Uso:
    python make_clip.py ../inputs/mi-video.mp4
    python make_clip.py ../inputs/mi-video.mp4 --out ../outputs/promo.asclv --cols 320 --fps 15
    python make_clip.py ../inputs/foto.jpg --image     # tambien imagen (sin audio)

Defaults (decididos con el usuario): modo pixel, 320 columnas, 15 fps, paleta global (DELTA).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoder
import ascl_bundle


def main(argv=None):
    p = argparse.ArgumentParser(description="video -> .asclv (un solo archivo)")
    p.add_argument("input")
    p.add_argument("--out", default=None, help="ruta .asclv (default ../outputs/<nombre>.asclv)")
    p.add_argument("--mode", choices=list(encoder.MODE_NAMES), default="pixel")
    p.add_argument("--profile", "--quality-profile", choices=encoder.QUALITY_PROFILE_NAMES,
                   default="custom", dest="quality_profile",
                   help="custom/detail/balanced/color; los overrides manuales prevalecen")
    p.add_argument("--cols", type=int, default=None,
                   help="columnas; default 320 o valor del perfil")
    p.add_argument("--rows", type=int, default=0, help="0 = filas automaticas")
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--palette", choices=["per-frame", "global"], default="global")
    p.add_argument("--threshold", type=int, default=0, help="T perceptual RGB (0=lossless); solo pixel+global")
    p.add_argument("--ramp", default="short")
    p.add_argument("--palette-size", type=int, default=None, dest="pal_size",
                   help="1..256; default 256 o valor del perfil")
    p.add_argument("--bake-smoothing", choices=encoder.BAKE_SMOOTHING_MODES, default="none",
                   help="suavizado offline antes de cuantizar")
    p.add_argument("--reconstruction", choices=encoder.RECONSTRUCTION_MODES, default="nearest",
                   help="filtro de presentacion recomendado al player")
    p.add_argument("--image", action="store_true", help="forzar modo imagen (sin audio)")
    p.add_argument("--keep", action="store_true", help="conservar los .ascl/.mp3 intermedios")
    args = p.parse_args(argv)
    args.cols, args.pal_size = encoder.resolve_quality_options(
        args.quality_profile, args.cols, args.pal_size, default_cols=320)
    try:
        encoder.validate_encode_options(args.mode, args.cols, args.rows, args.fps,
                                        args.pal_size, 0.5, args.palette,
                                        args.bake_smoothing, args.reconstruction)
    except ValueError as exc:
        p.error(str(exc))

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.abspath(os.path.join(here, "..", "outputs"))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.input))[0]
    out = args.out or os.path.join(out_dir, stem + ".asclv")
    tmp_ascl = os.path.splitext(out)[0] + ".ascl"
    keyint = max(1, args.fps * 2)

    ext = os.path.splitext(args.input)[1].lower()
    is_video = (not args.image) and (ext in encoder.VIDEO_EXTS)

    if is_video:
        info = encoder.encode_video(args.input, tmp_ascl, args.mode, args.cols, args.rows,
                                    args.fps, args.pal_size, args.ramp, 0.5, "auto",
                                    args.palette, keyint, with_audio=True,
                                    threshold=args.threshold,
                                    bake_smoothing=args.bake_smoothing,
                                    reconstruction=args.reconstruction,
                                    quality_profile=args.quality_profile)
        mp3 = os.path.splitext(tmp_ascl)[0] + ".mp3"
        mp3 = mp3 if (info.get("audio") and os.path.exists(mp3)) else None
        total, la, lau = ascl_bundle.pack(tmp_ascl, mp3, out)
        secs = info["n_frames"] / float(info["fps"]) or 1
        print("OK %s" % out)
        print("  %s %dx%d @ %dfps - %d frames - paleta %s" %
              (info["mode"], info["cols"], info["rows"], info["fps"],
               info["n_frames"], info["palette_mode"]))
        print("  calidad: perfil %s, hasta %d colores, bake %s, reconstruccion %s, flags 0x%02X" %
              (info["quality_profile"], info["pal_size"], info["bake_smoothing"],
               info["reconstruction"], info["flags"]))
        print("  bundle: %.1f KB  (video %.1f KB + audio %.1f KB)  ~%.1f KB/s" %
              (total/1024.0, la/1024.0, lau/1024.0, total/1024.0/secs))
        if not args.keep:
            for x in (tmp_ascl, mp3):
                if x and os.path.exists(x):
                    os.remove(x)
    else:
        info = encoder.encode_image(args.input, tmp_ascl, args.mode, args.cols, args.rows,
                                    args.fps, args.pal_size, args.ramp, 0.5, "auto", "per-frame",
                                    bake_smoothing=args.bake_smoothing,
                                    reconstruction=args.reconstruction,
                                    quality_profile=args.quality_profile)
        total, la, lau = ascl_bundle.pack(tmp_ascl, None, out)
        print("OK %s  (imagen, %s %dx%d, %.1f KB)" %
              (out, info["mode"], info["cols"], info["rows"], total/1024.0))
        print("  calidad: perfil %s, hasta %d colores, bake %s, reconstruccion %s, flags 0x%02X" %
              (info["quality_profile"], info["pal_size"], info["bake_smoothing"],
               info["reconstruction"], info["flags"]))
        if not args.keep and os.path.exists(tmp_ascl):
            os.remove(tmp_ascl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
