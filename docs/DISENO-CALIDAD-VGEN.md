# Calidad de imagen en 1280 con el front liviano — dónde se pierde hoy y qué palancas quedan

Pedido del operador (2026-09-07): *«pensemos en cómo mejorar el encode para
lograr una mejor calidad de video en 1280 pero manteniendo un nivel de
eficiencia y reproducibilidad livianos en el front… tomando ejemplos de los
mejores reproductores como YouTube pero destinado a esto, reproducibilidad
desde memoria, de forma eficiente, liviana y usando menos recursos»*. H-24 y
la radio quedan en pausa mientras se debate esto.

Este documento no decide nada: ordena la cadena, dice **dónde se pierde
calidad hoy** (medido o supuesto, marcado), lista las palancas con su costo
en el front (casi todas cero) y propone cómo medirlas. Lo que requiere
pantalla lo firma el operador.

## 1. Lo que cambió con el paradigma, y todavía no se cobró

Cuando el producto era el `.asclv` reproducido por JS, tres cosas mandaban
el encode y **ya no rigen**:

1. **Los bytes del `.asclv` viajaban al TV.** Por eso se adoptó pérdida en el
   máster para achicarlo: `--near-lossless 8` (E-24) y el refit de paleta
   (E-12), «pérdida mínima aceptable si el ahorro lo vale». En vgen el
   `.asclv` es **máster offline**: al TV viaja VP9/H.264. **Toda esa pérdida
   se puede deshacer gratis**, y el único costo aparece en los bytes del
   VP9, que se miden.
2. **La CPU del player JS fijaba resolución y cadencia.** 1280@15 se eligió
   a ojo en S-7 porque 1920@10 era *choppy* y 1920@15 no entraba en la CPU
   (DIAG-003: FRAME p50 233 ms en la caja). Con `<video>` por hardware la
   caja decodifica 1280@15 con 0 caídos, la superficie 4K no le cuesta
   (H-20) y sostiene dos planos (H-18b). **La fuente es 1920×1080 a ~24 fps**
   (REGISTRO 2026-08-30): hoy tiramos 9 cuadros por segundo y la mitad de
   los píxeles **antes** de codificar.
3. **El «look» indexado (paleta 256, graphic-hq, dither off) era además el
   formato.** Ahora es una elección estética. Hasta que el operador diga lo
   contrario, se asume que **el look se conserva** (es la identidad del
   producto); pero la pregunta va abajo (§5), porque cambia todo el diseño.

## 2. La cadena de hoy, pérdida por pérdida

| # | Paso | Qué se pierde | Estado |
|---|---|---|---|
| 1 | Fuente 1920×1080 ~24 fps → muestreo a **15 fps** sample-and-hold | 9 cuadros/s: el movimiento se ve a saltos | **medido** (S-7 lo eligió por CPU, no por imagen) |
| 2 | Reescalado a **1280×720** | la mitad de los píxeles; el TV lo vuelve a estirar a 1920 | medido (S-7) |
| 3 | Cuantización a **256 colores** por cuadro (kmeans-oklab) + `near-lossless 8` + refit 5 | banding en degradés suaves (el huevo, DIAG-001 pendiente), colores fusionados | **medido** (35,02 dB contra la fuente a 1280; el operador lo adoptó a ojo) |
| 4 | `rgb24 → yuv420p` en ffmpeg **sin matriz ni etiqueta de color** (`emit_pieces.build_command`: solo `-pix_fmt yuv420p`) | (a) croma a un cuarto de resolución: los bordes duros del look sangran color; (b) swscale usa **BT.601** por defecto y la pieza sale **sin etiquetar**; un decodificador HD puede asumir 709 → tonos y saturación corridos | (a) medido en el SSIM All de la matriz (incluye croma); **(b) SUPUESTO, no verificado** — hay que leer las piezas con `ffprobe` |
| 5 | **VP9 crf 38** `-deadline good -cpu-used 2`, GOP 15 cerrado, **sin alt-ref, sin lag, una pasada** | −0,0053 de SSIM contra crf 32 (al borde de la tolerancia); las herramientas de calidad de libvpx están apagadas | **medido** (H-6): el eje «contenido» de VP9 dio bytes idénticos porque `good` ya era aq 0 y sin alt-ref; **alt-ref + lag + 2 pasadas nunca se midió** |
| 6 | TV: decodifica por hardware y escala 1280 → 1920 (o 3840 en la caja) | el escalado del hardware, que no elegimos | medido (H-20: no cuesta fluidez) |

