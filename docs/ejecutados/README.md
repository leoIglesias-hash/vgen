# Docs ejecutados

Archivo de lo **ya cumplido y verificado**. Cada archivo resume un lote o fase cerrada:
qué se hizo, con qué evidencia, en qué commits, y qué decisiones quedaron tomadas.

Reglas:

1. Acá solo entra lo **cerrado según la definición de terminado** del runbook §5
   (regresión en verde incluida). Lo parcial o en curso vive en
   [`../RUNBOOK-ESTADO.md`](../RUNBOOK-ESTADO.md), nunca acá.
2. Un archivo por lote cerrado, nombrado `AAAA-MM-DD-<qué>.md`.
3. Estos archivos **no se releen** al arrancar una sesión: existen para no tener que
   reconstruir evidencia vieja, y para que el runbook de estado pueda mantenerse corto.
4. El detalle de por qué una decisión se tomó sigue en
   [`../REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](../REGISTRO-DE-PRUEBAS-Y-DECISIONES.md)
   (append-only). Acá va el resumen operativo.

## Índice

| Fecha | Lote | Archivo |
|---|---|---|
| 2026-08-27 | F0: base congelada (P-01..P-04, E-01, E-02, S-1) | [`2026-08-27-F0-base-congelada.md`](2026-08-27-F0-base-congelada.md) |
| 2026-08-27 | Frontend W-01..W-05 (gate ES5, seek v1, scratch, fuzzing) | [`2026-08-27-W01-05-frontend.md`](2026-08-27-W01-05-frontend.md) |
| 2026-08-27 | F1: paleta reservada + glifos + sidecar (E-03..E-07) | [`2026-08-27-F1-paleta-reservada-glifos-sidecar.md`](2026-08-27-F1-paleta-reservada-glifos-sidecar.md) |
| 2026-08-28 | F4: frontend W-06..W-14 (reader 40% más rápido, robustez player, markRectDirty) | [`2026-08-28-F4-frontend-w06-14.md`](2026-08-28-F4-frontend-w06-14.md) |
| 2026-08-28 | F2: compresión E-08..E-10 (Zopfli −7,2%, tile_size 4..32, keyframes por corte) | [`2026-08-28-F2-compresion-e08-10.md`](2026-08-28-F2-compresion-e08-10.md) |
| 2026-08-28 | F7: runtime del overlay (S-5) — overlay.js, canal de datos, referencia Python byte-idéntica, panel + live-player | [`2026-08-28-F7-runtime-overlay.md`](2026-08-28-F7-runtime-overlay.md) |
| 2026-08-28 | INT-003: parches genéricos (vía corta) — reserva 32, ASCLSLOT v2, runtime v2 con elección/presencia, bake_patches, workflow overlay=patches | [`2026-08-28-INT-003-parches-genericos.md`](2026-08-28-INT-003-parches-genericos.md) |
| 2026-08-28 | INT-004: texto nativo en el mismo canvas — textlayer.js + live-player (Canvas2D con backing escalado, demo lado a lado) | [`2026-08-28-INT-004-texto-nativo.md`](2026-08-28-INT-004-texto-nativo.md) |
| 2026-08-28 | INT-006: fondo sin reserva (768 byte-idéntico a P-02, 960 medido) + textfeed standalone + imagen nativa D7=a | [`2026-08-28-INT-006-fondo-sin-reserva.md`](2026-08-28-INT-006-fondo-sin-reserva.md) |
| 2026-08-29 | F3: carril de calidad E-12..E-18 (solo E-12 adoptado; E-17 validado pero la decisión del dither es visual, no numérica; E-18 corrige el revert del threshold) | [`2026-08-29-F3-carril-calidad.md`](2026-08-29-F3-carril-calidad.md) |
| 2026-08-30 | F5: trellis E-19..E-24 + INT-007 — producto 11,3 MB = 29 % del mp4 fuente (near-lossless 8 adoptado por el operador); tipografía con sombra y ruleta simulada | [`2026-08-30-F5-trellis-near-lossless.md`](2026-08-30-F5-trellis-near-lossless.md) |
| 2026-08-31 | F6 (S-4): formato v3 — SPARSE diferencial, envelope ASCLVID3 con meta embebida, barrido 2D de tile (ganador espacial 16 + regional 32), CACHE-001; producto adoptado 1280@15 v3 `dcd6afb6…` = 62,8 % de la fuente, en producción | [`2026-08-31-F6-formato-v3-S4.md`](2026-08-31-F6-formato-v3-S4.md) |
| 2026-08-31 | S-7: barrido de resolución (producto = 1280@15; el 1920 vuelve a más fps) + deploy del player a Cloudflare (iargen.com/player/ + variantes, R2+Worker, subida sin redeploy) | [`2026-08-31-S7-resolucion-y-deploy-player.md`](2026-08-31-S7-resolucion-y-deploy-player.md) |
| 2026-08-31 | Archivo del runbook de estado: tablas completas de tareas cerradas (P/E/W/F7/INT/F6, verbatim) + bitácora 2026-08-27..30 | [`2026-08-31-tablas-de-tareas-cerradas.md`](2026-08-31-tablas-de-tareas-cerradas.md) |
| 2026-08-31 | F9 (S-8): aceleración del frontend (W-16..W-20) + motor único `playloop.js` para las cuatro páginas (W-22..W-25); p95 14,90 ms de 66,7 con drops 0, el cuello pasó a `inflate`; publicado en 2 actos (24 + 28 keys) | [`2026-08-31-F9-aceleracion-frontend.md`](2026-08-31-F9-aceleracion-frontend.md) |
| 2026-09-01 | **H-9 (fase H, formato propio)**: el pack v0 emitido desde el máster (4 piezas + HLS/DASH por remux; VP9 −53,8 %, segmentos CMAF y DASH byte-idénticos entre sí), sus herramientas (`emit_pieces.py`, workflow `emitir-v0`, `v0.html` de una sola pantalla, `keypad.js`, `ir.html`) y las 60 keys publicadas y verificadas. Deja abierta **H-14** (el invariante 7 no se cumple en H.264) | [`2026-09-01-H9-pack-v0-y-herramientas.md`](2026-09-01-H9-pack-v0-y-herramientas.md) |
