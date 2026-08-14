import os
import struct
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_bundle  # noqa: E402


class AsclBundleV2Test(unittest.TestCase):
    def test_pack_selects_envelope_that_matches_inner_version(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_path = os.path.join(directory, "audio.mp3")
            with open(audio_path, "wb") as stream:
                stream.write(b"audio")
            for version, magic in ((1, ascl_bundle.MAGIC_V1),
                                   (2, ascl_bundle.MAGIC_V2)):
                ascl_path = os.path.join(directory, "video%d.ascl" % version)
                out_path = os.path.join(directory, "video%d.asclv" % version)
                payload = b"ASCL" + bytes((version,)) + b"payload"
                with open(ascl_path, "wb") as stream:
                    stream.write(payload)
                total, video_len, audio_len = ascl_bundle.pack(
                    ascl_path, audio_path, out_path)
                with open(out_path, "rb") as stream:
                    bundled = stream.read()
                self.assertEqual(bundled[:8], magic)
                self.assertEqual(total, len(bundled))
                self.assertEqual(video_len, len(payload))
                self.assertEqual(audio_len, 5)
                video, audio, detected = ascl_bundle.read_parts_info(out_path)
                self.assertEqual(video, payload)
                self.assertEqual(audio, b"audio")
                self.assertEqual(detected, version)

    def test_reader_rejects_truncation_extra_bytes_and_version_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bad.asclv")
            inner_v2 = b"ASCL" + bytes((2,)) + b"x"
            cases = [
                struct.pack(ascl_bundle.HEADER_FMT, ascl_bundle.MAGIC_V2,
                            len(inner_v2) + 1, 0) + inner_v2,
                struct.pack(ascl_bundle.HEADER_FMT, ascl_bundle.MAGIC_V2,
                            len(inner_v2), 0) + inner_v2 + b"extra",
                struct.pack(ascl_bundle.HEADER_FMT, ascl_bundle.MAGIC_V1,
                            len(inner_v2), 0) + inner_v2,
            ]
            for bundled in cases:
                with open(path, "wb") as stream:
                    stream.write(bundled)
                with self.assertRaises(ValueError):
                    ascl_bundle.read_parts_info(path)

    def test_pack_bytes_preserves_payloads_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "memory.asclv")
            video = b"ASCL" + bytes((2,)) + b"regional"
            audio = bytes(range(32))
            total, video_len, audio_len = ascl_bundle.pack_bytes(
                video, audio, out_path)
            restored_video, restored_audio, version = ascl_bundle.read_parts_info(out_path)
            self.assertEqual((restored_video, restored_audio), (video, audio))
            self.assertEqual((video_len, audio_len), (len(video), len(audio)))
            self.assertEqual(total, ascl_bundle.HEADER_SIZE + len(video) + len(audio))
            self.assertEqual(version, 2)


if __name__ == "__main__":
    unittest.main()
