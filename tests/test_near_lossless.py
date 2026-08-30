# -*- coding: utf-8 -*-
"""E-24: perfil --near-lossless = un presupuesto para las dos etapas del trellis.

``resolve_near_lossless`` es la unica fuente de verdad del perfil: con 0 es un
passthrough exacto de los flags explicitos (bytes identicos), con N fija
temporal y espacial a N, y mezclarlo con un presupuesto explicito se rechaza
(regla 9: el numero del operador no se pisa en silencio). make_clip la cablea
antes de llamar al encoder.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import make_clip  # noqa: E402
import trellis  # noqa: E402


class ResolveNearLosslessTest(unittest.TestCase):
    def test_zero_is_an_exact_passthrough(self):
        self.assertEqual(trellis.resolve_near_lossless(0, 0, 0), (0, 0))
        self.assertEqual(trellis.resolve_near_lossless(0, 4.0, 8.0),
                         (4.0, 8.0))

    def test_positive_budget_sets_both_stages(self):
        self.assertEqual(trellis.resolve_near_lossless(6.0, 0, 0), (6.0, 6.0))

    def test_mixing_with_explicit_budgets_is_rejected(self):
        for temporal, spatial in ((4.0, 0), (0, 8.0), (4.0, 8.0)):
            with self.assertRaisesRegex(ValueError, "near-lossless"):
                trellis.resolve_near_lossless(6.0, temporal, spatial)

    def test_negative_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "near-lossless"):
            trellis.resolve_near_lossless(-1.0, 0, 0)


class MakeClipWiringTest(unittest.TestCase):
    INFO = {
        "mode": "pixel", "cols": 32, "rows": 18, "fps": 15,
        "n_frames": 2, "palette_mode": "global", "quality_profile": "custom",
        "pal_size": 16, "bake_smoothing": "none", "reconstruction": "nearest",
        "flags": 12, "palette_algorithm": "kmeans-rgb", "dither": "off",
        "dither_matrix": 4, "audio": None,
    }
    V2_STATS = {
        "regional_frames": 1, "n_frames": 2, "saved_bytes": 50,
        "saved_percent": 5.0,
    }

    def run_make_clip(self, extra_args):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "clip.asclv")
            with mock.patch.object(make_clip.encoder, "encode_video",
                                   return_value=dict(self.INFO)) as encode_video, \
                    mock.patch.object(make_clip.ascl_v2, "transcode_path",
                                      return_value=dict(self.V2_STATS)), \
                    mock.patch.object(make_clip.ascl_bundle, "pack",
                                      return_value=(1000, 900, 100)), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = make_clip.main(
                    ["synthetic.mp4", "--out", output, "--format", "v2",
                     "--keep"] + extra_args)
            self.assertEqual(result, 0)
            return encode_video.call_args

    def test_near_lossless_reaches_the_encoder_as_both_budgets(self):
        call = self.run_make_clip(["--near-lossless", "6"])
        self.assertEqual(call.kwargs["trellis_temporal"], 6.0)
        self.assertEqual(call.kwargs["trellis_spatial"], 6.0)

    def test_explicit_flags_still_pass_verbatim_without_the_profile(self):
        call = self.run_make_clip(["--trellis-temporal", "4",
                                   "--trellis-spatial", "8"])
        self.assertEqual(call.kwargs["trellis_temporal"], 4.0)
        self.assertEqual(call.kwargs["trellis_spatial"], 8.0)

    def test_cli_mixing_profile_and_explicit_budget_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "clip.asclv")
            with mock.patch.object(make_clip.encoder, "encode_video",
                                   return_value=dict(self.INFO)) as encode_video, \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "near-lossless"):
                    make_clip.main(["synthetic.mp4", "--out", output,
                                    "--near-lossless", "6",
                                    "--trellis-temporal", "4"])
            encode_video.assert_not_called()


if __name__ == "__main__":
    unittest.main()
