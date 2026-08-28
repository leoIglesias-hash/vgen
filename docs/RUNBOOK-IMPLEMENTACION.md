# Runbook de implementación

Estado: ejecutable, 2026-08-27. Se sigue en orden.

Este documento no argumenta ni justifica: para eso están
[`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) y
[`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md). Acá está qué
tocar, en qué orden, cómo verificarlo y cuándo una tarea se considera cerrada.

Toda referencia `archivo:línea` fue verificada contra el árbol al 2026-08-27. Si una línea
no coincide, el código cambió: verificar antes de editar.

## 0. Reglas de ejecución

1. **Dos ramas.** `feature/opt-encoder` y `feature/opt-frontend`. Ningún commit mezcla
   carriles. Un merge a la rama base solo ocurre en un punto de sincronización.
2. **Un commit por tarea.** Mensaje: `<ID>: <título de la tarea>`. Si una tarea necesita
   varios commits, todos llevan el mismo ID.
3. **Regresión antes de cerrar.** `python tests/run_all.py` en verde. Sin excepciones.
4. **Fila de registro obligatoria** para toda tarea marcada Δbytes. Plantilla en §6.
5. **Una tarea no empieza si su precondición no está cerrada.** Las precondiciones están
   escritas en cada tarea; no hay atajos aunque parezcan independientes.
6. **Ninguna tarea se cierra "porque compila".** El criterio de cierre está escrito y es
   verificable.
7. **Todo test nuevo se cablea en el mismo commit.** Un test JavaScript nuevo se registra
   en `tests/run_all.py` y queda cubierto por el workflow de CI. Un test que existe pero
   no corre en la regresión no cuenta como test.
8. **Procedencia del código por sesión.** Al iniciar una sesión de trabajo se anota en
   `RUNBOOK-ESTADO.md` sobre qué commit o snapshot se trabaja. Las referencias
   `archivo:línea` de este runbook corresponden al árbol del 2026-08-27: ante cualquier
   duda, se localiza por el nombre de función o el fragmento citado, nunca por el número
   de línea a ciegas.

## 1. Preparación

### P-01 — Ramas y línea base

```bash
git checkout -b feature/opt-encoder
git checkout -b feature/opt-frontend
python tests/run_all.py          # debe pasar antes de tocar nada
```

**Cierre:** ambas ramas creadas desde el mismo commit; regresión en verde; commit base
anotado en el registro.

### P-02 — Congelar las dos referencias de medición

Se usan dos clips, no uno:

| Referencia | Origen | Uso |
|---|---|---|
| `synthetic` | `inputs/synthetic.mp4`, en el repo | medición reproducible en cualquier clon y en CI |
| `HQ` | `outputs/clip.asclv` local | cifras reales del perfil de producción |

`HQ` no se puede regenerar sin conservar su V1 autorizado. Se congela **su binario y su
SHA-256** antes de tocar el encoder, y se conserva intacto hasta F8.

```bash
sha256sum outputs/clip.asclv
cp outputs/clip.asclv outputs/clip.baseline.asclv
python backend/make_clip.py inputs/synthetic.mp4 --format v2 \
  --out outputs/synthetic.baseline.asclv --cols 64 --fps 10 \
  --palette global --palette-size 32
sha256sum outputs/synthetic.baseline.asclv
```

**Cierre:** ambos SHA-256 anotados en el registro con commit y parámetros exactos.

### P-03 — Herramienta de medición

Crear `tools/bench_ref.py`. Dado un `.asclv`, imprime en una línea de tabla Markdown:

- bytes `.ascl` y `.asclv`, bytes por celda;
- distribución de tags;
- cantidad de keyframes y longitud máxima de cadena delta;
- PSNR RGB y error Oklab contra el original cuando se le pasa la fuente;
- SHA-256.

Esta herramienta es la que hace cumplible la regla 4. Sin ella, la disciplina de medición
se abandona en la tercera tarea.

**Cierre:** `python tools/bench_ref.py outputs/synthetic.baseline.asclv` imprime la fila
base; la salida es determinista entre dos corridas.

### P-04 — Zopfli como dependencia opcional

```bash
pip install zopfli
```

Agregar a `backend/requirements.txt` como **opcional**: si el import falla, el encoder cae
a `zlib` y lo informa por CLI. Un clon limpio y CI deben seguir funcionando sin Zopfli.

**Cierre:** `python tests/run_all.py` pasa con y sin `zopfli` instalado.

---

## 2. Carril E — encoder

### E-01 — `_kmeans_rgb_palette` no ordena en la rama OpenCV

- **Precondición:** P-03.
- **Archivo:** `backend/encoder.py:252-283`.
- **Acción:** el `lexsort` de la línea 248 vive dentro de `_kmeans_rgb_numpy`. Sacarlo a
  `_kmeans_rgb_palette` y aplicarlo a los centros de **ambas** ramas antes de devolver: la
  de OpenCV (línea 282) y la del fallback NumPy (línea 283).
- **Verificación:**

```bash
python -c "import cv2"                       # confirmar que hay cv2
python backend/make_clip.py inputs/synthetic.mp4 --out /tmp/a.asclv \
  --palette-algorithm kmeans-rgb --cols 64 --fps 10 --palette-size 32
# repetir en un entorno sin cv2 (o con ImportError forzado)
sha256sum /tmp/a.asclv /tmp/b.asclv
```

- **Cierre:** SHA-256 idéntico con y sin OpenCV. Test nuevo que fuerza ambas ramas y
  compara la paleta byte a byte. Δbytes: sí, fila de registro.

> Esta es la primera tarea del carril por un motivo: hasta que cierre, ninguna medición
> posterior compara contra una base reproducible.

### E-02 — Endurecer las herramientas offline

- **Precondición:** E-01.
- **Archivos y acciones:**

