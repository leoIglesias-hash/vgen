# Emisión v0 — el primer video, por suposición

> **Estado: es una apuesta escrita, no una conclusión.** v0 existe para
> *reproducirse* y decirnos si vamos bien. Cada parámetro sale de lo que sabemos
> que cada códec hace bien —no de una medición— y cada suposición tiene escrito
> **qué la refutaría**. Lo que sobreviva a v0 pasa a la matriz (H-6); lo que caiga
> se corrige y se vuelve a emitir.
>
> Norte: [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md). Método:
> [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md). Tareas: **H-9** (emisión) y
> **H-10** (reproducirlo) en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).
>
> **Primer reporte de aparato: la TV box, 2026-09-01** → veredicto de cada
> suposición en **§4.b**, suposiciones nuevas S9..S12 en **§4.c**, y el rumbo
> que sale de ahí en [`PLAN-IMPLEMENTACION-ASCLH.md`](PLAN-IMPLEMENTACION-ASCLH.md).

---

## 1. Por qué se arranca suponiendo

Decisión del operador, 2026-09-01, después de leer el plan anterior:

> *«el camino de H-4 no es el correcto porque nos basaríamos solo en 1 tv box,
> mejor tomar las bondades de cada encoder para crear el nuestro y ya. Y empezar
> con el primer video aunque sea basado en suposiciones: al probarlo podremos ir
> viendo si vamos en la dirección correcta paso a paso.»*

Tiene dos razones buenas y las dos valen como regla del proyecto:

1. **Una sonda sintética corrida en una sola caja sobreajusta.** Contestaría
   «qué puede *esa* caja», y el formato tiene que servir en todas. La respuesta
   que necesitamos no es la de un aparato: es **la intersección de varios**.
2. **Reproducir el material real responde más que un cuestionario.** `canPlayType`
   dice «probablemente»; un video que corre 15 segundos sin caer cuadros dice
   que sí. Y de paso responde cosas que la sonda no preguntaba.

**Por eso la sonda no se pospone: se disuelve dentro del primer video.** La
página que reproduce v0 (H-10) reporta como subproducto lo que la sonda iba a
preguntar —códecs declarados, cuál arrancó de verdad, cuadros caídos, panel real,
`blob:`, alfa— pero sobre material verdadero y en todos los aparatos del
operador, no en uno.

## 2. Qué le tomamos a cada códec (las «bondades»)

Esto es lo que compone la emisión. Ninguna de estas afirmaciones es nuestra: son
propiedades conocidas de cada formato. Lo nuestro es **elegir cuáles usar y
poder garantizarlas desde el máster**.

| Linaje | Lo que le tomamos a v0 | Por qué |
|---|---|---|
| **H.264 Baseline** | el **piso universal**: sin cuadros B, **una sola referencia**, GOP cerrado y corto | el buffer de referencias (DPB) es la memoria que estos SoCs tienen contada. Baseline con `refs=1` y sin B es el menor DPB posible y la menor latencia de reordenamiento. Además es lo único que reproduce absolutamente todo |
| **H.264 Main** | **CABAC y transformada 8×8** — la misma imagen con menos bits | en un decodificador de **hardware** esas etapas son silicio y salen casi gratis; en **software** son caras. Por eso Main no está en el pack para «ganar»: está como **detector**. Si Main pesa menos y reproduce igual de bien que Baseline, el decodificador es hardware y la pelea no es por aliviar el bitstream |
| **VP9 (WebM)** | **compresión** (mismo look por bastante menos banda) y, sobre todo, **alfa real**: un WebM con canal alfa lo compone el navegador solo | si un aparato reproduce YouTube bien, casi seguro tiene **VP9 por hardware** — es el camino más rodado del aparato, no el exótico. Y el alfa por video resuelve el «personaje sin fondo» con CPU ≈ 0, que es exactamente lo que el mp4 no sabe hacer |
| **AV1** | nada en v0 — queda como **columna futura** | codificar AV1 en el runner cuesta mucho tiempo y hoy no decide nada. Cuando aparezca un aparato que lo tenga por hardware, se suma una fila y listo: para eso el formato es códec-agnóstico |
| **DASH** | el **modelo de datos**: el pack v0 ya viene con manifiesto, y las piezas son piezas (no «el video») | desde el primer día el material se describe como biblioteca, no como archivo. Cambiar de pieza —o de música— es editar el manifiesto |
| **ASCILINE** | **los píxeles antes del códec**: paleta y look decididos offline, cortes conocidos, zonas planas donde va lo vivo | es la ventaja que ningún encoder genérico tiene. En v0 se usa poco a propósito (un eje por vez); en H-6 se explota |

