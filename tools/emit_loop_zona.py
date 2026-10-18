#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_loop_zona.py - emite en H.264 un video en el que una PARTE de la pantalla
repite en loop corto (y el resto se mueve), configurando el encoder para que
aproveche la repeticion. Sin tocar el reproductor: es un H.264 estandar.

Por que: H.264 toma cada cuadro como referencia de hasta 16 cuadros
anteriores. Si una zona repite dentro de ese alcance, el encoder encuentra
SOLO la copia exacta y casi no paga por esa zona. Con las 4 referencias de la
receta de siempre no llega. Medido el 2026-10-17 (docs/INTRO-Y-LOOP.md §7):
mitad superior en loop de 12 cuadros, 300 cuadros 1280x720 @10, crf 26 ->

    referencias       4          5          9          16
    bytes        3.250.041  3.171.824  2.532.209  2.301.501
    vs 4 refs        -        -2,4 %    -22,1 %    -29,2 %

(control sin loop: 16 referencias solo -5,8 %; sin cuadros B, 16 refs
-21,6 %: los B ayudan, porque no ocupan lugar en la lista de referencias.)

El limite lo pone el NIVEL de H.264: la memoria de cuadros del decodificador
(DPB). A 1280x720 caben 5 cuadros en nivel 3.1, 9 en 4.0/4.1 y 16 desde 5.0;
a 1920x1080, 4 en 4.0/4.1 y 16 recien en 5.1. Por defecto se usan 16
referencias y el nivel minimo que las admite; --nivel-max topea (un aparato
viejo con decodificador 4.1 -> 9 referencias a 720p, que en la prueba ya
dieron -22 %). Al aparato le cuesta MEMORIA (16 cuadros de 720p = ~22 MB),
no calculo por cuadro.

Pasos:
  1. busca la zona en loop (tools/buscar_loops.py --por-zona) y la informa;
  2. referencia y4m a la cadencia y ancho destino (709 tv, como emit_v2);
  3. H.264 High con las referencias elegidas, cuadros B, GOP largo (las
     referencias no cruzan un keyframe: GOP >= 10 s y >= 4 periodos);
  4. con --comparar, la misma pieza con 4 referencias (la receta de hoy) y
     la ganancia medida;
  5. MANIFEST-loop-zona.tsv con bytes, SHA-256, SSIM, referencias y nivel.

Uso:
  python tools/emit_loop_zona.py fuente.mp4 --out outputs/zona --comparar
  python tools/emit_loop_zona.py fuente.mp4 --out o --nivel-max 4.1
  python tools/emit_loop_zona.py fuente.mp4 --out o --fps 15 --crf 24 --prefiltro c3