| Archivo | Línea | Acción |
|---|---|---|
| `encoder.py` | 681 | `src_fps` rechaza NaN y valores absurdos: `if not (0 < src_fps < 1000): src_fps = target_fps` |
| `encoder.py` | 719-745 | `encode_image` rechaza explícitamente un `palette_mode` distinto de `per-frame` en vez de ignorarlo |
| `perceptual_palette.py` | 347-357 | `_initial_centers` busca el siguiente índice no usado en lugar de `index % len(samples)` |
| `ascl_decode.py` | 101-185 | delegar el camino v1 en `ascl_v2._decode_v1_payload`; abortar si `crc_ok` es falso; validar `pal_count`, offsets contiguos e índices contra la paleta |
| `ascl_decode.py` | 218 | resolver `ffmpeg` con la misma lógica de `encoder.extract_audio` (`shutil.which` + `imageio_ffmpeg`) |
| `ascl_bundle.py` | 100 | leer y validar el header contra `os.path.getsize` antes de cargar el archivo entero |
| `ascl_bundle.py` | 35-40 | `_publish_mode` también captura `PermissionError` |

- **Verificación:** fixtures corruptos nuevos para cada validación agregada a
  `ascl_decode.py`; `python tests/run_all.py`.
- **Cierre:** un `.ascl` corrupto **falla** en `ascl_decode.py` en vez de decodificar.
  E-01 y E-02 juntos cierran la fase F0 del lado encoder. Δbytes: solo `perceptual_palette`
  (fila de registro).

### E-03 — Parámetro `reserved` cableado, default 0

- **Precondición:** E-02.
- **Archivos:** `backend/encoder.py`, `backend/perceptual_palette.py`.
- **Acción:** agregar `reserved` (entero, default `0`) y propagarlo por la cadena de
  construcción de paleta. Con `reserved=0` el comportamiento debe ser **byte-idéntico** al
  actual. Exigir `pal_size >= reserved + 22`.
- **Cierre:** con `reserved=0`, SHA-256 idéntico a la referencia de P-02. Δbytes: no.

### E-04 — Exclusión del rango reservado en las ocho funciones

- **Precondición:** E-03.
- **Archivos y líneas** (las ocho de `DISENO-INTERVENCION-MATRICIAL.md` §4.2):

| Función | Archivo:línea |
|---|---|
| `make_global_palette` | `encoder.py:286` |
| `_kmeans_rgb_numpy` / `_kmeans_rgb_palette` | `encoder.py:214,252` |
| `build_perceptual_palette` | `perceptual_palette.py:472` |
| `_repair_palette_duplicates` | `perceptual_palette.py:384` |
| `gamut_map_oklab` | `perceptual_palette.py:125` |
| `_align_to_previous` | `perceptual_palette.py:360` |
| `quantize_palette_rgb` | `encoder.py:466` |
| `frame_to_cells` | `encoder.py:498` |

- **Acción:** el cuantizador construye `pal_size - reserved` colores; las reservadas se
  estampan al final. Ninguna de las funciones de la tabla puede mover, reemplazar ni
  reasignar un índice `>= pal_size - reserved`. `quantize_palette_rgb` no puede elegirlos
  para el video base (INV-3).
- **Verificación:** test que corre las cuatro estrategias de paleta y los cuatro modos
  sobre un clip adaptativo y afirma, para cada época, que las `reserved` entradas finales
  son bit-idénticas y que ninguna celda base las usa.
- **Cierre:** el test anterior en verde con `reserved=10`. Δbytes: sí con `reserved>0`.

### E-05 — Rects protegidos en el dither

- **Precondición:** E-04.
- **Archivo:** `backend/dither.py:696-726` (`apply_selective_dither`) y `172` (`selective_tile_mask`).
- **Acción:** aceptar una lista de rectángulos y sumarlos a la máscara `protected` ya
  existente (`selected &= ~protected`, línea 237).
- **Cierre:** test que verifica que ninguna celda dentro de un rect declarado fue
  modificada por el dither. Δbytes: no (sin rects declarados).

### E-06 — Horneado de glifos

- **Precondición:** E-04.
- **Archivo:** herramienta nueva, `tools/bake_glyphs.py`.
- **Acción:** render de los dígitos `0..9` desde una fuente, downsample a
  `glyph_w x glyph_h` celdas, cuantización del antialias a los niveles reservados
  `247..250`, más el glifo vacío (índice `255`, transparente).
- **Cierre:** dos corridas producen bytes idénticos. Salida visualmente inspeccionada una
  vez y anotada.

### E-07 — Generador y validador de sidecar `ASCLSLOT`

- **Precondición:** E-06.
- **Archivo:** `tools/make_slots.py` (Python) y `frontend/slots.js` (validador ES5).
- **Acción:** estructura binaria de `DISENO-INTERVENCION-MATRICIAL.md` §7.1, con las siete
  restricciones de §6.3.
- **Verificación:** un fixture negativo por restricción: rect fuera de grilla, solapamiento,
  `n_slots` excedido, área excedida, byte de glifo fuera de `246..255`, `slot_id`
  inexistente, `slot_id` en dos campos, `reserved_rgb` que no coincide con el bundle.
- **Cierre:** los ocho fixtures rechazados; ninguno produce carga parcial. **Cierra F1.**

### E-08 — Zopfli en los cinco puntos, simultáneo

- **Precondición:** E-01, P-04. **No parcial**: los tres archivos en el mismo commit.
- **Archivos:** `encoder.py:569,581,584`; `ascl_v2.py:338`; `regional_codec_v2.py:322`.
- **Acción:** reemplazar cada `zlib.compress(x, N)` por el menor entre `zlib` y Zopfli:

```python
def _best_deflate(data, level=9, iterations=ZOPFLI_ITERATIONS):
    a = zlib.compress(data, level)
    if zopfli is None:
        return a
    b = zopfli.zlib.compress(data, numiterations=iterations)
    return b if len(b) < len(a) else a
```

- **Trampa a evitar:** `ascl_v2.transcode_ascl_bytes` compara el candidato v2 contra el
  payload v1 heredado. Ambos lados deben usar el mismo compresor o v2 pierde por asimetría
  de herramienta. Verificarlo explícitamente.
- **Verificación:** `python tools/bench_ref.py` sobre ambas referencias; el reader
  JavaScript abre los archivos nuevos sin cambios (`inflate.js` acepta el stream zlib
  estándar que produce Zopfli).
- **Cierre:** ahorro medido y registrado por tipo de payload; `bytes(v2) <= bytes(v1)`
  sigue verificado; regresión en verde con y sin Zopfli instalado. Δbytes: sí.

