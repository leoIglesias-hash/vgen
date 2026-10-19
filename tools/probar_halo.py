#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probar_halo.py - la evaluacion de halo del 2026-10-18, en una orden.

Ese dia la eleccion C3 -> C4 (docs/INTRO-Y-LOOP.md s3 y s4 filas 9-11) se
hizo con scripts sueltos y recortes a mano. Esto la deja hecha: emite la
misma pieza (la intro, o el loop) con varias VARIANTES de prefiltro y crf,
con la MISMA linea de comando que tools/emit_intro_loop.py, y las mide:

  bytes        lo que pesa cada variante;
  ondulacion   el halo SIN referencia: en el fondo oscuro (17..40 de luma,
               lejos de lo brillante: particulas y letras) lo que queda entre
               un suavizado de 7 px y uno de 41 px. El tramado fino lo borra
               el de 7, el degrade real lo sigue el de 41: lo del medio son
               escalones, anillos y bloques. Media y p95, en tonos de 8 bits.
               La fuente tambien tiene su numero (fila 0): un prefiltro puede
               quedar MEJOR que la fuente, cosa que una metrica contra la
               referencia no puede premiar (s4 fila 9);
  ssim / psnr  contra la referencia (emit_matrix.build_metrics_command: las
               dos entradas re-etiquetadas igual);
  sesgo luma   luma media variante - referencia. Con los colores bien es casi
               0; el corrimiento 601->709 del 2026-10-18 daba -3 a -5. Pasado
               el umbral de emit_v2 se marca ALARMA.

Deja en --out: las variantes (NN-<nombre>-crfNN.mp4), HALO.tsv (la tabla,
tambien en pantalla) y HALO.png: el mismo cuadro de la referencia y de cada
variante, recortado, a brillo normal y x3 (el numero de fila arriba a la
izquierda de cada tira). Determinista: mismas entradas -> mismos bytes de
piezas, tabla y lamina.

Variantes (--variante, se repite; sin ninguna: c3 y c4):
  c4 | c3 | ninguno      los prefiltros con nombre de emit_intro_loop
  c4@22                  con otro crf (default: el de la pieza, 24 / 26)
  "hqdn3d=3:2:4:3@26"    cualquier otro texto es el filtro ffmpeg tal cual

Uso:
  python tools/probar_halo.py fuente.mp4 --out outputs/halo
  python tools/probar_halo.py fuente.mp4 --out o --variante c3 --variante c4 --variante c4@22
  python tools/probar_halo.py fuente.mp4 --out o --intro 197 --periodo 85 --pieza loop
  python tools/probar_halo.py work/ref-intro.y4m --out o --variante c4   (referencia ya hecha)
  python tools/probar_halo.py fuente.mp4 --out o --cuadro 4 --recorte 0,180,640,360
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import buscar_loops  # noqa: E402
import emit_intro_loop  # noqa: E402
import emit_matrix  # noqa: E402
import emit_v2  # noqa: E402

# La mascara: fondo oscuro, lejos de lo brillante (el prototipo del 2026-10-18).
OSCURO_MIN = 17          # luma de la referencia >= esto (el negro de video es 16)
OSCURO_MAX = 40          # media de 17x17 px de la referencia <= esto
BRILLANTE = 45           # luma que cuenta como particula / letra...
LEJOS_R = 24             # ...y ninguna en 49x49 px
OSCURO_R = 8
# La ondulacion: dos pasadas de caja de 7 px contra dos de 41 px.
ONDA_CHICO_R = 3
ONDA_GRANDE_R = 20
HIST_PASO = 256          # el p95 sale de un histograma de 1/256 de tono
HIST_TOPE = 32           # tonos

CUADRO = 4               # el halo se ve al arrancar
RECORTE = (0, 180, 640, 360)   # x, y, ancho, alto: el costado izquierdo
GANANCIA = 3
SEPARACION = 4
GRIS = 64

