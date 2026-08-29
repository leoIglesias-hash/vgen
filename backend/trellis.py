#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trellis del encoder: la etapa que decide indices FINALES antes de emitir.

E-19 congela el orden canonico del pipeline por frame:

    cuantizar -> ditherear -> trellis -> emitir

y con el una regla de convivencia: **el `--threshold` no es una etapa aparte
que corre junto al trellis, es el caso degenerado del trellis**. Hoy el trellis
solo sabe hacer eso (revertir al frame anterior cuando el color casi no se
movio); E-20 a E-23 lo extienden ampliando ESTE modulo, no agregando pasadas
nuevas al bucle del encoder.

Por que importa el orden: cada etapa lee lo que decidio la anterior, y las tres
primeras escriben sobre la MISMA columna de indices (`cells[:, 0]`). Cuando dos
de ellas corren en el orden equivocado, la segunda deshace en silencio lo que
decidio la primera. Eso fue exactamente el bug de E-18: el revert del threshold
pisaba celdas que el dither habia tramado, rompiendo el patron Bayer distinto
en cada frame. Aca ese contrato queda explicito y verificable en vez de
depender del orden en que esten escritos los bloques del bucle.

E-20 agrega la metrica: el umbral puede medirse en euclidea sRGB (historico, el
default) o en delta-E Oklab, donde un mismo numero significa el mismo cambio
visible en las sombras y en las luces. La paleta se convierte al espacio de la
metrica UNA vez por paleta, asi que Oklab no cuesta mas por frame que sRGB.

El decoder no conoce este modulo: la salida sigue siendo una matriz comun de
indices de paleta ASCL v1.
"""

import numpy as np

import perceptual_palette


# Orden canonico del pipeline por frame (E-19). Es la fuente de verdad del
# contrato: los tests lo importan de aca en vez de repetir la lista.
CANONICAL_STAGES = ("quantize", "dither", "trellis", "emit")

# E-20: espacio en el que el trellis mide "cuanto cambio esta celda".
#   rgb   - euclidea en sRGB. Es el camino historico y sigue siendo el default:
#           un `--threshold N` que ya existia significa exactamente lo mismo que
#           antes (regla 9, los valores del operador no se reinterpretan solos).
#   oklab - delta-E perceptual. Un mismo numero significa el mismo cambio VISIBLE en
#           todo el rango, mientras que en sRGB el mismo salto numerico se ve
#           mucho mas en las sombras que en las luces. La escala es otra: los
#           valores utiles rondan 0,01-0,05, no 10-40.
THRESHOLD_METRICS = ("rgb", "oklab")


def canonical_order_index(stage):
    """Posicion de una etapa en el orden canonico. Lanza si no existe."""
    return CANONICAL_STAGES.index(stage)


def build_threshold_palette(palette_rgb, metric="rgb"):
    """Pasa la paleta al espacio de la metrica, UNA vez por paleta.

    El trellis compara distancias celda por celda, asi que convertir aca (y no
    adentro del bucle) es lo que hace que `oklab` cueste lo mismo que `rgb` por
    frame. El encoder la reconstruye solo cuando cambia la paleta activa.

    `rgb` devuelve int32 a proposito: en int16 el `einsum` de la distancia al
    cuadrado desborda (255^2 * 3 = 195.075 no entra en int16).
    """
    if metric not in THRESHOLD_METRICS:
        raise ValueError("metrica de threshold desconocida: %r" % (metric,))
    palette = np.asarray(palette_rgb)
    if metric == "oklab":
        return perceptual_palette.srgb_to_oklab(palette.astype(np.uint8))
    return palette.astype(np.int32)


def apply_threshold_trellis(cells, prev_cells, palette_metric, threshold,
                            protected_mask=None):
    """Caso degenerado del trellis: congelar celdas que casi no cambiaron.

    Para cada celda compara su color contra el que tenia en el frame anterior y,
    si la distancia no supera `threshold`, emite el indice ANTERIOR en lugar del
    nuevo. Eso hace que la celda desaparezca del DELTA y el frame comprima
    mejor, a cambio de congelar un cambio de color minimo.

    `palette_metric` ya viene en el espacio de la metrica (`build_threshold_palette`),
    asi que la cuenta es la misma para sRGB y para Oklab: lo unico que cambia es
    la escala en la que hay que leer `threshold` (E-20).

    `protected_mask` marca celdas que NO pueden revertirse aunque cumplan el
    umbral (E-18: lo que el dither decidio tramar). Sin ella, una celda tramada
    difiere de su predecesora justo por un vecino de paleta — exactamente la
    distancia que el umbral lee como "sin cambio" — y el revert deshace el
    tramado de forma sistematica.

    Devuelve `(cells, details)`. `cells` es un array nuevo cuando hubo cambios y
    el mismo objeto cuando no hubo ninguno; nunca se muta el argumento
    (invariante 4: `cells` jamas queda a medias).
    """
    if threshold <= 0 or prev_cells is None or palette_metric is None:
        return cells, {"reverted_cells": 0, "protected_cells": 0}

    current = cells[:, 0]
    delta = palette_metric[current] - palette_metric[prev_cells[:, 0]]
    keep = np.einsum("ij,ij->i", delta, delta) <= threshold * threshold

    protected = 0
    if protected_mask is not None:
        rescued = int(np.count_nonzero(keep & protected_mask))
        if rescued:
            keep &= ~protected_mask
            protected = rescued

    reverted = int(np.count_nonzero(keep))
    if not reverted:
        return cells, {"reverted_cells": 0, "protected_cells": protected}

    emitted = cells.copy()
    emitted[keep, 0] = prev_cells[keep, 0]
    return emitted, {"reverted_cells": reverted, "protected_cells": protected}