## 3. El pack v0

Todas las piezas salen del **mismo máster** (`.asclv` `dcd6afb6…1632a`, 1280×720
@15) y comparten resolución y duración. Determinismo: hilos fijados y parámetros
registrados — mismo máster + mismos parámetros → mismos bytes.

| Pieza | Códec / contenedor | Parámetros de la apuesta | Qué pone a prueba |
|---|---|---|---|
| `v0-h264-baseline.mp4` | H.264 Baseline, MP4 | `profile=baseline level=3.1`, `bf=0`, `refs=1`, GOP cerrado de 15, `yuv420p`, `+faststart` | el piso: que ande en todo, con el mínimo DPB posible |
| `v0-h264-main.mp4` | H.264 Main, MP4 | igual, pero `profile=main` (CABAC + 8×8) | **hardware o software**: si esta gana, la memoria no era el cuello |
| `v0-vp9.webm` | VP9, WebM | calidad constante, GOP 15, hilos fijos | si VP9 existe y con cuánta banda menos |
| `v0-vp9-alpha.webm` | VP9 + alfa, WebM | `yuva420p`, recorte chico (no pantalla completa) | si el **personaje sin fondo** se puede hacer por video, con CPU ≈ 0 |
| `hls-ts/stream.m3u8` | HLS + MPEG-TS | **remux** de la pieza Baseline, segmentos de 1 s | HLS nativo en su forma más rodada |
| `hls-fmp4/stream.m3u8` | HLS + CMAF | ídem, con `init.mp4` separado | HLS nativo con **init compartido**, que es la forma de nuestro formato |
| `dash/manifest.mpd` | DASH + fMP4 | ídem, plantilla + timeline | **DASH nativo**: nuestro modelo de datos servido tal cual |
| `MANIFEST.tsv` | texto tabulado | una fila por pieza: id, rol, tipo MIME, archivo, bytes, sha256 | el embrión del manifiesto del formato |

**Los tres empaquetados son un REMUX, no una segunda codificación** (`-c copy`):
los mismos bytes de video, envueltos distinto. Cuestan segundos y no tocan un
píxel. Por eso pueden compararse contra la pieza progresiva de la que salieron:
la única variable es el empaquetado.

Y hay una razón para no dejarlos para después: **nuestro formato es «piezas +
manifiesto», y HLS/DASH son exactamente esa idea, ya probada y decodificada por
hardware.** Si un aparato reproduce un `.m3u8` nativo, en ese aparato el muxer
ES5 (H-8) puede sobrar: se emite la playlist y la plataforma hace la costura
sola, sin MSE. Eso hay que saberlo **antes** de escribir el muxer, no después.

El GOP de 15 cuadros a 15 fps es lo que permite cortar segmentos de 1 s
**exactamente en cuadros clave**: la estructura elegida en §3 es la que habilita
el empaquetado.

**Restricción de formato que aparece acá y no es negociable:** el manifiesto de
runtime **no puede ser JSON** — el gate ES5 del proyecto prohíbe `JSON` porque
los WebViews viejos del parque no lo garantizan. Va en **texto tabulado**,
partido con `split`. Vale para v0 y para el manifiesto definitivo del `.asclh`.

**Lo que v0 deja fijo a propósito** (un eje por vez): 1280×720, 15 fps constante,
sin audio, sin intervención, sin variantes de bitrate.

## 3.b Lo que salió (emisión del 2026-09-01, H-9)

Workflow `emitir-v0`, run **33566441576** (la segunda corrida, la que ya trae los
empaquetados), desde el máster `dcd6afb6…1632a` (1280×720, 15 fps, **231
cuadros** = 15,4 s).

