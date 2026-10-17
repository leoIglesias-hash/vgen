# Intro + loop: encontrar lo que se repite y emitirlo una sola vez

**2026-10-17.** Trabajo exploratorio del operador sobre un video propio
(`intro_D_loop_ondas_perfecto_x9.mp4`). **No se publicó** (decisión del
operador); lo que queda es el método, cuatro herramientas y las lecciones,
todas medidas.

> **En una línea:** si un video es *intro + el mismo loop repetido*, no hace
> falta pagar cada vuelta. Dos formas: **dos piezas** —la intro (una vez) y
> **una** vuelta del loop (la repite el reproductor)— o **un solo mp4 común**
> con todas las vueltas adentro pero cada una guardada **una vez** (§6). En
> este video eso solo, con la misma receta, bajó el peso **77 % (VP9) y 78 %
> (H.264)**: más que cualquier ajuste del compresor.

## 1. Cuándo sirve y cuándo no

| Sirve | No sirve |
|---|---|
| Dos piezas: el reproductor puede repetir una pieza (`producto.html` con su anillo MSE, o `<video loop>` si no hay intro) | Dos piezas: un aparato que reproduce **un solo archivo una vez** |
| Archivo único (§6): un mp4 que el reproductor lee **siguiendo su índice** (Chromium y ffmpeg, medido) | Archivo único en **MPEG-TS** (sin índice: el pedido de ~2 min en `.ts`) o **WebM**: ahí cada vuelta se paga entera |
| El loop se repite **igual** (mismo render): las vueltas se parecen ~99 % | Escenas parecidas pero no idénticas (la cámara se movió, cambió el texto) |
| Fondos/gráficas en bucle, separadores, «en vivo», cortinas | Video sin repetición (el detector lo dice: `sin loop`) |

Por qué el compresor solo no alcanza: H.264 y VP9 aprovechan parecidos entre
cuadros **cercanos** (sus referencias alcanzan pocos cuadros); una repetición
cada 3,5 s la pagan entera en cada vuelta.

## 2. Cómo se encuentra un loop (lo que hace `tools/buscar_loops.py`)

1. **Miniaturas**: todos los cuadros de la fuente, a su cadencia original, en
   gris 64×36 (rápido: 40 s de video en ~3 s).
2. **El video contra sí mismo, corrido en el tiempo**: para cada
   desplazamiento *d* (0,5 s a 30 s) se compara cada cuadro con el que está
   *d* cuadros después. Una repetición da una **racha larga de diferencias
   casi nulas**. Para no confundir una escena quieta con un loop, «igual»
   exige además ser mucho más parecido que el cuadro vecino: en un loop con
   movimiento el vecino cambia y la copia no.
3. **Gana la racha más larga** = el período fundamental (el doble del período
   también coincide, pero con una racha más corta). Donde empieza la racha
   termina la intro; su largo da las vueltas.
4. **Bordes**: la intro suele **fundirse** con el loop durante unos cuadros
   (en intro_D la copia del cuadro 195 era 5× peor que la mediana, la del 196
   2×, desde el 197 igual al resto). Se recortan los bordes de la racha
   mientras la copia sea más del doble de mala que la mediana.
5. **Cuadros enteros**: al fps destino el loop tiene que durar una cantidad
   **entera** de cuadros o la costura salta. 85 cuadros a 24 fps = 3,542 s →
   35 cuadros a 10 fps = 3,5 s (**+1,2 % de velocidad**, imperceptible). Más
   de ±3 % se informa como advertencia.
6. **Costura**: el salto del último cuadro del loop al primero se compara con
   los saltos normales entre vecinos del mismo loop (percentil). Por debajo de
   100 = cae dentro de lo normal; 100 = más brusco que todos (se nota).

Salida real sobre intro_D, sin decirle nada:

```
fuente     962 cuadros @ 24.000 fps = 40.08 s
intro      cuadros 0-196  (197 cuadros, 8.21 s)
loop       cuadros 197-281  (85 cuadros, 3.542 s)
vueltas    9 completas  + cola de 0 cuadros (0.00 s)
copias     diferencia media 0.19 (0..255) con movimiento 2.97 entre vecinos
costura    salto 3.92; percentil 92 entre los vecinos del loop (mediana 2.97)
a 10 fps  loop = 35 cuadros (3.500 s; velocidad +1.2 %)
ahorro     viajan intro + 1 vuelta = 29.3 % de los cuadros
```

197 + 85 × 9 = 962: el video entero, sin sobrantes. Si el archivo **ya es**
una sola vuelta (el `loop_ondas_3.5s` de la misma tanda), dice `sin loop` y
además si el archivo entero cierra bien como loop.

