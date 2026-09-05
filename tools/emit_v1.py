#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_v1.py - H-6: la emision v1 = la receta que dejo la matriz + el audio.

v0 fue la apuesta (un punto por codec, mudo). v1 es lo que sale de la matriz
por bytes (tools/emit_matrix.py) y suma lo que v0 no tenia: la PISTA DE AUDIO
DEL MASTER, muxeada dentro de cada pieza (S13), y esa misma pista suelta como
"radio" para <audio> (S14). La caja decide si los dos bloques de hardware
-audio y video- conviven sin perder cuadros ni derivar.

Piezas:
  v1-vp9.webm            VP9 + Opus (la base; la receta la fija la matriz)
  v1-h264.mp4            H.264 + AAC (el piso; perfil y crf de la matriz)
  v1-ambiente.mp3        la pista del master tal cual, para <audio> aparte
  dash-vp9/manifest.mpd  WebM segmentado por REMUX de v1-vp9, solo video:
                         por donde entraria VP9 por MSE (S11)
  MANIFEST-v1.tsv        mismas columnas que el pack v0; la pagina lo anexa

La receta se pasa por linea de comandos y NO tiene defaults "buenos": los
defaults son v0 (crf 32 / baseline crf 20) para que, sin argumentos, v1 sea
"v0 con audio" y la diferencia mida solo el audio. Los valores elegidos en la
matriz viven en el workflow emitir-v1 y en docs/EMISION-V1.md, con su fila.

Determinismo: `-threads 1` y muxado bit-exacto como siempre. Los encoders de
AUDIO (libopus, aac) son de punto flotante y no tienen un `cpu-independent`:
el workflow emite DOS VECES y compara byte a byte, como en H-14. Si difieren
entre maquinas, la residencia (H-15) lo tiene que saber.

Uso:
  python tools/emit_v1.py master.asclv --out outputs/v1
  python tools/emit_v1.py master.asclv --out outputs/v1 --vp9-crf 38 --vfr exactos