| Pieza | Bytes | vs. Baseline | SHA-256 (12) |
|---|---:|---:|---|
| `v0-h264-baseline.mp4` | 9.551.715 | — | `cf927d578ab9` |
| `v0-h264-main.mp4` | 8.686.438 | **−9,1 %** | `b9b1e1f542fe` |
| `v0-vp9.webm` | 4.411.693 | **−53,8 %** | `5be4650747fd` |
| `v0-vp9-alpha.webm` | 4.664.676 | (lleva plano alfa) | `2b1fe6c3bfde` |
| `hls-ts/stream.m3u8` | 9.795.953 | +2,6 % (sobrecarga TS) | 16 segmentos |
| `hls-fmp4/stream.m3u8` | 9.555.175 | +0,04 % | 16 segmentos + init |
| `dash/manifest.mpd` | 9.555.712 | +0,04 % | 16 segmentos + init |

**Un hallazgo que vale por sí solo:** los segmentos de `hls-fmp4/` y los de
`dash/` son **byte-idénticos entre sí** (mismo md5, mismo tamaño, uno a uno).
O sea: un solo juego de piezas, dos manifiestos distintos. Es exactamente la
tesis del formato —piezas + manifiesto— comprobada sin escribir una línea de
muxer. Y la sobrecarga de empaquetar en CMAF/DASH es **0,04 %**; solo el TS
clásico cuesta 2,6 %.

### ⚠ El determinismo NO se cumplió en el carril H.264

La segunda corrida es, sin quererlo, una prueba del invariante 7 («mismo máster +
mismos parámetros → mismos bytes»). Resultado, textual:

- **VP9 y VP9+alfa: byte-idénticos** entre las dos corridas. ✔
- **Baseline y Main: NO.** Baseline 9.551.693 → 9.551.715 (+22 B), Main
  8.686.512 → 8.686.438 (−74 B), con SHA-256 distintos. ✘

Lo verificado sobre eso (no supuesto): **misma versión de ffmpeg** (6.1.1-3ubuntu5
en las dos), **línea de opciones de x264 idéntica** —incluidas `threads=1`,
`lookahead_threads=1`, `sliced_threads=0`—, y el primer byte distinto cae en el
**offset 605**, dentro de las tablas de muestras del `moov`: cambiaron los
tamaños de los cuadros, así que difiere el bitstream y no solo el contenedor.

**Hipótesis, marcada como hipótesis:** x264 con `mbtree` usa punto flotante, y
los runners de GitHub no son todos el mismo CPU; distintas rutas SIMD pueden
redondear distinto y cambiar decisiones de asignación de bits. Lo consistente con
eso es que VP9 (entero) sí sea determinista. **No está comprobado.** Lo resuelve
**H-14**: emitir la misma pieza dos veces *dentro de la misma corrida* — si ahí
salen iguales, el problema es entre máquinas y no dentro del encoder.

Esto **no invalida las mediciones de v0** (las dos son codificaciones válidas del
mismo máster y difieren en 0,0002 %), pero sí es una deuda abierta contra un
invariante del proyecto, y queda escrita como tal.

**Dos lecturas, las dos honestas:**

1. **VP9 comprime a menos de la mitad** que H.264 con la misma estructura y el
   mismo material. Si el aparato lo tiene por hardware (S3), es banda regalada.
2. **El piso cuesta caro en bytes:** el `producto.mp4` conocido —el que en la
   caja *«reproduce muy bien»*— pesa 4.130.240 B, o sea **2,3× menos** que
   nuestro Baseline. La diferencia no es misteriosa y hay que decirla completa:
   aquel salió con los **defaults de ffmpeg** (calidad más floja, GOP largo,
   cuadros B, varias referencias) y este lleva a propósito **CRF 20, GOP cerrado
   de 15, sin B y `refs=1`** — el DPB mínimo se paga en bitrate. Cuál de los dos
   precios conviene lo dice el aparato, no la tabla: si S2 se refuta (el
   decodificador es hardware), esa estructura estricta deja de valer lo que
   cuesta y H-6 la afloja.

Nada de esto se normaliza todavía: son bytes, no fluidez. La fluidez la dice
H-10.

## 4. Las suposiciones, con su refutación escrita

Esta tabla es el contrato del método: **cada fila dice qué creemos, por qué, y qué
hacemos si el video nos desmiente.** Ninguna pasa a la spec hasta que se haya
reproducido.

