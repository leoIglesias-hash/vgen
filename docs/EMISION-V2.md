# Emisión v2 — el video desde la fuente

> **Estado (2026-09-08): primera emisión real HECHA desde la PC del operador**
> (Intel i7-13700H, bundle de la corrida 34083813584 = commit `17d9903`):
> fuente `6e78efa38e10…` **etiquetada 709 tv** (supuesto de §1 verificado),
> base 1280×720 @20 = 308 cuadros; `v2-vp9` **3.757.946 B** ssim 0,987 psnr
> 43,66 (`74ea7f4b…`, huella Intel por el Opus), `v2-h264` **6.600.291 B**
> ssim 0,990 psnr 44,52 (`f75a2125…`), `v2-ambiente.m4a` 614.020 B, DASH 16
> segmentos. **El techo de 20 MB queda 5× arriba**: el barrido (§4) se corre a
> crf bajos. Transcripción completa: REGISTRO 2026-09-08. La emisión la hace
> **el operador desde su PC** con el bundle (`emitir.cmd -Fuente …`),
> porque la fuente no está en el remoto público y porque así lo pidió:
> *«debe correr lo mismo de mi PC en CI; trabajaremos sobre eso cuando
> terminemos las optimizaciones desde la PC»*. El carril v2 del workflow
> `portable` (dos runners, `pack-v2`) se cablea **después**, cuando la receta
> esté elegida. Hasta entonces, la huella de v2 es el SHA-256 que imprime
> `emitir.cmd` y va al REGISTRO junto con la receta.
>
> Decisión de origen: [`DISENO-CALIDAD-VGEN.md`](DISENO-CALIDAD-VGEN.md)
> §5.3 (*«el look fue un medio»*). Plan B: [`EMISION-V1.md`](EMISION-V1.md)
> (el máster de 256 colores). Tarea: H-26 en
> [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).

---

## 1. Qué cambia respecto de v1

v0 y v1 codificaban **el máster `.asclv` decodificado**: cada cuadro
cuantizado a 256 colores, a 1280×720 y 15 fps, con la conversión
rgb24 → yuv420p sin matriz ni etiqueta de color. Ese look existió para que
el player JS fuera fluido; el `<video>` por hardware no lo necesita.

v2 codifica **el clip original**. La cadena, cada paso declarado
(`tools/emit_v2.py`):

| paso | v1 (plan B) | v2 |
|---|---|---|
| entrada | `clip.dcd6afb66907.asclv` (máster indexado) | la fuente (archivo local o URL + SHA-256) |
| cadencia | 15 fps (la del máster) | **20 fps** (`fps=20`: tira cuadros, no interpola; operador: «manejables, menos que 24») |
| resolución | 1280×720 (la del máster) | **1280 de ancho**, alto proporcional, **lanczos** (operador: «lo que los TV box resisten mejor, el resto lo estiramos») |
| color | rgb24 → yuv420p **sin** matriz ni etiqueta (supuesto 601) | **matriz 709, rango tv, etiquetas explícitas** en la referencia y en cada pieza (E-C) |
| VP9 | crf 38, una pasada, sin alt-ref | **dos pasadas + alt-ref + lag 25 + arnr + tpl** (E-D), crf de la matriz v2 |
| H.264 | High crf 23, 3 B, ref 4 + AAC 96k | High crf de la matriz, 3 B, ref 4 + **el audio de la fuente copiado** si es AAC |
| GOP | 15 cuadros (1 s) | **20 cuadros (1 s)**: los segmentos de 1 s del anillo siguen arrancando en cuadro clave cerrado |
| radio | el mp3 del máster tal cual | la pista de la fuente **tal cual** (`.m4a` si es AAC, `.mp3` si es mp3; otra cosa → AAC 128k) |
| MSE | `dash-vp9/` | `dash-v2-vp9/` (no pisa al de v1 cuando comparten carpeta) |
| techo | — | **20 MB por pieza de video**: se marca, avisa y no se publica |
| calidad | SSIM contra el máster | **SSIM/PSNR contra la fuente llevada a la base** (la referencia y4m) |

