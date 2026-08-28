#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7-4: referencia Python del runtime del overlay (INT-001 §9).

Espejo semantico de ``frontend/overlay.js``: dada la metadata ASCLSLOT
validada (``tools/make_slots.validate``) y la misma cadena de datos, produce
la matriz de celdas compuesta **byte-identica** a la que el reader JavaScript
presenta tras ``beforeSeek()/seek()/afterSeek()``.

La referencia no necesita la disciplina de restauracion del runtime (opera
sobre una copia del frame decodificado, nunca muta el estado del decoder);
esa disciplina es justamente lo que garantiza que el runtime JS equivalga a
esta composicion pura: ``compose(decode(f)) == cells_js(f)``.

Las mutadoras replican el contrato del runtime: validan todo antes de aplicar
nada y devuelven ``False`` sin tocar el estado ante cualquier dato invalido
(INV-7). ``pad=0`` deja los ceros a la izquierda como glifo vacio.
"""
import numpy as np

EMPTY_GLYPH = 10
TRANSPARENT_INDEX = 255


class OverlayRef(object):
    def __init__(self, meta, cols, rows):
        self.glyph_w = int(meta["glyph_w"])
        self.glyph_h = int(meta["glyph_h"])
        self.n_glyphs = int(meta["n_glyphs"])
        if self.n_glyphs < EMPTY_GLYPH + 1:
            raise ValueError("la tabla necesita el glifo vacio (11 glifos)")
        self.glyph_table = bytearray(meta["glyph_table"])
        self.slots = meta["slots"]
        self.fields = meta["fields"]
        self.cols = int(cols)
        self.rows = int(rows)
        for slot in self.slots:
            if slot["x"] + self.glyph_w > self.cols or \
                    slot["y"] + self.glyph_h > self.rows:
                raise ValueError("slot fuera de la grilla")
        self.values = [EMPTY_GLYPH] * len(self.slots)
        self.active = True
        self._field_by_id = {}
        self.digit_count = 0
        for field in self.fields:
            self._field_by_id[field["field_id"]] = field
            self.digit_count += len(field["slot_ids"])

    # -- mutadoras: mismo contrato que overlay.js -------------------------
    def _apply_field(self, field, value):
        ids = field["slot_ids"]
        rest = value
        wrote = False
        for k in range(len(ids) - 1, -1, -1):
            if not field["pad"] and wrote and rest == 0:
                self.values[ids[k]] = EMPTY_GLYPH
            else:
                self.values[ids[k]] = rest % 10
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
            count = len(field["slot_ids"])
            value = int(digits[position:position + count])
            if value < field["min"] or value > field["max"]:
                return False
            loads.append(value)
            position += count
        for field, value in zip(self.fields, loads):
            self._apply_field(field, value)
        self.active = True
        return True

    def clear_field(self, field_id):
        field = self._field_by_id.get(field_id)
        if field is None:
            return False
        for slot_id in field["slot_ids"]:
            self.values[slot_id] = EMPTY_GLYPH
        return True

    def clear(self):
        self.values = [EMPTY_GLYPH] * len(self.slots)
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
        area = self.glyph_w * self.glyph_h
        for index, slot in enumerate(self.slots):
            if not (slot["flags"] & 1):
                continue
            if frame_index < slot["start"] or frame_index > slot["end"]:
                continue
            glyph = self.values[index]
            if glyph >= self.n_glyphs:
                glyph = EMPTY_GLYPH
            base = glyph * area
            for gy in range(self.glyph_h):
                row = (slot["y"] + gy) * self.cols + slot["x"]
                for gx in range(self.glyph_w):
                    value = self.glyph_table[base + gy * self.glyph_w + gx]
                    if value != TRANSPARENT_INDEX:
                        out[row + gx] = value
        return out