"""

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ascl_bundle  # noqa: E402
import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402

GOP = emit_pieces.GOP
DETERMINISM = emit_pieces.DETERMINISM
BITEXACT = emit_pieces.BITEXACT

# Opus solo trabaja a 48 kHz; el mp3 del master se remuestrea al entrar. AAC
# en mp4 es el caso mas rodado del planeta (S13 lo dice asi).
AUDIO_WEBM = ["-c:a", "libopus", "-b:a", "64k", "-ar", "48000", "-ac", "2"]
AUDIO_MP4 = ["-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2"]

H264_MIME = {"baseline": 'video/mp4; codecs="avc1.42E01F, mp4a.40.2"',
             "main": 'video/mp4; codecs="avc1.4D401F, mp4a.40.2"',
             "high": 'video/mp4; codecs="avc1.64001F, mp4a.40.2"'}
VP9_MIME = 'video/webm; codecs="vp9, opus"'
DASH_VP9_MIME = 'video/webm; codecs="vp9"'

MANIFEST_NAME = "MANIFEST-v1.tsv"
MANIFEST_COLUMNS = emit_pieces.MANIFEST_COLUMNS


def x264_params(profile, bframes, refs):
    """Los parametros de x264 de v1 se arman con los MISMOS invariantes de v0
    (GOP cerrado de 15, sin scenecut, un hilo, cpu-independent) y lo unico que
    la matriz puede haber relajado: cuadros B y referencias."""
    params = ("bframes=%d:ref=%d:keyint=%d:min-keyint=%d:scenecut=0"
              ":threads=1:cpu-independent=1" % (bframes, refs, GOP, GOP))
    if bframes > 0:
        params += ":b-adapt=1"
    if profile != "baseline":
        params += ":cabac=1"
    if profile == "high":
        params += ":8x8dct=1"
    return params


def recipe(vp9_crf=32, vp9_cpu=2, vp9_extra=None, h264_profile="baseline",
           h264_crf=20, h264_bframes=0, h264_refs=1, vfr="none"):
    """Las dos piezas de video de v1, como dicts con la misma forma que en
    emit_matrix. Sin argumentos es v0 con audio."""
    vf = None
    extra_video = []
    if vfr == "exactos":
        vf = emit_matrix.VFR_EXACTOS
        extra_video = list(emit_matrix.VFR_ARGS)
    elif vfr == "casi":
        vf = emit_matrix.VFR_CASI
        extra_video = list(emit_matrix.VFR_ARGS)
    elif vfr != "none":
        raise ValueError("vfr debe ser none, exactos o casi")
    vp9_args = ["-c:v", "libvpx-vp9", "-crf", str(vp9_crf), "-b:v", "0",
                "-deadline", "good", "-cpu-used", str(vp9_cpu),
                "-g", str(GOP), "-keyint_min", str(GOP), "-row-mt", "0"]
    if vp9_extra:
        vp9_args += list(vp9_extra)
    vp9_args += ["-pix_fmt", "yuv420p"] + extra_video
    h264_args = ["-c:v", "libx264", "-profile:v", h264_profile, "-level", "3.1",
                 "-preset", "slow", "-crf", str(h264_crf),
                 "-x264-params", x264_params(h264_profile, h264_bframes, h264_refs),
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart"] + extra_video
    return [
        {"id": "v1-vp9", "role": "v1", "ext": "webm", "mime": VP9_MIME,
         "vf": vf, "args": vp9_args, "audio": AUDIO_WEBM,
         "note": "VP9 crf %d cpu-used %d%s + Opus 64k%s" % (
             vp9_crf, vp9_cpu, (" " + " ".join(vp9_extra)) if vp9_extra else "",
             "; cadencia variable (%s)" % vfr if vf else "")},
        {"id": "v1-h264", "role": "v1", "ext": "mp4", "mime": H264_MIME[h264_profile],
         "vf": vf, "args": h264_args, "audio": AUDIO_MP4,
         "note": "H.264 %s crf %d B=%d ref=%d + AAC 96k%s" % (
             h264_profile, h264_crf, h264_bframes, h264_refs,
             "; cadencia variable (%s)" % vfr if vf else "")},
    ]


def build_command(ffmpeg, variant, ref_path, audio_path, out_path):
    """Video desde la referencia y4m (entrada 0) + audio del master (entrada
    1), una salida. `-shortest` recorta al video: la pieza dura lo que dura
    el master, y en bucle no queda un cuadro colgado esperando al audio."""
    command = [ffmpeg, "-y", "-nostdin", "-i", ref_path, "-i", audio_path]
    command += list(DETERMINISM)
    if variant.get("vf"):
        command += ["-vf", variant["vf"]]
    command += ["-map", "0:v:0", "-map", "1:a:0"]
    command += list(variant["args"]) + list(variant["audio"])
    command += ["-shortest"] + list(BITEXACT) + [out_path]
    return command


def build_dash_command(ffmpeg, source_path, out_dir):
    """WebM segmentado por remux, SOLO VIDEO: es lo que un SourceBuffer de
    `video/webm; codecs="vp9"` acepta tal cual. El audio de v1-vp9 no viaja
    por aca (S11 pregunta por el video; el audio por MSE es otra fila)."""
    return [ffmpeg, "-y", "-nostdin", "-i", source_path,
            "-map", "0:v:0", "-c", "copy", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            "-f", "dash", "-dash_segment_type", "webm",
            "-seg_duration", "1", "-use_template", "1", "-use_timeline", "1",
            "-init_seg_name", "init.webm",
            "-media_seg_name", "chunk-$Number%05d$.webm",
            os.path.join(out_dir, "manifest.mpd")]


def manifest_lines(rows, master_sha, width, height, fps, frames, receta):
    lines = [
        "# pack v1 - ASCILINE-hybrid - docs/EMISION-V1.md",
        "# master\t%s" % master_sha,
        "# base\t%dx%d\t%d fps\t%d cuadros" % (width, height, fps, frames),
        "# receta\t%s" % receta,
        "# " + "\t".join(MANIFEST_COLUMNS),
    ]
    for row in rows:
        lines.append("\t".join(str(row[column]) for column in MANIFEST_COLUMNS))
    return lines


def run(command, log_path):
    with open(log_path, "wb") as errlog:
        code = subprocess.call(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=errlog)
    if code != 0:
        raise RuntimeError("ffmpeg fallo (%d); ver %s" % (code, log_path))


def emit(master_path, out_dir, variants=None, max_frames=None, ffmpeg=None,
         log=None, receta="v0 con audio"):
    log = log or (lambda message: None)
    ffmpeg = ffmpeg or emit_pieces._resolve_ffmpeg()
    variants = variants or recipe()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    work_dir = os.path.join(out_dir, "work")
    if not os.path.isdir(work_dir):
        os.makedirs(work_dir)

    # El audio sale del MISMO envelope que el video: es la pista del master.
    _ascl, audio_path, _meta = ascl_bundle.unpack(master_path, work_dir)
    if not audio_path:
        raise RuntimeError("el master no trae audio; v1 existe para medirlo")

    ref_path = os.path.join(work_dir, "ref.y4m")
    master_sha, width, height, fps, frames = emit_matrix.write_reference(
        ffmpeg, master_path, work_dir, ref_path, max_frames, log)

    rows = []
    for variant in variants:
        out_path = os.path.join(out_dir, variant["id"] + "." + variant["ext"])
        log("+ " + variant["id"])
        run(build_command(ffmpeg, variant, ref_path, audio_path, out_path),
            os.path.join(out_dir, variant["id"] + ".ffmpeg.log"))
        cuadros = emit_matrix.count_frames(ffmpeg, out_path)
        rows.append({
            "id": variant["id"], "role": variant["role"], "mime": variant["mime"],
            "file": os.path.basename(out_path),
            "bytes": os.path.getsize(out_path),
            "sha256": emit_pieces.sha256_of(out_path),
            "cuadros": cuadros,
            "note": variant["note"] + "; %d cuadros" % cuadros,
        })
        log("  %-12s %10d B  %d cuadros" % (variant["id"], rows[-1]["bytes"],
                                           rows[-1]["cuadros"]))

    # La radio: la pista del master byte a byte. No se recodifica: <audio>
    # reproduce mp3 en todo el parque y asi la fila no mide un encoder.
    radio_path = os.path.join(out_dir, "v1-ambiente.mp3")
    shutil.copyfile(audio_path, radio_path)
    rows.append({
        "id": "v1-ambiente", "role": "radio", "mime": "audio/mpeg",
        "file": "v1-ambiente.mp3", "bytes": os.path.getsize(radio_path),
        "sha256": emit_pieces.sha256_of(radio_path), "cuadros": 0,
        "note": "la pista del master tal cual, para <audio> aparte (S14)",
    })
    log("  %-12s %10d B" % ("v1-ambiente", rows[-1]["bytes"]))

    # S11: VP9 segmentado, por remux.
    source = os.path.join(out_dir, "v1-vp9.webm")
    if os.path.exists(source):
        dash_dir = os.path.join(out_dir, "dash-vp9")
        if not os.path.isdir(dash_dir):
            os.makedirs(dash_dir)
        log("+ dash-vp9 (remux, sin recodificar)")
        run(build_dash_command(ffmpeg, source, dash_dir),
            os.path.join(out_dir, "dash-vp9.ffmpeg.log"))
        segments = len(os.listdir(dash_dir)) - 2
        rows.append({
            "id": "v1-dash-vp9", "role": "stream-v1", "mime": DASH_VP9_MIME,
            "file": "dash-vp9/manifest.mpd",
            "bytes": emit_pieces.directory_bytes(dash_dir),
            "sha256": emit_pieces.sha256_of(os.path.join(dash_dir, "manifest.mpd")),
            "cuadros": 0,
            "note": "WebM segmentado solo video, remux de v1-vp9; %d segmentos" % segments,
        })
        log("  %-12s %10d B  %d segmentos" % ("v1-dash-vp9", rows[-1]["bytes"],
                                              segments))

    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    with open(manifest_path, "w") as stream:
        stream.write("\n".join(manifest_lines(rows, master_sha, width, height,
                                              fps, frames, receta)) + "\n")
    return {"rows": rows, "manifest": manifest_path, "master_sha256": master_sha,
            "width": width, "height": height, "fps": fps, "frames": frames}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("master", help="master .asclv (envelope con audio)")
    parser.add_argument("--out", default="outputs/v1", help="carpeta de salida")
    parser.add_argument("--frames", type=int, default=None,
                        help="cortar en N cuadros (pruebas de humo)")
    parser.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg")
    parser.add_argument("--vp9-crf", type=int, default=32)
    parser.add_argument("--vp9-cpu", type=int, default=2)
    parser.add_argument("--vp9-extra", default="",
                        help='opciones extra del encoder VP9, p. ej. "-tune-content screen"')
    parser.add_argument("--h264-profile", default="baseline",
                        choices=("baseline", "main", "high"))
    parser.add_argument("--h264-crf", type=int, default=20)
    parser.add_argument("--h264-bframes", type=int, default=0)
    parser.add_argument("--h264-refs", type=int, default=1)
    parser.add_argument("--vfr", default="none", choices=("none", "exactos", "casi"),
                        help="cadencia variable: omitir cuadros iguales (exactos) o casi iguales")
    args = parser.parse_args(argv)

    extra = args.vp9_extra.split() if args.vp9_extra else None
    variants = recipe(vp9_crf=args.vp9_crf, vp9_cpu=args.vp9_cpu, vp9_extra=extra,
                      h264_profile=args.h264_profile, h264_crf=args.h264_crf,
                      h264_bframes=args.h264_bframes, h264_refs=args.h264_refs,
                      vfr=args.vfr)
    receta = " ".join(argv if argv is not None else sys.argv[1:])
    result = emit(args.master, args.out, variants=variants, max_frames=args.frames,
                  ffmpeg=args.ffmpeg, receta=receta,
                  log=lambda message: print(message, flush=True))
    print("-- PACK v1 --  %s" % result["manifest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