TABLA = "HALO.tsv"
LAMINA = "HALO.png"
COLUMNAS = ("fila", "variante", "crf", "bytes", "sha256", "cuadros", "ondulacion",
            "ondulacion_p95", "sesgo_luma", "ssim_all", "psnr_avg", "prefiltro")


# --------------------------------------------------------------------------
# Nucleo numpy (testeado sin ffmpeg)

def caja(a, r):
    """Media de una caja de (2r+1)x(2r+1) px, separable, con el borde
    extendido. float64 y sumas acumuladas: mismo resultado en cada corrida."""
    a = np.asarray(a, dtype=np.float64)
    k = 2 * r + 1
    for eje in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[eje] = (r + 1, r)
        c = np.cumsum(np.pad(a, pad, mode="edge"), axis=eje)
        n = a.shape[eje]
        hi = [slice(None), slice(None)]
        lo = [slice(None), slice(None)]
        hi[eje] = slice(k, k + n)
        lo[eje] = slice(0, n)
        a = (c[tuple(hi)] - c[tuple(lo)]) / k
    return a


def mascara_fondo(y_ref):
    """Donde se mide: fondo oscuro de la REFERENCIA (la misma para todas las
    variantes), lejos de cualquier cosa brillante."""
    y = np.asarray(y_ref, dtype=np.float64)
    lejos = caja(y > BRILLANTE, LEJOS_R) == 0
    return (caja(y, OSCURO_R) <= OSCURO_MAX) & lejos & (y >= OSCURO_MIN)


def ondulacion(y, mascara):
    """|suave chico - suave grande| en los pixeles de la mascara."""
    y = np.asarray(y, dtype=np.float64)
    chico = caja(caja(y, ONDA_CHICO_R), ONDA_CHICO_R)
    grande = caja(caja(y, ONDA_GRANDE_R), ONDA_GRANDE_R)
    return np.abs(chico - grande)[mascara]


class Acumulador(object):
    """Media y p95 de muchos valores sin guardarlos (histograma fijo)."""

    def __init__(self):
        self.suma = 0.0
        self.n = 0
        self.hist = np.zeros(HIST_PASO * HIST_TOPE, dtype=np.int64)

    def sumar(self, valores):
        valores = np.asarray(valores, dtype=np.float64)
        self.suma += float(valores.sum())
        self.n += int(valores.size)
        idx = np.minimum((valores * HIST_PASO).astype(np.int64), self.hist.size - 1)
        self.hist += np.bincount(idx, minlength=self.hist.size)

    def media(self):
        return self.suma / self.n if self.n else None

    def percentil(self, p=95):
        if not self.n:
            return None
        acum = np.cumsum(self.hist)
        cubeta = int(np.searchsorted(acum, self.n * p / 100.0))
        return (cubeta + 1) / float(HIST_PASO)


def medir_cuadros(ternas):
    """`ternas` = (y, suma de luma de la referencia en ese cuadro, mascara)
    por cuadro. Devuelve la ondulacion (media, p95), el sesgo de luma y los
    cuadros. La suma del sesgo es entera: exacta."""
    acum = Acumulador()
    suma = pixeles = cuadros = 0
    for y, suma_ref, mascara in ternas:
        y = np.asarray(y)
        acum.sumar(ondulacion(y, mascara))
        suma += int(y.sum(dtype=np.int64)) - int(suma_ref)
        pixeles += int(y.size)
        cuadros += 1
    return {"ondulacion": acum.media(), "ondulacion_p95": acum.percentil(95),
            "sesgo_luma": emit_v2.sesgo_de(suma, pixeles), "cuadros": cuadros}


# --------------------------------------------------------------------------
# Variantes