La única pérdida que el front paga es la 6, y no cuesta. Las otras cinco son
del encoder, y el encoder puede ser todo lo caro que haga falta.

## 3. Palancas, por impacto esperado y costo en el front

Ninguna toca `producto.html` por cuadro. Se listan de la más segura a la
más ambiciosa. «Bytes» es el único precio, y lo paga la residencia (tope 150
MB; hoy el pack v1 entero pesa 11 MB).

### E-A · Máster sin pérdida (deshacer E-24/E-12)

`--near-lossless 0`, refit como esté mejor, mismo perfil. Ataca el banding
(paso 3) sin tocar nada del front. Costo: el VP9 sube, porque el máster deja
de «regalar» zonas quietas por cuadro; hay que medir cuánto. **Reemplaza a
F10 (pérdida adaptativa) y a DIAG-001**, que existían para achicar un
`.asclv` que ya no viaja.

### E-B · Cadencia de la fuente y resolución: 1280@24 y 1920@24

El front reproduce lo que le den (regla 9 del repo viejo, y hoy por
hardware). La capa sigue a 15 pintadas por segundo leyendo `currentTime`
(H-11): no cambia. Costo: bytes (~1,6× por la cadencia, ~2× por la
resolución, a medir) y tiempo de encoder del máster (S-4: 1280@15 tardó 60
min de CI; a 1920@24 será ~3-4 h → **el bundle P-008 lo hace en la máquina
del operador sin cola**). Gate: la caja con `70`/`71` a 24 fps (nunca se
midió `<video>` a 24 en la caja; sí 15).

### E-C · Color correcto (matriz 709 + etiquetas + rango)

Fijar `-vf scale=out_color_matrix=bt709:out_range=tv` y etiquetar
(`-colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range
tv`) en las piezas. Es corrección, no compresión: cero bytes, cero front.
**Primero verificar** con `ffprobe` qué llevan hoy `v1-vp9.webm` y
`v1-h264.mp4` (`color_space`, `color_range`); si están «unknown», se
compara a ojo en la caja la misma pieza con y sin etiqueta (una tecla
nueva, dos piezas). Interacción con la regla 5: cambia la huella, se declara.

### E-D · VP9 con las herramientas de calidad encendidas

`-auto-alt-ref 1 -lag-in-frames 25 -arnr-maxframes 7 -arnr-strength 4`,
**dos pasadas** (`-pass 1/2`), `-enable-tpl 1`, y probar `-aq-mode 1|2`
solo en ese modo. Es lo que YouTube hace con VP9 y lo que la matriz **no**
midió (el eje «contenido» probó apagar cosas que ya estaban apagadas).
Esperable: mismos bytes con más SSIM, o mismo look con menos bytes; los
cuadros alt-ref viven dentro del GOP cerrado de 1 s, así que S12
(intercambio por segmentos) sigue valiendo. Dos gates: **determinismo** (dos
pasadas con `-threads 1` deberían ser bit-exactas: `portable` lo dice) y
**el decodificador de la caja con cuadros ocultos** (ARF): E-gate con una
tecla. El ffmpeg 8.1.2 del bundle trae libvpx moderno; el 6.1.1 de Ubuntu
ya no arbitra.

### E-E · Calidad constante por corte (per-shot), no CRF plano

