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
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoder
import ascl_bundle
import ascl_v2
import overlay_palette


def main(argv=None):
    p = argparse.ArgumentParser(description="video -> .asclv (un solo archivo)")
    p.add_argument("input")
    p.add_argument("--out", default=None, help="ruta .asclv (default ../outputs/<nombre>.asclv)")
    p.add_argument("--format", choices=("v1", "v2"), default="v1",
                   help="v1 compatible historico; v2 lossless exacto (default v1)")
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
    p.add_argument("--palette-refit", type=int, default=0,
                   help="E-12: iteraciones de refit de paleta a la asignacion "
                        "real (0=off, 3..5 tipico, max 10)")
    p.add_argument("--palette-uint8-refine", type=int, default=0,
                   help="E-13: iteraciones del cierre de Lloyd en dominio "
                        "uint8, solo kmeans-oklab (0=off, 2..5 tipico, max 10)")
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
    p.add_argument("--dither-exact", action="store_true",
                   help="E-16 opt-in: mezcla exacta desde la base real del "
                        "cuantizador (sin gate 555); mas CPU y mas bytes")
    p.add_argument("--dither-byte-budget", type=int, default=None,
                   help="E-17 opt-in: bytes extra permitidos por frame para el "
                        "dither, medidos con la estructura real del frame y "
                        "zlib-9 determinista; se aplica JUNTO al presupuesto "
                        "de celdas (auto recorta tiles, selective rechaza)")
    p.add_argument("--keyint", type=int, default=0,
                   help="E-10: keyframe cada N frames (0 = fps*2, el historico)")
    p.add_argument("--scene-keyframes", action="store_true",
                   help="E-10: keyframe en cada corte de escena; habilita --keyint largos")
    p.add_argument("--tile-size", type=int, default=ascl_v2.DEFAULT_TILE_SIZE,
                   help="E-09: tile regional v2 en 4..32 (default %d)"
                   % ascl_v2.DEFAULT_TILE_SIZE)
    p.add_argument("--tile-sweep", action="store_true",
                   help="E-09: barre %s y conserva el archivo menor"
                   % (ascl_v2.SWEEP_TILE_SIZES,))
    p.add_argument("--reserved", type=int, default=0,
                   help="entradas de paleta reservadas al overlay (0, 10 o 32); "
                   "se estampan los RGB canonicos de overlay_palette (F7 / INT-003)")
    p.add_argument("--image", action="store_true", help="forzar modo imagen (sin audio)")
    p.add_argument("--keep", action="store_true",
                   help="conservar .ascl/.mp3; rechaza nombres intermedios existentes")
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
                                        dither_window=args.dither_window,
                                        reserved=args.reserved,
                                        palette_refit=args.palette_refit,
                                        palette_uint8_refine=args.palette_uint8_refine,
                                        dither_exact=args.dither_exact,
                                        dither_byte_budget=args.dither_byte_budget)
    except ValueError as exc:
        p.error(str(exc))
    if args.reserved and args.image:
        p.error("--reserved es para video (el overlay F7 no cubre imagenes)")
    if args.reserved not in (0,) + overlay_palette.RESERVED_COUNTS:
        p.error("--reserved debe ser 0, 10 o 32 (reservas canonicas)")

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.abspath(os.path.join(here, "..", "outputs"))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.input))[0]
    out = os.path.abspath(args.out or os.path.join(out_dir, stem + ".asclv"))
    input_path = os.path.abspath(args.input)
    if os.path.splitext(out)[1].lower() != ".asclv":
        p.error("--out debe terminar en .asclv")
    if os.path.normcase(input_path) == os.path.normcase(out):
        p.error("--out no puede sobrescribir el archivo de entrada")
    try:
        if os.path.exists(input_path) and os.path.exists(out) and \
                os.path.samefile(input_path, out):
            p.error("--out no puede sobrescribir el archivo de entrada")
    except OSError:
        pass
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out_stem = os.path.splitext(out)[0]
    workspace = None
    if args.keep:
        build_stem = out_stem
    else:
        # Evita que dos procesos o un --out personalizado pisen sidecars del
        # usuario. TemporaryDirectory limpia tambien si main termina con error.
        workspace = tempfile.TemporaryDirectory(
            prefix=".asclv-build-", dir=os.path.dirname(out))
        build_stem = os.path.join(workspace.name, os.path.basename(out_stem))
    # v2 nace de la matriz v1 aprobada. Se usan nombres distintos para no
    # sobrescribir nunca la fuente durante la conversión.
    tmp_ascl = build_stem + (".source-v1.ascl" if args.format == "v2" else ".ascl")
    final_ascl = build_stem + ".ascl"
    keyint = args.keyint if args.keyint > 0 else max(1, args.fps * 2)

    ext = os.path.splitext(args.input)[1].lower()
    is_video = (not args.image) and (ext in encoder.VIDEO_EXTS)
    if args.keep:
        intermediates = [tmp_ascl]
        if args.format == "v2":
            intermediates.append(final_ascl)
        if is_video:
            intermediates.append(os.path.splitext(tmp_ascl)[0] + ".mp3")
        input_key = os.path.normcase(input_path)
        output_key = os.path.normcase(out)
        for intermediate in sorted(set(intermediates)):
            path_key = os.path.normcase(os.path.abspath(intermediate))
            if path_key in (input_key, output_key):
                p.error("un intermedio --keep coincide con la entrada o la salida: %s" %
                        intermediate)
            if os.path.lexists(intermediate):
                p.error("--keep no sobrescribe un intermedio existente: %s" %
                        intermediate)

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
                                    dither_window=args.dither_window,
                                    scene_keyframes=args.scene_keyframes,
                                    palette_refit=args.palette_refit,
                                    palette_uint8_refine=args.palette_uint8_refine,
                                    dither_exact=args.dither_exact,
                                    dither_byte_budget=args.dither_byte_budget,
                                    reserved=args.reserved,
                                    reserved_colors=(
                                        overlay_palette.reserved_table(args.reserved)
                                        if args.reserved else None),
                                    # INT-001 §11: con overlay, el dither no
                                    # toca los rects del panel canonico
                                    protect_panel=bool(args.reserved))
        mp3 = os.path.splitext(tmp_ascl)[0] + ".mp3"
        mp3 = mp3 if (info.get("audio") and os.path.exists(mp3)) else None
        if mp3 is None:
            print("AVISO: no se extrajo audio; la fuente puede no tenerlo o FFmpeg "
                  "puede haber fallado.", file=sys.stderr)
        v2_stats = None
        bundle_ascl = tmp_ascl
        if args.format == "v2":
            v2_stats = ascl_v2.transcode_path(
                tmp_ascl, final_ascl,
                tile_size=args.tile_size, sweep=args.tile_sweep)
            bundle_ascl = final_ascl
        total, la, lau = ascl_bundle.pack(bundle_ascl, mp3, out)
        secs = info["n_frames"] / float(info["fps"]) or 1
        print("OK %s" % out)
        print("  %s %dx%d @ %dfps - %d frames - paleta %s" %
              (info["mode"], info["cols"], info["rows"], info["fps"],
               info["n_frames"], info["palette_mode"]))
        print("  calidad: perfil %s, hasta %d colores, bake %s, reconstruccion %s, flags 0x%02X" %
              (info["quality_profile"], info["pal_size"], info["bake_smoothing"],
               info["reconstruction"], info["flags"]))
        print("  algoritmo de paleta: %s" % info["palette_algorithm"])
        if info.get("palette_refit"):
            print("  refit de paleta (E-12): %d iteraciones" % info["palette_refit"])
        if info.get("palette_uint8_refine"):
            print("  cierre Lloyd uint8 (E-13): %d iteraciones" %
                  info["palette_uint8_refine"])
        if info.get("dither_exact"):
            print("  dither exacto (E-16): mezcla desde la base real")
        if v2_stats is not None:
            print("  formato: ASCLVID2 lossless; %d regionales + %d predictores "
                  "de %d frames, "
                  "%d B menos que la matriz v1 (%.2f%%)" %
                  (v2_stats["regional_frames"], v2_stats.get("predictor_frames", 0),
                   v2_stats["n_frames"],
                   v2_stats["saved_bytes"], v2_stats["saved_percent"]))
            if v2_stats.get("sweep"):
                print("  barrido tile_size: %s -> ganador %d" %
                      (", ".join("%d:%d B" % pair for pair in v2_stats["sweep"]),
                       v2_stats["tile_size"]))
        else:
            print("  formato: ASCLVID1")
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
        if info.get("dither_byte_budget") is not None:
            print("  presupuesto de dither en bytes (E-17): %d B/frame; "
                  "%d frames limitados, %d tiles recortados" %
                  (info["dither_byte_budget"],
                   info["dither_byte_limited_frames"],
                   info["dither_byte_dropped_tiles"]))
        if info.get("threshold_dither_protected_frames"):
            print("  threshold (E-18): %d celdas tramadas protegidas del "
                  "revert en %d frames" %
                  (info["threshold_dither_protected_cells"],
                   info["threshold_dither_protected_frames"]))
        print("  bundle: %.1f KB  (video %.1f KB + audio %.1f KB)  ~%.1f KB/s" %
              (total/1024.0, la/1024.0, lau/1024.0, total/1024.0/secs))
        if not args.keep:
            cleanup = [tmp_ascl, mp3]
            if args.format == "v2":
                cleanup.append(final_ascl)
            for x in cleanup:
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
                                    dither_window=args.dither_window,
                                    palette_refit=args.palette_refit,
                                    palette_uint8_refine=args.palette_uint8_refine,
                                    dither_exact=args.dither_exact,
                                    dither_byte_budget=args.dither_byte_budget)
        v2_stats = None
        bundle_ascl = tmp_ascl
        if args.format == "v2":
            v2_stats = ascl_v2.transcode_path(
                tmp_ascl, final_ascl,
                tile_size=args.tile_size, sweep=args.tile_sweep)
            bundle_ascl = final_ascl
        total, la, lau = ascl_bundle.pack(bundle_ascl, None, out)
        print("OK %s  (imagen, %s %dx%d, %.1f KB)" %
              (out, info["mode"], info["cols"], info["rows"], total/1024.0))
        print("  calidad: perfil %s, hasta %d colores, bake %s, reconstruccion %s, flags 0x%02X" %
              (info["quality_profile"], info["pal_size"], info["bake_smoothing"],
               info["reconstruction"], info["flags"]))
        print("  algoritmo de paleta: %s" % info["palette_algorithm"])
        if info.get("palette_refit"):
            print("  refit de paleta (E-12): %d iteraciones" % info["palette_refit"])
        if info.get("palette_uint8_refine"):
            print("  cierre Lloyd uint8 (E-13): %d iteraciones" %
                  info["palette_uint8_refine"])
        if info.get("dither_exact"):
            print("  dither exacto (E-16): mezcla desde la base real")
        if info.get("dither_byte_budget") is not None:
            print("  presupuesto de dither en bytes (E-17): %d B/frame; "
                  "%d tiles recortados" %
                  (info["dither_byte_budget"],
                   info["dither_byte_dropped_tiles"]))
        if v2_stats is not None:
            print("  formato: ASCLVID2 lossless; %d regionales + %d predictores; "
                  "%d B menos (%.2f%%)" %
                  (v2_stats["regional_frames"], v2_stats.get("predictor_frames", 0),
                   v2_stats["saved_bytes"], v2_stats["saved_percent"]))
            if v2_stats.get("sweep"):
                print("  barrido tile_size: %s -> ganador %d" %
                      (", ".join("%d:%d B" % pair for pair in v2_stats["sweep"]),
                       v2_stats["tile_size"]))
        else:
            print("  formato: ASCLVID1")
        print("  dither: %s%s" %
              (info["dither"], (" Bayer %d" % info["dither_matrix"])
               if info["dither"] != "off" else ""))
        if not args.keep:
            for x in (tmp_ascl, final_ascl if args.format == "v2" else None):
                if x and os.path.exists(x):
                    os.remove(x)
    if workspace is not None:
        workspace.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
