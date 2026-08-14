# ASCILINE — Documento de contexto para Cowork

> **Documento histórico de contexto original.** No contiene el estado actual ni la cola
> vigente. Para continuar use `HOJA-DE-RUTA-TECNICA-V2.md`.

> Documento de trabajo original. Reúne el análisis inicial, las mejoras propuestas, las
> decisiones pendientes de esa etapa y el primer roadmap por fases.

---

## 0. Referencias

- **Proyecto original:** https://github.com/YusufB5/ASCILINE (autor: YusufB5)
- **Demo funcional de imagen/video** (ya construido, ruta WebGL + fallback Canvas2D, audio sync): `asciline-player.html`
- **Naturaleza del cambio:** no es un parche; es un rediseño para volverlo más eficiente y potente, con foco en **reproducir en webviews** (incluso viejos) y **superar el techo de ~360p**.

---

## 1. Qué es ASCILINE (estado actual)

Motor que convierte video a una grilla de texto (ASCII o "píxeles" de bloques de color) en tiempo real y la transmite por WebSocket a un Canvas HTML5.

**Arquitectura actual**
- **Backend:** Python + FastAPI + OpenCV + NumPy. Decodifica el video, mapea píxeles a caracteres, emite frames binarios por WebSocket.
- **Frontend:** JS vanilla. Recibe frames, los mete en un *jitter buffer* y los pinta en Canvas a 24–30 FPS.
- **Sincronización A/V:** el audio actúa como reloj maestro.

**Modos de color**
| Modo | Qué hace |
|---|---|
| B&W | solo carácter, sin color |
| Color reducido | carácter + color de paleta acotada |
| 16M color | carácter + RGB pleno |
| Pixel mode | bloque de color, sin carácter (mosaico, "se acerca a 360p") |

**Codec adaptativo (ya existente)**
Elige por frame el encoding más chico y lo marca con 1 byte de header:
| Tag | Encoding | Mejor para |
|---|---|---|
| 0 | RAW (framebuffer crudo, legacy) | frames incompresibles |
| 1 | ZLIB del framebuffer | movimiento general |
| 2 | DELTA (solo celdas que cambiaron) | escenas estáticas / poco movimiento |

Más un flag `--quality {lossless,high,balanced,low}` que activa **delta temporal con pérdida** (una celda de color se reenvía solo si se desvía más allá de una tolerancia). Default `lossless` (bit-exact).

**Ahorros medidos por el autor** (modo color, grilla 200×80):
- Pantalla estática / slideshow: ~0.3% del legacy (≈375× más chico)
- Pixel mode: ~11.6% (≈8.6×)
- Alto movimiento: ~63% (nunca peor que legacy)

**Casos de uso fuertes**
- Reproducir video en dispositivos sin GPU ni decoder de hardware (terminales retro, hardware limitado).
- Esquivar restricciones del browser (para el navegador es "JS actualizando un canvas").
- Aplicar filtros CSS sobre el resultado (glow, sombras) — imposible sobre `<video>` real.
- Reducir el stream visual a strings lógicos legibles por un LLM liviano.

**Pros**
- Cross-platform, liviano del lado cliente en modo ASCII.
- Ancho de banda y CPU mínimos *en ASCII con pocas columnas*.
- Codec adaptativo opt-in sin romper compatibilidad.
- Sincronización A/V sólida.

**Contras**
- El cómputo pesado vive en el **servidor**: encodea por conexión, no escala gratis.
- En pixel mode con muchas columnas el ancho de banda puede ser **peor** que H.264/VP9.
- Calidad limitada (pixel mode ~360p).
- Riesgo de desync si se sube `--cols` por encima de lo que la CPU aguanta.
- Proyecto de un solo dev, sin releases formales ni tests de carga publicados.

---

## 2. Diagnóstico: dónde está el cuello de botella

Presupuesto fijo: a 30 FPS hay **33 ms por frame**. Si la suma se pasa, el backend se atrasa respecto al audio (desync) y la "solución" actual es bajar `--cols` → de ahí el ~360p práctico.

Reparto estimado por etapa (pixel mode ~600 cols, ilustrativo):

