#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark reproducible de calidad/costo para artefactos ASCL/ASCLV v1 y v2.

La herramienta NO codifica. Compara archivos ya generados con el decoder de
referencia y, cuando se indica el video fuente, mide una muestra determinista.

Ejemplos:

  python backend/benchmark_quality_v1.py --source "TKN.mp4" \
    base=outputs/base.asclv candidato=outputs/candidato.asclv

  python backend/benchmark_quality_v1.py --source "TKN.mp4" --samples 0 \
    --decode-repeats 5 --metadata candidato=outputs/candidato.info.json \
    --json-out outputs/benchmark.json --markdown-out outputs/benchmark.md \
    base=outputs/base.asclv candidato=outputs/candidato.asclv

``--samples 0`` mide todos los cuadros. El default (9) reparte los cuadros de
forma uniforme e incluye primero y ultimo. Los PSNR se calculan con MSE RGB
agregado, no promediando dB por cuadro.

DeltaE OK es una aproximacion explicita: 100 por la distancia euclidea Oklab.
No pretende ser DeltaE76/CIEDE2000. El proxy de mesetas cuenta vecinos que se
vuelven iguales en la reconstruccion dentro de gradientes suaves de la fuente;
es experimental y solo debe compararse manteniendo sus umbrales.
"""

import argparse
import contextlib
import gc
import hashlib
import json
import math
import os
import platform
import statistics
import struct
import sys
import tempfile
import time
import zlib

import numpy as np

import ascl_bundle
import ascl_decode
import ascl_v2
import perceptual_palette


TAG_NAMES = {
    ascl_decode.TAG_RAW: "RAW",
    ascl_decode.TAG_ZLIB: "ZLIB",
    ascl_decode.TAG_DELTA: "DELTA",
    ascl_decode.TAG_DELTA_MASK: "DELTA_MASK",
    ascl_decode.TAG_REGIONAL_KEY_RAW: "REGIONAL_KEY_RAW",
    ascl_decode.TAG_REGIONAL_KEY_ZLIB: "REGIONAL_KEY_ZLIB",
    ascl_decode.TAG_REGIONAL_DELTA_RAW: "REGIONAL_DELTA_RAW",
    ascl_decode.TAG_REGIONAL_DELTA_ZLIB: "REGIONAL_DELTA_ZLIB",
    ascl_decode.TAG_PREDICT_KEY_ZLIB: "PREDICT_KEY_ZLIB",
    ascl_decode.TAG_PREDICT_DELTA_ZLIB: "PREDICT_DELTA_ZLIB",
}
KEYFRAME_TAGS = (
    ascl_decode.TAG_RAW,
    ascl_decode.TAG_ZLIB,
    ascl_decode.TAG_REGIONAL_KEY_RAW,
    ascl_decode.TAG_REGIONAL_KEY_ZLIB,
    ascl_decode.TAG_PREDICT_KEY_ZLIB,
)
REGIONAL_RAW_TAGS = (
    ascl_decode.TAG_REGIONAL_KEY_RAW,
    ascl_decode.TAG_REGIONAL_DELTA_RAW,
)
PREDICTOR_ZLIB_TAGS = (
    ascl_decode.TAG_PREDICT_KEY_ZLIB,
    ascl_decode.TAG_PREDICT_DELTA_ZLIB,
)
FLAG_NAMES = {
    0: "LOSSY",
    1: "PAL_PER_SCENE",
    2: "PAL_GLOBAL",
    3: "HAS_OFFSET_TABLE",
    4: "RECON_SOFT",
}


def crc32_hex(data):
    return "%08X" % (zlib.crc32(data) & 0xFFFFFFFF)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest().upper()


def file_checksums(path, chunk_size=1024 * 1024):
    crc = 0
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            digest.update(chunk)
    return {
        "bytes": int(size),
        "crc32": "%08X" % (crc & 0xFFFFFFFF),
        "sha256": digest.hexdigest().upper(),
    }


def psnr_from_mse(mse):
    mse = float(mse)
    if mse <= 0.0:
        return float("inf")
    return 10.0 * math.log10((255.0 * 255.0) / mse)


def format_float(value, digits=3):
    if value is None:
        return "-"
    if math.isinf(float(value)):
        return "inf"
    return ("%%.%df" % int(digits)) % float(value)


def parse_named_path(value):
    """Acepta RUTA o ETIQUETA=RUTA sin confundir el ``C:`` de Windows."""
    if "=" in value:
        label, path = value.split("=", 1)
        label = label.strip()
        path = path.strip()
        if not label or not path:
            raise ValueError("se esperaba ETIQUETA=RUTA: %s" % value)
        return label, path
    path = value
    label = os.path.splitext(os.path.basename(path))[0]
    return label, path


def deterministic_sample_indices(frame_count, sample_count):
    frame_count = int(frame_count)
    sample_count = int(sample_count)
    if frame_count <= 0:
        return []
    if sample_count <= 0 or sample_count >= frame_count:
        return list(range(frame_count))
    if sample_count == 1:
        return [frame_count // 2]
    denominator = sample_count - 1
    # Redondeo entero estable (sin depender del redondeo bancario de float).
    values = [((i * (frame_count - 1) * 2 + denominator) //
               (2 * denominator)) for i in range(sample_count)]
    return sorted(set(int(value) for value in values))


def _flag_labels(flags):
    return [name for bit, name in sorted(FLAG_NAMES.items()) if flags & (1 << bit)]


def load_artifact(path):
    """Carga ASCL/ASCLV y usa ``ascl_bundle`` para separar el bundle."""
    path = os.path.abspath(path)
    with open(path, "rb") as handle:
        artifact = handle.read()
    bundle_magic = artifact[:8]
    if bundle_magic in ascl_bundle.MAGICS:
        if len(artifact) < ascl_bundle.HEADER_SIZE:
            raise ValueError("ASCLV truncado: %s" % path)
        _magic, declared_ascl, declared_audio = struct.unpack_from(
            ascl_bundle.HEADER_FMT, artifact, 0)
        if (ascl_bundle.HEADER_SIZE + declared_ascl + declared_audio !=
                len(artifact)):
            raise ValueError("longitudes declaradas invalidas en ASCLV: %s" % path)
        ascl_bytes, audio_bytes, bundle_version = ascl_bundle.read_parts_info(path)
        kind = "asclv"
    elif artifact.startswith(b"ASCL"):
        ascl_bytes, audio_bytes, kind, bundle_version = artifact, b"", "ascl", None
    else:
        raise ValueError("no es ASCL ni ASCLV: %s" % path)
    if len(ascl_bytes) < ascl_decode.HEADER_SIZE:
        raise ValueError("ASCL truncado: %s" % path)
    ascl_version = int(ascl_decode.parse_header(ascl_bytes)["version"])
    return {
        "path": path,
        "kind": kind,
        "ascl_version": ascl_version,
        "bundle_version": bundle_version,
        "artifact_bytes_data": artifact,
        "ascl_bytes_data": ascl_bytes,
        "audio_bytes_data": audio_bytes,
    }


def _frame_records(ascl_bytes, header):
    n_frames = int(header["n_frames"])
    table_end = int(header["data_off"]) + n_frames * 4
    if table_end > len(ascl_bytes):
        raise ValueError("tabla de offsets fuera del ASCL")
    offsets = struct.unpack_from("<%dI" % n_frames, ascl_bytes, header["data_off"])
    records = []
    for index, offset in enumerate(offsets):
        if offset + 7 > len(ascl_bytes):
            raise ValueError("frame %d fuera del ASCL" % index)
        block_len = struct.unpack_from("<I", ascl_bytes, offset)[0]
        block_end = offset + 4 + block_len
        if block_end > len(ascl_bytes):
            raise ValueError("frame %d truncado" % index)
        tag = ascl_bytes[offset + 4]
        maximum_tag = (ascl_decode.TAG_DELTA_MASK if header["version"] == 1
                       else ascl_decode.TAG_PREDICT_DELTA_ZLIB)
        if tag not in TAG_NAMES or tag > maximum_tag:
            raise ValueError("tag desconocido %d en frame %d" % (tag, index))
        pal_count = struct.unpack_from("<H", ascl_bytes, offset + 5)[0]
        palette_start = offset + 7
        palette_end = palette_start + pal_count * 3
        if palette_end > block_end:
            raise ValueError("paleta truncada en frame %d" % index)
        palette = ascl_bytes[palette_start:palette_end]
        payload = ascl_bytes[palette_end:block_end]
        records.append({
            "index": index,
            "offset": int(offset),
            "block_bytes": int(block_len + 4),
            "tag": int(tag),
            "pal_count": int(pal_count),
            "palette": palette,
            "payload": payload,
        })
    return records


def infer_palette_blocks(records, n_frames):
    """Infiere cambios reales, ignorando reemisiones identicas de keyframes."""
    starts = []
    current_digest = None
    emissions = 0
    unique = set()
    for record in records:
        if record["pal_count"] <= 0:
            continue
        emissions += 1
        digest = sha256_hex(record["palette"])
        unique.add(digest)
        if digest != current_digest:
            starts.append(record["index"])
            current_digest = digest
    blocks = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else int(n_frames)
        blocks.append({"start": int(start), "end": int(end), "size": int(end - start)})
    return {
        "palette_emissions": int(emissions),
        "unique_palette_payloads": int(len(unique)),
        "inferred_change_frames": [int(value) for value in starts],
        "inferred_blocks": blocks,
        "inferred_block_sizes": [item["size"] for item in blocks],
    }


def inspect_ascl(ascl_bytes):
    """Inspeccion estructural, tags, CRC, paletas y costo de inflado."""
    header = ascl_decode.parse_header(ascl_bytes)
    if header["version"] not in (1, 2):
        raise ValueError("version ASCL no soportada: %s" % header["version"])
    if header["mode"] not in ascl_decode.BYTES_PER_CELL:
        raise ValueError("modo ASCL desconocido: %s" % header["mode"])
    computed_crc = ascl_decode.compute_crc(ascl_bytes, header)
    records = _frame_records(ascl_bytes, header)
    n = int(header["cols"]) * int(header["rows"])
    bpc = ascl_decode.BYTES_PER_CELL[header["mode"]]
    changed_v2 = None
    if header["version"] == 2:
        # Valida el stream completo y mide diferencias exactas conservando solo
        # la matriz anterior; el benchmark estructural no acumula todos los frames.
        changed_v2 = []
        previous_cells = None
        for frame in ascl_v2.iter_decoded_v2(ascl_bytes):
            current_cells = frame["cells"]
            changed_v2.append(
                n if frame["keyframe"] else
                int(np.count_nonzero(current_cells != previous_cells)))
            previous_cells = current_cells
    tags = dict((name, 0) for name in TAG_NAMES.values())
    stored_by_tag = dict((name, 0) for name in TAG_NAMES.values())
    changed_total = 0
    max_inflate = 0
    delta_chain = 0
    max_delta_chain = 0
    for record in records:
        name = TAG_NAMES[record["tag"]]
        tags[name] += 1
        stored_by_tag[name] += len(record["payload"])
        tag = record["tag"]
        if tag == ascl_decode.TAG_RAW:
            raw_len = len(record["payload"])
            changed = n
            uses_inflate = False
        elif tag in REGIONAL_RAW_TAGS:
            raw_len = len(record["payload"])
            uses_inflate = False
            if tag in KEYFRAME_TAGS:
                changed = n
            else:
                changed = changed_v2[record["index"]]
        else:
            compressed = record["payload"]
            if tag in PREDICTOR_ZLIB_TAGS:
                if len(compressed) < 2:
                    raise ValueError("PREDICT truncado en frame %d" %
                                     record["index"])
                # El primer byte identifica el predictor y no forma parte del
                # stream zlib de residuales.
                compressed = compressed[1:]
            try:
                raw = zlib.decompress(compressed)
            except zlib.error as exc:
                raise ValueError("zlib invalido en frame %d: %s" %
                                 (record["index"], exc))
            raw_len = len(raw)
            uses_inflate = True
            if tag in (ascl_decode.TAG_ZLIB,
                       ascl_decode.TAG_REGIONAL_KEY_ZLIB,
                       ascl_decode.TAG_PREDICT_KEY_ZLIB):
                changed = n
            elif tag == ascl_decode.TAG_DELTA:
                divisor = 4 + bpc
                if raw_len % divisor:
                    raise ValueError("DELTA invalido en frame %d" % record["index"])
                changed = raw_len // divisor
            elif tag == ascl_decode.TAG_DELTA_MASK:
                mask_len = (n + 7) // 8
                if raw_len < mask_len:
                    raise ValueError("DELTA_MASK invalido en frame %d" % record["index"])
                mask = np.frombuffer(raw, np.uint8, mask_len)
                changed = int(np.unpackbits(mask, bitorder="little", count=n).sum())
                if raw_len != mask_len + changed * bpc:
                    raise ValueError("DELTA_MASK inconsistente en frame %d" % record["index"])
            else:
                changed = changed_v2[record["index"]]
        if uses_inflate and raw_len > max_inflate:
            max_inflate = raw_len
        changed_total += int(changed)
        if tag in KEYFRAME_TAGS:
            delta_chain = 0
        else:
            delta_chain += 1
            max_delta_chain = max(max_delta_chain, delta_chain)
    palette = infer_palette_blocks(records, header["n_frames"])
    crc_present = int(header["crc32"]) != 0
    keyframe_count = sum(tags[TAG_NAMES[tag]] for tag in KEYFRAME_TAGS)
    return {
        "header": dict(header, flags_hex="0x%02X" % header["flags"],
                       flag_names=_flag_labels(header["flags"]),
                       mode_name=ascl_decode.MODE_LABEL.get(header["mode"], "UNKNOWN")),
        "crc": {
            "header": "%08X" % int(header["crc32"]),
            "computed": "%08X" % int(computed_crc),
            "scope": ("body" if header["version"] == 1
                      else "header_without_crc+body"),
            "present": crc_present,
            "ok": ((int(header["crc32"]) == int(computed_crc))
                   if crc_present else None),
        },
        "tags": tags,
        "stored_payload_bytes_by_tag": stored_by_tag,
        "keyframes": int(keyframe_count),
        "full_frame_fraction": (keyframe_count /
                                float(max(1, header["n_frames"]))),
        "max_delta_chain": int(max_delta_chain),
        "mean_changed_cells": changed_total / float(max(1, header["n_frames"])),
        "mean_changed_fraction": changed_total /
                                 float(max(1, header["n_frames"] * n)),
        "max_inflate_bytes": int(max_inflate),
        "palette": palette,
    }


def theoretical_player_memory(artifact_bytes, audio_bytes, inspection):
    """Cotas comparables para el player actual; no pretende medir el heap JS real.

    El ArrayBuffer XHR completo queda residente. Canvas mantiene ImageData RGBA y
    backing store; WebGL agrega una textura RGBA y su drawing buffer. Las tablas JS
    reales usan Arrays y dependen del motor, por lo que se computa solo su contenido
    logico (4 bytes de offset + 1 bit/flag redondeado a un byte por frame).
    """
    header = inspection["header"]
    n = int(header["cols"]) * int(header["rows"])
    bpc = ascl_decode.BYTES_PER_CELL[header["mode"]]
    cells = n * bpc
    rgba = n * 4
    backing = n * 4
    texture = n * 4
    indexes = int(header["n_frames"]) * 5
    palette = int(header["pal_size"]) * 3
    inflate = int(inspection["max_inflate_bytes"])
    common = cells + rgba + backing + indexes + palette + inflate
    canvas_total = int(artifact_bytes) + common
    webgl_total = int(artifact_bytes) + common + texture
    return {
        "download_buffer_bytes": int(artifact_bytes),
        "matrix_cells_bytes": int(cells),
        "rgba_upload_or_imagedata_bytes": int(rgba),
        "canvas_backing_bytes": int(backing),
        "webgl_texture_bytes": int(texture),
        "max_inflate_temporary_bytes": int(inflate),
        "offset_and_key_tables_logical_bytes": int(indexes),
        "palette_bytes": int(palette),
        "canvas2d_lower_bound_bytes": int(canvas_total),
        "webgl_lower_bound_bytes": int(webgl_total),
        "possible_audio_blob_copy_bytes": int(audio_bytes),
        "canvas2d_with_audio_copy_bytes": int(canvas_total + audio_bytes),
        "webgl_with_audio_copy_bytes": int(webgl_total + audio_bytes),
        "notes": [
            "Incluye el ArrayBuffer completo descargado por el player actual.",
            "No incluye overhead de objetos/Arrays del motor JavaScript.",
            "El Blob de audio puede compartir o copiar bytes segun el webview.",
            "La memoria real del canvas/GPU depende del navegador y del compositor.",
        ],
    }


@contextlib.contextmanager
def materialized_ascl(ascl_bytes, original_path, kind):
    if kind == "ascl":
        yield original_path
        return
    handle = tempfile.NamedTemporaryFile(prefix="ascl-benchmark-", suffix=".ascl",
                                         delete=False)
    try:
        handle.write(ascl_bytes)
        handle.close()
        yield handle.name
    finally:
        try:
            os.remove(handle.name)
        except OSError:
            pass


def decode_reference(ascl_bytes, original_path, kind):
    with materialized_ascl(ascl_bytes, original_path, kind) as ascl_path:
        return ascl_decode.decode_all(ascl_path)


def benchmark_reference_decode(ascl_bytes, original_path, kind, repeats=3):
    repeats = int(repeats)
    if repeats <= 0:
        return None
    values = []
    with materialized_ascl(ascl_bytes, original_path, kind) as ascl_path:
        # Warm-up explicito: evita atribuir imports/caches a la primera variante.
        decoded = ascl_decode.decode_all(ascl_path)
        del decoded
        for _ in range(repeats):
            gc.collect()
            start = time.perf_counter()
            decoded = ascl_decode.decode_all(ascl_path)
            values.append((time.perf_counter() - start) * 1000.0)
            del decoded
    frame_count = ascl_decode.parse_header(ascl_bytes)["n_frames"]
    return {
        "method": "ascl_decode.decode_all (incluye lectura local; mediana con warm-up)",
        "repeats": repeats,
        "samples_ms": values,
        "median_total_ms": float(statistics.median(values)),
        "median_ms_per_frame": float(statistics.median(values) /
                                     max(1, int(frame_count))),
    }


def _box_mean(values, size):
    values = np.asarray(values, dtype=np.float64)
    size = int(size)
    if size <= 0 or size % 2 == 0:
        raise ValueError("blur-size debe ser impar y > 0")
    radius = size // 2
    pad = ((radius, radius), (radius, radius))
    if values.ndim == 3:
        pad += ((0, 0),)
    padded = np.pad(values, pad, mode="edge")
    integral_pad = ((1, 0), (1, 0))
    if values.ndim == 3:
        integral_pad += ((0, 0),)
    integral = np.pad(padded, integral_pad, mode="constant")
    integral = np.cumsum(np.cumsum(integral, axis=0), axis=1)
    sums = (integral[size:, size:] - integral[:-size, size:] -
            integral[size:, :-size] + integral[:-size, :-size])
    return sums / float(size * size)


def banding_plateau_counts(source, reconstructed, minimum_gradient=0.5,
                           maximum_gradient=8.0, plateau_threshold=0.5):
    """Devuelve (mesetas, vecinos elegibles) en gradientes suaves de la fuente."""
    source = np.asarray(source, dtype=np.float64)
    reconstructed = np.asarray(reconstructed, dtype=np.float64)
    if source.shape != reconstructed.shape or source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("source/reconstructed deben tener la misma forma HxWx3")
    weights = np.asarray((0.2126, 0.7152, 0.0722), dtype=np.float64)
    source_luma = np.sum(source * weights, axis=2)
    recon_luma = np.sum(reconstructed * weights, axis=2)
    plateau_count = 0
    eligible_count = 0
    for axis in (0, 1):
        source_gradient = np.abs(np.diff(source_luma, axis=axis))
        recon_gradient = np.abs(np.diff(recon_luma, axis=axis))
        eligible = ((source_gradient >= float(minimum_gradient)) &
                    (source_gradient <= float(maximum_gradient)))
        plateau_count += int(np.count_nonzero(eligible &
                                              (recon_gradient < float(plateau_threshold))))
        eligible_count += int(np.count_nonzero(eligible))
    return plateau_count, eligible_count


class QualityAccumulator(object):
    def __init__(self):
        self.grid_sse = 0.0
        self.grid_values = 0
        self.source_sse = 0.0
        self.source_values = 0
        self.low_sse = 0.0
        self.low_values = 0
        self.oklab_sse = 0.0
        self.oklab_pixels = 0
        self.delta_e_sum = 0.0
        self.plateaus = 0
        self.plateau_eligible = 0
        self.frames = 0

    def add(self, source_grid, reconstructed_grid, source_full, reconstructed_full,
            blur_size=5):
        source_grid = np.asarray(source_grid, dtype=np.uint8)
        reconstructed_grid = np.asarray(reconstructed_grid, dtype=np.uint8)
        grid_delta = source_grid.astype(np.int32) - reconstructed_grid.astype(np.int32)
        self.grid_sse += float(np.sum(grid_delta * grid_delta, dtype=np.int64))
        self.grid_values += int(grid_delta.size)

        full_delta = source_full.astype(np.int32) - reconstructed_full.astype(np.int32)
        self.source_sse += float(np.sum(full_delta * full_delta, dtype=np.int64))
        self.source_values += int(full_delta.size)

        source_low = _box_mean(source_grid, blur_size)
        reconstructed_low = _box_mean(reconstructed_grid, blur_size)
        low_delta = source_low - reconstructed_low
        self.low_sse += float(np.sum(low_delta * low_delta))
        self.low_values += int(low_delta.size)

        source_ok = perceptual_palette.srgb_to_oklab(source_grid)
        reconstructed_ok = perceptual_palette.srgb_to_oklab(reconstructed_grid)
        ok_delta = source_ok - reconstructed_ok
        squared = np.sum(ok_delta * ok_delta, axis=2)
        self.oklab_sse += float(np.sum(squared))
        self.oklab_pixels += int(squared.size)
        self.delta_e_sum += float(np.sum(np.sqrt(squared) * 100.0))

        plateau, eligible = banding_plateau_counts(source_grid, reconstructed_grid)
        self.plateaus += plateau
        self.plateau_eligible += eligible
        self.frames += 1

    def result(self):
        grid_mse = self.grid_sse / max(1, self.grid_values)
        source_mse = self.source_sse / max(1, self.source_values)
        low_mse = self.low_sse / max(1, self.low_values)
        return {
            "sampled_frames": int(self.frames),
            "grid_rgb_mse": float(grid_mse),
            "grid_rgb_psnr_db": float(psnr_from_mse(grid_mse)),
            "oklab_mse_per_pixel": float(self.oklab_sse /
                                          max(1, self.oklab_pixels)),
            "delta_e_ok_mean": float(self.delta_e_sum /
                                      max(1, self.oklab_pixels)),
            "low_frequency_rgb_mse": float(low_mse),
            "low_frequency_psnr_db": float(psnr_from_mse(low_mse)),
            "banding_plateau_neighbors": int(self.plateaus),
            "banding_eligible_neighbors": int(self.plateau_eligible),
            "banding_plateau_fraction": (self.plateaus /
                                          float(max(1, self.plateau_eligible))),
            "source_bilinear_rgb_mse": float(source_mse),
            "source_bilinear_psnr_db": float(psnr_from_mse(source_mse)),
        }


def probe_video(path):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("el benchmark contra video requiere opencv-python-headless") from exc
    if not hasattr(cv2, "VideoCapture"):
        raise RuntimeError("la instalacion activa de OpenCV esta incompleta; "
                           "instale opencv-python-headless del backend")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("no se pudo abrir el video fuente: %s" % path)
    result = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": float(cap.get(cv2.CAP_PROP_FPS)),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "opencv_version": cv2.__version__,
    }
    cap.release()
    if result["width"] <= 0 or result["height"] <= 0 or result["fps"] <= 0:
        raise RuntimeError("metadatos invalidos en el video fuente")
    return result


def measure_quality(source_path, source_info, header, cells_list, palettes,
                    sample_indices, blur_size=5):
    import cv2
    source_map = {}
    for output_index in sample_indices:
        source_index = int((float(output_index) * source_info["fps"]) /
                           float(header["fps"]))
        source_map.setdefault(source_index, []).append(output_index)
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        raise RuntimeError("no se pudo abrir el video fuente: %s" % source_path)
    accumulator = QualityAccumulator()
    wanted = set(source_map)
    last_needed = max(wanted) if wanted else -1
    source_index = -1
    while source_index < last_needed:
        ok, bgr = cap.read()
        if not ok:
            break
        source_index += 1
        if source_index not in wanted:
            continue
        source_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        source_grid = cv2.resize(
            source_rgb, (header["cols"], header["rows"]),
            interpolation=cv2.INTER_AREA)
        for output_index in source_map[source_index]:
            reconstructed = ascl_decode.cells_to_rgb(
                header, cells_list[output_index], palettes[output_index])
            reconstructed_full = cv2.resize(
                reconstructed, (source_info["width"], source_info["height"]),
                interpolation=cv2.INTER_LINEAR)
            accumulator.add(source_grid, reconstructed, source_rgb,
                            reconstructed_full, blur_size=blur_size)
        wanted.remove(source_index)
    cap.release()
    if wanted:
        raise RuntimeError("faltan frames fuente: %s" % sorted(wanted))
    result = accumulator.result()
    result.update({
        "sample_indices": [int(value) for value in sample_indices],
        "source_mapping": "floor(output_index * source_fps / ascl_fps)",
        "grid_reference_resize": "OpenCV INTER_AREA",
        "source_reconstruction_resize": "OpenCV INTER_LINEAR (bilinear)",
        "low_frequency_box_size": int(blur_size),
        "delta_e_definition": "100 * distancia euclidea Oklab",
        "banding_proxy_definition": (
            "fraccion de vecinos reconstruidos con delta-luma < 0.5 entre "
            "vecinos fuente con delta-luma 0.5..8.0"),
    })
    return result


def summarize_external_metadata(value):
    if not isinstance(value, dict):
        return {"raw_type": type(value).__name__, "value": value}
    keys = (
        "quality_profile", "palette_mode", "palette_algorithm",
        "palette_block_frames", "palette_block_sizes", "palette_block_reasons",
        "adaptive_min_frames", "adaptive_max_frames",
        "adaptive_change_threshold", "adaptive_hard_cut_threshold",
        "adaptive_stability_max", "perceptual_lut_bits", "dither",
        "dither_matrix", "dither_budget", "dither_min_improvement",
        "dither_window", "dither_changed_cells", "dither_proxy_improvement",
        "bake_smoothing", "reconstruction", "threshold",
    )
    result = dict((key, value[key]) for key in keys if key in value)
    blocks = value.get("palette_blocks")
    if isinstance(blocks, list):
        result["palette_blocks"] = blocks
        result["palette_blocks_count"] = len(blocks)
    return result


def load_metadata_assignments(specs, artifact_labels):
    assigned = {}
    for spec in specs:
        label, path = parse_named_path(spec)
        if "=" not in spec:
            if len(artifact_labels) == 1:
                label = artifact_labels[0]
            elif label not in artifact_labels:
                raise ValueError("con varios artefactos use ETIQUETA=RUTA en --metadata")
        if label not in artifact_labels:
            raise ValueError("metadata para etiqueta desconocida: %s" % label)
        with open(path, "r", encoding="utf-8") as handle:
            assigned[label] = {
                "path": os.path.abspath(path),
                "content": summarize_external_metadata(json.load(handle)),
            }
    return assigned


def benchmark_artifact(label, path, source_path=None, source_info=None,
                       sample_count=9, decode_repeats=3, blur_size=5,
                       external_metadata=None):
    loaded = load_artifact(path)
    inspection = inspect_ascl(loaded["ascl_bytes_data"])
    header = inspection["header"]
    decode_timing = benchmark_reference_decode(
        loaded["ascl_bytes_data"], loaded["path"], loaded["kind"], decode_repeats)
    quality = None
    if source_path:
        decoded_header, _ramp, cells, palettes = decode_reference(
            loaded["ascl_bytes_data"], loaded["path"], loaded["kind"])
        sample_indices = deterministic_sample_indices(
            decoded_header["n_frames"], sample_count)
        quality = measure_quality(source_path, source_info, decoded_header, cells,
                                  palettes, sample_indices, blur_size=blur_size)
    memory = theoretical_player_memory(
        len(loaded["artifact_bytes_data"]), len(loaded["audio_bytes_data"]), inspection)
    result = {
        "label": label,
        "path": loaded["path"],
        "container": loaded["kind"],
        "ascl_version": loaded["ascl_version"],
        "bundle_version": loaded["bundle_version"],
        "sizes": {
            "artifact_bytes": len(loaded["artifact_bytes_data"]),
            "ascl_bytes": len(loaded["ascl_bytes_data"]),
            "audio_bytes": len(loaded["audio_bytes_data"]),
            "bytes_per_second": (len(loaded["artifact_bytes_data"]) /
                                 max(1e-12, header["n_frames"] /
                                     float(header["fps"]))),
        },
        "checksums": {
            "artifact_crc32": crc32_hex(loaded["artifact_bytes_data"]),
            "artifact_sha256": sha256_hex(loaded["artifact_bytes_data"]),
            "ascl_crc32": crc32_hex(loaded["ascl_bytes_data"]),
            "audio_crc32": (crc32_hex(loaded["audio_bytes_data"])
                            if loaded["audio_bytes_data"] else None),
            "ascl_integrity_crc": inspection["crc"],
            # Alias historico del schema v1; en ASCL v2 el alcance tambien
            # incluye el header salvo el propio campo CRC.
            "ascl_body_crc": inspection["crc"],
        },
        "structure": inspection,
        "quality": quality,
        "reference_decode_timing": decode_timing,
        "theoretical_player_memory": memory,
        "external_metadata": external_metadata,
    }
    # No conservar los buffers binarios en el resultado serializable.
    return result


def _mib(value):
    return float(value) / (1024.0 * 1024.0)


def markdown_report(report):
    lines = []
    lines.append("# Benchmark ASCL v1/v2")
    lines.append("")
    if report.get("source"):
        source = report["source"]
        lines.append("Fuente: `%s` (%dx%d, %.6g FPS, CRC32 `%s`)." %
                     (source["path"], source["width"], source["height"],
                      source["fps"], source["crc32"]))
        lines.append("")
    lines.append("| Variante | Grilla | Frames/FPS | MiB | CRC ASCL | Tags R/Z/D/M | Tags regional Kraw/Kz/Draw/Dz | Tags predictor Kz/Dz | Paletas/bloques | PSNR grilla | DeltaE OK | PSNR baja frec. | Mesetas | PSNR fuente bilinear | Decode ms/frame | RAM Canvas min. |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for item in report["artifacts"]:
        header = item["structure"]["header"]
        tags = item["structure"]["tags"]
        palette = item["structure"]["palette"]
        external = item.get("external_metadata") or {}
        external_content = external.get("content") or {}
        block_count = external_content.get(
            "palette_blocks_count", len(palette["inferred_blocks"]))
        quality = item.get("quality") or {}
        timing = item.get("reference_decode_timing") or {}
        crc_status = item["checksums"].get(
            "ascl_integrity_crc", item["checksums"]["ascl_body_crc"])["ok"]
        crc_text = ("OK" if crc_status is True else
                    ("ERROR" if crc_status is False else "ausente"))
        plateau_text = (format_float(quality["banding_plateau_fraction"] * 100.0, 2) + "%"
                        if quality else "-")
        lines.append(
            "| %s | %dx%d | %d/%d | %.2f | %s | %d/%d/%d/%d | %d/%d/%d/%d | %d/%d | %d/%d | %s | %s | %s | %s | %s | %s | %.2f MiB |" %
            (item["label"], header["cols"], header["rows"], header["n_frames"],
             header["fps"], _mib(item["sizes"]["artifact_bytes"]),
             crc_text,
             tags["RAW"], tags["ZLIB"], tags["DELTA"], tags["DELTA_MASK"],
             tags["REGIONAL_KEY_RAW"], tags["REGIONAL_KEY_ZLIB"],
             tags["REGIONAL_DELTA_RAW"], tags["REGIONAL_DELTA_ZLIB"],
             tags["PREDICT_KEY_ZLIB"], tags["PREDICT_DELTA_ZLIB"],
             palette["palette_emissions"], block_count,
             format_float(quality.get("grid_rgb_psnr_db")),
             format_float(quality.get("delta_e_ok_mean")),
             format_float(quality.get("low_frequency_psnr_db")),
             plateau_text,
             format_float(quality.get("source_bilinear_psnr_db")),
             format_float(timing.get("median_ms_per_frame")),
             _mib(item["theoretical_player_memory"]["canvas2d_lower_bound_bytes"])))
    lines.extend((
        "",
        "PSNR mas alto es mejor; DeltaE OK y mesetas son mejores cuanto mas bajos.",
        "La RAM es una cota comparable del player actual: incluye el archivo descargado, "
        "matriz, ImageData, backing de Canvas y pico de inflate; no incluye overhead del motor JS.",
        "DeltaE OK = 100 x distancia Oklab (no es DeltaE76/CIEDE2000). El proxy de mesetas "
        "es experimental y conserva umbrales fijos.",
    ))
    return "\n".join(lines) + "\n"


def _write_text(path, text_value):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text_value)


def json_compatible(value):
    """Convierte infinitos/NaN a texto para producir JSON RFC 8259 estricto."""
    if isinstance(value, dict):
        return dict((key, json_compatible(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        if math.isnan(float(value)):
            return "NaN"
        return "Infinity" if float(value) > 0 else "-Infinity"
    if isinstance(value, np.integer):
        return int(value)
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compara calidad, peso, decode y RAM teorica de ASCL/ASCLV v1/v2.")
    parser.add_argument("artifacts", nargs="+", metavar="[ETIQUETA=]ARTEFACTO")
    parser.add_argument("--source", default=None,
                        help="video fuente; si se omite solo mide estructura/costo")
    parser.add_argument("--samples", type=int, default=9,
                        help="cuadros uniformes por variante; 0=todos (default 9)")
    parser.add_argument("--decode-repeats", type=int, default=3,
                        help="repeticiones cronometradas tras warm-up; 0=omitir")
    parser.add_argument("--blur-size", type=int, default=5,
                        help="ventana impar del PSNR de baja frecuencia (default 5)")
    parser.add_argument("--metadata", action="append", default=[],
                        metavar="[ETIQUETA=]JSON",
                        help="JSON externo del encoder; repetible")
    parser.add_argument("--json-out", default=None, help="guardar resultado completo JSON")
    parser.add_argument("--markdown-out", default=None, help="guardar tabla Markdown")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.samples < 0:
        parser.error("--samples debe ser >= 0")
    if args.decode_repeats < 0:
        parser.error("--decode-repeats debe ser >= 0")
    if args.blur_size <= 0 or args.blur_size % 2 == 0:
        parser.error("--blur-size debe ser impar y > 0")
    try:
        named = [parse_named_path(value) for value in args.artifacts]
        labels = [label for label, _path in named]
        if len(set(labels)) != len(labels):
            raise ValueError("las etiquetas de artefactos deben ser unicas")
        metadata = load_metadata_assignments(args.metadata, labels)
        source_info = None
        source_record = None
        if args.source:
            source_path = os.path.abspath(args.source)
            source_info = probe_video(source_path)
            source_record = dict(source_info, path=source_path,
                                 **file_checksums(source_path))
        artifacts = []
        for label, path in named:
            artifacts.append(benchmark_artifact(
                label, path, source_path=(source_record["path"] if source_record else None),
                source_info=source_info, sample_count=args.samples,
                decode_repeats=args.decode_repeats, blur_size=args.blur_size,
                external_metadata=metadata.get(label)))
        report = {
            "schema": "ascl-quality-benchmark-v1",
            "method": {
                "samples_requested": int(args.samples),
                "decode_repeats": int(args.decode_repeats),
                "blur_size": int(args.blur_size),
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
            "source": source_record,
            "artifacts": artifacts,
        }
        markdown = markdown_report(report)
        sys.stdout.write(markdown)
        if args.json_out:
            _write_text(args.json_out, json.dumps(
                json_compatible(report), indent=2, ensure_ascii=False,
                sort_keys=True, allow_nan=False) + "\n")
        if args.markdown_out:
            _write_text(args.markdown_out, markdown)
    except (OSError, ValueError, RuntimeError, struct.error) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
