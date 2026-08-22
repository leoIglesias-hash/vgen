import os
import sys
import tempfile
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_bundle  # noqa: E402
import ascl_decode  # noqa: E402
import ascl_v2  # noqa: E402
import encoder  # noqa: E402


class PipelineSmokeTest(unittest.TestCase):
    def test_real_synthetic_video_encodes_v1_transcodes_v2_and_bundles(self):
        source = os.path.join(ROOT, "inputs", "synthetic.mp4")
        self.assertTrue(os.path.exists(source))
        with tempfile.TemporaryDirectory() as directory:
            v1_path = os.path.join(directory, "synthetic-v1.ascl")
            v2_path = os.path.join(directory, "synthetic-v2.ascl")
            bundle_path = os.path.join(directory, "synthetic-v2.asclv")
            info = encoder.encode_video(
                source, v1_path, "pixel", 32, 0, 5, 16, "short", 0.5,
                "auto", "global", 10, False,
                palette_algorithm="fast-octree")
            stats = ascl_v2.transcode_path(v1_path, v2_path)
            header_v1, _ramp_v1, frames_v1, palettes_v1 = \
                ascl_decode.decode_all(v1_path)
            header_v2, _ramp_v2, frames_v2, palettes_v2 = \
                ascl_decode.decode_all(v2_path)
            ascl_bundle.pack(v2_path, None, bundle_path)
            inner, audio, version = ascl_bundle.read_parts_info(bundle_path)

        self.assertGreater(info["n_frames"], 1)
        self.assertEqual(header_v1["version"], 1)
        self.assertEqual(header_v2["version"], 2)
        self.assertEqual(version, 2)
        self.assertEqual(audio, b"")
        self.assertEqual(inner[:5], b"ASCL\x02")
        self.assertLessEqual(stats["output_bytes"], stats["input_bytes"])
        self.assertEqual(len(frames_v1), len(frames_v2))
        for frame_v1, frame_v2, palette_v1, palette_v2 in zip(
                frames_v1, frames_v2, palettes_v1, palettes_v2):
            np.testing.assert_array_equal(frame_v1, frame_v2)
            np.testing.assert_array_equal(palette_v1, palette_v2)


if __name__ == "__main__":
    unittest.main()
