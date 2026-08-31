import os
import stat
import struct
import sys
import tempfile
import unittest
from unittest import mock


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

    def test_failed_atomic_publish_preserves_previous_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "stable.asclv")
            with open(out_path, "wb") as stream:
                stream.write(b"previous")
            with mock.patch.object(ascl_bundle.os, "replace",
                                   side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    ascl_bundle.pack_bytes(
                        b"ASCL" + bytes((2,)) + b"new", b"audio", out_path)
            with open(out_path, "rb") as stream:
                self.assertEqual(stream.read(), b"previous")
            self.assertFalse(any(name.endswith(".tmp")
                                 for name in os.listdir(directory)))

    @unittest.skipIf(os.name == "nt", "permisos POSIX")
    def test_atomic_publish_preserves_existing_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "served.asclv")
            with open(out_path, "wb") as stream:
                stream.write(b"previous")
            os.chmod(out_path, 0o640)
            ascl_bundle.pack_bytes(
                b"ASCL" + bytes((2,)) + b"new", b"audio", out_path)
            self.assertEqual(stat.S_IMODE(os.stat(out_path).st_mode), 0o640)

    @unittest.skipIf(os.name == "nt", "permisos POSIX")
    def test_new_atomic_publish_honors_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "served.asclv")
            previous_umask = os.umask(0o027)
            try:
                ascl_bundle.pack_bytes(
                    b"ASCL" + bytes((2,)) + b"new", b"", out_path)
            finally:
                os.umask(previous_umask)
            self.assertEqual(stat.S_IMODE(os.stat(out_path).st_mode), 0o640)


class AsclBundleV3Test(unittest.TestCase):
    """F6-3: envelope ASCLVID3 de 20 bytes con meta_len (sidecar embebido)."""

    def test_v3_pack_and_read_with_and_without_meta(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "v3.asclv")
            video = b"ASCL" + bytes((3,)) + b"regional-v3"
            audio = bytes(range(16))
            meta = b"ASCLSLOTmetadata"
            total, video_len, audio_len = ascl_bundle.pack_bytes(
                video, audio, out_path, meta=meta)
            with open(out_path, "rb") as stream:
                bundled = stream.read()
            self.assertEqual(bundled[:8], ascl_bundle.MAGIC_V3)
            self.assertEqual(total, ascl_bundle.HEADER_V3_SIZE +
                             len(video) + len(audio) + len(meta))
            restored = ascl_bundle.read_parts_meta(out_path)
            self.assertEqual(restored, (video, audio, meta, 3))
            # read_parts_info sigue devolviendo la tripla historica.
            self.assertEqual(ascl_bundle.read_parts_info(out_path),
                             (video, audio, 3))

            # Sin meta: header v3 con meta_len 0.
            ascl_bundle.pack_bytes(video, audio, out_path)
            self.assertEqual(ascl_bundle.read_parts_meta(out_path),
                             (video, audio, b"", 3))

    def test_meta_requires_inner_v3(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "bad.asclv")
            for version in (1, 2):
                with self.assertRaisesRegex(ValueError, "meta"):
                    ascl_bundle.pack_bytes(
                        b"ASCL" + bytes((version,)) + b"x", b"", out_path,
                        meta=b"m")

    def test_v3_unpack_writes_slots_file(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = os.path.join(directory, "clip.asclv")
            video = b"ASCL" + bytes((3,)) + b"cells"
            meta = b"ASCLSLOTv2bytes"
            ascl_bundle.pack_bytes(video, b"mp3", out_path, meta=meta)
            ascl_path, audio_path, meta_path = ascl_bundle.unpack(
                out_path, directory)
            self.assertTrue(meta_path.endswith("clip.slots"))
            with open(meta_path, "rb") as stream:
                self.assertEqual(stream.read(), meta)
            with open(ascl_path, "rb") as stream:
                self.assertEqual(stream.read(), video)

    def test_v3_rejects_truncation_mismatch_and_short_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bad.asclv")
            inner_v3 = b"ASCL" + bytes((3,)) + b"x"
            inner_v2 = b"ASCL" + bytes((2,)) + b"x"
            v3_header = struct.pack(
                ascl_bundle.HEADER_V3_FMT, ascl_bundle.MAGIC_V3,
                len(inner_v3), 0, 4)
            cases = [
                # meta_len declara 4 pero solo hay 3 bytes de meta.
                v3_header + inner_v3 + b"met",
                # meta_len declara 4 y hay 5 (bytes extra).
                v3_header + inner_v3 + b"metaX",
                # magic v3 con interior v2.
                struct.pack(ascl_bundle.HEADER_V3_FMT, ascl_bundle.MAGIC_V3,
                            len(inner_v2), 0, 0) + inner_v2,
                # interior v3 dentro de un envelope v2 de 16 bytes.
                struct.pack(ascl_bundle.HEADER_FMT, ascl_bundle.MAGIC_V2,
                            len(inner_v3), 0) + inner_v3,
                # header v3 cortado antes de meta_len.
                struct.pack(ascl_bundle.HEADER_V3_FMT, ascl_bundle.MAGIC_V3,
                            0, 0, 0)[:18],
            ]
            for bundled in cases:
                with open(path, "wb") as stream:
                    stream.write(bundled)
                with self.assertRaises(ValueError):
                    ascl_bundle.read_parts_meta(path)


if __name__ == "__main__":
    unittest.main()
