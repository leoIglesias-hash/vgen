import os
import struct
import sys
import tempfile
import unittest
import zlib

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ascl_bundle  # noqa: E402
import ascl_decode  # noqa: E402
import benchmark_quality_v1 as benchmark  # noqa: E402


def tiny_pixel_ascl():
    palette = bytes((0, 0, 0, 255, 255, 255))
    frame0_body = struct.pack("<BH", ascl_decode.TAG_RAW, 2) + palette + bytes((0, 1))
    frame0 = struct.pack("<I", len(frame0_body)) + frame0_body

    # En la grilla de dos celdas cambia solo la segunda: mascara bit 1 + valor 0.
    delta_raw = bytes((0b00000010, 0))
    delta_payload = zlib.compress(delta_raw, 9)
    frame1_body = struct.pack("<BH", ascl_decode.TAG_DELTA_MASK, 0) + delta_payload
    frame1 = struct.pack("<I", len(frame1_body)) + frame1_body

    data_off = ascl_decode.HEADER_SIZE
    table_size = 2 * 4
    offset0 = data_off + table_size
    offset1 = offset0 + len(frame0)
    body = struct.pack("<2I", offset0, offset1) + frame0 + frame1
    crc = zlib.crc32(body) & 0xFFFFFFFF
    header = struct.pack(
        ascl_decode.HEADER_FMT,
        b"ASCL", 1, ascl_decode.MODE_PIXEL, 8, 15,
        2, 1, 2, 2, 0, 3, data_off, 1000, 0, crc)
    return header + body


class BenchmarkQualityV1Test(unittest.TestCase):
    def test_deterministic_sample_indices_include_endpoints(self):
        self.assertEqual(benchmark.deterministic_sample_indices(10, 4), [0, 3, 6, 9])
        self.assertEqual(benchmark.deterministic_sample_indices(4, 0), [0, 1, 2, 3])
        self.assertEqual(benchmark.deterministic_sample_indices(9, 1), [4])

    def test_structural_inspection_counts_tags_crc_changes_and_palette_blocks(self):
        data = tiny_pixel_ascl()
        result = benchmark.inspect_ascl(data)
        self.assertTrue(result["crc"]["ok"])
        self.assertEqual(result["tags"]["RAW"], 1)
        self.assertEqual(result["tags"]["DELTA_MASK"], 1)
        self.assertEqual(result["keyframes"], 1)
        self.assertEqual(result["max_delta_chain"], 1)
        self.assertEqual(result["mean_changed_cells"], 1.5)
        self.assertEqual(result["palette"]["palette_emissions"], 1)
        self.assertEqual(result["palette"]["inferred_block_sizes"], [2])

    def test_load_artifact_uses_bundle_and_reference_decoder(self):
        ascl = tiny_pixel_ascl()
        audio = b"fake-mp3"
        bundle = struct.pack(ascl_bundle.HEADER_FMT, ascl_bundle.MAGIC,
                             len(ascl), len(audio)) + ascl + audio
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "clip.asclv")
            with open(path, "wb") as handle:
                handle.write(bundle)
            loaded = benchmark.load_artifact(path)
            self.assertEqual(loaded["kind"], "asclv")
            self.assertEqual(loaded["ascl_bytes_data"], ascl)
            self.assertEqual(loaded["audio_bytes_data"], audio)
            header, _ramp, cells, palettes = benchmark.decode_reference(
                ascl, path, "asclv")
            self.assertEqual(header["n_frames"], 2)
            self.assertEqual(cells[0][:, 0].tolist(), [0, 1])
            self.assertEqual(cells[1][:, 0].tolist(), [0, 0])
            self.assertEqual(palettes[1].tolist(), [[0, 0, 0], [255, 255, 255]])

    def test_quality_accumulator_is_exact_for_identical_gradient(self):
        gray = np.tile(np.arange(16, dtype=np.uint8) * 8, (8, 1))
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        accumulator = benchmark.QualityAccumulator()
        accumulator.add(rgb, rgb, rgb, rgb, blur_size=5)
        result = accumulator.result()
        self.assertTrue(np.isinf(result["grid_rgb_psnr_db"]))
        self.assertTrue(np.isinf(result["source_bilinear_psnr_db"]))
        self.assertEqual(result["delta_e_ok_mean"], 0.0)
        self.assertEqual(result["banding_plateau_fraction"], 0.0)

    def test_banding_proxy_detects_quantized_plateaus(self):
        gray = np.tile(np.arange(32, dtype=np.uint8) * 4, (8, 1))
        source = np.repeat(gray[:, :, None], 3, axis=2)
        quantized_gray = (gray // 16) * 16
        reconstructed = np.repeat(quantized_gray[:, :, None], 3, axis=2)
        plateau, eligible = benchmark.banding_plateau_counts(source, reconstructed)
        self.assertGreater(eligible, 0)
        self.assertGreater(plateau, 0)
        self.assertGreater(plateau / float(eligible), 0.5)

    def test_player_memory_separates_canvas_and_webgl_texture(self):
        inspection = benchmark.inspect_ascl(tiny_pixel_ascl())
        memory = benchmark.theoretical_player_memory(100, 20, inspection)
        self.assertEqual(memory["matrix_cells_bytes"], 2)
        self.assertEqual(memory["rgba_upload_or_imagedata_bytes"], 8)
        self.assertEqual(memory["canvas_backing_bytes"], 8)
        self.assertEqual(memory["webgl_texture_bytes"], 8)
        self.assertEqual(memory["webgl_lower_bound_bytes"] -
                         memory["canvas2d_lower_bound_bytes"], 8)
        self.assertEqual(memory["canvas2d_with_audio_copy_bytes"] -
                         memory["canvas2d_lower_bound_bytes"], 20)

    def test_external_metadata_keeps_adaptive_diagnostics(self):
        value = {
            "palette_mode": "adaptive",
            "palette_algorithm": "kmeans-oklab",
            "palette_blocks": [
                {"start": 0, "end": 7, "size": 7, "reason": "drift"},
                {"start": 7, "end": 12, "size": 5, "reason": "end"},
            ],
            "unrelated_large_field": [1, 2, 3],
        }
        result = benchmark.summarize_external_metadata(value)
        self.assertEqual(result["palette_blocks_count"], 2)
        self.assertEqual(result["palette_algorithm"], "kmeans-oklab")
        self.assertNotIn("unrelated_large_field", result)


if __name__ == "__main__":
    unittest.main()