Lo que **no** cambia: el anillo MSE, la residencia (IndexedDB, pineo por
contenido), la capa, las teclas, el ES5 del front. v2 es otra pieza con el
mismo manifiesto (`MANIFEST-v2.tsv`, mismas siete columnas que v0/v1) y la
página la anexa con el mismo parser.

## 2. La receta de arranque

```
--fps 20 --ancho 1280 --vp9-crf 34 --h264-crf 21 --techo 20000000
```

Es la **apuesta**, no un resultado: `crf 34` es el centro del eje que el
diseño propuso (34..42) y `h264-crf 21` dos escalones más generosos que v1,
porque el material ya no es plano. La matriz v2 la corrige (§4). Está en
tres lugares y un test los cruza (`tests/test_portable_bundle.py`):
`tools/portable/armar.py` (`RECETA_V2`, fila `receta_v2` de `VERSIONES.tsv`),
`tools/portable/emitir.ps1` (`-RecetaV2`) y este archivo.

Lo que la receta **no** dice y el emisor fija solo: `-threads 1`, muxado
bit-exacto, `-deadline good -cpu-used 2`, `-row-mt 0`, alt-ref/lag/arnr/tpl,
`cpu-independent=1` en x264, `-movflags +faststart`. Cambiarlos es cambiar el
emisor, no la receta.

## 3. Cómo se emite desde la PC (hasta que el CI lo reproduzca)

