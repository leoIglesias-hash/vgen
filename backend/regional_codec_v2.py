#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codec regional lossless de ASCL v2 para matrices de indices de un byte.

Expone dos niveles:

``encode_payload`` / ``decode_payload``
    Stream regional integrado en los tags 4..7 de un bloque ASCL v2. Las
    dimensiones, el tamano de tile y si es key/delta pertenecen al envelope ASCL.

``encode_frame`` / ``decode_frame``
    Envelope autocontenido solo de laboratorio, util para fuzzing y pruebas.

La eleccion de comando es puramente lossless y determinista: se materializa cada
candidato valido y se compara su longitud binaria real. No intervienen metricas
visuales, IA ni umbrales de calidad.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import zlib

import numpy as np

from deflate_util import best_deflate


OP_SKIP_RUN = 0x00
OP_SOLID = 0x01
OP_SPARSE = 0x02
OP_MASK = 0x03
OP_PACK1 = 0x04
OP_PACK2 = 0x05
OP_PAL4 = 0x06
OP_PAL8 = 0x07

OPCODE_NAMES = {
    OP_SKIP_RUN: "SKIP_RUN",
    OP_SOLID: "SOLID",
    OP_SPARSE: "SPARSE",
    OP_MASK: "MASK",
    OP_PACK1: "PACK1",
    OP_PACK2: "PACK2",
    OP_PAL4: "PAL4",
    OP_PAL8: "PAL8",
}

# Tags reservados por el prototipo ASCL v2. El modulo no escribe el envelope ASCL.
TAG_REGIONAL_KEY_RAW = 4
TAG_REGIONAL_KEY_ZLIB = 5
TAG_REGIONAL_DELTA_RAW = 6
TAG_REGIONAL_DELTA_ZLIB = 7

PACKET_MAGIC = b"RGV2"
PACKET_VERSION = 1
PACKET_FLAG_KEYFRAME = 0x01
PACKET_FLAG_ZLIB = 0x02
PACKET_HEADER = struct.Struct("<4sBBHIIIII")
MAX_UINT32 = 0xFFFFFFFF
DEFAULT_MAX_CELLS = 100_000_000

# Orden estable usado solamente para desempatar candidatos de igual longitud.
_CANDIDATE_PRIORITY = {
    OP_SOLID: 0,
    OP_SPARSE: 1,
    OP_MASK: 2,
    OP_PACK1: 3,
    OP_PACK2: 4,
    OP_PAL4: 5,
    OP_PAL8: 6,
}


class RegionalCodecError(ValueError):
    """Stream regional invalido, truncado o incompatible con su estado previo."""


@dataclass(frozen=True)
class RegionalEncoding:
    """Resultado reusable por un transcodificador ASCL v2."""

    raw_payload: bytes
    zlib_payload: bytes
    keyframe: bool
    rows: int
    cols: int
    tile_size: int
    command_counts: Tuple[Tuple[str, int], ...]
    dirty_tiles: Tuple[int, ...]

    @property
    def compressed(self) -> bool:
        """ZLIB se usa solo si es estrictamente menor; un empate conserva RAW."""
        return len(self.zlib_payload) < len(self.raw_payload)

    @property
    def payload(self) -> bytes:
        return self.zlib_payload if self.compressed else self.raw_payload

    @property
    def ascl_tag(self) -> int:
        if self.keyframe:
            return TAG_REGIONAL_KEY_ZLIB if self.compressed else TAG_REGIONAL_KEY_RAW
        return TAG_REGIONAL_DELTA_ZLIB if self.compressed else TAG_REGIONAL_DELTA_RAW

    @property
    def repeat(self) -> bool:
        return (not self.keyframe and not self.dirty_tiles and
                self.command_counts == (("REPEAT", 1),))


@dataclass(frozen=True)
class DecodedRegionalFrame:
    matrix: np.ndarray
    dirty_tiles: Tuple[int, ...]
    command_counts: Tuple[Tuple[str, int], ...]
    keyframe: bool

    @property
    def repeat(self) -> bool:
        return (not self.keyframe and not self.dirty_tiles and
                self.command_counts == (("REPEAT", 1),))


