# Benchmark inicial de calidad

Fecha: 2026-08-11

Prueba exploratoria sobre un frame real 1920x1080 (`outputs/src_frame.png`). Cada variante
se codifico como ASCL v1 PIXEL, se decodifico y se reconstruyo a 1920x1080 para calcular
PSNR contra la fuente. `soft` usa bilinear solo para esta reconstruccion de control;
`baked` almacena la reconstruccion 2x offline y se presenta con NEAREST.

| Variante | Grilla | Colores | Bake | Recon | Bytes ASCL | PSNR |
|---|---:|---:|---|---|---:|---:|
| referencia | 320x180 | 256 | none | nearest | 39.321 | 20,12 dB |
| balanced | 640x360 | 128 | none | soft | 96.205 | 26,24 dB |
| detail64 | 960x540 | 64 | none | soft | 136.276 | 24,84 dB |
| detail96 | 960x540 | 96 | none | soft | 158.304 | 25,48 dB |
| detail128 | 960x540 | 128 | none | soft | 174.951 | 26,25 dB |
| baked64 | 960x540 | 64 | soft | nearest | 123.389 | 22,50 dB |
| baked128 | 960x540 | 128 | soft | nearest | 154.827 | 23,52 dB |

## Lectura provisional

- Subir de 320x180 a 640x360 con 128 colores produjo la mejora mas grande en este frame.
- 960x540 con 64 colores perdio fidelidad frente a 640x360/128: mas celdas no compensan
  siempre una paleta demasiado pequena.
- 960x540/128 obtuvo casi el mismo PSNR que 640x360/128, pero ocupo bastante mas.
- El horneado redujo bytes frente a su equivalente 960, pero tambien bajo PSNR. Puede
  reducir bloques visuales y aun asi perder detalle numerico; debe seguir siendo opcional.
- Los perfiles deben ser puntos de partida. El encoder futuro debe buscar la combinacion
  por clip y no asumir una progresion fija.

Esta prueba no mide DELTA, movimiento, FPS ni parpadeo temporal. Antes de elegir defaults
se repetira sobre varios videos completos y en Canvas2D/WebGL1 de los dispositivos reales.

