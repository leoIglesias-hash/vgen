#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_v2.py - H-26: la emision v2 = el video desde la FUENTE, no desde el master.

Decision del operador (2026-09-07, docs/DISENO-CALIDAD-VGEN.md s5.3): "el
look fue un medio". La cuantizacion a 256 colores existio para que el player
JS fuera fluido; el <video> por hardware no la necesita. v2 toma el clip
original y lo lleva a la base 1280@20 con color 709 explicito, y lo codifica
con las herramientas de calidad de VP9 encendidas. El master indexado (v1)
queda como plan B, no se borra.

Cadena (cada paso es una decision declarada, no un default de ffmpeg):
  fuente (archivo local o bajado + SHA-256)
    -> referencia y4m UNA vez: fps=20 (tira cuadros, no interpola), escalado
       lanczos a 1280 de ancho, matriz 709 y rango tv explicitos, yuv420p
       (E-C). Es la MISMA imagen que ven todas las piezas y la que mide el
       SSIM: "calidad" se define contra ella.
    -> v2-vp9.webm    VP9 dos pasadas + alt-ref + lag + tpl (E-D) + Opus 64k
    -> v2-h264.mp4    H.264 High crf, 3 B, ref 4 (como v1) + audio de la
                      fuente copiado si es AAC, si no AAC 96k
    -> v2-ambiente.*  la pista de audio de la fuente tal cual (mp3 -> .mp3,
                      aac -> .m4a; otra cosa -> AAC), para <audio> aparte
    -> dash-v2-vp9/   v2-vp9 segmentado solo video por remux (MSE)
    -> MANIFEST-v2.tsv mismas columnas que v0/v1 (la pagina lo anexa igual)

GOP = 1 segundo a la cadencia de la base (20 cuadros a 20 fps): los segmentos
de 1 s del anillo MSE siguen arrancando en cuadro clave cerrado.

Techo (operador: "estaria bien un techo"): TECHO_BYTES por pieza de video.
Una pieza que lo pase se MARCA en la nota del manifiesto y el programa
termina con codigo 4: se emitio, no se publica.

Determinismo (regla 5 / P-008b): `-threads 1`, muxado bit-exacto, y el
binario de referencia es el ffmpeg del bundle vgen-portable. Las dos pasadas
de VP9 escriben su log de estadisticas en work/: con un hilo deberian ser
bit-exactas entre maquinas; el workflow `portable` lo dira cuando el carril
v2 entre al CI (el operador: "debe correr lo mismo de mi PC en CI").

Barrido (la matriz v2, en el mismo script): `--barrer 30,34,38` emite
v2-vp9 a cada crf (misma receta, sin audio) y mide SSIM/PSNR contra la
referencia; `--barrer-h264 20,23` idem para H.264. Deja MATRIZ-v2.tsv y
marca las filas que superan el techo. Se elige el crf mas bajo bajo el techo
que el ojo apruebe.

H-27 (2026-09-08, la caja ve v2 «trabado» y v1 no): tres perillas para buscar
la fluidez sin tocar la receta de bytes: `--fps 15` (la cadencia de v1),
`--colores 512` (la referencia pasa por una paleta adaptativa Oklab de N
colores ANTES del encoder: tools/cuantizar_y4m.py; el SSIM se sigue midiendo
contra la referencia sin paleta) y `--sin-altref` (VP9 sin cuadros alt-ref ni
arnr/tpl, como v1: los alt-ref son cuadros OCULTOS que el decodificador tiene
que procesar sin mostrar). `--solo-vp9` no emite el H.264 (ya esta publicado).

Uso:
  python tools/emit_v2.py fuente.mp4 --out outputs/v2
  python tools/emit_v2.py fuente.mp4 --out outputs/v2 --vp9-crf 32 --h264-crf 20
  python tools/emit_v2.py fuente.mp4 --out work/matriz-v2 --barrer 28,32,36,40 --sin-piezas
  python tools/emit_v2.py fuente.mp4 --out outputs/v2-15 --fps 15 --vp9-crf 18 --solo-vp9
  python tools/emit_v2.py fuente.mp4 --out outputs/v2-512 --vp9-crf 18 --colores 512 --solo-vp9
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402

DETERMINISM = emit_pieces.DETERMINISM
BITEXACT = emit_pieces.BITEXACT

# La base (operador, 2026-09-07): 1280 de ancho ("lo que los TV box resisten
# mejor, el resto lo estiramos") a 20 cuadros ("manejables, menos que 24").
ANCHO = 1280
FPS = 20

