# -*- coding: utf-8 -*-
"""P-008: el bundle portatil se arma con lo que el CI corre, y los pines (la
receta v1, el master) son UNO y estan en los tres lugares que los citan."""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "portable"))

import armar  # noqa: E402


def leer(rel):
    with io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def escribir(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class ArmarTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vgen-portable-")
        self.py = os.path.join(self.tmp, "py")
        self.ff = os.path.join(self.tmp, "ff")
        self.out = os.path.join(self.tmp, "bundle")
        escribir(os.path.join(self.py, "python.exe"), b"MZpython")
        escribir(os.path.join(self.py, "python311._pth"), b"python311.zip\n.\nimport site\n")
        escribir(os.path.join(self.py, "Lib", "site-packages", "numpy", "__init__.py"), b"")
        escribir(os.path.join(self.ff, "ffmpeg-7.1.1-essentials_build", "bin", "ffmpeg.exe"), b"MZff")
        escribir(os.path.join(self.ff, "ffmpeg-7.1.1-essentials_build", "bin", "ffprobe.exe"), b"MZfp")
        escribir(os.path.join(self.ff, "ffmpeg-7.1.1-essentials_build", "bin", "ffplay.exe"), b"MZno")
        escribir(os.path.join(self.ff, "LICENSE"), b"gpl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _manifest(self):
        rows = {}
        with io.open(os.path.join(self.out, armar.MANIFEST_NAME), encoding="utf-8") as f:
            header = f.readline().rstrip("\n").split("\t")
            for line in f:
                rel, size, digest = line.rstrip("\n").split("\t")
                rows[rel] = (int(size), digest)
        self.assertEqual(header, ["archivo", "bytes", "sha256"])
        return rows

    def test_arma_la_carpeta_con_el_mismo_codigo_que_el_ci(self):
        result = armar.armar(self.py, self.ff, self.out, commit="abc123", fecha="2026-09-06",
                             python_version="3.11.9", ffmpeg_version="ffmpeg version 7.1.1")
        for rel in ("emitir.cmd", "emitir.ps1", "py.cmd", "LEEME.md", "VERSIONES.tsv",
                    armar.MANIFEST_NAME, "python/python.exe", "python/python311._pth",
                    "python/Lib/site-packages/numpy/__init__.py",
                    "ffmpeg/bin/ffmpeg.exe", "ffmpeg/bin/ffprobe.exe", "ffmpeg/LICENSE",
                    "repo/backend/encoder.py", "repo/backend/ascl_decode.py",
                    "repo/backend/requirements.txt", "repo/tools/emit_v1.py",
                    "repo/tools/emit_pieces.py", "repo/tools/emit_matrix.py"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, *rel.split("/"))), rel)
        # Solo binarios y licencias de ffmpeg; nada del repo que no sea codigo.
        self.assertFalse(os.path.exists(os.path.join(self.out, "ffmpeg", "bin", "ffplay.exe")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "repo", "tests")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "repo", "backend",
                                                     "generar_1080_y_variantes.bat")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "repo", "tools", "portable")))
        self.assertEqual(result["versiones"]["commit"], "abc123")
        self.assertEqual(result["versiones"]["receta_v1"], armar.RECETA_V1)

    def test_el_manifest_tiene_el_sha_real_de_cada_archivo(self):
        armar.armar(self.py, self.ff, self.out)
        rows = self._manifest()
        self.assertNotIn(armar.MANIFEST_NAME, rows)
        real = os.path.join(ROOT, "tools", "emit_v1.py")
        with open(real, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(rows["repo/tools/emit_v1.py"], (os.path.getsize(real), digest))
        self.assertEqual(rows["python/python.exe"][1], hashlib.sha256(b"MZpython").hexdigest())
        self.assertEqual(sorted(rows), list(rows), "el manifest va ordenado")

    def test_versiones_es_tsv_con_los_pines(self):
        armar.armar(self.py, self.ff, self.out, commit="c0ffee", fecha="2026-09-06",
                    python_version="3.11.9", ffmpeg_version="ffmpeg version 7.1.1")
        with io.open(os.path.join(self.out, armar.VERSIONES_NAME), encoding="utf-8") as f:
            rows = dict(line.rstrip("\n").split("\t", 1) for line in f if line.strip())
        self.assertEqual(rows["commit"], "c0ffee")
        self.assertEqual(rows["python"], "3.11.9")
        self.assertEqual(rows["master_sha256"], armar.MASTER_SHA256)
        self.assertEqual(rows["receta_v1"], armar.RECETA_V1)

    def test_falla_claro_sin_python_o_sin_ffmpeg(self):
        with self.assertRaises(SystemExit):
            armar.armar(os.path.join(self.tmp, "nada"), self.ff, self.out)
        with self.assertRaises(SystemExit):
            armar.armar(self.py, os.path.join(self.tmp, "nada"), self.out)


class PinesTest(unittest.TestCase):
    """La receta v1 y el master pineado se citan en emitir.ps1, en el workflow y
    en EMISION-V1.md: si uno cambia solo, este test lo dice."""

    def test_receta_v1_es_la_de_emision_v1(self):
        self.assertIn("```\n%s\n```" % armar.RECETA_V1, leer("docs/EMISION-V1.md"))

    def test_emitir_ps1_trae_los_mismos_pines(self):
        ps1 = leer("tools/portable/emitir.ps1")
        self.assertIn('[string]$Receta = "%s"' % armar.RECETA_V1, ps1)
        self.assertIn('[string]$Master = "%s"' % armar.MASTER_URL, ps1)
        self.assertIn('[string]$Sha256 = "%s"' % armar.MASTER_SHA256, ps1)
        self.assertIn("-ExecutionPolicy Bypass", leer("tools/portable/emitir.cmd"))
        self.assertIn("python\\python.exe", leer("tools/portable/py.cmd"))

    def test_el_workflow_portable_pinea_lo_mismo(self):
        yml = leer(".github/workflows/portable.yml")
        self.assertIn('default: "%s"' % armar.RECETA_V1, yml)
        self.assertIn('default: "%s"' % armar.MASTER_URL, yml)
        self.assertIn('default: "%s"' % armar.MASTER_SHA256, yml)
        self.assertIn("tools/portable/armar.py", yml)
        self.assertIn("windows-latest", yml)
        self.assertIn("ubuntu-latest", yml)


if __name__ == "__main__":
    unittest.main()
