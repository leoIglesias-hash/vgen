#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_intro_loop.py - emite un video que es INTRO + LOOP REPETIDO de dos
formas, las dos sin pagar cada vuelta:

  - DOS PIEZAS: la intro (se reproduce una vez) y UNA vuelta del loop (la
    repite el reproductor: producto.html con su anillo MSE);
  - UN ARCHIVO UNICO (`unico-h264.mp4`): intro + el loop N veces en un mp4
    comun y reproducible, con cada vuelta guardada UNA vez
    (tools/mp4_dedup.py). Pesa como las dos piezas; sirve para un reproductor
    que pasa un archivo y nada mas (si sigue el indice del mp4).

Receta por defecto = la que eligio el operador el 2026-10-17 para intro_D
(C3, docs/INTRO-Y-LOOP.md): 1280 de ancho, 10 fps, H.264 High, intro crf 24,
loop crf 26, un solo keyframe por pieza, y un PREFILTRO antes del encoder:

  hqdn3d=3:2:4:3   limpia el ruido fino de la fuente (ya comprimida): esos
                   bits pasan al degrade; el fondo oscuro deja de motearse.
  deband=...       mezcla los pocos tonos de un degrade muy oscuro (8 tonos
                   de luma en el halo de intro_D) para que no se vean anillos.

La intro lleva mas calidad que el loop porque se descarga una sola vez; el
loop es lo que se paga en cada aparato y en la cache.

Pasos:
  1. intro y periodo: los da --intro/--periodo (cuadros de la FUENTE) o los
     busca tools/buscar_loops.py;
  2. dos referencias y4m (709 tv, como emit_v2): la intro a la cadencia
     destino, y el loop retemporizado para durar una cantidad ENTERA de
     cuadros (si no, la costura salta);
  3. una pieza H.264 por referencia (y VP9 en dos pasadas con --vp9-crf);
  4. archivo unico = intro + el loop N veces (--vueltas; default: las de la
     fuente), pegado SIN recodificar -> las vueltas son bytes identicos ->
     tools/mp4_dedup.py guarda cada una una vez (y verifica muestra por
     muestra que el archivo reproduce lo mismo que el pegado);
  5. MANIFEST-intro-loop.tsv con bytes, SHA-256, cuadros y SSIM contra la
     referencia de cada pieza, y la fila del archivo unico.

VP9 sale solo en piezas (WebM guarda los bloques dentro de los clusters, sin
un indice de muestras que se pueda reapuntar).

Uso:
  python tools/emit_intro_loop.py fuente.mp4 --out outputs/intro-loop
  python tools/emit_intro_loop.py fuente.mp4 --out o --intro 197 --periodo 85
  python tools/emit_intro_loop.py fuente.mp4 --out o --vp9-crf 14
  python tools/emit_intro_loop.py fuente.mp4 --out o --prefiltro ninguno
