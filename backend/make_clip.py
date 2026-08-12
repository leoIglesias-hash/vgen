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
                   help="perfil de grilla/color; overrides manuales prevalecen")
    p.add_argument("--cols", type=int, default=None,
                   help="columnas; default 320 o valor del perfil")
    p.add_argument("--rows", type=int, default=0, help="0 = filas automaticas")
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--palette", choices=encoder.PALETTE_MODES, default="global")
    p.add_argument("--palette-algorithm", choices=encoder.PALETTE_ALGORITHMS,
                   default="kmeans-rgb",
                   help="constructor offline (default kmeans-rgb, mejor fidelidad)")
    p.add_argument("--palette-block-frames", type=int, default=0,
                   help="frames por paleta en modo block (0 = fps*2)")
    p.add_argument("--adaptive-min-frames", type=int, default=5,
                   help="minimo antes de cortar por deriva de color")
    p.add_argument("--adaptive-max-frames", type=int, default=10,
                   help="maximo de frames por paleta adaptativa")
    p.add_argument("--adaptive-change-threshold", type=float, default=0.20,
                   help="umbral Oklab de deriva gradual")
    p.add_argument("--adaptive-hard-cut-threshold", type=float, default=0.58,
                   help="umbral entre frames para hard cut")
    p.add_argument("--adaptive-stability-max", "--temporal-stability-max",
                   type=float, default=0.25, dest="adaptive_stability_max",
                   help="retencion maxima de la paleta anterior")
    p.add_argument("--perceptual-lut-bits", type=int, default=0,
                   help="0=Oklab exacto; 3..7=LUT de cuantizacion offline")
    p.add_argument("--threshold", type=int, default=0,
                   help="T perceptual RGB (0=lossless); pixel con paleta global/block")
    p.add_argument("--ramp", default="short")
    p.add_argument("--palette-size", type=int, default=None, dest="pal_size",
                   help="1..256; default 256 o valor del perfil")
    p.add_argument("--bake-smoothing", choices=encoder.BAKE_SMOOTHING_MODES, default="none",
                   help="suavizado offline antes de cuantizar")
    p.add_argument("--reconstruction", choices=encoder.RECONSTRUCTION_MODES, default="nearest",
                   help="filtro de presentacion recomendado al player")
    p.add_argument("--dither", choices=encoder.DITHER_MODES, default="off",
                   help="tramado selectivo offline para mode pixel")
    p.add_argument("--dither-matrix", choices=encoder.DITHER_MATRIX_SIZES,
                   type=int, default=4,
                   help="Bayer 2 compacto o Bayer 4 equilibrado")
    p.add_argument("--dither-budget", "--dither-max-changed-fraction", type=float,
                   default=encoder.selective_dither.DEFAULT_MAX_CHANGED_FRACTION,
                   dest="dither_budget",
                   help="fraccion maxima de celdas modificadas por frame")
    p.add_argument("--dither-min-improvement", type=float,
                   default=encoder.selective_dither.DEFAULT_MIN_PROXY_IMPROVEMENT,
                   help="mejora minima del proxy para aceptar un tile")
    p.add_argument("--dither-window", "--dither-temporal-window", type=int,
                   default=encoder.selective_dither.DEFAULT_TEMPORAL_WINDOW,
                   dest="dither_window", help="ventana temporal de histeresis")
    p.add_argument("--image", action="store_true", help="forzar modo imagen (sin audio)")
    p.add_argument("--keep", action="store_true", help="conservar los .ascl/.mp3 intermedios")
    args = p.parse_args(argv)
    args.cols, args.pal_size = encoder.resolve_quality_options(
        args.quality_profile, args.cols, args.pal_size, default_cols=320)
    try:
        encoder.validate_encode_options(args.mode, args.cols, args.rows, args.fps,
                                        args.pal_size, 0.5, args.palette,
                                        args.bake_smoothing, args.reconstruction,
                                        args.palette_block_frames, args.dither,
                                        args.dither_matrix,
                                        args.palette_algorithm,
                                        adaptive_min_frames=args.adaptive_min_frames,
                                        adaptive_max_frames=args.adaptive_max_frames,
                                        adaptive_change_threshold=args.adaptive_change_threshold,
                                        adaptive_hard_cut_threshold=args.adaptive_hard_cut_threshold,
                                        adaptive_stability_max=args.adaptive_stability_max,
                                        perceptual_lut_bits=args.perceptual_lut_bits,
                                        dither_budget=args.dither_budget,
                                        dither_min_improvement=args.dither_min_improvement,
                                        dither_window=args.dither_window)
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
                                    quality_profile=args.quality_profile,
                                    palette_block_frames=args.palette_block_frames,
                                    dither_mode=args.dither,
                                    dither_matrix=args.dither_matrix,
                                    palette_algorithm=args.palette_algorithm,
                                    adaptive_min_frames=args.adaptive_min_frames,
                                    adaptive_max_frames=args.adaptive_max_frames,
                                    adaptive_change_threshold=args.adaptive_change_threshold,
                                    adaptive_hard_cut_threshold=args.adaptive_hard_cut_threshold,
                                    adaptive_stability_max=args.adaptive_stability_max,
                                    perceptual_lut_bits=args.perceptual_lut_bits,
                                    dither_budget=args.dither_budget,
                                    dither_min_improvement=args.dither_min_improvement,
                                    dither_window=args.dither_window)
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
        print("  algoritmo de paleta: %s" % info["palette_algorithm"])
        print("  dither: %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
        if info["palette_mode"] == "block":
            print("  paleta: bloque de %d frames" % info["palette_block_frames"])
        elif info["palette_mode"] == "adaptive":
            print("  paleta: %d bloques adaptativos; tamanos %s" %
                  (len(info["palette_blocks"]), info["palette_block_sizes"]))
            for block in info["palette_blocks"]:
                print("    #%d [%d,%d) n=%d fin=%s score=%.3f entrada=%s estable=%.3f" %
                      (block["index"], block["start"], block["end"], block["size"],
                       block["reason"], block["score"], block["entry_reason"],
                       block["stability"]))
        if info["dither"] == "auto":
            print("  dither auto: presupuesto %.3f, mejora min %.3f, ventana %d; "
                  "%d celdas cambiadas" %
                  (info["dither_budget"], info["dither_min_improvement"],
                   info["dither_window"], info["dither_changed_cells"]))
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
                                    quality_profile=args.quality_profile,
                                    dither_mode=args.dither,
                                    dither_matrix=args.dither_matrix,
                                    palette_algorithm=args.palette_algorithm,
                                    perceptual_lut_bits=args.perceptual_lut_bits,
                                    dither_budget=args.dither_budget,
                                    dither_min_improvement=args.dither_min_improvement,
                                    dither_window=args.dither_window)
        total, la, lau = ascl_bundle.pack(tmp_ascl, None, out)
        print("OK %s  (imagen, %s %dx%d, %.1f KB)" %
              (out, info["mode"], info["cols"], info["rows"], total/1024.0))
        print("  calidad: perfil %s, hasta %d colores, bake %s, reconstruccion %s, flags 0x%02X" %
              (info["quality_profile"], info["pal_size"], info["bake_smoothing"],
               info["reconstruction"], info["flags"]))
        print("  algoritmo de paleta: %s" % info["palette_algorithm"])
        print("  dither: %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
        if not args.keep and os.path.exists(tmp_ascl):
            os.remove(tmp_ascl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
