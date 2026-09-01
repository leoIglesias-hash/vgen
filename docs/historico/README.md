# Histórico — el paradigma 100 % JS (ASCILINE-video, 2026-08-27 .. 2026-09-01)

Este directorio guarda **verbatim** los diseños y planes del paradigma anterior:
el `.asclv` viajaba al TV y un player 100 % JS lo decodificaba y pintaba cuadro a
cuadro. Ese paradigma quedó **superado el 2026-09-01** por decisión del operador,
tras el diagnóstico DIAG-002/003 en la TV box real: el player JS no llega a 15 fps
en esas cajas (cuello CPU), mientras que el mismo producto decodificado a H.264 y
reproducido por `<video>` hardware **«reproduce muy bien»** — y pesa 6× menos.

Nada de esto se borra ni se reescribe: es la evidencia de cómo se llegó al look
del producto y la referencia de un codec que **sigue vivo como máster offline**
(el `.asclv` sigue siendo la salida canónica del encoder; el mp4 de distribución
se emite desde él). Se consulta, no se retoma sin decisión del operador.

| Documento | Qué era | Estado al archivarse |
|---|---|---|
| [`RUNBOOK-IMPLEMENTACION-asclv-js.md`](RUNBOOK-IMPLEMENTACION-asclv-js.md) | runbook de tareas del paradigma JS (F10, F11, F8, DIAG-001, opcionales) | F9 cerrada; F10/F11/F8/DIAG-001 **suspendidas** por el cambio de dirección |
| [`DISENO-RENDER-INDEXADO.md`](DISENO-RENDER-INDEXADO.md) | F9: LUT `Uint32`, textura de índices, cadencia, pre-decode | **ejecutado completo** (W-16..W-25, CI verde, publicado) |
| [`DISENO-PERDIDA-ADAPTATIVA.md`](DISENO-PERDIDA-ADAPTATIVA.md) | F10: pérdida modulada por suavidad (anti-banding) | **suspendido sin ejecutar** — re-evaluable: el mp4 hereda los píxeles del `.asclv`, así que la calidad del máster sigue importando |
| [`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md) | F11: formato v4 (LOD por tile, transparencia, solo-paleta) | **suspendido sin ejecutar** — su motivación principal (aliviar el decoder JS) desapareció con el híbrido |
| [`DISENO-ASCL-V2-TILES.md`](DISENO-ASCL-V2-TILES.md) | diseño implementado del codec regional/predictivo v2 | ejecutado; el contrato normativo vive en `../ASCL-format-spec.md` |
| [`DISENO-PLANIFICADOR-REGIONAL-V2.md`](DISENO-PLANIFICADOR-REGIONAL-V2.md) | selección píxel/máscara/bloque del regional v2 | ejecutado |
| [`HOJA-DE-RUTA-TECNICA-V2.md`](HOJA-DE-RUTA-TECNICA-V2.md) | backlog priorizado original | consumido (F0-F9) |
| [`PLAN-IMPLEMENTACION-OPTIMIZACION.md`](PLAN-IMPLEMENTACION-OPTIMIZACION.md) | principios e invariantes del carril de optimización | consumido; los invariantes que sobreviven están en `../../CLAUDE.md` |
| [`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) | cola de optimización por fases + protocolo de medición | consumido |

La evidencia de ejecución de todo esto está donde siempre:
[`../ejecutados/`](../ejecutados/README.md) (resúmenes por fase) y
[`../REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](../REGISTRO-DE-PRUEBAS-Y-DECISIONES.md)
(porqués, append-only). El diagnóstico que motivó el cambio: REGISTRO, entradas
DIAG-002/003 del 2026-08-31 .. 2026-09-01.
