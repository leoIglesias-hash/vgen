# -*- coding: utf-8 -*-
"""H-27: la referencia y4m con una paleta adaptativa de N colores (Oklab),
sin ffmpeg. Se verifica la ida y vuelta 709 tv, que K-means encuentre los
colores que hay, que la tabla los aplique y que el y4m de salida tenga la
misma cabecera, los mismos cuadros y no mas colores que los pedidos."""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import cuantizar_y4m  # noqa: E402

ROJO, VERDE, AZUL, GRIS = (250, 10, 10), (10, 240, 20), (20, 20, 250), (128, 128, 128)


def cuadro_de_bloques(colores, ancho=16, alto=8, bloque=4):
    """Un cuadro RGB uint8 hecho de bloques `bloque`x`bloque`, ciclando los
    colores. Alineado a 4 para que el promedio 2x2 del croma no mezcle."""
    rgb = np.zeros((alto, ancho, 3), dtype=np.uint8)
    n = 0
    for y in range(0, alto, bloque):
        for x in range(0, ancho, bloque):
            rgb[y:y + bloque, x:x + bloque] = colores[n % len(colores)]
            n += 1
    return rgb


def y4m_de(cuadros, path):
    alto, ancho = cuadros[0].shape[:2]
    with open(path, "wb") as stream:
        stream.write(("YUV4MPEG2 W%d H%d F20:1 Ip A1:1 C420jpeg XCOLORRANGE=LIMITED\n"
                      % (ancho, alto)).encode("ascii"))
        for rgb in cuadros:
            y, cb, cr = cuantizar_y4m.rgb_a_yuv(rgb)
            stream.write(cuantizar_y4m.FRAME_HEADER + y.tobytes() + cb.tobytes() + cr.tobytes())


def cuadros_de(path):
    line, ancho, alto, frames = cuantizar_y4m.cabecera_y4m(path)
    out = []
    with open(path, "rb") as stream:
        stream.readline()
        while True:
            cuadro = cuantizar_y4m.leer_cuadro(stream, ancho, alto)
            if cuadro is None:
                break
            out.append(cuantizar_y4m.yuv_a_rgb(*cuadro))
    return line, frames, out


def colores_unicos(rgb):
    return len(np.unique(rgb.reshape(-1, 3), axis=0))