### E-09 — `tile_size` parametrizado y búsqueda exhaustiva

- **Precondición:** E-08.
- **Archivos:** `ascl_v2.py:57` (`DEFAULT_TILE_SIZE`), `123-124` (geometría), `137`
  (validación), `456,462-463` (`transcode_ascl_bytes`).
- **Acción:** tres puntos a parametrizar, no dos: la constante, el cálculo de
  `tile_cols`/`tile_rows` y las dos validaciones. `regional_codec_v2._geometry` ya es
  genérico (acepta 1..256) y no se toca. Emitir el ganador en el byte 26 del header.
  Barrer `{4, 8, 12, 16, 24, 32}` por archivo y quedarse con el menor.
- **Bloqueo:** el archivo resultante **no abre** hasta que W-08 esté integrado. Generar los
  artefactos con `tile_size` distinto de 16 solo después del punto de sincronización S-2.
- **Cierre:** ahorro por `tile_size` registrado sobre ambas referencias; decoder Python
  round-trip exacto en todos los tamaños barridos. Δbytes: sí.
- **Nota de alcance:** el ganador elegido acá es **provisional**. El trellis espacial
  (E-23) cambia la estadística de colores por tile, así que el barrido definitivo se
  repite en S-4, al generar los artefactos finales. E-09 entrega el mecanismo; S-4 fija
  el valor.

### E-10 — Keyframes en cortes de escena y GOP variable

- **Precondición:** E-09 **y W-02 integrado** (regla C-2 del plan: alargar el GOP sin el
  atajo a keyframe empeora la reproducción en el equipo más lento).
- **Archivos:** `encoder.py:892` (`need_color_descriptor`), `903` (`hard_cut`), `908`
  (decisión de keyframe), `1088` (`keyint`).
- **Acción, en este orden:**
  1. `need_color_descriptor` debe ser verdadero también cuando se pide keyframes por corte,
     aunque el modo de paleta no sea adaptativo. **Sin esto, `hard_cut` es siempre falso en
     `--palette global` y `block`, y el cambio no hace nada.**
  2. línea 908: `keyframe = (idx == 0) or block_start or hard_cut or (keyint > 0 and idx % keyint == 0)`.
  3. exponer `--keyint` mayor para permitir GOPs largos entre cortes.
- **Verificación:** contar keyframes antes y después; verificar que cada corte detectado
  tiene su keyframe; medir la longitud máxima de cadena delta.
- **Cierre:** bytes y longitud máxima de cadena registrados; seek verificado en ambas
  direcciones contra el decoder Python. Δbytes: sí.

### E-11 — Flags de audio (OPCIONAL)

- **Precondición:** E-08. **Opcional**: no bloquea ninguna otra tarea y puede saltearse o
  hacerse en cualquier momento. En el HQ el audio es el 1% del bundle; solo importa en
  perfiles de 320 columnas.
- **Archivo:** `encoder.py:656-659`.
- **Acción:** exponer `--audio-bitrate`, `--audio-mono` y `--audio-samplerate`. Default sin
  cambios (`-q:a 4`).
- **Cierre:** el default produce audio byte-idéntico al actual. Δbytes: sí, solo si se usan.

> **E-08 a E-10 cierran F2.** E-11 es opcional y no forma parte del gate.

### E-12 — Refit de paleta a la asignación real

- **Precondición:** E-04 (exclusión del rango reservado).
- **Archivo:** `encoder.py:466` (`quantize_palette_rgb`), `498` (`frame_to_cells`).
- **Acción:** tras cuantizar, recalcular cada entrada como la media de los píxeles reales
  asignados (`np.bincount`), 3-5 iteraciones. Excluir los índices reservados.
- **Cierre:** PSNR y error Oklab registrados; solo cambian los bytes de paleta, la
  estructura del frame no. Δbytes: sí.

### E-13 — Cerrar Lloyd en dominio uint8

- **Precondición:** E-12.
- **Archivo:** `perceptual_palette.py:472-521`.
- **Acción:** tras `gamut_map_oklab` (512), `oklab_to_srgb` (515) y
  `_repair_palette_duplicates` (516), iterar 2-5 veces más restringido a valores sRGB
  representables: asignar, promediar, redondear, y **aceptar solo si baja la inercia**.
- **Cierre:** inercia final menor o igual a la actual en todas las referencias; determinismo
  verificado. Δbytes: sí.

### E-14 — Paleta sobre todos los píxeles, en dos pasadas

- **Precondición:** E-13.
- **Archivos:** `perceptual_palette.py:234-305` (`_weighted_samples`), `encoder.py:829`
  (`allf = list(...)`).
- **Acción:** una sola tarea para dos problemas. Primera pasada: recorrer el video
  agregando colores únicos con `_aggregate_rgb` (ya existe y colapsa idénticos sin perder
  masa). Segunda pasada: codificar. Elimina el límite de 65.536 muestras **y** el
  materializado completo en RAM.
- **Verificación:** medir RSS máximo con `graphic-ultra` sobre un clip de 90 s; hoy son
  ~2,8 GB.
- **Cierre:** RSS máximo acotado y registrado; PSNR igual o mejor. Δbytes: sí.

### E-15 — Estabilidad temporal para los cuatro algoritmos

- **Precondición:** E-14.
- **Archivo:** `encoder.py:286-320` (`make_global_palette`), `perceptual_palette.py:360-381`
  (`_align_to_previous`, ya genérico).
- **Acción:** propagar `previous_palette` y `temporal_strength` también en `median-cut`,
  `fast-octree` y `kmeans-rgb`. **`kmeans-rgb` es el default de `make_clip.py:43`**: hoy el
  camino por defecto del proyecto no tiene ninguna estabilización temporal.
- **Cierre:** error temporal medido en las fronteras de bloque, antes y después. Δbytes: sí.

### E-16 — `PairLUT` exacto

- **Precondición:** E-15.
- **Archivo:** `dither.py:287-344` (`PairLUT`), `721-722` (`apply_selective_dither`).
- **Acción:** calcular base, partner y level exactos por píxel en lugar de indexar por
  `rgb555_keys`. Hoy el dither se apaga en silencio en todo píxel donde la aproximación 555
  elige otra base que el cuantizador real.
