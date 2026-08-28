#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geometria canonica del panel de 20 numeros (INT-001 §1, caso de referencia).

Unica fuente de verdad del layout: ``tools/make_panel.py`` la usa para el
sidecar ASCLSLOT y ``encoder.encode_video`` (via ``protect_panel``) para
excluir los mismos rectangulos del dither automatico (INT-001 §11: el base
bajo el panel no deriva por dither; mecanismo ``protected_rects`` de E-05).
"""

GLYPH_W, GLYPH_H = 8, 12
N_FIELDS = 20
GROUPS_PER_ROW = 10
DIGIT_GAP = 2     # celdas entre los dos digitos de un numero
GROUP_GAP = 20    # celdas entre numeros de una misma fila
ROW_GAP = 8       # celdas entre las dos filas
BOTTOM_MARGIN = 16


def panel_rects(cols, rows):
    """Rectangulos ``(x, y, w, h)`` de los 40 slots, en celdas.

    Determinista; lanza ``ValueError`` si la grilla no alcanza. Es el mismo
    layout que el sidecar del panel, por construccion.
    """
    group_w = GLYPH_W * 2 + DIGIT_GAP
    row_w = GROUPS_PER_ROW * group_w + (GROUPS_PER_ROW - 1) * GROUP_GAP
    if row_w > cols:
        raise ValueError("grilla de %d columnas no alcanza para el panel (%d)"
                         % (cols, row_w))
    x0 = (cols - row_w) // 2
    y_bottom = rows - GLYPH_H - BOTTOM_MARGIN
    y_top = y_bottom - GLYPH_H - ROW_GAP
    if y_top < 0:
        raise ValueError("grilla de %d filas no alcanza para el panel" % rows)
    rects = []
    for number in range(N_FIELDS):
        row, column = divmod(number, GROUPS_PER_ROW)
        x = x0 + column * (group_w + GROUP_GAP)
        y = y_top if row == 0 else y_bottom
        rects.append((x, y, GLYPH_W, GLYPH_H))
        rects.append((x + GLYPH_W + DIGIT_GAP, y, GLYPH_W, GLYPH_H))
    return rects
