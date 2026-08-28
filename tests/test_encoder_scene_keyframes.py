#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-10 — keyframes en cortes de escena y GOP variable."""
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_decode  # noqa: E402
import encoder  # noqa: E402


WIDTH, HEIGHT = 24, 16


def with_gray(rgb):
    x = rgb.astype(np.uint16)
    gray = ((77 * x[:, :, 0] + 150 * x[:, :, 1] +
             29 * x[:, :, 2]) >> 8).astype(np.uint8)
    return rgb, gray


def two_scene_frames():
    """Dos escenas de 4 frames. El fondo es ruido incompresible (asi un frame
    completo NUNCA gana como ZLIB frente a un delta chico) y el corte cambia
    solo las dos filas superiores a un color plano fuerte: sin E-10 el corte
    se codifica como DELTA y la cadena no se rompe."""
    rng = np.random.RandomState(77)
    noise = rng.randint(0, 256, size=(HEIGHT, WIDTH, 3)).astype(np.uint8)
    scene_b_rgb = noise.copy()
    scene_b_rgb[:2, :, 0] = 250
    scene_b_rgb[:2, :, 1] = 200
    scene_b_rgb[:2, :, 2] = 30
    scene_a = with_gray(noise)
    scene_b = with_gray(scene_b_rgb)
    frames = []
    for _ in range(4):
        frames.append((scene_a[0].copy(), scene_a[1].copy()))
    for _ in range(4):
        frames.append((scene_b[0].copy(), scene_b[1].copy()))
    return frames


def encode(path, frames, **options):
    def fake_iter(_path, _cols, _rows, _fps, _bake="none"):
        return iter(frames)

    defaults = dict(
        # Paleta 256 sobre ruido: el frame completo pesa ~n bytes incluso en
        # ZLIB, de modo que el delta de dos filas gana con margen amplio.
        mode_name="pixel", cols=WIDTH, rows=HEIGHT, fps=15, pal_size=256,
        ramp_name="short", char_aspect=0.5, compress="auto",
        palette_mode="global", keyint=100, with_audio=False,
        palette_algorithm="fast-octree",
        # Umbral bajo: el corte parcial (2 filas) debe superarlo; los frames
        # identicos dentro de cada escena dan score 0.0 y nunca lo cruzan.
        # (la config exige change_threshold < hard_cut_threshold)
        adaptive_change_threshold=0.02,
        adaptive_hard_cut_threshold=0.05)
    defaults.update(options)
    with mock.patch.object(encoder, "probe_size", return_value=(WIDTH, HEIGHT)), \
            mock.patch.object(encoder, "iter_video_frames", side_effect=fake_iter):
        return encoder.encode_video("synthetic.mp4", path, **defaults)


def frame_tags(path):
    with open(path, "rb") as stream:
        data = stream.read()
    header = ascl_decode.parse_header(data)
    offsets = struct.unpack_from("<%dI" % header["n_frames"],
                                 data, header["data_off"])
    return [data[offset + 4] for offset in offsets]


def key_flags(tags):
    return [tag in (0, 1) for tag in tags]  # RAW o ZLIB = keyframe v1


def max_delta_chain(tags):
    longest = current = 0
    for tag in tags:
        current = 0 if tag in (0, 1) else current + 1
        longest = max(longest, current)
    return longest


class SceneKeyframesTest(unittest.TestCase):
    def test_scene_cut_produces_keyframe_and_shortens_delta_chain(self):
        frames = two_scene_frames()
        with tempfile.TemporaryDirectory() as directory:
            before_path = os.path.join(directory, "before.ascl")
            after_path = os.path.join(directory, "after.ascl")
            info_before = encode(before_path, frames)
            info_after = encode(after_path, frames, scene_keyframes=True)

            tags_before = frame_tags(before_path)
            tags_after = frame_tags(after_path)
            keys_before = key_flags(tags_before)
            keys_after = key_flags(tags_after)

            self.assertEqual(sum(keys_before), 1, "sin E-10 solo el frame 0 es key")
            self.assertEqual(sum(keys_after), 2, "el corte agrega exactamente un key")
            self.assertTrue(keys_after[4], "el corte detectado (frame 4) es keyframe")
            self.assertEqual(info_before["scene_cut_keyframes"], 0)
            self.assertEqual(info_after["scene_cut_keyframes"], 1)
            self.assertFalse(info_before["scene_keyframes"])
            self.assertTrue(info_after["scene_keyframes"])

            self.assertEqual(max_delta_chain(tags_before), 7)
            self.assertEqual(max_delta_chain(tags_after), 3,
                             "la cadena DELTA maxima se corta en el corte")

            # El decoder Python reconstruye exactamente las mismas celdas con y
            # sin el keyframe extra (el corte solo cambia la forma, no el video)
            _h1, _r1, frames_before, _p1 = ascl_decode.decode_all(before_path)
            _h2, _r2, frames_after, _p2 = ascl_decode.decode_all(after_path)
            self.assertEqual(len(frames_before), len(frames_after))
            for cells_a, cells_b in zip(frames_before, frames_after):
                np.testing.assert_array_equal(cells_a, cells_b)

    def test_default_off_is_byte_identical_to_explicit_false(self):
        frames = two_scene_frames()
        with tempfile.TemporaryDirectory() as directory:
            default_path = os.path.join(directory, "default.ascl")
            explicit_path = os.path.join(directory, "explicit.ascl")
            encode(default_path, frames)
            encode(explicit_path, frames, scene_keyframes=False)
            with open(default_path, "rb") as fh:
                default_bytes = fh.read()
            with open(explicit_path, "rb") as fh:
                explicit_bytes = fh.read()
            self.assertEqual(default_bytes, explicit_bytes)

    def test_periodic_keyint_still_applies_with_scene_keyframes(self):
        frames = two_scene_frames()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "keyint.ascl")
            encode(path, frames, scene_keyframes=True, keyint=3)
            keys = key_flags(frame_tags(path))
            self.assertTrue(keys[0] and keys[3] and keys[6],
                            "los keyframes periodicos se conservan")
            self.assertTrue(keys[4], "el corte sigue agregando su keyframe")


if __name__ == "__main__":
    unittest.main()
