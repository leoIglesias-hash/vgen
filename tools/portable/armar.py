#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
armar.py - P-008: arma la carpeta portatil `vgen-portable/` (el encoder fuera
del CI, sin instalar nada en Windows).

El bundle es UNA carpeta: Python embebido (el zip oficial, con numpy/Pillow/
OpenCV ya adentro), ffmpeg estatico de Windows, y el MISMO `backend/` +
`tools/` del repo que corre el CI. No toca PATH ni registro: `emitir.ps1`
suma `ffmpeg\\bin` al PATH solo de su proceso. La regla de la maquina del
operador ("sin Python ni Node instalados") se mantiene.

Este script no baja nada: recibe las carpetas ya descomprimidas (el workflow
`portable` las baja, pinneadas por version) y deja:

  vgen-portable/
    emitir.cmd / emitir.ps1   la emision v1 con un doble clic o una linea
    py.cmd                    el interprete embebido con ffmpeg en el PATH
    LEEME.md                  como se usa
    VERSIONES.tsv             commit, fecha, Python, ffmpeg, receta v1
    MANIFEST-portable.tsv     ruta, bytes y SHA-256 de cada archivo
    python/                   el interprete + site-packages
    ffmpeg/bin/               ffmpeg.exe, ffprobe.exe (+ licencias)
    repo/backend/, repo/tools/   solo .py (+ requirements.txt)

