#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Colores canonicos de las diez entradas reservadas del overlay.

Asignacion de INT-001 §4.3, alineada con los niveles del horneado de glifos
de E-06 (246..251): el antialias del glifo interpola entre el fondo del panel
y el texto. Estos RGB se estampan al final de CADA epoca de paleta cuando el
encoder corre con ``reserved=10`` (INV-4) y viajan en el campo
``reserved_rgb`` del sidecar ASCLSLOT para la verificacion cruzada.
"""
import numpy as np

RESERVED_FIRST = 246

RESERVED_RGB = np.array([
    (16, 16, 30),     # 246 fondo del panel
    (64, 64, 74),     # 247 antialias 1
    (113, 113, 124),  # 248 antialias 2
    (161, 161, 173),  # 249 antialias 3
    (209, 209, 220),  # 250 antialias 4
    (255, 255, 255),  # 251 texto base
    (255, 200, 0),    # 252 texto destacado
    (0, 200, 0),      # 253 estado A
    (200, 0, 0),      # 254 estado B
    (0, 0, 0),        # 255 transparente: nunca se pinta
], dtype=np.uint8)


def reserved_rgb_bytes():
    """Los 30 bytes (10 RGB) para el header del sidecar."""
    return RESERVED_RGB.tobytes()