- **Cierre:** cobertura de tramado antes y después; proxy de banding registrado. Δbytes: sí.

### E-17 — Presupuesto de dither en bytes (`V1-OPT-02`)

- **Precondición:** E-16.
- **Archivo:** `dither.py`.
- **Acción:** comparar los bytes reales del frame con dither contra el baseline y rechazarlo
  si excede un presupuesto configurable. El límite de bytes y el 5% de celdas se aplican
  **juntos**; ninguno reemplaza al otro.
- **Cierre:** cierra el ítem pendiente del backlog vigente. Δbytes: sí.

### E-18 — Interacción dither/threshold documentada y cubierta

- **Precondición:** E-17.
- **Archivo:** `encoder.py:938-948`.
- **Acción:** el threshold se aplica **después** del dither y revierte celdas al valor
  previo, rompiendo el patrón Bayer de forma distinta cada frame. Excluir del threshold las
  celdas que el dither marcó (`dither_details["changed"]`, hoy calculado y descartado).
- **Cierre:** test que cubre `--dither auto --threshold N` combinados, hoy inexistente.
  Δbytes: sí.

> **E-12 a E-18 cierran F3.**

### E-19 a E-24 — Trellis (F5)

- **Precondición:** F1, F2 y F3 cerradas.
- **Orden obligatorio:**

| ID | Tarea |
|---|---|
| E-19 | Congelar el orden canónico del pipeline: cuantizar → ditherear → trellis → emitir. `--threshold` queda absorbido como caso degenerado del trellis, no convive con él |
| E-20 | `--threshold` en ΔE-Oklab en lugar de euclídea RGB (`encoder.py:944-945`) |
| E-21 | Jerarquía de costo: proxy barato para explorar, `zlib -9` entre finalistas, Zopfli **solo** sobre el ganador. Zopfli dentro del bucle del trellis es inviable, no lento |
| E-22 | Trellis temporal: segundo candidato de paleta si hace que la celda desaparezca del DELTA |
| E-23 | Trellis espacial: forzar los cruces 17→16, 5→4 y 3→2 en `_dense_candidates` (`regional_codec_v2.py:203-227`) |
| E-24 | Perfil `--near-lossless`, opt-in, con presupuesto ΔE **conservador** |

- **Calibración de E-24:** implementar parametrizado, barrer un rango de ΔE sobre las dos
  referencias y elegir el mayor valor cuyo error temporal y proxy de banding no se
  distingan del baseline. El valor elegido se registra con su medición.
- **Cierre de F5:** si el ahorro medido no supera un mínimo acordado, **F5 se archiva con
  su evidencia**. Ninguna otra fase depende de ella. Δbytes: sí.

---

## 3. Carril W — frontend

### W-01 — Ampliar el gate de sintaxis ES5

- **Precondición:** P-01. **Primera tarea del carril, sin excepción.**
- **Archivo:** `tests/test_frontend_compatibility.js:62-77`.
- **Acción:** agregar a la lista negra `TypedArray.prototype.fill/copyWithin/slice`,
  `Object.keys/entries/values/assign`, `Array.isArray`, `Array.from/of`, `Math.trunc/imul/clz32`,
  `Uint8ClampedArray`, `String.prototype.repeat/startsWith/endsWith/padStart`,
  `dataset`, `classList`, `matches`, `closest`, `JSON.*`, getters/setters y comas finales.
- **Cierre:** el gate ampliado pasa sobre el código actual (que está limpio) y **falla**
  sobre un archivo de prueba que usa cada patrón prohibido.

> El código está limpio hoy; el gate no impediría la regresión mañana, justo cuando se
> reescriben inflate, readers y overlay.

### W-02 — Atajo a keyframe hacia adelante en `ReaderV1`

- **Precondición:** W-01.
- **Archivo:** `frontend/reader.js:449-478` (`Reader.prototype.seek`).
- **Acción:** portar las líneas equivalentes de `reader-v2.js:768-776`: buscar el último
  keyframe entre `decodedIndex` y `target` en lugar de reanudar siempre desde
  `decodedIndex + 1`.
- **Verificación:** con keyframes cada 30 frames, `seek(10)` seguido de `seek(100)`
  decodifica hoy 90 frames; el óptimo desde el keyframe 90 son 11.
- **Cierre:** el conteo de frames decodificados coincide con el óptimo; `cells` byte-idéntico
  al camino anterior en toda la regresión. **Desbloquea E-10.**

### W-03 — Rollback transaccional de `seek()` en `ReaderV1`

- **Precondición:** W-02.
- **Archivo:** `frontend/reader.js:449-478`.
- **Acción:** portar el rollback de `reader-v2.js:785-799`: ante excepción, restaurar
  `decodedIndex = -1`, la paleta inicial y limpiar los dirty sets.
- **Cierre:** un frame corrupto a mitad de cadena deja el reader en estado consistente, no
  con `cells` mutado a medias.

### W-04 — Dimensionar `_scratch` con `_scratchMax`

- **Precondición:** W-03.
- **Archivo:** `frontend/reader.js:200,223-225,281-294`.
- **Acción:** `_scratchMax` se calcula en el scan (líneas 223-225) y **nunca se lee**.
  Usarlo para dimensionar el scratch inicial en lugar de `min(maxLength, _fullLength)`.
- **Verificación:** instrumentar la cantidad de llamadas a `_inflate` por `seek`. Hoy el
  primer frame DELTA infla el bloque completo cuatro veces por reintentos de crecimiento
  (`catch(ASCL_OUTPUT_BUFFER)` en 291 reinicia desde cero).
- **Cierre:** una sola llamada a `_inflate` por frame en todo el clip de referencia.

### W-05 — Fuzzing permanente de `inflate.js`

- **Precondición:** W-04. **Antes de W-06, sin excepción.**
- **Archivo:** `tests/test_inflate_fuzz.js` (nuevo).
- **Acción:** corpus determinista de mutaciones sobre streams zlib válidos, con semilla
  fija. Debe cubrir: sobre-suscripción Huffman, longitudes mayores a 15, árbol vacío,
  fin-de-bloque ausente, `hlit>286`/`hdist>32`, repeticiones fuera de rango, símbolo
  inválido, distancia mayor a la ventana, LEN/NLEN inconsistente, CMF/FCHECK, diccionario
  preset, datos extra tras el stream, Adler32 y bomba de descompresión contra `maxLength`.
