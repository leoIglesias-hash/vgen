# -*- coding: utf-8 -*-
"""2026-10-17: tools/mp4_dedup.py guarda cada muestra repetida UNA vez y
reapunta el indice. Sin ffmpeg: mp4 sinteticos armados caja por caja (indice
con varias corridas de stsc, tamano fijo, co64, varias pistas, sin
repeticiones), un mp4 fragmentado que tiene que rechazar y un archivo
corrompido que la verificacion tiene que atrapar."""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mp4_dedup  # noqa: E402


def caja(tipo, cuerpo):
    return struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo


def full(tipo, cuerpo):
    return caja(tipo, b"\0\0\0\0" + cuerpo)


def corridas_stsc(por_chunk):
    """[3, 3, 2, 2] -> entradas (first_chunk, samples_per_chunk, 1)."""
    corridas = []
    for c, n in enumerate(por_chunk, start=1):
        if not corridas or corridas[-1][1] != n:
            corridas.append((c, n, 1))
    return corridas


def stbl(muestras, por_chunk, offsets_chunk, co64=False, fijo=False):
    tamanos = [len(m) for m in muestras]
    if fijo:
        assert len(set(tamanos)) == 1
        stsz = full(b"stsz", struct.pack(">II", tamanos[0], len(tamanos)))
    else:
        stsz = full(b"stsz", struct.pack(">II", 0, len(tamanos))
                    + struct.pack(">%dI" % len(tamanos), *tamanos))
    corr = corridas_stsc(por_chunk)
    stsc = full(b"stsc", struct.pack(">I", len(corr))
                + b"".join(struct.pack(">III", *c) for c in corr))
    if co64:
        co = full(b"co64", struct.pack(">I", len(offsets_chunk))
                  + struct.pack(">%dQ" % len(offsets_chunk), *offsets_chunk))
    else:
        co = full(b"stco", struct.pack(">I", len(offsets_chunk))
                  + struct.pack(">%dI" % len(offsets_chunk), *offsets_chunk))
    stts = full(b"stts", struct.pack(">III", 1, len(muestras), 100))
    stss = full(b"stss", struct.pack(">II", 1, 1))
    stsd = full(b"stsd", struct.pack(">I", 0))
    return caja(b"stbl", stsd + stts + stss + stsz + stsc + co)


def trak(stbl_bytes):
    minf = caja(b"minf", full(b"vmhd", b"\0" * 8) + stbl_bytes)
    mdia = caja(b"mdia", full(b"mdhd", b"\0" * 20) + full(b"hdlr", b"\0" * 21) + minf)
    return caja(b"trak", full(b"tkhd", b"\0" * 80) + mdia)


def mp4(pistas, co64=False, fijo=False, fragmentado=False):
    """pistas = [(muestras, por_chunk)]. mdat al final, pistas una tras otra.
    Dos pasadas: la cabeza con offsets en 0 mide lo mismo que la definitiva."""
    ftyp = caja(b"ftyp", b"isom\0\0\0\0isom")

    def armar(base):
        traks = b""
        pos = base
        cuerpo = b""
        for muestras, por_chunk in pistas:
            offsets = []
            i = 0
            for n in por_chunk:
                offsets.append(pos)
                for m in muestras[i:i + n]:
                    pos += len(m)
                    cuerpo += m
                i += n
            traks += trak(stbl(muestras, por_chunk, offsets, co64, fijo))
        moov = caja(b"moov", full(b"mvhd", b"\0" * 96) + traks)
        extra = caja(b"moof", b"\0" * 8) if fragmentado else b""
        return ftyp + moov + extra, cuerpo

    cabeza, _ = armar(0)
    cabeza, cuerpo = armar(len(cabeza) + 8)
    return cabeza + caja(b"mdat", cuerpo)


def muestras_de_archivo(data):
    top = mp4_dedup.leer_cajas(data)
    traks = [c for c in mp4_dedup.buscar(top, b"moov")[1] if c[0] == b"trak"]
    return [mp4_dedup.muestras_de(data, t) for t in traks]


def cajas_de_stbl(data, tipo):
    top = mp4_dedup.leer_cajas(data)
    t = [c for c in mp4_dedup.buscar(top, b"moov")[1] if c[0] == b"trak"][0]
    return mp4_dedup.buscar(mp4_dedup.stbl_de(t)[1], tipo)[1]


INTRO = [b"I0-keyframe-intro", b"I1-p", b"I2-p"]
LOOP = [b"L0-keyframe-del-loop!", b"L1-p-del-loop", b"L2-ultimo"]


