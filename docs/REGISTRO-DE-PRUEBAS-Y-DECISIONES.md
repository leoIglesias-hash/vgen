# Registro de pruebas y decisiones

Este documento conserva las apreciaciones, mediciones y decisiones de cada version
probada. Una conclusion no se considera universal: vale para la instancia y la
configuracion que figuran en su entrada.

## Regla para nuevas entradas

Registrar siempre:

1. fuente y hash;
2. version del formato y configuracion completa;
3. archivo resultante y hash;
4. observacion que motivo la prueba;
5. mediciones comparables;
6. explicacion de la causa probable;
7. decision y limites de validez;
8. resultado en dispositivos reales cuando este disponible.

Se debe repetir una conclusion si cambia alguno de estos factores: fuente, modo PIXEL o
ASCII, columnas/filas, FPS, cantidad de colores, algoritmo o duracion de paleta,
dithering, threshold con perdida, reconstruccion, formato/codec o reader/player.

## Fuente TKN usada en las instancias 001, 002 y 003

- Archivo: `TKN-2441-GANADOR- 15seg-.mp4`.
- Tamaño: 39.032.116 bytes.
- SHA-256: `EADB3346C8618E1954474696B8F96157B3E6409DBA57350440D7737B88A3AB55`.
- Salida: 640x360, 15 FPS, 231 frames, 15,4 segundos.
- Audio incluido en cada ASCLV: MP3 de 180.857 bytes.

## Instancia 001 - Seleccion de K-means y demo de 30 frames

Fecha: 2026-08-11.

### Configuracion evaluada

- ASCL v1, modo PIXEL.
- Perfil `graphic`: 640 columnas y hasta 256 colores.
- 15 FPS.
- Paleta temporal por bloques de 30 frames (2 segundos).
- Algoritmo `kmeans-rgb`.
- Reconstruccion `soft`.
- Dithering apagado y threshold 0.
- Implementacion del encoder: commit `62c56a7` (backend sin cambios durante la
  comparacion posterior de bloques).

### Motivo

La cuantizacion anterior producia escalas visibles en gradientes. Se compararon
MEDIANCUT, FASTOCTREE y K-means RGB, aceptando mas trabajo en la PC si el archivo y el
player del televisor mejoraban.

### Resultado que llevo a la decision

En el benchmark de nueve cuadros documentado en `BENCHMARK-TKN-COLORES.md`, K-means
frente a MEDIANCUT, ambos con 256 colores y bloques de 30 frames, obtuvo:

- +4,28 dB de PSNR de grilla;
- 14,8% menos bytes en el ASCLV;
- frente al candidato original de 128 colores, +6,75 dB por 917 KB adicionales.

El costo adicional quedo solo en el procesamiento offline. El formato, reader, RAM por
matriz y renderer no cambiaron.

### Version conservada

- Archivo: `outputs/TKN-2441-GANADOR-graphic-kmeans.asclv`.
- Tamaño: 12.089.965 bytes.
- SHA-256: `81702D32CABDFBB9F15D6AAA2908B3FE5B13751CFB52257DCF01DFE9CF2F87F5`.

### Decision y alcance

K-means RGB queda seleccionado para esta clase de animacion grafica con 256 colores.
La conclusion se obtuvo con este TKN, PIXEL 640x360, 15 FPS y sin dithering. No demuestra
por si sola que K-means sea siempre mejor en video fotografico, otra grilla, otra cantidad
de colores o modos ASCII.

## Instancia 002 - Duracion de paleta: 30, 15, 10 y 5 frames

Fecha: 2026-08-12.

### Observacion que motivo la prueba

Los ultimos frames del demo de la instancia 001 mostraban menos escalas de color que el
resto. Se planteo renovar la paleta cada 5 frames porque el tiempo de encode no es una
restriccion y la prioridad es la calidad final.

### Explicacion comprobada

El video tiene 231 frames. Con bloques de 30 se forman siete bloques completos y un
ultimo bloque de solo 21 frames. El encoder usa hasta 12 frames repartidos para construir
cada paleta:

- bloque normal: 12 de 30 frames representados (40%);
- bloque final: 12 de 21 frames representados (57%).

