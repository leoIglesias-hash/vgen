# Índice de documentación

Reorganizado el **2026-09-01** (H-0, nace ASCILINE-hybrid): los diseños y planes
del paradigma 100 % JS se movieron **verbatim** a [`historico/`](historico/README.md)
(sin pérdida; antes de eso, las podas 2026-08-30/31 dejaron lo retirado en el
historial Git). Si dos documentos se contradicen, prevalecen en este orden:
spec de formato → estado de ejecución → diseño vigente → registro de decisiones.

## Para trabajar (en este orden)

| Documento | Función |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | arranque de sesión: paradigma híbrido, modelo de trabajo, invariantes, estado grueso |
| [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md) | **el archivo vivo**: próxima acción y máster de producto arriba, tabla de tareas de la fase H, referencias de clips por SHA, bitácora al final |
| [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) | reglas de ejecución + las tareas de la fase H (H-1..H-3, W-26) |
| [`ejecutados/`](ejecutados/README.md) | resumen por fase cerrada (paradigma anterior) con su evidencia; se consulta, no se relee |
| [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md) | bitácora append-only: el porqué de cada decisión y cada medición, incluida la decisión de dirección del 2026-09-01 |

## Diseño de lo que está en obra (fase H)

| Documento | Función |
|---|---|
| `DISENO-HIBRIDO.md` | **H-1, todavía no existe**: sincronía intervención↔video, viaje del sidecar, distribución CACHE-001 del mp4, fallback. Se escribe antes que cualquier código de H-3 |

## Referencia técnica (sigue vigente en el híbrido)

| Documento | Función |
|---|---|
| [`ASCL-format-spec.md`](ASCL-format-spec.md) | contrato binario normativo del **máster** ASCL/ASCLV (v1/v2; envelope v3 en el REGISTRO de F6) |
| [`MAPA-DEL-PROYECTO.md`](MAPA-DEL-PROYECTO.md) | grafo de composición, flujo, contratos e invariantes (escrito para el paradigma anterior; su parte de encoder sigue válida) |
| [`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md) | la intervención: paleta reservada, slots, canal en vivo, runtime — la capa que sobrevive encima del video |
| [`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md) | ASCLSLOT v2, parches, texto nativo (INT-003/004) — referenciado por el código del overlay |
| [`DESPLIEGUE.md`](DESPLIEGUE.md) | layout de hosting estático, cabeceras y caché para el TV |

## Histórico

| Documento | Función |
|---|---|
| [`historico/`](historico/README.md) | los 9 diseños/planes/runbook del paradigma JS, verbatim, con README que dice qué fue cada uno y en qué estado se archivó (F9 ejecutada; F10/F11 suspendidas sin ejecutar; etc.) |

Las herramientas offline y helpers están en [`../backend/README.md`](../backend/README.md);
el resumen por versión en [`../CHANGELOG.md`](../CHANGELOG.md). Los documentos
retirados el 2026-08-30 (pre-histórico) siguen recuperables del historial Git
(`git log --diff-filter=D -- docs/`).
