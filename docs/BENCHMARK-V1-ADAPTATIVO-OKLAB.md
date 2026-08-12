# Benchmark v1: paleta adaptativa Oklab y resolucion

Fecha: 2026-08-12.

## Pregunta

Se evaluaron juntas y por etapas cinco mejoras que no agregan trabajo nuevo al
reproductor: paleta perceptual Oklab, bloques por cambio real de color, estabilidad
temporal de paleta, dithering calibrado y grillas seleccionables de 640, 768 y 960
columnas. La salida sigue siendo ASCL v1 y el player sigue recibiendo indices de un byte.

No se uso IA, deteccion de objetos ni comparacion espacial de escenas. El detector usa
histograma Oklab, color medio y una energia escalar de gradiente calculados offline.

## Control experimental

- Fuente: `TKN-2441-GANADOR- 15seg-.mp4`, 39.032.116 B.
- SHA-256 de fuente: `EADB3346C8618E1954474696B8F96157B3E6409DBA57350440D7737B88A3AB55`.
- 231 frames, 15 FPS, modo PIXEL, 256 colores, threshold 0.
- Reconstruccion sugerida `soft`, bake `none`, audio MP3 de 180.857 B.
- K-means Oklab exacto (`perceptual-lut-bits=0`), refuerzo numerico de gradientes.
- Adaptativo: minimo 5, maximo 10, deriva 0,20, hard cut 0,58, estabilidad maxima 0,25.
- Dither auto: Bayer 4, presupuesto 5%, mejora minima 8%, ventana 10.

El maximo de 10 frames es una guarda, no una renovacion fija. Sobre este clip produjo
27 bloques variables, con tamaños entre 1 y 10 frames y un hard cut exacto. El bloque de
un solo frame aparece porque un hard cut nunca se retrasa para cumplir el minimo.

Las metricas de grilla usan los 231 RGB reducidos con `INTER_AREA`. La metrica de fuente
reescala la matriz decodificada a 1920x1080 con bilinear, para poder comparar resoluciones
distintas contra la misma referencia. `DeltaE OK` es 100 por distancia euclidea Oklab;
no es DeltaE76 ni CIEDE2000. Mesetas es un proxy experimental con umbrales fijos.

## Resultados principales

| Variante | Grilla | ASCLV | Bloques | Tags R/Z/D/M | PSNR grilla | DeltaE OK | PSNR baja frec. | Mesetas | PSNR fuente bilinear | Decode ref. | RAM Canvas min. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline block5 RGB | 640x360 | 14.075.645 B | 47 | 0/86/1/144 | 36,731 | 0,989 | 41,953 dB | 61,26% | 28,026 dB | 1,209 ms/f | 15,64 MiB |
| eficiente Oklab | 640x360 | 13.196.334 B | 27 | 0/77/1/153 | 34,790 | 0,812 | 39,231 dB | 59,71% | 27,765 dB | 1,208 ms/f | 14,78 MiB |
| HQ Oklab + auto final | 768x432 | 17.935.310 B | 27 | 0/89/1/141 | 34,547 | 0,824 | 38,758 dB | 59,50% | 28,585 dB | 1,684 ms/f | 20,27 MiB |
| ultra Oklab + auto exploratorio | 960x540 | 26.069.769 B | 27 | 0/103/1/127 | 34,585 | 0,816 | 38,819 dB | 58,48% | 30,146 dB | 2,562 ms/f | 29,81 MiB |

Los tiempos son del decoder Python de referencia con lectura local, no del Smart TV.
Sirven para comparar tendencia; la aceptacion final exige medir Canvas2D y WebGL1 en
cada familia real. La RAM es una cota del player actual que incluye el ArrayBuffer del
archivo, matriz, RGBA, backing de Canvas y pico de inflate; no incluye overhead del motor.

## Auditoria perceptual de 640

Una auditoria adicional con Oklab sobre media grilla y filtros de baja frecuencia mostro:

| Variante | Delta OK medio | Delta OK baja frec. | RMS contorno suave | Residuo temporal medio |
|---|---:|---:|---:|---:|
| block5 RGB | 0,1973 | 0,1432 | 0,1278 | 0,1556 |
| adaptativo 5..10 Oklab | 0,1492 | 0,0810 | 0,1108 | 0,1275 |
| adaptativo 5..30 Oklab | 0,1631 | 0,0933 | 0,1203 | 0,1265 |

