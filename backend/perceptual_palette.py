#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paletas perceptuales offline para ASCILINE.

El modulo trabaja enteramente en el procesador que crea el ASCLV. No cambia el
formato ni agrega trabajo al navegador. Sus decisiones son deterministas:

* convierte sRGB a Oklab para medir diferencias como diferencias percibidas;
* sobremuestrea gradientes suaves mediante derivadas numericas (sin IA);
* ajusta K-means con inicializacion de punto mas lejano, sin azar;
* puede conservar el orden y amortiguar el movimiento de la paleta anterior;
* cuantiza exactamente por chunks o mediante una LUT RGB reutilizable.

Las paletas publicas siempre se devuelven como ``uint8`` sRGB, que es exactamente
lo que almacena ASCL v1.
"""

from __future__ import division

import numpy as np


DEFAULT_MAX_SAMPLES = 65536
DEFAULT_CHUNK_SIZE = 4096
DEFAULT_LUT_BITS = 6


def _srgb01(rgb):
    """Valida sRGB y lo normaliza a float64 en el intervalo 0..1."""
    source = np.asarray(rgb)
    if source.ndim < 1 or source.shape[-1] != 3:
        raise ValueError("rgb debe terminar en una dimension de 3 canales")
    if np.issubdtype(source.dtype, np.integer):
        if source.size and (int(source.min()) < 0 or int(source.max()) > 255):
            raise ValueError("rgb entero debe estar entre 0 y 255")
        return source.astype(np.float64) / 255.0
    values = source.astype(np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("rgb contiene valores no finitos")
    if values.size and (float(values.min()) < 0.0 or float(values.max()) > 1.0):
        raise ValueError("rgb flotante debe estar normalizado entre 0 y 1")
    return values


def _as_srgb8(rgb):
    """Normaliza una entrada sRGB valida sin permitir wrap de ``astype(uint8)``."""
    source = np.asarray(rgb)
    if source.dtype == np.uint8:
        if source.ndim < 1 or source.shape[-1] != 3:
            raise ValueError("rgb debe terminar en una dimension de 3 canales")
        return source
    return np.clip(np.rint(_srgb01(source) * 255.0), 0, 255).astype(np.uint8)


def srgb_to_oklab(rgb):
    """Convierte sRGB ``uint8`` (0..255) o flotante (0..1) a Oklab.

    La salida es float64. Mantener float64 en el backend hace reproducibles el
    redondeo final y las comparaciones aun cuando se procesen chunks distintos.
    """
    encoded = _srgb01(rgb)
    linear = np.where(
        encoded <= 0.04045,
        encoded / 12.92,
        np.power((encoded + 0.055) / 1.055, 2.4),
    )
    r = linear[..., 0]
    g = linear[..., 1]
    b = linear[..., 2]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_root = np.cbrt(l)
    m_root = np.cbrt(m)
    s_root = np.cbrt(s)
    return np.stack((
        0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
        1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
        0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
    ), axis=-1)


def _oklab_to_linear_srgb(lab):
    """Transformacion inversa sin clipping ni companding."""
    values = np.asarray(lab, dtype=np.float64)
    light = values[..., 0]
    axis_a = values[..., 1]
    axis_b = values[..., 2]
    l_root = light + 0.3963377774 * axis_a + 0.2158037573 * axis_b
    m_root = light - 0.1055613458 * axis_a - 0.0638541728 * axis_b
    s_root = light - 0.0894841775 * axis_a - 1.2914855480 * axis_b
    l = l_root * l_root * l_root
    m = m_root * m_root * m_root
    s = s_root * s_root * s_root
    return np.stack((
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ), axis=-1)


def oklab_to_srgb(lab, as_uint8=True):
    """Convierte Oklab a sRGB; devuelve ``uint8`` o flotantes 0..1.

    Colores que salen del gamut sRGB se recortan. Los centros de K-means pueden
    hacerlo y el contenedor v1 no tiene forma de representar valores fuera de gamut.
    """
    values = np.asarray(lab, dtype=np.float64)
    if values.ndim < 1 or values.shape[-1] != 3:
        raise ValueError("lab debe terminar en una dimension de 3 canales")
    if not np.all(np.isfinite(values)):
        raise ValueError("lab contiene valores no finitos")
    linear = np.clip(_oklab_to_linear_srgb(values), 0.0, 1.0)
    encoded = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )
    encoded = np.clip(encoded, 0.0, 1.0)
    if not as_uint8:
        return encoded
    return np.clip(np.rint(encoded * 255.0), 0, 255).astype(np.uint8)


def gamut_map_oklab(lab, iterations=16):
    """Lleva colores fuera de sRGB al gamut reduciendo croma, sin girar el tono.

    El clipping RGB independiente puede convertir varios centros Oklab distintos en
    el mismo color de borde. Para las paletas se conserva L y la direccion ``a:b``;
    una busqueda binaria encuentra el mayor croma representable en sRGB.
    """
    values = np.asarray(lab, dtype=np.float64)
    if values.ndim < 1 or values.shape[-1] != 3:
        raise ValueError("lab debe terminar en una dimension de 3 canales")
    if not np.all(np.isfinite(values)):
        raise ValueError("lab contiene valores no finitos")
    iterations = int(iterations)
    if iterations <= 0:
        raise ValueError("iterations debe ser > 0")
    shape = values.shape
    flat = values.reshape(-1, 3).copy()
    # Los centros promedian colores sRGB y ya cumplen 0<=L<=1. El clip hace que la
    # funcion tambien sea segura para llamadas publicas con Oklab arbitrario.
    flat[:, 0] = np.clip(flat[:, 0], 0.0, 1.0)
    linear = _oklab_to_linear_srgb(flat)
    outside = np.any((linear < 0.0) | (linear > 1.0), axis=1)
    if np.any(outside):
        affected = flat[outside].copy()
        low = np.zeros(len(affected), dtype=np.float64)
        high = np.ones(len(affected), dtype=np.float64)
        for _ in range(iterations):
            middle = (low + high) * 0.5
            candidates = affected.copy()
            candidates[:, 1:] *= middle[:, None]
            candidate_linear = _oklab_to_linear_srgb(candidates)
            valid = np.all((candidate_linear >= 0.0) &
                           (candidate_linear <= 1.0), axis=1)
            low = np.where(valid, middle, low)
            high = np.where(valid, high, middle)
        affected[:, 1:] *= low[:, None]
        flat[outside] = affected
    return flat.reshape(shape)


def _smooth_gradient_weights_from_lab(lab, gradient_boost, activity_scale,
                                      edge_scale, curvature_scale):
    """Implementacion que permite reutilizar Oklab durante el muestreo."""
    if float(gradient_boost) < 0.0:
        raise ValueError("gradient_boost debe ser >= 0")
    if min(float(activity_scale), float(edge_scale), float(curvature_scale)) <= 0.0:
        raise ValueError("las escalas de gradiente deben ser > 0")
    height, width = lab.shape[:2]
    derivative = np.zeros_like(lab)
    second = np.zeros_like(lab)
    if width > 1:
        derivative[:, 0] = lab[:, 1] - lab[:, 0]
        derivative[:, -1] = lab[:, -1] - lab[:, -2]
    if width > 2:
        derivative[:, 1:-1] = (lab[:, 2:] - lab[:, :-2]) * 0.5
        second[:, 1:-1] = lab[:, 2:] - 2.0 * lab[:, 1:-1] + lab[:, :-2]
    gradient_squared = np.sum(derivative * derivative, axis=2)
    derivative.fill(0.0)
    if height > 1:
        derivative[0] = lab[1] - lab[0]
        derivative[-1] = lab[-1] - lab[-2]
    if height > 2:
        derivative[1:-1] = (lab[2:] - lab[:-2]) * 0.5
        second[1:-1] += lab[2:] - 2.0 * lab[1:-1] + lab[:-2]
    gradient_squared += np.sum(derivative * derivative, axis=2)
    gradient = np.sqrt(gradient_squared)
    curvature = np.sqrt(np.sum(second * second, axis=2))
    activity = np.clip(gradient / float(activity_scale), 0.0, 1.0)
    edge_guard = 1.0 / (1.0 + (gradient / float(edge_scale)) ** 4)
    smooth_guard = 1.0 / (1.0 + (curvature / float(curvature_scale)) ** 2)
    emphasis = activity * edge_guard * smooth_guard
    return 1.0 + float(gradient_boost) * emphasis


def smooth_gradient_weights(rgb, gradient_boost=3.0,
                            activity_scale=0.020, edge_scale=0.080,
                            curvature_scale=0.012):
    """Calcula pesos espaciales que favorecen gradientes suaves, no bordes.

    Se usan primera y segunda derivada Oklab. Una zona plana conserva peso 1;
    una rampa suave recibe hasta ``1 + gradient_boost``; una discontinuidad fuerte
    se apaga mediante ``edge_guard``. Es analisis numerico O(H*W), sin modelos ni
    reconocimiento de contenido.
    """
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("rgb debe tener forma HxWx3")
    lab = srgb_to_oklab(image)
    return _smooth_gradient_weights_from_lab(
        lab, gradient_boost, activity_scale, edge_scale, curvature_scale)


def _packed_rgb(rgb):
    values = np.asarray(rgb, dtype=np.uint32).reshape(-1, 3)
    return (values[:, 0] << 16) | (values[:, 1] << 8) | values[:, 2]


def _aggregate_rgb(rgb, weights):
    """Colapsa colores identicos conservando exactamente su masa estadistica."""
    keys = _packed_rgb(rgb)
    unique_keys, inverse = np.unique(keys, return_inverse=True)
    aggregate = np.bincount(inverse, weights=np.asarray(weights, dtype=np.float64),
                            minlength=len(unique_keys))
    colors = np.stack(((unique_keys >> 16) & 255,
                       (unique_keys >> 8) & 255,
                       unique_keys & 255), axis=1).astype(np.uint8)
    return colors, aggregate


def _weighted_samples(sample_imgs, max_samples, gradient_boost, min_unique=1):
    pixels = []
    weights = []
    for image in sample_imgs:
        rgb = _as_srgb8(image)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("cada muestra debe tener forma HxWx3")
        if not rgb.size:
            continue
        lab = srgb_to_oklab(rgb)
        pixels.append(np.ascontiguousarray(rgb.reshape(-1, 3)))
        weights.append(_smooth_gradient_weights_from_lab(
            lab, gradient_boost, 0.020, 0.080, 0.012).reshape(-1))
    if not pixels:
        raise ValueError("no hay pixeles para construir la paleta")
    all_pixels = np.concatenate(pixels, axis=0)
    all_weights = np.concatenate(weights, axis=0).astype(np.float64, copy=False)
    wanted = min(int(max_samples), len(all_pixels))
    if wanted <= 0:
        raise ValueError("max_samples debe ser > 0")
    if wanted == len(all_pixels):
        selected_rgb, selected_weights = _aggregate_rgb(all_pixels, all_weights)
        draw_count = len(all_pixels)
    else:
        # Cuantiles equidistantes de la distribucion ponderada. A diferencia de una
        # eleccion aleatoria, el mismo clip produce los mismos pixeles en toda maquina.
        cumulative = np.cumsum(all_weights, dtype=np.float64)
        targets = ((np.arange(wanted, dtype=np.float64) + 0.5) *
                   cumulative[-1] / wanted)
        positions = np.searchsorted(cumulative, targets, side="left")
        positions = np.minimum(positions, len(all_pixels) - 1)
        # Cada extraccion representa la misma masa. Colapsar posiciones repetidas
        # acelera K-means sin deshacer la ponderacion de gradientes.
        unit_mass = cumulative[-1] / wanted
        selected_rgb, selected_weights = _aggregate_rgb(
            all_pixels[positions], np.full(wanted, unit_mass, dtype=np.float64))
        draw_count = wanted

        # Una imagen casi uniforme puede hacer caer muchos cuantiles sobre el mismo
        # color. Si la fuente posee variedad suficiente, agregamos los colores de
        # mayor masa que falten para no inicializar K-means con centros duplicados.
        needed = min(int(min_unique), len(all_pixels)) - len(selected_rgb)
        if needed > 0:
            source_rgb, source_weights = _aggregate_rgb(all_pixels, all_weights)
            selected_keys = set(_packed_rgb(selected_rgb).tolist())
            order = np.argsort(-source_weights, kind="mergesort")
            additions = []
            addition_weights = []
            for source_index in order:
                key = int(_packed_rgb(source_rgb[source_index:source_index + 1])[0])
                if key in selected_keys:
                    continue
                # Reemplaza una repeticion de un color ya elegido, no agrega masa:
                # asi se amplía cobertura sin sesgar el histograma total.
                donor = int(np.argmax(selected_weights))
                if selected_weights[donor] < unit_mass * (1.0 + 1e-12):
                    break
                selected_weights[donor] -= unit_mass
                additions.append(source_rgb[source_index])
                addition_weights.append(float(unit_mass))
                selected_keys.add(key)
                if len(additions) >= needed:
                    break
            if additions:
                selected_rgb = np.concatenate(
                    (selected_rgb, np.asarray(additions, dtype=np.uint8)), axis=0)
                selected_weights = np.concatenate(
                    (selected_weights, np.asarray(addition_weights, dtype=np.float64)))
    return (srgb_to_oklab(selected_rgb), selected_weights,
            {"source_pixel_count": int(len(all_pixels)),
             "sample_draw_count": int(draw_count),
             "unique_sample_count": int(len(selected_rgb))})


def _nearest_indices(lab, palette_lab, chunk_size=DEFAULT_CHUNK_SIZE,
                     return_distance=False):
    values = np.asarray(lab, dtype=np.float64).reshape(-1, 3)
    palette = np.asarray(palette_lab, dtype=np.float64).reshape(-1, 3)
    if not len(palette) or len(palette) > 256:
        raise ValueError("palette debe tener entre 1 y 256 colores")
    chunk_size = int(chunk_size)
    if chunk_size <= 0:
        raise ValueError("chunk_size debe ser > 0")
    result = np.empty(len(values), dtype=np.uint8)
    minimum = np.empty(len(values), dtype=np.float64) if return_distance else None
    for start in range(0, len(values), chunk_size):
        stop = min(start + chunk_size, len(values))
        current = values[start:stop]
        # ||x-p||^2 evita el tensor chunk x palette x 3 del broadcasting. Para
        # chunk=4096 y K=256 baja el temporal principal de ~32 MiB a ~8 MiB.
        distance = -2.0 * np.dot(current, palette.T)
        distance += np.sum(current * current, axis=1)[:, None]
        distance += np.sum(palette * palette, axis=1)[None, :]
        np.maximum(distance, 0.0, out=distance)
        indices = np.argmin(distance, axis=1)
        result[start:stop] = indices.astype(np.uint8)
        if return_distance:
            minimum[start:stop] = distance[np.arange(stop - start), indices]
    if return_distance:
        return result, minimum
    return result


def _initial_centers(samples, weights, count, chunk_size):
    """Inicializacion determinista equivalente a farthest-point ponderado."""
    center_count = int(count)
    centers = np.empty((center_count, 3), dtype=np.float64)
    mean = np.average(samples, axis=0, weights=weights)
    distance = np.sum((samples - mean) ** 2, axis=1)
    first = int(np.argmax(distance * weights))
    centers[0] = samples[first]
    nearest = np.sum((samples - centers[0]) ** 2, axis=1)
    used = {first}
    for index in range(1, center_count):
        score = nearest * weights
        candidate = int(np.argmax(score))
        if candidate in used or float(score[candidate]) <= 0.0:
            # Solo ocurre si hay menos colores unicos que entradas solicitadas.
            # Buscar el siguiente indice libre en lugar de index % len(samples),
            # que podia recaer en un centro ya usado y desperdiciar entradas.
            candidate = index % len(samples)
            while candidate in used and len(used) < len(samples):
                candidate = (candidate + 1) % len(samples)
        used.add(candidate)
        centers[index] = samples[candidate]
        current = np.sum((samples - centers[index]) ** 2, axis=1)
        nearest = np.minimum(nearest, current)
    return centers


def _align_to_previous(centers, previous):
    """Alineacion uno-a-uno estable para conservar el significado de los indices."""
    count = len(centers)
    delta = previous[:, None, :] - centers[None, :, :]
    costs = np.sum(delta * delta, axis=2)
    order = np.argsort(costs, axis=None, kind="mergesort")
    chosen_previous = np.zeros(count, dtype=bool)
    chosen_current = np.zeros(count, dtype=bool)
    aligned = np.empty_like(centers)
    assigned = 0
    for flat in order:
        old_index = int(flat // count)
        new_index = int(flat % count)
        if chosen_previous[old_index] or chosen_current[new_index]:
            continue
        aligned[old_index] = centers[new_index]
        chosen_previous[old_index] = True
        chosen_current[new_index] = True
        assigned += 1
        if assigned == count:
            break
    return aligned


def _repair_palette_duplicates(palette, samples, weights):
    """Recupera entradas que colapsaron al mismo sRGB despues del gamut mapping."""
    repaired = np.asarray(palette, dtype=np.uint8).copy()
    keys = _packed_rgb(repaired)
    seen = set()
    duplicate_slots = []
    for index, key in enumerate(keys):
        numeric_key = int(key)
        if numeric_key in seen:
            duplicate_slots.append(index)
        else:
            seen.add(numeric_key)
    if not duplicate_slots:
        return repaired, 0

    # Los samples nacieron de sRGB; la ida y vuelta reproduce esos colores salvo
    # que sean centroides. El gamut mapping evita clipping agresivo en ambos casos.
    candidate_rgb = oklab_to_srgb(gamut_map_oklab(samples), as_uint8=True)
    candidate_keys = _packed_rgb(candidate_rgb)
    active_indices = [index for index in range(len(repaired))
                      if index not in duplicate_slots]
    active_lab = srgb_to_oklab(repaired[active_indices])
    _nearest, distance = _nearest_indices(
        samples, active_lab, return_distance=True)
    repaired_count = 0
    for slot in duplicate_slots:
        score = distance * weights
        order = np.argsort(-score, kind="mergesort")
        candidate = None
        for sample_index in order:
            key = int(candidate_keys[sample_index])
            if key not in seen:
                candidate = int(sample_index)
                break
        if candidate is None:
            # La fuente no contiene suficientes colores representables distintos.
            continue
        repaired[slot] = candidate_rgb[candidate]
        seen.add(int(candidate_keys[candidate]))
        chosen_lab = srgb_to_oklab(repaired[slot:slot + 1])[0]
        candidate_distance = np.sum((samples - chosen_lab) ** 2, axis=1)
        distance = np.minimum(distance, candidate_distance)
        repaired_count += 1
    return repaired, repaired_count


def build_perceptual_palette(sample_imgs, pal_size, previous_palette=None,
                             temporal_strength=0.0,
                             max_samples=DEFAULT_MAX_SAMPLES,
                             gradient_boost=3.0, max_iter=40, tolerance=1e-5,
                             chunk_size=DEFAULT_CHUNK_SIZE, return_info=False,
                             reserved=0):
    """Construye una paleta K-means en Oklab con muestreo anti-banding.

    ``previous_palette`` debe tener el mismo largo. Su orden se conserva y
    ``temporal_strength`` (0..1) interpola los centros nuevos con los anteriores.
    Cero conserva solo un orden determinista; valores bajos como 0.1..0.25 son un
    punto de partida razonable para evitar parpadeo sin congelar cambios reales.
    ``reserved`` (INT-001) declara cuantas entradas finales quedan fuera del
    video base; con 0 el comportamiento es identico al historico.
    """
    pal_size = int(pal_size)
    if not (1 <= pal_size <= 256):
        raise ValueError("pal_size debe estar entre 1 y 256")
    reserved = int(reserved)
    if reserved < 0:
        raise ValueError("reserved debe ser >= 0")
    if reserved > 0:
        raise NotImplementedError(
            "reserved>0: la exclusion del rango reservado se implementa en E-04")
    max_samples = int(max_samples)
    if max_samples < pal_size:
        raise ValueError("max_samples debe ser >= pal_size")
    temporal_strength = float(temporal_strength)
    if not (0.0 <= temporal_strength <= 1.0):
        raise ValueError("temporal_strength debe estar entre 0 y 1")
    max_iter = int(max_iter)
    if max_iter <= 0:
        raise ValueError("max_iter debe ser > 0")
    if float(tolerance) < 0.0:
        raise ValueError("tolerance debe ser >= 0")
    samples, weights, sampling_info = _weighted_samples(
        sample_imgs, max_samples, gradient_boost, min_unique=pal_size)
    if previous_palette is not None:
        previous_rgb = _as_srgb8(previous_palette)
        if previous_rgb.shape != (pal_size, 3):
            raise ValueError("previous_palette debe tener forma pal_size x 3")
        previous_lab = srgb_to_oklab(previous_rgb)
    else:
        previous_lab = None

    if previous_lab is not None and temporal_strength > 0.0:
        centers = previous_lab.copy()
    else:
        centers = _initial_centers(samples, weights, pal_size, chunk_size)
    iterations = 0
    inertia = 0.0
    for iteration in range(max_iter):
        labels, minimum = _nearest_indices(
            samples, centers, chunk_size=chunk_size, return_distance=True)
        inertia = float(np.sum(minimum * weights))
        counts = np.bincount(labels, weights=weights, minlength=pal_size)
        updated = centers.copy()
        for channel in range(3):
            sums = np.bincount(labels, weights=weights * samples[:, channel],
                               minlength=pal_size)
            occupied = counts > 0.0
            updated[occupied, channel] = sums[occupied] / counts[occupied]
        empty = np.flatnonzero(counts <= 0.0)
        if len(empty):
            used = set()
            reseed_distance = minimum.copy()
            for center_index in empty:
                score = reseed_distance * weights
                if used:
                    score[np.fromiter(used, dtype=np.int64)] = -1.0
                sample_index = int(np.argmax(score))
                used.add(sample_index)
                updated[center_index] = samples[sample_index]
                new_distance = np.sum(
                    (samples - samples[sample_index]) ** 2, axis=1)
                reseed_distance = np.minimum(reseed_distance, new_distance)
        shift = float(np.max(np.sqrt(np.sum((updated - centers) ** 2, axis=1))))
        centers = updated
        iterations = iteration + 1
        if shift <= float(tolerance):
            break

    if previous_lab is not None:
        centers = _align_to_previous(centers, previous_lab)
        if temporal_strength:
            centers = ((1.0 - temporal_strength) * centers +
                       temporal_strength * previous_lab)
    else:
        # El orden no altera el color reconstruido, pero si la estabilidad de los
        # indices y la reproducibilidad de DELTA. L es la clave primaria.
        centers = centers[np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))]
    mapped_centers = gamut_map_oklab(centers)
    gamut_mapped_count = int(np.count_nonzero(np.any(
        np.abs(mapped_centers - centers) > 1e-12, axis=1)))
    palette = oklab_to_srgb(mapped_centers, as_uint8=True)
    palette, repaired_duplicates = _repair_palette_duplicates(
        palette, samples, weights)
    final_palette_lab = srgb_to_oklab(palette)
    _final_indices, final_distance = _nearest_indices(
        samples, final_palette_lab, chunk_size=chunk_size, return_distance=True)
    inertia = float(np.sum(final_distance * weights))
    if not return_info:
        return palette
    info = {
        "sample_count": int(len(samples)),
        "iterations": int(iterations),
        "weighted_inertia": float(inertia),
        "gradient_boost": float(gradient_boost),
        "temporal_strength": float(temporal_strength),
        "gamut_mapped_count": gamut_mapped_count,
        "repaired_duplicates": int(repaired_duplicates),
        "palette_unique_count": int(len(np.unique(_packed_rgb(palette)))),
    }
    info.update(sampling_info)
    return palette, info


def build_perceptual_lut(palette, bits=DEFAULT_LUT_BITS,
                         chunk_size=DEFAULT_CHUNK_SIZE):
    """Crea una LUT RGB->indice para reutilizar durante todo un bloque de paleta."""
    colors = _as_srgb8(palette)
    if colors.ndim != 2 or colors.shape[1] != 3 or not (1 <= len(colors) <= 256):
        raise ValueError("palette debe tener forma Nx3, con 1..256 colores")
    bits = int(bits)
    if not (3 <= bits <= 7):
        raise ValueError("bits debe estar entre 3 y 7")
    levels = 1 << bits
    step = 256.0 / levels
    axis = np.arange(levels, dtype=np.float64) * step + (step - 1.0) * 0.5
    total = levels ** 3
    result = np.empty(total, dtype=np.uint8)
    palette_lab = srgb_to_oklab(colors)
    # No materializamos tres meshgrids float64. Incluso bits=7 conserva memoria
    # acotada por chunk y solo deja residente la LUT final de 2 MiB.
    for start in range(0, total, int(chunk_size)):
        stop = min(start + int(chunk_size), total)
        keys = np.arange(start, stop, dtype=np.uint32)
        blue = keys % levels
        green = (keys // levels) % levels
        red = keys // (levels * levels)
        rgb_grid = np.stack((axis[red], axis[green], axis[blue]), axis=1) / 255.0
        result[start:stop] = _nearest_indices(
            srgb_to_oklab(rgb_grid), palette_lab, chunk_size=chunk_size)
    return result


class PerceptualQuantizer(object):
    """Cuantizador Oklab reutilizable para una paleta ASCL.

    ``lut_bits=None`` (default) usa distancias exactas en chunks para priorizar la
    calidad. Un valor 6 usa una LUT de 262144 bytes y limita el acceso por pixel a
    shifts + lookup. La LUT se construye una sola vez por bloque temporal.
    """

    def __init__(self, palette, lut_bits=None,
                 chunk_size=DEFAULT_CHUNK_SIZE):
        colors = _as_srgb8(palette)
        if colors.ndim != 2 or colors.shape[1] != 3 or not (1 <= len(colors) <= 256):
            raise ValueError("palette debe tener forma Nx3, con 1..256 colores")
        self.palette = np.ascontiguousarray(colors)
        self.palette_lab = srgb_to_oklab(self.palette)
        self.chunk_size = int(chunk_size)
        if self.chunk_size <= 0:
            raise ValueError("chunk_size debe ser > 0")
        self.lut_bits = None if lut_bits is None else int(lut_bits)
        self.lut = None
        if self.lut_bits is not None:
            self.lut = build_perceptual_lut(
                self.palette, self.lut_bits, self.chunk_size)

    def quantize(self, rgb):
        source = np.asarray(rgb)
        if source.ndim < 1 or source.shape[-1] != 3:
            raise ValueError("rgb debe terminar en una dimension de 3 canales")
        if source.dtype == np.uint8:
            image = source
        else:
            # Evita el wrap silencioso de enteros fuera de rango y conserva la API
            # de conversion para entradas flotantes normalizadas.
            image = _as_srgb8(source)
        shape = image.shape[:-1]
        if self.lut is None:
            flat = np.ascontiguousarray(image.reshape(-1, 3))
            indices = np.empty(len(flat), dtype=np.uint8)
            # Convertir Oklab dentro del loop evita que el frame completo y todos
            # los temporales de companding residan juntos en memoria.
            for start in range(0, len(flat), self.chunk_size):
                stop = min(start + self.chunk_size, len(flat))
                indices[start:stop] = _nearest_indices(
                    srgb_to_oklab(flat[start:stop]), self.palette_lab,
                    chunk_size=self.chunk_size)
            return indices.reshape(shape)
        shift = 8 - self.lut_bits
        # uint16 desborda al desplazar el canal rojo con LUT de 6/7 bits.
        # uint32 cubre incluso la clave maxima de 21 bits.
        reduced = np.right_shift(image.astype(np.uint32), shift)
        key = ((reduced[..., 0] << (2 * self.lut_bits)) |
               (reduced[..., 1] << self.lut_bits) |
               reduced[..., 2])
        return self.lut[key]


def quantize_perceptual(rgb, palette, lut_bits=None,
                        chunk_size=DEFAULT_CHUNK_SIZE):
    """Atajo de una llamada; para varios frames conviene ``PerceptualQuantizer``."""
    return PerceptualQuantizer(
        palette, lut_bits=lut_bits, chunk_size=chunk_size).quantize(rgb)
