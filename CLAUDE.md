# ASCILINE-video — guía de sesión (leer esto primero, siempre)

Convierte video **offline** (Python) a un formato propio `.ascl`/`.asclv` que un player
**ES5 sin dependencias** reproduce en Smart TVs antiguos. Encoder caro, decoder trivial:
el TV nunca cuantiza ni decide, solo ejecuta.

## Arranque post-compact — en este orden, sin leer de más

1. [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) — dónde quedó todo, próxima acción, bitácora de desvíos.
2. [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md) — **solo la tarea a ejecutar** (archivo, acción, criterio de cierre).
3. [`docs/ejecutados/`](docs/ejecutados/) — lo ya cumplido con su evidencia; consultar, no releer.
4. [`docs/MAPA-DEL-PROYECTO.md`](docs/MAPA-DEL-PROYECTO.md) — solo si falta orientación estructural.
5. Spec de formato / diseño de intervención — solo si la tarea toca bytes u overlay.

## Modelo de trabajo (acordado con el operador, 2026-08-27)

- **Esta máquina no tiene Python ni Node, a propósito.** Toda la regresión (tests Python +
  suites JS) se valida en **GitHub Actions** (workflow `regression`) en cada push.
  Una tarea se cierra **solo con CI en verde**; si CI falla, se corrige hacia adelante.
- **Commits directos a `main`**, un commit por tarea, mensaje `<ID>: <título>`.
  Push tras cada tarea; el CI de ese push es la regresión de cierre.
- Al cerrar una tarea: actualizar su fila en `RUNBOOK-ESTADO.md`; al cerrar una fase o
  lote, sumar el resumen a `docs/ejecutados/`.
- Todo test nuevo se cablea en `tests/run_all.py` **en el mismo commit** (regla 7).
- Los videos de producto **no se commitean a `main`** (`.gitignore` ya lo impone). El
  clip HQ fuente vive local en `inputs/TKN-2443-GANADOR- 15seg-.mp4` y en la rama
  huérfana **`assets`** del repo (solo insumos de encode). Receta de
  producto vigente (2026-08-30): 768 graphic-hq, adaptive kmeans-oklab,
  tile 16, `--palette-refit 5`, `--dither off`,
  **`--near-lossless 8`**, zopfli, overlay=off — exactamente los
  defaults del workflow `encode` — → `b081f4ba…f6a05e` (11.304.137 B,
  35,10 dB, **29,0 % del mp4 fuente**).
- **Generar un clip para ver:** workflow `encode` (Actions → encode → Run workflow).
  Encodea desde la rama `assets` con el perfil HQ por defecto y publica `clip.asclv`,
  la fila de `bench_ref`, el SHA-256 y un `preview.mp4` como artifacts descargables.
- **Al cerrar cada etapa, levantar el player para el operador** (pedido 2026-08-28):
  bajar el último `clip.asclv` del CI a `outputs/` (verificar SHA), correr
  `tools/serve-local.ps1` (puerto 8123, layout plano, **`Cache-Control: no-store`**
  para que nunca vea caché vieja) y avisarle que abra `http://localhost:8123/`.
- **Documentación siempre al día antes de cualquier compact:** estado, registro,
  ejecutados y este archivo se actualizan al cierre de cada tarea/etapa, nunca "después".

## Ayuda-memoria — no perder de vista nunca

1. **Retrocompatibilidad JS:** frontend en sintaxis **ES5.1 estricta**, piso ECMAScript
   2015 de features: sin `fetch`/`Promise`/`Worker`/`WASM`/`JSON`/arrow/`let`/`const`/
   template strings. El gate `tests/test_frontend_compatibility.js` lo verifica; correrlo
   mentalmente antes de escribir cada línea de frontend.
2. **Un solo layer (un solo elemento canvas):** la intervención GRÁFICA escribe índices
   sobre la **misma matriz de celdas** del video, con paleta reservada paramétrica
   (10 → 246..255 o 32 → 224..255; la 255 siempre transparente). Jamás un segundo
   canvas ni un DOM overlay. Desde INT-004 (2026-08-28), los TEXTOS se dibujan
   nativos con la API de texto de Canvas2D **sobre ese mismo canvas**, después del
   frame (no viven en la matriz; con texto nativo el renderer es Canvas2D).
3. **Optimización siempre en el front, pero ganando calidad de imagen:** el costo se paga
   offline (Oklab, K-means, dither, trellis); el front solo se optimiza para hacer *menos
   trabajo por frame*, nunca degradando la imagen ya decidida por el encoder.
4. **Validar todo antes de mutar:** corrupción = excepción tipada; `cells` jamás queda a
   medias. Esta propiedad no se sacrifica por velocidad (fusionar pasadas sí, perder la
   transaccionalidad no).
5. **Determinismo y medición:** mismo input → mismos bytes. Una mejora sin fila de
   `tools/bench_ref.py` registrada no existe. Byte-idéntico se verifica, no se supone.