def parse_variante(texto, crf_default):
    """'c4' / 'c3@26' / 'ninguno' / 'hqdn3d=3:2:4:3@22' -> dict. El crf va
    despues de la ULTIMA arroba, solo si son cifras."""
    texto = texto.strip()
    crf = crf_default
    cuerpo = texto
    if "@" in texto:
        antes, despues = texto.rsplit("@", 1)
        if despues.strip().isdigit():
            cuerpo, crf = antes.strip(), int(despues)
    clave = cuerpo.lower()
    if clave in ("", "ninguno", "none"):
        nombre = "ninguno"
    elif clave in emit_intro_loop.PREFILTROS:
        nombre = clave
    else:
        nombre = None          # texto libre: el nombre lo pone `variantes`
    return {"nombre": nombre, "prefiltro": emit_intro_loop.resolver_prefiltro(cuerpo),
            "crf": int(crf)}


def variantes(textos, crf_default):
    """Las variantes con su fila (1..N), nombre y archivo. Texto libre ->
    f1, f2, ..."""
    salida = []
    libres = 0
    for fila, texto in enumerate(textos or ("c3", "c4"), start=1):
        v = parse_variante(texto, crf_default)
        if v["nombre"] is None:
            libres += 1
            v["nombre"] = "f%d" % libres
        v["fila"] = fila
        v["file"] = "%02d-%s-crf%d.mp4" % (fila, v["nombre"], v["crf"])
        salida.append(v)
    return salida


def parse_recorte(texto):
    partes = [int(p) for p in texto.replace(" ", "").split(",")]
    if len(partes) != 4 or partes[2] <= 0 or partes[3] <= 0 or min(partes) < 0:
        raise ValueError("--recorte es x,y,ancho,alto (enteros, ancho y alto > 0)")
    return tuple(partes)


# --------------------------------------------------------------------------
# Lamina (PNG escrito a mano: sin dependencias, mismos bytes cada vez)

DIGITOS = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
}


def recortar(rgb, recorte):
    """El recorte dentro del cuadro (se acota al borde)."""
    x, y, w, h = recorte
    alto, ancho = rgb.shape[:2]
    x, y = min(x, ancho - 1), min(y, alto - 1)
    return rgb[y:min(alto, y + h), x:min(ancho, x + w)]


def realzar(rgb, ganancia=GANANCIA):
    return np.clip(rgb.astype(np.int32) * ganancia, 0, 255).astype(np.uint8)


def rotular(rgb, numero, escala=4):
    """El numero de fila arriba a la izquierda, blanco sobre negro."""
    texto = str(numero)
    out = rgb.copy()
    alto_t, ancho_t = 5 * escala, (4 * len(texto) - 1) * escala
    borde = escala
    out[:min(out.shape[0], alto_t + 2 * borde), :min(out.shape[1], ancho_t + 2 * borde)] = 0
    for i, ch in enumerate(texto):
        for fila, bits in enumerate(DIGITOS[ch]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    y0 = borde + fila * escala
                    x0 = borde + (i * 4 + col) * escala
                    out[y0:y0 + escala, x0:x0 + escala] = 255
    return out


def armar_lamina(cuadros_rgb, ganancia=GANANCIA, separacion=SEPARACION):
    """Una tira por cuadro (ya recortado): normal | x ganancia, apiladas en
    el orden recibido (fila 0 = referencia)."""
    alto = max(c.shape[0] for c in cuadros_rgb)
    ancho = max(c.shape[1] for c in cuadros_rgb)
    total_w = 2 * ancho + 3 * separacion
    total_h = len(cuadros_rgb) * (alto + separacion) + separacion
    lamina = np.full((total_h, total_w, 3), GRIS, dtype=np.uint8)
    for fila, rgb in enumerate(cuadros_rgb):
        y0 = separacion + fila * (alto + separacion)
        h, w = rgb.shape[:2]
        lamina[y0:y0 + h, separacion:separacion + w] = rotular(rgb, fila)
        x1 = 2 * separacion + ancho
        lamina[y0:y0 + h, x1:x1 + w] = realzar(rgb, ganancia)
    return lamina


def png_bytes(rgb):
    """PNG RGB de 8 bits, sin filtro por fila, zlib nivel 9."""
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    alto, ancho = rgb.shape[:2]
    crudo = b"".join(b"\x00" + rgb[y].tobytes() for y in range(alto))

    def trozo(tipo, datos):
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(crudo, 9)) + trozo(b"IEND", b""))