| # | Suposición | Por qué la creemos | Qué la refuta → qué hacemos |
|---|---|---|---|
| **S1** | H.264 Baseline 720p reproduce en todo aparato con `<video>` | `producto.mp4` (H.264 por defecto, 4,1 MB) *«reproduce muy bien»* en la caja; es el piso de HLS en todo el planeta | no reproduce en algún aparato → ese aparato queda fuera del piso y hay que bajar nivel/perfil |
| **S2** | Bajar el DPB (sin B, `refs=1`, GOP corto) alivia la memoria de video, que es el recurso escaso de estas cajas | es la memoria que el decodificador reserva sí o sí; el operador viene observando que estas cajas se ahogan con video denso | Main (CABAC, más referencias) reproduce igual o mejor y pesa menos → **el decodificador es hardware**, el alivio no pasa por el bitstream sino por **cantidad de cuadros y ancho de banda** → toda la matriz H-6 se reorienta |
| **S3** | Donde YouTube ande bien hay **VP9 por hardware** | YouTube sirve VP9 en Android TV; en la caja YouTube anda bien | VP9 no reproduce o cae cuadros → VP9 baja de «camino principal» a «camino de banda» donde el aparato lo tenga, y H.264 queda al centro |
| **S4** | El alfa de WebM lo compone el navegador sin CPU nuestra | es una propiedad estándar de VP8/VP9 en WebM | no transparenta (fondo negro) o cuesta cuadros → el personaje sin fondo vuelve al **sprite ASCILINE** sobre el canvas (N2), que ya sabemos hacer |
| **S5** | Un canvas encima del `<video>` no lo saca de su plano de hardware | es lo normal en navegadores modernos | caen cuadros al activar el canvas → **la intervención va al lado, no encima**: bifurcación de layout de todo el producto (se prueba en H-11) |
| **S6** | Menos cuadros = menos trabajo, lineal (fps variable por segmento) | en el contenedor la duración del cuadro es un dato, no bitstream | no baja el costo proporcionalmente → el ahorro está en otro eje (se prueba en H-6) |
| **S7** | Algún aparato del parque reproduce **HLS o DASH nativo** | HLS es nativo en Safari/iOS y en muchos Smart TV; el WebView de la caja es Android, donde lo normal es que **no** lo sea. La apuesta es débil a propósito | ninguno lo reproduce → el camino D no existe en el parque y **el muxer ES5 (H-8) es obligatorio**, no opcional. Si alguno sí → en ese perfil el muxer se puede saltear entero |
| **S8** | Las piezas se **intercambian sin recodificar**: segmentar es un remux | es la afirmación central del formato, y `-c copy` la ejecuta sin tocar un píxel | los segmentos no reproducen o se ve la costura → el modelo «piezas Lego» se cae y hay que revisar la estructura (GOP, init compartido) antes de seguir |

### 4.b Veredicto en la TV box (2026-09-01) — un aparato refuta, no consagra

Primer reporte de aparato (transcripción textual en el REGISTRO, entrada «H-10:
primer reporte de aparato»). Por el invariante VISION §8.11, «sostenida» acá
significa **sostenida en la caja**: falta una segunda clase de aparato o la
decisión manual del operador para normalizar.

| # | Veredicto en la caja | Qué falta |
|---|---|---|
| **S1** | **sostenida**: Baseline 0/156 caídos, 2.985 ms de arranque por red | segunda clase |
| **S2** | **el detector se resolvió: decodificador por hardware** (Main 1/153 con −9,1 % bytes). La suposición en sí (que el DPB chico alivie) **no se midió**: el Main de v0 lleva los mismos `refs=1` y sin B que Baseline, así que el par aísla la entropía. Y en esta caja no hay déficit de fluidez que aliviar → S2 **se reclasifica a bytes** (H-6) | fila de H-6 con `refs`/B relajados, medida por bytes con la fluidez como gate |
| **S3** | **sostenida a medias**: VP9 arranca en 931 ms y sostiene el reloj, pero el contador de cuadros no lo vio (`total 0`) | el **ojo** del operador; segunda clase |
| **S4** | **pendiente del ojo**: la pieza reprodujo (1/155) pero el reporte no dice si el fondo verde se vio | ¿verde o negro alrededor de la figura? |
| **S5** | sin probar | H-11 |
| **S6** | sin probar; **su valor cambia**: en esta caja los cuadros de menos ya no compran fluidez, compran bytes | H-6 |
| **S7** | **sostenida en la caja para HLS-TS** (2.012 ms, sin atascos) — la apuesta débil ganó justo donde se esperaba que perdiera. **Refutada para HLS-fMP4** (14.223 ms, 2 atascos) y **para DASH** (error) | segunda clase; en esta, el camino D = HLS-TS y nada más |
| **S8** | **sostenida en la caja**: 16 segmentos TS cosidos por la plataforma sin `waiting`; los CMAF decodifican desde el init compartido (154 cuadros) | la **costura visual** la firma el ojo; H-13 prueba el intercambio de orden |