"""

import argparse
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import buscar_loops  # noqa: E402
import emit_intro_loop  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402
import emit_v2  # noqa: E402

ANCHO = 1280
FPS = 10
CRF = 26
REFS = 16
REFS_HOY = 4
BFRAMES = 3
GOP_MIN_SEG = 10
MANIFEST_NAME = "MANIFEST-loop-zona.tsv"
MANIFEST_COLUMNS = ("pieza", "file", "bytes", "sha256", "cuadros", "refs", "nivel",
                    "ssim_all", "psnr_avg", "note")

# H.264 (ITU-T H.264, tabla A-1): nivel -> (MaxMBPS, MaxFS, MaxDpbMbs).
NIVELES_H264 = (
    ("3.0", 40500, 1620, 8100),
    ("3.1", 108000, 3600, 18000),
    ("3.2", 216000, 5120, 20480),
    ("4.0", 245760, 8192, 32768),
    ("4.1", 245760, 8192, 32768),
    ("4.2", 522240, 8704, 34816),
    ("5.0", 589824, 22080, 110400),
    ("5.1", 983040, 36864, 184320),
    ("5.2", 2073600, 36864, 184320),
)


def macrobloques(ancho, alto):
    return ((ancho + 15) // 16) * ((alto + 15) // 16)


def _nivel_num(nivel):
    return float(str(nivel))


def refs_maximas(ancho, alto, nivel):
    """Cuadros que entran en la DPB del nivel a esa resolucion (tope 16)."""
    for nombre, _, _, max_dpb in NIVELES_H264:
        if _nivel_num(nombre) == _nivel_num(nivel):
            return min(16, max_dpb // macrobloques(ancho, alto))
    raise ValueError("nivel H.264 desconocido: %s" % nivel)


def nivel_h264(ancho, alto, fps, refs):
    """El nivel mas bajo que admite la resolucion, la cadencia y las
    referencias pedidas; None si ninguno."""
    mbs = macrobloques(ancho, alto)
    for nombre, max_mbps, max_fs, max_dpb in NIVELES_H264:
        if mbs <= max_fs and mbs * fps <= max_mbps and min(16, max_dpb // mbs) >= refs:
            return nombre
    return None


def elegir_refs_y_nivel(ancho, alto, fps, refs=REFS, nivel_max=None):
    """(refs, nivel): las referencias pedidas, bajadas a lo que admita
    nivel_max si lo hay, y el nivel minimo que las admite."""
    if nivel_max is not None:
        refs = min(refs, refs_maximas(ancho, alto, nivel_max))
    while refs > 1 and nivel_h264(ancho, alto, fps, refs) is None:
        refs -= 1
    nivel = nivel_h264(ancho, alto, fps, refs)
    if nivel is None:
        raise ValueError("ningun nivel H.264 admite %dx%d @%g" % (ancho, alto, fps))
    return refs, nivel


def gop_para(fps, periodo_destino=None):
    """Un keyframe corta las referencias: el GOP tiene que ser largo frente al
    periodo de la zona (>= 10 s y >= 4 periodos)."""
    gop = int(GOP_MIN_SEG * fps)
    if periodo_destino:
        gop = max(gop, int(round(4 * periodo_destino)))
    return gop


def x264_params(refs, gop, bframes=BFRAMES):
    """Los invariantes de determinismo del proyecto (emit_v1) con las
    referencias que pide la zona."""
    return emit_v1.x264_params("high", bframes, refs, gop=gop)


def build_ref_command(ffmpeg, fuente_path, ref_path, ancho=ANCHO, fps=FPS, matriz_fuente="auto"):
    return emit_v2.build_reference_command(ffmpeg, fuente_path, ref_path, ancho, fps,
                                           matriz_fuente=matriz_fuente)


def build_h264_command(ffmpeg, ref_path, out_path, crf, refs, nivel, gop, prefiltro=None):
    return (emit_intro_loop.entrada_ref(ffmpeg, ref_path)
            + list(emit_pieces.DETERMINISM) + ["-map", "0:v:0"]
            + (["-vf", prefiltro] if prefiltro else [])
            + ["-c:v", "libx264", "-profile:v", "high", "-level", nivel,
               "-preset", "slow", "-crf", str(crf), "-x264-params", x264_params(refs, gop),
               "-pix_fmt", "yuv420p"]
            + emit_v2.COLOR_709 + ["-movflags", "+faststart", "-an"]
            + list(emit_pieces.BITEXACT) + [out_path])


def manifest_lines(filas, fuente_sha, fuente_nombre, zona, receta):
    if zona:
        mapa = "/".join("".join("#" if v else "." for v in fila) for fila in zona["mascara"])
        linea_zona = ("# zona\t%.0f %% de la pantalla (%s) repite cada %d cuadros de la fuente"
                      % (100 * zona["area"], mapa, zona["periodo"]))
    else:
        linea_zona = "# zona\tninguna detectada (0,3 a 3 s)"
    lineas = ["# emit_loop_zona.py - loop en una parte de la pantalla (docs/INTRO-Y-LOOP.md s7)",
              "# fuente\t%s\t%s" % (fuente_sha, fuente_nombre), linea_zona,
              "# receta\t%s" % receta, "\t".join(MANIFEST_COLUMNS)]
    for fila in filas:
        lineas.append("\t".join(str(fila.get(col, "")) for col in MANIFEST_COLUMNS))
    return lineas


def emitir(fuente_path, out_dir, ffmpeg="ffmpeg", fps=FPS, ancho=ANCHO, crf=CRF,
           refs=REFS, nivel_max=None, prefiltro=None, comparar=False, forzar=False,
           matriz_fuente="auto", log=print):
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "work")
    os.makedirs(work, exist_ok=True)
    errlog = os.path.join(out_dir, "emit_loop_zona.ffmpeg.log")
    open(errlog, "wb").close()

    fps_fuente = buscar_loops.fps_de_fuente(ffmpeg, fuente_path)
    log("+ buscando loops por zona (tools/buscar_loops.py --por-zona)")
    zona = buscar_loops.detectar_loops_por_zona(buscar_loops.leer_miniaturas(ffmpeg, fuente_path),
                                                fps_fuente)
    for linea in buscar_loops.reporte_zona(zona, fps):
        log("  " + linea)
    if zona is None and not forzar:
        shutil.rmtree(work, ignore_errors=True)
        raise SystemExit("sin loop por zona: no hay nada que aprovechar (--forzar emite igual)")
    periodo_destino = (buscar_loops.periodo_a_fps(zona["periodo"], fps_fuente, fps)[0]
                       if zona else None)

    ref = os.path.join(work, "ref.y4m")
    log("+ referencia %dx? @%d" % (ancho, fps))
    emit_v2.run(build_ref_command(ffmpeg, fuente_path, ref, ancho, fps, matriz_fuente), errlog)
    w, h, _, n = emit_v2.read_y4m_header(ref)
    refs_ok, nivel = elegir_refs_y_nivel(w, h, fps, refs, nivel_max)
    gop = gop_para(fps, periodo_destino)
    log("  %dx%d, %d cuadros; referencias %d, nivel %s, GOP %d%s" % (
        w, h, n, refs_ok, nivel, gop,
        " (topeado por --nivel-max %s)" % nivel_max if refs_ok < refs else ""))

    variantes = [("zona", "zona-h264.mp4", refs_ok, nivel)]
    if comparar:
        variantes.append(("hoy", "hoy-h264.mp4", REFS_HOY,
                          elegir_refs_y_nivel(w, h, fps, REFS_HOY)[1]))
    filas = []
    for pieza, archivo, r, niv in variantes:
        out = os.path.join(out_dir, archivo)
        emit_v2.run(build_h264_command(ffmpeg, ref, out, crf, r, niv, gop, prefiltro),
                    errlog, append=True)
        metricas = emit_v2.medir(ffmpeg, out, ref, fps)
        fila = {"pieza": pieza, "file": archivo, "bytes": os.path.getsize(out),
                "sha256": emit_intro_loop.sha256_de(out), "cuadros": n, "refs": r,
                "nivel": niv, "ssim_all": metricas.get("ssim_all", ""),
                "psnr_avg": metricas.get("psnr_avg", ""),
                "note": "crf %d; GOP %d; prefiltro %s" % (crf, gop, "si" if prefiltro else "no")}
        filas.append(fila)
        log("  %-14s %10d B  refs %2d  nivel %-4s ssim %s" % (
            archivo, fila["bytes"], r, niv, fila["ssim_all"]))
    if comparar:
        ganancia = 100.0 * (filas[0]["bytes"] / float(filas[1]["bytes"]) - 1)
        filas[0]["note"] += "; %+.1f %% vs %d referencias" % (ganancia, REFS_HOY)
        log("-- ganancia medida: %+.1f %% (zona %d B vs hoy %d B)"
            % (ganancia, filas[0]["bytes"], filas[1]["bytes"]))

    receta = "fps %d; ancho %d; crf %d; refs %d (nivel %s); GOP %d; prefiltro %s" % (
        fps, ancho, crf, refs_ok, nivel, gop, prefiltro or "ninguno")
    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as stream:
        stream.write("\n".join(manifest_lines(filas, emit_intro_loop.sha256_de(fuente_path),
                                              os.path.basename(fuente_path), zona, receta)) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    return filas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente")
    parser.add_argument("--out", default="outputs/loop-zona")
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--ancho", type=int, default=ANCHO)
    parser.add_argument("--crf", type=int, default=CRF)
    parser.add_argument("--refs", type=int, default=REFS, help="referencias pedidas (1..16)")
    parser.add_argument("--nivel-max", default=None,
                        help="nivel H.264 maximo que acepta el aparato (p. ej. 4.1)")
    parser.add_argument("--prefiltro", default="ninguno",
                        help="filtro ffmpeg antes del encoder; 'c4' / 'c3' = los de intro_D")
    parser.add_argument("--comparar", action="store_true",
                        help="emite tambien con 4 referencias y mide la ganancia")
    parser.add_argument("--forzar", action="store_true",
                        help="emite aunque no se detecte loop por zona")
    parser.add_argument("--matriz-fuente", default="auto")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args(argv)
    if not 1 <= args.refs <= 16:
        parser.error("--refs va de 1 a 16 (el maximo de H.264)")
    prefiltro = emit_intro_loop.resolver_prefiltro(args.prefiltro.strip())
    emitir(args.fuente, args.out, args.ffmpeg, args.fps, args.ancho, args.crf, args.refs,
           args.nivel_max, prefiltro, args.comparar, args.forzar, args.matriz_fuente)
    return 0


if __name__ == "__main__":
    sys.exit(main())
