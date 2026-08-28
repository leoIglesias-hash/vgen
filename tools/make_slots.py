#!/usr/bin/env python3
"""E-07: generador y validador del sidecar ``ASCLSLOT`` (INT-001 §7.1).

Estructura binaria (little-endian, offsets fijos):

    magic        8 B   "ASCLSLOT"
    version      1 B   1
    reserved     1 B   0
    pal_reserved 1 B   10
    n_glyphs     1 B
    glyph_w      2 B
    glyph_h      2 B
    n_slots      2 B
    n_fields     2 B
    reserved_rgb 30 B  los diez RGB de 246..255
    crc32        4 B   zlib.crc32 sobre el resto del archivo (byte 54 en adelante)
    glyph_table  n_glyphs * glyph_w * glyph_h
    slot_table   n_slots * 13 B   (x u16, y u16, start u32, end u32, flags u8;
                                   el slot_id es el indice de la tabla)
    field_table  variable         (field_id u16, n u8, slot_ids u16*n,
                                   min u32, max u32, pad u8)

Las restricciones de §6.3 se validan enteras: una metadata que no cumple se
rechaza completa, sin carga parcial. ``frontend/slots.js`` es el espejo ES5 de
``validate`` y debe rechazar exactamente los mismos archivos.

INT-003 agrega la **version 2** (DISENO-PARCHES-GENERICOS §5): parches de
tamanos heterogeneos, reserva parametrica (``pal_reserved`` 10..64), slots con
dimensiones propias y campos con ``kind`` (0 digitos / 1 eleccion):

    magic         8 B   "ASCLSLOT"
    version       1 B   2
    reserved      1 B   0
    pal_reserved  1 B   N (reserva = 256-N .. 255)
    flags         1 B   0
    n_patches     2 B
    n_slots       2 B
    n_fields      2 B
    crc32         4 B   zlib.crc32 del byte 22 en adelante
    reserved_rgb  3*N B
    patch_dir     n_patches * 4 B  (w u16, h u16)
    patch_data    sum(w*h) B       (indices en [256-N .. 255])
    slot_table    n_slots * 17 B   (x,y,w,h u16; start,end u32; flags u8)
    field_table   variable         (field_id u16, kind u8, count u8,
                                    slot_ids u16*count, min u32, max u32,
                                    pad u8, patch_base u16)

``validate`` despacha por el byte de version y acepta ambas; los presupuestos
v2 son POR FRAME (5% con barrido de eventos start/end) mas un techo de RAM
del 25% sobre el total de areas de slots. Solape espacial entre slots solo se
admite con ventanas temporales disjuntas.
"""
import argparse
import json
import struct
import sys
import zlib

MAGIC = b"ASCLSLOT"
VERSION = 1
PAL_RESERVED = 10
HEADER_SIZE = 54
SLOT_SIZE = 13
MAX_SLOTS = 1024
MAX_GLYPH_AREA = 4096
RESERVED_FIRST = 246

# --- version 2 (INT-003 §5) ---
VERSION_2 = 2
HEADER_SIZE_V2 = 22          # parte fija; reserved_rgb variable a continuacion
SLOT_SIZE_V2 = 17
MAX_PATCHES = 512
MAX_PATCH_AREA = 4096        # D3: se mantiene el limite por parche
MAX_PATCH_DATA = 262144      # 256 KiB de datos de parches en total
MAX_CHOICE_SPAN = 511        # variantes maximas de un campo de eleccion (max-min)
KIND_DIGITS = 0
KIND_CHOICE = 1