- **Cierre:** cero hangs, cero accesos fuera de rango, cero excepciones no tipadas.
  Tiempo de corrida acotado para que pueda vivir en CI.

### W-06 — Reescritura de `inflate.js` con bit-buffer y tabla

- **Precondición:** W-05 en verde.
- **Archivo:** `frontend/inflate.js:121-148` (`getBit`, `getBits`, `decodeSymbol`).
- **Acción:** bit-buffer de 32 bits y tabla de lookup de 9 bits en lugar de la
  decodificación bit a bit con una llamada de función por bit.
- **Contexto:** es el 41-43% del tiempo total de decode de un frame. Es la mejora de CPU
  individual más grande del frontend.
- **Cierre:** salida byte-idéntica a la implementación actual sobre todo el corpus y sobre
  ambas referencias; W-05 en verde; mejora de tiempo medida y registrada.

### W-07 — Cachear buffers de `inflate` a nivel módulo

- **Precondición:** W-06.
- **Archivo:** `frontend/inflate.js:31,210-211,247,270`.
- **Acción:** hoy se crean unos diez objetos tipados por llamada: cuatro `Uint16Array` en
  `new Data(...)` + `makeTree()` ×2, un `Uint8Array(320)` y tres `Uint16Array(16)` por
  bloque dinámico, más un `subarray` por frame. Cachearlos a nivel módulo.
- **Cierre:** cero allocaciones tipadas por frame en el camino estable, verificado con
  instrumentación.

### W-08 — Aceptar `tile_size` flexible

- **Precondición:** W-07.
- **Archivo:** `frontend/reader-v2.js:176`.
- **Acción:** reemplazar `if (h.tileSize !== 16) fail(...)` por una validación de rango:
  `tileSize` entre 4 y 32 y `tileCount` acotado. El resto de `ReaderV2` ya es genérico
  (`this.tileSize`, líneas 180-181, 308-312, 351).
- **Cierre:** abre correctamente archivos con los seis tamaños de E-09. **Desbloquea la
  generación de artefactos de E-09.**

### W-09 — Una sola pasada en `_walkRegional`

- **Precondición:** W-08.
- **Archivo:** `frontend/reader-v2.js:736-741`.
- **Acción:** la pasada de validación no está guardada por `apply` en ninguno de sus bucles
  caros: revalida cada código packed (536-541), cada byte PAL8 (552), cada valor MASK (500)
  y recalcula `_tileGeometry` por tile. Guardar los bucles tras `apply` o fusionar ambas
  pasadas conservando la validación transaccional.
- **Cuidado:** la propiedad de "validar todo antes de mutar una sola celda"
  (`regional_codec_v2.py:584-590` del lado Python) **no se puede perder**. Fusionar solo si
  la validación completa sigue ocurriendo antes de la primera escritura.
- **Cierre:** `cells` byte-idéntico; un stream corrupto sigue sin dejar la matriz a medias;
  mejora medida (~15-20%).

### W-10 — Recuperar en v2 dos optimizaciones que v1 ya tenía

- **Precondición:** W-09.
- **Archivos:**
  - `reader-v2.js:99-102,756-757`: `clearBytes` byte a byte, llamado dos veces por frame
    sobre 253 KB. Usar `set(zeroBlock)` como `reader.js:90-98`. Medido: 20× más rápido.
  - `reader-v2.js:402-404,721`: recuperar el atajo `if (paletteEntries < 256)` de
    `reader.js:140-141`. Con paleta de 256 el bucle de la línea 721 es demostrablemente
    inútil y hace millones de invocaciones de método por keyframe.
- **Cierre:** `cells` idéntico; ambas mejoras medidas.

### W-11 — Limpieza de los caminos calientes de v2

- **Precondición:** W-10.
- **Archivo:** `frontend/reader-v2.js`.

| Línea | Acción |
|---|---|
| 324-337 | guardar el barrido de 256 celdas de `_markDirty` tras `if (this._dCellCount)` |
| 349-351 | `_markDirtyCell` hace 4 div/mod por celda: precalcular |
| 420,423 | `_writeTilePacked`: 2 divisiones flotantes por píxel |
| 537 | validación packed: idem |
| 643-644 | predictor keyframe: reemplazar `i % cols` / `floor(i/cols)` por bucle anidado con acumulador |
| 294 | `Math.pow(2, shift)` por byte de uvarint: tabla de 5 entradas |
| 666-677 | predictor delta: no recalcular el residual en la segunda pasada |
| 369 | `_markFull()` deja `_dCount = tileCount` con `dirtyTiles` sin poblar: usar `dirtyCount = 0` |

- **Cierre:** `cells` idéntico en toda la regresión; mejora agregada medida.

### W-12 — Salto por byte en el walk de DELTA_MASK

- **Precondición:** W-11.
- **Archivos:** `reader.js:419-427`, `reader-v2.js:606-612`.
- **Acción:** a 5% de densidad, dos tercios de los bytes de máscara son cero y se leen ocho
  veces cada uno. Saltar el byte completo cuando es cero.
- **Cierre:** `cells` idéntico; mejora medida (~29%).

### W-13 — `markRectDirty` en ambos readers

- **Precondición:** W-12.
- **Archivos:** `reader.js`, `reader-v2.js`.
- **Acción:** `Reader.prototype.markRectDirty(x0, y0, w, h)`. En v1 marca bits del bitset de
  celdas; en v2 marca celdas exactas y promueve a tile cuando el rect cubre un tile
  completo, respetando la disyunción celda/tile existente.
- **Cierre:** API simétrica, con test en ambos readers. **Desbloquea F7.**

### W-14 — Seguridad y robustez del player

- **Precondición:** W-13.

