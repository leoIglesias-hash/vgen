#!/usr/bin/env python3
"""Ejecuta la regresion Python y JavaScript con una sola orden."""
import argparse
import os
import shutil
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_SUITES = (
    "test_frontend_renderers.js",
    "test_reader_bundle_view.js",
    "test_reader_safety.js",
    "test_cache_refresh.js",
    "test_tv_controller.js",
    "test_tv_player_page.js",
    "test_tv_player_runtime.js",
    "test_inflate_fuzz.js",
    "test_inflate_alloc.js",
    "test_reader_v1_seek.js",
    "test_reader_dirty_rect.js",
    "test_reader_v2.js",
    "test_reader_v2_tilesize.js",
    "test_reader_factory.js",
    "test_player_page.js",
    "test_live_player_page.js",
    "test_slots_js.js",
    "test_slots_v2.js",
    "test_overlay_runtime.js",
    "test_overlay_v2_runtime.js",
    "test_overlay_datachannel.js",
    "test_overlay_cross.js",
    "test_overlay_v2_cross.js",
    "test_textlayer.js",
    "test_textfeed.js",
    "test_frontend_compatibility.js",
)


def run(command, environment=None):
    print("+ " + " ".join(command), flush=True)
    subprocess.check_call(command, cwd=ROOT, env=environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=None,
                        help="ruta al ejecutable Node.js (default: node en PATH)")
    parser.add_argument(
        "--require-release-artifact", action="store_true",
        help="falla si outputs/clip.asclv no existe; util antes de publicar un release")
    args = parser.parse_args(argv)

    node = args.node or shutil.which("node")
    if not node:
        parser.error("Node.js no esta en PATH; indique --node RUTA")

    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    python_count = unittest.defaultTestLoader.discover("tests").countTestCases()
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    environment = os.environ.copy()
    if args.require_release_artifact:
        environment["ASCLV_REQUIRE_RELEASE_ARTIFACT"] = "1"
    for suite in JS_SUITES:
        run([node, os.path.join("tests", suite)], environment)

    print("OK: %d pruebas Python y %d suites JavaScript." %
          (python_count, len(JS_SUITES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
