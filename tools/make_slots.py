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


def validate(data, cols, rows, n_frames=None, expected_reserved_rgb=None):
    """Valida un sidecar entero contra §6.3 y devuelve la metadata parseada.

    Cualquier incumplimiento lanza ``ValueError`` sin devolver nada parcial.
    ``expected_reserved_rgb`` (30 bytes) activa la verificacion cruzada contra
    la paleta del bundle.
    """
    if len(data) < HEADER_SIZE:
        raise ValueError("sidecar truncado")
    if bytes(data[0:8]) != MAGIC:
        raise ValueError("magic invalido")
    if data[8] != VERSION:
        raise ValueError("version no soportada")
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