# --------------------------------------------------------------------------
# Tabla

def fmt(valor, decimales):
    return "-" if valor is None else "%.*f" % (decimales, valor)


def fila_tabla(fila, nombre, crf, bytes_, sha, medida, metricas, prefiltro):
    return {"fila": fila, "variante": nombre, "crf": crf, "bytes": bytes_, "sha256": sha,
            "cuadros": medida["cuadros"], "ondulacion": fmt(medida["ondulacion"], 3),
            "ondulacion_p95": fmt(medida["ondulacion_p95"], 3),
            "sesgo_luma": "-" if medida["sesgo_luma"] is None else "%+.2f" % medida["sesgo_luma"],
            "ssim_all": metricas.get("ssim_all", "-"), "psnr_avg": metricas.get("psnr_avg", "-"),
            "prefiltro": prefiltro}


def tabla_lineas(filas, cabecera):
    lineas = ["# probar_halo.py - docs/INTRO-Y-LOOP.md s3"] + ["# " + c for c in cabecera]
    lineas.append("\t".join(COLUMNAS))
    for f in filas:
        lineas.append("\t".join(str(f[c]) for c in COLUMNAS))
    return lineas


def tabla_pantalla(filas):
    cols = ("fila", "variante", "crf", "bytes", "ondulacion", "ondulacion_p95",
            "sesgo_luma", "ssim_all", "psnr_avg")
    anchos = [max(len(c), max(len(str(f[c])) for f in filas)) for c in cols]
    salida = ["  ".join(c.rjust(a) for c, a in zip(cols, anchos))]
    for f in filas:
        salida.append("  ".join(str(f[c]).rjust(a) for c, a in zip(cols, anchos)))
    return salida


# --------------------------------------------------------------------------
# ffmpeg

def build_rgb_command(ffmpeg, path, cuadro, fps=None):
    """Un cuadro en RGB para la lamina, con la conversion 709 tv declarada
    (las dos entradas re-etiquetadas igual: emit_matrix.MISMAS_ETIQUETAS)."""
    filtro = (("fps=%d," % fps if fps else "") + "format=yuv420p," + emit_matrix.MISMAS_ETIQUETAS
              + ",trim=start_frame=%d:end_frame=%d," % (cuadro, cuadro + 1)
              + "scale=in_color_matrix=bt709:in_range=tv,format=rgb24")
    return [ffmpeg, "-v", "error", "-nostdin", "-i", path, "-vf", filtro, "-frames:v", "1",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]