class ColorTest(unittest.TestCase):

    def test_la_ida_y_vuelta_709_tv_conserva_los_colores(self):
        rgb = cuadro_de_bloques([ROJO, VERDE, AZUL, GRIS, (255, 255, 255), (0, 0, 0)])
        y, cb, cr = cuantizar_y4m.rgb_a_yuv(rgb)
        self.assertEqual((y.shape, cb.shape, cr.shape), ((8, 16), (4, 8), (4, 8)))
        self.assertTrue(np.all(y >= 16) and np.all(y <= 235), "Y en rango tv")
        self.assertTrue(np.all(cb >= 16) and np.all(cb <= 240), "Cb en rango tv")
        vuelta = cuantizar_y4m.yuv_a_rgb(y, cb, cr)
        self.assertLessEqual(int(np.max(np.abs(vuelta.astype(int) - rgb.astype(int)))), 4)

    def test_el_gris_no_tiene_croma_y_el_blanco_es_235(self):
        y, cb, cr = cuantizar_y4m.rgb_a_yuv(cuadro_de_bloques([GRIS]))
        self.assertTrue(np.all(cb == 128) and np.all(cr == 128))
        self.assertEqual(int(y[0, 0]), 126)
        y, _cb, _cr = cuantizar_y4m.rgb_a_yuv(cuadro_de_bloques([(255, 255, 255)]))
        self.assertEqual(int(y[0, 0]), 235)

    def test_la_cabecera_rechaza_lo_que_no_es_420_de_8_bits_y_par(self):
        tmp = tempfile.mkdtemp(prefix="h27-y4m-")
        try:
            path = os.path.join(tmp, "ref.y4m")
            y4m_de([cuadro_de_bloques([ROJO])] * 2, path)
            line, ancho, alto, frames = cuantizar_y4m.cabecera_y4m(path)
            self.assertEqual((ancho, alto, frames), (16, 8, 2))
            self.assertTrue(line.startswith(b"YUV4MPEG2 W16 H8"))
            frame = b"FRAME\n" + b"\x80" * (16 * 8 * 3 // 2)
            with open(path, "wb") as f:
                f.write(b"YUV4MPEG2 W16 H8 F20:1 C444\n" + frame)
            with self.assertRaises(ValueError):
                cuantizar_y4m.cabecera_y4m(path)
            with open(path, "wb") as f:
                f.write(b"YUV4MPEG2 W15 H8 F20:1 C420\n" + frame)
            with self.assertRaises(ValueError):
                cuantizar_y4m.cabecera_y4m(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PaletaTest(unittest.TestCase):

    def test_kmeans_en_oklab_encuentra_los_dos_colores_que_hay(self):
        rng = np.random.RandomState(7)
        rojo = np.array(ROJO) + rng.randint(-3, 4, size=(200, 3))
        azul = np.array(AZUL) + rng.randint(-3, 4, size=(200, 3))
        muestras = np.clip(np.concatenate([rojo, azul]), 0, 255).astype(np.uint8)
        centros, etiquetas = cuantizar_y4m.paleta_oklab(muestras, 2)
        self.assertEqual(centros.shape, (2, 3))
        self.assertEqual(len(np.unique(etiquetas)), 2)
        rgb = cuantizar_y4m.perceptual_palette.oklab_to_srgb(centros)
        # cada color original tiene un centro a menos de 8 (suma de los tres canales)
        for color in (ROJO, AZUL):
            cerca = min(int(np.sum(np.abs(rgb[i].astype(int) - np.array(color)))) for i in range(2))
            self.assertLessEqual(cerca, 8, "%s no tiene centro cerca: %s" % (color, rgb.tolist()))
        with self.assertRaises(ValueError):
            cuantizar_y4m.paleta_oklab(muestras, 1)

    def test_la_paleta_es_determinista(self):
        muestras = cuadro_de_bloques([ROJO, VERDE, AZUL, GRIS]).reshape(-1, 3)
        a, _ = cuantizar_y4m.paleta_oklab(muestras, 3)
        b, _ = cuantizar_y4m.paleta_oklab(muestras, 3)
        self.assertTrue(np.array_equal(a, b))

    def test_la_tabla_aplica_la_paleta_a_un_cuadro(self):
        muestras = cuadro_de_bloques([ROJO, AZUL]).reshape(-1, 3)
        centros, _ = cuantizar_y4m.paleta_oklab(muestras, 2)
        tabla = cuantizar_y4m.tabla_de(centros)
        self.assertEqual(tabla.shape, (cuantizar_y4m.NIVELES ** 3, 3))
        self.assertEqual(tabla.dtype, np.uint8)
        self.assertLessEqual(colores_unicos(tabla), 2)
        cuadro = cuadro_de_bloques([ROJO, VERDE, AZUL, GRIS])
        salida = cuantizar_y4m.aplicar(cuadro, tabla)
        self.assertEqual(salida.shape, cuadro.shape)
        self.assertLessEqual(colores_unicos(salida), 2)
        # el rojo queda rojo y el azul, azul: la tabla no los cruza
        self.assertLess(int(np.sum(np.abs(salida[0, 0].astype(int) - np.array(ROJO)))), 12)
        self.assertLess(int(np.sum(np.abs(salida[0, 8].astype(int) - np.array(AZUL)))), 12)


class ArchivoTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="h27-cuantizar-")
        self.entrada = os.path.join(self.tmp, "ref.y4m")
        self.salida = os.path.join(self.tmp, "ref-c2.y4m")
        cuadro = cuadro_de_bloques([ROJO, VERDE, AZUL, GRIS])
        y4m_de([cuadro, cuadro[:, ::-1].copy(), cuadro], self.entrada)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_el_y4m_de_salida_tiene_la_misma_cabecera_y_no_mas_colores_que_los_pedidos(self):
        mensajes = []
        resumen = cuantizar_y4m.cuantizar(self.entrada, self.salida, 2, mensajes.append)
        self.assertEqual(resumen["cuadros"], 3)
        self.assertEqual(resumen["colores"], 2)
        self.assertEqual(resumen["usados"], 2)
        self.assertEqual(os.path.getsize(self.salida), os.path.getsize(self.entrada))
        linea_in = cuantizar_y4m.cabecera_y4m(self.entrada)[0]
        linea_out, frames, cuadros = cuadros_de(self.salida)
        self.assertEqual(linea_out, linea_in, "la cabecera no cambia: mismo tamano, misma cadencia")
        self.assertEqual(frames, 3)
        for rgb in cuadros:
            self.assertLessEqual(colores_unicos(rgb), 2)
        self.assertTrue(any("paleta 2 colores" in m for m in mensajes), mensajes)

    def test_con_tantos_colores_como_hay_la_imagen_no_cambia(self):
        cuantizar_y4m.cuantizar(self.entrada, self.salida, 4)
        _line, _frames, antes = cuadros_de(self.entrada)
        _line, _frames, despues = cuadros_de(self.salida)
        for a, b in zip(antes, despues):
            self.assertLessEqual(int(np.max(np.abs(a.astype(int) - b.astype(int)))), 6)

    def test_el_muestreo_reparte_cuadros_y_posiciones(self):
        muestras = cuantizar_y4m.muestrear(self.entrada, 16, 8, 3, cuadros=2, pixeles=40)
        self.assertEqual(muestras.shape[1], 3)
        self.assertLessEqual(len(muestras), 40)
        self.assertGreaterEqual(len(muestras), 20)


if __name__ == "__main__":
    unittest.main()
