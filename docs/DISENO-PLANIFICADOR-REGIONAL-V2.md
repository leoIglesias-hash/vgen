# Diseño del planificador regional ASCL v2

Estado: propuesta técnica previa al prototipo. No reserva opcodes ni modifica ASCL v1.

Este documento formaliza la selección entre cambios por celda, máscara y bloque, junto
con un modo temporal con pérdida opcional. Complementa `DISENO-ASCL-V2-TILES.md` y la
sección V2-00 de `HOJA-DE-RUTA-TECNICA-V2.md`.

## 1. Objetivo e invariantes

El encoder de PC puede gastar más CPU para producir un archivo menor y un decoder más
barato. El runtime del TV debe seguir siendo ES5/ECMAScript 2015, con una matriz de
índices, una paleta, dirty metadata y scratch acotado.

Invariantes:

- no usar IA, detección de objetos ni motion vectors;
- no exigir WebGL: Canvas2D y WebGL1 consumen el mismo estado y dirty set;
- no mantener un segundo framebuffer lógico;
- no modificar una celda cuyo valor emitido siga siendo válido;
- modo `lossless`: la matriz emitida coincide exactamente con el objetivo en cada frame;
- modo con pérdida: error, edad y deuda tienen límites verificables;
- seek y frames omitidos producen el mismo resultado que decode secuencial;
- el encoder compara bytes reales y costo de reproducción, no solo heurísticas.

## 2. Dos decisiones separadas

### 2.1 Planificador perceptual temporal

Produce `E[t]`, la matriz que realmente se mostrará.

- En lossless, `E[t] = T[t]`, donde `T` es la matriz objetivo cuantizada.
- En near-lossless, puede conservar una celda de `E[t-1]` únicamente si toda la región
  cumple los límites de calidad y tiempo.

El decoder no conoce esta decisión. Recibe una transición ya resuelta.

### 2.2 Empaquetador regional lossless

Representa `E[t-1] -> E[t]` con comandos simples. Una retención perceptual se convierte
en un `SKIP` común; no hace falta un opcode lossy.

Orden conceptual:

1. frame idéntico: `REPEAT` o duración `HOLD_TICKS`;
2. tile idéntico: `SKIP_RUN`;
3. pocos cambios: `SPARSE`;
4. densidad intermedia: `MASK`;
5. tile uniforme: `SOLID_RUN`;
6. 2, 4 o 16 índices locales: `PACK1`, `PACK2` o `PACK4`;
7. tile denso general: `PAL8`;
8. comparar el frame completo con DELTA_MASK v1, `MASK_ZLIB` y ZLIB.

Los nombres son provisionales. V2-00 mide antes de fijar números de opcode.

## 3. Unidad regional

La grilla inicial es 16x16. El encoder prueba también 8 y 32 offline. Los tiles de borde
usan su tamaño real. Tiles adyacentes con la misma estrategia se fusionan en corridas o
rectángulos cuando reduce el header y no aumenta escrituras.

Para 16x16 y un byte por índice, antes de headers y compresión:

| Candidato | Bytes aproximados |
|---|---:|
| `SPARSE` | `2 * K` |
| `MASK` | `32 + K` |
| `PACK1` | `32 + mapa` |
| `PACK2` | `64 + mapa` |
| `PACK4` | `128 + mapa` |
| `PAL8` | `256` |

`K` es la cantidad de celdas cambiadas. Los cortes reales se determinan con el payload
final, porque DEFLATE, corridas y headers pueden cambiar el ganador.

## 4. Retención temporal con pérdida

El porcentaje propuesto por el usuario se divide en variables distintas:

- área mínima o densidad de la región candidata;
- magnitud perceptual media;
- percentil 95 y máximo permitidos;
- edad máxima sin actualización;
- deuda temporal máxima;
- salto máximo cuando finalmente se actualiza.

No se interpreta `2%` como diferencia RGB cruda ni como default universal.

Para cada celda:

