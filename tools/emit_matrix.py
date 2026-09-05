#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_matrix.py - H-6: la matriz por BYTES a igual look.

En la caja la fluidez esta saturada (E2: todo lo progresivo reproduce por
hardware sin caer cuadros) y el decodificador no es nuestro. Lo unico que
queda por comprar son BYTES: menos bytes es arranque mas corto (E4) y mas
piezas residentes en la misma cuota (H-15). Esta herramienta barre los ejes
del encoder desde el MISMO master y contesta, por variante, tres cosas:

  cuantos bytes           tamano de la pieza y % contra la referencia v0
  a que look              SSIM y PSNR contra el master (4:2:0), cuadro a cuadro
  a que costo de emision  segundos de encoder (se paga una vez, offline)

La fluidez NO se mide aca: es un gate del aparato (PLAN §3.1) y la firma el
operador con la emision v1, no un runner.

Metodo:
  1. El master se decodifica UNA vez a una referencia y4m yuv420p, con la misma
     conversion rgb24 -> yuv420p que hizo v0 (asi las filas `ref-v0-*` tienen
     que reproducir los bytes del pack publicado: es el autocontrol de la
     corrida, no una suposicion).
  2. Cada variante codifica desde esa referencia con `-threads 1` y muxado
     bit-exacto (invariante 7: mismos bytes en cualquier corrida).
  3. Cada pieza se decodifica y se compara contra la referencia con los filtros
     `ssim` y `psnr` de ffmpeg. Las piezas de cadencia variable se re-expanden
     a 15 fps antes de comparar, que es lo que hace el <video> al mostrarlas.

"Igual look" se define contra la fila de referencia del mismo codec: una
variante conserva el look si su SSIM (All) no baja mas de LOOK_TOLERANCIA
respecto de esa fila. El umbral es de trabajo -para leer la tabla-; el gate
ultimo sigue siendo el ojo del operador (PLAN §3.5).

Uso:
  python tools/emit_matrix.py master.asclv --out work/matriz --grupo vp9-crf
  python tools/emit_matrix.py master.asclv --out work/matriz --only ref-v0-vp9
  python tools/emit_matrix.py --resumen work/matriz/MATRIZ-*.tsv
