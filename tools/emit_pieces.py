#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_pieces.py - H-9: emisor del pack v0 (el primer video, por suposicion).

Toma el MASTER .asclv/.ascl -la verdad determinista offline- y emite las piezas
descritas en docs/EMISION-V0.md S3. Cada pieza es una apuesta distinta sobre por
donde entra el video al hardware del aparato:

  v0-h264-baseline.mp4   el piso universal, con el DPB mas chico posible
                         (sin cuadros B, refs=1, GOP cerrado y corto)
  v0-h264-main.mp4       el DETECTOR de hardware vs. software: CABAC + 8x8 son
                         casi gratis en silicio y caros en CPU. Si esta gana,
                         el cuello no es el bitstream (suposicion S2)
  v0-vp9.webm            banda: el camino que YouTube usa en Android TV (S3)
  v0-vp9-alpha.webm      papelitos sobre transparencia total: el efecto como
                         pieza aparte, compuesto por el navegador (S4)

y despues las EMPAQUETA en segmentos, por REMUX (`-c copy`, sin recodificar):

  hls-ts/stream.m3u8     HLS clasico con segmentos MPEG-TS
  hls-fmp4/stream.m3u8   HLS CMAF: init separado, como nuestro formato
  dash/manifest.mpd      DASH: el modelo de datos del formato, servido tal cual
  MANIFEST.tsv           el embrion del manifiesto del formato

Los tres empaquetados prueban dos cosas de una: si el aparato reproduce HLS/DASH
NATIVO (camino D -en ese aparato el muxer ES5 podria sobrar-) y si las piezas se
intercambian sin recodificar, que es la afirmacion central del formato.

El manifiesto va en TEXTO TABULADO y NUNCA en JSON: el gate ES5 del proyecto
prohibe `JSON` porque los WebViews viejos del parque no lo garantizan.

Todo lo caro se paga aca: el aparato solo recibe algo que su <video> sabe leer.

Uso:
  python tools/emit_pieces.py master.asclv --out outputs/v0
  python tools/emit_pieces.py master.asclv --out outputs/v0 --only v0-vp9
  python tools/emit_pieces.py master.asclv --out outputs/v0 --frames 30