```text
error[p,t] = DeltaEOK(color_objetivo[p,t], color_emitido[p,t-1])
```

Para cada tile se conserva estado acotado:

```text
age[t]  = frames desde la última actualización
debt[t] = rho * debt[t-1] + error_medio[t]
```

Una región se puede retener solo si cumple simultáneamente:

- media, p95 y máximo debajo de sus límites;
- `age < max_hold_frames`;
- deuda debajo del presupuesto;
- ausencia de corte fuerte;
- ausencia de bordes o texto nuevos;
- protección de degradado satisfecha;
- ahorro real mínimo frente a actualizarla.

Se fuerza actualización antes de que el error se acumule. Comparar contra el último
color emitido evita deriva ilimitada, pero no evita por sí solo un salto visible; por eso
también se limitan edad, deuda y amplitud del refresco.

### 4.1 Clasificación numérica, sin IA

- plano: rango espacial casi cero;
- degradado suave: gradiente pequeño, coherente y no nulo;
- borde/texto: energía de gradiente alta o aparición de nuevas discontinuidades;
- textura: varianza y gradiente irregulares.

Un degradado suave recibe tolerancia más estricta que un fondo realmente plano. El
promedio de una región nunca puede ocultar un error máximo localizado.

### 4.2 Relación con el threshold v1

El threshold v1 conserva el índice anterior si la distancia RGB cuantizada no supera el
umbral. En el encoder actual solo se aplica efectivamente a paleta global. No modela área,
p95, bordes, degradados, edad, deuda ni bytes finales. Se conserva para compatibilidad,
pero no se usa como diseño de este modo v2.

## 5. Paleta estable y fondos progresivos

Cuando la matriz de índices permanece igual y cambia el tono, reescribir miles de celdas
es redundante. `PAL_PATCH` es candidato experimental:

```text
changed_palette_entries
(palette_id, new_R, new_G, new_B)...
dirty_tile_runs...
```

Requisitos:

- IDs estabilizados en Oklab dentro de un GOP;
- paleta completa en el keyframe de inicio;
- rechazar el parche si un mismo ID se usa en regiones que requieren cambios distintos;
- dirty runs explícitos para no escanear toda la matriz en el TV;
- comparar el costo Canvas además del ahorro de archivo.

WebGL puede actualizar pocos bytes de paleta. Canvas debe regenerar las regiones afectadas,
por lo que `PAL_PATCH` no se selecciona por tamaño solamente.

`REMAP_RECT` prueba pocas parejas `índice_anterior -> índice_nuevo` dentro de un rectángulo.
Escanea el área y solo gana si reduce suficientes bytes y no empeora el p95 del decoder.

## 6. Selección offline

Algoritmo inicial:

1. cuantizar cada frame y conservar la matriz objetivo;
2. estabilizar IDs de paleta dentro del GOP;
3. simular exactamente el estado mostrado;
4. medir cambio exacto, Oklab, gradiente, edad y deuda por tile;
5. generar candidatos exactos y, si está habilitado, candidatos retenidos;
6. fusionar tiles compatibles en corridas/rectángulos;
7. resolver el stream mediante programación dinámica sobre el orden de tiles;
8. medir bytes comprimidos reales, escrituras, inflate y unpack;
9. comparar contra codecs completos v1/ZLIB;
10. simular el decoder y validar calidad, CRC, seek, RAM y tiempo;
11. emitir diagnósticos reproducibles por comando y motivo de decisión.

Un lookahead corto o beam search de 3 a 8 frames puede evitar una decisión barata hoy que
encarezca los frames siguientes. Este costo ocurre solo offline.

## 7. Ideas de WebP que se pueden adaptar

WebP lossless aporta conceptos, no un decoder para incluir dentro de ASCL:

- decisiones locales por bloques;
- indexación de hasta 256 colores;
- packing de 1, 2 y 4 bits para 2, 4 y 16 valores;
- predictores espaciales y residuos;
- referencias 2D a datos ya decodificados;
- codificación diferencial de paleta;
- preprocesamiento near-lossless en el encoder.

