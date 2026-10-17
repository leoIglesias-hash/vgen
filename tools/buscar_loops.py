#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_loops.py - encuentra la intro y el loop repetido de un video, para
emitirlos como dos piezas (la intro una vez, el loop lo repite el reproductor).

Por que existe (2026-10-17, video exploratorio `intro_D_loop_ondas_x9`, ver
docs/INTRO-Y-LOOP.md): un video de 40 s era 8,2 s de intro + el mismo loop de
3,54 s repetido 9 veces. El encoder solo aprovecha parecidos entre cuadros
cercanos (sus referencias alcanzan pocos cuadros), asi que cada vuelta se paga
entera; separar intro + una vuelta, con la misma receta, bajo el peso 77 %
(VP9) y 78 % (H.264).

Como lo encuentra (sin decirle nada del video):

  1. Miniaturas en gris (64x36 por defecto) de TODOS los cuadros de la fuente,
     a su cadencia original (el corte se decide en cuadros de la fuente).
  2. Para cada desplazamiento d (de --min-seg a --max-seg) compara cada
     cuadro i con el i+d: diferencia media absoluta. Una repeticion da una
     racha larga de diferencias casi nulas. Para no confundir una escena
     quieta con un loop, "igual" exige ademas ser mucho mas parecido que el
     cuadro vecino (i contra i+1): en una repeticion con movimiento el vecino
     cambia y la copia no.
  3. Gana el desplazamiento con la racha mas larga (el periodo fundamental:
     el doble del periodo da una racha mas corta). La racha empieza donde
     termina la intro; su largo dice cuantas vueltas hay.
  4. Ajuste al fps destino: el loop tiene que durar una cantidad ENTERA de
     cuadros, o la costura salta. Se redondea y se informa el cambio de
     velocidad (3,54 s -> 3,5 s = 35 cuadros a 10 fps, +1,2 %).
  5. Costura: el salto del ultimo cuadro del loop al primero se compara con
     los saltos normales entre vecinos del mismo loop (percentil).

Uso:
  python tools/buscar_loops.py fuente.mp4
  python tools/buscar_loops.py fuente.mp4 --fps-destino 10
  python tools/buscar_loops.py fuente.mp4 --min-seg 1 --max-seg 20