# Techo por pieza de video: 20 MB (el ejemplo de la pregunta 4; se ajusta con
# las primeras filas).
TECHO_BYTES = 20000000

# E-C: color correcto. Etiquetas en la pieza (VUI de H.264, cabecera de VP9 y
# del contenedor) para que el aparato no adivine. La matriz de la CONVERSION
# va en el filtro `scale` de la referencia.
COLOR_709 = ["-colorspace", "bt709", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-color_range", "tv"]

# E-D: lo que la matriz H-6 nunca midio. Cuadros alt-ref (ocultos, viven
# dentro del GOP cerrado), 25 cuadros de anticipacion, filtro temporal de
# ruido (arnr) y el modelo de propagacion temporal (tpl).
VP9_CALIDAD = ["-auto-alt-ref", "1", "-lag-in-frames", "25",
               "-arnr-maxframes", "7", "-arnr-strength", "4",
               "-enable-tpl", "1"]
# H-27: la misma receta SIN alt-ref (como v1, que en la caja es fluido). Se
# conserva la anticipacion de las dos pasadas; se apagan los cuadros ocultos y
# lo que solo tiene sentido con ellos (arnr, tpl).
VP9_SIN_ALTREF = ["-auto-alt-ref", "0", "-lag-in-frames", "25"]

AUDIO_WEBM = emit_v1.AUDIO_WEBM
AUDIO_MP4 = emit_v1.AUDIO_MP4

VP9_MIME = emit_v1.VP9_MIME
H264_MIME = emit_v1.H264_MIME["high"]
DASH_VP9_MIME = emit_v1.DASH_VP9_MIME
DASH_DIR = "dash-v2-vp9"     # no pisa al dash-vp9/ de v1 cuando comparten carpeta

MANIFEST_NAME = "MANIFEST-v2.tsv"
MANIFEST_COLUMNS = emit_pieces.MANIFEST_COLUMNS
MATRIZ_NAME = "MATRIZ-v2.tsv"
MATRIZ_COLUMNS = ("id", "eje", "codec", "file", "bytes", "sha256", "cuadros",
                  "ssim_y", "ssim_all", "psnr_avg", "seg_encode", "perfil",
                  "techo", "note")

# Que hacer con la pista de la fuente segun su codec: extension, MIME y como
# entra en el mp4. `copy` = los mismos bytes que la fuente (sin encoder de
# audio en el medio: determinismo gratis).
RADIO = {
    "mp3": {"ext": "mp3", "mime": "audio/mpeg", "args": ["-c:a", "copy"], "mp4": AUDIO_MP4},
    "aac": {"ext": "m4a", "mime": "audio/mp4", "args": ["-c:a", "copy"], "mp4": ["-c:a", "copy"]},
}
RADIO_OTRO = {"ext": "m4a", "mime": "audio/mp4",
              "args": ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"],
              "mp4": AUDIO_MP4}

CODIGO_TECHO = 4


# --------------------------------------------------------------------------
# La referencia: la fuente llevada a la base, una vez.

def escala(ancho=ANCHO, fps=FPS, matriz_fuente="auto"):
    """El filtro que lleva la fuente a la base. `fps` primero (menos cuadros
    que escalar), `scale` con lanczos y la matriz de salida 709 en rango tv;
    `in_color_matrix` confia en las etiquetas de la fuente (`auto`) salvo que
    el operador diga otra cosa (una fuente HD sin etiquetar se declara
    `bt709`, no se deja adivinar como 601)."""
    return ("fps=%d,scale=%d:-2:flags=lanczos:in_color_matrix=%s"
            ":out_color_matrix=bt709:out_range=tv,format=yuv420p"
            % (fps, ancho, matriz_fuente))


def build_reference_command(ffmpeg, fuente_path, ref_path, ancho=ANCHO, fps=FPS,
                            max_frames=None, matriz_fuente="auto"):
    command = [ffmpeg, "-y", "-nostdin", "-i", fuente_path] + list(DETERMINISM)
    command += ["-map", "0:v:0", "-vf", escala(ancho, fps, matriz_fuente)]
    if max_frames:
        command += ["-frames:v", str(max_frames)]
    command += COLOR_709 + list(BITEXACT) + ["-f", "yuv4mpegpipe", ref_path]
    return command


Y4M_FRAME_HEADER = b"FRAME\n"


def read_y4m_header(path):
    """Lee la cabecera de la referencia y cuenta sus cuadros por tamano:
    (ancho, alto, fps, cuadros). Solo 4:2:0 de 8 bits, que es lo que la
    referencia escribe; otra cosa es un error, no una suposicion."""
    with open(path, "rb") as stream:
        line = stream.readline()
    fields = line.decode("ascii", "replace").split()
    if not fields or fields[0] != "YUV4MPEG2":
        raise ValueError("no es un y4m: %s" % path)
    width = height = None
    fps = None
    chroma = "420"
    for token in fields[1:]:
        if token[0] == "W":
            width = int(token[1:])
        elif token[0] == "H":
            height = int(token[1:])
        elif token[0] == "F":
            num, den = token[1:].split(":")
            fps = int(num) // int(den) if int(num) % int(den) == 0 else int(num) / float(den)
        elif token[0] == "C":
            chroma = token[1:]
    if not width or not height or fps is None:
        raise ValueError("cabecera y4m incompleta: %r" % line)
    if not chroma.startswith("420") or "p10" in chroma or "p12" in chroma:
        raise ValueError("la referencia tiene que ser 4:2:0 de 8 bits, no C%s" % chroma)
    frame_bytes = len(Y4M_FRAME_HEADER) + width * height * 3 // 2
    frames = (os.path.getsize(path) - len(line)) // frame_bytes
    return width, height, fps, frames


# --------------------------------------------------------------------------
# ffprobe: lo que la fuente y las piezas dicen de si mismas.

def ffprobe_path(ffmpeg):
    ffprobe = os.path.join(os.path.dirname(ffmpeg) or ".",
                           os.path.basename(ffmpeg).replace("ffmpeg", "ffprobe"))
    if not shutil.which(ffprobe):
        ffprobe = shutil.which("ffprobe")
    return ffprobe


def probe(ffmpeg, path, stream, entries):
    """Valores de `entries` (lista) del stream `v:0`/`a:0` via ffprobe; lista
    vacia si no hay ffprobe o el stream no existe."""
    ffprobe = ffprobe_path(ffmpeg)
    if not ffprobe:
        return []
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", stream, "-show_entries",
         "stream=" + ",".join(entries), "-of", "csv=p=0", path],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    text = result.stdout.decode("utf-8", "replace").strip()
    return text.split(",") if text else []


