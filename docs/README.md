# Índice de documentación

Este índice separa el estado vigente de la evidencia histórica. Si dos documentos se
contradicen, prevalecen en este orden: especificación de formato, estado actual, roadmap
activo y registro de decisiones. Para la intervención matricial, el documento de diseño
prevalece sobre el resumen del §12 del roadmap. Los documentos históricos explican cómo se llegó a una
decisión, pero no definen el backlog ni los valores actuales.

## Vigentes

| Documento | Función |
|---|---|
| [`ESTADO-ACTUAL.md`](ESTADO-ACTUAL.md) | foto técnica de la versión candidata, objetivos cumplidos y límites |
| [`ASCL-format-spec.md`](ASCL-format-spec.md) | contrato binario normativo de ASCL/ASCLV v1 y v2 |
| [`HOJA-DE-RUTA-TECNICA-V2.md`](HOJA-DE-RUTA-TECNICA-V2.md) | backlog priorizado, dependencias y gates de aceptación |
| [`PLAN-IMPLEMENTACION-OPTIMIZACION.md`](PLAN-IMPLEMENTACION-OPTIMIZACION.md) | principios e invariantes de compatibilidad y eficiencia |
| [`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) | cola de optimización por fases, colisiones resueltas y protocolo de medición |
| [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) | ejecución tarea por tarea: archivos, líneas, verificación y criterio de cierre |
| [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md) | estado vivo de la ejecución: qué está cerrado, en curso y bloqueado, y sobre qué código |
| [`../CLAUDE.md`](../CLAUDE.md) | guía de arranque de sesión: orden de lectura post-compact, modelo de trabajo y ayuda-memoria de invariantes |
| [`ejecutados/`](ejecutados/README.md) | archivo de lotes cerrados con su evidencia; lo terminado sale del estado vivo y queda acá |
| [`MAPA-DEL-PROYECTO.md`](MAPA-DEL-PROYECTO.md) | grafo de composición, flujo, contratos e invariantes: el punto de entrada de una sesión nueva |
| [`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md) | diseño de INT-001: paleta reservada, glifos, slots, canal en vivo y runtime |
| [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md) | bitácora append-only: contexto, medición, conclusión y alcance por instancia |
| [`DESPLIEGUE.md`](DESPLIEGUE.md) | layout PHP/hosting, caché y archivos necesarios en el TV |
| [`PUBLICACION-GITHUB.md`](PUBLICACION-GITHUB.md) | qué entra al repositorio/release y decisiones pendientes antes del push |

## Diseño y evidencia de la versión actual

| Documento | Estado |
|---|---|
| [`DISENO-ASCL-V2-TILES.md`](DISENO-ASCL-V2-TILES.md) | diseño implementado de ASCLV2 exacto regional/predictivo |
| [`BENCHMARK-V2-HQ-768.md`](BENCHMARK-V2-HQ-768.md) | igualdad de 231/231 frames, audio exacto y tamaño final |
| [`BENCHMARK-V1-ADAPTATIVO-OKLAB.md`](BENCHMARK-V1-ADAPTATIVO-OKLAB.md) | origen de la matriz HQ 768 y decisiones de calidad offline |
| [`DISENO-PLANIFICADOR-REGIONAL-V2.md`](DISENO-PLANIFICADOR-REGIONAL-V2.md) | parte exacta implementada y parte near-lossless futura, claramente separadas |

## Históricos

- [`ASCILINE-contexto.md`](ASCILINE-contexto.md): contexto y alternativas iniciales.
- [`ESTADO-Y-CONTINUACION.md`](ESTADO-Y-CONTINUACION.md): handoff de sesiones tempranas;
  sus pendientes no son el estado actual.
- [`GENERAR-1080-Y-VARIANTES.md`](GENERAR-1080-Y-VARIANTES.md): receta de una campaña
  anterior, no el proceso de release vigente.
- [`BENCHMARK-CALIDAD-INICIAL.md`](BENCHMARK-CALIDAD-INICIAL.md),
  [`BENCHMARK-TKN-COLORES.md`](BENCHMARK-TKN-COLORES.md) y
  [`DISENO-DITHERING-SELECTIVO.md`](DISENO-DITHERING-SELECTIVO.md): evidencia que se
  conserva para trazabilidad.

Las herramientas offline activas y los helpers históricos están separados en
[`../backend/README.md`](../backend/README.md).

El resumen legible por versión está en [`../CHANGELOG.md`](../CHANGELOG.md). El detalle
de por qué una conclusión fue aceptada o descartada permanece en el registro append-only.