### 4.c Suposiciones nuevas que salen del reporte (para H-13)

Mismo contrato: qué creemos, por qué, y qué hacemos si el aparato nos desmiente.

| # | Suposición | Por qué la creemos | Qué la refuta → qué hacemos |
|---|---|---|---|
| **S9** | **MSE reproduce los segmentos CMAF ya publicados** (`dash/init.m4s` + `chunk-*.m4s`) anexados a un `SourceBuffer` de `avc1.42E01F`, y sostiene los gates | `isTypeSupported` lo declara; los mismos segmentos ya decodificaron desde el init compartido (E7) | no reproduce o atasca → el camino B no existe en esta clase: la intervención N1 se hace por A (S10) o por D (playlist), y el muxer de H-8 no alimenta MSE |
| **S10** | **`init + segmentos` concatenados en un solo Blob es un archivo que `<video>` reproduce** como progresivo (un fMP4 es exactamente eso) | es la definición del contenedor fragmentado; el camino A ya reproduce Blobs (517 ms) | no reproduce, o reporta duración desconocida y rompe el bucle → el muxer de A tiene que rearmar `moov` (tablas de muestras) en ES5, que es más caro pero conocido; o A se limita a piezas enteras |
| **S11** | **VP9 también entra por MSE** con segmentos WebM (init + clusters), con el mismo modelo de init compartido | `isTypeSupported('video/webm; codecs="vp9"')` = sí; WebM segmentado es lo que DASH usa con VP9 | no reproduce → VP9 queda como pieza entera (A/C) y la intervención N1 en vivo va solo por H.264. Requiere emitir los segmentos WebM (H-6, emisión v1) |
| **S12** | **Las piezas se intercambian sin costura visible**: anexar los segmentos en otro orden (o concatenarlos en otro orden) reproduce sin `waiting` ni salto; y el **bucle** (`ended` → `play()` o `loop`) cose sin atasco | cada segmento arranca en cuadro clave cerrado y comparte init | se ve la costura o hay `waiting` en el corte → hay que revisar la estructura (GOP, init, `sidx`) antes de escribir H-7; el bucle se resuelve con dos elementos alternados **solo si** H-11 muestra que un segundo `<video>` no cuesta |

## 5. Lo que v0 **no** prueba

Para que nadie sobre-lea el resultado: v0 no dice nada todavía sobre escalones de
bitrate, fps variable, tiles, intercambio sub-cuadro (N4), caché, audio ni
intervención. Cada uno tiene su tarea. v0 responde una sola pregunta grande:
**¿por dónde entra el video en cada aparato?**

## 6. Cómo se lee el resultado

| Lo que pase | Lo que significa | Lo que sigue |
|---|---|---|
| Baseline anda en todo y VP9 también | mejor caso: piso garantizado + camino de banda | H-6 barre fps y estructura sobre VP9, con H.264 de piso |
| Baseline anda, VP9 no | el piso es el camino; VP9 queda por aparato | H-6 se concentra en estructura y cantidad de cuadros |
| Main ≥ Baseline en fluidez | el decodificador es **hardware**; el bitstream no es el cuello | se abandona el carril «aliviar el bitstream» y se ataca cuadros/banda |
| Alfa compone | el personaje sin fondo sale por video | N2 se reserva para texto y datos |

## 7. La regla de método que sale de acá

> **Ningún aparato solo define el formato.**

Toda decisión de emisión necesita **una fila por aparato** en el registro de
[`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §5, y se normaliza solo si gana en
**al menos dos clases** de aparato (caja / celular / Smart TV / escritorio) —o si
el operador la fija a mano, que siempre prevalece. Una caja sola puede *refutar*
(si algo no anda ahí, no anda), pero no puede *consagrar*.
