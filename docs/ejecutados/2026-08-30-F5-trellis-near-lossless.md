# F5 — carril trellis (E-19..E-24) + INT-007 · cerrado 2026-08-30

Resultado neto: el producto pasa de 17.168.633 B (sin dither, pre-trellis) a
**11.304.137 B = 29,0 % del mp4 fuente** (−34 % por −0,53 dB; aún +0,81 dB sobre P-02).
Producto final: `b081f4ba…f6a05e` (35,10 dB, Oklab 0,00897), receta = defaults del
workflow `encode` con `extra = --palette-refit 5 --near-lossless 8`.

## Qué quedó implementado

| Tarea | Qué | Commit | Adopción |
|---|---|---|---|
| E-19 | `backend/trellis.py`: `CANONICAL_STAGES` (quantize→dither→trellis→emit) como dato importable; `--threshold` absorbido como caso degenerado del trellis. Refactor puro, byte-identidad verificada | commit E-19 | n/a (sin cambio de bytes) |
| E-20 | `--threshold-metric {rgb,oklab}` (default `rgb`, regla 9); paleta convertida una vez por paleta — Oklab no cuesta más por frame | commit E-20 | sin fila (no cambia recetas) |
| E-21 | `COST_LADDER` (proxy entropía / zlib-9 finalista / Zopfli solo al campeón): la ELECCIÓN de candidatos ya no depende del entorno; wall del encode −54 % por +0,012 % de bytes | `7e6fd8e` | **ADOPTADA** (Instancia 024) |
| E-22 | trellis temporal: índice del frame anterior como segundo candidato bajo presupuesto de error extra (métrica E-20); la celda sale del DELTA | `9ab95f6` | **ADOPTADA, presupuesto 4** (−25,2 % bytes por −0,04 dB; Instancia 025, dos decisiones del operador el mismo día) |
| E-23 | trellis espacial: fusionar el valor más raro del tile cruza a un opcode más barato del regional v2; forzado en el encoder, transcode sigue lossless | `626694a` | opt-in `--trellis-spatial`; sin adopción en solitario (−0,32 %; Instancia 026) |
| E-24 | `--near-lossless N` (temporal+espacial al mismo presupuesto, 0 = byte-idéntico, no se mezcla con flags explícitos) + columnas `err_temporal` y `proxy_banding` en `bench_ref.py` | `29ad7f8`+`271dd19` | **ADOPTADA, presupuesto 8** (decisión del operador 2026-08-30: «mínima pérdida pero aceptable»; Instancia 027) |
| INT-007 | `weight`/`shadow` en `textlayer.js` (sombra translúcida, derrame < 1 celda) + logo girando como ruleta simulada (ángulo determinista por frame, caja sucia circunscripta) | `faf2390` | verificado en navegador; la ruleta REAL sigue en F6 |

## Propiedades que protege la regresión

- Todos los flags nuevos con default 0/None = **bytes byte-idénticos** (tests de identidad).
- `apply_*_trellis` nunca muta su argumento (transaccionalidad, invariante 4).
- Dither protegido del trellis y del threshold (E-18).
- Sin Zopfli la salida es byte-idéntica a la histórica (pata de CI propia).
- Suites: `test_trellis_order` (16), `test_cost_ladder` (11), `test_trellis_temporal` (9),
  `test_trellis_spatial` (10), `test_near_lossless` (7), `test_bench_ref` (11).

## Decisiones del operador que marcaron el carril

1. Dither **off** (E-17, 2026-08-29): sin diferencia visible, gana el ahorro.
2. Temporal 2 → 4 el mismo día: «el más agresivo se ve perfecto».
3. Near-lossless 8 (2026-08-30): primera vez que acepta una pérdida VISIBLE a conciencia
   («se nota una mínima pérdida pero es aceptable»). Su criterio evolucionó a
   «pérdida mínima aceptable si el ahorro lo vale».

Evidencia detallada: Instancias 023–027 del REGISTRO. SHAs de todos los candidatos:
`RUNBOOK-ESTADO.md` §Referencias de clips.
