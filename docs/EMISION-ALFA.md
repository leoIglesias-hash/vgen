# Emisión con alfa — video con transparencia (H-28)

> **Estado (2026-10-19): emisor HECHO y medido con un clip sintético**
> (`tools/emit_alfa.py` + `tests/test_emit_alfa.py`, 37 pruebas). Sale VP9 +
> alfa y VP8 + alfa, con Opus si la fuente trae audio, de forma determinista
> (dos corridas, mismos bytes), con el alfa vivo y sin alarma de color.
> **Falta:** (1) **un clip real con transparencia del operador**: todos los
> números de abajo son del sintético; (2) los planos en `v1/` para mirarlo en
> la caja y el Smart TV (paso 3 de H-28); (3) que el ojo del operador decida
> el alfa binario (§3).
>
> Decisión de origen: REGISTRO 2026-10-19 (*«sumar vp9 y vp8 bien, h265 no lo
> vamos a usar… y alguna manera de aprovechar las transparencias de canal alfa
> donde corresponde»*). **H.265 no se emite.** Tarea: H-28 en
> [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).

---

## 1. Cómo se emite

```
py.cmd repo\tools\emit_alfa.py C:\efecto.mov --out outputs\alfa
py.cmd repo\tools\emit_alfa.py C:\efecto.mov --out outputs\alfa --medir-palancas
py.cmd repo\tools\emit_alfa.py C:\efecto.webm --out outputs\alfa --solo vp9 --vp9-crf 28
py.cmd repo\tools\emit_alfa.py --hacer-sintetico outputs\sintetico.mov
```

**Entrada:** una fuente **con canal alfa**: ProRes 4444 (`.mov`), QuickTime
Animation (qtrle), PNG en secuencia (`efecto%04d.png`) o WebM con alfa. Si el
`pix_fmt` no trae alfa, el programa **se niega** (código 3) y dice que se use
`emit_v2.py`. Un WebM con alfa dice `yuv420p` y lo anuncia con la etiqueta
`ALPHA_MODE=1`; se lee con el decoder de libvpx (`-c:v libvpx-vp9` /
`libvpx` **antes** del `-i`), porque **el decoder nativo de ffmpeg descarta
el alfa sin avisar**.

**Salida** (en `--out`):

| archivo | qué es |
|---|---|
| `alfa-vp9.webm` | VP9 + alfa (`yuva420p`, `auto-alt-ref 0`) + Opus 64k si hay audio |
| `alfa-vp8.webm` | VP8 + alfa (`yuva420p`, `auto-alt-ref 0`) + Opus 64k si hay audio |
| `opaco-vp9.webm` + `opaco-h264.mp4` | **en lugar de las dos de arriba** si el canal resulta siempre opaco (§2 a) |
| `MANIFEST-alfa.tsv` | mismas columnas que v0/v1/v2 + `lienzo`, `rect` (dónde va la pieza) y `tiempo` (desde qué cuadro) |
| `INFORME-alfa.txt` | lo que dice el canal y las decisiones tomadas |
| `PALANCAS-alfa.tsv` | con `--medir-palancas`: el Δbytes de cada palanca (§3) |

Código 5 = se emitió pero sonó una alarma (color o alfa): **no se publica**.

Opciones que deciden bytes: `--ancho` (1280; 0 = el de la fuente), `--fps`
(15, la receta v2), `--vp9-crf` (30), `--vp8-crf` (24), `--vp8-tope` (4M),
`--vp9-2pass`, `--limpiar plano|sangrado|no`, `--sin-recorte`, `--tiempo
auto|recortar|entero`, `--alfa-binario N`, `--solo vp9|vp8|h264`. La receta
canónica (sin rutas) queda en el manifiesto.

## 2. La cadena

1. **La fuente a la base, en RGBA**: `fps` primero, después el escalado
   lanczos **sobre alfa premultiplicado** (`premultiply` → `scale` →
   `unpremultiply`). Sobre alfa recto, el lanczos mezcla en el borde el color
   de lo invisible: el halo oscuro de los recortes. Efecto lateral medido: al
   escalar así, lo invisible sale negro.
2. **Pasada 1, el análisis del canal** (sin guardar cuadros):
   - siempre opaco;
   - rectángulo útil (la unión de alfa > 0 en todo el clip, con coordenadas pares);
   - cobertura;
   - cuadros vacíos, separando las puntas de los huecos interiores;
   - qué parte de lo visible es semitransparente;
   - el color medio de lo visible.