El final estaba mejor adaptado por cubrir menos tiempo y estar mas densamente muestreado;
ademas, su contenido es cromaticamente mas sencillo. No recibio un tratamiento manual.
Al pasar a bloques de 5, la diferencia de PSNR entre el tramo anterior y el final bajo de
aproximadamente 0,95 dB a 0,04 dB, confirmando la causa.

### Comparacion controlada

Todas las variantes conservaron exactamente: fuente, ASCL v1, PIXEL 640x360, 15 FPS,
231 frames, 256 colores, K-means RGB, reconstruccion soft, dithering apagado, threshold 0
y el mismo audio.

Se compararon los 231 cuadros. La referencia fue cada RGB 640x360 anterior a la
cuantizacion y la salida fue la matriz ASCL decodificada con su paleta activa. Estas
metricas aislan la cuantizacion; no miden la perdida de reducir la fuente a 640x360 ni
el escalado soft del navegador. Los tamaños incluyen el mismo audio y el header ASCLV.

| Bloque | Renovacion | ASCLV | Cambio | PSNR | PSNR baja frec. | DeltaE76 | Contorno proxy | Full frames |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 2,000 s | 12.089.965 B | base | 35,952 dB | 41,382 dB | 2,788 | 8,88% | 60 |
| 15 | 1,000 s | 13.106.144 B | +8,40% | 36,421 dB | 41,962 dB | 2,607 | 7,91% | 58 |
| 10 | 0,667 s | 13.288.322 B | +9,91% | 36,541 dB | 42,130 dB | 2,557 | 7,68% | 67 |
| 5 | 0,333 s | 14.075.645 B | +16,42% | 36,731 dB | 42,410 dB | 2,499 | 7,30% | 86 |

PSNR mas alto es mejor; DeltaE y contorno artificial mas bajos son mejores. El contorno
es un proxy experimental sobre gradientes suaves, no una metrica perceptual estandar ni
un umbral universal de aceptacion.

El PSNR de esta tabla usa los 231 cuadros y MSE RGB agregado. No se compara directamente
con el PSNR historico de la instancia 001, calculado sobre nueve cuadros.

Con 5 frames, respecto de 30:

- el error perceptual de color bajo aproximadamente 10,4%;
- los contornos artificiales asociados al banding bajaron aproximadamente 17,8%;
- el archivo crecio 1.985.680 bytes;
- la RAM de la matriz, el byte por celda y el algoritmo del renderer no cambiaron;
- los frames completos ZLIB aumentaron de 60 a 86, reduciendo continuidad DELTA y
  agregando algunas descompresiones/subidas completas en el player.

### Version seleccionada para probar en Smart TV

- Archivo: `outputs/TKN-2441-GANADOR-graphic-kmeans-block5.asclv`.
- Tamaño: 14.075.645 bytes.
- SHA-256: `C74CE669AEE4F10788BE8EAD02971A487E95E65D7E1E326FC26BDD3E759BC798`.
- Flags ASCL: `0x1A`; CRC validado.

Comando reproducible:

```text
python backend/make_clip.py "TKN-2441-GANADOR- 15seg-.mp4" \
  --out outputs/TKN-2441-GANADOR-graphic-kmeans-block5.asclv \
  --profile graphic --fps 15 --palette block --palette-block-frames 5 \
  --palette-algorithm kmeans-rgb --reconstruction soft --dither off
```

### Decision y alcance

- Para equilibrio general, 10 frames entrega casi toda la mejora con +9,91% de peso.
- Para esta demostracion y una prioridad explicita de maxima calidad, se seleccionan
  5 frames: la reduccion de banding es medible y +1,99 MB fue considerado aceptable.
- Esto no convierte 5 frames en default universal. Debe repetirse el barrido si cambia
  cualquier condicion enumerada al comienzo del documento.
- Falta registrar la prueba fisica en cada familia de Smart TV. Si los 26 frames completos
  adicionales producen tirones en un decoder especialmente lento, 10 frames es el
  fallback ya medido; no se debe bajar calidad por suposicion antes de probarlo.

### Resultado en dispositivos reales

Pendiente.

## Instancia 003 - Oklab, bloques adaptativos, estabilidad, auto y resolucion

Fecha: 2026-08-12.

### Motivo y alcance

