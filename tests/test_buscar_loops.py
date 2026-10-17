# -*- coding: utf-8 -*-
"""2026-10-17: tools/buscar_loops.py encuentra intro + loop repetido sobre
miniaturas, sin ffmpeg. Un video sintetico (intro con movimiento + loop con
movimiento repetido + ruido) tiene que devolver su intro, su periodo y sus
vueltas; una escena quieta y un video sin repeticion no son loops."""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import buscar_loops  # noqa: E402

ALTO, ANCHO = 18, 32


def cuadro_movil(t, semilla):
    """Un cuadro con un patron que se desplaza con t (movimiento real entre
    vecinos), distinto para cada semilla."""
    y, x = np.mgrid[0:ALTO, 0:ANCHO].astype(np.float32)
    fase = semilla * 1.7
    return (127 + 100 * np.sin((x + 3.0 * t) / 3.0 + fase)
            * np.cos((y - 2.0 * t) / 4.0 + fase)).astype(np.float32)


def cuadro_ciclico(t, periodo):
    """Un cuadro de un loop que CIERRA: el patron da una vuelta entera en
    `periodo` cuadros, asi el ultimo -> el primero es un paso como cualquiera."""
    y, x = np.mgrid[0:ALTO, 0:ANCHO].astype(np.float32)
    fase = 2 * np.pi * t / float(periodo)
    # Suma (no producto) de un termino de periodo 2*pi y otro de periodo pi:
    # el patron vuelve a ser igual SOLO al completar la vuelta.
    return (127 + 70 * np.sin(x / 3.0 + fase)
            + 40 * np.cos(y / 4.0 + 2 * fase)).astype(np.float32)


def video(intro=30, periodo=20, vueltas=4, cola=5, ruido=0.3, semilla=0, ciclico=True):
    rng = np.random.RandomState(semilla)
    if ciclico:
        loop = [cuadro_ciclico(t, periodo) for t in range(periodo)]
    else:
        loop = [cuadro_movil(t, 2) for t in range(periodo)]
    cuadros = [cuadro_movil(t, 1) for t in range(intro)]
    for _ in range(vueltas):
        cuadros += loop
    cuadros += [cuadro_movil(t + 50, 3) for t in range(cola)]
    mini = np.stack(cuadros)
    return mini + rng.normal(0, ruido, mini.shape).astype(np.float32)


class DeteccionTest(unittest.TestCase):
    def test_encuentra_intro_periodo_y_vueltas(self):
        loop = buscar_loops.detectar_loop(video(), fps_fuente=10, min_seg=0.5, max_seg=5)
        self.assertIsNotNone(loop)
        self.assertEqual(loop["intro"], 30)
        self.assertEqual(loop["periodo"], 20)
        self.assertEqual(loop["vueltas"], 4)
        self.assertEqual(loop["cola"], 5)
        self.assertLess(loop["dif_copias"], 1.0)

    def test_periodo_fundamental_no_un_multiplo(self):
        # El doble del periodo tambien coincide, pero con una racha mas corta.
        loop = buscar_loops.detectar_loop(video(intro=0, periodo=12, vueltas=6, cola=0),
                                          fps_fuente=10, min_seg=0.5, max_seg=5)
        self.assertEqual(loop["periodo"], 12)
        self.assertEqual(loop["intro"], 0)
        self.assertEqual(loop["vueltas"], 6)

    def test_escena_quieta_no_es_un_loop(self):
        rng = np.random.RandomState(1)
        quieto = np.full((60, ALTO, ANCHO), 90.0, dtype=np.float32)
        quieto += rng.normal(0, 0.3, quieto.shape).astype(np.float32)
        self.assertIsNone(buscar_loops.detectar_loop(quieto, 10, 0.5, 5))

    def test_sin_repeticion_no_hay_loop(self):
        sin = np.stack([cuadro_movil(t, 1) for t in range(80)])
        self.assertIsNone(buscar_loops.detectar_loop(sin, 10, 0.5, 5))

    def test_la_costura_de_un_loop_que_cierra_cae_entre_los_vecinos(self):
        salto, percentil, mediana = buscar_loops.costura(video(), 30, 20)
        self.assertLess(percentil, 100.0)
        self.assertGreater(mediana, 0.0)

    def test_una_costura_que_salta_se_detecta(self):
        # Mismo loop repetido, pero su ultimo cuadro no lleva al primero.
        mini = video(ciclico=False)
        loop = buscar_loops.detectar_loop(mini, 10, 0.5, 5)
        self.assertEqual((loop["intro"], loop["periodo"]), (30, 20))
        salto, percentil, mediana = buscar_loops.costura(mini, 30, 20)
        self.assertEqual(percentil, 100.0)
        self.assertGreater(salto, mediana)
        self.assertIn("mas brusco que todos",
                      "\n".join(buscar_loops.reporte(loop, salto=(salto, percentil, mediana))))


