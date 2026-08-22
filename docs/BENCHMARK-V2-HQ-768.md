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

En el árbol actual, el V2 exacto existe localmente como `outputs/clip.asclv` y está
ignorado por Git. El V1 se recupera desde el tag `asclv2-exact-hq-v0.1`; los comandos de
abajo restauran solo ese V1 y generan nuevamente el V2 con su nombre lógico. Para una
publicación, el V2 aprobado se adjunta al release únicamente si se confirman sus derechos.

## Protocolo de regeneración condicionado

Este protocolo es reproducible solo donde el tag v0.1 y su V1 estén autorizados y
disponibles. Si la publicación pública usa una historia saneada sin esos binarios, esta
sección conserva trazabilidad histórica; no debe prometerse regeneración desde ese clon.

Entorno de esta corrida: Windows, Python 3.12.13 y Node.js 24.19.0. Base V1 en Git:
`abb0451`. La implementación v2 verificada corresponde al commit `ad4b6b7`, tag
`asclv2-exact-hq-v0.1`; el cierre de publicación queda en `asclv2-exact-hq-v0.2`.

```powershell
git restore --source asclv2-exact-hq-v0.1 --worktree -- `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv

python backend/ascl_v2.py `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv

node backend/verify_v1_v2.js `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv

python backend/benchmark_quality_v1.py --decode-repeats 0 `
  v1=outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv `
  v2=outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv

Get-FileHash -Algorithm SHA256 `
  outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv, `
  outputs/TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv
```

`git restore` materializa el control histórico sin alterar el índice. La conversión
verifica en Python cada candidato regional/predictivo contra la matriz original antes de
aceptarlo. Node usa los readers JavaScript reales y compara RGBA cuadro por cuadro, además
del audio. El benchmark inspecciona estructura, CRC y tags; el último paso debe coincidir
con los dos SHA-256 de la tabla.

## Resultado

| Variante | ASCL interior | Tags R/Z/D/M | Regional Kraw/Kz/Draw/Dz | Predictor Kz/Dz |
|---|---:|---:|---:|---:|
| V1 | 17.754.437 B | 0/89/1/141 | 0/0/0/0 | 0/0 |
| V2 | 17.754.432 B | 0/89/0/141 | 0/0/1/0 | 0/0 |

- RGBA idéntico en 231/231 frames entre ReaderV1 y ReaderV2.
- Audio idéntico byte por byte: 180.857 B.
- CRC interior válido en ambas versiones.
- Regresión del cierre v0.1: 108 pruebas Python y 10 suites JavaScript aprobadas.
- Regresión de publicación v0.2: 115 pruebas Python y 11 suites JavaScript aprobadas,
  incluido el smoke real con el video sintético versionado.
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
