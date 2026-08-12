# Benchmark de color - TKN-2441-GANADOR

Fecha: 2026-08-11

Fuente: `TKN-2441-GANADOR- 15seg-.mp4`, 39.032.116 bytes. Todas las variantes usan
ASCL v1 PIXEL, grilla 640x360, 15 FPS, reconstruccion SOFT y audio incluido. Las
metricas promedian nueve cuadros repartidos durante los 231 cuadros de salida.

| Variante | Paleta | Dither | Bytes `.asclv` | Reduccion | PSNR grilla | PSNR baja frecuencia | PSNR SOFT a fuente |
|---|---|---|---:|---:|---:|---:|---:|
| balanced original | 128 / 2 s | off | 11.172.977 | 71,4% | 29,64 dB | 32,62 dB | 26,73 dB |
| 128 selectivo | 128 / 2 s | Bayer 4 | 11.835.167 | 69,7% | 29,34 dB | 32,81 dB | 26,70 dB |
| 256 median-cut | 256 / 2 s | off | 14.196.201 | 63,6% | 32,11 dB | 35,82 dB | 27,73 dB |
| 256 selectivo | 256 / 2 s | Bayer 4 | 14.775.424 | 62,1% | 31,86 dB | 35,95 dB | 27,71 dB |
| 256 bloque corto | 256 / 1 s | off | 15.166.038 | 61,1% | 32,36 dB | - | - |
| **graphic K-means** | **256 / 2 s** | **off** | **12.089.965** | **69,0%** | **36,39 dB** | **40,75 dB** | **28,58 dB** |

## Conclusion

- La perdida visible provenia principalmente de compartir solo 128 colores entre los
  cuadros de un bloque, no de la resolucion de la matriz ni de Canvas/WebGL.
- Subir a 256 colores con MEDIANCUT mejora 2,48 dB el PSNR de grilla y 3,20 dB el
  error de baja frecuencia. Cada celda sigue siendo un indice de un byte, por lo que
  no aumenta la matriz residente ni cambia el trabajo de presentacion.
- Reemplazar MEDIANCUT por K-means RGB es la ganancia principal: a los mismos 256
  colores suma otros 4,28 dB y reduce el archivo 14,8%. Frente al candidato original
  de 128 colores gana 6,75 dB usando solo 917 KB adicionales.
- K-means tambien reduce trabajo temporal: el promedio baja a 103.312 celdas cambiadas
  y 51.344 bytes de payload por cuadro, frente a 109.452 y 60.468 con 256/MEDIANCUT.
- El flujo comprimido crece porque tiene mas entropia; el payload medio pasa de 47.455
  a 60.468 bytes por cuadro. La cantidad media de celdas actualizadas queda casi igual:
  108.903 con 128 colores frente a 109.451 con 256.
- Acortar el bloque a un segundo mejora solo 0,25 dB en promedio y agrega casi 1 MB;
  no se recomienda como default para este clip.
- El dithering selectivo reduce levemente el error de baja frecuencia, pero introduce
  grano visible en superficies suaves y baja las metricas de fidelidad directa. Debe
  permanecer experimental y apagado por defecto hasta incorporar presupuesto automatico
  y una seleccion temporal mejor calibrada.

Para este tipo de pieza grafica, el candidato recomendado es **perfil `graphic`
(640x360/256), K-means RGB, paleta por bloques de dos segundos, SOFT y dithering
apagado**. Mantiene ASCL v1 y el mismo decoder; todo el costo extra vive en el encoder.