def build(meta):
    """Serializa la metadata a bytes ASCLSLOT. No valida §6.3: eso es tarea de
    ``validate`` (y permite construir fixtures negativos para los tests)."""
    glyph_w = int(meta["glyph_w"])
    glyph_h = int(meta["glyph_h"])
    glyph_table = bytes(bytearray(meta["glyph_table"]))
    n_glyphs = len(glyph_table) // max(1, glyph_w * glyph_h)
    if n_glyphs > 255 or n_glyphs * glyph_w * glyph_h != len(glyph_table):
        raise ValueError("glyph_table inconsistente con glyph_w/glyph_h")
    reserved_rgb = bytes(bytearray(meta["reserved_rgb"]))
    if len(reserved_rgb) != 30:
        raise ValueError("reserved_rgb debe tener 30 bytes (10 RGB)")

    body = bytearray(glyph_table)
    for slot in meta["slots"]:
        body += struct.pack("<HHIIB", int(slot["x"]), int(slot["y"]),
                            int(slot["start"]), int(slot["end"]),
                            int(slot.get("flags", 1)))
    for field in meta["fields"]:
        slot_ids = list(field["slot_ids"])
        if not (1 <= len(slot_ids) <= 255):
            raise ValueError("un campo necesita 1..255 slots")
        body += struct.pack("<HB", int(field["field_id"]), len(slot_ids))
        for slot_id in slot_ids:
            body += struct.pack("<H", int(slot_id))
        body += struct.pack("<IIB", int(field["min"]), int(field["max"]),
                            int(field.get("pad", 1)))

    header = bytearray(HEADER_SIZE)
    header[0:8] = MAGIC
    header[8] = VERSION
    header[9] = 0
    header[10] = PAL_RESERVED
    header[11] = n_glyphs
    struct.pack_into("<HHHH", header, 12, glyph_w, glyph_h,
                     len(meta["slots"]), len(meta["fields"]))
    header[20:50] = reserved_rgb
    struct.pack_into("<I", header, 50, zlib.crc32(bytes(body)) & 0xffffffff)
    return bytes(header) + bytes(body)


def rewrite_crc(data):
    """Recalcula el CRC tras mutar el cuerpo (para fixtures de test)."""
    out = bytearray(data)
    struct.pack_into("<I", out, 50, zlib.crc32(bytes(out[HEADER_SIZE:])) & 0xffffffff)
    return bytes(out)


def build_v2(meta):
    """Serializa metadata v2 a bytes ASCLSLOT. No valida §5: eso es tarea de
    ``validate`` (y permite construir fixtures negativos para los tests).

    ``meta``: ``pal_reserved``, ``reserved_rgb`` (3*pal_reserved bytes),
    ``patches`` ([{w, h, data}]), ``slots`` ([{x, y, w, h, start, end,
    flags}]) y ``fields`` ([{field_id, kind, slot_ids, min, max, pad,
    patch_base}]).
    """
    pal_reserved = int(meta["pal_reserved"])
    reserved_rgb = bytes(bytearray(meta["reserved_rgb"]))
    if len(reserved_rgb) != 3 * pal_reserved:
        raise ValueError("reserved_rgb debe tener 3*pal_reserved bytes")

    body = bytearray()
    for patch in meta["patches"]:
        body += struct.pack("<HH", int(patch["w"]), int(patch["h"]))
    for patch in meta["patches"]:
        data = bytes(bytearray(patch["data"]))
        if len(data) != int(patch["w"]) * int(patch["h"]):
            raise ValueError("datos de parche inconsistentes con w*h")
        body += data
    for slot in meta["slots"]:
        body += struct.pack("<HHHHIIB", int(slot["x"]), int(slot["y"]),
                            int(slot["w"]), int(slot["h"]),
                            int(slot["start"]), int(slot["end"]),
                            int(slot.get("flags", 1)))
    for field in meta["fields"]:
        slot_ids = list(field["slot_ids"])
        if not (1 <= len(slot_ids) <= 255):
            raise ValueError("un campo necesita 1..255 slots")
        body += struct.pack("<HBB", int(field["field_id"]),
                            int(field.get("kind", KIND_DIGITS)), len(slot_ids))
        for slot_id in slot_ids:
            body += struct.pack("<H", int(slot_id))
        body += struct.pack("<IIBH", int(field["min"]), int(field["max"]),
                            int(field.get("pad", 0)),
                            int(field.get("patch_base", 0)))

    header = bytearray(HEADER_SIZE_V2)
    header[0:8] = MAGIC
    header[8] = VERSION_2
    header[9] = 0
    header[10] = pal_reserved & 0xff
    header[11] = 0
    struct.pack_into("<HHH", header, 12, len(meta["patches"]),
                     len(meta["slots"]), len(meta["fields"]))
    payload = reserved_rgb + bytes(body)
    struct.pack_into("<I", header, 18, zlib.crc32(payload) & 0xffffffff)
    return bytes(header) + payload


def rewrite_crc_v2(data):
    """Recalcula el CRC v2 tras mutar el cuerpo (para fixtures de test)."""
    out = bytearray(data)
    struct.pack_into("<I", out, 18,
                     zlib.crc32(bytes(out[HEADER_SIZE_V2:])) & 0xffffffff)
    return bytes(out)


