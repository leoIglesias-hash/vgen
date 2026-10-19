#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emit_alfa.py - H-28: video con transparencia, de verdad.

Pedido del operador (2026-10-19), sobre la tabla H.264+AAC / H.265 /
VP9+alfa+Opus / VP8+alfa: "sumar vp9 y vp8 bien, h265 no lo vamos a usar... y
alguna manera de aprovechar las transparencias de canal alfa donde
corresponde". H.265 NO se emite.

Entrada: una fuente CON canal alfa (ProRes 4444, qtrle, PNG en secuencia,
WebM con alfa). Si la fuente no trae alfa, el programa se niega (codigo 3) y
dice que se use emit_v2. Un WebM con alfa se lee con el decoder de libvpx
(`-c:v libvpx-vp9` / `libvpx` ANTES del `-i`): el decoder nativo de ffmpeg
descarta el alfa sin avisar.

Cadena (cada paso es una decision declarada, no un default de ffmpeg):
  fuente -> RGBA a la base: fps (tira cuadros), escalado lanczos sobre alfa
            PREMULTIPLICADO (asi el color invisible no se mete en los bordes)
    -> pasada 1: ANALISIS del canal (INFORME-alfa.txt)
         siempre opaco? rectangulo util? cuadros vacios? alfa binario o suave?
    -> pasada 2: las PALANCAS sobre cada cuadro
         (b) RGB bajo alfa 0 limpiado: color plano (o sangrado del borde)
         (c) recorte al rectangulo util (union del clip, coordenadas pares)
         (d) cuadros vacios al principio y al final = hueco, no video
         (f) alfa binario (opcional, con umbral)
       -> referencia work/ref.yuva (yuva420p crudo, matriz 709 rango tv)
    -> alfa-vp9.webm  VP9 + alfa (yuva420p, auto-alt-ref 0) + Opus si hay audio
    -> alfa-vp8.webm  VP8 + alfa (yuva420p, auto-alt-ref 0) + Opus si hay audio
    -> MANIFEST-alfa.tsv (mismas columnas que v0/v1/v2 + lienzo, rect y tiempo)
  (a) si el canal es SIEMPRE opaco, no es una pieza alfa: avisa y emite
      opaco-vp9.webm + opaco-h264.mp4 (por hardware, mas livianas).

Cada pieza se mide contra la referencia: cuadros, PSNR de luma donde se ve
(alfa > 0), error del alfa, y la ALARMA DE COLOR (lecciones del 2026-10-18):
la luma media de lo visible contra la que dice la matriz 709 calculada aparte
del ffmpeg, desde el RGBA. Ademas la ALARMA DE ALFA: si la pieza volvio
opaca, el alfa se perdio por el camino.

`--medir-palancas` emite VP9 con cada palanca apagada de a una y deja
PALANCAS-alfa.tsv con el delta de bytes de cada una (el criterio de H-28).

Determinismo (regla 5): `-threads 1`, muxado bit-exacto, todo el trabajo de
pixeles en enteros. Opus no es cpu-independent (P-010): el video si.

Uso:
  python tools/emit_alfa.py efecto.mov --out outputs/alfa
  python tools/emit_alfa.py efecto.mov --out outputs/alfa --medir-palancas
  python tools/emit_alfa.py efecto.webm --out outputs/alfa --solo vp9 --vp9-crf 28
  python tools/emit_alfa.py --hacer-sintetico work/sintetico.mov