3. **Pasada 2, las palancas**, cuadro a cuadro, todo en enteros:
   - **(a) Siempre opaco** → no es una pieza alfa. Se avisa y se emiten
     `opaco-vp9` + `opaco-h264` (por hardware, más livianas). Para el pack
     v2, `emit_v2`.
   - **(b) RGB bajo alfa 0**: `plano` (el color medio; default),
     `sangrado` (el borde extendido 8 px y después plano) o `no`.
   - **(c) Recorte** al rectángulo útil. La posición queda en el manifiesto
     (`# rect x y ancho alto` sobre el `# lienzo`).
   - **(d) Tiempo**: los cuadros vacíos de las puntas son hueco, no video.
     `auto` = recortar **solo si no hay audio**, porque el sonido puede
     empezar antes que la imagen. El manifiesto dice desde qué cuadro arranca
     la pieza.
   - **(e) Loops**: no se evalúan acá. Correr `tools/buscar_loops.py` sobre
     la fuente; si repite, una vuelta + `docs/INTRO-Y-LOOP.md`.
   - **(f) Alfa binario** (`--alfa-binario 128`): todo o nada, apagado por
     default (§3).
4. **La referencia** `work/ref.yuva` (yuva420p crudo): RGBA → YUV con la
   matriz 709 y rango tv **declarados en la conversión**; la entrada es RGB,
   así que no hay matriz que adivinar. Entra a los encoders **etiquetada 709
   antes del `-i`** (regla de color del 2026-10-18).
5. **Cada pieza se mide** decodificándola con su alfa:
   - **PSNR de luma** donde la referencia se ve.
   - **PSNR del compuesto**: el efecto puesto sobre gris medio, en Y, U y V, contando solo donde hay algo. Es el borde como lo ve el ojo, croma incluida; un halo o un tinte aparecen acá y no en la luma suelta.
   - **Error medio del alfa**.
   - **Alarma de color**: la luma media de lo visible contra la que da la fórmula 709 calculada en numpy desde el RGBA, aparte de ffmpeg; umbral ±1 tono.
   - **Alarma de alfa**: si la pieza decodificada salió opaca.

## 3. Lo medido (sintético, 2026-10-19)

**El sintético** (`--hacer-sintetico`, `ea05e8635db1…`, 937 MB) es ProRes
4444 a 1920×1080 @30, 4 s, con:

- 1 s transparente al principio;
- un disco de borde suave (30 px) que cruza la mitad izquierda;
- color **ruidoso debajo del alfa 0**, el peor caso de un exportador;
- un tono de audio.

En el lienzo de 1280×720 @15 queda así:

- rectángulo útil 898×360 en x 258 y 180 (35,1 % del lienzo);
- cobertura 8,3 %;
- 21,2 % de lo visible es semitransparente;
- 15 de 60 cuadros vacíos, en la punta.

**Las palancas**, VP9 crf 30, sin audio, `--tiempo recortar`
(`PALANCAS-alfa.tsv`). Cada fila apaga o cambia una palanca contra la
receta, que en esta corrida era `sangrado`:

| palanca | lienzo | bytes | Δ | compuesto | contra la receta |
|---|---|---:|---:|---:|---:|
| receta (sangrado) | 898×360 | 536.049 | — | 39,05 | 39,05 |
| sin limpiar | 898×360 | 427.240 | −20,3 % | 38,99 | 38,99 |
| **plano** | 898×360 | **421.718** | **−21,3 %** | 39,03 | 39,03 |
| sin recorte | 1280×720 | 585.503 | +9,2 % | 38,99 | — |
| sin hueco (60 cuadros) | 898×360 | 548.472 | +2,3 % | 39,07 | — |
| alfa binario 128 | 898×360 | 382.656 | −28,6 % | 38,39 | **32,85** |

Sin escalar (`--ancho 0`, 1920×1080), el ruido de debajo **sobrevive**, y ahí
se ve la palanca grande: **no limpiar cuesta +170,6 %** (3.734.362 contra
1.380.049 B). Plano vuelve a costar −3,3 % contra sangrado, el recorte −0,1 %
(lo invisible, limpio, ya no cuesta) y el alfa binario −8,3 %.

Lecturas:

- **Limpiar es obligatorio, y `plano` alcanza.** Plano cuesta 21 % menos que
  el sangrado y da el mismo compuesto. El sangrado arrastra hacia afuera la
  textura del borde y el ojo no gana nada. **Default: `plano`.**
- **El recorte vale por lo que no se decodifica.** Ahorra 8 % de bytes a
  1280, pero sobre todo baja la decodificación **por software** (el alfa en
  Chromium no va por hardware) al 35 % de los píxeles. **Default: on.**
- **El hueco** de las puntas vale poco (2 %) y además ordena el tiempo
  (`# tiempo`).
- **El alfa binario ahorra mucho y se ve.** −29 % de bytes, pero el borde
  pierde 6 dB contra la verdad suave. **Apagado por default; lo decide el
  ojo** con un clip real (un recorte de persona necesita borde suave; una
  gráfica plana quizá no).

