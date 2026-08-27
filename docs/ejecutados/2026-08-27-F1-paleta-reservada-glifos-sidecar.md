# F1 — Paleta reservada, glifos y sidecar (E-03..E-07) · cerrado 2026-08-27

La base completa de la intervención matricial (INT-001) del lado encoder: el video puede
reservar entradas de paleta que ningún camino toca, los dígitos existen como glifos
horneados, y la metadata de slots viaja validada de punta a punta.

## Qué quedó cumplido

| ID | Qué | Evidencia |
|---|---|---|
| E-03 | `reserved` cableado por las 9 funciones de la cadena de paleta, default 0 | `08234f1`; byte-identidad con `reserved=0` en los tres caminos (test); `pal_size >= reserved+22` |
| E-04 | Exclusión del rango reservado | `8badec4`+`c6e55a8`; reserva centralizada en `make_global_palette` (base + `reserved_colors` estampadas, INV-4); cuantizadores, `pal_img` y PairLUT del dither solo ven la base (INV-3 por construcción); test 4 estrategias × 4 modos + dither. El CI atrapó el desajuste dither/LUT y se corrigió |
| E-05 | Rects protegidos en el dither | `7879f05`; `protected_rects` en `selective_tile_mask` y `apply_selective_dither`; ninguna celda dentro de un rect se trama; sin rects, byte-idéntico |
| E-06 | Horneado de glifos (`tools/bake_glyphs.py`) | `bc57e04`+`b0c2058`; supersample 8×, cobertura normalizada al pico (entera), índices 246..251, glifo 10 transparente; dos corridas byte-idénticas (`cmp` en CI); tabla 8×12 SHA `2ee438f4…042c`; **inspección visual aprobada** (registro Instancia 009) |
| E-07 | Sidecar `ASCLSLOT` (`tools/make_slots.py` + `frontend/slots.js`) | `1d46353`; formato §7.1 con `slot_id` implícito por índice (13 B/slot); validador Python y espejo ES5 con veredictos idénticos sobre fixtures compartidos; las 7 restricciones de §6.3 + `reserved_rgb` con un fixture negativo cada una; sin carga parcial |

## Decisiones que siguen vigentes

- **La reserva se resuelve en `make_global_palette`**: los builders de bajo nivel
  (`_kmeans_rgb_palette`, `build_perceptual_palette`) reciben `pal_size` ya reducido y
  rechazan `reserved>0` directo (guard de mal uso permanente).
- `reserved_colors` son **RGB fijos declarados por el operador** (sin defaults
  inventados); la validación cruzada del sidecar (`reserved_rgb`) impide servir un
  sidecar viejo con un video nuevo.
- La cobertura de glifos se **normaliza al pico de cada glifo** antes de cuantizar:
  trazos más finos que una celda igual alcanzan "texto pleno". La tabla depende de la
  fuente del entorno emisor: regenerar y registrar SHA al emitir la de producción.
- En el sidecar el `slot_id` es el índice de la tabla (así los 13 B/slot de la spec
  cierran); los campos referencian esos índices.
- Los fixtures del sidecar se generan desde **un solo builder** (Python) y ambos
  validadores deben dar el mismo veredicto: la suite JS lee lo que volcó la suite Python
  (`tests/fixtures/slots-generated/`, ignorado por git).

## Mediciones asociadas

- Registro Instancia 007: referencia HQ reproducible (workflow `encode`).
- Registro Instancia 009: tabla de glifos de referencia y su inspección.

Lo que NO entra en F1: el runtime del overlay (F7, bloqueado por W-13) y el transporte
`ASCLVID3` (F6). El sidecar es transitorio hasta esa revisión de formato.
