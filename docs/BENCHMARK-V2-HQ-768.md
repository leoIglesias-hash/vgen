# Benchmark exacto ASCLV2 — HQ 768

Fecha: 2026-08-14. Estado: verificación local final; validación física TV pendiente.

## Objetivo

Comprobar la primera revisión ASCLV2 sin evaluación visual: mismo video cuantizado,
misma paleta visible, mismos frames RGBA y mismo audio. La única variable es la
representación binaria interna de la matriz.

## Artefactos

| Variante | Archivo | Bytes | SHA-256 |
|---|---|---:|---|
| V1 aprobado | `TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv` | 17.935.310 | `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70` |
| V2 exacto | `TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv` | 17.935.305 | `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A` |

Ambos contienen 768×432, 231 frames, 15 FPS y audio MP3 de 180.857 B.

## Protocolo reproducible

Entorno de esta corrida: Windows, Python 3.12.13 y Node.js 24.19.0. Base V1 en Git:
`abb0451`; la revisión V2 queda identificada por el tag Git de esta entrega.

```powershell
python backend/ascl_v2.py `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv

node backend/verify_v1_v2.js `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv

python backend/benchmark_quality_v1.py --decode-repeats 0 `
  v1=outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  v2=outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv
```

La primera orden verifica en Python cada candidato regional/predictivo contra la matriz
original antes de aceptarlo. La segunda usa los readers JavaScript reales y compara
RGBA cuadro por cuadro, además del audio. La tercera inspecciona estructura, CRC y tags.

## Resultado

| Variante | ASCL interior | Tags R/Z/D/M | Regional Kraw/Kz/Draw/Dz | Predictor Kz/Dz |
|---|---:|---:|---:|---:|
| V1 | 17.754.437 B | 0/89/1/141 | 0/0/0/0 | 0/0 |
| V2 | 17.754.432 B | 0/89/0/141 | 0/0/1/0 | 0/0 |

- RGBA idéntico en 231/231 frames entre ReaderV1 y ReaderV2.
- Audio idéntico byte por byte: 180.857 B.
- CRC interior válido en ambas versiones.
- Regresión final: 108 pruebas Python y 10 suites JavaScript, todas aprobadas.
- V2 reemplazó un DELTA por `REGIONAL_DELTA_RAW`; los otros 230 payloads conservaron
  su representación v1 porque ninguna alternativa exacta era estrictamente menor.
- Ahorro final: 5 B. No hubo aumento de archivo.

## Interpretación y límite

El HQ 768 ya estaba optimizado con DELTA_MASK y paletas adaptativas; por eso este clip no
ofrece regiones suficientemente ventajosas. El resultado valida el comportamiento más
importante del transcodificador: nunca acepta una alternativa peor y no cambia calidad.
No demuestra una mejora de CPU en Smart TV. Esa decisión requiere TV-02 sobre Canvas2D y
WebGL1 reales; hasta entonces V1 sigue siendo el default y V2 permanece opt-in.

El remap exacto de IDs se midió aparte y no se incorporó: ahorraba 0,9569% estimado pero
introducía 94 frames predictivos, una relación insuficiente sin medir CPU/drops físicos.
