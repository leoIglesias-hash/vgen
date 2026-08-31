# Runbook de implementación

Estado: **podado el 2026-08-30, re-podado el 2026-08-31 (F6/S-4 y S-7 cerradas)**.
Este archivo contiene SOLO las reglas de ejecución y las tareas que quedan por hacer:
**F8 (S-6) y las opcionales E-11/W-15**. Los cuerpos de las tareas ya ejecutadas
(P-01..P-04, E-01..E-24, W-01..W-14, F6, F7, INT-003/004/006/007, S-7, deploy del
player) se retiraron: su resumen operativo está en
[`ejecutados/`](ejecutados/README.md), su fila de cierre en las tablas archivadas
([`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md))
y su evidencia en
[`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md). El texto
completo original vive en el historial Git (hasta el commit anterior a cada poda).

Este documento no argumenta ni justifica: para eso están
[`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) y
[`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md). Acá está qué
tocar, cómo verificarlo y cuándo una tarea se considera cerrada.

## 0. Reglas de ejecución

1. **Commits directos a `main`, un commit por tarea.** Mensaje: `<ID>: <título>`. Si una
   tarea necesita varios commits, todos llevan el mismo ID. (El modelo original de dos
   ramas quedó sin efecto por decisión del operador, 2026-08-27.)
2. **Regresión antes de cerrar.** La máquina de trabajo no tiene Python ni Node
   **a propósito**: la regresión completa corre en GitHub Actions (workflow `regression`)
   en cada push. Una tarea se cierra solo con ese CI en verde; si falla, se corrige hacia
   adelante.
3. **Fila de registro obligatoria** para toda tarea marcada Δbytes. Plantilla en §6.
4. **Una tarea no empieza si su precondición no está cerrada.**
5. **Ninguna tarea se cierra «porque compila».** El criterio de cierre está escrito y es
   verificable.
6. **Todo test nuevo se cablea en `tests/run_all.py` en el mismo commit.** Un test que no
   corre en la regresión no cuenta como test.
7. **Procedencia del código por sesión.** Al iniciar una sesión se anota en
   `RUNBOOK-ESTADO.md` sobre qué commit se trabaja. Las referencias `archivo:línea`
   antiguas se localizan por nombre de función, nunca por número de línea a ciegas.

## 1. Trabajo en curso (definido fuera de este archivo)

- **Del operador:** probar `iargen.com/player/` en celular y Smart TV (antesala de F8);
  prueba futura del 1920 a más fps. El detalle vivo está en
  `RUNBOOK-ESTADO.md` §Próxima acción.

## 2. Tareas opcionales (no bloquean nada)

### E-11 — Flags de audio (OPCIONAL)

- En el HQ el audio es ~1 % del bundle; solo importa en perfiles de 320 columnas.
- **Archivo:** `backend/encoder.py` (llamada a ffmpeg del audio).
- **Acción:** exponer `--audio-bitrate`, `--audio-mono` y `--audio-samplerate`. Default
  sin cambios (`-q:a 4`).
- **Cierre:** el default produce audio byte-idéntico al actual. Δbytes: sí, solo si se usan.

### W-15 — Camino ASCII de Canvas2D (OPCIONAL)

- Solo afecta a los modos `ascii-*`, que el camino `pixel` de producción no usa. Se hace
  únicamente si los modos ASCII vuelven a ser objetivo del producto.
- **Archivo:** `frontend/render-canvas2d.js` (camino de glifos).
- **Acción:** cachear las cadenas `"rgb(r,g,b)"` por entrada de paleta y los
  `ramp.charAt(i)` en arrays; agrupar por color para minimizar cambios de `fillStyle`;
  limitar el redibujo a `dirtyY0..dirtyY1` (hoy ignora el dirty set).
- **Cierre:** salida visual idéntica; mejora medida.

## 3. Fases pendientes

### S-6 — Validación física (F8)

| ID | Tarea |
|---|---|
| F8-1 | `frontend/diagnostic-player.html`, ES5, separado de `tv-player.html` |
| F8-2 | Matriz física con las resoluciones de producto: **1280@15 v3** (producto), 768 y 640 de referencia, y el **1920** (directiva del operador: el front procesa cualquier resolución/fps; el 1920 se re-prueba a más fps); Canvas2D y WebGL1, 30 minutos |
| F8-3 | Go/no-go de v2/**v3** (`TV-02`) contra los artefactos **ya optimizados** |
| F8-4 | `MEM-001`: memoria por componente, con y sin overlay |
| F8-5 | Regenerar el artefacto de release **después** del último cambio de codec |

Gates físicos heredados de INT-002: costo p95 por frame del overlay nativo (decide si
INT-005 se implementa) y MEM-001 con y sin overlay.

**INT-005 (parches por época)** sigue **condicionado** (dirección del operador,
2026-08-30): el overlay nativo Canvas2D (texto + imagen sobre el mismo canvas,
INT-004/006/007) es la vía preferida; INT-005 solo se implementa si los gates físicos
de F8 muestran que el dibujo nativo por frame no rinde en el TV real.

**Sigue vetado hasta tener benchmark neto en TV:** `PAL5`/`PAL6` para el hueco de
17-255 colores por tile (candidato de una revisión de formato futura, estimación
25-37 % en tiles de gradiente; quedó fuera de F6 a propósito).

## 5. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa (CI en verde sobre su push);
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si es Δbytes, su fila está en el registro;
4. el commit lleva su ID;
5. si tocó el frontend, el gate ES5 ampliado pasa;
6. si tocó `inflate.js` o un reader, el fuzzing pasa.

## 6. Plantilla de fila de registro

```text
| ID | fecha | commit | referencia | parámetros | bytes .ascl | bytes .asclv |
  bytes/celda | keyframes | cadena delta máx | PSNR RGB | error Oklab |
  err_temporal | proxy_banding | SHA-256 | conclusión y alcance |
```

Una conclusión queda ligada a su configuración. Si cambia el modo, la grilla, los FPS, la
paleta, el dithering o el codec, se revalida.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por tarea,
actualizada al cerrar cada una. Ese archivo —no la memoria de nadie— es lo que le dice a
la próxima sesión dónde quedó todo.
