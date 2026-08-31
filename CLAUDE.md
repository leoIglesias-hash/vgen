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
  producto vigente (2026-08-31, S-4 cerrada): **1280 @15 fps, formato v3,
  tile=sweep** = defaults del workflow `encode` (graphic-hq, adaptive
  kmeans-oklab, dither off, zopfli, overlay=off) **+ `format=v3` +
  `tile=sweep` + extra `--palette-refit 5 --near-lossless 8 --cols
  1280`** → `dcd6afb6…1632a` (24.458.884 B, 35,02 dB, **62,8 % del mp4
  fuente**; el sweep elige regional 32 con trellis espacial 16).
  Instalado en `outputs/` y servido como raíz de iargen.com/player/.
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
   automatismo. **Resolución y fps son elegibles POR VIDEO, nunca fijados por una
   receta** (operador, 2026-08-31): el destino real son TVs de 1920, así que toda grilla
   se estira; lo que se decide por clip es cuánta densidad conviene pagar. El front debe
   procesar cualquier combinación que se le pase.

Referencia completa de invariantes: `docs/MAPA-DEL-PROYECTO.md` §7 y
`docs/PLAN-IMPLEMENTACION-OPTIMIZACION.md`.

## Estado (resumen grueso — el detalle vive en RUNBOOK-ESTADO)

**Cerrado y verificado** (no re-implementar; resumen en `docs/ejecutados/`, porqué en el
REGISTRO, SHAs en `RUNBOOK-ESTADO.md` §Referencias de clips):

- **F0-F7 completas (todas las fases de encoder/frontend/overlay/formato).**
  Encoder: paleta reservada/glifos/sidecar (F1), Zopfli + tile_size 4..32 +
  keyframes por corte (F2), refit de paleta (F3, solo E-12 adoptado), carril
  trellis completo (F5). Frontend: W-01..14 (F4). Overlay: runtime F7, INT-003,
  INT-004 (texto nativo), INT-006, INT-007 (logo ruleta). **F6 (S-4) CERRADA
  2026-08-31: formato v3 ADOPTADO** — SPARSE diferencial gateado por versión,
  envelope ASCLVID3 (20 B) con sidecar embebido, tile ganador espacial 16 +
  regional 32 (vía `tile=sweep`, estable entre resoluciones), CACHE-001
  (puntero `clip.current.txt` no-cache/304 → `clip.<sha12>.asclv` immutable).
- **S-7 CERRADA (Instancia 028):** producto = 1280@15 elegido a ojo; el 1920@10
  descartado por FLUIDEZ, no por imagen — vuelve a más fps y **el front debe
  procesar cualquier resolución que se le tire** (directiva del operador). Tasa
  por celda CAE con la resolución: 0,1451 → 0,1144 → 0,1023 B/celda/frame.
- **Producto vigente:** `dcd6afb6…1632a` = 24.458.884 B = **62,8 % del mp4
  fuente** (35,02 dB, 1280×720 @15, v3) — en `outputs/` y como raíz de
  iargen.com/player/. El operador adoptó cada escalón de pérdida a ojo; su
  criterio: «pérdida mínima aceptable si el ahorro lo vale».
- **Player EN PRODUCCIÓN:** `https://iargen.com/player/` (PRODUCTO 1280@15 v3
  vía puntero CACHE-001), variantes `/player/1280-15/` (v2), `/player/1280-12/`,
  `/player/1920-10/` (espejo `asciline-player.iargen.workers.dev`). Bucket R2 +
  Worker `asciline-player`, nada preexistente tocado. Subidas SIN redeploy:
  rotar `UPLOAD_TOKEN` vía API y `PUT /__upload/<key>` con `x-sha256`; desde CI,
  workflow `publish-player` (pin por contenido).
- **Byte-identidad re-verificada** (regla 5) también para el pipeline v3
  (dos pares de runs byte-idénticos en F6-2).

**En curso / pendiente** (detalle operativo en `RUNBOOK-ESTADO.md` §Próxima acción):

Plan nuevo aprobado por el operador el 2026-08-31 (Instancia 030). Orden:
**F9 → F10 → F11 → F8 → DIAG-001**.

- **F9 (S-8) — EN EJECUCIÓN, arranca por `W-16`.** Aceleración del frontend sin tocar
  bytes ni formato: banco de medición + diagnostic-player (W-16), LUT `Uint32` (W-17),
  **textura de índices + paleta en el shader** (W-18, «probarlo cuanto antes»),
  reconstrucción de 4 taps (W-19, acoplada a W-18), cadencia y pre-decode (W-20).
  Motivo: la conversión índice→RGBA cuesta ~14,5 M accesos y 8,3 MB de subida por
  keyframe a 1920. Diseño: `docs/DISENO-RENDER-INDEXADO.md`.
- **F10 (S-9)** — pérdida adaptativa por suavidad (E-25, E-27, E-26, E-28): el banding
  solo se ve en zonas suaves, así que el presupuesto deja de ser plano. Ataca el degradé
  escalonado del huevo sin devolver el ahorro del near-lossless 8. Emite v3 igual que
  hoy. Diseño: `docs/DISENO-PERDIDA-ADAPTATIVA.md`.
- **F11 (S-10) — formato v4:** LOD por tile (E-30 horneado **sin** cambio de formato →
  F11-1 opcode `LOD2`) y **transparencia** (F11-2: `cell_fmt 4`, paleta RGBA, `--alpha`;
  feature nueva pedida por el operador para clips de personaje sobre fondo transparente).
  Depende de F9. Diseño: `docs/DISENO-FORMATO-V4-LOD-Y-ALPHA.md`.
- **F8 (S-6)** — TV físico, p95, MEM-001, con F9-F11 adentro (F8-1 se adelanta como
  W-16). **INT-005 por época sigue CONDICIONADO** a que los gates físicos fallen para el
  overlay nativo (dirección del operador 2026-08-30).
- **DIAG-001** — causa del escalonado del huevo, **al final por decisión del operador**.
- **Del operador:** probar iargen.com/player/ en celular y Smart TV.
- Opcionales: E-11, W-15, W-21, E-29. Menor: si se retoma el 960, re-medirlo con refit 5.

> Docs podados el 2026-08-30 y limpiados el 2026-08-31 (cierre de F6/S-4 y S-7): los
> runbooks solo contienen lo pendiente (F8 + opcionales); las tablas completas de
> tareas cerradas y la bitácora 2026-08-27..30 están archivadas **verbatim** en
> `docs/ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`; los benchmarks/estados
> históricos retirados viven en el historial Git (lista en `docs/README.md`). La
> evidencia canónica es REGISTRO + ejecutados/.