"""

import argparse
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import emit_pieces  # noqa: E402  (la receta v0 es la referencia)

# Lo compartido con v0 se importa, no se copia: si la receta v0 cambia, la
# referencia de la matriz cambia con ella y la fila `ref-v0-*` lo delata.
GOP = emit_pieces.GOP
DETERMINISM = emit_pieces.DETERMINISM
BITEXACT = emit_pieces.BITEXACT
X264_COMMON = emit_pieces.X264_COMMON

# Tolerancia de "igual look" en SSIM (All) contra la fila de referencia del
# mismo codec. 0,005 de SSIM es del orden de lo que separa dos CRF vecinos
# en material plano: mas chico que eso, la tabla no distinguiria nada.
LOOK_TOLERANCIA = 0.005

# SHA-256 del pack v0 publicado (outputs/v0/MANIFEST.tsv, 2026-09-04, con
# cpu-independent=1). Las filas de referencia deben reproducirlos: si no, la
# corrida no compara contra v0 sino contra otra cosa, y se avisa.
V0_SHA256 = {
    "ref-v0-h264-baseline": "cf927d578ab993d468ada2cd2440d9a18b030a343e23ef5008ed39912ef04fdc",
    "ref-v0-h264-main": "b9b1e1f542fe4f10ff44dc53f6eb2a297bcff9e357d9c277068a088e72451890",
    "ref-v0-vp9": "5be4650747fd511aa0b54b493c3a9a1d7c24f15c630ba7d22fc1acf42543830b",
}

# Cadencia variable (S6, ahora en bytes): el cuadro que no cambia no viaja.
# `mpdecimate` descarta cuadros iguales al anterior; con hi=lo=0 y frac=1 solo
# descarta los EXACTAMENTE iguales -que en un master de paleta con zonas
# estaticas existen de verdad-, con los umbrales por defecto descarta tambien
# los "casi iguales", y la tabla dice que look cuesta eso. El cuadro clave se
# fuerza POR TIEMPO (cada 1 s), porque con cadencia variable `-g 15` ya no
# significa un segundo y el corte de segmentos tiene que seguir cayendo ahi.
VFR_EXACTOS = "mpdecimate=hi=0:lo=0:frac=1"
VFR_CASI = "mpdecimate"
VFR_ARGS = ["-fps_mode", "vfr", "-force_key_frames", "expr:gte(t,n_forced*1)"]


def _vp9(crf, cpu_used=2, extra=None):
    args = ["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0",
            "-deadline", "good", "-cpu-used", str(cpu_used),
            "-g", str(GOP), "-keyint_min", str(GOP), "-row-mt", "0"]
    if extra:
        args += list(extra)
    return args + ["-pix_fmt", "yuv420p"]


def _h264(profile, crf, params, level="3.1", tune=None):
    args = ["-c:v", "libx264", "-profile:v", profile, "-level", level,
            "-preset", "slow"]
    if tune:
        args += ["-tune", tune]
    return args + ["-crf", str(crf), "-x264-params", params,
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


# x264 con cuadros B DENTRO del GOP cerrado: el DPB crece (ref=3 o 4) y hay
# reordenamiento, que es lo que Baseline evitaba a proposito en v0. Aca se
# mide cuantos bytes compra eso; si el aparato lo paga en fluidez, lo dira el
# gate del aparato, no esta tabla.
X264_B2 = ("bframes=2:b-adapt=1:ref=3:keyint=%d:min-keyint=%d:scenecut=0"
           ":threads=1:cpu-independent=1" % (GOP, GOP))
X264_B3 = ("bframes=3:b-adapt=2:ref=4:8x8dct=1:keyint=%d:min-keyint=%d"
           ":scenecut=0:threads=1:cpu-independent=1" % (GOP, GOP))
X264_DEFAULT_GOP = ("keyint=%d:min-keyint=%d:scenecut=0:threads=1"
                    ":cpu-independent=1" % (GOP, GOP))

# Una fila = una pieza. `eje` agrupa las filas que contestan la misma
# pregunta y es el grupo que corre en paralelo en CI. El orden dentro de un
# eje es el orden de lectura de la tabla, no una preferencia.
VARIANTS = (
    # -- referencia: v0 tal cual (autocontrol) y los defaults de ffmpeg -------
    {"id": "ref-v0-vp9", "eje": "referencia", "codec": "vp9", "ext": "webm",
     "args": list(emit_pieces.variant_by_id("v0-vp9")["args"]),
     "note": "v0 tal cual (crf 32, cpu-used 2); debe reproducir el pack"},
    {"id": "ref-v0-h264-baseline", "eje": "referencia", "codec": "h264",
     "ext": "mp4",
     "args": list(emit_pieces.variant_by_id("v0-h264-baseline")["args"]),
     "note": "v0 tal cual (crf 20, sin B, ref=1); debe reproducir el pack"},
    {"id": "ref-v0-h264-main", "eje": "referencia", "codec": "h264",
     "ext": "mp4",
     "args": list(emit_pieces.variant_by_id("v0-h264-main")["args"]),
     "note": "v0 tal cual (main, cabac); debe reproducir el pack"},
    {"id": "ref-defaults-h264", "eje": "referencia", "codec": "h264",
     "ext": "mp4",
     "args": ["-c:v", "libx264", "-x264-params",
              "threads=1:cpu-independent=1", "-pix_fmt", "yuv420p"],
     "note": "defaults de ffmpeg (medium, crf 23, GOP 250): lo que producto.mp4 nunca midio"},

    # -- vp9-crf: la curva bytes/look del carril base -------------------------
    {"id": "vp9-crf26", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(26), "note": "crf 26"},
    {"id": "vp9-crf29", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(29), "note": "crf 29"},
    {"id": "vp9-crf35", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(35), "note": "crf 35"},
    {"id": "vp9-crf38", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(38), "note": "crf 38"},
    {"id": "vp9-crf42", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(42), "note": "crf 42"},
    {"id": "vp9-crf46", "eje": "vp9-crf", "codec": "vp9", "ext": "webm",
     "args": _vp9(46), "note": "crf 46"},

    # -- vp9-velocidad: cuanto compra el tiempo de encoder (se paga una vez) --
    {"id": "vp9-cpu0", "eje": "vp9-velocidad", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, cpu_used=0), "note": "crf 32, cpu-used 0 (el mas lento)"},
    {"id": "vp9-cpu1", "eje": "vp9-velocidad", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, cpu_used=1), "note": "crf 32, cpu-used 1"},
    {"id": "vp9-cpu3", "eje": "vp9-velocidad", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, cpu_used=3), "note": "crf 32, cpu-used 3"},
    {"id": "vp9-cpu4", "eje": "vp9-velocidad", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, cpu_used=4), "note": "crf 32, cpu-used 4"},

    # -- vp9-contenido: zonas estaticas y paleta plana (E8: lo que el master
    #    le regala al codec) ---------------------------------------------------
    {"id": "vp9-screen", "eje": "vp9-contenido", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, extra=["-tune-content", "screen"]),
     "note": "crf 32, tune-content screen (paleta plana, bordes duros)"},
    {"id": "vp9-screen-crf38", "eje": "vp9-contenido", "codec": "vp9",
     "ext": "webm", "args": _vp9(38, extra=["-tune-content", "screen"]),
     "note": "crf 38, tune-content screen"},
    {"id": "vp9-film", "eje": "vp9-contenido", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, extra=["-tune-content", "film"]),
     "note": "crf 32, tune-content film (el contrario, para acotar)"},
    {"id": "vp9-aq0", "eje": "vp9-contenido", "codec": "vp9", "ext": "webm",
     "args": _vp9(32, extra=["-aq-mode", "0"]),
     "note": "crf 32, sin cuantizacion adaptativa"},
    {"id": "vp9-sin-altref", "eje": "vp9-contenido", "codec": "vp9",
     "ext": "webm",
     "args": _vp9(32, extra=["-auto-alt-ref", "0", "-lag-in-frames", "0"]),
     "note": "crf 32, sin alt-ref ni lag: cuanto compra el cuadro oculto"},

    # -- h264-piso: relajar el piso universal ---------------------------------
    {"id": "h264-baseline-crf23", "eje": "h264-piso", "codec": "h264",
     "ext": "mp4", "args": _h264("baseline", 23, X264_COMMON),
     "note": "baseline v0 con crf 23"},
    {"id": "h264-baseline-crf26", "eje": "h264-piso", "codec": "h264",
     "ext": "mp4", "args": _h264("baseline", 26, X264_COMMON),
     "note": "baseline v0 con crf 26"},
    {"id": "h264-main-b2", "eje": "h264-piso", "codec": "h264", "ext": "mp4",
     "args": _h264("main", 20, X264_B2 + ":cabac=1"),
     "note": "main, 2 B dentro del GOP cerrado, ref=3"},
    {"id": "h264-high-b3", "eje": "h264-piso", "codec": "h264", "ext": "mp4",
     "args": _h264("high", 20, X264_B3 + ":cabac=1"),
     "note": "high, 3 B, ref=4, 8x8dct"},
    {"id": "h264-high-b3-crf23", "eje": "h264-piso", "codec": "h264",
     "ext": "mp4", "args": _h264("high", 23, X264_B3 + ":cabac=1"),
     "note": "high, 3 B, ref=4, 8x8dct, crf 23"},
    {"id": "h264-main-animation", "eje": "h264-piso", "codec": "h264",
     "ext": "mp4",
     "args": _h264("main", 20, X264_COMMON + ":cabac=1", tune="animation"),
     "note": "main v0 con tune animation (zonas planas)"},

    # -- cadencia: S6 medido en bytes -----------------------------------------
    {"id": "vp9-vfr-exactos", "eje": "cadencia", "codec": "vp9", "ext": "webm",
     "vf": VFR_EXACTOS, "args": _vp9(32) + VFR_ARGS,
     "note": "crf 32, solo se omiten cuadros EXACTAMENTE iguales al anterior"},
    {"id": "vp9-vfr-casi", "eje": "cadencia", "codec": "vp9", "ext": "webm",
     "vf": VFR_CASI, "args": _vp9(32) + VFR_ARGS,
     "note": "crf 32, se omiten cuadros casi iguales (mpdecimate por defecto)"},
    {"id": "h264-baseline-vfr-exactos", "eje": "cadencia", "codec": "h264",
     "ext": "mp4", "vf": VFR_EXACTOS,
     "args": _h264("baseline", 20, X264_COMMON) + VFR_ARGS,
     "note": "baseline v0, solo cuadros exactamente iguales omitidos"},
)

GRUPOS = ("referencia", "vp9-crf", "vp9-velocidad", "vp9-contenido",
          "h264-piso", "cadencia")

REFERENCIA_DE = {"vp9": "ref-v0-vp9", "h264": "ref-v0-h264-baseline"}

TSV_NAME = "MATRIZ-%s.tsv"
COLUMNS = ("id", "eje", "codec", "file", "bytes", "sha256", "cuadros",
           "ssim_y", "ssim_all", "psnr_avg", "seg_encode", "perfil", "note")


def variant_by_id(variant_id):
    for variant in VARIANTS:
        if variant["id"] == variant_id:
            return variant
    raise KeyError(variant_id)


def variants_of(grupo):
    return [variant for variant in VARIANTS if variant["eje"] == grupo]


def build_reference_command(ffmpeg, width, height, fps, ref_path):
    """rgb24 crudo por el pipe -> y4m yuv420p, con la MISMA conversion que en
    v0 hacia el propio comando del encoder (`-pix_fmt yuv420p` sobre entrada
    rawvideo rgb24). Es lo que permite que `ref-v0-*` reproduzca los bytes."""
    return [ffmpeg, "-y", "-nostdin",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", "%dx%d" % (width, height), "-r", str(fps), "-i", "-",
            "-pix_fmt", "yuv420p", "-f", "yuv4mpegpipe", ref_path]


def build_command(ffmpeg, variant, ref_path, out_path):
    """Linea de ffmpeg de una variante, desde la referencia y4m. `vf` (si
    existe) va ANTES de los argumentos del encoder: decide que cuadros entran,
    no como se codifican."""
    command = [ffmpeg, "-y", "-nostdin", "-i", ref_path] + list(DETERMINISM)
    if variant.get("vf"):
        command += ["-vf", variant["vf"]]
    return command + list(variant["args"]) + list(BITEXACT) + [out_path]


def build_metrics_command(ffmpeg, out_path, ref_path):
    """Decodifica la pieza y la compara contra la referencia con `ssim` y
    `psnr` en UNA pasada. `fps=15` re-expande las piezas de cadencia variable
    -repite el cuadro mientras dura, como hace el <video>- y no cambia nada en
    las de cadencia fija."""
    graph = ("[0:v]fps=15,format=yuv420p,split[a][b];"
             "[1:v]split[c][d];[a][c]ssim;[b][d]psnr")
    return [ffmpeg, "-nostdin", "-i", out_path, "-i", ref_path,
            "-lavfi", graph, "-f", "null", "-"]


# ffmpeg imprime cada valor seguido de su dB entre parentesis: "Y:0.98 (19.1) U:...".
SSIM_RE = re.compile(r"SSIM Y:([0-9.]+)(?: \([^)]*\))? U:([0-9.]+)(?: \([^)]*\))?"
                     r" V:([0-9.]+)(?: \([^)]*\))? All:([0-9.]+)")
PSNR_RE = re.compile(r"PSNR y:([0-9.inf]+) u:([0-9.inf]+) v:([0-9.inf]+) average:([0-9.inf]+)")
FRAME_RE = re.compile(r"frame=\s*(\d+)")


def parse_metrics(stderr_text):
    """Extrae SSIM (Y, All), PSNR promedio y cuadros comparados de la salida
    de los filtros. Devuelve '-' donde no hubo dato: una fila incompleta se
    lee, no se inventa."""
    ssim_y = ssim_all = psnr = "-"
    match = SSIM_RE.search(stderr_text)
    if match:
        ssim_y, ssim_all = match.group(1), match.group(4)
    match = PSNR_RE.search(stderr_text)
    if match:
        psnr = match.group(4)
    frames = FRAME_RE.findall(stderr_text)
    return {"ssim_y": ssim_y, "ssim_all": ssim_all, "psnr_avg": psnr,
            "cuadros_comparados": int(frames[-1]) if frames else 0}


def count_frames(ffmpeg, path):
    """Cuadros que la pieza tiene de verdad (los que codifico el encoder),
    sin re-expandir: es la columna que dice cuanto omitio la cadencia
    variable."""
    result = subprocess.run([ffmpeg, "-nostdin", "-i", path, "-map", "0:v",
                             "-f", "null", "-"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    frames = FRAME_RE.findall(result.stderr.decode("utf-8", "replace"))
    return int(frames[-1]) if frames else 0


def probe_profile(ffmpeg, path):
    """`codec perfil nivel` via ffprobe si esta al lado de ffmpeg; '-' si no.
    Es lo que el aparato mira antes de decidir si decodifica por hardware."""
    ffprobe = os.path.join(os.path.dirname(ffmpeg) or ".",
                           os.path.basename(ffmpeg).replace("ffmpeg", "ffprobe"))
    if not shutil.which(ffprobe):
        ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return "-"
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,profile,level", "-of", "csv=p=0", path],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    text = result.stdout.decode("utf-8", "replace").strip().replace(",", " ")
    return text or "-"


def sha256_of(path):
    return emit_pieces.sha256_of(path)


def tsv_lines(rows, master_sha, width, height, fps, frames, grupo):
    lines = [
        "# matriz H-6 - ASCILINE-hybrid - tools/emit_matrix.py",
        "# master\t%s" % master_sha,
        "# base\t%dx%d\t%d fps\t%d cuadros\tgrupo %s" % (width, height, fps,
                                                          frames, grupo),
        "# " + "\t".join(COLUMNS),
    ]
    for row in rows:
        lines.append("\t".join(str(row[column]) for column in COLUMNS))
    return lines


def read_tsv(path):
    """Lee un MATRIZ-*.tsv (o varios concatenados). Devuelve filas como dicts;
    ignora comentarios. El formato es texto tabulado a proposito: se lee con
    `cut` en un runner y con ES5 en un aparato."""
    rows = []
    with open(path, "r") as stream:
        for line in stream:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != len(COLUMNS):
                raise ValueError("fila con %d columnas (esperadas %d): %r"
                                 % (len(parts), len(COLUMNS), line))
            rows.append(dict(zip(COLUMNS, parts)))
    return rows


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resumen(rows, tolerancia=LOOK_TOLERANCIA):
    """Tabla de lectura: bytes y % contra la referencia del codec, look
    conservado o no, y el veredicto de autocontrol de las filas v0. Devuelve
    filas enriquecidas (dicts) en el orden de VARIANTS; las que no corrieron
    no aparecen."""
    by_id = {}
    for row in rows:
        by_id[row["id"]] = row
    out = []
    for variant in VARIANTS:
        row = by_id.get(variant["id"])
        if not row:
            continue
        ref = by_id.get(REFERENCIA_DE[variant["codec"]])
        size = _num(row["bytes"])
        ssim = _num(row["ssim_all"])
        pct = look = "-"
        if ref and size is not None and _num(ref["bytes"]):
            pct = "%.1f" % (100.0 * size / _num(ref["bytes"]))
        if ref and ssim is not None and _num(ref["ssim_all"]) is not None:
            look = "=" if ssim >= _num(ref["ssim_all"]) - tolerancia else "-"
        esperado = V0_SHA256.get(variant["id"])
        autocontrol = "-"
        if esperado:
            autocontrol = "v0 IDENTICA" if row["sha256"] == esperado else "v0 DISTINTA"
        enriched = dict(row)
        enriched["pct_ref"] = pct
        enriched["look"] = look
        enriched["autocontrol"] = autocontrol
        out.append(enriched)
    return out


def resumen_markdown(rows, tolerancia=LOOK_TOLERANCIA):
    lines = ["| id | eje | bytes | % ref | cuadros | SSIM All | SSIM Y | PSNR | s enc | perfil | look | nota |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---|:---:|---|"]
    for row in resumen(rows, tolerancia):
        nota = row["note"]
        if row["autocontrol"] != "-":
            nota = row["autocontrol"] + "; " + nota
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["id"], row["eje"], row["bytes"], row["pct_ref"], row["cuadros"],
            row["ssim_all"], row["ssim_y"], row["psnr_avg"], row["seg_encode"],
            row["perfil"], row["look"], nota))
    lines.append("")
    lines.append("`look` = : SSIM All no baja mas de %.3f respecto de la referencia "
                 "de su codec (`ref-v0-vp9` / `ref-v0-h264-baseline`). "
                 "El gate ultimo es el ojo del operador." % tolerancia)
    return "\n".join(lines)


def write_reference(ffmpeg, master_path, work_dir, ref_path, max_frames, log):
    """Decodifica el master una vez y escribe la referencia y4m. Devuelve
    (sha del master, ancho, alto, fps, cuadros)."""
    master_sha = sha256_of(master_path)
    ascl_path = emit_pieces.resolve_master(master_path, work_dir)
    header, _ramp, cells_list, palettes = emit_pieces.decode_all(ascl_path)
    width, height, fps = header["cols"], header["rows"], header["fps"]
    frames = len(cells_list)
    if max_frames:
        frames = min(frames, max_frames)
    log("master %s  %dx%d @%d  %d cuadros -> %s" %
        (master_sha[:12], width, height, fps, frames, ref_path))
    command = build_reference_command(ffmpeg, width, height, fps, ref_path)
    errlog = open(ref_path + ".ffmpeg.log", "wb")
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=errlog)
    try:
        for index in range(frames):
            rgb = emit_pieces.cells_to_rgb(header, cells_list[index],
                                           palettes[index])
            process.stdin.write(rgb.tobytes())
    finally:
        process.stdin.close()
        code = process.wait()
        errlog.close()
    if code != 0:
        raise RuntimeError("ffmpeg fallo (%d) escribiendo la referencia" % code)
    return master_sha, width, height, fps, frames


def emit_one(ffmpeg, variant, ref_path, out_dir, log):
    out_path = os.path.join(out_dir, variant["id"] + "." + variant["ext"])
    command = build_command(ffmpeg, variant, ref_path, out_path)
    log("+ " + variant["id"])
    started = time.time()
    with open(os.path.join(out_dir, variant["id"] + ".ffmpeg.log"), "wb") as errlog:
        code = subprocess.call(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=errlog)
    elapsed = time.time() - started
    if code != 0:
        raise RuntimeError("ffmpeg fallo (%d) emitiendo %s (ver %s.ffmpeg.log)"
                           % (code, variant["id"], variant["id"]))
    result = subprocess.run(build_metrics_command(ffmpeg, out_path, ref_path),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    metrics = parse_metrics(result.stderr.decode("utf-8", "replace"))
    row = {
        "id": variant["id"],
        "eje": variant["eje"],
        "codec": variant["codec"],
        "file": os.path.basename(out_path),
        "bytes": os.path.getsize(out_path),
        "sha256": sha256_of(out_path),
        "cuadros": count_frames(ffmpeg, out_path),
        "ssim_y": metrics["ssim_y"],
        "ssim_all": metrics["ssim_all"],
        "psnr_avg": metrics["psnr_avg"],
        "seg_encode": "%.1f" % elapsed,
        "perfil": probe_profile(ffmpeg, out_path),
        "note": variant["note"],
    }
    log("  %-26s %10d B  ssim %s  psnr %s  %d cuadros  %.1f s" %
        (row["id"], row["bytes"], row["ssim_all"], row["psnr_avg"],
         row["cuadros"], elapsed))
    return row


def emit(master_path, out_dir, grupo=None, only=None, max_frames=None,
         ffmpeg=None, log=None, keep_pieces=True):
    log = log or (lambda message: None)
    ffmpeg = ffmpeg or emit_pieces._resolve_ffmpeg()
    if only:
        variants = [variant_by_id(name) for name in only]
        grupo = grupo or "seleccion"
    elif grupo:
        variants = variants_of(grupo)
        if not variants:
            raise KeyError("grupo desconocido: %s (hay %s)" % (grupo, ", ".join(GRUPOS)))
    else:
        variants = list(VARIANTS)
        grupo = "todo"
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    work_dir = os.path.join(out_dir, "work")
    if not os.path.isdir(work_dir):
        os.makedirs(work_dir)
    ref_path = os.path.join(work_dir, "ref.y4m")
    master_sha, width, height, fps, frames = write_reference(
        ffmpeg, master_path, work_dir, ref_path, max_frames, log)

    rows = []
    for variant in variants:
        rows.append(emit_one(ffmpeg, variant, ref_path, out_dir, log))
        if not keep_pieces:
            os.remove(os.path.join(out_dir, rows[-1]["file"]))

    tsv_path = os.path.join(out_dir, TSV_NAME % grupo)
    with open(tsv_path, "w") as stream:
        stream.write("\n".join(tsv_lines(rows, master_sha, width, height, fps,
                                         frames, grupo)) + "\n")
    return {"rows": rows, "tsv": tsv_path, "master_sha256": master_sha,
            "width": width, "height": height, "fps": fps, "frames": frames}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("master", nargs="?", help="master .asclv (envelope) o .ascl pelado")
    parser.add_argument("--out", default="work/matriz", help="carpeta de salida")
    parser.add_argument("--grupo", default=None,
                        help="emitir solo este eje: " + ", ".join(GRUPOS))
    parser.add_argument("--only", action="append", default=None,
                        help="emitir solo esta variante (repetible)")
    parser.add_argument("--frames", type=int, default=None,
                        help="cortar en N cuadros (pruebas de humo)")
    parser.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg")
    parser.add_argument("--sin-piezas", action="store_true",
                        help="borrar cada pieza tras medirla (solo la tabla)")
    parser.add_argument("--resumen", nargs="+", default=None, metavar="TSV",
                        help="no emitir: leer estos MATRIZ-*.tsv y escribir la tabla")
    args = parser.parse_args(argv)

    if args.resumen:
        rows = []
        for pattern in args.resumen:
            for path in sorted(glob.glob(pattern)) or [pattern]:
                rows += read_tsv(path)
        print(resumen_markdown(rows))
        return 0
    if not args.master:
        parser.error("falta el master (o --resumen)")
    result = emit(args.master, args.out, grupo=args.grupo, only=args.only,
                  max_frames=args.frames, ffmpeg=args.ffmpeg,
                  keep_pieces=not args.sin_piezas,
                  log=lambda message: print(message, flush=True))
    print("-- MATRIZ H-6 --  %s" % result["tsv"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