| Archivo:línea | Acción |
|---|---|
| `tv-player.html` | exigir CRC distinto de cero en v1 y fallar explícito; verificar antes el inventario de artefactos existentes |
| `tv-player.html:107-108`, `player.html:76-77` | emparejar `requestFrame`/`cancelFrame` como par; si falta `cancelAnimationFrame` nativo, usar el shim de `setTimeout` para ambos y preservar `window` como receptor |
| `tv-player.html:262-291` | manejar `webglcontextrestored`; hoy una pérdida transitoria degrada a Canvas2D **para siempre** |
| `player.html:109-126` | llamar `renderer.dispose()` en `pickRenderer`; hoy cada cambio de renderer o zoom abandona un contexto WebGL vivo |
| `player.html:198-213` | capturar excepciones en el loop y pausar el audio |
| `player.html:257-263` | eliminar `?src=` arbitrario, como ya hizo `tv-player.html:115` |
| `inflate.js:15` | `maxLength` obligatorio en la API pública; hoy el default es ~2 GB |
| `inflate.js:45-49` | rechazar árbol Huffman sub-suscripto (`left > 0 && used > 1`), por RFC 1951 |

- **Cierre:** cada ítem con su test. W-05 sigue en verde tras los cambios de `inflate.js`.

### W-15 — Camino ASCII de Canvas2D (OPCIONAL)

- **Precondición:** W-14. **Opcional**: solo afecta a los modos `ascii-*`, que el camino
  `pixel` de producción no usa. No bloquea nada; se hace únicamente si los modos ASCII
  vuelven a ser un objetivo del producto.
- **Archivo:** `render-canvas2d.js:134-149`.
- **Acción:** cachear las cadenas `"rgb(r,g,b)"` por entrada de paleta y los `ramp.charAt(i)`
  en arrays; agrupar por color para minimizar cambios de `fillStyle`; limitar el `fillRect`
  y el bucle a `dirtyY0..dirtyY1`. Hoy ignora por completo el dirty set y redibuja todo
  aunque el reader informe tres celdas sucias.
- **Cierre:** salida visual idéntica; mejora medida.

> **W-01 a W-14 cierran F4.** W-15 es opcional y no forma parte del gate.

---

## 4. Puntos de sincronización

| ID | Cuándo | Qué se integra | Condición |
|---|---|---|---|
| **S-1** | E-02 y W-01 cerradas | merge de F0 a la rama base | regresión en verde en ambas ramas |
| **S-2** | W-08 cerrada | habilita generar artefactos de E-09 | `ReaderV2` abre los seis `tile_size` |
| **S-3** | W-02 cerrada | desbloquea E-10 | conteo de frames decodificados óptimo |
| **S-4** | F2, F3, F4 cerradas | **revisión única de formato (F6)** | ver abajo |
| **S-5** | F1 y W-13 cerradas | runtime del overlay (F7) | gates de INT-002 |
| **S-6** | F6 y F7 cerradas | validación física (F8) | artefactos finales regenerados |

### S-4 — Revisión única de formato (F6)

Se agrupa **todo** lo que el TV debe entender distinto, para desplegar una sola versión de
decoder:

| ID | Tarea |
|---|---|
| F6-1 | `SPARSE` con offsets diferenciales (`regional_codec_v2.py:236-241`); el decoder ya exige que sean estrictamente crecientes (459), así que codificar `offset - prior - 1` es gratis semánticamente |
| F6-2 | `tile_size` flexible declarado y cerrado (E-09 + W-08); **barrido definitivo** por artefacto sobre la salida del trellis, porque E-23 cambia la estadística por tile |
| F6-3 | Envelope `ASCLVID3` con `meta_len`; migrar el sidecar adentro |
| F6-4 | Nombre versionado `clip.<sha-corto>.asclv` e invalidación de caché (`CACHE-001`) |

**No entra:** `PAL5`/`PAL6` para el hueco de 17-255 colores por tile. El §17 del roadmap lo
mantiene vetado hasta tener benchmark neto en TV. Queda anotado como candidato de la
revisión siguiente, con la estimación de 25-37% en tiles de gradiente.

**Cierre de S-4:** readers viejos rechazan `ASCLVID3` por magic desconocido, limpiamente;
round-trip Python/JavaScript byte-exacto; corpus de corrupción ampliado a los campos nuevos;
prueba de caché fría y caliente.

### S-5 — Runtime del overlay (F7)

| ID | Tarea |
|---|---|
| F7-1 | Estado y orden por frame de `DISENO-INTERVENCION-MATRICIAL.md` §9.2 |
| F7-2 | API ES5 `attach/setField/setValues/clearField/clear/detach` |
| F7-3 | Canal de datos: texto de longitud fija, serial monotónico, validación en cinco pasos, backoff acotado |
| F7-4 | Referencia Python que reproduce la misma matriz con overlay |

**Cierre de S-5:** los gates de INT-002 sin excepción. En particular, `cells` byte-idéntico
a la reproducción sin overlay tras `clear()`, seek hacia atrás y reinicio de loop.

### S-6 — Validación física (F8)

| ID | Tarea |
|---|---|
| F8-1 | `frontend/diagnostic-player.html`, ES5, separado de `tv-player.html` |
| F8-2 | Matriz física 640 y 768, Canvas2D y WebGL1, 30 minutos |
| F8-3 | Go/no-go de v2 (`TV-02`) contra los artefactos **ya optimizados** |
| F8-4 | `MEM-001`: memoria por componente, con y sin overlay |
| F8-5 | Regenerar el artefacto de release **después** del último cambio de codec |

## 4-INT-003. Carril INT-003 — parches genéricos de imagen (vía corta)