"""

import argparse
import hashlib
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import buscar_loops  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402
import emit_v2  # noqa: E402
import mp4_dedup  # noqa: E402

ANCHO = 1280
FPS = 10
CRF_INTRO = 24
CRF_LOOP = 26
PREFILTRO_C3 = ("hqdn3d=3:2:4:3,"
                "deband=1thr=0.015:2thr=0.015:3thr=0.015:range=24:blur=1")
H264_BFRAMES = 3
H264_REFS = 4
VP9_CPU = 2
MANIFEST_NAME = "MANIFEST-intro-loop.tsv"
ARCHIVO_UNICO = "unico-h264.mp4"
MANIFEST_COLUMNS = ("pieza", "file", "bytes", "sha256", "cuadros", "codec", "crf",
                    "ssim_all", "psnr_avg", "note")


# --------------------------------------------------------------------------
# Plan y lineas de comando (puras)

def plan(intro, periodo, fps_fuente, fps=FPS):
    """Los cortes en cuadros de la fuente y el retemporizado del loop."""
    cuadros_loop, factor = buscar_loops.ajustar_a_fps(periodo, fps_fuente, fps)
    return {"intro": int(intro), "periodo": int(periodo), "fps_fuente": float(fps_fuente),
            "fps": fps, "cuadros_loop": cuadros_loop, "factor": factor}


def filtro_intro(p, ancho=ANCHO, matriz_fuente="auto"):
    return ("trim=start_frame=0:end_frame=%d,setpts=PTS-STARTPTS,%s"
            % (p["intro"], emit_v2.escala(ancho, p["fps"], matriz_fuente)))


def filtro_loop(p, ancho=ANCHO, matriz_fuente="auto"):
    """El loop: sus cuadros de la fuente, estirados/comprimidos en el tiempo
    por `factor` para que a `fps` sean exactamente `cuadros_loop`."""
    return ("trim=start_frame=%d:end_frame=%d,setpts=(PTS-STARTPTS)*%.9f,%s"
            % (p["intro"], p["intro"] + p["periodo"], p["factor"],
               emit_v2.escala(ancho, p["fps"], matriz_fuente)))


def build_ref_command(ffmpeg, fuente_path, filtro, ref_path, cuadros=None):
    command = [ffmpeg, "-y", "-nostdin", "-i", fuente_path] + list(emit_pieces.DETERMINISM)
    command += ["-map", "0:v:0", "-vf", filtro]
    if cuadros:
        command += ["-frames:v", str(cuadros)]
    command += emit_v2.COLOR_709 + list(emit_pieces.BITEXACT) + ["-f", "yuv4mpegpipe", ref_path]
    return command


def prefiltro_args(prefiltro):
    return ["-vf", prefiltro] if prefiltro else []


def build_h264_command(ffmpeg, ref_path, out_path, crf, gop, prefiltro=PREFILTRO_C3):
    """Una pieza H.264 High 3.1 con UN keyframe (gop = cuadros de la pieza):
    la pieza se reproduce entera, no por segmentos."""
    return ([ffmpeg, "-y", "-nostdin", "-f", "yuv4mpegpipe", "-i", ref_path]
            + list(emit_pieces.DETERMINISM) + ["-map", "0:v:0"] + prefiltro_args(prefiltro)
            + ["-c:v", "libx264", "-profile:v", "high", "-level", "3.1",
               "-preset", "slow", "-crf", str(crf),
               "-x264-params", emit_v1.x264_params("high", H264_BFRAMES, H264_REFS, gop=gop),
               "-pix_fmt", "yuv420p"]
            + emit_v2.COLOR_709 + ["-movflags", "+faststart", "-an"]
            + list(emit_pieces.BITEXACT) + [out_path])


def build_vp9_commands(ffmpeg, ref_path, out_path, crf, gop, passlog, prefiltro=PREFILTRO_C3):
    """VP9 en dos pasadas con la calidad de emit_v2 (alt-ref, arnr, tpl)."""
    base = ([ffmpeg, "-y", "-nostdin", "-f", "yuv4mpegpipe", "-i", ref_path]
            + list(emit_pieces.DETERMINISM) + ["-map", "0:v:0"] + prefiltro_args(prefiltro)
            + ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(crf),
               "-cpu-used", str(VP9_CPU), "-row-mt", "0", "-g", str(gop),
               "-keyint_min", str(gop)] + list(emit_v2.VP9_CALIDAD)
            + ["-pix_fmt", "yuv420p"] + emit_v2.COLOR_709 + ["-an"])
    return [base + ["-pass", "1", "-passlogfile", passlog] + list(emit_pieces.BITEXACT)
            + ["-f", "null", os.devnull],
            base + ["-pass", "2", "-passlogfile", passlog] + list(emit_pieces.BITEXACT)
            + ["-f", "webm", out_path]]


def lista_concat(intro_file, loop_file, vueltas):
    """El archivo de lista del demuxer concat: intro (si hay) + loop x vueltas."""
    lineas = []
    if intro_file:
        lineas.append("file '%s'" % intro_file)
    lineas += ["file '%s'" % loop_file] * max(1, int(vueltas))
    return "\n".join(lineas) + "\n"


def build_concat_command(ffmpeg, lista_path, out_path):
    return [ffmpeg, "-y", "-nostdin", "-f", "concat", "-safe", "0", "-i", lista_path,
            "-c", "copy", "-movflags", "+faststart"] + list(emit_pieces.BITEXACT) + [out_path]


def manifest_lines(filas, fuente_sha, fuente_nombre, p, receta):
    lineas = ["# emit_intro_loop.py - intro + loop como piezas (docs/INTRO-Y-LOOP.md)",
              "# fuente\t%s\t%s" % (fuente_sha, fuente_nombre),
              "# corte\tintro %d cuadros de la fuente; loop %d cuadros de la fuente "
              "@ %.3f fps -> %d cuadros @ %g fps (factor de tiempo %.6f)"
              % (p["intro"], p["periodo"], p["fps_fuente"], p["cuadros_loop"], p["fps"],
                 p["factor"]),
              "# receta\t%s" % receta,
              "\t".join(MANIFEST_COLUMNS)]
    for fila in filas:
        lineas.append("\t".join(str(fila.get(col, "")) for col in MANIFEST_COLUMNS))
    return lineas


# --------------------------------------------------------------------------
# Ejecucion

def sha256_de(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for bloque in iter(lambda: stream.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


def archivo_unico(ffmpeg, out_dir, work, h264, vueltas, errlog, log=print):
    """intro + loop x vueltas pegados sin recodificar (work/) y deduplicados
    con mp4_dedup -> unico-h264.mp4. Devuelve su fila del manifiesto."""
    lista = os.path.join(work, "unico-h264.txt")
    with open(lista, "w") as stream:
        intro_file = h264.get("intro")
        stream.write(lista_concat("../" + intro_file if intro_file else None,
                                  "../" + h264["loop"], vueltas))
    pegado = os.path.join(work, "pegado-h264.mp4")
    emit_v2.run(build_concat_command(ffmpeg, lista, pegado), errlog, append=True)
    with open(pegado, "rb") as stream:
        datos, resumen = mp4_dedup.deduplicar(stream.read())
    unico = os.path.join(out_dir, ARCHIVO_UNICO)
    with open(unico, "wb") as stream:
        stream.write(datos)
    log("+ archivo unico %s: intro + loop x%d, %d cuadros (%d unicos); %d B pegado -> %d B"
        % (ARCHIVO_UNICO, vueltas, resumen["muestras"], resumen["unicas"],
           resumen["bytes_antes"], resumen["bytes_despues"]))
    return {"pieza": "unico", "file": ARCHIVO_UNICO, "bytes": len(datos),
            "sha256": hashlib.sha256(datos).hexdigest(), "cuadros": resumen["muestras"],
            "codec": "h264", "crf": "-", "ssim_all": "-", "psnr_avg": "-",
            "note": "intro + loop x%d; cada vuelta guardada una vez (mp4_dedup); pegado %d B"
                    % (vueltas, resumen["bytes_antes"])}


def emitir(fuente_path, out_dir, ffmpeg="ffmpeg", intro=None, periodo=None, fps=FPS,
           ancho=ANCHO, crf_intro=CRF_INTRO, crf_loop=CRF_LOOP, prefiltro=PREFILTRO_C3,
           vp9_crf=None, vueltas=None, matriz_fuente="auto", conservar_refs=False,
           log=print):
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "work")
    os.makedirs(work, exist_ok=True)
    errlog = os.path.join(out_dir, "emit_intro_loop.ffmpeg.log")
    fps_fuente = buscar_loops.fps_de_fuente(ffmpeg, fuente_path)

    if intro is None or periodo is None:
        log("+ buscando el loop (tools/buscar_loops.py)")
        mini = buscar_loops.leer_miniaturas(ffmpeg, fuente_path)
        hallado = buscar_loops.detectar_loop(mini, fps_fuente)
        if hallado is None:
            raise SystemExit("no se encontro un loop repetido; pasar --intro y --periodo a mano")
        for linea in buscar_loops.reporte(hallado, fps, buscar_loops.costura(
                mini, hallado["intro"], hallado["periodo"])):
            log("  " + linea)
        intro, periodo = hallado["intro"], hallado["periodo"]
        vueltas = vueltas or hallado["vueltas"]
    p = plan(intro, periodo, fps_fuente, fps)
    vueltas = vueltas or 3

    piezas = []
    if p["intro"] > 0:
        piezas.append(("intro", filtro_intro(p, ancho, matriz_fuente), None, crf_intro))
    piezas.append(("loop", filtro_loop(p, ancho, matriz_fuente), p["cuadros_loop"], crf_loop))

    filas = []
    archivos = {}
    open(errlog, "wb").close()
    for nombre, filtro, cuadros, crf in piezas:
        ref = os.path.join(work, "ref-%s.y4m" % nombre)
        log("+ referencia %s" % nombre)
        emit_v2.run(build_ref_command(ffmpeg, fuente_path, filtro, ref, cuadros), errlog, append=True)
        _, _, _, n = emit_v2.read_y4m_header(ref)
        destino = [("h264", "%s-h264.mp4" % nombre, crf)]
        if vp9_crf is not None:
            destino.append(("vp9", "%s-vp9.webm" % nombre, vp9_crf))
        for codec, archivo, crf_pieza in destino:
            out = os.path.join(out_dir, archivo)
            started = time.time()
            if codec == "h264":
                emit_v2.run(build_h264_command(ffmpeg, ref, out, crf_pieza, n, prefiltro),
                            errlog, append=True)
            else:
                for command in build_vp9_commands(ffmpeg, ref, out, crf_pieza, n,
                                                  os.path.join(work, "vp9-%s" % nombre), prefiltro):
                    emit_v2.run(command, errlog, append=True)
            metricas = emit_v2.medir(ffmpeg, out, ref, fps)
            fila = {"pieza": nombre, "file": archivo, "bytes": os.path.getsize(out),
                    "sha256": sha256_de(out), "cuadros": n, "codec": codec, "crf": crf_pieza,
                    "ssim_all": metricas.get("ssim_all", ""),
                    "psnr_avg": metricas.get("psnr_avg", ""),
                    "note": "prefiltro %s; %.0f s" % ("si" if prefiltro else "no",
                                                      time.time() - started)}
            filas.append(fila)
            archivos.setdefault(codec, {})[nombre] = archivo
            log("  %-16s %10d B  %3d cuadros  ssim %s" % (archivo, fila["bytes"], n,
                                                           fila["ssim_all"]))

    filas.append(archivo_unico(ffmpeg, out_dir, work, archivos["h264"], vueltas, errlog, log))

    receta = "fps %g; ancho %d; h264 intro crf %d / loop crf %d%s; prefiltro %s" % (
        fps, ancho, crf_intro, crf_loop,
        "; vp9 crf %d" % vp9_crf if vp9_crf is not None else "", prefiltro or "ninguno")
    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as stream:
        stream.write("\n".join(manifest_lines(filas, sha256_de(fuente_path),
                                              os.path.basename(fuente_path), p, receta)) + "\n")
    if conservar_refs:
        log("+ referencias conservadas en %s (para tools/medir_banding.py)" % work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    for codec in sorted(archivos):
        total = sum(f["bytes"] for f in filas if f["codec"] == codec and f["pieza"] != "unico")
        log("-- %s: dos piezas = %d B (intro + 1 vuelta)" % (codec, total))
    log("-- h264: archivo unico = %d B (%s)" % (filas[-1]["bytes"], ARCHIVO_UNICO))
    return filas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente")
    parser.add_argument("--out", default="outputs/intro-loop")
    parser.add_argument("--intro", type=int, default=None,
                        help="cuadros de la FUENTE antes del loop (sin esto se detecta)")
    parser.add_argument("--periodo", type=int, default=None,
                        help="cuadros de la FUENTE de una vuelta del loop")
    parser.add_argument("--fps", type=int, default=FPS,
                        help="cadencia destino, entera (minimo 10, maximo 15 en este uso)")
    parser.add_argument("--ancho", type=int, default=ANCHO)
    parser.add_argument("--crf-intro", type=int, default=CRF_INTRO)
    parser.add_argument("--crf-loop", type=int, default=CRF_LOOP)
    parser.add_argument("--prefiltro", default=PREFILTRO_C3,
                        help="filtro ffmpeg antes del encoder; 'ninguno' lo apaga")
    parser.add_argument("--vp9-crf", type=int, default=None,
                        help="emite tambien VP9 (dos pasadas) con este crf")
    parser.add_argument("--vueltas", type=int, default=None,
                        help="vueltas del loop en el archivo unico (default: las de la fuente; "
                             "3 si se pasan --intro/--periodo a mano)")
    parser.add_argument("--matriz-fuente", default="auto")
    parser.add_argument("--conservar-refs", action="store_true",
                        help="deja work/ref-*.y4m para medir con tools/medir_banding.py")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args(argv)
    if (args.intro is None) != (args.periodo is None):
        parser.error("--intro y --periodo van juntos (o ninguno, para detectarlos)")
    prefiltro = None if args.prefiltro.lower() in ("", "ninguno", "none") else args.prefiltro
    emitir(args.fuente, args.out, args.ffmpeg, args.intro, args.periodo, args.fps,
           args.ancho, args.crf_intro, args.crf_loop, prefiltro, args.vp9_crf,
           args.vueltas, args.matriz_fuente, args.conservar_refs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
