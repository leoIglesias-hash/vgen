# Estado técnico actual

Fecha de corte: 2026-08-22. Referencia de publicación local:
`asclv2-exact-hq-v0.2`.

## Resumen

La versión actual es utilizable para la prueba física en Smart TV. El encoder produce
ASCLV1 por defecto y ASCLV2 exacto de forma opt-in. El frontend dual abre ambos formatos
con una sola matriz y los mismos renderers Canvas2D/WebGL1. Todo el trabajo perceptual
nuevo ocurre offline; el TV no ejecuta Oklab, K-means, detección de escenas ni dithering.

La implementación local está verificada, pero ASCLV2 todavía no se promueve como default:
en el clip HQ actual conserva exactamente la imagen y el audio, pero solo ahorra 5 bytes.
Falta medir CPU, RAM, p95 y cuadros descartados en los dispositivos físicos objetivo.

## Objetivos y estado real

| Objetivo rector | Estado | Evidencia | Límite pendiente |
|---|---|---|---|
| un solo archivo cacheable con audio | cumplido | envelopes `ASCLVID1/2`, `ascl_bundle.py`, readers | descarga completa; no streaming |
| FPS, celdas y colores editables | cumplido | CLI de `make_clip.py`, perfiles y overrides manuales | validar límites por familia de TV |
| mejor color sin lógica perceptual nueva en el TV | cumplido para esta instancia | K-means Oklab, paleta adaptativa y dither horneado | costo efectivo y valores pendientes de medición física |
| evitar escalas/banding manteniendo peso controlado | cumplido para el HQ probado | adaptativo 5..10 + dither auto; registro Instancia 003 | presupuesto de dither por bytes aún pendiente |
| frontend retrocompatible | cumplido localmente | sintaxis ES5, XHR, TypedArrays, Canvas2D/WebGL1; suite global de compatibilidad | prueba en WebViews físicos |
| Canvas2D y WebGL con igual función | cumplido localmente | una matriz, una API dirty, mismos frames | medir costo real por renderer |
| reducir RAM/asignaciones de reproducción | parcialmente cumplido | scratch, bitsets y buffers reutilizables | inventario MEM-001 en TV |
| formato v2 exacto que nunca crece frente a su v1 | cumplido | selección por bytes y fallback v1 por frame | ganancia del HQ actual no es material |
| renovación del archivo con nombre estable | parcialmente cumplido | menú `MENU`, token y revalidación XHR | ETag/cabeceras PHP y caché fría/caliente |
| intervención matricial durante playback | pendiente | solo contrato preliminar en el roadmap | metadata, formato y runtime de slots |
| carga parcial/streaming | diferido | no forma parte del envelope v2 actual | solo se estudia si MEM-001 demuestra necesidad |

## Artefacto de referencia local

`outputs/clip.asclv` es el clip de prueba física y no forma parte del árbol Git.

| Propiedad | Valor |
|---|---:|
| envelope | ASCLVID2 |
| grilla | 768 x 432 |
| cuadros / FPS | 231 / 15 |
| tamaño | 17.935.305 B |
| audio incluido | 180.857 B |
| SHA-256 | `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A` |

El nombre original del benchmark fue
`TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv`; `clip.asclv` es únicamente el nombre
estable esperado por `tv-player.html`. El binario no se renombró internamente ni perdió
audio. Si se confirman los derechos, para GitHub se adjunta como asset de un release y no
se incorpora al historial de código.

## Código y verificación

- Backend Python: encoder v1, paletas perceptuales/adaptativas, dithering, bundle,
  transcode/decoder v2 y herramientas de benchmark.
- Frontend sin dependencias: readers v1/v2, factory, inflate ES5, Canvas2D, WebGL1,
  player tradicional y player TV.
- Seguridad del parser: límites de dimensiones/inflate, CRC, offsets, bloques, paletas,
  tags, padding e índices; los frames se validan antes de consolidar cambios.
- Regresión actual: 115 pruebas Python y 11 suites JavaScript.
- CI configurada: una clonación limpia ejecuta `python tests/run_all.py`; el clip de
  producto es opcional allí y obligatorio con `--require-release-artifact` antes de un
  release. La primera corrida remota queda pendiente del push.

## Próximo gate técnico

El siguiente paso no es agregar otro codec. Es ejecutar VAL-001/TV-02 en los Smart TV
reales con 640 y 768, tanto en Canvas2D como en WebGL1. La medición decide si:

1. 768 puede ser el perfil general;
2. ASCLV2 queda opt-in, especializado o promovido;
3. el límite real es decode, upload, Canvas, memoria del XHR o caché;
4. corresponde priorizar intervención matricial o investigar carga parcial.

Hasta obtener esa evidencia, v1 continúa como default del encoder y v2 es una revisión
exacta disponible, no una promesa de menor CPU o RAM en todos los equipos.
