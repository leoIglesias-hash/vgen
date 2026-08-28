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