Con el bundle `vgen-portable` de una corrida del workflow `portable` **con
este commit o posterior** (el zip incluye `repo\tools\emit_v2.py`); si el
bundle es anterior, alcanza con copiar `tools/emit_v2.py`, `tools/emit_v1.py`,
`tools/emit_matrix.py` y `tools/portable/emitir.ps1` del repo encima de
`repo\tools\` y de la raíz del bundle.

```
emitir.cmd -Fuente "C:\ruta\TKN-2443-GANADOR- 15seg-.mp4"
```

Sale en `outputs\v2\`: `v2-vp9.webm`, `v2-h264.mp4`, `v2-ambiente.m4a` (o
`.mp3`), `dash-v2-vp9\`, `MANIFEST-v2.tsv`, y un `.ffmpeg.log` por pieza. La
primera línea de la salida dice de la fuente **su SHA-256 y sus etiquetas de
color** (`color: bt709 tv bt709 bt709` o `unknown …`): es la verificación que
el diseño §2 dejó como supuesto. Si dice `unknown`, la fuente HD se declara
709 con `--matriz-fuente bt709` en la receta.

Qué se reporta de cada emisión (va al REGISTRO): la línea `fuente …`, la
línea `referencia WxH @fps N cuadros`, las líneas por pieza (bytes, SSIM,
PSNR, cuadros, segundos) y los SHA-256 del final.

## 4. La matriz v2: elegir el crf bajo el techo

```
emitir.cmd -Fuente "C:\clip.mp4" -Receta "--barrer 10,14,18,22,26,30 --barrer-h264 11,14,17,20 --sin-piezas"
```

(Ejes corregidos el 2026-09-08 con la primera emisión: crf 34 dio 3,76 MB y
h264 crf 21 dio 6,6 MB, 5× por debajo del techo; el rango del diseño, 34..42,
no acorrala nada. Estos ejes van de ~2× el techo a ~4 MB.)

Emite `v2-vp9-crfNN` (dos pasadas, sin audio) por cada crf, y `v2-h264-crfNN`,
mide SSIM y PSNR **contra la fuente llevada a la base**, y deja
`MATRIZ-v2.tsv` más una tabla en pantalla con `pasa` / `SUPERA` por fila.
Regla acordada: **el crf más bajo (más calidad) que quede bajo el techo** es
el candidato; el ojo del operador en la caja lo firma o sube un escalón.
`--sin-piezas` borra cada pieza tras medirla (solo la tabla); sin él quedan
para mirarlas. `--vp9-1pass` acota (una pasada, misma receta) si hay que
saber cuánto compran las dos pasadas.

Techo: 20 000 000 B por pieza de video (el ejemplo de la pregunta 4). Se
ajusta con las primeras filas si resulta que todo pasa de sobra o nada pasa.

**Resultado (2026-09-08, PC del operador, 615 s;** archivo
[`matrices/2026-09-08-MATRIZ-v2-pc-operador.tsv`](matrices/2026-09-08-MATRIZ-v2-pc-operador.tsv),
transcripción en el REGISTRO**):** VP9 **no llega al techo ni a crf 10**
(10.825.432 B, ssim 0,9938; crf 14 = 8,26 MB; 18 = 6,87 MB; 22 = 5,94 MB;
26 = 5,04 MB; 30 = 4,30 MB; 34 = 3,76 MB). H.264 lo cruza: crf 11 =
21.944.485 B **SUPERA**, crf 14 = 14.399.566 B pasa (ssim 0,9942), 17 = 9,68
MB, 20 = 6,71 MB. Por la regla, el candidato es **VP9 crf 10 + H.264 crf 14**;
como en VP9 el techo no decide, la alternativa de ahorro es crf 18 (mitad de
bytes por −0,002 de SSIM). El ojo del operador en la caja elige.

## 5. Determinismo y huella

Regla 5 / P-008b: el binario de referencia es el ffmpeg del bundle. Con
`-threads 1`, las dos pasadas de VP9 escriben su log de estadísticas en
`work\` y deberían reproducirse byte a byte en otra máquina con el mismo
zip; **eso no está verificado todavía** (es lo que el carril v2 del workflow
`portable` dirá cuando entre). El audio copiado de la fuente no pasa por
ningún encoder: determinismo gratis; Opus (webm) sigue siendo punto flotante
y **ya se sabe que NO se repite entre familias de CPU** (corrida
34083813584 del 2026-09-07: AMD e Intel emitieron `v1-vp9.webm` distinto
con el mismo zip, y el DASH sin audio idéntico). `v2-vp9.webm` hereda eso;
`v2-h264.mp4` no. Salida propuesta: P-010 (la pista Opus emitida una vez,
publicada pineada por contenido y muxeada por `-c:a copy`); hasta que el
operador decida, la huella del webm se declara **con la CPU que lo emitió**.

La receta viaja en el manifiesto como texto **canónico** (solo lo que decide
los bytes, sin rutas): así el `MANIFEST-v2.tsv` de la PC y el del CI pueden
coincidir línea a línea aunque la fuente viva en otra carpeta.

## 6. Qué falta para cerrar H-26 (en orden)

1. ~~**Primera emisión desde la PC** con la receta de arranque; reportar §3.~~
   HECHA 2026-09-08 (REGISTRO): 709 verificado, 3,76 / 6,6 MB, techo 5× arriba.
2. ~~**Matriz v2** (§4)~~ HECHA 2026-09-08 (VP9 crf 10 = 10,8 MB bajo el
   techo; H.264 cruza entre 14 y 11). Falta la **elección del crf** a ojo; si
   el ojo la firma, la receta nueva reemplaza a la de §2 en los tres lugares.
3. ~~**Publicar v2 en `v0/`** con el ritual (copia en `deploy/` antes) y una
   tecla que alterne **v1 (256 colores, 15 fps) / v2 (fuente, 20 fps)** a
   pantalla entera~~ HECHO 2026-09-08 (tarde): **las dos recetas** (crf 10 y
   crf 18, un solo H.264 crf 14) en `v0/` (42 keys, SHA verificados), tecla
   `78` (a ojo, en bucle, tres piezas) y `79` (lote medido). `producto.html`
   sigue con v1 hasta la foto.
4. **Foto de la caja**: v2 a 20 fps con caídos ≤ 3 % y el operador firma el
   look contra v1. Si la caja no sostiene 20, `--fps 15` desde la fuente
   antes de volver al carril v1.
5. **El CI reproduce lo de la PC** (pedido del operador): carril `v2` en el
   workflow `portable` (inputs `fuente_url`/`fuente_sha256`, dos runners,
   `pack-v2`), y `ffprobe` en la corrida verificando las etiquetas de color
   de v1 y v2. Requiere decidir dónde vive la fuente para el CI (bucket
   pineado por contenido, como el `.asclv`).
6. Papel: bytes, SSIM y huellas acá; SPEC §9 (carril v2 = huella del
   bundle); DISENO-CALIDAD §5.3 cerrado; REGISTRO.
