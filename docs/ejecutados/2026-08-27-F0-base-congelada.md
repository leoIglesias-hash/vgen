# F0 — Base congelada (carril E) · cerrado 2026-08-27

Fase F0 del plan: dejar el encoder sobre una base reproducible y endurecida antes de
optimizar nada. Cerrada junto con la preparación P-01..P-04 y el punto de sincronización
S-1.

## Qué quedó cumplido

| ID | Qué | Evidencia |
|---|---|---|
| P-01 | Línea base y regresión en verde antes de tocar código | regresión 115+11 en verde sobre baseline `5493455` |
| P-02 | Referencia sintética congelada | `synthetic.baseline` SHA `c29e7728…5d1d7`; tras E-01 el canónico kmeans-rgb con cv2 pasó a `9cc88e55…` (ver bitácora). **El HQ sigue pendiente** |
| P-03 | `tools/bench_ref.py`: fila de medición determinista por artefacto | commit `bfa2a1f`; PSNR/Oklab con `--source` verificados |
| P-04 | Zopfli como dependencia opcional con fallback a zlib | commit `bf8cd58`; regresión pasa con y sin zopfli |
| E-01 | Paleta kmeans-rgb reproducible: `lexsort` en ambas ramas (OpenCV y NumPy) | commit `6b6b65a`; RGB byte-idéntico 40/40 frames; test de paridad de ramas |
| E-02 | Herramientas offline endurecidas (7 validaciones + 6 fixtures de corrupción) | commit `d3f2bfd`; un `.ascl` corrupto ahora falla en vez de decodificar |
| S-1 | Merge de F0 a la base | historial lineal en `main`, equivale al merge |

## Decisiones que siguen vigentes

- E-01 **cambió el SHA canónico** de artefactos kmeans-rgb generados con OpenCV (la
  paleta sale ordenada); el RGB reconstruido es idéntico. Toda comparación futura usa el
  SHA nuevo.
- El fixture de `test_benchmark_quality_v1` se corrigió de flags per-frame a per-scene:
  la combinación per-frame + DELTA_MASK no la admite la spec y el decoder endurecido la
  rechaza.
- Regla 7 operativa desde acá: todo test nuevo se cablea en `tests/run_all.py` y CI en el
  mismo commit.

## Lo que NO quedó cerrado de esta zona

- **P-02 parcial:** el HQ de producción no se congeló (el binario no estaba en el
  snapshot). El clip fuente real está disponible localmente en
  `inputs/TKN-2443-GANADOR- 15seg-.mp4` (no se commitea); congelar el HQ requiere un
  entorno con Python (la máquina de trabajo actual valida solo por CI).

Regresión al cierre del lote: **125 pruebas Python y 13 suites JavaScript en verde**
(base previa: 115 y 11).
