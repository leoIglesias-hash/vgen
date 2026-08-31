# F9 (S-8) — Aceleración del frontend, y un solo motor para las cuatro páginas

**Cerrada el 2026-08-31.** Fase de front puro: **no toca bytes ni formato**, así que se
validó entera contra el clip que ya estaba publicado (`dcd6afb6…1632a`, 1280×720 @15,
v3). El decoder no cambió de contrato en ningún punto.

## Qué se buscaba

W-16 midió el costo real de presentar un frame y encontró el cuello donde el diseño lo
sospechaba: la conversión de índice a RGBA cuesta ~14,5 M accesos por keyframe a 1920 y
mueve 8,3 MB. El resto de la fase ataca eso, y después la cadencia.

## Tareas

| ID | Qué | Commit | Resultado medido |
|---|---|---|---|
| `W-16` | banco `tools/bench_render.js` + `frontend/diagnostic-player.html` (F8-1 adelantada) | `f1ccfa3` | keyframe a 1920 = **11,0 ms de pura conversión**; el prototipo LUT daba 1,3×–3,3× |
| `W-17` | LUT `Uint32` de paleta en los dos readers | `8cecc7b` | keyframe a 1920 **11,4 → 5,7 ms** (2,0×), tiles densos 1,9×, disperso 1,33×. **Salida byte-idéntica** |
| `W-18` | índices como textura `LUMINANCE` + paleta 256×1 en el shader | `07a94e2` | **paridad GL/2D delta 0** con contexto WebGL real; etapa `rgba` en **0,00 ms** |
| `W-19` | reconstrucción de 4 taps (`soft`) | `07a94e2` + `af6bfff` | el operador **no la distingue** de `nearest` → **default `nearest`** (1 tap, bit-idéntico); `soft` queda disponible por video |
| `W-20` | cadencia de presentación + pre-decode del keyframe | `798203a`, `1cb0e38`, `af6bfff` | medido por el operador en pantalla real, 497 presentaciones: **p95 14,90 ms contra 66,7 de presupuesto, drops 0, tarde 0** |
| `W-22` | motor compartido `frontend/playloop.js` + `tests/test_playloop.js` | `3c46d3d` | CI verde (`866f2f1`) |
| `W-23` | `tv-player` y `diagnostic` pasan al motor | `2753fd1` | el diagnostic instrumenta los **dos** readers: mide el código de producción, no una copia |
| `W-24` | `live-player` (la raíz) y `player.html` estrenan el motor; `overlay.rebind()` | `26b4170` | gate nuevo: **adoptar y no adoptar dan las mismas celdas** |
| `W-25` | el gate ES5 salteaba páginas enteras | `1fe95a9` | `player.html` y `diagnostic-player.html` vuelven a analizarse |
| `W-21` | dirty rect en X | — | **opcional**, candidata a dejar de serlo: W-17 mostró que en deltas dispersos lo caro es barrer todo `dirtyCellBits` |

## Los tres hallazgos que valen más que los números

1. **Dos defectos que el CI verde no veía y el ojo del operador sí** (`af6bfff`).
   `_drawIndexed` cacheaba la vista de la banda sucia **solo por rango de filas**, así que
   tras un intercambio de readers subía a la GPU celdas del reader anterior; y la mezcla
   de 4 taps de `soft` necesita `highp` real, pero la caída a `mediump` era un fallback de
   compilación: el shader compilaba y dibujaba basura. Lecciones: **la identidad del
   buffer es parte de la clave del cache**, y una caída de precisión es un fallback válido
   para *compilar* pero una fuente de basura para *calcular*.
2. **El cuello se movió a `inflate`** (8,70 de los 14,90 ms del frame, ~58 %). Después de
   W-17 y W-18, lo caro es descomprimir, no convertir ni dibujar. Eso ordena cualquier
   optimización futura del front.
3. **La copia mentía sobre lo que se estaba midiendo.** La cadencia y el pre-decode vivían
   duplicados en `tv-player.html` y `diagnostic-player.html`, y **ausentes** en
   `live-player.html` —que es lo que sirve la raíz publicada—. El diagnostic medía una
   copia *parecida* al código de producción. Fusionarlo en `playloop.js` arregló las dos
   cosas de una: la raíz ganó la cadencia y la medición pasó a ser sobre el producto.

## El intercambio de readers y el overlay

El pre-decode adopta el keyframe **intercambiando readers**, nunca copiando celdas: cada
reader queda internamente consistente (paleta, dirty y `decodedIndex` viajan juntos), así
que el invariante 4 no se toca.

Con overlay activo, el intercambio va **entre `beforeSeek` y `afterSeek`**, con
`overlay.rebind(reader)` en el medio, que apaga `restoreValid` porque la base guardada
pertenece al reader que se va. El reader desplazado queda limpio y su próximo trabajo es
un keyframe, que reescribe todas las celdas. El gate no verifica el mecanismo sino la
propiedad: **adoptar y no adoptar tienen que dar exactamente las mismas celdas.**

## Publicación (2026-08-31)

Dos actos, los dos verificados byte a byte contra el repo:

- **Instancia 038 — 24 keys**: los 4 archivos compartidos que F9 cambió
  (`reader.js`, `reader-v2.js`, `render-webgl.js`, `render-canvas2d.js`) y 2 páginas
  nuevas (`tv-player.html`, `diagnostic-player.html`) × 4 carpetas.
- **Instancia 040 — 28 keys**: `live-player.html`, su copia `index.html`,
  `diagnostic-player.html`, `tv-player.html`, `overlay.js` (los 5 cambiados por
  W-22..W-25) más `playloop.js` y `player.html` (nuevos) × 4 carpetas. El número se
  calculó **auditando lo servido** contra el repo archivo por archivo, no estimando: los
  runbooks decían 25.

Las dos **puramente aditivas**: los archivos no tocados conservan su digest. El
procedimiento (token efímero acuñado por API, `PUT /__upload/<key>` con `x-sha256`
verificado por R2 de los dos lados, y token quemado al terminar) está en
[`deploy/asciline-player/README.md`](../../deploy/asciline-player/README.md). El repo no
guarda ningún token.

## Nota de infraestructura

El CI estuvo caído cuatro instancias por facturación de GitHub, no por código. Se resolvió
mudando el repo de trabajo a `leoIglesias-hash` (Instancia 040): los minutos de un repo
privado se le cobran al **dueño del repo**. `W-22`..`W-25` se escribieron a ciegas y
cerraron después con el run verde de `866f2f1`.

## Lo que queda abierto

- `W-21` (dirty rect en X) sigue opcional, ahora con argumento a favor.
- El costo del pre-decode es **otro `cells`** (2 MB a 1920) → anotado para **MEM-001**.
- La medición de W-20 es en GPU de PC. **F8** tiene que confirmar que la holgura de 4,5×
  le alcanza a un televisor. La comparación `1280 soft` vs `1920` nativo en TV vive ahí.