COLOR_ENTRIES = ("color_space", "color_range", "color_primaries", "color_transfer")


def probe_color(ffmpeg, path):
    """`espacio rango primarias transferencia` del video, o '-'. Es la
    verificacion que el diseno s2 dejo como supuesto: se guarda en el
    manifiesto para la fuente y se puede pedir por cada pieza."""
    values = probe(ffmpeg, path, "v:0", COLOR_ENTRIES)
    return " ".join(value or "unknown" for value in values) if values else "-"


def probe_audio_codec(ffmpeg, path):
    values = probe(ffmpeg, path, "a:0", ("codec_name",))
    return values[0] if values and values[0] else None


def radio_plan(codec):
    if codec is None:
        return None
    return RADIO.get(codec, RADIO_OTRO)


# --------------------------------------------------------------------------
# La receta.

def recipe(fps=FPS, vp9_crf=34, vp9_cpu=2, vp9_2pass=True, vp9_extra=None,
           h264_crf=21, h264_bframes=3, h264_refs=4, audio_codec="aac",
           sin_altref=False, colores=0, solo_vp9=False):
    """Las dos piezas de video de v2. `audio_codec` es el de la fuente: decide
    si el mp4 copia la pista o la recodifica. GOP = 1 s a la cadencia.
    H-27: `sin_altref` apaga los cuadros ocultos de VP9, `colores` solo se
    declara en la nota (la paleta se aplica a la referencia, no aca) y
    `solo_vp9` devuelve una sola pieza."""
    gop = int(round(fps))
    vp9_args = ["-c:v", "libvpx-vp9", "-crf", str(vp9_crf), "-b:v", "0",
                "-deadline", "good", "-cpu-used", str(vp9_cpu),
                "-g", str(gop), "-keyint_min", str(gop), "-row-mt", "0"]
    vp9_args += VP9_SIN_ALTREF if sin_altref else VP9_CALIDAD
    if vp9_extra:
        vp9_args += list(vp9_extra)
    vp9_args += ["-pix_fmt", "yuv420p"] + COLOR_709
    paleta = ("; %d colores (paleta adaptativa Oklab sobre la referencia)" % colores
              if colores else "")
    h264_args = ["-c:v", "libx264", "-profile:v", "high", "-level", "3.1",
                 "-preset", "slow", "-crf", str(h264_crf),
                 "-x264-params", emit_v1.x264_params("high", h264_bframes, h264_refs, gop=gop),
                 "-pix_fmt", "yuv420p"] + COLOR_709 + ["-movflags", "+faststart"]
    plan = radio_plan(audio_codec) or RADIO_OTRO
    piezas = [
        {"id": "v2-vp9", "role": "v2", "ext": "webm", "mime": VP9_MIME,
         "codec": "vp9", "args": vp9_args, "audio": AUDIO_WEBM,
         "pasadas": 2 if vp9_2pass else 1,
         "note": "VP9 crf %d cpu-used %d %s pasada%s %s%s + Opus 64k; 709 tv; %d fps; GOP %d%s" % (
             vp9_crf, vp9_cpu, "dos" if vp9_2pass else "una", "s" if vp9_2pass else "",
             "sin alt-ref (como v1) lag 25" if sin_altref else "alt-ref lag 25 tpl",
             (" " + " ".join(vp9_extra)) if vp9_extra else "", fps, gop, paleta)},
        {"id": "v2-h264", "role": "v2", "ext": "mp4", "mime": H264_MIME,
         "codec": "h264", "args": h264_args, "audio": plan["mp4"], "pasadas": 1,
         "note": "H.264 high crf %d B=%d ref=%d + %s; 709 tv; %d fps; GOP %d%s" % (
             h264_crf, h264_bframes, h264_refs,
             "audio de la fuente copiado" if plan["mp4"] == ["-c:a", "copy"] else "AAC 96k",
             fps, gop, paleta)},
    ]
    return piezas[:1] if solo_vp9 else piezas