**VP9 contra VP8 a la misma imagen** (con Opus; el compuesto es la escala
común):

| compuesto | VP9 | VP8 | VP8 / VP9 |
|---:|---|---|---:|
| ≈ 40,5 dB | crf 24 → 701.539 B | crf 16 → 880.547 B | +25 % |
| ≈ 39,0 dB | **crf 30 → 470.532 B** | **crf 24 → 749.433 B** | **+59 %** |
| 37,25 dB | crf 36 → 298.374 B | crf 32 → 628.436 B | +110 % |

**Defaults: VP9 crf 30 y VP8 crf 24**, la misma imagen. VP8 queda como la
pieza para un aparato que no tenga VP9; cuesta más y la diferencia crece
cuanto más se comprime.

**Dos pasadas** (`--vp9-2pass`) funcionan con alfa, pero en la prueba previa al emisor
dieron +7,6 % de bytes por −0,14 dB: quedan como opción, no como receta.

**Determinismo:** dos corridas completas en paralelo dieron los mismos bytes
y el mismo manifiesto: `alfa-vp9.webm` `3bafca752333…` (470.532 B) y
`alfa-vp8.webm` `111e43a44dbd…` (1.169.858 B, con el crf 10 de esa corrida).
Opus no es cpu-independent (P-010): la huella de una pieza **con audio** es
la de esta máquina.

**Color:** las dos piezas quedaron en **+0,01 / +0,02 tonos** de luma contra
la fórmula 709 (umbral ±1). Antes de escribir el emisor se verificó la
conversión RGBA → yuva420p del ffmpeg del bundle contra la fórmula:

| matriz | sesgo | error medio |
|---|---:|---:|
| 709 | +0,008 | 0,25 tonos |
| 601 | −0,36 | 8 tonos |

**Los otros caminos**, probados de punta a punta:

- **Fuente siempre opaca** (testsrc2 en ProRes 4444): emite `opaco-vp9` y
  `opaco-h264`.
- **Fuente sin alfa** (H.264 yuv420p): código 3.
- **WebM con alfa como fuente** (la pieza VP9 de arriba): leído con
  `libvpx-vp9`, el alfa entra vivo, los 15 cuadros vacíos siguen exactamente
  en 0 y el rectángulo es el cuadro entero (ya era la pieza recortada).

## 4. Qué tiene que hacer la página

La pieza **no** es necesariamente del tamaño de la pantalla:

- Va en `# rect x y ancho alto` sobre un `# lienzo` (1280×720). La página
  la estira con la misma proporción que el video base: posición absoluta,
  `left = x / lienzo_ancho` y `width = ancho / lienzo_ancho`, en % del
  plano.
- Arranca en el cuadro `# tiempo` (en segundos, al lado).
- El alfa en Chromium se decodifica **por software**. Por eso la caja
  (Chromium 70) y el Smart TV (Chrome 142) dicen cuánto sostienen, igual
  que en H-18b (dos planos).

## 5. Qué falta para cerrar H-28 (en orden)

1. **Un clip real con transparencia** del operador: emitir, `--medir-palancas`,
   anotar en el REGISTRO.
2. **Planos en `v1/`** — **HECHOS en el repo (2026-10-19), falta publicar**:
   `frontend/v1.html` tiene un segundo `<video id="efecto">` que va encima,
   puesto por `rect` y escalado con el plano (también a pantalla entera); la
   misma tecla pausa los dos y el zócalo cuenta los caídos de los dos.
   `v1-planes.tsv` suma las columnas opcionales `encima rect bytes_encima
   sha256_encima` y las teclas **8** (v1 + `alfa-sintetico-vp9.webm`) y **9**
   (v1 + `alfa-sintetico-vp8.webm`), con el v1 fluido abajo para que una
   traba sea del alfa. Verificado en el Chromium del escritorio: el alfa
   compone (disco con borde suave, lo demás transparente), VP8 también, y el
   plano 1 suelta el archivo del efecto. Ese navegador encontró un bug que el
   test no veía (`display = ""` le devolvía el control al CSS, que lo
   escondía): ahora `block` y el test lo fija. **Publicar** = 4 keys en
   `player/v1/` (`index.html`, `PLANES.tsv` y los dos webm de
   `vgen-portable\outputslfa-sintetico\`, renombrados) con el ritual de
   `deploy/asciline-player/README.md`: hace falta la API de Cloudflare que
   pone el secreto `UPLOAD_TOKEN`. Después, la foto y el veredicto de la caja y
   del Smart TV (caídos ≤ 3 % y el ojo).
3. **Alfa binario a ojo** con el clip real.
4. **Loops** (palanca e): si el efecto repite, una vuelta.