def _validate_v2(data, cols, rows, n_frames, expected_reserved_rgb):
    if len(data) < HEADER_SIZE_V2:
        raise ValueError("sidecar truncado")
    if data[9] != 0:
        raise ValueError("byte reservado distinto de 0")
    pal_reserved = data[10]
    if not (10 <= pal_reserved <= 64):
        raise ValueError("pal_reserved fuera de 10..64")
    if data[11] != 0:
        raise ValueError("flags distinto de 0")
    reserved_first = 256 - pal_reserved
    n_patches, n_slots, n_fields = struct.unpack_from("<HHH", data, 12)
    crc_declared = struct.unpack_from("<I", data, 18)[0]
    if zlib.crc32(bytes(data[HEADER_SIZE_V2:])) & 0xffffffff != crc_declared:
        raise ValueError("CRC32 invalido")
    offset = HEADER_SIZE_V2
    if offset + 3 * pal_reserved > len(data):
        raise ValueError("sidecar truncado")
    reserved_rgb = bytes(data[offset:offset + 3 * pal_reserved])
    offset += 3 * pal_reserved
    if expected_reserved_rgb is not None and \
            bytes(bytearray(expected_reserved_rgb)) != reserved_rgb:
        raise ValueError("reserved_rgb no coincide con el bundle")
    if not n_patches:
        raise ValueError("sin parches")
    if n_patches > MAX_PATCHES:
        raise ValueError("n_patches supera 512")
    if not n_slots:
        raise ValueError("sin slots")
    if n_slots > MAX_SLOTS:
        raise ValueError("n_slots supera 1024")

    if offset + n_patches * 4 > len(data):
        raise ValueError("tabla de parches truncada")
    patch_dims = []
    total_patch_data = 0
    for index in range(n_patches):
        width, height = struct.unpack_from("<HH", data, offset)
        offset += 4
        if not width or not height or width * height > MAX_PATCH_AREA:
            raise ValueError("parche %d con dimensiones invalidas" % index)
        patch_dims.append((width, height))
        total_patch_data += width * height
    if total_patch_data > MAX_PATCH_DATA:
        raise ValueError("datos de parches superan 256 KiB")
    if offset + total_patch_data > len(data):
        raise ValueError("tabla de parches truncada")
    patches = []
    for index in range(n_patches):
        width, height = patch_dims[index]
        chunk = bytes(data[offset:offset + width * height])
        offset += width * height
        for value in bytearray(chunk):
            if value < reserved_first:
                raise ValueError("byte de parche fuera de la reserva")
        patches.append({"w": width, "h": height, "data": chunk})

    if offset + n_slots * SLOT_SIZE_V2 > len(data):
        raise ValueError("tabla de slots truncada")
    slots = []
    for index in range(n_slots):
        x, y, width, height, start, end, flags = struct.unpack_from(
            "<HHHHIIB", data, offset)
        offset += SLOT_SIZE_V2
        if not width or not height:
            raise ValueError("slot %d con dimensiones invalidas" % index)
        if x + width > cols or y + height > rows:
            raise ValueError("slot %d fuera de la grilla" % index)
        if end < start:
            raise ValueError("slot %d con end_frame < start_frame" % index)
        if n_frames is not None and end >= n_frames:
            raise ValueError("slot %d activo mas alla del ultimo frame" % index)
        slots.append({"x": x, "y": y, "w": width, "h": height,
                      "start": start, "end": end, "flags": flags})

    # solape espacial permitido SOLO con ventanas temporales disjuntas (D4)
    for a in range(len(slots)):
        for b in range(a + 1, len(slots)):
            sa, sb = slots[a], slots[b]
            if (sa["x"] < sb["x"] + sb["w"] and sb["x"] < sa["x"] + sa["w"] and
                    sa["y"] < sb["y"] + sb["h"] and
                    sb["y"] < sa["y"] + sa["h"] and
                    sa["start"] <= sb["end"] and sb["start"] <= sa["end"]):
                raise ValueError("slots %d y %d se solapan" % (a, b))

    # presupuesto POR FRAME (5%): barrido de eventos start/end+1 (§5.4)
    events = []
    total_area = 0
    for slot in slots:
        area = slot["w"] * slot["h"]
        total_area += area
        events.append((slot["start"], area))
        events.append((slot["end"] + 1, -area))
    events.sort()
    active = 0
    for _frame, delta in events:
        active += delta
        if active * 20 > cols * rows:
            raise ValueError("area activa supera el 5% de la grilla")
    if total_area * 4 > cols * rows:
        raise ValueError("area total de slots supera el 25% de la grilla")

    fields = []
    used_ids = set()
    for index in range(n_fields):
        if offset + 4 > len(data):
            raise ValueError("tabla de campos truncada")
        field_id, kind, count = struct.unpack_from("<HBB", data, offset)
        offset += 4
        if kind not in (KIND_DIGITS, KIND_CHOICE):
            raise ValueError("campo %d con kind invalido" % field_id)
        if not count:
            raise ValueError("campo %d sin slots" % index)
        if offset + count * 2 + 11 > len(data):
            raise ValueError("tabla de campos truncada")
        slot_ids = list(struct.unpack_from("<%dH" % count, data, offset))
        offset += count * 2
        minimum, maximum, pad, patch_base = struct.unpack_from(
            "<IIBH", data, offset)
        offset += 11
        for slot_id in slot_ids:
            if slot_id >= n_slots:
                raise ValueError("campo %d referencia un slot inexistente"
                                 % field_id)
            if slot_id in used_ids:
                raise ValueError("slot %d aparece en dos campos" % slot_id)
            used_ids.add(slot_id)
        if maximum < minimum:
            raise ValueError("campo %d con max < min" % field_id)
        first = slots[slot_ids[0]]
        for slot_id in slot_ids:
            if slots[slot_id]["w"] != first["w"] or \
                    slots[slot_id]["h"] != first["h"]:
                raise ValueError("campo %d con slots de dimensiones distintas"
                                 % field_id)
        if kind == KIND_DIGITS:
            if pad not in (0, 1):
                raise ValueError("campo %d con pad invalido" % field_id)
            if maximum >= 10 ** count:
                raise ValueError(
                    "campo %d no puede representar max con %d digitos"
                    % (field_id, count))
            span = 11  # digitos 0..9 + vacio en patch_base+10
        else:
            if count != 1:
                raise ValueError(
                    "campo %d de eleccion debe tener un solo slot" % field_id)
            if pad != 0:
                raise ValueError(
                    "campo %d de eleccion con pad distinto de 0" % field_id)
            if maximum - minimum > MAX_CHOICE_SPAN:
                raise ValueError(
                    "campo %d de eleccion supera 512 variantes" % field_id)
            span = maximum - minimum + 1
        if patch_base + span > n_patches:
            raise ValueError("campo %d referencia un parche inexistente"
                             % field_id)
        for patch_index in range(patch_base, patch_base + span):
            patch = patches[patch_index]
            if patch["w"] != first["w"] or patch["h"] != first["h"]:
                raise ValueError(
                    "campo %d con parches de dimensiones distintas al slot"
                    % field_id)
        fields.append({"field_id": field_id, "kind": kind,
                       "slot_ids": slot_ids, "min": minimum, "max": maximum,
                       "pad": pad, "patch_base": patch_base})

    if offset != len(data):
        raise ValueError("bytes sobrantes al final del sidecar")

    return {"version": VERSION_2, "pal_reserved": pal_reserved,
            "reserved_rgb": reserved_rgb, "patches": patches,
            "slots": slots, "fields": fields}