Solo lee la fuente; no escribe nada. El corte en piezas lo hace
tools/emit_intro_loop.py con lo que este reporta.
"""

import argparse
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

MINI_ANCHO = 64
MINI_ALTO = 36

# Una copia "es igual" si su diferencia media (0..255) no pasa UMBRAL_ABS y
# ademas es <= UMBRAL_REL de la diferencia con el cuadro vecino. Calibrado con
# intro_D (repeticiones ~0,3-0,6; vecinos con movimiento ~3-15).
UMBRAL_ABS = 2.0
UMBRAL_REL = 0.35
# Ventana (en cuadros) de la mediana que mide el movimiento local.
VENTANA_MOVIMIENTO = 9
# Se tolera este hueco (en cuadros) dentro de una racha: un cuadro con un
# destello o un cuadro duplicado de la fuente no corta la repeticion.
HUECO = 2
# Un cambio de velocidad mayor a esto se informa como advertencia.
VELOCIDAD_MAX = 0.03
# Bordes de la racha: la intro suele FUNDIRSE con el loop (intro_D: la copia
# del cuadro 195 es 5x peor que la mediana, la del 196 2x, desde el 197 igual
# al resto). Se recortan los bordes mientras la copia sea > BORDE x mediana.
BORDE = 2.0


# --------------------------------------------------------------------------
# Miniaturas

def miniaturas_command(ffmpeg, fuente_path, ancho=MINI_ANCHO, alto=MINI_ALTO):
    """Todos los cuadros de la fuente (sin cambiar la cadencia) en gris
    `ancho`x`alto`, crudos por stdout."""
    return [ffmpeg, "-v", "error", "-nostdin", "-i", fuente_path, "-map", "0:v:0",
            "-vf", "scale=%d:%d:flags=area,format=gray" % (ancho, alto),
            "-f", "rawvideo", "-pix_fmt", "gray", "-"]


def miniaturas_de_bytes(data, ancho=MINI_ANCHO, alto=MINI_ALTO):
    """Los bytes crudos -> array float32 (cuadros, alto, ancho). Un cuadro
    incompleto al final se descarta."""
    por_cuadro = ancho * alto
    cuadros = len(data) // por_cuadro
    plano = np.frombuffer(data[:cuadros * por_cuadro], dtype=np.uint8)
    return plano.reshape(cuadros, alto, ancho).astype(np.float32)


def leer_miniaturas(ffmpeg, fuente_path, ancho=MINI_ANCHO, alto=MINI_ALTO):
    result = subprocess.run(miniaturas_command(ffmpeg, fuente_path, ancho, alto),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg fallo: %s" % result.stderr.decode("utf-8", "replace"))
    return miniaturas_de_bytes(result.stdout, ancho, alto)


def parse_fps(text):
    """'24/1', '30000/1001' o '25' -> float."""
    text = text.strip()
    if "/" in text:
        num, den = text.split("/", 1)
        return float(num) / float(den)
    return float(text)


def fps_de_fuente(ffmpeg, fuente_path):
    """La cadencia de la fuente (r_frame_rate de ffprobe)."""
    import emit_v2
    valores = emit_v2.probe(ffmpeg, fuente_path, "v:0", ["r_frame_rate"])
    if not valores:
        raise RuntimeError("ffprobe no pudo leer la cadencia de %s" % fuente_path)
    return parse_fps(valores[0])


# --------------------------------------------------------------------------
# Deteccion (pura, sobre las miniaturas)

def diferencias(mini, desplazamiento):
    """Diferencia media absoluta (0..255) entre cada cuadro i y el i+d."""
    n = len(mini)
    if desplazamiento <= 0 or desplazamiento >= n:
        return np.zeros(0, dtype=np.float32)
    return np.abs(mini[desplazamiento:] - mini[:n - desplazamiento]).mean(axis=(1, 2))


def movimiento_local(mini, ventana=VENTANA_MOVIMIENTO):
    """Cuanto cambia cada cuadro respecto de su vecino, suavizado con una
    mediana movil. Largo n (el ultimo repite al anterior)."""
    vecino = diferencias(mini, 1)
    if len(vecino) == 0:
        return np.zeros(len(mini), dtype=np.float32)
    vecino = np.append(vecino, vecino[-1])
    medio = ventana // 2
    salida = np.empty_like(vecino)
    for i in range(len(vecino)):
        salida[i] = np.median(vecino[max(0, i - medio):i + medio + 1])
    return salida


def racha_mas_larga(iguales, hueco=HUECO):
    """(inicio, largo) de la racha de True mas larga, tolerando hasta `hueco`
    False seguidos adentro. Largo 0 si no hay ninguna."""
    mejor = (0, 0)
    inicio = None
    ultimo_true = None
    for i, valor in enumerate(iguales):
        if valor:
            if inicio is None:
                inicio = i
            ultimo_true = i
        elif inicio is not None and i - ultimo_true > hueco:
            largo = ultimo_true - inicio + 1
            if largo > mejor[1]:
                mejor = (inicio, largo)
            inicio = None
    if inicio is not None:
        largo = ultimo_true - inicio + 1
        if largo > mejor[1]:
            mejor = (inicio, largo)
    return mejor


def recortar_bordes(dif, inicio, largo, borde=BORDE):
    """Achica la racha [inicio, inicio+largo) por los dos lados mientras la
    copia del borde sea peor que `borde` x la mediana de la racha (el fundido
    de la intro con el loop, o el del final)."""
    if largo <= 0:
        return inicio, largo
    tope = borde * float(np.median(dif[inicio:inicio + largo]))
    fin = inicio + largo
    while inicio < fin and dif[inicio] > tope:
        inicio += 1
    while fin > inicio and dif[fin - 1] > tope:
        fin -= 1
    return inicio, fin - inicio


def perfil(mini, min_desp, max_desp, umbral_abs=UMBRAL_ABS, umbral_rel=UMBRAL_REL):
    """Para cada desplazamiento: (d, inicio de la racha, largo, diferencia
    media dentro de la racha)."""
    mov = movimiento_local(mini)
    filas = []
    for d in range(max(1, int(min_desp)), min(int(max_desp), len(mini) - 1) + 1):
        dif = diferencias(mini, d)
        iguales = (dif <= umbral_abs) & (dif <= umbral_rel * mov[:len(dif)])
        inicio, largo = racha_mas_larga(iguales)
        media = float(dif[inicio:inicio + largo].mean()) if largo else float("inf")
        filas.append((d, inicio, largo, media))
    return filas


def detectar_loop(mini, fps_fuente, min_seg=0.5, max_seg=30.0,
                  umbral_abs=UMBRAL_ABS, umbral_rel=UMBRAL_REL):
    """El loop mas largo de la fuente, o None si no hay al menos una vuelta
    repetida completa. Devuelve un dict con cuadros de la FUENTE:
    intro (cuadros antes del loop), periodo, vueltas (completas, contando la
    primera), cola (cuadros despues de la ultima vuelta completa), diferencia
    media de las copias y movimiento medio del loop."""
    n = len(mini)
    min_desp = max(2, int(round(min_seg * fps_fuente)))
    max_desp = int(round(max_seg * fps_fuente))
    filas = perfil(mini, min_desp, max_desp, umbral_abs, umbral_rel)
    # Gana la racha mas larga; en empate, el periodo mas corto.
    candidatas = [f for f in filas if f[2] >= f[0]]   # al menos una vuelta entera repetida
    if not candidatas:
        return None
    d, inicio, largo, media = max(candidatas, key=lambda f: (f[2], -f[0]))
    inicio, largo = recortar_bordes(diferencias(mini, d), inicio, largo)
    if largo < d:
        return None
    media = float(diferencias(mini, d)[inicio:inicio + largo].mean())
    vueltas = (largo + d) // d
    fin = inicio + vueltas * d
    mov = movimiento_local(mini)
    return {
        "cuadros": n,
        "fps_fuente": float(fps_fuente),
        "intro": int(inicio),
        "periodo": int(d),
        "vueltas": int(vueltas),
        "cola": int(max(0, n - fin)),
        "dif_copias": media,
        "movimiento": float(mov[inicio:inicio + d].mean()),
    }


def ajustar_a_fps(periodo, fps_fuente, fps_destino):
    """(cuadros enteros del loop a fps_destino, factor de velocidad).
    factor = duracion nueva / duracion original (< 1 = un poco mas rapido)."""
    original = periodo / float(fps_fuente)
    cuadros = max(1, int(round(original * fps_destino)))
    return cuadros, (cuadros / float(fps_destino)) / original


def costura(mini, inicio, periodo):
    """Salto del ultimo cuadro del loop al primero, y su percentil entre los
    saltos normales de vecinos dentro del loop (0 = el mas suave, 100 = el
    mas brusco). Una costura buena cae dentro de lo normal (no por encima de
    todos)."""
    loop = mini[inicio:inicio + periodo]
    vecinos = np.abs(loop[1:] - loop[:-1]).mean(axis=(1, 2))
    salto = float(np.abs(loop[0] - loop[-1]).mean())
    percentil = 100.0 * float((vecinos < salto).sum()) / max(len(vecinos), 1)
    return salto, percentil, float(np.median(vecinos)) if len(vecinos) else 0.0


# --------------------------------------------------------------------------
# Reporte

def reporte(loop, fps_destino=None, salto=None):
    if loop is None:
        lineas = ["sin loop: ningun tramo se repite al menos una vez entera"]
        if salto is not None:
            lineas.append("archivo    como loop entero: salto final->inicio %.2f; percentil %.0f "
                          "entre vecinos (mediana %.2f)%s" % (
                              salto[0], salto[1], salto[2],
                              "  -> cierra como loop" if salto[1] < 100
                              else "  ** el corte final->inicio se nota **"))
        return lineas
    fps = loop["fps_fuente"]
    seg = lambda cuadros: cuadros / fps  # noqa: E731
    lineas = [
        "fuente     %d cuadros @ %.3f fps = %.2f s" % (loop["cuadros"], fps, seg(loop["cuadros"])),
        "intro      cuadros 0-%d  (%d cuadros, %.2f s)" % (
            loop["intro"] - 1, loop["intro"], seg(loop["intro"])) if loop["intro"] else
        "intro      ninguna (el video arranca en el loop)",
        "loop       cuadros %d-%d  (%d cuadros, %.3f s)" % (
            loop["intro"], loop["intro"] + loop["periodo"] - 1, loop["periodo"],
            seg(loop["periodo"])),
        "vueltas    %d completas  + cola de %d cuadros (%.2f s)" % (
            loop["vueltas"], loop["cola"], seg(loop["cola"])),
        "copias     diferencia media %.2f (0..255) con movimiento %.2f entre vecinos" % (
            loop["dif_copias"], loop["movimiento"]),
    ]
    if salto is not None:
        lineas.append("costura    salto %.2f; percentil %.0f entre los vecinos del loop "
                      "(mediana %.2f)%s" % (salto[0], salto[1], salto[2],
                                             "" if salto[1] < 100 else "  ** mas brusco que todos **"))
    if fps_destino:
        cuadros, factor = ajustar_a_fps(loop["periodo"], fps, fps_destino)
        aviso = "  ** revisar: cambio de velocidad > %d %% **" % int(VELOCIDAD_MAX * 100) \
            if abs(factor - 1) > VELOCIDAD_MAX else ""
        lineas.append("a %g fps  loop = %d cuadros (%.3f s; velocidad %+.1f %%)%s" % (
            fps_destino, cuadros, cuadros / float(fps_destino), (1 / factor - 1) * 100, aviso))
        total = loop["intro"] + loop["vueltas"] * loop["periodo"] + loop["cola"]
        lineas.append("ahorro     viajan intro + 1 vuelta = %.1f %% de los cuadros" % (
            100.0 * (loop["intro"] + loop["periodo"]) / max(total, 1)))
    return lineas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente", help="el video a analizar")
    parser.add_argument("--fps-destino", type=float, default=None,
                        help="ajusta el loop a cuadros enteros a esta cadencia")
    parser.add_argument("--min-seg", type=float, default=0.5, help="loop mas corto a buscar")
    parser.add_argument("--max-seg", type=float, default=30.0, help="loop mas largo a buscar")
    parser.add_argument("--umbral-abs", type=float, default=UMBRAL_ABS)
    parser.add_argument("--umbral-rel", type=float, default=UMBRAL_REL)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args(argv)

    fps = fps_de_fuente(args.ffmpeg, args.fuente)
    mini = leer_miniaturas(args.ffmpeg, args.fuente)
    loop = detectar_loop(mini, fps, args.min_seg, args.max_seg,
                         args.umbral_abs, args.umbral_rel)
    if loop:
        salto = costura(mini, loop["intro"], loop["periodo"])
    else:
        salto = costura(mini, 0, len(mini)) if len(mini) > 2 else None
    for linea in reporte(loop, args.fps_destino, salto):
        print(linea)
    return 0 if loop else 1


if __name__ == "__main__":
    sys.exit(main())