| Etapa | Actual (Canvas 2D) | Optimizado | Comentario |
|---|---|---|---|
| Decode backend (OpenCV) | 4 ms | 4 ms | igual |
| Encode backend | 9 ms | 3 ms | zstd + paleta + Rust |
| Red / WebSocket | 3 ms | 1 ms | menos bytes |
| Decode cliente | 2 ms | 1 ms | en Web Worker |
| **Render cliente** | **24 ms** ← el muro | **2 ms** | Canvas 2D → WebGL |
| **Total** | **42 ms** (no llega) | **11 ms** (sobra) | |

**Conclusión clave:** el techo de 360p **no es del ASCII**, es del render Canvas-2D celda-por-celda (`fillRect`/`fillText` con `fillStyle` por celda rompe el batching). Moviéndolo a WebGL, el techo se corre solo.

---

## 3. Mejoras propuestas

### 3.1 Render: Canvas 2D → WebGL (la grande)
- **Pixel mode:** armar un buffer RGBA de `cols×rows` y subirlo como textura (`texImage2D`), dibujar un quad fullscreen → **1 upload + 1 draw call** en vez de cientos de miles de `fillRect`. Filtro `NEAREST` = bloques nítidos. Esto solo lleva de 360p a 720p+ en el mismo hardware.
- **ASCII mode:** dos caminos posibles (ver decisión pendiente D2): (a) glyph atlas + instancing (`drawArraysInstanced`, 1 draw call), o (b) Canvas 2D `fillText` (universal, simple, suficiente a ~150 cols).

### 3.2 Sacar el decode del hilo de UI
- `OffscreenCanvas` + Web Worker para que decode/upload no congelen el scroll ni el toque. `SharedArrayBuffer` para pasar frames sin copiar. (Solo en webviews que lo soporten; degradar si no.)

### 3.3 Encoding backend
- **zlib → zstd** (~3× más rápido, mejor ratio).
- **Paleta adaptativa** en pixel mode → **1 byte/celda** (índice) en vez de 3 (RGB). Combinado con DELTA, ahorro grande.
- **Chroma subsampling** (YCbCr, croma compartida entre celdas vecinas) → color a la mitad, plano de caracteres exacto.
- **Fan-out:** encodear *una vez por frame* y repartir a todos los clientes (pub/sub) en vez de re-encodear por conexión. Esto es lo que más limita la escala en live.
- **Encoder en Rust** (pyo3) para el hot loop de delta/quantize (saca el GIL).

### 3.4 Matar el modo DOM
- El modo DOM es lo más lento en un webview. Forzar siempre Canvas/WebGL.

### 3.5 Pre-encoding (VOD) — el cambio estructural
Si el video no cambia, **encodear en vivo es desperdicio**. Se encodea **una vez, offline**, se genera un archivo binario compacto (`.ascl`), y en playtime el server solo sirve un archivo estático (o lo sirve la CDN). El backend pasa a **≈0 cómputo** y escala infinito. Como es offline, se puede exprimir compresión que en vivo no da el tiempo (k-means de paleta, motion estimation, zstd a nivel máximo, probar las 3 codificaciones y quedarse con el mínimo real).

---

## 4. Formato `.ascl` propuesto

Contenedor con header + paleta + índice de offsets + frames (+ audio por separado).

**Header (borrador, 32 bytes)**
- `magic` = `ASCL`
- `version` (uint8)
- `cols`, `rows` (uint16 c/u)
- `fps` (uint8) ← **FPS configurable, vive en el header** (default 15)
- `mode` (uint8) — ASCII / color reducido / 16M / pixel
- `pal_size` (uint16) — 256 = 1 byte/celda
- `n_frames` (uint32) — **una imagen = `n_frames = 1`**
- `flags` (uint8) — bit0=lossy, bit1=paleta por escena, etc.

**Por frame:** tag de 1 byte (RAW / ZLIB→zstd / DELTA) + payload. Tabla de offsets al inicio para seek a keyframes.

**Planos:** plano de caracteres (exacto) + plano de índices de color (paleta de 1 byte). En pixel mode solo el plano de índices.

