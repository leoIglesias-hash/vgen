# Índice de documentación

Este índice separa el estado vigente de la evidencia histórica. Si dos documentos se
contradicen, prevalecen en este orden: especificación de formato, estado actual, roadmap
activo y registro de decisiones. Los documentos históricos explican cómo se llegó a una
decisión, pero no definen el backlog ni los valores actuales.

## Vigentes

| Documento | Función |
|---|---|
| [`ESTADO-ACTUAL.md`](ESTADO-ACTUAL.md) | foto técnica de la versión candidata, objetivos cumplidos y límites |
| [`ASCL-format-spec.md`](ASCL-format-spec.md) | contrato binario normativo de ASCL/ASCLV v1 y v2 |
| [`HOJA-DE-RUTA-TECNICA-V2.md`](HOJA-DE-RUTA-TECNICA-V2.md) | backlog priorizado, dependencias y gates de aceptación |
| [`PLAN-IMPLEMENTACION-OPTIMIZACION.md`](PLAN-IMPLEMENTACION-OPTIMIZACION.md) | principios e invariantes de compatibilidad y eficiencia |
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
