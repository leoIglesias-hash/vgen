# Índice de documentación

Podado el 2026-08-30 y limpiado el 2026-08-31 (cierre de F6/S-4 y S-7): lo que no está
acá se retiró del árbol y vive en el historial Git (`git log --diff-filter=D -- docs/`
lo lista); las tablas de tareas cerradas del runbook de estado se archivaron **verbatim**
en `ejecutados/` (sin pérdida). Si dos documentos se contradicen, prevalecen en este
orden: spec de formato → estado de ejecución → diseño vigente → registro de decisiones.

## Para trabajar (en este orden)

| Documento | Función |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | arranque de sesión: orden de lectura, modelo de trabajo, invariantes, estado grueso |
| [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md) | **el archivo vivo**: próxima acción y receta de producto arriba, resumen de carriles cerrados, tabla de fases, referencias de clips por SHA, bitácora vigente al final |
| [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) | reglas de ejecución + SOLO las tareas pendientes (F8/S-6, opcionales E-11/W-15) |
| [`ejecutados/`](ejecutados/README.md) | resumen por fase cerrada con su evidencia + tablas de tareas y bitácora 2026-08-27..30 archivadas verbatim; se consulta, no se relee |
| [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md) | bitácora append-only por Instancia: el porqué de cada decisión y cada medición |

## Diseño de lo que está en obra (plan del 2026-08-31, Instancia 030)

| Documento | Función |
|---|---|
| [`DISENO-RENDER-INDEXADO.md`](DISENO-RENDER-INDEXADO.md) | **F9**: LUT `Uint32`, textura de índices con lookup en el shader, reconstrucción de 4 taps, cadencia y pre-decode. No toca el formato |
| [`DISENO-PERDIDA-ADAPTATIVA.md`](DISENO-PERDIDA-ADAPTATIVA.md) | **F10**: repartir la pérdida según el mapa de suavidad en vez de en partes iguales (el banding solo se ve en zonas suaves) |
| [`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md) | **F11**: resolución por tile (LOD) y transparencia (paleta RGBA), agrupadas en una sola revisión de formato |

## Referencia técnica

| Documento | Función |
|---|---|
| [`ASCL-format-spec.md`](ASCL-format-spec.md) | contrato binario normativo de ASCL/ASCLV v1 y v2 |
| [`MAPA-DEL-PROYECTO.md`](MAPA-DEL-PROYECTO.md) | grafo de composición, flujo, contratos e invariantes |
| [`DISENO-ASCL-V2-TILES.md`](DISENO-ASCL-V2-TILES.md) | diseño implementado de ASCLV2 exacto regional/predictivo |
| [`DISENO-PLANIFICADOR-REGIONAL-V2.md`](DISENO-PLANIFICADOR-REGIONAL-V2.md) | selección píxel/máscara/bloque del regional v2 |
| [`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md) | diseño de la intervención: paleta reservada, slots, canal en vivo, runtime |
| [`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md) | ASCLSLOT v2, parches, texto nativo (INT-003/004) e INT-005 por época |
| [`DESPLIEGUE.md`](DESPLIEGUE.md) | layout de hosting estático, cabeceras y caché para el TV |

## Roadmap y principios (consultados, mayormente consumidos)

| Documento | Función |
|---|---|
| [`HOJA-DE-RUTA-TECNICA-V2.md`](HOJA-DE-RUTA-TECNICA-V2.md) | backlog priorizado original y gates; F0-F5/F7 ya ejecutadas — el estado real está en el runbook de estado |
| [`PLAN-IMPLEMENTACION-OPTIMIZACION.md`](PLAN-IMPLEMENTACION-OPTIMIZACION.md) | principios e invariantes de compatibilidad y eficiencia |
| [`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) | cola de optimización por fases y protocolo de medición |

Las herramientas offline y helpers están en [`../backend/README.md`](../backend/README.md);
el resumen por versión en [`../CHANGELOG.md`](../CHANGELOG.md).

Retirados el 2026-08-30 (recuperables del historial Git): `ESTADO-ACTUAL`,
`ESTADO-Y-CONTINUACION`, `ASCILINE-contexto`, `GENERAR-1080-Y-VARIANTES`,
`BENCHMARK-CALIDAD-INICIAL`, `BENCHMARK-TKN-COLORES`, `BENCHMARK-V1-ADAPTATIVO-OKLAB`,
`BENCHMARK-V2-HQ-768`, `DISENO-DITHERING-SELECTIVO`, `PUBLICACION-GITHUB`. Sus menciones
en el REGISTRO son históricas y se conservan tal cual (append-only).