"""

import argparse
import os
import re
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import emit_matrix  # noqa: E402
import emit_pieces  # noqa: E402
import emit_v1  # noqa: E402
import emit_v2  # noqa: E402

DETERMINISM = emit_pieces.DETERMINISM
BITEXACT = emit_pieces.BITEXACT
COLOR_709 = emit_v2.COLOR_709
COLOR_709_ENTRADA = emit_v2.COLOR_709_ENTRADA

# La base de v2 (receta firmada el 2026-09-08: 1280 a 15 fps). El efecto va
# ENCIMA de ese video, a pantalla entera: mismo lienzo, misma cadencia.
ANCHO = 1280
FPS = 15

# Medidos con el sintetico del 2026-10-19 (docs/EMISION-ALFA.md s3): a igual
# compuesto (~39,0 dB) VP9 crf 30 = 470 KB y VP8 crf 24 = 749 KB (+59 %). Los
# dos defaults dan la MISMA imagen: lo que cambia entre piezas es el codec.
VP9_CRF = 30
VP8_CRF = 24
# VP8 con crf necesita un tope de bitrate (con -b:v 0 libvpx no hace crf).
VP8_TOPE = "4M"

# (b) Que se pinta debajo de alfa 0. Medido con el sintetico el 2026-10-19
# (docs/EMISION-ALFA.md s3): `plano` (un color, el medio de lo visible) cuesta
# 21 % menos que `sangrado` (el borde extendido 8 px y despues plano) con el
# mismo compuesto (39,03 vs 39,05 dB): el sangrado arrastra hacia afuera la
# textura del borde y el ojo no gana nada. Sin limpiar, una fuente con basura
# debajo cuesta +170 %.
LIMPIAR = "plano"
SANGRADO_PASOS = 8

CODIGO_SIN_ALFA = 3
CODIGO_ALARMA = 5

UMBRAL_SESGO_LUMA = emit_v2.UMBRAL_SESGO_LUMA

MANIFEST_NAME = "MANIFEST-alfa.tsv"
MANIFEST_COLUMNS = emit_pieces.MANIFEST_COLUMNS
INFORME_NAME = "INFORME-alfa.txt"
PALANCAS_NAME = "PALANCAS-alfa.tsv"
PALANCAS_COLUMNS = ("palanca", "file", "bytes", "delta_bytes", "delta_pct", "lienzo",
                    "cuadros", "psnr_luma_visible", "psnr_compuesto", "compuesto_vs_receta",
                    "alfa_mae", "note")

H264_MIME = emit_v1.H264_MIME["high"]


# --------------------------------------------------------------------------
# La fuente: tiene alfa? con que decoder se lee?

# pix_fmt de ffmpeg que llevan alfa (yuva*, gbrap*, rgba/bgra/argb/abgr y sus
# variantes de 16 bits, ya8/ya16 = gris con alfa).
_PIX_ALFA = re.compile(r"^(yuva|gbrap|rgba|bgra|argb|abgr|ya8|ya16|rgba64|bgra64)")


def tiene_alfa(pix_fmt, alpha_mode=""):
    """Un WebM con alfa dice pix_fmt yuv420p (el alfa viaja aparte, como
    BlockAdditional) y lo anuncia en la etiqueta ALPHA_MODE=1."""
    if str(alpha_mode).strip() == "1":
        return True
    return bool(_PIX_ALFA.match(pix_fmt or ""))


def decoder_de(codec, alpha_mode=""):
    """El decoder a poner ANTES del `-i`: el nativo de ffmpeg descarta el alfa
    de VP8/VP9; el de libvpx lo devuelve."""
    if str(alpha_mode).strip() != "1":
        return []
    if codec == "vp9":
        return ["-c:v", "libvpx-vp9"]
    if codec == "vp8":
        return ["-c:v", "libvpx"]
    return []


def parse_probe(text):
    """Salida `-of default=nw=1` de ffprobe -> dict (los tags llegan como
    TAG:alpha_mode=1)."""
    values = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.upper().startswith("TAG:"):
            key = key[4:].lower()
        values.setdefault(key, value.strip())
    return values


def probe_fuente(ffmpeg, path):
    ffprobe = emit_v2.ffprobe_path(ffmpeg)
    if not ffprobe:
        raise RuntimeError("hace falta ffprobe al lado de ffmpeg para leer la fuente")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,width,height,r_frame_rate:stream_tags=alpha_mode",
         "-of", "default=nw=1", path],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    values = parse_probe(result.stdout.decode("utf-8", "replace"))
    if "width" not in values:
        raise RuntimeError("ffprobe no encontro video en %s" % path)
    return {"codec": values.get("codec_name", "?"), "pix_fmt": values.get("pix_fmt", "?"),
            "width": int(values["width"]), "height": int(values["height"]),
            "fps": values.get("r_frame_rate", "?"), "alpha_mode": values.get("alpha_mode", "")}


# --------------------------------------------------------------------------
# La base: la fuente en RGBA al lienzo y a la cadencia.

def lienzo(ancho_fuente, alto_fuente, ancho=ANCHO):
    """(ancho, alto) del lienzo, los dos pares (4:2:0). `ancho` 0 = el de la
    fuente."""
    if not ancho:
        ancho = ancho_fuente
    ancho -= ancho % 2
    alto = int(round(alto_fuente * ancho / float(ancho_fuente) / 2.0)) * 2
    return ancho, max(alto, 2)


def filtro_base(ancho_fuente, alto_fuente, ancho, alto, fps):
    """fps primero (menos cuadros que escalar). Si hay escalado, se hace sobre
    alfa premultiplicado: un lanczos sobre alfa recto mezcla en el borde el
    color de lo invisible (el halo oscuro de los recortes)."""
    partes = ["fps=%d" % fps, "format=rgba"]
    if (ancho, alto) != (ancho_fuente, alto_fuente):
        partes += ["premultiply=inplace=1",
                   "scale=%d:%d:flags=lanczos" % (ancho, alto),
                   "unpremultiply=inplace=1", "format=rgba"]
    return ",".join(partes)


def build_rgba_command(ffmpeg, fuente_path, decoder, filtro, max_frames=None):
    command = [ffmpeg, "-v", "error", "-nostdin"] + list(decoder) + ["-i", fuente_path]
    command += list(DETERMINISM) + ["-map", "0:v:0", "-vf", filtro]
    if max_frames:
        command += ["-frames:v", str(max_frames)]
    return command + ["-f", "rawvideo", "-pix_fmt", "rgba", "-"]


def cuadros_rgba(command, ancho, alto):
    """Generador: cada cuadro como uint8 (alto, ancho, 4), escribible."""
    tam = ancho * alto * 4
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = proc.stdout.read(tam)
            if len(buf) < tam:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(alto, ancho, 4).copy()
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


# --------------------------------------------------------------------------
# Pasada 1: el analisis del canal.

class Analisis(object):
    """Acumula lo que el canal dice, cuadro a cuadro, sin guardar cuadros."""

    def __init__(self, ancho, alto):
        self.ancho = ancho
        self.alto = alto
        self.cuadros = 0
        self.vacios = []          # indices de cuadros sin un pixel visible
        self.rect = None          # union de los alfa > 0: [x0, y0, x1, y1) en pixeles
        self.visibles = 0
        self.opacos = 0
        self.semi = 0
        self.pixeles = 0
        self.suma_rgb = np.zeros(3, dtype=np.int64)

    def cuadro(self, rgba):
        alfa = rgba[:, :, 3]
        visible = alfa > 0
        n_visible = int(np.count_nonzero(visible))
        n_opaco = int(np.count_nonzero(alfa == 255))
        self.pixeles += alfa.size
        self.visibles += n_visible
        self.opacos += n_opaco
        self.semi += n_visible - n_opaco
        if n_visible == 0:
            self.vacios.append(self.cuadros)
        else:
            filas = np.flatnonzero(visible.any(axis=1))
            cols = np.flatnonzero(visible.any(axis=0))
            caja = [int(cols[0]), int(filas[0]), int(cols[-1]) + 1, int(filas[-1]) + 1]
            if self.rect is None:
                self.rect = caja
            else:
                self.rect = [min(self.rect[0], caja[0]), min(self.rect[1], caja[1]),
                             max(self.rect[2], caja[2]), max(self.rect[3], caja[3])]
            self.suma_rgb += rgba[:, :, :3][visible].sum(axis=0, dtype=np.int64)
        self.cuadros += 1

    def resumen(self):
        return resumen_canal(self.ancho, self.alto, self.cuadros, self.vacios, self.rect,
                             self.visibles, self.opacos, self.semi, self.pixeles,
                             self.suma_rgb)


def rect_par(rect, ancho, alto):
    """[x0, y0, x1, y1) -> (x, y, w, h) con todo par (4:2:0), dentro del lienzo."""
    x0, y0, x1, y1 = rect
    x0 -= x0 % 2
    y0 -= y0 % 2
    x1 = min(x1 + x1 % 2, ancho)
    y1 = min(y1 + y1 % 2, alto)
    return x0, y0, x1 - x0, y1 - y0


def tramos_vacios(vacios, cuadros):
    """(desde, hasta) = primer y ultimo+1 cuadro con algo visible, y los
    huecos INTERIORES como [(inicio, largo)]."""
    vacio = set(vacios)
    llenos = [i for i in range(cuadros) if i not in vacio]
    if not llenos:
        return 0, 0, []
    desde, hasta = llenos[0], llenos[-1] + 1
    huecos = []
    inicio = None
    for i in range(desde, hasta):
        if i in vacio:
            if inicio is None:
                inicio = i
        elif inicio is not None:
            huecos.append((inicio, i - inicio))
            inicio = None
    return desde, hasta, huecos


def resumen_canal(ancho, alto, cuadros, vacios, rect, visibles, opacos, semi, pixeles,
                  suma_rgb):
    desde, hasta, huecos = tramos_vacios(vacios, cuadros)
    siempre_opaco = cuadros > 0 and opacos == pixeles
    rect_wh = rect_par(rect, ancho, alto) if rect else (0, 0, 0, 0)
    color = tuple(int((int(v) + visibles // 2) // visibles) for v in suma_rgb) if visibles else (0, 0, 0)
    return {
        "lienzo": (ancho, alto), "cuadros": cuadros, "vacios": len(vacios),
        "desde": desde, "hasta": hasta, "huecos": huecos,
        "siempre_opaco": siempre_opaco, "rect": rect_wh,
        "area_rect": (rect_wh[2] * rect_wh[3]) / float(ancho * alto) if ancho and alto else 0.0,
        "cobertura": visibles / float(pixeles) if pixeles else 0.0,
        "semi": semi / float(visibles) if visibles else 0.0,
        "color_medio": color,
    }


def informe_lineas(fuente, resumen, fps, decisiones):
    r = resumen
    x, y, w, h = r["rect"]
    lineas = [
        "# informe del canal alfa - vgen - tools/emit_alfa.py (H-28)",
        "fuente          %s  %s %s %dx%d %s fps%s" % (
            fuente["nombre"], fuente["codec"], fuente["pix_fmt"], fuente["width"],
            fuente["height"], fuente["fps"],
            "  ALPHA_MODE=1" if fuente.get("alpha_mode") == "1" else ""),
        "lienzo          %dx%d @%d fps, %d cuadros" % (r["lienzo"][0], r["lienzo"][1], fps,
                                                       r["cuadros"]),
        "siempre opaco   %s" % ("SI: no es una pieza alfa" if r["siempre_opaco"] else "no"),
        "rect util       x %d y %d  %dx%d  = %.1f %% del lienzo" % (x, y, w, h,
                                                                    100.0 * r["area_rect"]),
        "cobertura       %.1f %% de los pixeles del clip son visibles" % (100.0 * r["cobertura"]),
        "alfa suave      %.1f %% de lo visible es semitransparente (0 < alfa < 255)" % (
            100.0 * r["semi"]),
        "tiempo          visible del cuadro %d al %d (de %d); %d cuadros vacios" % (
            r["desde"], max(r["hasta"] - 1, 0), r["cuadros"], r["vacios"]),
        "huecos          %s" % (", ".join("%d+%d" % hueco for hueco in r["huecos"])
                                or "ninguno adentro"),
        "color medio     rgb%s (el plano de lo invisible)" % (r["color_medio"],),
        "",
        "# decisiones",
    ]
    lineas += decisiones
    return lineas


# --------------------------------------------------------------------------
# Pasada 2: las palancas, cuadro a cuadro. Todo en enteros.

_VECINOS = ((0, 1), (0, -1), (1, 0), (-1, 0))


def sangrar(rgb, conocido, pasos=SANGRADO_PASOS):
    """Extiende el color de lo conocido hacia lo desconocido, `pasos` pixeles:
    cada pixel nuevo toma el promedio (redondeado) de sus vecinos 4-conexos
    conocidos. Devuelve la mascara de conocidos al final."""
    conocido = conocido.copy()
    alto, ancho = conocido.shape
    for _ in range(pasos):
        suma = np.zeros((alto, ancho, 3), dtype=np.int32)
        cuenta = np.zeros((alto, ancho), dtype=np.int32)
        for dy, dx in _VECINOS:
            ys = slice(max(dy, 0), alto + min(dy, 0))
            yd = slice(max(-dy, 0), alto + min(-dy, 0))
            xs = slice(max(dx, 0), ancho + min(dx, 0))
            xd = slice(max(-dx, 0), ancho + min(-dx, 0))
            fuente = conocido[ys, xs]
            suma[yd, xd] += rgb[ys, xs].astype(np.int32) * fuente[:, :, None]
            cuenta[yd, xd] += fuente
        nuevos = (~conocido) & (cuenta > 0)
        if not nuevos.any():
            break
        c = cuenta[nuevos][:, None]
        rgb[nuevos] = ((suma[nuevos] + c // 2) // c).astype(np.uint8)
        conocido |= nuevos
    return conocido


def limpiar(rgba, modo, color):
    """(b) Lo que hay debajo de alfa 0 no se ve: no gastar bits en eso.
    `plano` = un color (el de la receta); `sangrado` = el borde visible
    extendido hacia afuera + color plano; `no` = tal cual."""
    if modo == "no":
        return rgba
    invisible = rgba[:, :, 3] == 0
    if not invisible.any():
        return rgba
    rgb = rgba[:, :, :3]
    conocido = ~invisible
    if modo == "sangrado" and conocido.any():
        conocido = sangrar(rgb, conocido)
    rgb[~conocido] = color
    return rgba


def binarizar(rgba, umbral):
    """(f) Alfa todo o nada: >= umbral es opaco, el resto invisible."""
    alfa = rgba[:, :, 3]
    rgba[:, :, 3] = np.where(alfa >= umbral, 255, 0).astype(np.uint8)
    return rgba


def recortar(rgba, rect):
    x, y, w, h = rect
    return rgba[y:y + h, x:x + w]


KR, KB = 0.2126, 0.0722


def luma_709(rgb):
    """La luma que dice la matriz 709 en rango tv, calculada aca y no por
    ffmpeg: el patron independiente de la alarma de color."""
    r = rgb[:, :, 0].astype(np.float64)
    g = rgb[:, :, 1].astype(np.float64)
    b = rgb[:, :, 2].astype(np.float64)
    return 16.0 + 219.0 * (KR * r + (1.0 - KR - KB) * g + KB * b) / 255.0


def build_ref_command(ffmpeg, ancho, alto, fps, ref_path):
    """RGBA por stdin -> yuva420p crudo con la matriz 709 y rango tv
    DECLARADOS en la conversion (la entrada es RGB: no hay matriz que adivinar)."""
    return [ffmpeg, "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", "%dx%d" % (ancho, alto), "-r", str(fps), "-i", "-"] + list(DETERMINISM) + [
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuva420p",
            "-f", "rawvideo", "-pix_fmt", "yuva420p", ref_path]


def escribir_referencia(ffmpeg, rgba_command, ancho, alto, fps, ref_path, resumen,
                        limpiar_modo=LIMPIAR, recorte=True, tiempo=True, umbral=0):
    """Pasada 2: aplica las palancas y escribe la referencia. Devuelve el
    patron de la alarma de color: por cuadro, (suma de luma 709 de lo
    visible, pixeles visibles)."""
    rect = resumen["rect"] if recorte and resumen["rect"][2] else (0, 0, ancho, alto)
    desde, hasta = (resumen["desde"], resumen["hasta"]) if tiempo else (0, resumen["cuadros"])
    patron = []
    proc = subprocess.Popen(build_ref_command(ffmpeg, rect[2], rect[3], fps, ref_path),
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        for index, rgba in enumerate(cuadros_rgba(rgba_command, ancho, alto)):
            if index < desde or index >= hasta:
                continue
            if umbral:
                binarizar(rgba, umbral)
            limpiar(rgba, limpiar_modo, resumen["color_medio"])
            cuadro = np.ascontiguousarray(recortar(rgba, rect))
            visible = cuadro[:, :, 3] > 0
            patron.append((float(luma_709(cuadro)[visible].sum()), int(np.count_nonzero(visible))))
            proc.stdin.write(cuadro.tobytes())
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise RuntimeError("ffmpeg fallo (%d) al escribir la referencia %s" % (code, ref_path))
    return {"rect": rect, "desde": desde, "hasta": hasta, "patron": patron}


# --------------------------------------------------------------------------
# La receta.

def mime(codec, audio):
    if codec == "h264":
        return H264_MIME if audio else H264_MIME.replace(", mp4a.40.2", "")
    return 'video/webm; codecs="%s%s"' % (codec, ", opus" if audio else "")


def recipe(fps=FPS, vp9_crf=VP9_CRF, vp8_crf=VP8_CRF, vp8_tope=VP8_TOPE, vp9_2pass=False,
           opaco=False, solo=None, audio=False, h264_crf=21):
    """Las piezas. Alfa: VP9 y VP8 en yuva420p con auto-alt-ref 0 (libvpx no
    codifica alfa con alt-ref). Opaco: VP9 y H.264 en yuv420p, la receta de
    v2 en chico. GOP = 1 s a la cadencia."""
    gop = int(round(fps))
    pix = "yuv420p" if opaco else "yuva420p"
    prefijo = "opaco" if opaco else "alfa"
    vp9 = ["-c:v", "libvpx-vp9", "-crf", str(vp9_crf), "-b:v", "0", "-deadline", "good",
           "-cpu-used", "2", "-g", str(gop), "-keyint_min", str(gop), "-row-mt", "0",
           "-auto-alt-ref", "0", "-lag-in-frames", "25", "-pix_fmt", pix] + COLOR_709
    piezas = [{"id": prefijo + "-vp9", "codec": "vp9", "ext": "webm", "args": vp9,
               "audio": emit_v1.AUDIO_WEBM, "pasadas": 2 if vp9_2pass else 1,
               "decoder": ["-c:v", "libvpx-vp9"], "alfa": not opaco,
               "note": "VP9 crf %d %s pasada%s %s; 709 tv; %d fps; GOP %d" % (
                   vp9_crf, "dos" if vp9_2pass else "una", "s" if vp9_2pass else "",
                   "sin alfa (el canal era siempre opaco)" if opaco else "+ alfa (yuva420p)",
                   fps, gop)}]
    if opaco:
        h264 = ["-c:v", "libx264", "-profile:v", "high", "-level", "3.1", "-preset", "slow",
                "-crf", str(h264_crf), "-x264-params", emit_v1.x264_params("high", 3, 4, gop=gop),
                "-pix_fmt", "yuv420p"] + COLOR_709 + ["-movflags", "+faststart"]
        piezas.append({"id": "opaco-h264", "codec": "h264", "ext": "mp4", "args": h264,
                       "audio": emit_v1.AUDIO_MP4, "pasadas": 1, "decoder": [], "alfa": False,
                       "note": "H.264 high crf %d; 709 tv; %d fps; GOP %d (el canal era "
                               "siempre opaco)" % (h264_crf, fps, gop)})
    else:
        vp8 = ["-c:v", "libvpx", "-crf", str(vp8_crf), "-b:v", str(vp8_tope),
               "-deadline", "good", "-cpu-used", "1", "-g", str(gop), "-keyint_min", str(gop),
               "-auto-alt-ref", "0", "-lag-in-frames", "25", "-pix_fmt", "yuva420p"] + COLOR_709
        piezas.append({"id": "alfa-vp8", "codec": "vp8", "ext": "webm", "args": vp8,
                       "audio": emit_v1.AUDIO_WEBM, "pasadas": 1,
                       "decoder": ["-c:v", "libvpx"], "alfa": True,
                       "note": "VP8 crf %d tope %s + alfa (yuva420p); 709 tv; %d fps; GOP %d" % (
                           vp8_crf, vp8_tope, fps, gop)})
    for pieza in piezas:
        pieza["mime"] = mime(pieza["codec"], audio)
        if audio:
            pieza["note"] += "; + %s" % ("AAC 96k" if pieza["codec"] == "h264" else "Opus 64k")
    if solo:
        piezas = [pieza for pieza in piezas if pieza["codec"] == solo]
    return piezas


def entrada_ref(ref_path, ancho, alto, fps):
    """La referencia cruda, etiquetada 709 ANTES del `-i` (lecciones del
    2026-10-18: sin etiqueta, ffmpeg supone 601 y convierte de mas)."""
    return COLOR_709_ENTRADA + ["-f", "rawvideo", "-pix_fmt", "yuva420p",
                                "-s", "%dx%d" % (ancho, alto), "-r", str(fps), "-i", ref_path]


def build_commands(ffmpeg, variant, ref_path, ancho, alto, fps, out_path, passlog,
                   audio_path=None, audio_desde=0.0, audio_dur=None):
    """Video = la referencia (entrada 0); audio = la pista de la fuente desde
    el primer cuadro emitido (entrada 1), o nada."""
    base = [ffmpeg, "-y", "-nostdin"] + entrada_ref(ref_path, ancho, alto, fps)
    if audio_path:
        if audio_desde:
            base += ["-ss", "%.6f" % audio_desde]
        if audio_dur:
            base += ["-t", "%.6f" % audio_dur]
        base += ["-i", audio_path]
    base += list(DETERMINISM) + ["-map", "0:v:0"]
    commands = []
    if variant.get("pasadas", 1) == 2:
        commands.append(base + list(variant["args"]) + ["-an", "-pass", "1",
                        "-passlogfile", passlog] + list(BITEXACT) + ["-f", "null", os.devnull])
    final = list(base)
    if audio_path:
        final += ["-map", "1:a:0"]
    final += list(variant["args"])
    final += list(variant["audio"]) if audio_path else ["-an"]
    if variant.get("pasadas", 1) == 2:
        final += ["-pass", "2", "-passlogfile", passlog]
    final += ["-shortest"] + list(BITEXACT) + [out_path]
    commands.append(final)
    return commands


# --------------------------------------------------------------------------
# Medicion: la pieza contra su referencia.

def build_decode_command(ffmpeg, variant, out_path):
    """La pieza decodificada CON su alfa (decoder de libvpx antes del `-i`),
    re-etiquetada sin convertir (emit_matrix.MISMAS_ETIQUETAS)."""
    return ([ffmpeg, "-v", "error", "-nostdin"] + list(variant["decoder"]) + ["-i", out_path,
            "-map", "0:v:0", "-vf", "format=yuva420p," + emit_matrix.MISMAS_ETIQUETAS,
            "-f", "rawvideo", "-pix_fmt", "yuva420p", "-"])


def planos(stream, ancho, alto):
    """Generador de (Y, U, V, A) de un yuva420p crudo."""
    area = ancho * alto
    cuarto = area // 4
    tam = area * 5 // 2
    while True:
        buf = stream.read(tam)
        if len(buf) < tam:
            return
        cuadro = np.frombuffer(buf, dtype=np.uint8)
        yield (cuadro[:area].reshape(alto, ancho),
               cuadro[area:area + cuarto].reshape(alto // 2, ancho // 2),
               cuadro[area + cuarto:area + 2 * cuarto].reshape(alto // 2, ancho // 2),
               cuadro[area * 3 // 2:].reshape(alto, ancho))


# Fondo del compuesto: gris medio neutro (Y 128, croma 128). Es lo que el
# ojo ve en el aparato: el efecto ENCIMA de otra cosa. Un borde mal hecho
# (halo, tinte del color de abajo) aparece aca y no en la luma suelta.
FONDO = 128.0


def compuesto(y, u, v, a):
    """El cuadro compuesto sobre FONDO (float64): Y con el alfa entero, U y V
    con el alfa promediado 2x2 (la croma de 4:2:0)."""
    alfa = a.astype(np.float64) / 255.0
    alto, ancho = a.shape
    alfa_c = alfa.reshape(alto // 2, 2, ancho // 2, 2).mean(axis=(1, 3))
    return (alfa * y + (1.0 - alfa) * FONDO,
            alfa_c * u + (1.0 - alfa_c) * FONDO,
            alfa_c * v + (1.0 - alfa_c) * FONDO,
            alfa_c)


def sse_compuesto(pieza, ref):
    """(suma de errores al cuadrado, muestras) del compuesto en Y, U y V,
    solo donde la referencia o la pieza tienen algo (el fondo puro no cuenta)."""
    cp = compuesto(*pieza)
    cr = compuesto(*ref)
    luma = (pieza[3] > 0) | (ref[3] > 0)
    croma = (cp[3] > 0) | (cr[3] > 0)
    sse = float(((cp[0] - cr[0])[luma] ** 2).sum())
    sse += float(((cp[1] - cr[1])[croma] ** 2).sum()) + float(((cp[2] - cr[2])[croma] ** 2).sum())
    return sse, int(np.count_nonzero(luma)) + 2 * int(np.count_nonzero(croma))


def psnr_de(sse, n):
    if not n:
        return None
    return 99.0 if not sse else min(99.0, 10.0 * np.log10(255.0 ** 2 / (sse / float(n))))


def alarma_alfa(alfa_vivo, era_alfa):
    if era_alfa and not alfa_vivo:
        return ("ALARMA DE ALFA: la pieza decodificada es opaca; el alfa se perdio "
                "(pix_fmt? decoder nativo?)")
    return ""


def medir(ffmpeg, variant, out_path, ref_path, ancho, alto, patron):
    """Cuadros, PSNR de luma donde la referencia se ve, PSNR del compuesto
    sobre gris (Y, U y V: el borde como lo ve el ojo), error del alfa, si el
    alfa llego vivo y el sesgo de luma contra el patron 709."""
    proc = subprocess.Popen(build_decode_command(ffmpeg, variant, out_path),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    cuadros = 0
    sse = 0
    n_vis = 0
    sse_c = 0.0
    n_c = 0
    alfa_err = 0
    alfa_n = 0
    alfa_vivo = False
    luma_pieza = 0
    patron_suma = 0.0
    patron_n = 0
    try:
        with open(ref_path, "rb") as ref_stream:
            for pieza, ref in zip(planos(proc.stdout, ancho, alto), planos(ref_stream, ancho, alto)):
                yp, ap = pieza[0], pieza[3]
                yr, ar = ref[0], ref[3]
                visible = ar > 0
                diff = yp.astype(np.int32) - yr.astype(np.int32)
                sse += int((diff[visible] ** 2).sum(dtype=np.int64))
                n_vis += int(np.count_nonzero(visible))
                c_sse, c_n = sse_compuesto(pieza, ref)
                sse_c += c_sse
                n_c += c_n
                alfa_err += int(np.abs(ap.astype(np.int32) - ar.astype(np.int32)).sum(dtype=np.int64))
                alfa_n += ap.size
                if not alfa_vivo and int(ap.min()) < 255:
                    alfa_vivo = True
                if cuadros < len(patron):
                    luma_pieza += int(yp[visible].sum(dtype=np.int64))
                    patron_suma += patron[cuadros][0]
                    patron_n += patron[cuadros][1]
                cuadros += 1
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    psnr = psnr_de(sse, n_vis)
    psnr_c = psnr_de(sse_c, n_c)
    sesgo = round((luma_pieza - patron_suma) / float(patron_n), 2) if patron_n else None
    return {"cuadros": cuadros,
            "psnr_luma_visible": "%.2f" % psnr if psnr is not None else "-",
            "psnr_compuesto": "%.2f" % psnr_c if psnr_c is not None else "-",
            "alfa_mae": "%.3f" % (alfa_err / float(alfa_n)) if alfa_n else "-",
            "alfa_vivo": alfa_vivo, "sesgo_luma": sesgo}


# --------------------------------------------------------------------------
# Emision.

def emit_variant(ffmpeg, variant, ref, out_dir, work_dir, fps, log, audio=None):
    """`ref` = lo que devolvio escribir_referencia + su ruta. `audio` =
    (ruta, desde_s, dur_s) o None."""
    x, y, ancho, alto = ref["rect"]
    out_path = os.path.join(out_dir, variant["id"] + "." + variant["ext"])
    log_path = os.path.join(out_dir, variant["id"] + ".ffmpeg.log")
    passlog = os.path.join(work_dir, variant["id"])
    log("+ " + variant["id"])
    started = time.time()
    audio_path, audio_desde, audio_dur = audio if audio else (None, 0.0, None)
    for index, command in enumerate(build_commands(
            ffmpeg, variant, ref["path"], ancho, alto, fps, out_path, passlog,
            audio_path, audio_desde, audio_dur)):
        emit_v2.run(command, log_path, append=index > 0)
    elapsed = time.time() - started
    m = medir(ffmpeg, variant, out_path, ref["path"], ancho, alto, ref["patron"])
    alarmas = [texto for texto in (emit_v2.alarma_color(m["sesgo_luma"]),
                                   alarma_alfa(m["alfa_vivo"], variant["alfa"])) if texto]
    for texto in alarmas:
        log("  " + "!" * 72)
        log("  !!! " + texto)
        log("  " + "!" * 72)
    row = {
        "id": variant["id"], "role": "alfa" if variant["alfa"] else "opaco",
        "mime": variant["mime"], "file": os.path.basename(out_path),
        "bytes": os.path.getsize(out_path), "sha256": emit_pieces.sha256_of(out_path),
        "cuadros": m["cuadros"], "psnr_luma_visible": m["psnr_luma_visible"],
        "psnr_compuesto": m["psnr_compuesto"], "alfa_mae": m["alfa_mae"],
        "alarmas": alarmas, "seg_encode": elapsed, "path": out_path,
    }
    row["note"] = ("%s; %dx%d en x %d y %d; psnr luma visible %s; psnr compuesto %s; "
                   "alfa mae %s%s; luma %s; %d cuadros; %.0f s") % (
        variant["note"], ancho, alto, x, y, m["psnr_luma_visible"], m["psnr_compuesto"],
        m["alfa_mae"],
        "" if not variant["alfa"] else ("; alfa vivo" if m["alfa_vivo"] else ""),
        "-" if m["sesgo_luma"] is None else "%+.2f" % m["sesgo_luma"],
        m["cuadros"], elapsed)
    if alarmas:
        row["note"] += "; " + "; ".join(alarmas)
    log("  %-12s %10d B  %dx%d  psnr %s  compuesto %s  alfa mae %s  luma %s  %d cuadros  %.0f s" % (
        row["id"], row["bytes"], ancho, alto, m["psnr_luma_visible"], m["psnr_compuesto"],
        m["alfa_mae"],
        "-" if m["sesgo_luma"] is None else "%+.2f" % m["sesgo_luma"], m["cuadros"], elapsed))
    return row


def manifest_lines(rows, fuente_sha, fuente, resumen, ref, fps, receta):
    x, y, w, h = ref["rect"]
    lineas = [
        "# pack alfa - vgen - docs/EMISION-ALFA.md",
        "# fuente\t%s\t%s" % (fuente_sha, fuente["nombre"]),
        "# fuente_formato\t%s %s %dx%d %s fps%s" % (
            fuente["codec"], fuente["pix_fmt"], fuente["width"], fuente["height"], fuente["fps"],
            " ALPHA_MODE=1" if fuente.get("alpha_mode") == "1" else ""),
        "# lienzo\t%dx%d\t%d fps" % (resumen["lienzo"][0], resumen["lienzo"][1], fps),
        "# rect\t%d\t%d\t%d\t%d\tx y ancho alto de la pieza sobre el lienzo" % (x, y, w, h),
        "# tiempo\t%d\t%d\tcuadros del lienzo: la pieza empieza en el primero (%.3f s)" % (
            ref["desde"], ref["hasta"], ref["desde"] / float(fps)),
        "# canal\topaco %s; cobertura %.1f %%; rect %.1f %%; alfa suave %.1f %%; huecos %s" % (
            "si" if resumen["siempre_opaco"] else "no", 100.0 * resumen["cobertura"],
            100.0 * resumen["area_rect"], 100.0 * resumen["semi"],
            ",".join("%d+%d" % hueco for hueco in resumen["huecos"]) or "-"),
        "# receta\t%s" % receta,
        "# " + "\t".join(MANIFEST_COLUMNS),
    ]
    for row in rows:
        lineas.append("\t".join(str(row[column]) for column in MANIFEST_COLUMNS))
    return lineas


def palancas_lines(filas):
    lineas = ["# palancas del alfa - vgen - tools/emit_alfa.py --medir-palancas (VP9)",
              "# " + "\t".join(PALANCAS_COLUMNS)]
    for fila in filas:
        lineas.append("\t".join(str(fila[column]) for column in PALANCAS_COLUMNS))
    return lineas


def variantes_palancas(opciones, resumen):
    """Cada palanca apagada de a una (y el alfa binario prendido, si el alfa
    es suave). La primera fila es la receta: contra ella se mide el delta."""
    filas = [("receta", dict(opciones))]
    if opciones["limpiar_modo"] != "no":
        filas.append(("sin-limpiar", dict(opciones, limpiar_modo="no")))
    if opciones["limpiar_modo"] == "sangrado":
        filas.append(("plano-sin-sangrado", dict(opciones, limpiar_modo="plano")))
    elif opciones["limpiar_modo"] == "plano":
        filas.append(("con-sangrado", dict(opciones, limpiar_modo="sangrado")))
    if opciones["recorte"] and resumen["area_rect"] < 1.0:
        filas.append(("sin-recorte", dict(opciones, recorte=False)))
    if opciones["tiempo"] and (resumen["desde"] > 0 or resumen["hasta"] < resumen["cuadros"]):
        filas.append(("sin-hueco", dict(opciones, tiempo=False)))
    if not opciones["umbral"] and resumen["semi"] > 0:
        filas.append(("alfa-binario-128", dict(opciones, umbral=128)))
    return filas


def medir_palancas(ffmpeg, rgba_command, ancho, alto, fps, resumen, opciones, variant,
                   out_dir, log):
    carpeta = os.path.join(out_dir, "palancas")
    if not os.path.isdir(carpeta):
        os.makedirs(carpeta)
    filas = []
    receta = None
    for nombre, opts in variantes_palancas(opciones, resumen):
        log("-- palanca %s --" % nombre)
        ref_path = os.path.join(carpeta, "ref-%s.yuva" % nombre)
        ref = escribir_referencia(ffmpeg, rgba_command, ancho, alto, fps, ref_path, resumen,
                                  **opts)
        ref["path"] = ref_path
        v = dict(variant, id="palanca-" + nombre)
        row = emit_variant(ffmpeg, v, ref, carpeta, carpeta, fps, log)
        if receta is None:
            receta = (ref, row)
        # Contra la referencia de la RECETA (la verdad que se ve), cuando la
        # palanca no cambio el rectangulo ni el tiempo: asi el alfa binario
        # paga su borde perdido y la limpieza muestra si tino el borde.
        vs_receta = "-"
        mismo = (ref["rect"] == receta[0]["rect"] and ref["desde"] == receta[0]["desde"]
                 and ref["hasta"] == receta[0]["hasta"])
        if mismo:
            vs_receta = medir(ffmpeg, v, row["path"], receta[0]["path"], ref["rect"][2],
                              ref["rect"][3], receta[0]["patron"])["psnr_compuesto"]
        if ref is not receta[0]:
            os.remove(ref_path)
        base = receta[1]["bytes"]
        filas.append({
            "palanca": nombre, "file": "palancas/" + row["file"], "bytes": row["bytes"],
            "delta_bytes": row["bytes"] - base,
            "delta_pct": "%+.1f" % (100.0 * (row["bytes"] - base) / base) if base else "-",
            "lienzo": "%dx%d" % (ref["rect"][2], ref["rect"][3]), "cuadros": row["cuadros"],
            "psnr_luma_visible": row["psnr_luma_visible"],
            "psnr_compuesto": row["psnr_compuesto"], "compuesto_vs_receta": vs_receta,
            "alfa_mae": row["alfa_mae"], "note": "; ".join(row["alarmas"]) or "-",
        })
    if receta:
        os.remove(receta[0]["path"])
    path = os.path.join(out_dir, PALANCAS_NAME)
    with open(path, "w") as stream:
        stream.write("\n".join(palancas_lines(filas)) + "\n")
    return path, filas


def decisiones_de(resumen, opciones, audio):
    d = []
    if resumen["siempre_opaco"]:
        d.append("(a) el canal es SIEMPRE opaco: no es una pieza alfa -> opaco-vp9 + opaco-h264 "
                 "(por hardware). Para el pack v2 usar emit_v2.")
    d.append("(b) RGB bajo alfa 0: %s" % {
        "sangrado": "sangrado %d px del borde + color plano" % SANGRADO_PASOS,
        "plano": "color plano", "no": "tal cual (palanca apagada)"}[opciones["limpiar_modo"]])
    x, y, w, h = resumen["rect"]
    d.append("(c) recorte: %s" % ("%dx%d en x %d y %d" % (w, h, x, y)
                                  if opciones["recorte"] and resumen["area_rect"] < 1.0
                                  else "no (todo el lienzo)"))
    if opciones["tiempo"]:
        d.append("(d) tiempo: cuadros %d..%d (los vacios de las puntas son hueco)%s" % (
            resumen["desde"], max(resumen["hasta"] - 1, 0),
            "; huecos interiores quedan adentro: %s" % ", ".join(
                "%d+%d" % hueco for hueco in resumen["huecos"]) if resumen["huecos"] else ""))
    else:
        d.append("(d) tiempo: entero%s" % (" (la fuente trae audio: el sonido puede empezar "
                                           "antes que la imagen)" if audio else ""))
    d.append("(e) loops: no evaluado aca; correr tools/buscar_loops.py sobre la fuente")
    d.append("(f) alfa: %s" % ("binario, umbral %d" % opciones["umbral"] if opciones["umbral"]
                               else "tal cual (%.1f %% suave)" % (100.0 * resumen["semi"])))
    return d


def emit(fuente_path, out_dir, ancho=ANCHO, fps=FPS, ffmpeg=None, log=None, receta="",
         max_frames=None, limpiar_modo=LIMPIAR, recorte=True, tiempo="auto", umbral=0,
         solo=None, medir_las_palancas=False, recipe_kwargs=None, forzar_opaco=False):
    log = log or (lambda message: None)
    ffmpeg = ffmpeg or emit_pieces._resolve_ffmpeg()
    recipe_kwargs = dict(recipe_kwargs or {})
    work_dir = os.path.join(out_dir, "work")
    for carpeta in (out_dir, work_dir):
        if not os.path.isdir(carpeta):
            os.makedirs(carpeta)

    fuente = probe_fuente(ffmpeg, fuente_path)
    fuente["nombre"] = os.path.basename(fuente_path)
    if not tiene_alfa(fuente["pix_fmt"], fuente["alpha_mode"]):
        return {"sin_alfa": fuente}
    fuente_sha = emit_pieces.sha256_of(fuente_path)
    audio_codec = emit_v2.probe_audio_codec(ffmpeg, fuente_path)
    decoder = decoder_de(fuente["codec"], fuente["alpha_mode"])
    log("fuente %s  %s  %s %s %dx%d%s  audio: %s" % (
        fuente_sha[:12], fuente["nombre"], fuente["codec"], fuente["pix_fmt"], fuente["width"],
        fuente["height"], " ALPHA_MODE=1 (decoder %s)" % decoder[1] if decoder else "",
        audio_codec or "sin pista"))

    ancho, alto = lienzo(fuente["width"], fuente["height"], ancho)
    rgba_command = build_rgba_command(ffmpeg, fuente_path, decoder,
                                      filtro_base(fuente["width"], fuente["height"],
                                                  ancho, alto, fps), max_frames)
    log("+ analisis del canal (%dx%d @%d)" % (ancho, alto, fps))
    analisis = Analisis(ancho, alto)
    for rgba in cuadros_rgba(rgba_command, ancho, alto):
        analisis.cuadro(rgba)
    resumen = analisis.resumen()
    if resumen["cuadros"] == 0:
        raise RuntimeError("no se leyo ningun cuadro de %s" % fuente_path)
    if resumen["hasta"] == 0:
        raise RuntimeError("el clip es todo transparente: no hay nada que emitir")
    opaco = resumen["siempre_opaco"] and not forzar_opaco
    if tiempo == "auto":
        tiempo = not audio_codec
    opciones = {"limpiar_modo": limpiar_modo, "recorte": bool(recorte),
                "tiempo": bool(tiempo), "umbral": int(umbral)}
    decisiones = decisiones_de(resumen, opciones, audio_codec)
    with open(os.path.join(out_dir, INFORME_NAME), "w") as stream:
        stream.write("\n".join(informe_lineas(fuente, resumen, fps, decisiones)) + "\n")
    for linea in informe_lineas(fuente, resumen, fps, decisiones)[1:]:
        log("  " + linea)

    ref_path = os.path.join(work_dir, "ref.yuva")
    log("+ referencia (palancas, 709 tv, yuva420p)")
    ref = escribir_referencia(ffmpeg, rgba_command, ancho, alto, fps, ref_path, resumen,
                              **opciones)
    ref["path"] = ref_path
    log("  referencia %dx%d en x %d y %d, cuadros %d..%d" % (
        ref["rect"][2], ref["rect"][3], ref["rect"][0], ref["rect"][1], ref["desde"],
        ref["hasta"] - 1))

    recipe_kwargs.update(fps=fps, opaco=opaco, solo=solo, audio=bool(audio_codec))
    variants = recipe(**recipe_kwargs)
    audio = None
    if audio_codec:
        audio = (fuente_path, ref["desde"] / float(fps),
                 (ref["hasta"] - ref["desde"]) / float(fps))
    rows = [emit_variant(ffmpeg, variant, ref, out_dir, work_dir, fps, log, audio)
            for variant in variants]

    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    with open(manifest_path, "w") as stream:
        stream.write("\n".join(manifest_lines(rows, fuente_sha, fuente, resumen, ref, fps,
                                              receta)) + "\n")

    palancas = None
    if medir_las_palancas:
        vp9 = recipe(**dict(recipe_kwargs, solo="vp9", audio=False))[0]
        palancas = medir_palancas(ffmpeg, rgba_command, ancho, alto, fps, resumen, opciones,
                                  vp9, out_dir, log)
    return {"rows": rows, "manifest": manifest_path, "resumen": resumen, "ref": ref,
            "fuente": fuente, "fuente_sha256": fuente_sha, "audio": audio_codec,
            "opaco": opaco, "palancas": palancas,
            "alarmas": [texto for row in rows for texto in row["alarmas"]]}


# --------------------------------------------------------------------------
# El sintetico (mientras no llegue un clip real con alfa).

def build_sintetico_command(ffmpeg, out_path, segundos=4, ancho=1920, alto=1080, fps=30):
    """ProRes 4444 con: 1 s transparente al principio (hueco), un disco de
    borde suave (alfa suave) que cruza la mitad izquierda (recorte), color
    ruidoso BAJO alfa 0 (el peor caso de exportador: limpieza) y un tono de
    audio (Opus)."""
    video = ("nullsrc=s=%dx%d:r=%d:d=%d,format=rgba,geq="
             "r='128+100*sin(X/37+T*3)':g='128+100*sin(Y/23)':b='random(1)*255':"
             "a='if(lt(T,1),0,255*clip((%d-hypot(X-(%d+T*%d),Y-%d))/30,0,1))'" % (
                 ancho, alto, fps, segundos, alto // 4, ancho // 5, ancho // 7, alto // 2))
    return [ffmpeg, "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", video,
            "-f", "lavfi", "-i", "sine=f=440:d=%d" % segundos,
            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
            "-c:a", "pcm_s16le", "-shortest", out_path]


# --------------------------------------------------------------------------

def receta_de(args):
    """Solo lo que decide los bytes, en orden fijo, sin rutas."""
    parts = ["--ancho", str(args.ancho), "--fps", str(args.fps),
             "--vp9-crf", str(args.vp9_crf), "--vp8-crf", str(args.vp8_crf),
             "--vp8-tope", args.vp8_tope, "--limpiar", args.limpiar, "--tiempo", args.tiempo]
    if args.vp9_2pass:
        parts.append("--vp9-2pass")
    if args.sin_recorte:
        parts.append("--sin-recorte")
    if args.alfa_binario:
        parts += ["--alfa-binario", str(args.alfa_binario)]
    if args.solo:
        parts += ["--solo", args.solo]
    if args.frames:
        parts += ["--frames", str(args.frames)]
    return " ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente", nargs="?", help="el clip con canal alfa (mov/webm/png%%04d.png)")
    parser.add_argument("--out", default="outputs/alfa", help="carpeta de salida")
    parser.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg")
    parser.add_argument("--ancho", type=int, default=ANCHO, help="ancho del lienzo (0 = el de la fuente)")
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--frames", type=int, default=None, help="cortar en N cuadros (pruebas)")
    parser.add_argument("--vp9-crf", type=int, default=VP9_CRF)
    parser.add_argument("--vp9-2pass", action="store_true", help="VP9 en dos pasadas")
    parser.add_argument("--vp8-crf", type=int, default=VP8_CRF)
    parser.add_argument("--vp8-tope", default=VP8_TOPE, help="tope de bitrate de VP8 (crf lo necesita)")
    parser.add_argument("--solo", choices=("vp9", "vp8", "h264"), default=None)
    parser.add_argument("--limpiar", choices=("plano", "sangrado", "no"), default=LIMPIAR,
                        help="(b) que hacer con el RGB bajo alfa 0")
    parser.add_argument("--sin-recorte", action="store_true", help="(c) no recortar al rectangulo util")
    parser.add_argument("--tiempo", choices=("auto", "recortar", "entero"), default="auto",
                        help="(d) cuadros vacios de las puntas; auto = recortar si no hay audio")
    parser.add_argument("--alfa-binario", type=int, default=0,
                        help="(f) umbral 1..255 para alfa todo o nada (0 = alfa tal cual)")
    parser.add_argument("--medir-palancas", action="store_true",
                        help="emitir VP9 con cada palanca apagada y dejar PALANCAS-alfa.tsv")
    parser.add_argument("--hacer-sintetico", default=None, metavar="SALIDA.mov",
                        help="escribir el clip sintetico de prueba y salir")
    args = parser.parse_args(argv)

    ffmpeg = args.ffmpeg or emit_pieces._resolve_ffmpeg()
    if args.hacer_sintetico:
        subprocess.check_call(build_sintetico_command(ffmpeg, args.hacer_sintetico))
        print("sintetico: %s  %s" % (args.hacer_sintetico,
                                     emit_pieces.sha256_of(args.hacer_sintetico)))
        return 0
    if not args.fuente:
        parser.error("falta la fuente")
    if not 0 <= args.alfa_binario <= 255:
        parser.error("--alfa-binario va de 1 a 255 (0 = apagado)")
    tiempo = {"auto": "auto", "recortar": True, "entero": False}[args.tiempo]
    recipe_kwargs = dict(vp9_crf=args.vp9_crf, vp8_crf=args.vp8_crf, vp8_tope=args.vp8_tope,
                         vp9_2pass=args.vp9_2pass)
    result = emit(args.fuente, args.out, ancho=args.ancho, fps=args.fps, ffmpeg=ffmpeg,
                  receta=receta_de(args), max_frames=args.frames, limpiar_modo=args.limpiar,
                  recorte=not args.sin_recorte, tiempo=tiempo, umbral=args.alfa_binario,
                  solo=args.solo, medir_las_palancas=args.medir_palancas,
                  recipe_kwargs=recipe_kwargs,
                  log=lambda message: print(message, flush=True))
    if "sin_alfa" in result:
        f = result["sin_alfa"]
        print("-- SIN ALFA --  %s es %s %s: no trae canal alfa. Para video opaco usar "
              "tools/emit_v2.py." % (args.fuente, f["codec"], f["pix_fmt"]))
        return CODIGO_SIN_ALFA
    print("-- PACK ALFA --  %s" % result["manifest"])
    if result["palancas"]:
        print("-- PALANCAS --  %s" % result["palancas"][0])
    if result["alarmas"]:
        print("-- ALARMAS --  %s" % " | ".join(result["alarmas"]))
        return CODIGO_ALARMA
    return 0


if __name__ == "__main__":
    sys.exit(main())
