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

El decoder no conoce este modulo: la salida sigue siendo una matriz comun de
indices de paleta ASCL v1.
"""

import numpy as np


# Orden canonico del pipeline por frame (E-19). Es la fuente de verdad del
# contrato: los tests lo importan de aca en vez de repetir la lista.
CANONICAL_STAGES = ("quantize", "dither", "trellis", "emit")


def canonical_order_index(stage):
    """Posicion de una etapa en el orden canonico. Lanza si no existe."""
    return CANONICAL_STAGES.index(stage)


def apply_threshold_trellis(cells, prev_cells, palette_rgb, threshold,
                            protected_mask=None):
    """Caso degenerado del trellis: congelar celdas que casi no cambiaron.

    Para cada celda compara su color contra el que tenia en el frame anterior y,
    si la distancia euclidea en RGB no supera `threshold`, emite el indice
    ANTERIOR en lugar del nuevo. Eso hace que la celda desaparezca del DELTA y
    el frame comprima mejor, a cambio de congelar un cambio de color minimo.

    `protected_mask` marca celdas que NO pueden revertirse aunque cumplan el
    umbral (E-18: lo que el dither decidio tramar). Sin ella, una celda tramada
    difiere de su predecesora justo por un vecino de paleta — exactamente la
    distancia que el umbral lee como "sin cambio" — y el revert deshace el
    tramado de forma sistematica.

    Devuelve `(cells, details)`. `cells` es un array nuevo cuando hubo cambios y
    el mismo objeto cuando no hubo ninguno; nunca se muta el argumento
    (invariante 4: `cells` jamas queda a medias).
    """
    if threshold <= 0 or prev_cells is None or palette_rgb is None:
        return cells, {"reverted_cells": 0, "protected_cells": 0}

    current = cells[:, 0]
    delta = (palette_rgb[current].astype(np.int32)
             - palette_rgb[prev_cells[:, 0]].astype(np.int32))
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
