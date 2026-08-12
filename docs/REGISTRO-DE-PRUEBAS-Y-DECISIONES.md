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

## Fuente TKN usada en las instancias 001 y 002

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