## 3. Las herramientas

Todas tienen el núcleo en numpy (testeado en CI sin ffmpeg) y usan ffmpeg
solo para leer/escribir video. Desde la PC, con el bundle portátil (el
ffmpeg del bundle queda en el PATH de ese proceso):

```
py.cmd repo\tools\buscar_loops.py fuente.mp4 --fps-destino 10
py.cmd repo\tools\emit_intro_loop.py fuente.mp4 --out outputs\mi-loop
py.cmd repo\tools\medir_banding.py ref.y4m pieza1.mp4 pieza2.mp4
py.cmd repo\tools\mp4_dedup.py pegado.mp4 unico.mp4
```

(Hasta que se rearme el bundle con estas herramientas, usar la ruta del repo:
`py.cmd C:\Users\leo_8\OneDrive\Escritorio\ASCILINE-hybrid\tools\buscar_loops.py …`.)

| Herramienta | Qué hace | Test |
|---|---|---|
| `tools/buscar_loops.py` | detecta intro, período, vueltas, cola y costura; ajusta el loop a cuadros enteros al fps destino. Solo lee | `tests/test_buscar_loops.py` (13): loop sintético con intro/cola, período fundamental y no su múltiplo, escena quieta ≠ loop, sin repetición, costura buena y costura que salta, recorte de fundidos |
| `tools/emit_intro_loop.py` | detecta (o recibe `--intro`/`--periodo` en cuadros de la fuente), arma las dos referencias 709 (la del loop retemporizada a cuadros enteros), emite las **dos piezas** H.264 (y VP9 con `--vp9-crf`), el **archivo único** `unico-h264.mp4` (intro + loop × `--vueltas`, pegado sin recodificar y pasado por `mp4_dedup`) y `MANIFEST-intro-loop.tsv` con bytes, SHA-256 y SSIM. `--conservar-refs` deja las referencias y el pegado expandido en `work\` | `tests/test_emit_intro_loop.py` (11): receta C3 fijada, plan de cortes, filtros, un keyframe por pieza, determinismo, VP9 dos pasadas, pegado sin recodificar, manifiesto |
| `tools/mp4_dedup.py` | un mp4 común con cada muestra repetida guardada **una vez**: reapunta el índice (§6). Varias pistas; relee lo que escribió y exige las mismas muestras byte a byte; rechaza mp4 fragmentado | `tests/test_mp4_dedup.py` (13): mp4 sintéticos caja por caja (intro + vueltas, varias corridas de `stsc`, tamaño fijo, `co64`, varias pistas, sin repeticiones), tiempos y keyframes intactos, determinismo, fragmentado rechazado, byte cambiado atrapado |
| `tools/medir_banding.py` | el `proxy_banding` de `bench_ref.py` aplicado a piezas de video contra su referencia, total y **solo en zonas oscuras** | `tests/test_medir_banding.py` (5) |

**Receta por defecto de `emit_intro_loop.py` = C3** (la que eligió el
operador, §5): 1280 de ancho, 10 fps, H.264 High 3.1, **intro crf 24 / loop
crf 26**, un keyframe por pieza (la pieza se reproduce entera, no por
segmentos), y prefiltro:

```
hqdn3d=3:2:4:3,deband=1thr=0.015:2thr=0.015:3thr=0.015:range=24:blur=1
```

`--prefiltro ninguno` lo apaga. La intro lleva más calidad que el loop porque
se descarga una vez; el loop es lo que paga cada aparato y cada caché.

**Verificado sobre intro_D (2026-10-17):** la herramienta detectó el loop
sola y emitió **1.261.054 B** en H.264 (intro 847.518 + loop 413.536;
C3 hecho a mano: 1.262.857 B, el loop arrancaba un cuadro antes, dentro del
fundido); **dos corridas, mismos bytes** (`8f5be78391ae…` intro,
`b30154754ab7…` loop). Con `--vp9-crf 14`: VP9 1.901.576 B. El archivo único
(intro + 9 vueltas, 397 cuadros, 117 únicos) pesa **1.265.036 B** contra
4.562.436 B del pegado expandido, decodifica idéntico a ese pegado cuadro
por cuadro y también sale con los mismos bytes en dos corridas
(`8fe4d155c542…`).

**Mismo video con el doble de vueltas (`…_x18.mp4`, 2026-10-17):** 1.727
cuadros, 72 s, 25,1 MB. Detectado solo: intro 197 + loop 85 × **18**
(197 + 85 × 18 = 1.727). Con la receta C3 sin tocar: intro 843.326 B + loop
404.346 B; **archivo único 1.256.714 B** (712 cuadros, 117 únicos) contra
8.107.673 B del pegado expandido, decodifica idéntico al pegado. Duplicar las
vueltas no agrega peso: el índice crece ~2 KB y nada más (este export de la
fuente venía algo más limpio, por eso las piezas pesan un poco menos que las
del x9). El halo de la intro queda tratado igual que en C3.

## 4. Lo que aprendimos (todo medido)

| # | Lección | Números |
|---|---|---|
| 1 | **La ganancia grande fue de estructura**: intro + una vuelta | 128 colores crf 14, un archivo: VP9 15,8 MB → 3,65 MB (−77 %); H.264 38,0 MB → 8,26 MB (−78 %); con el resto de §4, H.264 final 1,26 MB (−97 % del primer intento) |
| 2 | **La paleta reducida no ayuda en `<video>` por hardware**: suma bytes, suma decodificación y escalona los degradés (el halo) | 128 colores a igual crf (14): +31 % (VP9) / +40 % (H.264) en `loop_ondas_3.5s` a 640×360 @10; decodificar 40 s en CPU: 1,14 s con paleta vs 1,00–1,06 s sin (crf 22) y 0,75–0,88 s (crf 26). Solo ahorraba en el player JS indexado del paradigma anterior. Coincide con H-27 (*«controlar los colores no nos dio ganancia»*) |
| 3 | **El crf no se compara entre códecs**: a igual fidelidad al look, H.264 crf 18 ≈ VP9 crf 14 | contra la referencia con paleta: H.264 crf 14 50,5 dB (0,996), crf 18 47,5 dB, crf 22 45,4 dB; VP9 crf 14 47,3 dB |
| 4 | **GOP largo** cuando la pieza se reproduce entera | H.264 −7,9 %, VP9 −19 % (GOP 1 s → un keyframe por pieza) |
| 5 | **Congelar píxeles quietos empeora** con mucho movimiento (lo anticipó el operador) | +2,9 % / +5,9 % de bytes y peor SSIM (umbral 4 y 8) |
| 6 | **`aq-mode=3` y deblock más fuerte no sirven** para el halo | aq3: +8 % bytes y más banding; deblock 1/2: sin cambio |
| 7 | **Limpiar ruido antes de comprimir** (`hqdn3d=3:2:4:3`) baja bytes y mancha menos | loop crf 26: 448.668 → 434.679 B y banding en oscuros −11 %; denoise fuerte ya come detalle (SSIM 0,9818) |
| 8 | **Degradé muy oscuro = anillos; se arregla con `deband` antes de comprimir** | el halo de intro_D se dibuja con **8 tonos de luma (16..23)**; la fuente ya trae los anillos y la compresión los vuelve manchas en bloque. Con deband la intro queda más pareja que la fuente; en el loop además baja bytes (430 → 424 KB) |
| 9 | **Medir halo**: el número relativo a la fuente detecta escalones nuevos pero **no puede premiar ir más allá de la fuente** (un deband suma un poco donde la fuente tenía mesetas) | por eso cada decisión de halo se tomó con recortes de gamma realzada y la vista previa |

## 5. El recorrido sobre intro_D (para no repetirlo)

Fuente: 1280×720 @24, 40,08 s, 962 cuadros, 26.536.426 B, sin audio,
SHA-256 `0ee33f22acae…`.

| Paso | Qué | Resultado |
|---|---|---|
| 1 | Pedido inicial: 128 colores, crf 14, 10 fps, 1280×720, un archivo | VP9 15,8 MB; H.264 38,0 MB (supera el techo de 20 MB y a la fuente) |
| 2 | Intro + 1 vuelta, misma receta | VP9 3,65 MB; H.264 8,26 MB |
| 3 | H.264 crf 18 / 22 con paleta, GOP largo | 4,27 MB / 2,23 MB (porción de 11,7 s) |
| 4 | Halo a ojo: A paleta crf 22 · B sin paleta crf 22 · C sin paleta crf 26 | 2,2 · 2,0 · **1,24 MB**; sin paleta, sin manchas y más liviano |
| 5 | C2: C + `hqdn3d` | 1,17 MB, banding oscuros −7 % (intro) / −11 % (loop) |
| 6 | **C3: + `deband`, intro crf 24** (la captura del operador: el halo detrás de «TABLEROS») | **1,26 MB — elegido por el operador** («excelente, nos quedamos con ese») |

C3 hecho a mano: intro `defe38cf805a…` 847.555 B, loop `2795a693ad42…`
415.302 B. Las piezas viven en la PC (`vgen-portable\outputs\introD-*`), no
en el repo (video del cliente).

## 6. Un solo archivo reproducible que guarda cada vuelta una vez (`tools/mp4_dedup.py`)

Pregunta del operador: ¿se puede aprovechar lo del loop **en el mismo
archivo de video**, como una compresión zip pero reproducible? Primero se
midió qué hace un compresor general con el archivo de intro + 9 vueltas
pegadas sin recodificar (cada vuelta = bytes idénticos):

| | Bytes |
|---|---|
| Archivo único (intro + 9 vueltas) | 4.578.034 |
| …con gzip -9 (recuerda 32 KB hacia atrás) | 4.573.776 — no gana nada: una vuelta pesa 415 KB |
| …con xz -9 (recuerda 64 MB) | **1.262.632** |
| Dos piezas (intro + 1 vuelta) | 1.262.857 |
| **mp4 deduplicado (`mp4_dedup`)** | **1.266.930 — reproducible directo** |

xz demuestra que la repetición es lo único que sobra (sobre las piezas solas
ahorra ~400 B: el video ya está comprimido), pero un `.xz` no se reproduce.
`mp4_dedup` consigue lo mismo **dentro de un mp4 común**:

- un mp4 guarda los datos de cada cuadro en `mdat` y un **índice** por pista
  (`stsz` tamaños; `stsc` + `stco`/`co64` posiciones) que le dice al
  reproductor dónde está cada uno;
- nada obliga a que dos cuadros vivan en bytes distintos: el índice de las
  vueltas 2..9 **apunta a los bytes de la vuelta 1** (un «acceso directo» por
  cuadro). 397 cuadros en el índice, 117 guardados (82 de intro + 35 del loop);
- el reproductor busca cada cuadro donde dice el índice y recibe exactamente
  la misma secuencia que en el archivo expandido. Tiempos (`stts`/`ctts`),
  keyframes (`stss`), `stsd` y edit lists se copian tal cual; solo cambian
  `mdat`, `stsc` (una muestra por chunk) y `stco` (una posición por muestra).
  La diferencia con las dos piezas (~4 KB) es ese índice más largo.

**Verificado (2026-10-17):**

- ffmpeg: los 397 cuadros decodificados son idénticos al archivo expandido
  (framemd5) y la lista de paquetes también (pts, dts, duración, tamaño,
  keyframe);
- Chromium (el motor de la caja), servido por HTTP: saltando a la intro y a
  las vueltas 1, 3, 6 y 9 cada cuadro es **idéntico píxel por píxel** al del
  archivo expandido; reproducción continua del segundo 29 al final cruzando
  tres costuras: sin errores, 0 cuadros caídos, termina en 39,7 s;
- la herramienta relee el archivo que escribió y exige, pista por pista, las
  mismas muestras byte a byte; si no, no lo entrega.

**Condiciones:**

1. Las vueltas tienen que ser **bytes idénticos**: el loop se codifica **una
   vez** y se pega N veces sin recodificar (`emit_intro_loop.py` lo hace).
   Recodificar el video de 40 s nunca da dos vueltas iguales.
2. **Solo mp4** (ISO BMFF) no fragmentado. MPEG-TS no tiene índice (los bytes
   son la transmisión misma) y WebM guarda los bloques dentro de los clusters:
   ahí no se puede. VP9 se puede meter en mp4 si hiciera falta.
3. El reproductor tiene que **seguir el índice**. Chromium y ffmpeg lo hacen;
   un reproductor de hardware que lea el archivo de corrido podría no hacerlo.

Lo que el códec no puede hacer solo: H.264 mira hasta 16 cuadros hacia atrás
y VP9 menos; el loop dura 35 cuadros, así que al empezar una vuelta el
compresor ya «se olvidó» de la anterior.

## 7. Lo que falta / límites conocidos

- **No probado en la caja ni en el Smart TV.** Los anillos de un degradé tan
  oscuro dependen del brillo/contraste del panel; la costura intro → loop
  también se valida reproduciendo, no en el banco. Lo mismo para el
  **archivo único**: pasó ffmpeg y Chromium de escritorio; la caja
  (Chromium 70), el Smart TV (Chrome 142) y los reproductores de hardware
  (MediaPlayer/ExoPlayer de una app) hay que verlos reproduciendo.
- **VP9 de C3 sin mirar a ojo** (la caja tiene VP9 por hardware y la receta
  firmada v2 es VP9): `--vp9-crf` existe, la elección del crf es del operador.
- **No está cableado a `emitir.ps1`** ni al workflow `portable`: se corre con
  `py.cmd` (§3). Entra al bundle en el próximo armado (`armar.py` copia
  `tools/*.py`).
- El detector busca **un** loop (el de racha más larga). Un video con dos
  loops distintos en secuencia necesita correrlo por tramos.