Candidatos de bajo riesgo:

- `PACK1/PACK2`, además de `PAL4`;
- paletas estables y `PAL_PATCH`;
- predictores simples `LEFT`, `TOP` o `GRADIENT` solo en bloques densos, comparados contra
  DEFLATE y aceptados únicamente con ganancia neta clara;
- referencia exacta y acotada a patrones de tile por hash, sin detectar objetos.

No trasladar:

- WebP/VP8, DCT, YUV420, motion vectors, dequantización o loop filter en JavaScript;
- entropy coder y árboles Huffman propios cuando ya existe DEFLATE validado;
- ZLIB independiente por tile;
- restar índices de paleta sin estabilizar su significado;
- referencias interframe que exijan un segundo framebuffer.

Fuentes primarias:

- RFC 9649, WebP Lossless Bitstream: https://www.rfc-editor.org/rfc/rfc9649.html
- WebP Lossless Bitstream Specification:
  https://developers.google.com/speed/webp/docs/webp_lossless_bitstream_specification
- libwebp encoder API (`near_lossless`):
  https://chromium.googlesource.com/webm/libwebp/+/refs/heads/main/src/webp/encode.h

## 8. Descarga completa por chunks y streaming futuro

El codec regional no obliga a streaming. El envelope v2 puede dividir el video en GOPs
autocontenidos, cada uno iniciado por keyframe y con CRC. La descarga normal acumula todos
los chunks y conserva el archivo completo cacheable. HTTP Range o reproducción progresiva
quedan como opciones posteriores sobre la misma estructura.

La intervención matricial en vivo es otra capa: se aplica después de decodificar y antes
de presentar dirty regions. No debe confundirse con la forma de descargar el archivo.

## 9. Pruebas y gates

Corpus sintético mínimo:

- frame idéntico y un solo cambio;
- 1%, 5%, 25% y 90% de celdas cambiadas;
- rectángulo sólido grande;
- fondo plano con deriva pequeña por frame;
- degradado suave con deriva de 1–2%;
- texto, bordes y textura;
- oscilación alrededor del umbral;
- un ID de paleta usado en regiones con cambios divergentes;
- dimensiones no divisibles por tile;
- cortes fuertes, frames omitidos y seeks aleatorios.

Métricas obligatorias:

- bytes totales y por comando;
- escrituras de `cells` y RGBA;
- bytes inflados y operaciones de unpack/remap;
- p50/p95 de decode y render;
- RAM y scratch máximos;
- DeltaEOK media/p95/máxima;
- deuda y edad máximas;
- error de derivada temporal, salto de refresco y longitud de mesetas;
- proxy de banding ya usado por el proyecto.

Gates:

- lossless: CRC de matriz idéntico en cada frame;
- near-lossless: ningún frame o región excede los límites configurados;
- cortes fuertes exactos e inmediatos y deuda siempre acotada;
- sin regresión p95 mayor al 5% en perfil legacy;
- reducción mediana de payload de al menos 10% sin casos mayores al 3%, o reducción de
  escrituras de al menos 20% para un perfil especializado;
- `PAL_PATCH`, `REMAP_RECT`, predictores y referencias solo entran si ganan en al menos
  dos clases reales y no perjudican Canvas2D.

## 10. Parámetros provisionales del encoder

No forman todavía una interfaz pública:

```text
--temporal-loss off|conservative|custom
--temporal-delta-ok-mean
--temporal-delta-ok-p95
--temporal-delta-ok-max
--temporal-max-hold-frames
--temporal-debt-limit
--temporal-refresh-jump-limit
--tile-size auto|8|16|32
--regional-profile legacy|balanced|smallest
```

Los defaults se fijan después de VAL-002 y del prototipo V2-00, no a partir de un único
clip ni de un porcentaje informal.