def leer_rgb(ffmpeg, path, cuadro, ancho, alto, fps=None):
    datos = subprocess.run(build_rgb_command(ffmpeg, path, cuadro, fps), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
    if len(datos) < ancho * alto * 3:
        raise RuntimeError("no se pudo leer el cuadro %d de %s" % (cuadro, path))
    return np.frombuffer(datos[:ancho * alto * 3], dtype=np.uint8).reshape(alto, ancho, 3)


def metricas_de(ffmpeg, out_path, ref_path, fps):
    result = subprocess.run(emit_matrix.build_metrics_command(ffmpeg, out_path, ref_path, fps=fps),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    return emit_matrix.parse_metrics(result.stderr.decode("utf-8", "replace"))


def preparar_referencia(fuente, out_dir, ffmpeg, pieza, intro, periodo, fps, ancho,
                        matriz_fuente, log):
    """Una fuente -> la referencia y4m de la pieza (como emit_intro_loop).
    Un .y4m se usa tal cual."""
    if fuente.lower().endswith(".y4m"):
        return fuente, "referencia dada %s" % os.path.basename(fuente)
    fps_fuente = buscar_loops.fps_de_fuente(ffmpeg, fuente)
    if intro is None or periodo is None:
        hallado = emit_intro_loop.detectar(ffmpeg, fuente, fps_fuente, fps, log)
        intro, periodo = hallado["intro"], hallado["periodo"]
    p = emit_intro_loop.plan(intro, periodo, fps_fuente, fps)
    if pieza == "intro":
        if p["intro"] <= 0:
            raise SystemExit("la fuente no tiene intro; usar --pieza loop")
        filtro, cuadros = emit_intro_loop.filtro_intro(p, ancho, matriz_fuente), None
    else:
        filtro, cuadros = emit_intro_loop.filtro_loop(p, ancho, matriz_fuente), p["cuadros_loop"]
    work = os.path.join(out_dir, "work")
    os.makedirs(work, exist_ok=True)
    ref = os.path.join(work, "ref-%s.y4m" % pieza)
    log("+ referencia %s (intro %d, periodo %d cuadros de la fuente)" % (pieza, intro, periodo))
    emit_v2.run(emit_intro_loop.build_ref_command(ffmpeg, fuente, filtro, ref, cuadros),
                os.path.join(out_dir, "probar_halo.ffmpeg.log"), append=True)
    return ref, "fuente %s %s; pieza %s (intro %d, periodo %d)" % (
        emit_intro_loop.sha256_de(fuente)[:12], os.path.basename(fuente), pieza, intro, periodo)


def probar(fuente, out_dir, textos=None, ffmpeg="ffmpeg", pieza="intro", intro=None,
           periodo=None, fps=emit_intro_loop.FPS, ancho=emit_intro_loop.ANCHO, crf=None,
           cuadro=CUADRO, recorte=RECORTE, ganancia=GANANCIA, matriz_fuente="auto", log=print):
    os.makedirs(out_dir, exist_ok=True)
    errlog = os.path.join(out_dir, "probar_halo.ffmpeg.log")
    open(errlog, "wb").close()
    ref, origen = preparar_referencia(fuente, out_dir, ffmpeg, pieza, intro, periodo, fps,
                                      ancho, matriz_fuente, log)
    w, h, fps_ref, n = emit_v2.read_y4m_header(ref)
    if crf is None:
        crf = emit_intro_loop.CRF_INTRO if pieza == "intro" else emit_intro_loop.CRF_LOOP
    lista = variantes(textos, crf)
    cuadro = max(0, min(cuadro, n - 1))

    # La referencia: mascaras (guardadas en bits), su luma y su propia ondulacion.
    log("+ mascara del fondo oscuro (%d cuadros %dx%d @%s)" % (n, w, h, fps_ref))
    mascaras = []
    lumas_ref = []

    def ternas_ref():
        for y in emit_v2.lumas(ffmpeg, ref, w, h):
            m = mascara_fondo(y)
            mascaras.append(np.packbits(m))
            lumas_ref.append(int(y.sum(dtype=np.int64)))
            yield y, lumas_ref[-1], m

    medida_ref = medir_cuadros(ternas_ref())
    if len(mascaras) != n:
        raise RuntimeError("la referencia dio %d cuadros, la cabecera dice %d" % (len(mascaras), n))
    fondo = 100.0 * sum(int(np.unpackbits(b).sum()) for b in mascaras) / float(n * w * h)
    filas = [fila_tabla(0, "referencia", "-", "-", emit_intro_loop.sha256_de(ref)[:12],
                        medida_ref, {}, "-")]
    rgbs = [recortar(leer_rgb(ffmpeg, ref, cuadro, w, h), recorte)]

    for v in lista:
        out = os.path.join(out_dir, v["file"])
        log("+ %s (crf %d, prefiltro %s)" % (v["file"], v["crf"], v["nombre"]))
        emit_v2.run(emit_intro_loop.build_h264_command(ffmpeg, ref, out, v["crf"], n, v["prefiltro"]),
                    errlog, append=True)
        medida = medir_pieza(ffmpeg, out, w, h, fps_ref, mascaras, lumas_ref)
        filas.append(fila_tabla(v["fila"], v["nombre"], v["crf"], os.path.getsize(out),
                                emit_intro_loop.sha256_de(out)[:12], medida,
                                metricas_de(ffmpeg, out, ref, fps_ref), v["prefiltro"] or "ninguno"))
        emit_v2.anotar_color(medida["sesgo_luma"], log)
        rgbs.append(recortar(leer_rgb(ffmpeg, out, cuadro, w, h, fps_ref), recorte))

    cabecera = [origen,
                "referencia %dx%d @%s, %d cuadros; fondo oscuro medido: %.1f %% de los pixeles"
                % (w, h, fps_ref, n, fondo),
                "lamina %s: cuadro %d, recorte x,y,ancho,alto %s, normal | x%d; fila 0 = referencia"
                % (LAMINA, cuadro, ",".join(str(r) for r in recorte), ganancia)]
    with open(os.path.join(out_dir, TABLA), "w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(tabla_lineas(filas, cabecera)) + "\n")
    with open(os.path.join(out_dir, LAMINA), "wb") as stream:
        stream.write(png_bytes(armar_lamina(rgbs, ganancia)))
    for linea in cabecera:
        log("-- " + linea)
    for linea in tabla_pantalla(filas):
        log(linea)
    for v in lista:
        log("   fila %d = %s" % (v["fila"], v["prefiltro"] or "sin prefiltro"))
    log("-- %s y %s en %s" % (TABLA, LAMINA, out_dir))
    return filas


def medir_pieza(ffmpeg, path, w, h, fps, mascaras, lumas_ref):
    """Decodifica la variante cuadro por cuadro contra las mascaras y la luma
    de la referencia (sin volver a leer la referencia)."""
    gen = emit_v2.lumas(ffmpeg, path, w, h, fps)
    try:
        return medir_cuadros(
            (y, suma_ref, np.unpackbits(bits, count=w * h).astype(bool).reshape(h, w))
            for y, bits, suma_ref in zip(gen, mascaras, lumas_ref))
    finally:
        gen.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente", help="el video fuente, o una referencia .y4m ya hecha")
    parser.add_argument("--out", default="outputs/halo")
    parser.add_argument("--variante", action="append", default=None,
                        help="c4 | c3 | ninguno | filtro, con @crf opcional; se repite "
                             "(default: c3 y c4)")
    parser.add_argument("--pieza", choices=("intro", "loop"), default="intro")
    parser.add_argument("--intro", type=int, default=None)
    parser.add_argument("--periodo", type=int, default=None)
    parser.add_argument("--crf", type=int, default=None,
                        help="crf de las variantes sin @ (default: 24 intro / 26 loop)")
    parser.add_argument("--fps", type=int, default=emit_intro_loop.FPS)
    parser.add_argument("--ancho", type=int, default=emit_intro_loop.ANCHO)
    parser.add_argument("--cuadro", type=int, default=CUADRO, help="cuadro de la lamina")
    parser.add_argument("--recorte", default=",".join(str(r) for r in RECORTE),
                        help="x,y,ancho,alto de la lamina (default: %(default)s)")
    parser.add_argument("--ganancia", type=int, default=GANANCIA)
    parser.add_argument("--matriz-fuente", default="auto")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args(argv)
    if (args.intro is None) != (args.periodo is None):
        parser.error("--intro y --periodo van juntos (o ninguno, para detectarlos)")
    try:
        recorte = parse_recorte(args.recorte)
    except ValueError as error:
        parser.error(str(error))
    probar(args.fuente, args.out, args.variante, args.ffmpeg, args.pieza, args.intro,
           args.periodo, args.fps, args.ancho, args.crf, args.cuadro, recorte, args.ganancia,
           args.matriz_fuente)
    return 0


if __name__ == "__main__":
    sys.exit(main())