El arbitro sigue siendo el CI (ENCODER-PORTATIL.md S4): el workflow emite con
el bundle en un runner de Windows y con Linux la misma receta, y compara los
SHA-256. RECETA_V1 y el master pinneado viven aca y el test los cruza contra
emitir.ps1, el workflow y docs/EMISION-V1.md.
"""

import argparse
import hashlib
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AQUI = os.path.dirname(os.path.abspath(__file__))

# La receta v1 (docs/EMISION-V1.md S3): lo que eligio la matriz H-6.
RECETA_V1 = "--vp9-crf 38 --h264-profile high --h264-crf 23 --h264-bframes 3 --h264-refs 4"

# El master producto (1280@15 v3, con audio), pineado por contenido.
MASTER_URL = "https://iargen.com/player/outputs/clip.dcd6afb66907.asclv"
MASTER_SHA256 = "dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a"

# Lo que viaja del repo: solo codigo. Nada de tests, outputs ni .bat viejos.
REPO_DIRS = ("backend", "tools")
REPO_EXTRA = ("backend/requirements.txt",)
BUNDLE_SCRIPTS = ("emitir.cmd", "emitir.ps1", "py.cmd", "LEEME.md")
MANIFEST_NAME = "MANIFEST-portable.tsv"
VERSIONES_NAME = "VERSIONES.tsv"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _limpio(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)


def copiar_repo(root, out):
    """backend/*.py y tools/*.py (solo el primer nivel) + requirements.txt."""
    copiados = []
    for name in REPO_DIRS:
        src = os.path.join(root, name)
        dst = os.path.join(out, "repo", name)
        os.makedirs(dst)
        for entry in sorted(os.listdir(src)):
            if entry.endswith(".py") and os.path.isfile(os.path.join(src, entry)):
                shutil.copy2(os.path.join(src, entry), os.path.join(dst, entry))
                copiados.append("repo/%s/%s" % (name, entry))
    for rel in REPO_EXTRA:
        shutil.copy2(os.path.join(root, *rel.split("/")),
                     os.path.join(out, "repo", *rel.split("/")))
        copiados.append("repo/" + rel)
    return copiados


def copiar_scripts(out):
    for name in BUNDLE_SCRIPTS:
        shutil.copy2(os.path.join(AQUI, name), os.path.join(out, name))
    return ["%s" % n for n in BUNDLE_SCRIPTS]


def copiar_python(src, out):
    if not os.path.isfile(os.path.join(src, "python.exe")):
        raise SystemExit("armar: %s no tiene python.exe (es el zip embebido descomprimido?)" % src)
    shutil.copytree(src, os.path.join(out, "python"))


def copiar_ffmpeg(src, out):
    """Encuentra ffmpeg.exe/ffprobe.exe donde esten (el zip de ffmpeg trae una
    carpeta con version en el nombre) y deja solo los binarios y licencias."""
    exes = {}
    for base, _dirs, files in os.walk(src):
        for name in files:
            low = name.lower()
            if low in ("ffmpeg.exe", "ffprobe.exe") and low not in exes:
                exes[low] = os.path.join(base, name)
    if "ffmpeg.exe" not in exes:
        raise SystemExit("armar: no hay ffmpeg.exe debajo de %s" % src)
    bin_dir = os.path.join(out, "ffmpeg", "bin")
    os.makedirs(bin_dir)
    for low, path in sorted(exes.items()):
        shutil.copy2(path, os.path.join(bin_dir, low))
    for base, _dirs, files in os.walk(src):
        for name in files:
            if name.lower().startswith(("license", "readme", "copying")):
                shutil.copy2(os.path.join(base, name), os.path.join(out, "ffmpeg", name))
        break  # solo la raiz del zip
    return sorted(exes)


def escribir_versiones(out, commit, fecha, python_version, ffmpeg_version):
    rows = [("commit", commit), ("fecha", fecha), ("python", python_version),
            ("ffmpeg", ffmpeg_version), ("receta_v1", RECETA_V1),
            ("master_url", MASTER_URL), ("master_sha256", MASTER_SHA256)]
    with io.open(os.path.join(out, VERSIONES_NAME), "w", encoding="utf-8", newline="\n") as f:
        for key, value in rows:
            f.write("%s\t%s\n" % (key, value))
    return dict(rows)


def escribir_manifest(out):
    """Ruta (posix, relativa al bundle), bytes y SHA-256 de cada archivo,
    ordenado, para que dos bundles del mismo commit se comparen linea a linea."""
    rows = []
    for base, dirs, files in os.walk(out):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, out).replace(os.sep, "/")
            if rel == MANIFEST_NAME:
                continue
            rows.append((rel, os.path.getsize(path), sha256_of(path)))
    rows.sort()
    with io.open(os.path.join(out, MANIFEST_NAME), "w", encoding="utf-8", newline="\n") as f:
        f.write("archivo\tbytes\tsha256\n")
        for rel, size, digest in rows:
            f.write("%s\t%d\t%s\n" % (rel, size, digest))
    return rows


def armar(python_dir, ffmpeg_dir, out, commit="", fecha="", python_version="",
          ffmpeg_version="", root=ROOT, log=None):
    log = log or (lambda m: None)
    _limpio(out)
    repo = copiar_repo(root, out)
    log("repo: %d archivos" % len(repo))
    copiar_scripts(out)
    copiar_python(python_dir, out)
    log("python: copiado")
    exes = copiar_ffmpeg(ffmpeg_dir, out)
    log("ffmpeg: %s" % ", ".join(exes))
    versiones = escribir_versiones(out, commit, fecha, python_version, ffmpeg_version)
    rows = escribir_manifest(out)
    total = sum(size for _rel, size, _d in rows)
    log("manifest: %d archivos, %d bytes" % (len(rows), total))
    return {"archivos": len(rows), "bytes": total, "versiones": versiones}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", required=True, help="carpeta del Python embebido (con python.exe)")
    parser.add_argument("--ffmpeg", required=True, help="carpeta del zip de ffmpeg descomprimido")
    parser.add_argument("--out", required=True, help="carpeta destino (se recrea)")
    parser.add_argument("--commit", default="")
    parser.add_argument("--fecha", default="")
    parser.add_argument("--python-version", default="")
    parser.add_argument("--ffmpeg-version", default="")
    parser.add_argument("--root", default=ROOT, help="raiz del repo (default: la de este script)")
    args = parser.parse_args(argv)
    result = armar(args.python, args.ffmpeg, args.out, commit=args.commit, fecha=args.fecha,
                   python_version=args.python_version, ffmpeg_version=args.ffmpeg_version,
                   root=args.root, log=lambda m: print("armar: " + m, flush=True))
    print("-- BUNDLE --  %s  %d archivos  %d bytes" % (args.out, result["archivos"], result["bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