Esto explica por que el PSNR RGB aislado no debe decidir una paleta perceptual: el modo
5..10 reduce 24,4% el error Oklab medio, 43,4% el error Oklab de baja frecuencia y 13,3%
el error de contornos suaves frente al block5 RGB. La revision de planchas de cuadros y
recortes de gradientes fue consistente con esas medidas.

El experimento inicial con maximo 30 generaba solo 11 paletas, varias de 1,5 a 2 segundos.
Aunque pesaba 12.554.539 B, sostenia demasiado el sesgo de una paleta. Por eso se descarto
como default. Con maximo 10 se obtuvieron 27 bloques, promedio 8,56 frames. Bajar el umbral
de deriva de 0,20 a 0,15 casi no cambio los cortes y se descarto para esta instancia.

## Dithering calibrado

En la comparacion controlada 640/max30, activar `auto`:

- cambio en promedio 0,71% de las celdas, muy por debajo del presupuesto de 5%;
- redujo el proxy de mesetas de 61,11% a 60,38%;
- agrego 133.141 B (+1,06%);
- mejoro 0,08 dB el PSNR RGB de baja frecuencia;
- aumento 1,29% el DeltaE OK medio.

Por eso queda aplicado en los perfiles HQ/ultra, donde se busca reducir escalas, y apagado
en el artefacto eficiente 640. No se considera una mejora universal: cada tile se acepta
solo si mejora su proxy y el guard final impide una regresion global del proxy calibrado.
En HQ cambio 0,57% de las celdas y en ultra 0,69%.

## Decision de esta instancia

1. `graphic` 640 adaptativo sin dither es la opcion eficiente: pesa 6,25% menos que el
   block5, reduce 17,9% DeltaE OK y mantiene el mismo tiempo de decode de referencia, a
   cambio de 0,26 dB menos contra la fuente 1080p reescalada.
2. `graphic-hq` 768 con auto es la recomendacion general de alta calidad: supera la fuente
   bilinear del block5 por 0,56 dB y reduce mesetas 1,76 puntos. Cuesta 27,4% mas archivo,
   29,6% mas RAM minima y 39% mas decode de referencia.
3. `graphic-ultra` 960 es un techo seleccionable, no el default para equipos antiguos.
   Frente a HQ gana 1,56 dB contra la fuente y 1,02 puntos de mesetas, pero cuesta 45,4%
   mas archivo, 47,0% mas RAM minima y 47% mas decode de referencia.
4. El default adaptativo queda en 5..10 para priorizar calidad. Esta conclusion pertenece
   a este clip y debe repetirse si cambian fuente, FPS, colores, algoritmo o modo.
5. No se modifica el formato, reader ni renderer. Canvas2D y WebGL1 presentan la misma
   matriz y el archivo conserva flags `0x1A`, CRC valido, audio y seek autocontenido.

## Artefactos

- Eficiente 640: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-efficient-640.asclv`,
  SHA-256 `D53611B89991CF01FBFB7E08AAE31BCEDD0AE2DD6C06AB0D5D5E9033D0BC6875`.
- Recomendado HQ 768: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv`,
  SHA-256 `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`.
- Ultra 960: medicion exploratoria local. Fue generado antes del ultimo guard de textura
  del dithering y debe regenerarse con el codigo final antes de entregarlo o versionarlo.

Los dos primeros se conservan en Git. Ultra queda regenerable hasta superar la prueba
fisica en Smart TV, para no aumentar innecesariamente el historial del repositorio.

## Pendiente de prueba fisica

- cuadros perdidos, CPU, RAM pico y temperatura en cada Smart TV/WebView;
- Canvas2D y WebGL1 por separado, sin aceptar diferencias funcionales;
- inspeccion de parpadeo en las 26 fronteras de paleta;
- decidir si algun modelo debe usar 640, 768 o 960 como limite operativo;
- contrastar estabilidad 0,25 contra 0,10 en clips fotograficos o con cambios sutiles.
