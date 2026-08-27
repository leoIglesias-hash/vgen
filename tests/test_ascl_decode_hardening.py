# -*- coding: utf-8 -*-
"""E-02: el decoder/verificador de referencia rechaza archivos corruptos.

Antes ascl_decode.py calculaba el CRC sin abortar, inflaba sin cota y aplicaba
offsets sin validar: un .ascl corrupto podia "verificarse" como correcto.
"""
import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
import ascl_decode  # noqa: E402


def _pixel_ascl(frames, flags=10, pal_size=2, cols=2, rows=1, crc=None):
    body_frames = b"".join(frames)
    data_off = ascl_decode.HEADER_SIZE
    table = b""
    offset = data_off + 4 * len(frames)
    for frame in frames:
        table += struct.pack("<I", offset)
        offset += len(frame)
    body = table + body_frames
    real_crc = zlib.crc32(body) & 0xFFFFFFFF if crc is None else crc
    header = struct.pack(ascl_decode.HEADER_FMT, b"ASCL", 1,
                         ascl_decode.MODE_PIXEL, flags, 15, cols, rows,
                         pal_size, len(frames), 0, 3, data_off, 1000, 0,
                         real_crc)
    return header + body


def _key_frame(values, palette=bytes((0, 0, 0, 255, 255, 255))):
    body = struct.pack("<BH", ascl_decode.TAG_RAW, len(palette) // 3)
    body += palette + bytes(values)
    return struct.pack("<I", len(body)) + body


def _delta_mask_frame(mask, values):
    payload = zlib.compress(bytes(mask) + bytes(values), 9)
    body = struct.pack("<BH", ascl_decode.TAG_DELTA_MASK, 0) + payload
    return struct.pack("<I", len(body)) + body


class DecodeHardening(unittest.TestCase):
    def _write(self, data):
        import tempfile
        handle = tempfile.NamedTemporaryFile(suffix=".ascl", delete=False)
        handle.write(data)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_valid_file_decodes(self):
        data = _pixel_ascl([_key_frame((0, 1)),
                            _delta_mask_frame((0b10,), (0,))])
        hdr, _ramp, cells, _pal = ascl_decode.decode_all(self._write(data))
        self.assertTrue(hdr["crc_ok"])
        self.assertEqual(cells[1][:, 0].tolist(), [0, 0])

    def test_bad_crc_aborts(self):
        data = _pixel_ascl([_key_frame((0, 1))], crc=0xDEADBEEF)
        with self.assertRaises(ValueError):
            ascl_decode.decode_all(self._write(data))

    def test_crc_zero_is_omitted_not_invalid(self):
        data = _pixel_ascl([_key_frame((0, 1))], crc=0)
        hdr, _ramp, _cells, _pal = ascl_decode.decode_all(self._write(data))
        self.assertTrue(hdr["crc_ok"])

    def test_out_of_range_index_rejected(self):
        # celda con indice 7 y paleta de 2 entradas
        data = _pixel_ascl([_key_frame((0, 7))])
        with self.assertRaises(Exception):
            ascl_decode.decode_all(self._write(data))

    def test_truncated_payload_rejected(self):
        good = _pixel_ascl([_key_frame((0, 1))])
        with self.assertRaises(Exception):
            ascl_decode.decode_all(self._write(good[:-1]))

    def test_zip_bomb_bounded(self):
        # ZLIB declara descomprimir mucho mas que n celdas
        bomb = zlib.compress(b"\\x00" * 1000000, 9)
        body = struct.pack("<BH", ascl_decode.TAG_ZLIB, 2)
        body += bytes((0, 0, 0, 255, 255, 255)) + bomb
        frame = struct.pack("<I", len(body)) + body
        data = _pixel_ascl([frame])
        with self.assertRaises(Exception):
            ascl_decode.decode_all(self._write(data))


if __name__ == "__main__":
    unittest.main()
