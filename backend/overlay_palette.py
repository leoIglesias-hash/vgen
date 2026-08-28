#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Colores canonicos de las entradas de paleta reservadas al overlay.

Dos reservas canonicas (INT-003 D1):

- ``RESERVED_RGB`` (10 entradas, 246..255): la reserva original de INT-001
  §4.3, alineada con los niveles del horneado de glifos de E-06.
- ``RESERVED_RGB_32`` (32 entradas, 224..255): la reserva ampliada de
  DISENO-PARCHES-GENERICOS §4. Sus ULTIMAS DIEZ FILAS SON BIT-IDENTICAS a
  ``RESERVED_RGB``: los glifos ya horneados (246..255) siguen validos, 255
  sigue siendo el transparente, y un sidecar v1 valida contra un clip
  encodeado con reserva de 32.

Estos RGB se estampan al final de CADA epoca de paleta cuando el encoder
corre con ``reserved=N`` (INV-4) y viajan en el campo ``reserved_rgb`` del
sidecar ASCLSLOT para la verificacion cruzada.
"""
import numpy as np

RESERVED_FIRST = 246  # primer indice de la reserva de 10 (compat F7)

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

# INT-003 §4: 22 colores de arte generico para parches (224..245).
ART_RGB_22 = np.array([
    (128, 0, 0),      # 224 rojo oscuro
    (255, 0, 0),      # 225 rojo
    (255, 128, 128),  # 226 rojo claro
    (128, 64, 0),     # 227 marron
    (255, 128, 0),    # 228 naranja
    (255, 255, 0),    # 229 amarillo
    (128, 128, 0),    # 230 oliva
    (0, 128, 0),      # 231 verde oscuro
    (0, 255, 0),      # 232 verde
    (128, 255, 128),  # 233 verde claro
    (0, 128, 128),    # 234 verde azulado
    (0, 255, 255),    # 235 cian
    (0, 0, 128),      # 236 azul oscuro
    (0, 0, 255),      # 237 azul
    (128, 128, 255),  # 238 azul claro
    (128, 0, 128),    # 239 purpura
    (255, 0, 255),    # 240 magenta
    (255, 128, 192),  # 241 rosa
    (255, 224, 189),  # 242 piel clara
    (141, 85, 36),    # 243 piel oscura
    (192, 192, 192),  # 244 plata
    (255, 215, 0),    # 245 oro
], dtype=np.uint8)

RESERVED_RGB_32 = np.vstack([ART_RGB_22, RESERVED_RGB])

RESERVED_COUNTS = (10, 32)


def reserved_table(count):
    """La tabla RGB canonica para una reserva de ``count`` entradas."""
    count = int(count)
    if count == 10:
        return RESERVED_RGB
    if count == 32:
        return RESERVED_RGB_32
    raise ValueError("reserva no canonica: %r (solo 10 o 32)" % (count,))


def reserved_first(count):
    """Primer indice reservado para una reserva de ``count`` entradas."""
    return 256 - int(count)


def reserved_rgb_bytes(count=10):
    """Los ``3*count`` bytes para el header del sidecar ASCLSLOT."""
    return reserved_table(count).tobytes()