def _uvarint(value: int) -> bytes:
    if not isinstance(value, (int, np.integer)) or value < 0 or value > MAX_UINT32:
        raise ValueError("uvarint fuera de uint32")
    out = bytearray()
    value = int(value)
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _read_uvarint(data: bytes, pos: int) -> Tuple[int, int]:
    start = pos
    value = 0
    for shift in range(0, 35, 7):
        if pos >= len(data):
            raise RegionalCodecError("uvarint truncado")
        byte = data[pos]
        pos += 1
        if shift == 28 and byte > 0x0F:
            raise RegionalCodecError("uvarint excede uint32")
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            if data[start:pos] != _uvarint(value):
                raise RegionalCodecError("uvarint no canonico")
            return value, pos
    raise RegionalCodecError("uvarint excede cinco bytes")


def _matrix(value: np.ndarray, label: str) -> np.ndarray:
    if not isinstance(value, np.ndarray):
        raise TypeError("%s debe ser numpy.ndarray" % label)
    if value.ndim != 2:
        raise ValueError("%s debe tener forma HxW" % label)
    if value.dtype != np.uint8:
        raise TypeError("%s debe usar dtype uint8" % label)
    if value.shape[0] <= 0 or value.shape[1] <= 0:
        raise ValueError("%s no puede estar vacia" % label)
    return value


def _geometry(rows: int, cols: int, tile_size: int,
              max_cells: int = DEFAULT_MAX_CELLS) -> Tuple[int, int, int]:
    for value, label in ((rows, "rows"), (cols, "cols"),
                         (tile_size, "tile_size")):
        if not isinstance(value, (int, np.integer)):
            raise TypeError("%s debe ser entero" % label)
    rows, cols, tile_size = int(rows), int(cols), int(tile_size)
    if rows <= 0 or cols <= 0:
        raise RegionalCodecError("dimensiones invalidas")
    if tile_size <= 0 or tile_size > 256:
        raise RegionalCodecError("tile_size debe estar entre 1 y 256")
    cells = rows * cols
    if cells > int(max_cells):
        raise RegionalCodecError("matriz excede max_cells")
    tile_cols = (cols + tile_size - 1) // tile_size
    tile_rows = (rows + tile_size - 1) // tile_size
    return tile_rows, tile_cols, tile_rows * tile_cols


def _tile_bounds(tile_id: int, rows: int, cols: int, tile_size: int,
                 tile_cols: int) -> Tuple[int, int, int, int]:
    ty, tx = divmod(tile_id, tile_cols)
    y0, x0 = ty * tile_size, tx * tile_size
    return y0, min(y0 + tile_size, rows), x0, min(x0 + tile_size, cols)