**Imagen fija = caso fácil:** mismo header con `n_frames=1`. La paleta de 256 es *óptima para esa imagen puntual* (no hay que comprometer entre escenas). Sirve para validar el mapeo (rampa de caracteres, corrección de aspecto, cuantización) en aislamiento antes del video.

**Corrección de aspecto del carácter:** el glifo monoespaciado es ~2× más alto que ancho. `rows = cols × (altoSrc/anchoSrc) × 0.5` en ASCII; factor 1.0 en pixel mode. Sin esto la imagen sale estirada en vertical.

**Rampa de caracteres (ASCII):** luminancia de la celda → índice en una rampa ordenada por densidad de tinta. Rampa corta (look limpio), rampa larga (más gradientes/foto), o detección de bordes con Sobel (`/ \ | -` según dirección del gradiente) para contornos nítidos.

---

## 5. Audio

- **Carriles separados:** audio y "video ASCII" van aparte; el audio es el **reloj maestro**.
- **Formato:** MP3 como piso universal (lo decodifica hasta el webview más viejo). Opus/AAC donde haya soporte (archivos más chicos). **Nunca PCM crudo.**
- **Almacenamiento:** archivo de audio aparte (`clip.mp3`), cacheado con el mismo HTTP cache + IndexedDB que los frames. No se mete dentro del binario de frames.
- **Sincronización:** se lee `audio.currentTime`; el frame a mostrar es `Math.floor(currentTime × fps)`. Si el render se atrasa, se descartan frames; el audio nunca espera.
- **En el demo:** cuando la fuente es video, el audio viene gratis del `<video>` (ese elemento es el reloj maestro).

---

## 6. WebGL: compatibilidad y fallback

| Entorno | WebGL 1.0 | Detalle |
|---|---|---|
| WKWebView iOS 8+ | ✅ | confiable |
| Android WebView (Chromium 4.4+) | ✅ | desde ~2014 |
| Android WebView viejo (4.0–4.3) | ❌/⚠️ | sin WebGL confiable |
| GPU en blacklist | ⚠️ | el driver puede desactivarlo aunque el navegador "soporte" |
| WebGL 2.0 | solo modernos | **no contar con él** |

**Regla:** intentar `getContext('webgl')`; si devuelve `null`, caer a Canvas 2D sin romper nada. WebGL para pixel mode (donde importa la performance); Canvas 2D para ASCII (texto, universal) y como red de seguridad.

---

## 7. Precarga / cache en webviews viejos (ES2015)

El piso universal es el **HTTP cache**; todo lo demás es mejora opcional encima (*progressive enhancement*).

| Mecanismo | Webview viejo (~2015) | Binarios pesados | Control programático | Offline real | Veredicto |
|---|---|---|---|---|---|
| **HTTP cache** | ✅ universal | ✅ | ❌ | ⚠️ no garantizado | **piso confiable** |
| **IndexedDB** | ✅ 2015+ (bugs iOS 8–9) | ✅ | ✅ | ✅ | **mejor opción real** |
| WebSQL / AppCache | ✅ reliquias | ⚠️ | ⚠️ | ✅ | fallback ancestral (deprecado) |
| Service Worker | ❌ webview viejo / iOS<14 | ✅ | ✅ | ✅ | **no contar con él** |
| Cache API | ❌ atado a SW | ✅ | ✅ | ✅ | mismo problema |
| localStorage | ✅ universal | ❌ (~5MB, strings) | ✅ | ✅ | inútil para video |

**Plan de degradación (cae solo):**
1. **HTTP cache** siempre activo: `Cache-Control: public, max-age=31536000, immutable` + nombre versionado por hash (`clip.a1b2c3.ascl`).
2. **IndexedDB** si está: precarga con progreso, lista de bajados, borrado manual, playback offline confiable. Target principal.
3. **Service Worker + Cache API** solo si existe: experiencia transparente, tratado como lujo.
4. **Fallback ancestral:** HTTP cache puro.

**Detalles:** `navigator.storage.persist()` donde exista (evita evicción agresiva, sobre todo iOS); versionado por hash resuelve cache stale en todas las capas a la vez.

---

## 8. Decisiones pendientes (a tomar en Cowork)

