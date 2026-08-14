#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transcodificador lossless ASCL v1 -> ASCL v2 exacto.

La conversión no vuelve a cuantizar ni evalúa calidad visual. Decodifica una sola
matriz de índices a la vez y, para cada frame, conserva el bloque v1 original salvo
que una representación regional o predictiva reconstruya exactamente la misma
matriz con menos bytes.
"""

from __future__ import print_function

import argparse
import os
import struct
import sys
import zlib

import numpy as np

import ascl_bundle
import regional_codec_v2


MAGIC = b"ASCL"
VERSION_V1 = 1
VERSION_V2 = 2
MODE_PIXEL = 3
TAG_RAW = 0
TAG_ZLIB = 1
TAG_DELTA = 2
TAG_DELTA_MASK = 3
TAG_REGIONAL_KEY_RAW = 4
TAG_REGIONAL_KEY_ZLIB = 5
TAG_REGIONAL_DELTA_RAW = 6
TAG_REGIONAL_DELTA_ZLIB = 7
TAG_PREDICT_KEY_ZLIB = 8
TAG_PREDICT_DELTA_ZLIB = 9
PRED_LEFT = 0
PRED_TOP = 1
PRED_GRADIENT = 2
PRED_PREVIOUS_SUB = 3
PRED_PREVIOUS_XOR = 4
KEY_TAGS = (TAG_RAW, TAG_ZLIB, TAG_REGIONAL_KEY_RAW, TAG_REGIONAL_KEY_ZLIB,
            TAG_PREDICT_KEY_ZLIB)
DELTA_TAGS = (TAG_DELTA, TAG_DELTA_MASK,
              TAG_REGIONAL_DELTA_RAW, TAG_REGIONAL_DELTA_ZLIB,
              TAG_PREDICT_DELTA_ZLIB)

HEADER_FMT = "<4sBBBBHHHIBBIHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
UINT32_MAX = (1 << 32) - 1
FLAG_HAS_OFFSET_TABLE = 8
FLAG_PAL_PER_SCENE = 2
FLAG_PAL_GLOBAL = 4
CODEC_FLAG_REGIONAL = 1
DEFAULT_TILE_SIZE = 16
MAX_DECODE_BYTES = 64 * 1024 * 1024


class ASCLV2Error(ValueError):
    pass


def _fail(message):
    raise ASCLV2Error(message)


def _crc_v2(buf):
    """CRC v2: protege header/metadata y cuerpo, omitiendo el propio CRC."""
    value = zlib.crc32(buf[:28])
    return zlib.crc32(buf[32:], value) & 0xFFFFFFFF


def _inflate_bounded(payload, maximum, label):
    """Descomprime un zlib sin permitir salida, cola o stream extra."""
    try:
        dec = zlib.decompressobj()
        raw = dec.decompress(payload, maximum + 1)
        if len(raw) > maximum or dec.unconsumed_tail:
            _fail("%s excede el limite de salida" % label)
        raw += dec.flush()
    except zlib.error as exc:
        _fail("%s zlib invalido: %s" % (label, exc))
    if len(raw) > maximum:
        _fail("%s excede el limite de salida" % label)
    if not dec.eof or dec.unused_data:
        _fail("%s zlib truncado o con stream extra" % label)
    return raw


def _header_fields(buf, expected_version=None):
    if len(buf) < HEADER_SIZE:
        _fail("ASCL truncado")
    fields = struct.unpack_from(HEADER_FMT, buf, 0)
    (magic, version, mode, flags, fps, cols, rows, pal_size, n_frames,
     ramp_len, cell_fmt, data_off, char_aspect, reserved, crc32) = fields
    if magic != MAGIC:
        _fail("magic ASCL invalido")
    if expected_version is not None and version != expected_version:
        _fail("se esperaba ASCL v%d y se recibio v%d" % (expected_version, version))
    if version not in (VERSION_V1, VERSION_V2):
        _fail("version ASCL no soportada: %d" % version)
    if mode != MODE_PIXEL:
        _fail("ASCL v2 regional inicial solo admite mode=pixel")
    if flags & 0xE0:
        _fail("flags reservados activos")
    if not (flags & FLAG_HAS_OFFSET_TABLE):
        _fail("falta tabla de offsets")
    if (flags & FLAG_PAL_PER_SCENE) and (flags & FLAG_PAL_GLOBAL):
        _fail("flags de paleta incompatibles")
    if fps == 0 or cols == 0 or rows == 0 or n_frames == 0:
        _fail("header ASCL con valores vacios")
    if pal_size < 1 or pal_size > 256:
        _fail("pal_size fuera de rango")
    if ramp_len != 0 or data_off != HEADER_SIZE or cell_fmt != MODE_PIXEL:
        _fail("header PIXEL incompatible")
    if char_aspect == 0:
        _fail("char_aspect invalido")
    if data_off + n_frames * 4 > len(buf):
        _fail("tabla de offsets truncada")
    n = cols * rows
    tile_cols = (cols + DEFAULT_TILE_SIZE - 1) // DEFAULT_TILE_SIZE
    tile_rows = (rows + DEFAULT_TILE_SIZE - 1) // DEFAULT_TILE_SIZE
    tile_count = tile_cols * tile_rows
    # Mismos topes que ReaderV2: evitan que un header diminuto declare un
    # inflate de varios GiB y garantizan que el resultado sea reproducible en TV.
    if n * 5 > MAX_DECODE_BYTES:
        _fail("dimensiones exceden limite DELTA operativo")
    if n * 7 + tile_count * 8 > MAX_DECODE_BYTES:
        _fail("dimensiones exceden limite regional operativo")
    if version == VERSION_V1 and reserved != 0:
        _fail("reserved v1 debe ser cero")
    if version == VERSION_V2:
        tile_size = reserved & 255
        codec_flags = reserved >> 8
        if tile_size != DEFAULT_TILE_SIZE:
            _fail("tile_size v2 no soportado: %d" % tile_size)
        if codec_flags != CODEC_FLAG_REGIONAL:
            _fail("codec_flags v2 no soportado: 0x%02X" % codec_flags)
    return {
        "fields": fields,
        "version": version,
        "mode": mode,
        "flags": flags,
        "fps": fps,
        "cols": cols,
        "rows": rows,
        "pal_size": pal_size,
        "n_frames": n_frames,
        "ramp_len": ramp_len,
        "cell_fmt": cell_fmt,
        "data_off": data_off,
        "char_aspect": char_aspect,
        "reserved": reserved,
        "crc32": crc32,
    }


def _validate_crc(buf, header):
    expected = header["crc32"]
    if header["version"] == VERSION_V1 and not expected:
        return
    actual = (zlib.crc32(buf[HEADER_SIZE:]) & 0xFFFFFFFF
              if header["version"] == VERSION_V1 else _crc_v2(buf))
    if actual != expected:
        _fail("CRC32 ASCL v%d invalido" % header["version"])


def _validate_palette_values(values, palette_entries, label):
    if palette_entries < 1 or palette_entries > 256:
        _fail("cantidad de paleta activa invalida")
    if len(values) and palette_entries < 256 and int(np.max(values)) >= palette_entries:
        _fail("%s contiene indice de paleta fuera de rango" % label)


def _decode_v1_payload(tag, payload, previous, n, palette_entries):
    if tag == TAG_RAW:
        if len(payload) != n:
            _fail("RAW con longitud incorrecta")
        values = np.frombuffer(payload, dtype=np.uint8)
        _validate_palette_values(values, palette_entries, "RAW")
        return values.copy()
    if tag == TAG_ZLIB:
        raw = _inflate_bounded(payload, n, "ZLIB")
        if len(raw) != n:
            _fail("ZLIB con longitud descomprimida incorrecta")
        values = np.frombuffer(raw, dtype=np.uint8)
        _validate_palette_values(values, palette_entries, "ZLIB")
        return values.copy()
    if previous is None:
        _fail("primer frame no puede ser DELTA")
    cells = previous.copy()
    if tag == TAG_DELTA:
        raw = _inflate_bounded(payload, n * 5, "DELTA")
        if len(raw) % 5:
            _fail("DELTA con longitud invalida")
        count = len(raw) // 5
        if count > n:
            _fail("DELTA excede una tupla por celda")
        offsets = np.frombuffer(raw, dtype="<u4", count=count, offset=0)
        values = np.frombuffer(raw, dtype=np.uint8, count=count, offset=count * 4)
        if count and int(offsets.max()) >= n:
            _fail("DELTA con offset fuera de rango")
        # Se validan incluso valores de offsets repetidos que luego serian
        # sobrescritos. Un stream corrupto nunca se sanea al transcodificarlo.
        _validate_palette_values(values, palette_entries, "DELTA")
        # El orden histórico es válido y, ante repetidos, la última tupla gana.
        for index, value in zip(offsets, values):
            cells[int(index)] = value
        return cells
    if tag == TAG_DELTA_MASK:
        mask_len = (n + 7) // 8
        raw = _inflate_bounded(payload, mask_len + n, "DELTA_MASK")
        if len(raw) < mask_len:
            _fail("DELTA_MASK truncado")
        mask = np.frombuffer(raw, dtype=np.uint8, count=mask_len)
        if n & 7 and (int(mask[-1]) >> (n & 7)):
            _fail("DELTA_MASK con bits de padding activos")
        bits = np.unpackbits(mask, bitorder="little", count=n).astype(bool)
        count = int(bits.sum())
        if len(raw) != mask_len + count:
            _fail("DELTA_MASK con valores faltantes o extra")
        values = np.frombuffer(raw, dtype=np.uint8, count=count, offset=mask_len)
        _validate_palette_values(values, palette_entries, "DELTA_MASK")
        cells[bits] = values
        return cells
    _fail("tag v1 desconocido: %d" % tag)


def _validate_predictor_dimensions(rows, cols):
    """Valida dimensiones antes de descomprimir o reservar matrices.

    Se replica el limite operativo que aplica el header ASCL. Mantenerlo tambien
    en la API focal evita que un caller directo convierta un payload diminuto en
    una reserva desproporcionada.
    """
    if (isinstance(rows, bool) or isinstance(cols, bool) or
            not isinstance(rows, (int, np.integer)) or
            not isinstance(cols, (int, np.integer))):
        _fail("dimensiones PREDICT deben ser enteras")
    rows = int(rows)
    cols = int(cols)
    if rows <= 0 or cols <= 0:
        _fail("dimensiones PREDICT deben ser positivas")
    cells = rows * cols
    if cells * 5 > MAX_DECODE_BYTES:
        _fail("dimensiones exceden limite PREDICT operativo")
    return rows, cols, cells


def _predictor_matrix(matrix, label):
    if not isinstance(matrix, np.ndarray):
        _fail("%s debe ser numpy.ndarray" % label)
    if matrix.ndim != 2:
        _fail("%s requiere matriz HxW" % label)
    if matrix.dtype != np.uint8:
        _fail("%s debe usar dtype uint8" % label)
    _validate_predictor_dimensions(matrix.shape[0], matrix.shape[1])
    return matrix


def _predictor_previous(previous, shape, label):
    if previous is None:
        _fail("%s requiere previous HxW" % label)
    if (not isinstance(previous, np.ndarray) or previous.ndim != 2 or
            previous.shape != shape or previous.dtype != np.uint8):
        _fail("%s requiere previous HxW compatible" % label)
    return previous


def _predict_residual(matrix, predictor, previous=None):
    """Transformada reversible de un byte; no altera el frame reconstruido."""
    current = _predictor_matrix(matrix, "predictor")
    if predictor == PRED_LEFT:
        residual = np.empty_like(current)
        residual[:, 0] = current[:, 0]
        np.subtract(current[:, 1:], current[:, :-1],
                    dtype=np.uint8, out=residual[:, 1:])
        return residual
    if predictor == PRED_TOP:
        residual = np.empty_like(current)
        residual[0, :] = current[0, :]
        np.subtract(current[1:, :], current[:-1, :],
                    dtype=np.uint8, out=residual[1:, :])
        return residual
    if predictor == PRED_GRADIENT:
        # current-left-top+top_left equivale a diferenciar primero en X y
        # despues en Y. Dos scratchs sustituyen cinco matrices temporales.
        horizontal = np.empty_like(current)
        horizontal[:, 0] = current[:, 0]
        np.subtract(current[:, 1:], current[:, :-1],
                    dtype=np.uint8, out=horizontal[:, 1:])
        residual = np.empty_like(current)
        residual[0, :] = horizontal[0, :]
        np.subtract(horizontal[1:, :], horizontal[:-1, :],
                    dtype=np.uint8, out=residual[1:, :])
        return residual
    if predictor not in (PRED_PREVIOUS_SUB, PRED_PREVIOUS_XOR):
        _fail("predictor desconocido: %d" % predictor)
    prior = _predictor_previous(previous, current.shape, "predictor temporal")
    if predictor == PRED_PREVIOUS_SUB:
        return np.subtract(current, prior, dtype=np.uint8)
    if predictor == PRED_PREVIOUS_XOR:
        return np.bitwise_xor(current, prior)


def _restore_predictor(residual, predictor, previous=None):
    residual = _predictor_matrix(residual, "residual predictor")
    if predictor in (PRED_PREVIOUS_SUB, PRED_PREVIOUS_XOR):
        prior = _predictor_previous(
            previous, residual.shape, "predictor temporal")
        if predictor == PRED_PREVIOUS_SUB:
            return np.add(prior, residual, dtype=np.uint8)
        return np.bitwise_xor(prior, residual)
    if predictor not in (PRED_LEFT, PRED_TOP, PRED_GRADIENT):
        _fail("predictor key desconocido")
    # LEFT/TOP son diferencias de primer orden; GRADIENT es la diferencia
    # separable en ambos ejes. Las acumulaciones uint8 conservan exactamente la
    # aritmetica modular del stream y evitan un bucle Python por celda.
    if predictor == PRED_LEFT:
        return np.add.accumulate(residual, axis=1, dtype=np.uint8)
    if predictor == PRED_TOP:
        return np.add.accumulate(residual, axis=0, dtype=np.uint8)
    result = np.empty_like(residual)
    np.add.accumulate(residual, axis=0, dtype=np.uint8, out=result)
    np.add.accumulate(result, axis=1, dtype=np.uint8, out=result)
    return result


def encode_predictor_payload(matrix, keyframe, previous=None, zlib_level=9):
    """Elige mecánicamente el predictor exacto de menor payload."""
    predictor_ids = ((PRED_LEFT, PRED_TOP, PRED_GRADIENT) if keyframe else
                     (PRED_PREVIOUS_SUB, PRED_PREVIOUS_XOR))
    candidates = []
    for predictor in predictor_ids:
        residual = _predict_residual(matrix, predictor, previous)
        payload = bytes((predictor,)) + zlib.compress(residual.tobytes(), zlib_level)
        candidates.append((len(payload), predictor, payload))
    _length, predictor, payload = min(candidates, key=lambda item: (item[0], item[1]))
    return ((TAG_PREDICT_KEY_ZLIB if keyframe else TAG_PREDICT_DELTA_ZLIB),
            payload, predictor)


def decode_predictor_payload(payload, rows, cols, keyframe, previous=None):
    rows, cols, cells = _validate_predictor_dimensions(rows, cols)
    if len(payload) < 2:
        _fail("payload predictor truncado")
    predictor = payload[0]
    allowed = ((PRED_LEFT, PRED_TOP, PRED_GRADIENT) if keyframe else
               (PRED_PREVIOUS_SUB, PRED_PREVIOUS_XOR))
    if predictor not in allowed:
        _fail("predictor incompatible con key/delta")
    raw = _inflate_bounded(payload[1:], cells, "PREDICT")
    if len(raw) != cells:
        _fail("PREDICT con longitud descomprimida incorrecta")
    residual = np.frombuffer(raw, dtype=np.uint8).reshape(rows, cols)
    return _restore_predictor(residual, predictor, previous)


def _frame_blocks_v1(buf, header):
    """Itera bloques v1 validados sin retener matrices de todos los frames."""
    n = header["cols"] * header["rows"]
    expected = header["data_off"] + header["n_frames"] * 4
    current_palette_count = 0
    previous = None
    for index in range(header["n_frames"]):
        offset = struct.unpack_from("<I", buf, header["data_off"] + index * 4)[0]
        if offset != expected or offset > len(buf) - 7:
            _fail("offset no contiguo o frame truncado en %d" % index)
        block_len = struct.unpack_from("<I", buf, offset)[0]
        end = offset + 4 + block_len
        if block_len < 3 or end > len(buf):
            _fail("block_len fuera de rango en %d" % index)
        tag = buf[offset + 4]
        pal_count = struct.unpack_from("<H", buf, offset + 5)[0]
        if tag > TAG_DELTA_MASK:
            _fail("entrada no es ASCL v1 canonico")
        if pal_count > header["pal_size"] or pal_count > 256:
            _fail("pal_count fuera de rango")
        if tag in (TAG_DELTA, TAG_DELTA_MASK) and pal_count:
            _fail("DELTA no puede cambiar paleta")
        palette_start = offset + 7
        payload_start = palette_start + pal_count * 3
        if payload_start > end:
            _fail("paleta truncada")
        palette = bytes(buf[palette_start:payload_start])
        payload = bytes(buf[payload_start:end])
        if tag != TAG_RAW and not payload:
            _fail("payload comprimido vacio")
        if pal_count:
            current_palette_count = pal_count
        if not current_palette_count:
            _fail("frame PIXEL sin paleta activa")
        keyframe = tag in (TAG_RAW, TAG_ZLIB)
        if header["flags"] & FLAG_PAL_GLOBAL:
            if index == 0 and not pal_count:
                _fail("paleta global ausente")
            if index > 0 and pal_count:
                _fail("paleta global reemitida")
        elif header["flags"] & FLAG_PAL_PER_SCENE:
            if keyframe and not pal_count:
                _fail("keyframe temporal sin paleta")
        elif not pal_count:
            _fail("paleta per-frame ausente")
        cells = _decode_v1_payload(
            tag, payload, previous, n, current_palette_count)
        if int(cells.max()) >= current_palette_count:
            _fail("indice de paleta fuera de rango")
        yield {
            "index": index,
            "tag": tag,
            "pal_count": pal_count,
            "palette": palette,
            "payload": payload,
            "cells": cells,
            "keyframe": keyframe,
        }
        previous = cells
        expected = end
    if expected != len(buf):
        _fail("bytes extra al final del ASCL")


def _build_v2(header, blocks, tile_size, codec_flags):
    n_frames = len(blocks)
    data_off = HEADER_SIZE
    first_offset = data_off + n_frames * 4
    offsets = []
    offset = first_offset
    encoded_blocks = []
    for frame in blocks:
        body = struct.pack("<BH", frame["tag"], frame["pal_count"])
        body += frame["palette"] + frame["payload"]
        if len(body) > UINT32_MAX or offset > UINT32_MAX:
            _fail("ASCL v2 excede offsets uint32")
        block = struct.pack("<I", len(body)) + body
        offsets.append(offset)
        encoded_blocks.append(block)
        offset += len(block)
    if offset > UINT32_MAX + 1:
        _fail("ASCL v2 excede 4 GiB")
    table = struct.pack("<%dI" % n_frames, *offsets)
    body = table + b"".join(encoded_blocks)
    f = header["fields"]
    reserved = int(tile_size) | (int(codec_flags) << 8)
    provisional = struct.pack(
        HEADER_FMT, MAGIC, VERSION_V2, f[2], f[3], f[4], f[5], f[6], f[7],
        f[8], f[9], f[10], data_off, f[12], reserved, 0)
    out = provisional + body
    crc = _crc_v2(out)
    final_header = provisional[:28] + struct.pack("<I", crc)
    return final_header + body


def transcode_ascl_bytes(source, tile_size=DEFAULT_TILE_SIZE,
                         codec_flags=CODEC_FLAG_REGIONAL, verify_roundtrip=True):
    """Convierte bytes ASCL v1 a v2 y devuelve ``(bytes, stats)``."""
    source = bytes(source)
    header = _header_fields(source, VERSION_V1)
    _validate_crc(source, header)
    if tile_size != DEFAULT_TILE_SIZE or codec_flags != CODEC_FLAG_REGIONAL:
        _fail("esta revision v2 exige tile_size=16 y codec_flags=0x01")

    blocks = []
    previous = None
    source_payload_bytes = 0
    output_payload_bytes = 0
    regional_frames = 0
    predictor_frames = 0
    source_tags = dict((i, 0) for i in range(4))
    output_tags = dict((i, 0) for i in range(10))
    command_counts = {}
    predictor_counts = {}
    for frame in _frame_blocks_v1(source, header):
        matrix = frame["cells"].reshape(header["rows"], header["cols"])
        previous_matrix = (None if previous is None else
                           previous.reshape(header["rows"], header["cols"]))
        regional = regional_codec_v2.encode_payload(
            matrix,
            previous=(None if frame["keyframe"] else previous_matrix),
            tile_size=tile_size, zlib_level=9)
        predictor_tag, predictor_payload, predictor_id = encode_predictor_payload(
            matrix, frame["keyframe"], previous=previous_matrix, zlib_level=9)
        chosen_tag = frame["tag"]
        chosen_payload = frame["payload"]
        chosen_kind = "v1"
        # Solo gana si reduce bytes reales. Los empates conservan el bloque v1.
        if (bool(regional.keyframe) == bool(frame["keyframe"]) and
                len(regional.payload) < len(chosen_payload)):
            if verify_roundtrip:
                decoded = regional_codec_v2.decode_payload(
                    regional.payload, header["rows"], header["cols"], tile_size,
                    frame["keyframe"], previous=previous_matrix,
                    compressed=regional.compressed)
                if not np.array_equal(decoded.matrix, matrix):
                    _fail("codec regional no reconstruye exactamente frame %d" % frame["index"])
            chosen_tag = regional.ascl_tag
            chosen_payload = regional.payload
            chosen_kind = "regional"
        if len(predictor_payload) < len(chosen_payload):
            if verify_roundtrip:
                decoded = decode_predictor_payload(
                    predictor_payload, header["rows"], header["cols"],
                    frame["keyframe"], previous=previous_matrix)
                if not np.array_equal(decoded, matrix):
                    _fail("predictor no reconstruye exactamente frame %d" % frame["index"])
            chosen_tag = predictor_tag
            chosen_payload = predictor_payload
            chosen_kind = "predictor"
        if chosen_kind == "regional":
            regional_frames += 1
            for name, count in regional.command_counts:
                command_counts[name] = command_counts.get(name, 0) + int(count)
        elif chosen_kind == "predictor":
            predictor_frames += 1
            predictor_counts[predictor_id] = predictor_counts.get(predictor_id, 0) + 1
        blocks.append({
            "tag": chosen_tag,
            "pal_count": frame["pal_count"],
            "palette": frame["palette"],
            "payload": chosen_payload,
        })
        source_payload_bytes += len(frame["payload"])
        output_payload_bytes += len(chosen_payload)
        source_tags[frame["tag"]] += 1
        output_tags[chosen_tag] += 1
        previous = frame["cells"]

    result = _build_v2(header, blocks, tile_size, codec_flags)
    if len(result) > len(source):
        _fail("invariante rota: ASCL v2 crecio respecto de v1")
    stats = {
        "input_bytes": len(source),
        "output_bytes": len(result),
        "saved_bytes": len(source) - len(result),
        "saved_percent": ((len(source) - len(result)) * 100.0 / len(source)),
        "source_payload_bytes": source_payload_bytes,
        "output_payload_bytes": output_payload_bytes,
        "regional_frames": regional_frames,
        "predictor_frames": predictor_frames,
        "n_frames": header["n_frames"],
        "source_tags": source_tags,
        "output_tags": output_tags,
        "command_counts": command_counts,
        "predictor_counts": predictor_counts,
        "tile_size": tile_size,
        "codec_flags": codec_flags,
    }
    return result, stats


def iter_decoded_v2(source):
    """Itera frames v2 validados con una sola matriz previa residente.

    Cada elemento contiene ``cells`` HxW, la paleta activa, el tag y si es
    keyframe. Se usa como decoder de referencia y para comprobar el reader JS.
    """
    source = bytes(source)
    header = _header_fields(source, VERSION_V2)
    _validate_crc(source, header)
    expected = header["data_off"] + header["n_frames"] * 4
    previous = None
    active_palette = None
    active_palette_count = 0
    n = header["cols"] * header["rows"]
    for index in range(header["n_frames"]):
        offset = struct.unpack_from("<I", source,
                                    header["data_off"] + index * 4)[0]
        if offset != expected or offset > len(source) - 7:
            _fail("offset v2 no contiguo o frame truncado en %d" % index)
        block_len = struct.unpack_from("<I", source, offset)[0]
        end = offset + 4 + block_len
        if block_len < 3 or end > len(source):
            _fail("block v2 fuera de rango en %d" % index)
        tag = source[offset + 4]
        if tag > TAG_PREDICT_DELTA_ZLIB:
            _fail("tag v2 desconocido: %d" % tag)
        pal_count = struct.unpack_from("<H", source, offset + 5)[0]
        if pal_count > header["pal_size"] or pal_count > 256:
            _fail("pal_count v2 fuera de rango")
        if tag in DELTA_TAGS and pal_count:
            _fail("delta v2 no puede cambiar paleta")
        palette_start = offset + 7
        payload_start = palette_start + pal_count * 3
        if payload_start > end:
            _fail("paleta v2 truncada")
        if pal_count:
            active_palette = bytes(source[palette_start:payload_start])
            active_palette_count = pal_count
        if not active_palette_count:
            _fail("frame v2 sin paleta activa")
        payload = bytes(source[payload_start:end])
        keyframe = tag in KEY_TAGS
        if index == 0 and not keyframe:
            _fail("primer frame v2 no es keyframe")
        if header["flags"] & FLAG_PAL_GLOBAL:
            if index == 0 and not pal_count:
                _fail("paleta global v2 ausente")
            if index > 0 and pal_count:
                _fail("paleta global v2 reemitida")
        elif header["flags"] & FLAG_PAL_PER_SCENE:
            if keyframe and not pal_count:
                _fail("keyframe temporal v2 sin paleta")
        elif not pal_count:
            _fail("paleta per-frame v2 ausente")
        if tag != TAG_RAW and not payload:
            _fail("payload v2 vacio")
        if tag <= TAG_DELTA_MASK:
            flat_previous = None if previous is None else previous.reshape(-1)
            cells = _decode_v1_payload(
                tag, payload, flat_previous, n, active_palette_count)
            cells = cells.reshape(header["rows"], header["cols"])
        elif tag <= TAG_REGIONAL_DELTA_ZLIB:
            decoded = regional_codec_v2.decode_payload(
                payload, header["rows"], header["cols"], header["reserved"] & 255,
                keyframe=keyframe, previous=previous,
                compressed=tag in (TAG_REGIONAL_KEY_ZLIB,
                                   TAG_REGIONAL_DELTA_ZLIB),
                palette_entries=active_palette_count)
            cells = decoded.matrix
        else:
            cells = decode_predictor_payload(
                payload, header["rows"], header["cols"], keyframe,
                previous=previous)
        if int(cells.max()) >= active_palette_count:
            _fail("indice v2 fuera de paleta activa")
        yield {
            "index": index,
            "tag": tag,
            "keyframe": keyframe,
            "pal_count": pal_count,
            "palette": active_palette,
            "cells": cells,
        }
        previous = cells
        expected = end
    if expected != len(source):
        _fail("bytes extra al final del ASCL v2")


def decode_ascl_v2_bytes(source):
    """Materializa el decoder de referencia; conveniente para tests/diagnóstico."""
    header = _header_fields(bytes(source), VERSION_V2)
    frames = list(iter_decoded_v2(source))
    return header, frames


def transcode_path(input_path, output_path, verify_roundtrip=True):
    """Convierte .ascl o .asclv v1 sin sobrescribir la fuente."""
    input_resolved = os.path.normcase(os.path.realpath(os.path.abspath(input_path)))
    output_resolved = os.path.normcase(os.path.realpath(os.path.abspath(output_path)))
    same_path = input_resolved == output_resolved
    if not same_path and os.path.exists(input_path) and os.path.exists(output_path):
        try:
            same_path = os.path.samefile(input_path, output_path)
        except OSError:
            pass
    if same_path:
        _fail("la conversion v2 no puede sobrescribir la fuente")
    with open(input_path, "rb") as fh:
        prefix = fh.read(8)
    is_bundle = prefix == ascl_bundle.MAGIC_V1
    if prefix == ascl_bundle.MAGIC_V2:
        _fail("la entrada ya es ASCLVID2")
    if is_bundle:
        ascl, audio, version = ascl_bundle.read_parts_info(input_path)
        if version != VERSION_V1:
            _fail("el bundle de entrada no es v1")
        converted, stats = transcode_ascl_bytes(ascl, verify_roundtrip=verify_roundtrip)
        total, video_bytes, audio_bytes = ascl_bundle.pack_bytes(converted, audio, output_path)
        stats.update({"bundle": True, "bundle_bytes": total,
                      "video_bytes": video_bytes, "audio_bytes": audio_bytes})
    else:
        with open(input_path, "rb") as fh:
            ascl = fh.read()
        converted, stats = transcode_ascl_bytes(ascl, verify_roundtrip=verify_roundtrip)
        with open(output_path, "wb") as fh:
            fh.write(converted)
        stats.update({"bundle": False, "video_bytes": len(converted), "audio_bytes": 0})
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="transcodifica ASCL/ASCLV v1 a v2 lossless exacto")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--no-verify-roundtrip", action="store_true",
                        help="omite verificar los candidatos v2 (no recomendado)")
    args = parser.parse_args(argv)
    try:
        stats = transcode_path(args.input, args.output,
                               verify_roundtrip=not args.no_verify_roundtrip)
    except (ASCLV2Error, OSError) as exc:
        parser.error(str(exc))
    print("OK %s" % args.output)
    print("  v2 lossless: %d regionales + %d predictores de %d frames; "
          "%d B -> %d B (%.2f%% menos)" %
          (stats["regional_frames"], stats["predictor_frames"],
           stats["n_frames"], stats["input_bytes"], stats["output_bytes"],
           stats["saved_percent"]))
    if stats.get("bundle"):
        print("  ASCLVID2: %d B; audio copiado exacto: %d B" %
              (stats["bundle_bytes"], stats["audio_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