def build_commands(ffmpeg, variant, ref_path, audio_path, out_path, passlog):
    """Las lineas de ffmpeg de una pieza, en orden. Video = la referencia
    (entrada 0); audio = la fuente (entrada 1, solo su pista a:0), o nada.
    Dos pasadas: la primera solo video a `-f null`, la segunda con el log de
    la primera. `-shortest` recorta al video, como en v1."""
    base = [ffmpeg, "-y", "-nostdin", "-i", ref_path]
    if audio_path:
        base += ["-i", audio_path]
    base += list(DETERMINISM) + ["-map", "0:v:0"]
    commands = []
    if variant.get("pasadas", 1) == 2:
        commands.append(base + list(variant["args"]) + ["-an", "-pass", "1",
                        "-passlogfile", passlog] + list(BITEXACT)
                        + ["-f", "null", os.devnull])
    final = list(base)
    if audio_path:
        final += ["-map", "1:a:0"]
    final += list(variant["args"])
    if audio_path:
        final += list(variant["audio"])
    else:
        final += ["-an"]
    if variant.get("pasadas", 1) == 2:
        final += ["-pass", "2", "-passlogfile", passlog]
    final += ["-shortest"] + list(BITEXACT) + [out_path]
    commands.append(final)
    return commands


def build_radio_command(ffmpeg, fuente_path, plan, out_path):
    """La pista de la fuente, sola. `copy` cuando el <audio> del parque la
    reproduce tal cual (mp3, aac); si no, AAC."""
    return ([ffmpeg, "-y", "-nostdin", "-i", fuente_path, "-map", "0:a:0", "-vn"]
            + list(plan["args"]) + ["-map_metadata", "-1", "-fflags", "+bitexact",
                                    "-flags:a", "+bitexact", out_path])


def build_dash_command(ffmpeg, source_path, out_dir):
    return emit_v1.build_dash_command(ffmpeg, source_path, out_dir)


# --------------------------------------------------------------------------
# Techo, manifiesto, barrido.

def supera_techo(row, techo):
    return row["role"] in ("v2", "barrido") and techo and row["bytes"] > techo


def marcar_techo(rows, techo):
    """Marca en la nota las piezas de video que pasan el techo y las devuelve."""
    fuera = []
    for row in rows:
        if supera_techo(row, techo):
            row["note"] += "; SUPERA EL TECHO (%d B)" % techo
            fuera.append(row)
    return fuera


def manifest_lines(rows, fuente_sha, fuente_nombre, fuente_color, width, height,
                   fps, frames, receta, techo, colores=0):
    lines = [
        "# pack v2 - ASCILINE-hybrid - docs/EMISION-V2.md",
        "# fuente\t%s\t%s" % (fuente_sha, fuente_nombre),
        "# fuente_color\t%s" % fuente_color,
        "# base\t%dx%d\t%s fps\t%d cuadros" % (width, height, fps, frames),
        "# receta\t%s" % receta,
        "# techo\t%d" % techo,
    ]
    if colores:
        lines.append("# colores\t%d\tpaleta adaptativa Oklab sobre la referencia (H-27)" % colores)
    lines.append("# " + "\t".join(MANIFEST_COLUMNS))
    for row in rows:
        lines.append("\t".join(str(row[column]) for column in MANIFEST_COLUMNS))
    return lines


