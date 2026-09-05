# Emisión v1 — la receta que dejó la matriz, más el audio

> **Estado (2026-09-05): emitida, publicada y con dos pasadas byte-idénticas;
> falta la foto de los aparatos.** v1 sale de **H-6**: la matriz por bytes a
> igual look (`tools/emit_matrix.py`, workflow `matriz-h6`). Toma la receta
> más barata que conserva el look según la tolerancia de trabajo y le suma lo
> que v0 no tenía: la **pista de audio del máster**, muxeada en cada pieza
> (S13) y suelta como radio (S14), y `v1-vp9` segmentado por remux para MSE
> (S11). Se mide en la página de banco con las teclas `72`, `74`, `75`, `76`.
>
> Antecesor: [`EMISION-V0.md`](EMISION-V0.md). Método:
> [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md). Gates:
> [`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md) §3.1.

---

## 1. Qué contesta la matriz (run `33936095399`, 231 cuadros, 1280×720 @15)

La caja ya dijo que la fluidez está saturada y que el decodificador es
hardware (E2, E6). Lo único que queda por comprar son **bytes**: arranque
(E4) y cuota de residencia (H-15). La matriz barre seis ejes desde el mismo
máster y mide, por variante, bytes, SSIM y PSNR contra el máster (4:2:0),
cuadros y segundos de encoder. La fluidez **no** se mide acá: es gate del
aparato.

**Método y autocontrol.** El máster se decodifica una vez a una referencia
y4m (misma conversión rgb24 → yuv420p que v0) y cada variante codifica desde
ahí con `-threads 1` y muxado bit-exacto. Las filas `ref-v0-*` tienen que
reproducir el pack v0 publicado. Salieron «DISTINTAS» por SHA y el autocontrol
del run `33936615188` dijo exactamente por qué: **el bitstream VP9 es
idéntico (ivf `cmp` limpio) y los píxeles decodificados son idénticos
(framemd5 igual); solo difiere el contenedor WebM en 8 bytes** (una etiqueta
de color que el y4m arrastra). Es decir: la matriz midió exactamente lo que
v0 emite. Para H.264 no se hizo la comparación a nivel bitstream (las piezas
difieren en +1,5 KB / −5,3 KB de contenedor); se asume lo mismo y queda
anotado como no verificado.

**«Igual look» de trabajo:** SSIM (All) que no baja más de **0,005** respecto
de la referencia v0 del mismo códec. Es un umbral para leer la tabla; el gate
último es el ojo del operador (§3.5 del plan).

| id | eje | bytes | % ref | SSIM All | PSNR | s enc | look | qué dice |
|---|---|---:|---:|---:|---:|---:|:---:|---|
| ref-v0-vp9 | referencia | 4.411.701 | 100,0 | 0,9793 | 42,24 | 36 | = | v0 (crf 32, cpu-used 2) |
| ref-v0-h264-baseline | referencia | 9.553.195 | 100,0 | 0,9872 | 44,25 | 29 | = | v0 (crf 20, sin B, ref 1) |
| ref-v0-h264-main | referencia | 8.681.169 | 90,9 | 0,9871 | 44,20 | 17 | = | CABAC compra 9 % y la caja lo decodifica igual (E6) |
| ref-defaults-h264 | referencia | 4.130.335 | 43,2 | 0,9814 | 42,07 | 10 | − | defaults de ffmpeg (High, medium, crf 23, **GOP 250**): el `producto.mp4` medido por fin |
| vp9-crf26 | vp9-crf | 6.852.233 | 155,3 | 0,9838 | 43,78 | 53 | = | |
| vp9-crf29 | vp9-crf | 5.512.801 | 125,0 | 0,9816 | 43,01 | 50 | = | |
| vp9-crf35 | vp9-crf | 3.541.869 | 80,3 | 0,9768 | 41,50 | 43 | = | −0,0025 |
| **vp9-crf38** | vp9-crf | **2.830.345** | **64,2** | 0,9740 | 40,74 | 40 | − | **−0,0053: al borde de la tolerancia → v1** |
| vp9-crf42 | vp9-crf | 2.119.031 | 48,0 | 0,9697 | 39,70 | 37 | − | −0,0096 |
| vp9-crf46 | vp9-crf | 1.610.846 | 36,5 | 0,9646 | 38,63 | 34 | − | −0,0148 |
| vp9-cpu0 | vp9-velocidad | 4.343.074 | 98,4 | 0,9803 | 42,53 | 166 | = | 4,6× el tiempo por −1,6 % de bytes |
| vp9-cpu1 | vp9-velocidad | 4.424.559 | 100,3 | 0,9801 | 42,45 | 67 | = | |
| vp9-cpu3 | vp9-velocidad | 4.482.839 | 101,6 | 0,9793 | 42,21 | 35 | = | |
| vp9-cpu4 | vp9-velocidad | 4.539.356 | 102,9 | 0,9790 | 42,11 | 31 | = | |
| vp9-screen | vp9-contenido | 4.411.701 | 100,0 | 0,9793 | 42,24 | 37 | = | **bytes idénticos a la referencia** |
| vp9-screen-crf38 | vp9-contenido | 2.830.345 | 64,2 | 0,9740 | 40,74 | 32 | − | idéntico a vp9-crf38 |
| vp9-film | vp9-contenido | 4.491.951 | 101,8 | 0,9785 | 42,16 | 43 | = | peor en todo: acota |
| vp9-aq0 | vp9-contenido | 4.411.701 | 100,0 | 0,9793 | 42,24 | 36 | = | idéntico: el default ya era aq 0 |
| vp9-sin-altref | vp9-contenido | 4.411.701 | 100,0 | 0,9793 | 42,24 | 36 | = | idéntico: el default ya era sin alt-ref |
| h264-baseline-crf23 | h264-piso | 6.348.025 | 66,4 | 0,9824 | 42,44 | 26 | = | −0,0049 |
| h264-baseline-crf26 | h264-piso | 4.337.650 | 45,4 | 0,9769 | 40,78 | 19 | − | −0,0104 |
| h264-main-b2 | h264-piso | 7.777.404 | 81,4 | 0,9865 | 43,75 | 22 | = | 2 B dentro del GOP cerrado, ref 3 |
| h264-high-b3 | h264-piso | 7.648.888 | 80,1 | 0,9865 | 43,75 | 23 | = | 3 B, ref 4, 8×8 |
| **h264-high-b3-crf23** | h264-piso | **5.064.003** | **53,0** | 0,9819 | 42,15 | 19 | − | **−0,0053: al borde → v1** |
| h264-main-animation | h264-piso | 8.735.840 | 91,4 | 0,9871 | 44,89 | 20 | = | mejor PSNR, mismos bytes que main |
| vp9-vfr-exactos | cadencia | 6.018.589 | 136,4 | 0,9798 | 42,37 | 41 | = | **230 cuadros: 1 solo duplicado exacto**; +36 % por los cuadros clave forzados |
| vp9-vfr-casi | cadencia | 5.976.917 | 135,5 | 0,9802 | 42,46 | 39 | = | 227 cuadros: 4 casi iguales |
| h264-baseline-vfr-exactos | cadencia | 9.560.078 | 100,1 | 0,9872 | 44,25 | 29 | = | 230 cuadros, sin ganancia |

Tabla completa (con SSIM Y, cuadros y perfil/nivel) en el artifact
`matriz-h6-tabla` del run y en el REGISTRO (entrada 2026-09-05).

## 2. Lo que la tabla enseña (por eje)

1. **VP9 CRF es el único eje que compra bytes de verdad.** De crf 32 a 38 se
   ahorra el 36 % con −0,005 de SSIM; a 42, el 52 % con −0,010. La curva es
   suave: no hay un codo. Dónde parar lo dice el ojo, no la tabla.
2. **`cpu-used` no compra nada:** −1,6 % de bytes por 4,6× de tiempo. Se
   queda en 2.
3. **`tune-content screen`, `aq-mode 0` y «sin alt-ref» dan bytes IDÉNTICOS
   a la referencia:** en `-deadline good` libvpx ya estaba en aq 0 y sin
   alt-ref, y el modo pantalla no cambia una decisión. El eje «contenido» de
   VP9 está agotado con estas palancas; lo que el máster regala (paleta plana,
   zonas quietas) el códec ya lo aprovecha por el `crf`.
4. **H.264: el GOP cerrado de 1 s cuesta más que el perfil.** Los defaults de
   ffmpeg (High, GOP 250) pesan el 43 % de Baseline v0; el mismo High con
   3 B y GOP 15 pesa el 53 %. Esa diferencia (10 puntos) es lo que pagamos
   por poder **cortar segmentos de 1 s e intercambiar piezas** (S12), y se
   paga a propósito. Main = Baseline en la caja (E6), así que High con B
   dentro del GOP cerrado es la apuesta razonable para el piso; **si la caja
   lo paga en fluidez, cae** y se vuelve a `h264-baseline-crf23` (66 %).
5. **Cadencia variable (S6): refutada para este máster.** Hay **un** cuadro
   exactamente igual al anterior en 231 y cuatro «casi». Con `near-lossless 8`
   el máster no deja cuadros quietos, y forzar cuadros clave por tiempo con
   cadencia variable le **subió** un 36 % a VP9. Queda abierta para clips con
   quietud real (P-004 en [`../PROPUESTAS.md`](../PROPUESTAS.md)).

## 3. La receta v1 y sus piezas

`tools/emit_v1.py` — sin argumentos es «v0 con audio»; la receta elegida va
por argumentos y queda en el manifiesto:

```
--vp9-crf 38 --h264-profile high --h264-crf 23 --h264-bframes 3 --h264-refs 4
```

Las dos variantes están **al borde** de la tolerancia (−0,0053 las dos), a
propósito: el criterio del operador es «pérdida mínima aceptable si el ahorro
lo vale», y el ahorro es 36 % (VP9) y 47 % (H.264). Si el ojo dice que se ve
feo, el escalón anterior está medido: `vp9-crf35` (80 %) y
`h264-high-b3` (80 %) o `h264-baseline-crf23` (66 %).

| id | rol | MIME | bytes | qué es |
|---|---|---|---:|---|
| `v1-vp9` | v1 | `video/webm; codecs="vp9, opus"` | 2.941.449 | VP9 crf 38 + **Opus 64k** (S13). 66,7 % de `v0-vp9` **con audio adentro** |
| `v1-h264` | v1 | `video/mp4; codecs="avc1.64001F, mp4a.40.2"` | 5.254.272 | H.264 High crf 23, 3 B, ref 4 + **AAC 96k** (S13). 55 % de `v0-h264-baseline` |
| `v1-ambiente` | radio | `audio/mpeg` | 183.353 | la pista del máster **byte a byte** (no se recodifica), para `<audio>` aparte (S14) |
| `v1-dash-vp9` | stream-v1 | `video/webm; codecs="vp9"` | 2.831.164 | `v1-vp9` segmentado **solo video** por remux (`-c copy`), init + 16 chunks de 1 s (S11) |

SHA-256 en `v0/MANIFEST-v1.tsv` (publicado) y en el REGISTRO. Emitido por
el workflow `emitir-v1` (run `33936096738`, 1:12 de reloj): **dos pasadas
byte-idénticas** en la misma máquina para las tres piezas. Los encoders de
audio son de punto flotante y no tienen `cpu-independent`: si otra CPU emite
otros bytes, la residencia lo tiene que saber (P-006 propone el mp3 tal cual
dentro del mp4).

## 4. Cómo se mide (página `v0/`, teclas nuevas)

| tecla | suposición | qué hace | gate |
|---|---|---|---|
| `72` | **S13** | `v1-vp9` y `v1-h264` **con sonido** (el `<video>` se destapa solo durante la medición) | caídos ≤ 3 %, atascos 0, y que **suene** |
| `74` | **S14** | `<audio>` con `v1-ambiente.mp3` en bucle **y** VP9 mudo en bucle; la nota trae «radio arrancó en N ms; deriva radio; **deriva A/V**» | deriva A/V ≤ 50 ms / 10 s |
| `75` | **S11** | los 16 segmentos WebM de `dash-vp9/` por `SourceBuffer` (`video/webm; codecs="vp9"`, modo `segments`) | arranque ≤ 3.000 ms, atascos 0 |
| `76` | — | las tres seguidas | — |

El `1` («lo que falta») corre las cuatro **solo si** `MANIFEST-v1.tsv` está
publicado; si no, cada fila dice «falta MANIFEST-v1.tsv» en vez de un cero.
El `0` vuelve a tapar el video y calla la radio.

## 5. Qué refutaría cada cosa

| Suposición | Cae si… | Entonces |
|---|---|---|
| S13 (audio muxeado sin costo) | `72` cae cuadros ≥ 3 % o no arranca con sonido | el audio propio va por `<audio>` con cue; la sincronía exacta se abandona |
| S14 (`<audio>` + `<video>` sin deriva) | deriva A/V > 50 ms en 10 s | la ambiente se muxea en las piezas |
| S11 (VP9 por MSE) | `75` no arranca o se atasca | VP9 queda como pieza entera (A/C); N1 en vivo solo por H.264 |
| la receta v1 (look) | el operador dice «se ve feo» en la caja | escalón anterior medido (§3) |
| High + B en el piso | la caja cae cuadros con `v1-h264` | `h264-baseline-crf23` (66 %) |
| `.mp3` como `octet-stream` | el `74` dice «radio NO arrancó» | agregar `mp3:'audio/mpeg'` al Worker (redeploy pendiente) |