def _pack_indices(flat: np.ndarray, palette: Sequence[int], bits: int) -> bytes:
    lookup = {int(value): index for index, value in enumerate(palette)}
    per_byte = 8 // bits
    out = bytearray((flat.size + per_byte - 1) // per_byte)
    for i, value in enumerate(flat):
        out[i // per_byte] |= lookup[int(value)] << ((i % per_byte) * bits)
    return bytes(out)


def _dense_candidates(flat: np.ndarray) -> List[Tuple[int, bytes]]:
    values = [int(value) for value in np.unique(flat)]
    candidates: List[Tuple[int, bytes]] = []
    if len(values) == 1:
        candidates.append((OP_SOLID, bytes((OP_SOLID, values[0]))))
    elif len(values) == 2:
        candidates.append((
            OP_PACK1,
            bytes((OP_PACK1, values[0], values[1])) +
            _pack_indices(flat, values, 1),
        ))
    elif len(values) <= 4:
        candidates.append((
            OP_PACK2,
            bytes((OP_PACK2, len(values))) + bytes(values) +
            _pack_indices(flat, values, 2),
        ))
    elif len(values) <= 16:
        candidates.append((
            OP_PAL4,
            bytes((OP_PAL4, len(values))) + bytes(values) +
            _pack_indices(flat, values, 4),
        ))
    candidates.append((OP_PAL8, bytes((OP_PAL8,)) + flat.tobytes()))
    return candidates


def _delta_candidates(flat: np.ndarray, old: np.ndarray) -> List[Tuple[int, bytes]]:
    candidates = _dense_candidates(flat)
    changed = np.flatnonzero(flat != old)
    if not changed.size:
        return candidates

    sparse = bytearray((OP_SPARSE,))
    sparse.extend(_uvarint(int(changed.size)))
    for offset in changed:
        sparse.extend(_uvarint(int(offset)))
        sparse.append(int(flat[offset]))
    candidates.append((OP_SPARSE, bytes(sparse)))

    mask_len = (flat.size + 7) // 8
    mask = bytearray(mask_len)
    for offset in changed:
        mask[int(offset) >> 3] |= 1 << (int(offset) & 7)
    masked = bytearray((OP_MASK,))
    masked.extend(mask)
    masked.extend(flat[changed].tobytes())
    candidates.append((OP_MASK, bytes(masked)))
    return candidates


def _count_tuple(counts: Dict[str, int], repeat: bool = False
                 ) -> Tuple[Tuple[str, int], ...]:
    if repeat:
        return (("REPEAT", 1),)
    order = ["SKIP_RUN", "SOLID", "SPARSE", "MASK",
             "PACK1", "PACK2", "PAL4", "PAL8"]
    return tuple((name, counts[name]) for name in order if counts.get(name))


def encode_payload(current: np.ndarray, previous: Optional[np.ndarray] = None,
                   tile_size: int = 16, zlib_level: int = 9) -> RegionalEncoding:
    """Codifica una transicion exacta y devuelve RAW y ZLIB para comparar afuera.

    ``previous is None`` genera keyframe. En delta, ambas matrices deben tener la
    misma forma. Por tile se elige el comando de menor longitud materializada;
    los empates usan ``_CANDIDATE_PRIORITY`` y por tanto son reproducibles.
    """
    current = _matrix(current, "current")
    rows, cols = current.shape
    tile_rows, tile_cols, tile_count = _geometry(rows, cols, tile_size)
    keyframe = previous is None
    if previous is not None:
        previous = _matrix(previous, "previous")
        if previous.shape != current.shape:
            raise ValueError("previous y current deben tener igual forma")
    if not isinstance(zlib_level, int) or not 0 <= zlib_level <= 9:
        raise ValueError("zlib_level debe estar entre 0 y 9")

    commands = bytearray()
    counts: Dict[str, int] = {}
    dirty: List[int] = []
    skip_run = 0

    def flush_skip() -> None:
        nonlocal skip_run
        if skip_run:
            commands.append(OP_SKIP_RUN)
            commands.extend(_uvarint(skip_run))
            counts["SKIP_RUN"] = counts.get("SKIP_RUN", 0) + 1
            skip_run = 0

    for tile_id in range(tile_count):
        y0, y1, x0, x1 = _tile_bounds(
            tile_id, rows, cols, tile_size, tile_cols)
        flat = np.asarray(current[y0:y1, x0:x1]).reshape(-1)
        old = None
        if previous is not None:
            old = np.asarray(previous[y0:y1, x0:x1]).reshape(-1)
            if np.array_equal(flat, old):
                skip_run += 1
                continue
        flush_skip()
        candidates = (_dense_candidates(flat) if keyframe else
                      _delta_candidates(flat, old))
        opcode, command = min(
            candidates,
            key=lambda item: (len(item[1]), _CANDIDATE_PRIORITY[item[0]]),
        )
        commands.extend(command)
        name = OPCODE_NAMES[opcode]
        counts[name] = counts.get(name, 0) + 1
        dirty.append(tile_id)
    flush_skip()

    raw = bytes(commands)
    # Una matriz no vacia siempre cubre al menos un tile/comando.
    if not raw:
        raise AssertionError("stream regional vacio")
    compressed = best_deflate(raw, zlib_level)
    repeat = (not keyframe and not dirty and
              raw == bytes((OP_SKIP_RUN,)) + _uvarint(tile_count))
    return RegionalEncoding(
        raw_payload=raw,
        zlib_payload=compressed,
        keyframe=keyframe,
        rows=rows,
        cols=cols,
        tile_size=int(tile_size),
        command_counts=_count_tuple(counts, repeat=repeat),
        dirty_tiles=tuple(dirty),
    )


def _inflate_exact(payload: bytes, expected_length: Optional[int] = None,
                   max_length: Optional[int] = None) -> bytes:
    if not isinstance(payload, bytes):
        raise TypeError("payload debe ser bytes")
    if expected_length is not None:
        limit = expected_length
    elif max_length is not None:
        limit = max_length
    else:
        raise ValueError("se requiere limite de inflate")
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(payload, int(limit) + 1)
        if len(raw) > limit or decoder.unconsumed_tail:
            raise RegionalCodecError("salida ZLIB excede el limite")
        raw += decoder.flush()
    except zlib.error as exc:
        raise RegionalCodecError("payload ZLIB invalido") from exc
    if len(raw) > limit:
        raise RegionalCodecError("salida ZLIB excede el limite")
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise RegionalCodecError("stream ZLIB truncado o con datos extra")
    if expected_length is not None and len(raw) != expected_length:
        raise RegionalCodecError("longitud RAW declarada no coincide")
    return raw


def _raw_limit(rows: int, cols: int, tile_count: int) -> int:
    # Acepta incluso SPARSE con offsets uint32; sigue siendo un limite acotado.
    return rows * cols * 7 + tile_count * 8


def _take(data: bytes, pos: int, length: int, label: str) -> Tuple[int, int]:
    end = pos + length
    if length < 0 or end > len(data):
        raise RegionalCodecError("%s truncado" % label)
    return pos, end


def _strict_palette(data: bytes, start: int, count: int,
                    palette_entries: Optional[int] = None) -> None:
    if (palette_entries is not None and
            any(data[start + i] >= palette_entries for i in range(count))):
        raise RegionalCodecError("indice fuera de paleta activa")
    for i in range(1, count):
        if data[start + i - 1] >= data[start + i]:
            raise RegionalCodecError("paleta local no canonica")


def _validate_packed(data: bytes, start: int, cell_count: int,
                     bits: int, palette_count: int) -> None:
    per_byte = 8 // bits
    mask = (1 << bits) - 1
    packed_len = (cell_count + per_byte - 1) // per_byte
    for cell in range(cell_count):
        index = (data[start + cell // per_byte] >>
                 ((cell % per_byte) * bits)) & mask
        if index >= palette_count:
            raise RegionalCodecError("indice fuera de paleta local")
    used = cell_count % per_byte
    if used:
        used_bits = used * bits
        if data[start + packed_len - 1] >> used_bits:
            raise RegionalCodecError("padding packed no nulo")


def _parse_payload(raw: bytes, rows: int, cols: int, tile_size: int,
                   keyframe: bool, previous: Optional[np.ndarray],
                   palette_entries: Optional[int] = None
                   ) -> Tuple[List[Tuple], Tuple[int, ...], Tuple[Tuple[str, int], ...]]:
    _, tile_cols, tile_count = _geometry(rows, cols, tile_size)
    if not raw:
        raise RegionalCodecError("stream regional vacio")
    operations: List[Tuple] = []
    dirty: List[int] = []
    counts: Dict[str, int] = {}
    cursor = 0
    pos = 0

    while cursor < tile_count:
        if pos >= len(raw):
            raise RegionalCodecError("stream no cubre todos los tiles")
        opcode = raw[pos]
        pos += 1
        if opcode not in OPCODE_NAMES:
            raise RegionalCodecError("opcode regional desconocido")
        name = OPCODE_NAMES[opcode]
        counts[name] = counts.get(name, 0) + 1

        if opcode == OP_SKIP_RUN:
            if keyframe:
                raise RegionalCodecError("SKIP_RUN no es valido en keyframe")
            run, pos = _read_uvarint(raw, pos)
            if run < 1 or run > tile_count - cursor:
                raise RegionalCodecError("SKIP_RUN fuera de rango")
            operations.append((opcode, cursor, run))
            cursor += run
            continue

        tile_id = cursor
        y0, y1, x0, x1 = _tile_bounds(
            tile_id, rows, cols, tile_size, tile_cols)
        tile_w = x1 - x0
        cell_count = tile_w * (y1 - y0)
        dirty.append(tile_id)

        if opcode == OP_SOLID:
            start, pos = _take(raw, pos, 1, "SOLID")
            if palette_entries is not None and raw[start] >= palette_entries:
                raise RegionalCodecError("indice fuera de paleta activa")
            operations.append((opcode, tile_id, raw[start]))

        elif opcode == OP_SPARSE:
            if keyframe or previous is None:
                raise RegionalCodecError("SPARSE requiere delta previo")
            count, pos = _read_uvarint(raw, pos)
            if count < 1 or count > cell_count:
                raise RegionalCodecError("cantidad SPARSE invalida")
            pairs = []
            prior_offset = -1
            for _ in range(count):
                offset, pos = _read_uvarint(raw, pos)
                if offset >= cell_count or offset <= prior_offset:
                    raise RegionalCodecError("offset SPARSE invalido o no canonico")
                start, pos = _take(raw, pos, 1, "valor SPARSE")
                value = raw[start]
                if palette_entries is not None and value >= palette_entries:
                    raise RegionalCodecError("indice fuera de paleta activa")
                py, px = divmod(offset, tile_w)
                if int(previous[y0 + py, x0 + px]) == value:
                    raise RegionalCodecError("SPARSE contiene cambio nulo")
                pairs.append((offset, value))
                prior_offset = offset
            operations.append((opcode, tile_id, tuple(pairs)))

        elif opcode == OP_MASK:
            if keyframe or previous is None:
                raise RegionalCodecError("MASK requiere delta previo")
            mask_len = (cell_count + 7) // 8
            mask_start, pos = _take(raw, pos, mask_len, "mascara MASK")
            if cell_count & 7 and raw[pos - 1] >> (cell_count & 7):
                raise RegionalCodecError("padding MASK no nulo")
            offsets = [i for i in range(cell_count)
                       if raw[mask_start + (i >> 3)] & (1 << (i & 7))]
            if not offsets:
                raise RegionalCodecError("MASK vacia")
            values_start, pos = _take(raw, pos, len(offsets), "valores MASK")
            for i, offset in enumerate(offsets):
                if (palette_entries is not None and
                        raw[values_start + i] >= palette_entries):
                    raise RegionalCodecError("indice fuera de paleta activa")
                py, px = divmod(offset, tile_w)
                if int(previous[y0 + py, x0 + px]) == raw[values_start + i]:
                    raise RegionalCodecError("MASK contiene cambio nulo")
            operations.append((opcode, tile_id, tuple(offsets),
                               values_start, len(offsets)))

        elif opcode == OP_PACK1:
            palette_start, pos = _take(raw, pos, 2, "paleta PACK1")
            _strict_palette(raw, palette_start, 2, palette_entries)
            packed_len = (cell_count + 7) // 8
            packed_start, pos = _take(raw, pos, packed_len, "indices PACK1")
            _validate_packed(raw, packed_start, cell_count, 1, 2)
            operations.append((opcode, tile_id, palette_start, 2,
                               packed_start, 1))

        elif opcode in (OP_PACK2, OP_PAL4):
            count_start, pos = _take(raw, pos, 1, "cantidad de paleta")
            palette_count = raw[count_start]
            low, high, bits = ((3, 4, 2) if opcode == OP_PACK2 else (5, 16, 4))
            if not low <= palette_count <= high:
                raise RegionalCodecError("cantidad de paleta local invalida")
            palette_start, pos = _take(raw, pos, palette_count, "paleta local")
            _strict_palette(raw, palette_start, palette_count, palette_entries)
            per_byte = 8 // bits
            packed_len = (cell_count + per_byte - 1) // per_byte
            packed_start, pos = _take(raw, pos, packed_len, "indices packed")
            _validate_packed(raw, packed_start, cell_count, bits, palette_count)
            operations.append((opcode, tile_id, palette_start, palette_count,
                               packed_start, bits))

        elif opcode == OP_PAL8:
            values_start, pos = _take(raw, pos, cell_count, "PAL8")
            if (palette_entries is not None and
                    any(raw[values_start + i] >= palette_entries
                        for i in range(cell_count))):
                raise RegionalCodecError("indice fuera de paleta activa")
            operations.append((opcode, tile_id, values_start, cell_count))

        cursor += 1

    if cursor != tile_count or pos != len(raw):
        raise RegionalCodecError("cobertura de tiles o trailing bytes invalidos")
    repeat = (not keyframe and len(operations) == 1 and
              operations[0][0] == OP_SKIP_RUN and operations[0][2] == tile_count)
    return operations, tuple(dirty), _count_tuple(counts, repeat=repeat)


def _unpack_values(raw: bytes, palette_start: int, palette_count: int,
                   packed_start: int, bits: int, cell_count: int) -> np.ndarray:
    per_byte = 8 // bits
    mask = (1 << bits) - 1
    palette = raw[palette_start:palette_start + palette_count]
    values = np.empty(cell_count, dtype=np.uint8)
    for i in range(cell_count):
        index = (raw[packed_start + i // per_byte] >>
                 ((i % per_byte) * bits)) & mask
        values[i] = palette[index]
    return values


def decode_payload(payload: bytes, rows: int, cols: int, tile_size: int,
                   keyframe: bool, previous: Optional[np.ndarray] = None,
                   compressed: bool = False,
                   max_cells: int = DEFAULT_MAX_CELLS,
                   palette_entries: Optional[int] = None) -> DecodedRegionalFrame:
    """Valida el payload completo antes de crear/mutar la matriz de salida."""
    tile_rows, tile_cols, tile_count = _geometry(
        rows, cols, tile_size, max_cells=max_cells)
    del tile_rows
    if not isinstance(payload, bytes):
        raise TypeError("payload debe ser bytes")
    if not isinstance(keyframe, (bool, np.bool_)):
        raise TypeError("keyframe debe ser bool")
    keyframe = bool(keyframe)
    if palette_entries is not None:
        if (isinstance(palette_entries, bool) or
                not isinstance(palette_entries, (int, np.integer)) or
                not 1 <= int(palette_entries) <= 256):
            raise RegionalCodecError("cantidad de paleta activa invalida")
        palette_entries = int(palette_entries)
    if keyframe:
        if previous is not None:
            previous = _matrix(previous, "previous")
            if previous.shape != (rows, cols):
                raise ValueError("previous no coincide con dimensiones")
    else:
        if previous is None:
            raise RegionalCodecError("delta regional requiere previous")
        previous = _matrix(previous, "previous")
        if previous.shape != (rows, cols):
            raise ValueError("previous no coincide con dimensiones")
    raw = (_inflate_exact(payload, max_length=_raw_limit(rows, cols, tile_count))
           if compressed else payload)
    if len(raw) > _raw_limit(rows, cols, tile_count):
        raise RegionalCodecError("payload RAW excede el limite")

    # Fase 1: parseo y validacion completa. No se toca ``previous`` ni una salida.
    operations, dirty, counts = _parse_payload(
        raw, rows, cols, tile_size, keyframe, previous, palette_entries)

    # Fase 2: una sola matriz logica mutable.
    matrix = (np.empty((rows, cols), dtype=np.uint8) if keyframe
              else previous.copy())
    for operation in operations:
        opcode, tile_id = operation[0], operation[1]
        if opcode == OP_SKIP_RUN:
            continue
        y0, y1, x0, x1 = _tile_bounds(
            tile_id, rows, cols, tile_size, tile_cols)
        tile_w = x1 - x0
        cell_count = tile_w * (y1 - y0)
        if opcode == OP_SOLID:
            matrix[y0:y1, x0:x1] = operation[2]
        elif opcode == OP_SPARSE:
            for offset, value in operation[2]:
                py, px = divmod(offset, tile_w)
                matrix[y0 + py, x0 + px] = value
        elif opcode == OP_MASK:
            offsets, values_start = operation[2], operation[3]
            for i, offset in enumerate(offsets):
                py, px = divmod(offset, tile_w)
                matrix[y0 + py, x0 + px] = raw[values_start + i]
        elif opcode in (OP_PACK1, OP_PACK2, OP_PAL4):
            values = _unpack_values(
                raw, operation[2], operation[3], operation[4], operation[5],
                cell_count)
            matrix[y0:y1, x0:x1] = values.reshape(y1 - y0, tile_w)
        elif opcode == OP_PAL8:
            start = operation[2]
            values = np.frombuffer(raw, dtype=np.uint8,
                                   count=cell_count, offset=start)
            matrix[y0:y1, x0:x1] = values.reshape(y1 - y0, tile_w)
    return DecodedRegionalFrame(matrix, dirty, counts, keyframe)


def encode_frame(current: np.ndarray, previous: Optional[np.ndarray] = None,
                 tile_size: int = 16, zlib_level: int = 9) -> bytes:
    """Crea un paquete autocontenido de laboratorio con CRC del stream RAW."""
    encoded = encode_payload(current, previous, tile_size, zlib_level)
    flags = PACKET_FLAG_KEYFRAME
    if not encoded.keyframe:
        flags = 0
    if encoded.compressed:
        flags |= PACKET_FLAG_ZLIB
    payload = encoded.payload
    header = PACKET_HEADER.pack(
        PACKET_MAGIC, PACKET_VERSION, flags, encoded.tile_size,
        encoded.rows, encoded.cols, len(encoded.raw_payload), len(payload),
        zlib.crc32(encoded.raw_payload) & MAX_UINT32,
    )
    return header + payload


def decode_frame(packet: bytes, previous: Optional[np.ndarray] = None,
                 max_cells: int = DEFAULT_MAX_CELLS) -> DecodedRegionalFrame:
    """Decodifica el envelope de laboratorio; no es el envelope publico ASCL."""
    if not isinstance(packet, bytes):
        raise TypeError("packet debe ser bytes")
    if len(packet) < PACKET_HEADER.size:
        raise RegionalCodecError("header regional truncado")
    (magic, version, flags, tile_size, rows, cols, raw_length,
     payload_length, expected_crc) = PACKET_HEADER.unpack_from(packet)
    if magic != PACKET_MAGIC or version != PACKET_VERSION:
        raise RegionalCodecError("magic o version regional invalida")
    if flags & ~(PACKET_FLAG_KEYFRAME | PACKET_FLAG_ZLIB):
        raise RegionalCodecError("flags regionales desconocidos")
    _, _, tile_count = _geometry(rows, cols, tile_size, max_cells=max_cells)
    if raw_length <= 0 or raw_length > _raw_limit(rows, cols, tile_count):
        raise RegionalCodecError("raw_length regional invalido")
    if payload_length != len(packet) - PACKET_HEADER.size:
        raise RegionalCodecError("payload_length regional invalido")
    payload = packet[PACKET_HEADER.size:]
    compressed = bool(flags & PACKET_FLAG_ZLIB)
    raw = (_inflate_exact(payload, expected_length=raw_length)
           if compressed else payload)
    if len(raw) != raw_length:
        raise RegionalCodecError("raw_length regional no coincide")
    if (zlib.crc32(raw) & MAX_UINT32) != expected_crc:
        raise RegionalCodecError("CRC regional no coincide")
    return decode_payload(raw, rows, cols, tile_size,
                          bool(flags & PACKET_FLAG_KEYFRAME), previous,
                          compressed=False, max_cells=max_cells)


__all__ = [
    "DecodedRegionalFrame", "RegionalCodecError", "RegionalEncoding",
    "OP_SKIP_RUN", "OP_SOLID", "OP_SPARSE", "OP_MASK", "OP_PACK1",
    "OP_PACK2", "OP_PAL4", "OP_PAL8", "OPCODE_NAMES",
    "TAG_REGIONAL_KEY_RAW", "TAG_REGIONAL_KEY_ZLIB",
    "TAG_REGIONAL_DELTA_RAW", "TAG_REGIONAL_DELTA_ZLIB",
    "encode_payload", "decode_payload", "encode_frame", "decode_frame",
]