def matriz_lines(rows, fuente_sha, width, height, fps, frames, receta, techo):
    lines = [
        "# matriz v2 - ASCILINE-hybrid - tools/emit_v2.py --barrer",
        "# fuente\t%s" % fuente_sha,
        "# base\t%dx%d\t%s fps\t%d cuadros" % (width, height, fps, frames),
        "# receta\t%s" % receta,
        "# techo\t%d" % techo,
        "# " + "\t".join(MATRIZ_COLUMNS),
    ]
    for row in rows:
        lines.append("\t".join(str(row[column]) for column in MATRIZ_COLUMNS))
    return lines


def parse_lista(text):
    """'30,34,38' -> [30, 34, 38]; vacio -> []."""
    return [int(item) for item in re.split(r"[,\s]+", text.strip()) if item] if text else []


def barrido_variants(vp9_crfs, h264_crfs, **kwargs):
    """Una variante por crf, con la receta de `recipe` y el id que dice el
    eje: v2-vp9-crf30, v2-h264-crf20. Sin audio: el barrido mide video.
    Los crf de la receta base no cuentan aca: el eje los reemplaza."""
    kwargs = dict(kwargs)
    kwargs.pop("vp9_crf", None)
    kwargs.pop("h264_crf", None)
    kwargs.pop("solo_vp9", None)      # el barrido mide lo que se le pide, entero
    variants = []
    for crf in vp9_crfs:
        vp9 = recipe(vp9_crf=crf, **kwargs)[0]
        vp9.update({"id": "v2-vp9-crf%d" % crf, "role": "barrido", "eje": "vp9-crf"})
        variants.append(vp9)
    for crf in h264_crfs:
        h264 = recipe(h264_crf=crf, **kwargs)[1]
        h264.update({"id": "v2-h264-crf%d" % crf, "role": "barrido", "eje": "h264-crf"})
        variants.append(h264)
    return variants


def resumen_markdown(rows, techo):
    lines = ["| id | eje | bytes | techo | ssim All | psnr | cuadros | s encode | perfil |",
             "|---|---|---:|:---:|---:|---:|---:|---:|---|"]
    for row in rows:
        lines.append("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["id"], row["eje"], "{:,}".format(int(row["bytes"])).replace(",", "."),
            row["techo"], row["ssim_all"], row["psnr_avg"], row["cuadros"],
            row["seg_encode"], row["perfil"]))
    lines.append("")
    lines.append("techo = %d B por pieza de video; `pasa` / `SUPERA`. SSIM y PSNR "
                 "contra la fuente llevada a la base (4:2:0), cuadro a cuadro. "
                 "El gate ultimo es el ojo del operador." % techo)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Emision.

def run(command, log_path, append=False):
    with open(log_path, "ab" if append else "wb") as errlog:
        errlog.write(("$ " + " ".join(command) + "\n").encode("utf-8"))
        errlog.flush()
        code = subprocess.call(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=errlog)
    if code != 0:
        raise RuntimeError("ffmpeg fallo (%d); ver %s" % (code, log_path))