def validate(data, cols, rows, n_frames=None, expected_reserved_rgb=None):
    """Valida un sidecar entero (v1 o v2) y devuelve la metadata parseada.

    Cualquier incumplimiento lanza ``ValueError`` sin devolver nada parcial.
    ``expected_reserved_rgb`` (30 bytes en v1, ``3*pal_reserved`` en v2)
    activa la verificacion cruzada contra la paleta del bundle.
    """
    if len(data) < 9:
        raise ValueError("sidecar truncado")
    if bytes(data[0:8]) != MAGIC:
        raise ValueError("magic invalido")
    if data[8] == VERSION_2:
        return _validate_v2(data, cols, rows, n_frames, expected_reserved_rgb)
    if data[8] != VERSION:
        raise ValueError("version no soportada")
    return _validate_v1(data, cols, rows, n_frames, expected_reserved_rgb)


def _validate_v1(data, cols, rows, n_frames, expected_reserved_rgb):
    if len(data) < HEADER_SIZE:
        raise ValueError("sidecar truncado")
    if data[9] != 0:
        raise ValueError("byte reservado distinto de 0")
    if data[10] != PAL_RESERVED:
        raise ValueError("pal_reserved debe ser 10")
    n_glyphs = data[11]
    glyph_w, glyph_h, n_slots, n_fields = struct.unpack_from("<HHHH", data, 12)
    reserved_rgb = bytes(data[20:50])
    crc_declared = struct.unpack_from("<I", data, 50)[0]
    if zlib.crc32(bytes(data[HEADER_SIZE:])) & 0xffffffff != crc_declared:
        raise ValueError("CRC32 invalido")
    if expected_reserved_rgb is not None and \
            bytes(bytearray(expected_reserved_rgb)) != reserved_rgb:
        raise ValueError("reserved_rgb no coincide con el bundle")
    if not n_glyphs or not glyph_w or not glyph_h:
        raise ValueError("glifos vacios")
    if glyph_w * glyph_h > MAX_GLYPH_AREA:
        raise ValueError("glyph_w * glyph_h supera 4096")
    if n_slots > MAX_SLOTS:
        raise ValueError("n_slots supera 1024")

    offset = HEADER_SIZE
    glyph_len = n_glyphs * glyph_w * glyph_h
    if offset + glyph_len > len(data):
        raise ValueError("tabla de glifos truncada")
    glyph_table = bytes(data[offset:offset + glyph_len])
    for value in bytearray(glyph_table):
        if value < RESERVED_FIRST:
            raise ValueError("byte de glifo fuera de 246..255")
    offset += glyph_len

    if offset + n_slots * SLOT_SIZE > len(data):
        raise ValueError("tabla de slots truncada")
    slots = []
    for index in range(n_slots):
        x, y, start, end, flags = struct.unpack_from("<HHIIB", data, offset)
        offset += SLOT_SIZE
        if x + glyph_w > cols or y + glyph_h > rows:
            raise ValueError("slot %d fuera de la grilla" % index)
        if end < start:
            raise ValueError("slot %d con end_frame < start_frame" % index)
        if n_frames is not None and end >= n_frames:
            raise ValueError("slot %d activo mas alla del ultimo frame" % index)
        slots.append({"x": x, "y": y, "start": start, "end": end,
                      "flags": flags})

    for a in range(len(slots)):
        for b in range(a + 1, len(slots)):
            if (slots[a]["x"] < slots[b]["x"] + glyph_w and
                    slots[b]["x"] < slots[a]["x"] + glyph_w and
                    slots[a]["y"] < slots[b]["y"] + glyph_h and
                    slots[b]["y"] < slots[a]["y"] + glyph_h):
                raise ValueError("slots %d y %d se solapan" % (a, b))

    if n_slots * glyph_w * glyph_h * 20 > cols * rows:
        raise ValueError("area activa supera el 5% de la grilla")

    fields = []
    used_ids = set()
    for index in range(n_fields):
        if offset + 3 > len(data):
            raise ValueError("tabla de campos truncada")
        field_id, count = struct.unpack_from("<HB", data, offset)
        offset += 3
        if not count:
            raise ValueError("campo %d sin slots" % index)
        if offset + count * 2 + 9 > len(data):
            raise ValueError("tabla de campos truncada")
        slot_ids = list(struct.unpack_from("<%dH" % count, data, offset))
        offset += count * 2
        minimum, maximum, pad = struct.unpack_from("<IIB", data, offset)
        offset += 9
        for slot_id in slot_ids:
            if slot_id >= n_slots:
                raise ValueError("campo %d referencia un slot inexistente"
                                 % field_id)
            if slot_id in used_ids:
                raise ValueError("slot %d aparece en dos campos" % slot_id)
            used_ids.add(slot_id)
        if maximum < minimum:
            raise ValueError("campo %d con max < min" % field_id)
        if maximum >= 10 ** count:
            raise ValueError("campo %d no puede representar max con %d digitos"
                             % (field_id, count))
        fields.append({"field_id": field_id, "slot_ids": slot_ids,
                       "min": minimum, "max": maximum, "pad": pad})

    if offset != len(data):
        raise ValueError("bytes sobrantes al final del sidecar")

    return {"glyph_w": glyph_w, "glyph_h": glyph_h, "n_glyphs": n_glyphs,
            "glyph_table": glyph_table, "reserved_rgb": reserved_rgb,
            "slots": slots, "fields": fields}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", help="JSON con glyph_w/h, glyph_table (ruta "
                        ".bin en 'glyphs'), reserved_rgb, slots y fields")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cols", type=int, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args(argv)

    with open(args.spec, "r") as stream:
        spec = json.load(stream)
    if "glyphs" in spec:
        with open(spec.pop("glyphs"), "rb") as stream:
            spec["glyph_table"] = stream.read()
    data = build(spec)
    validate(data, args.cols, args.rows, args.frames)
    with open(args.out, "wb") as stream:
        stream.write(data)
    print("OK %s: %d bytes, %d slots, %d campos" %
          (args.out, len(data), len(spec["slots"]), len(spec["fields"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