6. **Canvas2D es el piso; WebGL1 solo acelera**, nunca agrega función.
7. **Ningún buffer nuevo proporcional al frame por cuadro** en el loop estable.
8. **Canonicidad forzada del formato:** uvarint no canónico, padding ≠ 0 u offsets no
   crecientes se **rechazan**. El decoder confía en cero campos.
9. Los valores manuales del operador (cols, fps, colores) prevalecen sobre cualquier
   automatismo.

Referencia completa de invariantes: `docs/MAPA-DEL-PROYECTO.md` §7 y
`docs/PLAN-IMPLEMENTACION-OPTIMIZACION.md`.

## Estado (resumen grueso — el detalle vive en RUNBOOK-ESTADO)

**Cerrado y verificado** (no re-implementar; resumen en `docs/ejecutados/`, porqué en el
REGISTRO, SHAs en `RUNBOOK-ESTADO.md` §Referencias de clips):

- **F0-F5 y F7 completas.** Encoder: paleta reservada/glifos/sidecar (F1), Zopfli +
  tile_size 4..32 + keyframes por corte (F2), refit de paleta (F3, solo E-12 adoptado),
  carril trellis completo (F5: orden canónico, métrica Oklab, jerarquía de costo,
  temporal, espacial, `--near-lossless`). Frontend: W-01..14 (inflate 2,3×, walk −40%,
  robustez player, F4). Overlay: runtime F7 (overlay.js + datachannel.js + referencia
  Python byte-idéntica), INT-003 (parches, reserva 32), INT-004 (texto NATIVO Canvas2D
  sobre el mismo canvas), INT-006 (fondo sin reserva + textfeed standalone + imagen
  nativa D7=a), INT-007 (Palatino bold + sombra translúcida + logo girando como ruleta
  simulada).
- **Producto vigente:** `b081f4ba…f6a05e` = 11.304.137 B = **29,0 % del mp4 fuente**
  (35,10 dB) — defaults del workflow `encode` (`extra = --palette-refit 5
  --near-lossless 8`). El operador adoptó cada escalón de pérdida a ojo (dither off →
  temporal 4 → near-lossless 8); su criterio: «pérdida mínima aceptable si el ahorro
  lo vale».
- **Byte-identidad re-verificada 4 veces** (regla 5); desde E-21 el SHA se movió a
  propósito (elección de candidatos determinista en todos los entornos).

**En curso / pendiente** (detalle operativo en `RUNBOOK-ESTADO.md` §Próxima acción):

- ▶ **S-7 (Instancia 028 ABIERTA):** 1280 **APROBADO** por el operador (@15 fps
  `2a9201bf…` 24,5 MB = 63 % de la fuente; @12 fps `27ae0019…` 21,2 MB = 54 %,
  «casi ni se nota»). 1920@10 **medido** (`87160987…8d4e` = 32,8 MB = 84,3 %,
  34,81 dB, run 33333170964, preview enviado). **Falta su veredicto del 1920 y las
  definiciones finales** (qué resolución/fps queda de producto). La tasa por celda cae
  al subir resolución: 0,1451 → 0,1144 → 0,1023 B/celda/frame.
- ✅ **Player EN PRODUCCIÓN (2026-08-30):** `https://iargen.com/player/` (768),
  `/player/1280-15/`, `/player/1280-12/`, `/player/1920-10/` (espejo
  `asciline-player.iargen.workers.dev`). Infra 100 % nueva: bucket R2 `asciline-player`
  + Worker `asciline-player` + ruta `iargen.com/player*` — nada preexistente se tocó.
  Subidas futuras SIN redeploy: rotar el secret `UPLOAD_TOKEN` vía API y
  `PUT /__upload/<key>` con `x-sha256`; desde CI, workflow `publish-player`
  (pin por contenido en el worker, sin secretos en el repo).
  Falta que el operador lo pruebe en celular / Smart TV (antesala de F8).
- ▶ **F6 (S-4) EN CURSO (2026-08-30, orden F6-1 → F6-3 → F6-2 → F6-4):** F6-1 y
  F6-3 cerradas — el formato v3 está completo de punta a punta (SPARSE diferencial
  gateado por versión, envelope ASCLVID3 de 20 B con sidecar embebido, espejo JS,
  round-trip Python↔JS byte-exacto en la regresión, spec §14). El default de
  producto sigue v2: adoptar v3 es la decisión de cierre de S-4. **Sigue F6-2:**
  workflow `encode` con `tile=sweep` + `format=v3` + receta de producto (da además
  el primer Δbytes v3 vs v2). Después F6-4 (CACHE-001). **INT-005 por época sigue
  CONDICIONADO** a que los gates físicos de F8 fallen para el overlay nativo
  (dirección del operador 2026-08-30).
- **Después:** F8 (S-6: TV físico, p95, MEM-001). Opcionales: E-11, W-15. Menor: si
  se retoma el 960, re-medirlo con refit 5.

> Docs podados el 2026-08-30: el runbook de implementación solo contiene lo pendiente;
> los benchmarks/estados históricos se retiraron al historial Git (lista en
> `docs/README.md`). La evidencia canónica es REGISTRO + ejecutados/.