def medir(ffmpeg, out_path, ref_path, fps):
    result = subprocess.run(emit_matrix.build_metrics_command(ffmpeg, out_path, ref_path, fps=fps),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    return emit_matrix.parse_metrics(result.stderr.decode("utf-8", "replace"))


def emit_variant(ffmpeg, variant, ref_path, audio_path, out_dir, work_dir, log,
                 fps, medir_look=True, enc_ref=None):
    """`enc_ref` (H-27) es la referencia que ENTRA al encoder cuando no es la
    misma contra la que se mide (la de la paleta); el SSIM se mide siempre
    contra `ref_path`, la fuente llevada a la base."""
    out_path = os.path.join(out_dir, variant["id"] + "." + variant["ext"])
    log_path = os.path.join(out_dir, variant["id"] + ".ffmpeg.log")
    passlog = os.path.join(work_dir, variant["id"])
    log("+ " + variant["id"] + (" (dos pasadas)" if variant.get("pasadas") == 2 else ""))
    started = time.time()
    for index, command in enumerate(build_commands(ffmpeg, variant, enc_ref or ref_path,
                                                   audio_path, out_path, passlog)):
        run(command, log_path, append=index > 0)
    elapsed = time.time() - started
    row = {
        "id": variant["id"], "role": variant["role"], "mime": variant["mime"],
        "eje": variant.get("eje", "receta"), "codec": variant.get("codec", "-"),
        "file": os.path.basename(out_path),
        "bytes": os.path.getsize(out_path),
        "sha256": emit_pieces.sha256_of(out_path),
        "cuadros": emit_matrix.count_frames(ffmpeg, out_path),
        "ssim_y": "-", "ssim_all": "-", "psnr_avg": "-",
        "seg_encode": "%.1f" % elapsed,
        "perfil": emit_matrix.probe_profile(ffmpeg, out_path),
        "techo": "-", "note": variant["note"],
    }
    if medir_look:
        row.update(medir(ffmpeg, out_path, ref_path, fps))
        row["note"] += "; ssim %s psnr %s" % (row["ssim_all"], row["psnr_avg"])
    row["note"] += "; %d cuadros; %.0f s" % (row["cuadros"], elapsed)
    log("  %-16s %10d B  ssim %s  psnr %s  %d cuadros  %.0f s" % (
        row["id"], row["bytes"], row["ssim_all"], row["psnr_avg"], row["cuadros"], elapsed))
    return row


def emit(fuente_path, out_dir, ancho=ANCHO, fps=FPS, variants=None, max_frames=None,
         ffmpeg=None, log=None, receta="", techo=TECHO_BYTES, matriz_fuente="auto",
         barrer_vp9=(), barrer_h264=(), keep_pieces=True, medir_look=True,
         recipe_kwargs=None, fuente_sha256=None, colores=0):
    log = log or (lambda message: None)
    ffmpeg = ffmpeg or emit_pieces._resolve_ffmpeg()
    recipe_kwargs = dict(recipe_kwargs or {})
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    work_dir = os.path.join(out_dir, "work")
    if not os.path.isdir(work_dir):
        os.makedirs(work_dir)

    fuente_sha = emit_pieces.sha256_of(fuente_path)
    if fuente_sha256 and fuente_sha.lower() != fuente_sha256.lower():
        raise RuntimeError("la fuente no es la esperada: SHA-256 %s (se esperaba %s)"
                           % (fuente_sha, fuente_sha256))
    fuente_color = probe_color(ffmpeg, fuente_path)
    audio_codec = probe_audio_codec(ffmpeg, fuente_path)
    log("fuente %s  %s  color: %s  audio: %s" % (
        fuente_sha[:12], os.path.basename(fuente_path), fuente_color, audio_codec or "sin pista"))

    ref_path = os.path.join(work_dir, "ref.y4m")
    log("+ referencia %dx? @%s (lanczos, 709 tv, yuv420p)" % (ancho, fps))
    run(build_reference_command(ffmpeg, fuente_path, ref_path, ancho, fps, max_frames,
                                matriz_fuente), ref_path + ".ffmpeg.log")
    width, height, ref_fps, frames = read_y4m_header(ref_path)
    log("  referencia %dx%d @%s  %d cuadros" % (width, height, ref_fps, frames))

    # H-27: la paleta adaptativa se aplica a la REFERENCIA, una vez, y lo que
    # sale es lo que entra a todos los encoders. Se mide contra la de antes.
    enc_ref = None
    if colores:
        import cuantizar_y4m
        enc_ref = os.path.join(work_dir, "ref-c%d.y4m" % colores)
        log("+ paleta de %d colores sobre la referencia (Oklab)" % colores)
        paleta = cuantizar_y4m.cuantizar(ref_path, enc_ref, colores, log)
        log("  referencia con paleta: %d cuadros, %.0f s" % (paleta["cuadros"], paleta["segundos"]))
        recipe_kwargs.setdefault("colores", colores)

    recipe_kwargs.setdefault("fps", fps)
    recipe_kwargs["audio_codec"] = audio_codec
    variants = variants or recipe(**recipe_kwargs)
    audio_path = fuente_path if audio_codec else None

    rows = []
    for variant in variants:
        rows.append(emit_variant(ffmpeg, variant, ref_path, audio_path, out_dir, work_dir,
                                 log, ref_fps, medir_look, enc_ref))

    plan = radio_plan(audio_codec)
    if plan:
        radio_path = os.path.join(out_dir, "v2-ambiente." + plan["ext"])
        log("+ v2-ambiente (%s)" % ("copia" if plan["args"][1] == "copy" else "AAC"))
        run(build_radio_command(ffmpeg, fuente_path, plan, radio_path),
            os.path.join(out_dir, "v2-ambiente.ffmpeg.log"))
        rows.append({
            "id": "v2-ambiente", "role": "radio", "mime": plan["mime"],
            "file": os.path.basename(radio_path), "bytes": os.path.getsize(radio_path),
            "sha256": emit_pieces.sha256_of(radio_path), "cuadros": 0,
            "note": "la pista de la fuente (%s) %s, para <audio> aparte" % (
                audio_codec, "tal cual" if plan["args"][1] == "copy" else "en AAC 128k"),
        })
        log("  %-16s %10d B" % ("v2-ambiente", rows[-1]["bytes"]))
    else:
        log("  la fuente no trae audio: piezas mudas, sin radio")

    source = os.path.join(out_dir, "v2-vp9.webm")
    if os.path.exists(source):
        dash_dir = os.path.join(out_dir, DASH_DIR)
        if not os.path.isdir(dash_dir):
            os.makedirs(dash_dir)
        log("+ %s (remux, sin recodificar)" % DASH_DIR)
        run(build_dash_command(ffmpeg, source, dash_dir),
            os.path.join(out_dir, DASH_DIR + ".ffmpeg.log"))
        segments = len(os.listdir(dash_dir)) - 2
        rows.append({
            "id": "v2-dash-vp9", "role": "stream-v2", "mime": DASH_VP9_MIME,
            "file": DASH_DIR + "/manifest.mpd",
            "bytes": emit_pieces.directory_bytes(dash_dir),
            "sha256": emit_pieces.sha256_of(os.path.join(dash_dir, "manifest.mpd")),
            "cuadros": 0,
            "note": "WebM segmentado solo video, remux de v2-vp9; %d segmentos" % segments,
        })
        log("  %-16s %10d B  %d segmentos" % ("v2-dash-vp9", rows[-1]["bytes"], segments))

    fuera = marcar_techo(rows, techo)
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    with open(manifest_path, "w") as stream:
        stream.write("\n".join(manifest_lines(
            rows, fuente_sha, os.path.basename(fuente_path), fuente_color,
            width, height, ref_fps, frames, receta, techo, colores)) + "\n")

    matriz_path = None
    matriz_rows = []
    if barrer_vp9 or barrer_h264:
        log("-- barrido --")
        for variant in barrido_variants(barrer_vp9, barrer_h264, **recipe_kwargs):
            row = emit_variant(ffmpeg, variant, ref_path, None, out_dir, work_dir, log,
                               ref_fps, True, enc_ref)
            row["techo"] = "SUPERA" if supera_techo(row, techo) else "pasa"
            matriz_rows.append(row)
            if not keep_pieces:
                os.remove(os.path.join(out_dir, row["file"]))
        matriz_path = os.path.join(out_dir, MATRIZ_NAME)
        with open(matriz_path, "w") as stream:
            stream.write("\n".join(matriz_lines(matriz_rows, fuente_sha, width, height,
                                                ref_fps, frames, receta, techo)) + "\n")

    for row in rows:
        if row["role"] == "v2":
            row["techo"] = "SUPERA" if row in fuera else "pasa"
    return {"rows": rows, "manifest": manifest_path, "fuente_sha256": fuente_sha,
            "fuente_color": fuente_color, "audio": audio_codec,
            "width": width, "height": height, "fps": ref_fps, "frames": frames,
            "fuera_de_techo": fuera, "matriz": matriz_path, "matriz_rows": matriz_rows}


# --------------------------------------------------------------------------

def receta_de(args):
    """La receta como texto CANONICO: solo lo que decide los bytes, en orden
    fijo, sin rutas ni carpetas. Asi el manifiesto de la PC y el del CI
    coinciden aunque la fuente viva en otro path."""
    parts = ["--ancho", str(args.ancho), "--fps", str(args.fps),
             "--vp9-crf", str(args.vp9_crf), "--vp9-cpu", str(args.vp9_cpu)]
    if args.vp9_1pass:
        parts.append("--vp9-1pass")
    if args.vp9_extra:
        parts += ["--vp9-extra", '"%s"' % args.vp9_extra]
    if getattr(args, "sin_altref", False):
        parts.append("--sin-altref")
    if getattr(args, "colores", 0):
        parts += ["--colores", str(args.colores)]
    if getattr(args, "solo_vp9", False):
        parts.append("--solo-vp9")
    parts += ["--h264-crf", str(args.h264_crf), "--h264-bframes", str(args.h264_bframes),
              "--h264-refs", str(args.h264_refs), "--techo", str(args.techo)]
    if args.matriz_fuente != "auto":
        parts += ["--matriz-fuente", args.matriz_fuente]
    if args.frames:
        parts += ["--frames", str(args.frames)]
    return " ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente", help="el clip original (mp4/mov/...)")
    parser.add_argument("--fuente-sha256", default=None,
                        help="SHA-256 esperado de la fuente (se verifica antes de emitir)")
    parser.add_argument("--out", default="outputs/v2", help="carpeta de salida")
    parser.add_argument("--ancho", type=int, default=ANCHO)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--frames", type=int, default=None,
                        help="cortar en N cuadros de la base (pruebas de humo)")
    parser.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg")
    parser.add_argument("--matriz-fuente", default="auto",
                        help="matriz de color de la fuente si no viene etiquetada (bt709, bt601)")
    parser.add_argument("--vp9-crf", type=int, default=34)
    parser.add_argument("--vp9-cpu", type=int, default=2)
    parser.add_argument("--vp9-1pass", action="store_true", help="una pasada (acota, no es la receta)")
    parser.add_argument("--vp9-extra", default="",
                        help='opciones extra del encoder VP9, p. ej. "-aq-mode 1"')
    parser.add_argument("--sin-altref", action="store_true",
                        help="H-27: VP9 sin cuadros alt-ref ni arnr/tpl (como v1)")
    parser.add_argument("--colores", type=int, default=0,
                        help="H-27: paleta adaptativa Oklab de N colores sobre la referencia (0 = no)")
    parser.add_argument("--solo-vp9", action="store_true",
                        help="H-27: no emitir el H.264 (ya esta publicado)")
    parser.add_argument("--h264-crf", type=int, default=21)
    parser.add_argument("--h264-bframes", type=int, default=3)
    parser.add_argument("--h264-refs", type=int, default=4)
    parser.add_argument("--techo", type=int, default=TECHO_BYTES,
                        help="bytes maximos por pieza de video (se marca, no se publica)")
    parser.add_argument("--barrer", default="", help="crf de VP9 a barrer: 28,32,36,40")
    parser.add_argument("--barrer-h264", default="", help="crf de H.264 a barrer: 18,21,24")
    parser.add_argument("--sin-piezas", action="store_true",
                        help="borrar cada pieza del barrido tras medirla (solo la tabla)")
    parser.add_argument("--sin-medir", action="store_true",
                        help="no medir SSIM/PSNR de las piezas de la receta")
    args = parser.parse_args(argv)

    extra = args.vp9_extra.split() if args.vp9_extra else None
    if args.colores and args.colores < 2:
        parser.error("--colores tiene que ser >= 2 (o 0 para no aplicar paleta)")
    recipe_kwargs = dict(vp9_crf=args.vp9_crf, vp9_cpu=args.vp9_cpu,
                         vp9_2pass=not args.vp9_1pass, vp9_extra=extra,
                         h264_crf=args.h264_crf, h264_bframes=args.h264_bframes,
                         h264_refs=args.h264_refs, sin_altref=args.sin_altref,
                         solo_vp9=args.solo_vp9)
    result = emit(args.fuente, args.out, ancho=args.ancho, fps=args.fps,
                  max_frames=args.frames, ffmpeg=args.ffmpeg, receta=receta_de(args),
                  techo=args.techo, matriz_fuente=args.matriz_fuente,
                  barrer_vp9=parse_lista(args.barrer), barrer_h264=parse_lista(args.barrer_h264),
                  keep_pieces=not args.sin_piezas, medir_look=not args.sin_medir,
                  recipe_kwargs=recipe_kwargs, fuente_sha256=args.fuente_sha256,
                  colores=args.colores,
                  log=lambda message: print(message, flush=True))
    print("-- PACK v2 --  %s" % result["manifest"])
    if result["matriz"]:
        print("-- MATRIZ v2 --  %s" % result["matriz"])
        print(resumen_markdown(result["matriz_rows"], args.techo))
    if result["fuera_de_techo"]:
        print("-- TECHO --  %s supera%s %d B: emitido, NO se publica" % (
            ", ".join(row["id"] for row in result["fuera_de_techo"]),
            "n" if len(result["fuera_de_techo"]) > 1 else "", args.techo))
        return CODIGO_TECHO
    return 0


if __name__ == "__main__":
    sys.exit(main())
