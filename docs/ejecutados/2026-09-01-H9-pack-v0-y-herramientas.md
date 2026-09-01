# 2026-09-01 — H-9 cerrada: el pack v0, sus herramientas y su publicación

Resumen operativo de lo cerrado. El **porqué** de cada decisión está en el
[REGISTRO](../REGISTRO-DE-PRUEBAS-Y-DECISIONES.md) (entradas del 2026-09-01); las
suposiciones vivas están en [`../EMISION-V0.md`](../EMISION-V0.md).

## Qué quedó hecho

**H-9 — el primer video del formato.** Emitido desde el máster
`dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a`
(1280×720, 15 fps, **231 cuadros**), workflow `emitir-v0`, run **33566441576**.

| Pieza | Bytes | vs. Baseline | SHA-256 (12) |
|---|---:|---:|---|
| `v0-h264-baseline.mp4` | 9.551.715 | — | `cf927d578ab9` |
| `v0-h264-main.mp4` | 8.686.438 | −9,1 % | `b9b1e1f542fe` |
| `v0-vp9.webm` | 4.411.693 | **−53,8 %** | `5be4650747fd` |
| `v0-vp9-alpha.webm` | 4.664.676 | (plano alfa) | `2b1fe6c3bfde` |
| `hls-ts/stream.m3u8` | 9.795.953 | +2,6 % | 16 segmentos TS |
| `hls-fmp4/stream.m3u8` | 9.555.175 | +0,04 % | 16 segmentos CMAF |
| `dash/manifest.mpd` | 9.555.712 | +0,04 % | 16 segmentos |

Los tres empaquetados salen **por remux (`-c copy`)** de la pieza Baseline: no
recodifican nada.

## Lo que ya se aprendió de los bytes (fluidez todavía no)

1. **VP9 comprime a menos de la mitad** que H.264 con la misma estructura y el
   mismo material.
2. **El DPB mínimo se paga en bitrate:** nuestro Baseline (CRF 20, GOP cerrado
   15, sin B, `refs=1`) pesa **2,3×** el `producto.mp4` de defaults, que en la
   caja «reproduce muy bien». Cuál precio conviene lo dice el aparato.
3. **Main gana 9,1 %** con estructura idéntica: es lo que Baseline paga por no
   usar CABAC.
4. **Los 16 segmentos de `hls-fmp4/` y los 16 de `dash/` son byte-idénticos uno
   a uno.** Un solo juego de piezas, dos manifiestos: la tesis del formato
   comprobada sin escribir una línea de muxer.

## Herramientas que quedaron (no re-implementar)

| Archivo | Qué es |
|---|---|
| `tools/emit_pieces.py` | emisor del pack: decodifica el máster **una vez** y alimenta con el mismo cuadro a los cuatro encoders (comparables por construcción), después empaqueta HLS/DASH por remux. `--only`, `--frames`, `--no-segment`; stderr de cada encoder en su propio log |
| `.github/workflows/emitir-v0.yml` | baja el máster pineado, **lo verifica por SHA-256** y publica el pack como artifact |
| `frontend/v0.html` | la página que reproduce el pack y reporta lo que el aparato hizo. **Una sola pantalla, sin scroll**; un solo `<video>`; mando numérico; tecla 95 = reporte a pantalla completa |
| `frontend/keypad.js` | el mando numérico **compartido**. Regla: se espera solo cuando el dígito puede ser el comienzo de un código más largo |
| `frontend/ir.html` | lanzador **autocontenido** para otro servidor (URLs absolutas; se muda editando `BASE`). **No está en el bucket a propósito** |
| `tests/test_emit_pieces.py`, `test_v0_page.js`, `test_ir_page.js`, `test_keypad.js` | cableadas en `run_all.py` |

`tools/serve-local.ps1` aprendió `.webm` y `.tsv`.

## Publicación

**60 keys** bajo `v0/` en `https://iargen.com/player/v0/`, todas verificadas
bajando y comparando SHA-256 contra el archivo local. Tokens efímeros quemados
en cada tanda (403 comprobado).

El worker `asciline-player` se **redesplegó dos veces**, con la copia guardada y
commiteada antes de cada despliegue:

1. `mp4`, `webm`, `tsv` + soporte de **`Range`** (206/416/`accept-ranges`).
2. `m3u8`, `mpd`, `ts`, `m4s`.

Sin eso, un aparato podía rechazar el video **por culpa del servidor y no del
códec** — un falso negativo que habría mandado el proyecto en la dirección
equivocada. La raíz del player quedó intacta (200, 26.679 B), verificado después
de cada despliegue.

## Deuda que quedó abierta

**H-14 — el invariante 7 no se cumple en el carril H.264.** Dos corridas del
mismo máster con los mismos parámetros dieron Baseline **+22 B** y Main **−74 B**
con **la misma versión de ffmpeg y la misma línea de opciones de x264**
(`threads=1`), mientras VP9 y VP9+alfa salieron **byte-idénticos**. El primer
byte distinto cae en las tablas de muestras: difiere el bitstream, no el
contenedor. Hipótesis **sin comprobar**: `mbtree` en punto flotante sobre runners
con CPU distinto.

## Commits

`0128309` (documentación del alcance) · `5ea6459` (corrección de método) ·
`38a48bc`, `d51be8c` (emisor) · `02dd95c` (página) · `965f0df` (cierre de H-9) ·
`bfa931c`, `20cb0bd` (worker + publicación) · `840c8d7` (HLS/DASH) ·
`00deb9f`, `d518f35` (tipos del carril segmentado) · `2cb3bfd`, `e1134dc`
(mando numérico y lanzador) · `53d6090`, `eef9e45` (una sola pantalla).
Todos con CI en verde.