Diseño cerrado en [`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md)
(D1..D6 resueltas con el operador el 2026-08-28). Secuencial: cada tarea tiene
como precondición la anterior. La ruleta NO está en este carril (va con
`ASCLVID3` en F6/S-4).

### INT-003-A — Reserva ampliada a 32 entradas

- **Archivos:** `backend/overlay_palette.py`, `backend/make_clip.py`.
- **Acción:** `RESERVED_RGB_32` (§4 del diseño; últimas 10 filas bit-idénticas a
  `RESERVED_RGB`), `reserved_rgb_bytes(n)` paramétrico; `--reserved` acepta
  `0|10|32` y con 32 estampa la tabla de 32 y mantiene `protect_panel`.
- **Cierre:** test Python nuevo (cableado en `run_all.py`): encode real con
  `reserved=32` → toda época termina en los 96 bytes canónicos (INV-4) y
  ninguna celda base usa índice ≥224 (INV-3 paramétrico); las tablas de 10 y
  32 coinciden en la cola. CI en verde. Δbytes: sí — fila de `bench_ref` del
  sintético con `reserved=32` (costo de calidad de la base de 224).

### INT-003-B — ASCLSLOT v2: escritor y validador Python

- **Archivo:** `tools/make_slots.py` (+ tests).
- **Acción:** `build` v2 y `validate` que acepta v1 y v2 según el byte de
  versión: `pal_reserved` variable, `patch_dir`/`patch_data` heterogéneos,
  slots con `w,h`, campos con `kind` (dígitos/elección) y `patch_base`,
  presupuestos §5.4 (barrido de eventos + techo de RAM), canonicidad §5.5.
- **Cierre:** suite Python con corpus positivo y negativo (cada regla de §5
  tiene su rechazo probado); v1 sigue aceptando/rechazando exactamente lo
  mismo (regresión intacta). CI en verde.

### INT-003-C — slots.js espejo v2

- **Archivo:** `frontend/slots.js` (+ suite JS nueva en `run_all.py`).
- **Acción:** `ASCL_parseSlots` acepta v1 y v2 y devuelve meta normalizada
  (parches + `palReserved`; un sidecar v1 se normaliza a parches uniformes con
  los campos legados intactos). Espejo exacto del validador Python.
- **Cierre:** suite JS con el mismo corpus negativo que B (mensajes espejados);
  fixture v2 generado por Python aceptado byte a byte; gate ES5 en verde.

### INT-003-D — Runtime v2 + referencia Python

- **Archivos:** `frontend/overlay.js`, `backend/overlay_ref.py`,
  `frontend/datachannel.js` (solo verificación), tests runtime + cruzados.
- **Acción:** `values` u16 con centinela `NONE=65535`; campos de elección
  (`setField` para ambos kinds, payload con dígito de presencia en
  `setValues`); offsets de parche/base por sumas prefijas en `attach`; cola de
  paleta verificada con `N` del sidecar. Con sidecar v1 el comportamiento es
  byte-idéntico al de F7 (mismos tests en verde sin tocar).
- **Cierre:** `test_overlay_runtime.js` intacto y en verde; suite v2 nueva
  (compose byte-exacto con elección/presencia, solape espacial de ventanas
  disjuntas, NONE no marca sucio); fixtures cruzados Python/JS byte-idénticos
  con un clip real `reserved=32`; `datachannel.js` sin cambios (test que fija
  la longitud de payload v2 vía `digitCount`). CI en verde.

### INT-003-E — Horneado de parches arbitrarios

- **Archivo:** `tools/bake_patches.py` (nuevo; `bake_glyphs.py` queda como está).
- **Acción:** hornear parches desde (a) texto con **cualquier fuente TrueType**
  (dígitos u otros caracteres, tamaño libre) y (b) imagen PNG con alpha, a la
  reserva de 32: color → entrada reservada más cercana en Oklab, alpha<umbral
  → 255. Determinista (aritmética entera o LUT fija); salida = `patch_dir` +
  `patch_data` listos para el spec JSON de make_slots.
- **Cierre:** test Python determinista (dos corridas → bytes idénticos; todo
  byte en [224..255]; alpha→255) cableado en `run_all.py`. CI en verde.

### INT-003-F — Integración de producto y cierre de etapa

- **Archivos:** `tools/make_panel.py` o herramienta nueva, workflow `encode`,
  `frontend/live-player.html`.
- **Acción:** generar un sidecar v2 de demo: panel de 20 números (kind=0) +
  slots candidatos con números grandes en tipografía libre (kind=1, varias
  posiciones/ventanas); workflow `encode` gana `overlay=patches`
  (`--reserved 32` + sidecar v2); `live-player.html` lo reproduce y el botón
  de simulación genera payloads v2 (presencia aleatoria).
- **Cierre:** CI en verde; clip HQ `reserved=32` publicado por el workflow con
  SHA registrado; **player local levantado para el operador** con el clip y
  números en tipografía libre apareciendo en posiciones/momentos aleatorios;
  docs al día (estado, registro, ejecutados).

## 4-INT-004. Carril INT-004 — texto nativo en el mismo canvas

Pedido del operador (2026-08-28, tras la demo INT-003): los textos se dibujan
nítidos con la API de texto de Canvas2D sobre el MISMO canvas, después del
frame; la matriz queda para gráficos. Diseño en
[`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md) §10.

### INT-004-A — Módulo `frontend/textlayer.js`

- **Acción:** ES5 estricto, sin dependencias. `ASCILINETextLayer.create(items)
  -> capa | null` (todo-o-nada); item: caja en CELDAS (`x,y,w,h`), `size`
  (altura de texto en celdas), `color`, `outline`, `font`, `align`.
  `setText(id, str)` valida y devuelve bool (INV-7); `markDirty(reader)`
  marca las cajas con texto via `markRectDirty` (el video se repinta debajo);
  `draw(ctx, cellPx)` pinta borde + relleno a resolución del canvas con la
  fuente pedida (cache del string de fuente por `cellPx`: sin allocaciones
  repetidas en el camino caliente).
- **Cierre:** suite JS nueva cableada en `run_all.py`: create/setText
  todo-o-nada, escalado por `cellPx`, orden stroke→fill, `markDirty` con las
  cajas exactas, texto vacío no dibuja ni marca; gate ES5 en verde. CI verde.

### INT-004-B — Integración en `live-player.html`

- **Precondición:** INT-004-A.
- **Acción:** con items de texto declarados, `pickRenderer` elige Canvas2D
  (el piso: WebGL no gana funciones); orden por frame: `beforeSeek → seek →
  afterSeek → markDirty(texto) → renderer.draw → textLayer.draw`. Demo: tres
  textos nativos (serif, con borde) espejando los números grandes de la
  matriz para comparar nitidez lado a lado; «Simular carga» alimenta ambos.
- **Cierre:** `test_live_player_page.js` cubre el orden y la elección de
  renderer; CI verde; player local levantado para el operador.

