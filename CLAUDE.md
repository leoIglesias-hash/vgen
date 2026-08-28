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
  huérfana **`assets`** del repo (solo insumos de encode).
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
2. **Un solo layer:** la intervención en vivo (overlay de resultados) escribe índices
   sobre la **misma matriz de celdas** del video, con 10 entradas de paleta reservadas
   (246..255, la 255 transparente). Jamás un segundo canvas ni un DOM overlay.
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

## Estado de fases (resumen grueso — el detalle vive en RUNBOOK-ESTADO)

- ✅ F0 · **F1** (paleta reservada, glifos, sidecar) · **F2** (E-08 Zopfli −7,2%,
  E-09 tile_size 4..32 + barrido, E-10 keyframes por corte) · **F4** (W-01..14:
  inflate 2,3×, walk regional ≈−40%, markRectDirty, robustez player) ·
  **F7/S-5** (runtime del overlay: overlay.js + datachannel.js + referencia
  Python byte-idéntica; `make_clip --reserved 10`, panel de 20 números,
  workflow `encode` con `overlay=on` publica `clip.asclv`+`clip.slots`;
  `live-player.html` lo reproduce) · S-1/S-2/S-3 · P-02 (HQ reproducible;
  con Zopfli: 17.482.270 B, `ebfe2eb4…4b36`)
- ✅ **INT-003 (vía corta)**: reserva de 32 (224..255, cola F7 intacta),
  ASCLSLOT v2 (parches heterogéneos, kind dígitos/elección, presupuestos por
  frame), runtime v2 con NONE y presencia (v1 byte-idéntico), `bake_patches`
  (cualquier TTF/PNG → Oklab), `make_patch_pack` demo, workflow
  `overlay=off/panel/patches`. La **ruleta** va con ASCLVID3 (F6/S-4).
  Evidencia: `docs/ejecutados/2026-08-28-INT-003-parches-genericos.md`.
- ▶ Carril E (F3) desde **E-12** (el refit debe excluir la reserva vigente,
  224.. o 246.. según el clip).
- Pendiente: F3 (E-12..E-18), F5, F6 (S-4), F8 (necesita F6; F7 ya está).
  Opcionales: E-11, W-15. Gates físicos de INT-002 (p95, MEM-001) → F8