| # | Decisión | Opciones | Notas |
|---|---|---|---|
| D1 | Resolución objetivo / sweet spot | (a) pixel ~480–540p con paleta+zstd; (b) ASCII high-cols con instancing | Pixel a más resolución pierde la gracia (lo gana un códec normal) |
| D2 | Render ASCII | (a) glyph atlas + instancing WebGL; (b) Canvas 2D `fillText` | (b) es universal y simple; (a) escala mejor a cols altas |
| D3 | Paleta | per-frame / per-escena / global; tamaño (256 vs menos) | Per-escena = buen balance fidelidad/peso |
| D4 | Formato de audio | MP3 solo / MP3 + Opus dual | MP3 = piso seguro |
| D5 | Compresión en el cable | zstd / brotli / ambos | brotli lo decodifica el browser nativo en HTTP |
| D6 | Lenguaje del encoder offline | Python+Numba / extensión Rust (pyo3) | Rust = más rápido, más laburo |
| D7 | ¿Mantener streaming live o VOD-only? | live (fan-out) + VOD / solo VOD | VOD saca el cómputo del playtime |
| D8 | Versión mínima de webview a soportar | define qué capas activar | impacta D2 y la capa de cache |
| D9 | ¿Fork de ASCILINE o reader/encoder nuevo? | fork / build fresco compatible con `.ascl` | el reader/player nuevo es propio igual |
| D10 | Spec final del `.ascl` (header, tags, planos) | — | depende de D1–D6 |

---

## 9. Archivos propuestos

| Archivo | Rol | Estado |
|---|---|---|
| `asciline-player.html` | Demo interactivo imagen/video (WebGL + fallback, audio sync, sliders) | ✅ hecho |
| `ASCL-format-spec.md` | Spec del contenedor `.ascl` (header, tags, planos, audio) | a crear |
| `encoder.py` | Encoder offline: imagen/video → `.ascl` (paleta, delta, zstd) | a crear |
| `reader.js` | Reader/player ES2015-safe: parse `.ascl` + WebGL/Canvas2D | a crear |
| `storage.js` | Capa de almacenamiento: detección de features + degradación (HTTP cache/IndexedDB/SW) | a crear |
| `render-webgl.js` | Renderer WebGL (texture upload pixel; opcional glyph atlas ASCII) | a crear |
| `render-canvas2d.js` | Renderer fallback Canvas 2D | a crear |

---

## 10. Roadmap por fases

- **Fase 0 — Validación de mapeo (✅ hecha):** demo de imagen con rampa de caracteres, corrección de aspecto, cuantización, WebGL+fallback.
- **Fase 1 — Formato + encoder de imagen:** `ASCL-format-spec.md` + `encoder.py` para imágenes (`n_frames=1`), paleta de 1 byte.
- **Fase 2 — Reader/player ES2015-safe:** `reader.js` + `render-webgl.js` + `render-canvas2d.js` con detección de features y fallback.
- **Fase 3 — Video:** extender el encoder a frames (DELTA + paleta + zstd), decimación variable, FPS configurable en header.
- **Fase 4 — Audio:** muxing por archivo separado + sincronización por `currentTime`.
- **Fase 5 — Almacenamiento/precarga:** `storage.js` con HTTP cache + IndexedDB (+ SW opcional), versionado por hash, `persist()`.
- **Fase 6 — Optimización:** encoder en Rust, fan-out para live (si se mantiene), chroma subsampling, OffscreenCanvas/Worker.

---

## 11. Limitaciones técnicas (restricciones del proyecto)

- **Target webviews viejos que corren ES2015 (ES6):** no asumir APIs modernas. Service Worker / Cache API / OffscreenCanvas son opcionales con degradación, nunca requeridos.
- **HTTP cache es el piso universal**; IndexedDB es el target real para offline.
- **WebGL no está garantizado** (driver/blacklist): siempre Canvas 2D fallback.
- **FPS por defecto 15, configurable** (20/25/30) — vive en el header del `.ascl`.
- **1 byte por celda** vía reducción de colores (paleta) como objetivo de peso.
- **Objetivo:** más eficiente y potente, reproducir en webviews, **superar 360p** (sin perder la gracia de la técnica).
- Mantener este proyecto **standalone** (no mezclarlo con otros sistemas).