Se aplicaron las mejoras 1 a 5 manteniendo ASCL v1: K-means Oklab, renovacion de paleta
por cambio numerico de color, estabilidad temporal, dithering calibrado y perfiles
seleccionables 640x360, 768x432 y 960x540. No se uso IA ni deteccion de objetos. Todo el
trabajo nuevo ocurre en el encoder de PC; el player recibe la misma matriz de indices.

La fuente, FPS, 256 colores, threshold 0, reconstruccion `soft`, audio y 231 frames son
los mismos de la instancia 002. La metodologia y las tablas completas se conservan en
`docs/BENCHMARK-V1-ADAPTATIVO-OKLAB.md`.

### Por que el adaptativo no quedo en 5..30

El primer candidato produjo 11 bloques de hasta 30 frames y peso 12.554.539 B. Mejoro
el error perceptual puntual, pero compartia una paleta durante 1,5 a 2 segundos y perdia
calidad de baja frecuencia. Al limitar el maximo a 10, sin convertirlo en intervalo fijo,
el mismo detector produjo 27 bloques de 1..10 frames, promedio 8,56, y mantuvo un hard
cut exacto. Bajar el umbral 0,20 a 0,15 casi no cambio la segmentacion.

Esta es una conclusion de esta instancia: el maximo de 10 queda como default conservador
de calidad, pero el valor sigue editable. Los cortes siguen dependiendo del color real y
pueden ocurrir antes; no se renueva obligatoriamente cada 10 frames.

### Evidencia resumida

| Variante | ASCLV | DeltaE OK | Mesetas | PSNR fuente 1080p bilinear | Decode ref. | RAM Canvas min. |
|---|---:|---:|---:|---:|---:|---:|
| block5 RGB 640 | 14.075.645 B | 0,989 | 61,26% | 28,026 dB | 1,209 ms/f | 15,64 MiB |
| adaptativo Oklab 640 | 13.196.334 B | 0,812 | 59,71% | 27,765 dB | 1,208 ms/f | 14,78 MiB |
| adaptativo Oklab auto 768 final | 17.935.310 B | 0,824 | 59,50% | 28,585 dB | 1,684 ms/f | 20,27 MiB |
| adaptativo Oklab auto 960 exploratorio | 26.069.769 B | 0,816 | 58,48% | 30,146 dB | 2,562 ms/f | 29,81 MiB |

La auditoria Oklab de baja frecuencia del 640 adaptativo 5..10 bajo de 0,1432 a 0,0810
frente al block5 RGB, y el RMS de contorno suave bajo de 0,1278 a 0,1108. Esto motivo
conservar Oklab aunque el PSNR RGB de grilla no aumentara: miden objetivos diferentes.

El dither auto se mantuvo conservador. En HQ cambio 0,57% de las celdas y en ultra 0,69%,
con presupuesto maximo de 5%; sus indices quedan horneados y no agregan CPU/GPU al player.

### Decisiones

- Conservar 640 adaptativo Oklab sin dither como perfil eficiente.
- Seleccionar 768 adaptativo Oklab con dither auto como candidato HQ recomendado.
- Mantener 960 como perfil ultra opcional hasta medirlo en dispositivos fisicos.
- Mantener estabilidad maxima 0,25 en esta version para que la paleta conserve continuidad;
  contrastar 0,10 en clips fotograficos antes de universalizar el valor.
- No cambiar el formato: los tres archivos son ASCL v1, flags `0x1A`, CRC valido y audio
  incluido. Canvas2D y WebGL1 siguen consumiendo la misma matriz.

### Versiones conservadas

- Eficiente: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-efficient-640.asclv`,
  13.196.334 B, SHA-256
  `D53611B89991CF01FBFB7E08AAE31BCEDD0AE2DD6C06AB0D5D5E9033D0BC6875`.
- HQ recomendado: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv`,
  17.935.310 B, SHA-256
  `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`.
- Ultra: medicion exploratoria local; debe regenerarse con el guard final de textura
  antes de entregarlo o versionarlo.

### Resultado en dispositivos reales

Pendiente. No convertir los tiempos del decoder Python en una garantia de Smart TV;
medir cuadros perdidos, CPU y RAM en Canvas2D y WebGL1 por familia de equipo.