Lo que Netflix/YouTube llaman *per-shot encoding*: el máster ya tiene
**cuadros clave en cada corte** (F2) y el pack ya se sirve **segmentado** al
anillo MSE (S11/S12). La palanca es elegir el CRF **por corte** para una
calidad objetivo (SSIM/VMAF contra la fuente) y emitir cada corte como su
propio segmento (largo variable; el anillo no distingue). El front **no
cambia**: sigue anexando segmentos en orden. El encoder paga N codificaciones
por corte. Es la novedad más «de reproductor grande» que cabe en vgen sin
tocar el aparato.

### E-F · Escalera por clase: elegir una vez, guardar una

ABR de YouTube adapta al ancho de banda cuadro a cuadro; vgen no tiene ese
problema: baja **una vez** y reproduce desde el aparato. La versión vgen es
una escalera de 2-3 CRF en el manifiesto y **una elección por aparato** (por
clase y presupuesto, o manual del operador): el `GUION.tsv` ya tiene
`prioridad`; falta que una pieza pueda declararse «alternativa de» otra y que
el plan elija una sola. El Smart TV (Chrome 142, `quality si`) puede además
medir caídos y bajar un escalón; la caja no mide, elige por clase.

### Lo que NO se propone

- **AV1 / HEVC / VP9 10-bit / 4:4:4:** el decodificador de la caja (Chromium
  70) no los presenta o no está probado; el 10-bit sí atacaría el banding
  (paso 3), pero E-A lo ataca antes y sin apostar al hardware. Se anota, no
  se ejecuta.
- **Interpolar cuadros, escalar o filtrar en el front:** toda la regla del
  proyecto es al revés (caro offline, trivial en el aparato); H-23 mostró
  que presentar el canvas ya cuesta.
- **Cadencia variable (S6):** refutada para este máster (H-6).

## 4. Cómo se mide sin engañarse

- **Referencia común: la fuente**, no el máster. Si E-A/E-B cambian el máster,
  medir contra el máster viejo no sirve. La matriz (`tools/emit_matrix.py`,
  P-007) se extiende con: referencia = fuente reescalada a la resolución de
  la pieza; ejes `vp9-2pass` (E-D), `color` (E-C), `master` (E-A: mismo VP9
  sobre dos másters) y `cadencia/resolución` (E-B). SSIM/PSNR de ffmpeg como
  hoy; VMAF solo si el binario lo trae (el essentials de gyan no; anotar).
- **Cada fila con bytes, SSIM, PSNR, segundos** y, para lo que va a la caja,
  la foto. El ojo del operador cierra, la tabla ordena.
- **Determinismo primero:** toda variante que entre al pack pasa por
  `portable` (dos runners). Dos pasadas de VP9 y filtros de color son nuevas
  fuentes posibles de no-determinismo.
- **Orden sugerido para medir** (cada paso es una corrida de la matriz +
  una foto): E-C (gratis y corrige) → E-D (mismo máster, ganancia pura) →
  E-A (máster sin pérdida) → E-B (24 fps, después 1920) → E-E → E-F.

## 5. Preguntas al operador (cambian el diseño)

1. **¿El look indexado sigue siendo el producto?** Si sí, E-A mejora el
   máster y todo lo demás va encima. Si el look fue un medio para el player
   JS, el vgen puede codificar **la fuente directa** (VP9 del 1920@24 sin
   cuantizar) y la calidad máxima está a un `crf` de distancia — pero es otra
   estética. No se asume: se pregunta.
2. **¿24 fps?** La fuente los tiene y el hardware los reproduce; el costo es
   ~1,6× bytes y tiempo de encoder. La capa no cambia.
3. **¿1920 o 1280?** El TV de destino es 1920. A 1280 el hardware estira;
   a 1920 pagamos ~2× bytes y el máster tarda horas (bundle local).
4. **Presupuesto por clip para la residencia:** con 150 MB de tope y 3-11
   MB por pack, hay margen para 24 fps y 1920 juntos; ¿el operador quiere
   fijar un techo por pieza (p. ej. 20 MB) para que la matriz tenga un gate
   de bytes además del de look?

Anotado como **P-009** en [`../PROPUESTAS.md`](../PROPUESTAS.md). Nada de
esto se implementa hasta que el operador conteste §5 y elija por dónde
medir.