## 4-INT-006. Carril INT-006 — fondo sin reserva + texto standalone

Pedido del operador (2026-08-28, tras ver la demo INT-004): el fondo actual
está encodeado con reserva de 32 para los números de matriz, que ya no
sirven (el texto es nativo). Se re-procesa el fondo **sin reserva** con la
máxima calidad de las herramientas ya desarrolladas, dejando los textos
nativos interviniendo como ahora — pero sin depender del sidecar de parches.
Después el operador pasa una imagen para probar la intervención gráfica
(decisión D7, ver INT-006-C).

### INT-006-A — Fondo HQ sin reserva, máxima calidad actual

- **Herramientas:** workflow `encode` (sin cambios de código; solo dispatch).
- **Acción:** dos encodes desde la rama `assets` con `overlay=off` (sin
  reserva: la base recupera los 256 colores), `zopfli=on`, `tile=16`,
  `palette=adaptive`, `algorithm=kmeans-oklab`, `dither=auto`, `fps=15`:
  1. perfil `graphic-hq` (768 — el perfil de producción vigente; debería
     reproducir `ebfe2eb4…4b36` / 17.482.270 B si nada cambió);
  2. perfil `graphic-ultra` (960 — candidato «mayor calidad posible»; más
     celdas, archivo y decode más caros: es dato para que el operador elija).
- Bajar ambos artifacts, verificar SHA, registrar las dos filas de
  `bench_ref` (PSNR RGB y error Oklab) en el registro. Dejar en `outputs/`
  el **768** como fondo de producto (los valores manuales del operador
  prevalecen; el 960 queda como artifact citado por SHA salvo que el
  operador lo prefiera al ver los números).
- **Importante:** borrar `outputs/clip.slots` y `outputs/data.txt` viejos
  (son del clip de parches; con el fondo nuevo el overlay de matriz no debe
  intentar attach).
- **Cierre:** fila(s) de registro con bytes/PSNR/Oklab/SHA de ambos
  perfiles; `outputs/clip.asclv` nuevo verificado por SHA. Δbytes: sí.

### INT-006-B — Texto nativo standalone (sin sidecar)

- **Precondición:** INT-004 cerrado (ya). Puede hacerse en paralelo con A.
- **Archivos:** `frontend/textfeed.js` (nuevo), `frontend/live-player.html`,
  suites nuevas + `test_live_player_page.js`.
- **Acción:**
  1. `textfeed.js` (ES5, sin dependencias): `ASCILINETextFeed.create(capa,
     campos)` con campos `[{id, width}]` → objeto con `digitCount` (suma de
     anchos) y `setValues(digits)` (todo-numérico, longitud exacta,
     todo-o-nada; escribe cada tramo con `capa.setText`). Es la misma
     interfaz que consume `datachannel.js`, que queda **sin cambios**.
  2. `live-player.html`: si NO hay overlay de matriz (sin sidecar, attach
     nulo o clip sin reserva), declarar items de texto por defecto (tres
     campos de 2 dígitos en las tres posiciones de la demo INT-004,
     dimensionados por cols/rows) + crear el feed; «Simular carga» genera el
     payload del feed; el canal de datos apunta al feed si `data.txt`
     existe (si no existe, el canal falla suave: INV-7). `pickRenderer` y el
     orden por frame ya son genéricos (INT-004-B).
- **Cierre:** suite JS nueva de `textfeed.js` cableada en `run_all.py`
  (mismo commit); `test_live_player_page.js` cubre el modo standalone; gate
  ES5 en verde; CI verde; **player local levantado** con el fondo nuevo de A
  y los números nítidos encima («Simular carga» los cambia).

### INT-006-C — Imagen del operador (decisión D7, bloqueada)

- **Precondición:** el operador entrega la imagen. **No arrancar antes.**
- **D7 — cómo interviene un GRÁFICO sobre el fondo sin reserva** (resolver
  con el operador al llegar la imagen):
  - (a) **nativa**: `drawImage` de la imagen sobre el MISMO canvas después
    del frame, como el texto (nitidez de pantalla, cero costo de paleta;
    el gráfico deja de ser byte-verificable y la regla 2 se reformula
    igual que se hizo con el texto);
  - (b) **matriz con reserva 32**: pipeline INT-003 ya listo
    (`bake_patches` PNG → sidecar v2), pero exige re-encodear el fondo con
    `--reserved 32` y volver a pagar el costo de calidad (−0,24 dB);
  - (c) **esperar INT-005** (parches por época, F6): sin costo de paleta,
    pero requiere el envelope ASCLVID3.
  - Recomendación a validar: (a) para probar ya con la imagen (coherente
    con lo decidido para el texto), (c) como definitivo para la ruleta.
- **Cierre:** decisión D7 registrada + prueba con la imagen real en el
  player local.

---

## 5. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa;
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si es Δbytes, su fila está en el registro;
4. el commit lleva su ID y no mezcla carriles;
5. si tocó el frontend, el gate ES5 ampliado pasa;
6. si tocó `inflate.js` o un reader, el fuzzing pasa.

## 6. Plantilla de fila de registro

```text
| ID | fecha | commit | referencia | parámetros | bytes .ascl | bytes .asclv |
  bytes/celda | keyframes | cadena delta máx | PSNR RGB | error Oklab |
  SHA-256 | conclusión y alcance |
```

Una conclusión queda ligada a su configuración. Si cambia el modo, la grilla, los FPS, la
paleta, el dithering o el codec, se revalida.

## 7. Arranque

En este orden, sin saltear:

1. **P-01** ramas y línea base
2. **P-02** congelar las dos referencias y sus SHA-256
3. **P-03** `tools/bench_ref.py`
4. **P-04** Zopfli opcional
5. **E-01** el `lexsort` de la rama OpenCV — hasta que cierre, ninguna medición vale
6. **W-01** gate ES5 ampliado — en paralelo, en la otra rama

Recién con E-01 y W-01 cerradas se abre el resto del carril.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por tarea,
actualizada al cerrar cada una. Ese archivo —no la memoria de nadie— es lo que le dice a
la próxima sesión de trabajo dónde quedó todo.