def media_pantalla(periodo=6, cuadros=60, ruido=0.3, semilla=0):
    """Mitad superior en loop ciclico de `periodo`; mitad inferior siempre en
    movimiento, sin repetir."""
    rng = np.random.RandomState(semilla)
    salida = []
    for t in range(cuadros):
        arriba = cuadro_ciclico(t % periodo, periodo)
        abajo = cuadro_movil(t, 5)
        cuadro = np.vstack([arriba[:ALTO // 2], abajo[ALTO // 2:]])
        salida.append(cuadro)
    mini = np.stack(salida)
    return mini + rng.normal(0, ruido, mini.shape).astype(np.float32)


class PorZonaTest(unittest.TestCase):
    def test_encuentra_la_mitad_que_repite(self):
        zona = buscar_loops.detectar_loops_por_zona(media_pantalla(), fps_fuente=10,
                                                    min_seg=0.3, max_seg=3)
        self.assertIsNotNone(zona)
        self.assertEqual(zona["periodo"], 6)
        self.assertAlmostEqual(zona["area"], 0.5)
        self.assertTrue(zona["mascara"][:2].all())
        self.assertFalse(zona["mascara"][2:].any())
        texto = "\n".join(buscar_loops.reporte_zona(zona, fps_destino=10))
        self.assertIn("50 % de la pantalla", texto)
        self.assertIn("####", texto)
        self.assertIn("6.00 cuadros (exacto)", texto)

    def test_pantalla_completa_se_deriva_al_archivo_unico(self):
        mini = video(intro=0, periodo=8, vueltas=8, cola=0)
        zona = buscar_loops.detectar_loops_por_zona(mini, 10, 0.3, 3)
        self.assertEqual(zona["periodo"], 8)
        self.assertEqual(zona["area"], 1.0)
        self.assertIn("TODA la pantalla", "\n".join(buscar_loops.reporte_zona(zona)))

    def test_todo_en_movimiento_no_es_loop_por_zona(self):
        sin = np.stack([cuadro_movil(t, 1) for t in range(60)])
        self.assertIsNone(buscar_loops.detectar_loops_por_zona(sin, 10, 0.3, 3))

    def test_escena_quieta_no_es_loop_por_zona(self):
        rng = np.random.RandomState(2)
        quieto = np.full((60, ALTO, ANCHO), 70.0, dtype=np.float32)
        quieto += rng.normal(0, 0.3, quieto.shape).astype(np.float32)
        self.assertIsNone(buscar_loops.detectar_loops_por_zona(quieto, 10, 0.3, 3))

    def test_periodo_a_fps(self):
        self.assertEqual(buscar_loops.periodo_a_fps(12, 10, 10), (12.0, True))
        cuadros, exacto = buscar_loops.periodo_a_fps(85, 24, 10)
        self.assertAlmostEqual(cuadros, 35.4166, places=3)
        self.assertFalse(exacto)
        self.assertTrue(buscar_loops.periodo_a_fps(24, 24, 10)[1])

    def test_por_zona_promedia_cada_zona(self):
        valores = np.zeros((1, 4, 4), dtype=np.float32)
        valores[0, :2, :2] = 8.0
        zonas = buscar_loops.por_zona(valores, 2, 2)
        self.assertEqual(zonas.shape, (1, 2, 2))
        self.assertEqual(float(zonas[0, 0, 0]), 8.0)
        self.assertEqual(float(zonas[0, 1, 1]), 0.0)


class PiezasTest(unittest.TestCase):
    def test_racha_tolera_un_hueco_chico(self):
        iguales = [False, True, True, False, True, True, True, False, False, False, True]
        self.assertEqual(buscar_loops.racha_mas_larga(iguales, hueco=1), (1, 6))
        self.assertEqual(buscar_loops.racha_mas_larga(iguales, hueco=0), (4, 3))
        self.assertEqual(buscar_loops.racha_mas_larga([False, False]), (0, 0))

    def test_recorta_el_fundido_de_los_bordes(self):
        dif = np.array([5.0, 0.9, 0.2, 0.2, 0.2, 0.2, 0.21, 0.19, 0.6], dtype=np.float32)
        self.assertEqual(buscar_loops.recortar_bordes(dif, 0, len(dif)), (2, 6))

    def test_ajuste_a_cuadros_enteros(self):
        # intro_D: 85 cuadros a 24 fps = 3,542 s -> 35 cuadros a 10 fps (+1,2 %).
        cuadros, factor = buscar_loops.ajustar_a_fps(85, 24, 10)
        self.assertEqual(cuadros, 35)
        self.assertAlmostEqual(factor, 3.5 / (85 / 24.0), places=9)
        self.assertEqual(buscar_loops.ajustar_a_fps(48, 24, 10), (20, 1.0))

    def test_miniaturas_de_bytes_descarta_el_cuadro_incompleto(self):
        data = bytes(range(6)) * 2 + b"\x01\x02"
        mini = buscar_loops.miniaturas_de_bytes(data, ancho=3, alto=2)
        self.assertEqual(mini.shape, (2, 2, 3))
        self.assertEqual(mini.dtype, np.float32)

    def test_comando_de_miniaturas(self):
        command = buscar_loops.miniaturas_command("ffmpeg", "f.mp4", 64, 36)
        self.assertIn("scale=64:36:flags=area,format=gray", command)
        self.assertEqual(command[-3:], ["-pix_fmt", "gray", "-"])
        self.assertNotIn("fps=", " ".join(command))   # la cadencia de la fuente, sin tocar

    def test_parse_fps(self):
        self.assertEqual(buscar_loops.parse_fps("24/1"), 24.0)
        self.assertAlmostEqual(buscar_loops.parse_fps("30000/1001"), 29.97, places=2)
        self.assertEqual(buscar_loops.parse_fps("25"), 25.0)

    def test_reporte_sin_loop_y_con_loop(self):
        self.assertIn("sin loop", buscar_loops.reporte(None)[0])
        loop = buscar_loops.detectar_loop(video(), 10, 0.5, 5)
        texto = "\n".join(buscar_loops.reporte(loop, fps_destino=10))
        self.assertIn("vueltas    4 completas", texto)
        self.assertIn("loop = 20 cuadros", texto)


if __name__ == "__main__":
    unittest.main()
