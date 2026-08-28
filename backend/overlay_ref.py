#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7-4 / INT-003-D: referencia Python del runtime del overlay.

Espejo semantico de ``frontend/overlay.js``: dada la metadata ASCLSLOT
validada (``tools/make_slots.validate``, v1 o v2) y la misma cadena de datos,
produce la matriz de celdas compuesta **byte-identica** a la que el reader
JavaScript presenta tras ``beforeSeek()/seek()/afterSeek()``.

La referencia no necesita la disciplina de restauracion del runtime (opera
sobre una copia del frame decodificado, nunca muta el estado del decoder);
esa disciplina es justamente lo que garantiza que el runtime JS equivalga a
esta composicion pura: ``compose(decode(f)) == cells_js(f)``.

Las mutadoras replican el contrato del runtime: validan todo antes de aplicar
nada y devuelven ``False`` sin tocar el estado ante cualquier dato invalido
(INV-7). ``pad=0`` deja los ceros a la izquierda como parche vacio; un campo
de eleccion sin presencia deja su slot en ``NONE`` (no se pinta).
"""
import numpy as np

EMPTY_GLYPH = 10
TRANSPARENT_INDEX = 255
NONE = 65535
KIND_DIGITS = 0
KIND_CHOICE = 1


def _wire_width(maximum):
    width, threshold = 1, 10
    while maximum >= threshold and width < 10:
        width += 1
        threshold *= 10
    return width


class OverlayRef(object):
    def __init__(self, meta, cols, rows):
        self.cols = int(cols)
        self.rows = int(rows)
        if meta.get("version") == 2:
            self._init_v2(meta)
        else:
            self._init_v1(meta)
        for slot in self.slots:
            if slot["x"] + slot["w"] > self.cols or \
                    slot["y"] + slot["h"] > self.rows:
                raise ValueError("slot fuera de la grilla")
        self.active = True
        self._field_by_id = {}
        self.digit_count = 0
        for field in self.fields:
            self._field_by_id[field["field_id"]] = field
            self.digit_count += field["wire"]
        self.values = list(self._defaults)

    def _init_v1(self, meta):
        glyph_w = int(meta["glyph_w"])
        glyph_h = int(meta["glyph_h"])
        n_glyphs = int(meta["n_glyphs"])
        if n_glyphs < EMPTY_GLYPH + 1:
            raise ValueError("la tabla necesita el glifo vacio (11 glifos)")
        table = bytearray(meta["glyph_table"])
        area = glyph_w * glyph_h
        self.patches = [{"w": glyph_w, "h": glyph_h,
                         "data": bytes(table[g * area:(g + 1) * area])}
                        for g in range(n_glyphs)]
        self.slots = [dict(slot, w=glyph_w, h=glyph_h)
                      for slot in meta["slots"]]
        self.fields = [dict(field, kind=KIND_DIGITS, patch_base=0,
                            wire=len(field["slot_ids"]))
                       for field in meta["fields"]]
        # v1: TODOS los slots arrancan en el glifo vacio (comportamiento F7)
        self._defaults = [EMPTY_GLYPH] * len(self.slots)

    def _init_v2(self, meta):
        self.patches = list(meta["patches"])
        self.slots = [dict(slot) for slot in meta["slots"]]
        self.fields = []
        self._defaults = [NONE] * len(self.slots)
        for field in meta["fields"]:
            wire = (1 + _wire_width(field["max"])
                    if field["kind"] == KIND_CHOICE
                    else len(field["slot_ids"]))
            self.fields.append(dict(field, wire=wire))
            if field["kind"] == KIND_DIGITS:
                for slot_id in field["slot_ids"]:
                    self._defaults[slot_id] = field["patch_base"] + EMPTY_GLYPH

    # -- mutadoras: mismo contrato que overlay.js -------------------------
    def _apply_field(self, field, value):
        ids = field["slot_ids"]
        if field["kind"] == KIND_CHOICE:
            if value < 0:
                self.values[ids[0]] = NONE
            else:
                self.values[ids[0]] = field["patch_base"] + \
                    (value - field["min"])
            return
        rest = value
        wrote = False
        for k in range(len(ids) - 1, -1, -1):
            if not field["pad"] and wrote and rest == 0:
                self.values[ids[k]] = field["patch_base"] + EMPTY_GLYPH
            else:
                self.values[ids[k]] = field["patch_base"] + rest % 10
                rest //= 10
                wrote = True

    def set_field(self, field_id, value):
        field = self._field_by_id.get(field_id)
        if field is None:
            return False
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        if value < field["min"] or value > field["max"]:
            return False
        self._apply_field(field, value)
        self.active = True
        return True

    def set_values(self, digits):
        if not isinstance(digits, str) or len(digits) != self.digit_count:
            return False
        if not all("0" <= c <= "9" for c in digits):
            return False
        loads = []
        position = 0
        for field in self.fields:
            wire = field["wire"]
            chunk = digits[position:position + wire]
            if field["kind"] == KIND_CHOICE:
                presence = int(chunk[0])
                if presence > 1:
                    return False
                value = int(chunk[1:])
                if presence == 0:
                    if value != 0:  # canonico: sin presencia -> ceros
                        return False
                    loads.append(-1)
                else:
                    if value < field["min"] or value > field["max"]:
                        return False
                    loads.append(value)
            else:
                value = int(chunk)
                if value < field["min"] or value > field["max"]:
                    return False
                loads.append(value)
            position += wire
        for field, value in zip(self.fields, loads):
            self._apply_field(field, value)
        self.active = True
        return True

    def clear_field(self, field_id):
        field = self._field_by_id.get(field_id)
        if field is None:
            return False
        for slot_id in field["slot_ids"]:
            self.values[slot_id] = self._defaults[slot_id]
        return True

    def clear(self):
        self.values = list(self._defaults)
        self.active = False

    # -- composicion pura -------------------------------------------------
    def compose(self, cells, frame_index):
        """Devuelve una copia plana (cols*rows,) del frame con el overlay.

        ``cells`` es la matriz del video base decodificado (cualquier forma
        con cols*rows celdas). El frame base nunca se muta.
        """
        out = np.array(cells, dtype=np.uint8).reshape(-1).copy()
        if out.shape[0] != self.cols * self.rows:
            raise ValueError("cells no coincide con la grilla declarada")
        if not self.active:
            return out
        for index, slot in enumerate(self.slots):
            if not (slot["flags"] & 1):
                continue
            if frame_index < slot["start"] or frame_index > slot["end"]:
                continue
            value = self.values[index]
            if value >= len(self.patches):
                continue  # NONE o valor defensivo: no se pinta
            patch = self.patches[value]
            if patch["w"] != slot["w"] or patch["h"] != slot["h"]:
                continue
            data = patch["data"]
            for gy in range(slot["h"]):
                row = (slot["y"] + gy) * self.cols + slot["x"]
                for gx in range(slot["w"]):
                    cell = data[gy * slot["w"] + gx]
                    if cell != TRANSPARENT_INDEX:
                        out[row + gx] = cell
        return out
