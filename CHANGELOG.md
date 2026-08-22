# Historial de versiones

Este resumen enumera hitos recuperables. Las métricas, causas y límites completos están
en [`docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md).

## asclv2-exact-hq-v0.2 — 2026-08-22

- Conserva ASCLV2 exacto y el frontend dual de v0.1 sin cambiar el codec.
- Deja el workspace de release con un único artefacto local estable en `outputs/`:
  `clip.asclv`; el binario está ignorado y no forma parte del checkout del tag.
- Hace visible el acceso translúcido `MENU` para renovar el video/caché sin cambiar el
  nombre base.
- Separa estado vigente, roadmap, evidencia histórica y checklist de publicación.
- Agrega una orden única de regresión y CI para clones sin artefactos de producto.
- Publica el bundle de forma atómica conservando permisos del servidor y aísla los
  intermedios del encoder para no sobrescribir sidecars del usuario.
- Retira helpers pickle heredados que no pertenecían al pipeline vigente.

Conclusión: es el candidato correcto para publicar el código y comenzar la validación
física. No promueve v2 sobre v1 por rendimiento; esa decisión continúa detrás de TV-02.

## asclv2-exact-hq-v0.1 — 2026-08-14

- Implementa ASCLV2 regional/predictivo exacto con tiles de 16 y fallback v1 por frame.
- Agrega ReaderV2 ES5 y factory común para Canvas2D/WebGL1.
- Verifica 231/231 frames RGBA y 180.857 B de audio byte-exactos.
- Reduce el HQ de 17.935.310 a 17.935.305 B.

Conclusión: se acepta la seguridad de no crecimiento y la compatibilidad exacta; el ahorro
de 5 B no justifica convertir v2 en default sin métricas físicas.

## tv-runtime-hq-v1 — 2026-08-14

- Endurece ReaderV1/inflate y reutiliza scratch, bitsets y buffers.
- Convierte solo celdas modificadas y comparte el mismo dirty state entre renderers.
- Agrega fallback WebGL a Canvas sin perder reader, frame ni reloj de audio.

Conclusión: reduce asignaciones y trabajo medido en PC sin modificar el ASCLV; las cifras
no se extrapolan a Smart TV hasta VAL-001.

## tkn-adaptive-oklab-hq-v1 — 2026-08-12

- Introduce K-means Oklab, paleta adaptativa 5..10, estabilidad temporal y dither auto.
- Selecciona 768x432 como candidato HQ y mantiene 640 como perfil eficiente.

Conclusión: mejora gradientes y detalle para la instancia TKN sin agregar lógica
perceptual al TV. El costo efectivo de la matriz resultante aún requiere medición física;
los valores son editables y no constituyen un default universal.

## tkn-kmeans-block5-v1 — 2026-08-12

- Reduce el bloque de paleta de 30 a 5 frames para atacar escalas visibles.

Conclusión: mejoró banding medible a cambio de mayor peso y más frames completos; luego
fue reemplazado por cortes adaptativos basados en cambio numérico de color.

## tv-demo-kmeans-v1 — 2026-08-11

- Agrega el player TV fullscreen y selecciona K-means RGB frente a median-cut para la
  primera demo de color.

Conclusión: confirmó que más trabajo offline podía mejorar calidad y peso sin aumentar
el costo algorítmico del reproductor.