"""

import argparse
import hashlib
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_bundle  # noqa: E402
from ascl_decode import cells_to_rgb, decode_all, _resolve_ffmpeg  # noqa: E402


# Cuadros por GOP. A 15 fps es 1 s: la granularidad con la que despues se
# cortan los segmentos del paquete (cada pieza tiene que arrancar en un cuadro
# clave cerrado para ser intercambiable).
GOP = 15

# Calidad constante, no bitrate fijo: v0 fija un solo punto por codec porque el
# barrido de calidad es otro eje (H-6). Los numeros son la apuesta, no un
# resultado.
CRF_H264 = 20
CRF_VP9 = 32

# Determinismo (invariante 7 del proyecto): un solo hilo por encoder y muxado
# bit-exacto, para que la pieza no cambie de bytes entre corridas.
DETERMINISM = ("-threads", "1")
BITEXACT = ("-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1")

# H-14b (adoptado por el operador el 2026-09-04): `threads=1` alcanza para que
# UNA maquina repita sus propios bytes, pero no para que DOS coincidan: x264
# elige con aritmetica que depende del juego de instrucciones de la CPU (medido
# en H-14: AMD EPYC 9V74 y 7763 dan un archivo, Intel 6973P-C otro).
# `cpu-independent=1` apaga esos atajos y las CPUs del parque de runners emiten
# los mismos bytes; cuesta +0,016 % en baseline y -0,06 % en main. Va EN LA
# RECETA, no como palanca de CI, porque la residencia (H-15) pinea las piezas
# por contenido: una re-emision sin cambios no puede invalidar lo que el
# aparato ya tiene guardado.
X264_COMMON = ("bframes=0:ref=1:keyint=%d:min-keyint=%d:scenecut=0"
               ":threads=1:cpu-independent=1" % (GOP, GOP))
X264_BASELINE = X264_COMMON
X264_MAIN = X264_COMMON + ":cabac=1"

VARIANTS = (
    {
        "id": "v0-h264-baseline",
        "role": "base",
        "file": "v0-h264-baseline.mp4",
        "mime": 'video/mp4; codecs="avc1.42E01F"',
        "pix_in": "rgb24",
        "note": "piso universal; DPB minimo (sin B, refs=1)",
        "args": ["-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
                 "-preset", "slow", "-crf", str(CRF_H264),
                 "-x264-params", X264_BASELINE,
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    },
    {
        "id": "v0-h264-main",
        "role": "base",
        "file": "v0-h264-main.mp4",
        "mime": 'video/mp4; codecs="avc1.4D401F"',
        "pix_in": "rgb24",
        "note": "detector hardware vs software (CABAC + 8x8)",
        "args": ["-c:v", "libx264", "-profile:v", "main", "-level", "3.1",
                 "-preset", "slow", "-crf", str(CRF_H264),
                 "-x264-params", X264_MAIN,
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    },
    {
        "id": "v0-vp9",
        "role": "base",
        "file": "v0-vp9.webm",
        "mime": 'video/webm; codecs="vp9"',
        "pix_in": "rgb24",
        "note": "banda: el camino de YouTube en Android TV",
        "args": ["-c:v", "libvpx-vp9", "-crf", str(CRF_VP9), "-b:v", "0",
                 "-deadline", "good", "-cpu-used", "2",
                 "-g", str(GOP), "-keyint_min", str(GOP), "-row-mt", "0",
                 "-pix_fmt", "yuv420p"],
    },
    {
        "id": "v0-vp9-alpha",
        "role": "alpha",
        "file": "v0-vp9-alpha.webm",
        "mime": 'video/webm; codecs="vp9"',
        "pix_in": "rgba",
        "note": "papelitos sobre transparencia total: el efecto no existe abajo",
        "args": ["-c:v", "libvpx-vp9", "-crf", str(CRF_VP9), "-b:v", "0",
                 "-deadline", "good", "-cpu-used", "2",
                 "-g", str(GOP), "-keyint_min", str(GOP), "-row-mt", "0",
                 "-auto-alt-ref", "0", "-pix_fmt", "yuva420p"],
    },
)

# Empaquetados segmentados. Salen de una pieza YA CODIFICADA por REMUX (`-c
# copy`): no se recodifica nada, no se toca un pixel, y cuesta segundos. Prueban
# dos cosas de una: si el aparato reproduce HLS/DASH NATIVO (camino D, que en ese
# aparato puede volver innecesario al muxer ES5), y si las piezas se intercambian
# sin recodificar -que es la afirmacion central del formato-.
#
# El GOP de 15 cuadros a 15 fps hace que `-hls_time 1` corte EXACTAMENTE en
# cuadros clave: la estructura que elegimos en v0 es la que habilita esto.
SEGMENT_ARGS = ["-c", "copy", "-map_metadata", "-1",
                "-fflags", "+bitexact", "-flags:v", "+bitexact"]

STREAMS = (
    {
        "id": "v0-hls-ts",
        "role": "stream",
        "source": "v0-h264-baseline",
        "dir": "hls-ts",
        "playlist": "stream.m3u8",
        "mime": "application/vnd.apple.mpegurl",
        "note": "HLS con segmentos MPEG-TS: el empaquetado mas rodado",
        "args": ["-f", "hls", "-hls_time", "1", "-hls_playlist_type", "vod",
                 "-hls_list_size", "0", "-hls_segment_type", "mpegts",
                 "-hls_flags", "independent_segments"],
        "segment_name": "seg%03d.ts",
    },
    {
        "id": "v0-hls-fmp4",
        "role": "stream",
        "source": "v0-h264-baseline",
        "dir": "hls-fmp4",
        "playlist": "stream.m3u8",
        "mime": "application/vnd.apple.mpegurl",
        "note": "HLS CMAF: init separado, como nuestro formato",
        "args": ["-f", "hls", "-hls_time", "1", "-hls_playlist_type", "vod",
                 "-hls_list_size", "0", "-hls_segment_type", "fmp4",
                 "-hls_fmp4_init_filename", "init.mp4",
                 "-hls_flags", "independent_segments"],
        "segment_name": "seg%03d.m4s",
    },
    {
        "id": "v0-dash",
        "role": "stream",
        "source": "v0-h264-baseline",
        "dir": "dash",
        "playlist": "manifest.mpd",
        "mime": "application/dash+xml",
        "note": "DASH: el modelo de datos del formato, servido tal cual",
        "args": ["-f", "dash", "-seg_duration", "1", "-use_template", "1",
                 "-use_timeline", "1",
                 "-init_seg_name", "init.m4s",
                 "-media_seg_name", "chunk-$Number%05d$.m4s"],
        "segment_name": None,
    },
)

MANIFEST_NAME = "MANIFEST.tsv"
MANIFEST_COLUMNS = ("id", "role", "mime", "file", "bytes", "sha256", "note")


def variant_by_id(variant_id):
    for variant in VARIANTS:
        if variant["id"] == variant_id:
            return variant
    raise KeyError(variant_id)


def build_command(ffmpeg, variant, width, height, fps, out_path,
                  x264_extra=None):
    """Linea de ffmpeg de una pieza. El contenido no se toca: entra RGB crudo
    decodificado del master y sale la pieza; ningun paso re-cuantiza el look.

    `x264_extra` (H-14) se pega al final de -x264-params de las piezas H.264:
    es la palanca para probar en CI una opcion del encoder sin tocar la receta
    declarada arriba. La que se probo asi -cpu-independent=1- ya no necesita la
    palanca: desde H-14b vive en la receta (X264_COMMON)."""
    args = list(variant["args"])
    if x264_extra and "-x264-params" in args:
        at = args.index("-x264-params") + 1
        args[at] = args[at] + ":" + x264_extra
    return ([ffmpeg, "-y", "-nostdin",
             "-f", "rawvideo", "-pix_fmt", variant["pix_in"],
             "-s", "%dx%d" % (width, height), "-r", str(fps), "-i", "-"]
            + list(DETERMINISM) + args + list(BITEXACT)
            + [out_path])


def stream_by_id(stream_id):
    for stream in STREAMS:
        if stream["id"] == stream_id:
            return stream
    raise KeyError(stream_id)


def posix_path(path):
    """Los muxers hls/dash de ffmpeg ubican la carpeta del playlist buscando
    '/': con '\\' (Windows, P-008) escriben init y segmentos en el directorio
    actual y el playlist queda solo. Barras siempre; en Linux no cambia nada."""
    return path.replace("\\", "/")


def build_segment_command(ffmpeg, stream, source_path, out_dir):
    """Remux de una pieza ya codificada a un empaquetado segmentado. `-c copy`
    es lo que hace que esto NO sea una segunda codificacion: los mismos bytes de
    video, envueltos distinto."""
    command = [ffmpeg, "-y", "-nostdin", "-i", source_path] + list(SEGMENT_ARGS)
    if stream["segment_name"]:
        command += ["-hls_segment_filename",
                    posix_path(os.path.join(out_dir, stream["segment_name"]))]
    return command + list(stream["args"]) + [posix_path(os.path.join(out_dir, stream["playlist"]))]


def directory_bytes(directory):
    total = 0
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            total += os.path.getsize(path)
    return total


# H-18b (pedido del operador, 2026-09-04): la pieza con alfa dejo de llevar el
# RGB del master. Antes era el propio cuadro de abajo con una mascara de disco:
# superpuesta EXACTA sobre el video de abajo se veria identica a el, asi que la
# prueba no podia contestar si el navegador compuso o no. Ahora lleva CONTENIDO
# QUE NO EXISTE ABAJO -papelitos de colores- sobre transparencia TOTAL, que es
# el caso real de un efecto: "al ser transparente el video de arriba se veria el
# de abajo con los papelitos de festejo como si fuera un solo video".
#
# Todo se calcula con ENTEROS y ondas triangulares. Nada de sin/cos: una
# diferencia de 1 ULP entre dos libm mueve el borde de un papelito y cambia los
# bytes de la pieza, y el invariante 7 pide que dos maquinas emitan el mismo
# archivo (H-14b lo acaba de saldar para x264; no se rompe por el otro lado).
CONFETTI_COUNT = 160
CONFETTI_COLORS = (
    (255, 64, 64), (255, 176, 32), (255, 240, 64), (64, 224, 96),
    (64, 176, 255), (160, 96, 255), (255, 96, 192), (245, 245, 255),
)


def _sorteo(seed, salt):
    """Entero -> entero en [0, 4095]. Congelado a proposito: no se usa el
    generador de numpy porque aca no importa la estadistica sino que el archivo
    salga igual en cualquier maquina y con cualquier version instalada."""
    value = (seed * 1103515245 + salt * 12345 + 2531011) & 0x7FFFFFFF
    value ^= value >> 13
    value = (value * 1103515245 + 12345) & 0x7FFFFFFF
    return (value >> 11) & 0xFFF


def _triangulo(value, period):
    """Onda triangular entera en [0, period]: sube y baja sin trascendentes."""
    step = value % (2 * period)
    return step if step <= period else 2 * period - step


def confetti_rgba(width, height, index):
    """Un cuadro de papelitos sobre transparencia TOTAL, derivado SOLO del
    indice de cuadro.

    Lo que se prueba con esto es la COMPOSICION -si el navegador transparenta un
    WebM con alfa, a que costo, y si el de abajo se sigue viendo entero-, no el
    arte: el contenido definitivo sale del master. Los bordes son duros a
    proposito, que es el caso que mas sufre al componer y al subsamplear."""
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    unit = max(2, height // 90)
    for particle in range(CONFETTI_COUNT):
        color = CONFETTI_COLORS[particle % len(CONFETTI_COLORS)]
        alto = unit + _sorteo(particle, 1) % (2 * unit)
        caida = unit + _sorteo(particle, 2) % (3 * unit)
        ciclo = height + 4 * alto
        top = (_sorteo(particle, 3) * ciclo // 4096 +
               index * caida) % ciclo - 2 * alto
        vaiven = _triangulo(index * 2 + _sorteo(particle, 4) % 64, 32) - 16
        left = _sorteo(particle, 5) * width // 4096 + vaiven * unit // 4
        # El ancho late como un papelito que gira sobre su eje: de 1 a `alto`.
        ancho = 1 + _triangulo(index * 3 + _sorteo(particle, 6) % 24, 12) * alto // 12
        y0, y1 = max(0, top), min(height, top + alto)
        x0, x1 = max(0, left), min(width, left + ancho)
        if y1 <= y0 or x1 <= x0:
            continue
        frame[y0:y1, x0:x1, 0] = color[0]
        frame[y0:y1, x0:x1, 1] = color[1]
        frame[y0:y1, x0:x1, 2] = color[2]
        frame[y0:y1, x0:x1, 3] = 255
    return frame


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def manifest_lines(rows, master_sha, width, height, fps, frames):
    """MANIFEST.tsv: texto tabulado, jamas JSON (el gate ES5 prohibe `JSON`).
    Las lineas de comentario arrancan con '#'; el orden de las filas es el
    ORDEN DE PRUEBA, no un orden de preferencia -cual gana lo dice el aparato."""
    lines = [
        "# pack v0 - ASCILINE-hybrid - docs/EMISION-V0.md",
        "# master\t%s" % master_sha,
        "# base\t%dx%d\t%d fps\t%d cuadros" % (width, height, fps, frames),
        "# " + "\t".join(MANIFEST_COLUMNS),
    ]
    for row in rows:
        lines.append("\t".join(str(row[column]) for column in MANIFEST_COLUMNS))
    return lines


def resolve_master(path, work_dir):
    """Acepta el master empaquetado (.asclv, envelope ASCLVID*) o el .ascl
    pelado. Devuelve la ruta al .ascl que sabe leer el decoder de referencia."""
    with open(path, "rb") as stream:
        magic = stream.read(8)
    if magic.startswith(b"ASCLVID"):
        if not os.path.isdir(work_dir):
            os.makedirs(work_dir)
        ascl_path, _audio, _meta = ascl_bundle.unpack(path, work_dir)
        return ascl_path
    return path


def emit_streams(ffmpeg, out_dir, produced, log):
    """Empaqueta las piezas ya emitidas en HLS y DASH, por remux. Devuelve una
    fila de manifiesto por empaquetado: `file` apunta al playlist/manifiesto y
    `bytes` es el total de la carpeta (playlist + init + segmentos), porque lo
    que se reproduce es el conjunto, no un archivo."""
    rows = []
    for stream in STREAMS:
        source = produced.get(stream["source"])
        if not source:
            continue
        directory = os.path.join(out_dir, stream["dir"])
        if not os.path.isdir(directory):
            os.makedirs(directory)
        command = build_segment_command(ffmpeg, stream, source, directory)
        log("+ " + stream["id"] + " (remux, sin recodificar)")
        errlog = open(os.path.join(out_dir, stream["id"] + ".ffmpeg.log"), "wb")
        try:
            code = subprocess.call(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=errlog)
        finally:
            errlog.close()
        if code != 0:
            raise RuntimeError("ffmpeg fallo (%d) empaquetando %s (ver %s.ffmpeg.log)"
                               % (code, stream["id"], stream["id"]))
        playlist = os.path.join(directory, stream["playlist"])
        total = directory_bytes(directory)
        pieces = len(os.listdir(directory)) - 1
        rows.append({
            "id": stream["id"],
            "role": stream["role"],
            "mime": stream["mime"],
            "file": stream["dir"] + "/" + stream["playlist"],
            "bytes": total,
            "sha256": sha256_of(playlist),
            "note": stream["note"] + "; %d segmentos" % pieces,
        })
        log("  %-18s %10d B  %s (%d segmentos)" %
            (stream["id"], total, rows[-1]["file"], pieces))
    return rows


def emit(master_path, out_dir, only=None, max_frames=None, ffmpeg=None,
         work_dir=None, log=None, segment=True, x264_extra=None):
    log = log or (lambda message: None)
    ffmpeg = ffmpeg or _resolve_ffmpeg()
    variants = [variant_by_id(name) for name in only] if only else list(VARIANTS)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    work_dir = work_dir or os.path.join(out_dir, "work")

    master_sha = sha256_of(master_path)
    ascl_path = resolve_master(master_path, work_dir)
    header, _ramp, cells_list, palettes = decode_all(ascl_path)
    width, height, fps = header["cols"], header["rows"], header["fps"]
    frames = len(cells_list)
    if max_frames:
        frames = min(frames, max_frames)
    log("master %s  %dx%d @%d  %d cuadros" %
        (master_sha[:12], width, height, fps, frames))

    running = []
    logs = []
    for variant in variants:
        out_path = os.path.join(out_dir, variant["file"])
        command = build_command(ffmpeg, variant, width, height, fps, out_path,
                                x264_extra=x264_extra)
        log("+ " + variant["id"])
        # El stderr de cada encoder va a su propio archivo: sin eso, un fallo
        # solo deja un codigo de salida y no se puede diagnosticar la corrida.
        stderr = open(os.path.join(out_dir, variant["id"] + ".ffmpeg.log"), "wb")
        logs.append(stderr)
        running.append((variant, out_path, subprocess.Popen(
            command, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=stderr)))

    # Se decodifica el master UNA sola vez y el mismo cuadro alimenta a todos
    # los encoders: asi las piezas son comparables por construccion (misma
    # entrada exacta) y no se paga la decodificacion N veces.
    for index in range(frames):
        rgb = cells_to_rgb(header, cells_list[index], palettes[index])
        raw_rgb = rgb.tobytes()
        raw_rgba = None
        for variant, _out_path, process in running:
            if variant["pix_in"] == "rgba":
                if raw_rgba is None:
                    raw_rgba = confetti_rgba(width, height, index).tobytes()
                payload = raw_rgba
            else:
                payload = raw_rgb
            try:
                process.stdin.write(payload)
            except (IOError, OSError):
                raise RuntimeError(
                    "el encoder de %s murio en el cuadro %d (ver %s.ffmpeg.log)"
                    % (variant["id"], index, variant["id"]))

    rows = []
    for variant, out_path, process in running:
        process.stdin.close()
        code = process.wait()
        if code != 0:
            raise RuntimeError("ffmpeg fallo (%d) emitiendo %s (ver %s.ffmpeg.log)"
                               % (code, variant["id"], variant["id"]))
        size = os.path.getsize(out_path)
        rows.append({
            "id": variant["id"],
            "role": variant["role"],
            "mime": variant["mime"],
            "file": variant["file"],
            "bytes": size,
            "sha256": sha256_of(out_path),
            "note": variant["note"],
        })
        log("  %-18s %10d B  %s" % (variant["id"], size, variant["file"]))
    for handle in logs:
        handle.close()

    if segment:
        produced = {}
        for row in rows:
            produced[row["id"]] = os.path.join(out_dir, row["file"])
        rows = rows + emit_streams(ffmpeg, out_dir, produced, log)

    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    with open(manifest_path, "w") as stream:
        stream.write("\n".join(
            manifest_lines(rows, master_sha, width, height, fps, frames)) + "\n")
    return {"rows": rows, "manifest": manifest_path, "master_sha256": master_sha,
            "width": width, "height": height, "fps": fps, "frames": frames}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("master", help="master .asclv (envelope) o .ascl pelado")
    parser.add_argument("--out", default="outputs/v0", help="carpeta de salida")
    parser.add_argument("--only", action="append", default=None,
                        help="emitir solo esta pieza (repetible); ids: "
                             + ", ".join(v["id"] for v in VARIANTS))
    parser.add_argument("--frames", type=int, default=None,
                        help="cortar en N cuadros (pruebas de humo)")
    parser.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg")
    parser.add_argument("--no-segment", action="store_true",
                        help="no empaquetar HLS/DASH (por defecto se empaquetan)")
    parser.add_argument("--x264-extra", default=None,
                        help="H-14: opciones extra pegadas a -x264-params "
                             "(p. ej. cpu-independent=1)")
    args = parser.parse_args(argv)

    result = emit(args.master, args.out, only=args.only, max_frames=args.frames,
                  ffmpeg=args.ffmpeg, segment=not args.no_segment,
                  x264_extra=args.x264_extra,
                  log=lambda message: print(message, flush=True))
    print("-- PACK v0 --  %s" % result["manifest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