class DedupTest(unittest.TestCase):
    def test_intro_mas_vueltas_queda_una_vuelta(self):
        muestras = INTRO + LOOP * 5
        original = mp4([(muestras, [3, 3, 3, 3, 3, 3])])
        salida, r = mp4_dedup.deduplicar(original)
        self.assertEqual(r["muestras"], 18)
        self.assertEqual(r["unicas"], 6)
        self.assertEqual(r["datos_despues"], sum(len(m) for m in INTRO + LOOP))
        self.assertLess(len(salida), len(original))
        self.assertEqual(muestras_de_archivo(salida), [muestras])

    def test_tiempos_y_keyframes_no_se_tocan(self):
        original = mp4([(INTRO + LOOP * 3, [2, 2, 2, 2, 2, 2])])
        salida, _ = mp4_dedup.deduplicar(original)
        for tipo in (b"stts", b"stss", b"stsz", b"stsd"):
            self.assertEqual(cajas_de_stbl(salida, tipo), cajas_de_stbl(original, tipo))

    def test_indice_nuevo_una_muestra_por_chunk(self):
        original = mp4([(INTRO + LOOP * 2, [4, 4, 1])])
        salida, _ = mp4_dedup.deduplicar(original)
        self.assertEqual(cajas_de_stbl(salida, b"stsc"), struct.pack(">IIIII", 0, 1, 1, 1, 1))
        stco = cajas_de_stbl(salida, b"stco")
        n = struct.unpack(">I", stco[4:8])[0]
        offsets = struct.unpack(">%dI" % n, stco[8:])
        self.assertEqual(n, 9)
        # Las vueltas 2 apuntan a los mismos bytes que la 1.
        self.assertEqual(offsets[3:6], offsets[6:9])
        self.assertTrue(all(o < len(salida) for o in offsets))

    def test_stsc_con_varias_corridas_y_ultimo_chunk_corto(self):
        muestras = [bytes([65 + k]) * (k + 1) for k in range(10)]
        salida, r = mp4_dedup.deduplicar(mp4([(muestras, [3, 3, 2, 2])]))
        self.assertEqual(r["unicas"], 10)
        self.assertEqual(muestras_de_archivo(salida), [muestras])

    def test_tamano_fijo_en_stsz(self):
        muestras = [b"abcd", b"efgh", b"abcd", b"efgh", b"ijkl"]
        salida, r = mp4_dedup.deduplicar(mp4([(muestras, [5])], fijo=True))
        self.assertEqual(r["unicas"], 3)
        self.assertEqual(muestras_de_archivo(salida), [muestras])

    def test_entrada_co64(self):
        muestras = INTRO + LOOP * 2
        salida, r = mp4_dedup.deduplicar(mp4([(muestras, [3, 3, 3])], co64=True))
        self.assertEqual(r["unicas"], 6)
        self.assertEqual(muestras_de_archivo(salida), [muestras])

    def test_varias_pistas_cada_una_conserva_lo_suyo(self):
        video = INTRO + LOOP * 3
        audio = [b"aac-frame-1", b"aac-frame-2"] * 4
        salida, r = mp4_dedup.deduplicar(mp4([(video, [3, 3, 3, 3]), (audio, [4, 4])]))
        self.assertEqual(r["pistas"], 2)
        self.assertEqual(r["unicas"], 6 + 2)
        self.assertEqual(muestras_de_archivo(salida), [video, audio])

    def test_sin_repeticiones_conserva_todo(self):
        muestras = [b"m%02d" % k for k in range(12)]
        salida, r = mp4_dedup.deduplicar(mp4([(muestras, [4, 4, 4])]))
        self.assertEqual(r["unicas"], 12)
        self.assertEqual(r["datos_despues"], r["datos_antes"])
        self.assertEqual(muestras_de_archivo(salida), [muestras])

    def test_es_determinista(self):
        original = mp4([(INTRO + LOOP * 4, [3, 3, 3, 3, 3])])
        self.assertEqual(mp4_dedup.deduplicar(original)[0], mp4_dedup.deduplicar(original)[0])


class RechazosTest(unittest.TestCase):
    def test_fragmentado_se_rechaza(self):
        with self.assertRaises(mp4_dedup.NoSoportado):
            mp4_dedup.deduplicar(mp4([(INTRO, [3])], fragmentado=True))

    def test_sin_moov_se_rechaza(self):
        with self.assertRaises(mp4_dedup.NoSoportado):
            mp4_dedup.deduplicar(caja(b"ftyp", b"isom\0\0\0\0") + caja(b"mdat", b"x"))

    def test_la_verificacion_atrapa_un_byte_cambiado(self):
        muestras = INTRO + LOOP * 2
        salida, _ = mp4_dedup.deduplicar(mp4([(muestras, [3, 3, 3])]))
        roto = bytearray(salida)
        roto[-1] ^= 0xFF          # ultimo byte del mdat = ultima muestra unica
        with self.assertRaises(AssertionError):
            mp4_dedup.verificar([muestras], bytes(roto))

    def test_caja_truncada(self):
        with self.assertRaises(ValueError):
            mp4_dedup.leer_cajas(struct.pack(">I4s", 100, b"moov") + b"\0" * 10)


if __name__ == "__main__":
    unittest.main()
