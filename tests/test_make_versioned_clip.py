import os
import re
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import make_versioned_clip  # noqa: E402


class MakeVersionedClipTest(unittest.TestCase):
    """CACHE-001 (F6-4): nombre por contenido + puntero de texto plano."""

    def write_clip(self, directory, payload):
        path = os.path.join(directory, "clip.asclv")
        with open(path, "wb") as stream:
            stream.write(payload)
        return path

    def test_installs_byte_identical_copy_and_pointer(self):
        payload = b"ASCLVID2" + bytes(range(64))
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_clip(directory, payload)
            name, digest = make_versioned_clip.install_versioned(path)
            self.assertRegex(name, r"^clip\.[0-9a-f]{12}\.asclv$")
            self.assertEqual(name, "clip.%s.asclv" % digest[:12])
            with open(os.path.join(directory, name), "rb") as stream:
                self.assertEqual(stream.read(), payload)
            with open(os.path.join(directory, "clip.current.txt")) as stream:
                pointer = stream.read()
            lines = [line for line in pointer.splitlines()
                     if line and not line.startswith("#")]
            self.assertEqual(lines, [name])
            self.assertIn("sha256=%s" % digest, pointer)
            # El formato del puntero es EXACTAMENTE el que valida el frontend
            # (cache-refresh.js::parseClipPointer): una linea clip.<hex>.asclv.
            self.assertTrue(re.match(r"^clip\.[0-9a-f]{8,64}\.asclv$", lines[0]))

    def test_is_deterministic_and_content_addressed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_clip(directory, b"ASCLVID3" + b"\x00" * 40)
            first = make_versioned_clip.install_versioned(path)
            second = make_versioned_clip.install_versioned(path)
            self.assertEqual(first, second)
            # Contenido distinto => nombre distinto (invalidacion por nombre).
            other = self.write_clip(directory, b"ASCLVID3" + b"\x01" * 40)
            self.assertNotEqual(make_versioned_clip.install_versioned(other)[0],
                                first[0])

    def test_rejects_non_bundle_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_clip(directory, b"NO-ES-UN-BUNDLE")
            with self.assertRaisesRegex(ValueError, "magic"):
                make_versioned_clip.install_versioned(path)


if __name__ == "__main__":
    unittest.main()
