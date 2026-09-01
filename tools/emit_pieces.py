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
  v0-vp9-alpha.webm      el personaje sin fondo, compuesto por el navegador (S4)
  MANIFEST.tsv           el embrion del manifiesto del formato

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

X264_BASELINE = "bframes=0:ref=1:keyint=%d:min-keyint=%d:scenecut=0:threads=1" % (GOP, GOP)
X264_MAIN = "bframes=0:ref=1:keyint=%d:min-keyint=%d:scenecut=0:threads=1:cabac=1" % (GOP, GOP)

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
        "note": "personaje sin fondo: alfa compuesta por el navegador",
        "args": ["-c:v", "libvpx-vp9", "-crf", str(CRF_VP9), "-b:v", "0",
                 "-deadline", "good", "-cpu-used", "2",
                 "-g", str(GOP), "-keyint_min", str(GOP), "-row-mt", "0",
                 "-auto-alt-ref", "0", "-pix_fmt", "yuva420p"],
    },
)

MANIFEST_NAME = "MANIFEST.tsv"
MANIFEST_COLUMNS = ("id", "role", "mime", "file", "bytes", "sha256", "note")


def variant_by_id(variant_id):
    for variant in VARIANTS:
        if variant["id"] == variant_id:
            return variant
    raise KeyError(variant_id)


def build_command(ffmpeg, variant, width, height, fps, out_path):
    """Linea de ffmpeg de una pieza. El contenido no se toca: entra RGB crudo
    decodificado del master y sale la pieza; ningun paso re-cuantiza el look."""
    return ([ffmpeg, "-y", "-nostdin",
             "-f", "rawvideo", "-pix_fmt", variant["pix_in"],
             "-s", "%dx%d" % (width, height), "-r", str(fps), "-i", "-"]
            + list(DETERMINISM) + list(variant["args"]) + list(BITEXACT)
            + [out_path])


_GRID_CACHE = {}


def _grid(width, height):
    key = (width, height)
    grid = _GRID_CACHE.get(key)
    if grid is None:
        yy, xx = np.mgrid[0:height, 0:width]
        grid = (xx.astype(np.float32), yy.astype(np.float32))
        _GRID_CACHE[key] = grid
    return grid


def alpha_channel(width, height, index, count):
    """Mascara del sprite de prueba: un disco de borde duro que cruza el cuadro
    de izquierda a derecha, derivado SOLO del indice de cuadro (deterministico).

    Lo que se prueba con esto es la COMPOSICION -si el navegador transparenta un
    WebM con alfa y a que costo-, no el arte: el contenido definitivo sale del
    master. El borde es duro a proposito, que es el caso que mas sufre."""
    xx, yy = _grid(width, height)
    radius = height * 0.35
    span = float(max(1, count - 1))
    center_x = -radius + (width + 2.0 * radius) * (float(index) / span)
    center_y = height * 0.5
    inside = ((xx - center_x) ** 2 + (yy - center_y) ** 2) <= radius * radius
    return np.where(inside, np.uint8(255), np.uint8(0))


def rgba_frame(rgb, index, count):
    height, width = rgb.shape[0], rgb.shape[1]
    out = np.empty((height, width, 4), dtype=np.uint8)
    out[:, :, :3] = rgb
    out[:, :, 3] = alpha_channel(width, height, index, count)
    return out


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


def emit(master_path, out_dir, only=None, max_frames=None, ffmpeg=None,
         work_dir=None, log=None):
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
        command = build_command(ffmpeg, variant, width, height, fps, out_path)
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
                    raw_rgba = rgba_frame(rgb, index, frames).tobytes()
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
    for stream in logs:
        stream.close()

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
    args = parser.parse_args(argv)

    result = emit(args.master, args.out, only=args.only, max_frames=args.frames,
                  ffmpeg=args.ffmpeg, log=lambda message: print(message, flush=True))
    print("-- PACK v0 --  %s" % result["manifest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
