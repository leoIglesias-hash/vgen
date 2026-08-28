#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-08 — DEFLATE al mejor postor: zlib siempre, Zopfli si esta instalado.

Un solo punto de verdad para los cinco sitios de compresion del encoder y el
transcodificador (encoder.py x3, ascl_v2.py, regional_codec_v2.py). Ambos lados
de ``transcode_ascl_bytes`` (payload v1 heredado y candidatos v2) pasan por esta
funcion, de modo que la comparacion de longitudes nunca sufre asimetria de
herramienta.

Zopfli emite un stream zlib estandar (RFC 1950): ningun decoder cambia.
El fallback a zlib es automatico y silencioso; la regresion corre en verde con
y sin el paquete instalado.
"""

import os
import zlib

try:
    import zopfli.zlib as _zopfli_zlib
except ImportError:
    _zopfli_zlib = None

# Iteraciones estandar de Zopfli; mas alto = mas lento con retorno decreciente.
ZOPFLI_ITERATIONS = int(os.environ.get("ASCL_ZOPFLI_ITERATIONS", "15"))


def have_zopfli():
    return _zopfli_zlib is not None


def best_deflate(data, level=9, iterations=None):
    """Devuelve el stream zlib mas corto entre zlib.compress y Zopfli.

    Determinista para un entorno dado: con Zopfli instalado gana siempre el
    candidato estrictamente menor; en empate se conserva el de zlib.
    """
    a = zlib.compress(data, level)
    if _zopfli_zlib is None:
        return a
    if iterations is None:
        iterations = ZOPFLI_ITERATIONS
    b = _zopfli_zlib.compress(data, numiterations=iterations)
    return b if len(b) < len(a) else a
