# Checkpoint técnico — runtime TV v1

Fecha: 2026-08-14

Rama: `feature/quality-optimization`

Base al iniciar esta etapa: `5f0d983`

Este checkpoint existe para poder retomar sin depender del historial del chat. No es una
decisión final ni reemplaza la hoja de ruta o el registro append-only.

## Implementado

- menú técnico oculto de renovación de `./outputs/clip.asclv`, tecla 9 moderna y hotspot;
- liberación de audio, Blob, reader, Canvas y GPU antes de volver a descargar;
- reader v1 sin arrays de offsets por frame, keyframes en bitset y validación defensiva;
- inflater zlib ES5 acotado con salida directa a scratch reutilizable;
- bitset exacto de celdas modificadas y conversión RGBA incremental común;
- Canvas2D y WebGL1 con actualizaciones parciales y fallback completo seguro;
- fallback WebGL→Canvas durante reproducción sin reiniciar frame, audio ni RAF;
- `dispose()` explícito y manejo de `webglcontextlost`;
- diseño técnico del planificador regional v2 lossless/near-lossless inspirado solo en
  conceptos útiles de WebP, sin incorporar su decoder;
- documentación de despliegue PHP/Apache y layout de la ruta relativa estable.

## Evidencia antes del checkpoint

- 67/67 pruebas Python verdes;
- 7/7 suites JavaScript verdes;
- HQ 768 intacto: 17.935.310 B;
- SHA-256 HQ intacto:
  `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`;
- ningún archivo de `outputs/` forma parte del diff;
- auditoría independiente sin blockers P0/P1.

## Único ajuste pendiente antes del cierre final

El reader nuevo exige actualmente offsets DELTA estrictamente ascendentes, aunque la spec
v1 histórica no fijaba ese orden y el reader anterior aceptaba cualquier orden. Para
preservar compatibilidad binaria hay que:

1. validar primero que todos los offsets estén dentro de la matriz y que todos los valores
   sean válidos;
2. aceptar offsets desordenados;
3. aceptar repetidos con semántica explícita **última escritura gana**;
4. calcular `dirtyY0/dirtyY1` por mínimo/máximo y contar cada celda dirty una sola vez;
5. agregar una prueba con offsets `[7, 2, 7]`;
6. ajustar `docs/ASCL-format-spec.md`, quitando la restricción ascendente recién agregada;
7. repetir las 67 pruebas Python, las 7 suites JS, hash y `git diff --check`.

Después: crear commit final limpio y tag local `tv-runtime-hq-v1`.
