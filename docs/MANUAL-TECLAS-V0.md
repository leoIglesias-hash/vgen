# Manual de teclas de la página v0

> Para leer **desde la PC** mientras se prueba en la caja. La página
> (`https://iargen.com/player/v0/`) muestra en pantalla **solo las teclas
> vigentes**; todo lo demás sigue andando pero no ocupa lugar, y se busca acá.
>
> Pedido del operador, 2026-09-04: *«en vez de darme todas las opciones en
> pantalla largame un archivo manual donde yo desde la pc pueda saber qué
> aprieto para las opciones que ya probamos y que van a estar ocultas (dejá al
> menos 10 siempre a la vista, alineada a la izquierda dándole más lugar a los
> logs de prueba para que bajen mientras probamos)»*.

## Cómo se aprieta

El control remoto manda números. Las teclas de **dos cifras** se escriben
seguidas: el `7`, el `8` y el `9` son puertas, no acciones. La página muestra
abajo a la izquierda lo que se va tecleando (`8_`, `83_`) y ejecuta cuando pasan
900 ms sin otra tecla, así que **una tecla de una cifra tarda un momento en
salir**: es normal, está esperando a ver si viene la segunda.

## Lo que se ve en pantalla (19 teclas)

**Lo que hay que probar**

| tecla | qué hace |
|---|---|
| `77` | **el producto** (H-8a): salta a `producto.html`, la forma del producto entera — loop en bucle desde la caché, publicidad, incentivador, radio y capa. Sus teclas son de **una cifra** y están en la sección de abajo. Se vuelve con Volver (historial) |
| `84` | caché: baja y guarda Baseline + VP9, las reproduce desde ahí y mide el techo en tandas de 5 MB |
| `85` | **desde caché**: la tecla de después de apagar y prender. ¿Siguen ahí? ¿Arranca sin red? |
| `87` | **dos videos a la vez** (H-18b): el loop VP9 abajo y los **papelitos con alfa encima, exactamente del mismo tamaño**. Si el aparato compone, se ve un solo video con papelitos. La fila trae los cuadros caídos de los dos |
| `70` | **pantalla entera** (H-20): el video ocupando toda la superficie, en cuatro escalones — solo, con la capa, con el efecto, y todo junto. La nota dice a qué tamaño quedó y si el WebView concedió la pantalla completa de verdad |
| `71` | **los dos a ojo** (H-21): los mismos dos planos del `87`, pero **a toda la superficie, en bucle y sin un solo corte**, para mirarlos el rato que haga falta. No mide: el zócalo va contando los caídos vivos de los dos. Se sale con `71` otra vez o con `0` |
| `72` | **v1 con audio** (H-6/S13): `v1-vp9` (VP9 crf 38 + Opus) y `v1-h264` (High con B + AAC), **con sonido** — el video se destapa solo mientras mide. Si el aparato exige un gesto para sonar, la fila dice «no arrancó» y eso también es un dato |
| `74` | **radio + video** (H-6/S14): el mp3 del máster en un `<audio>` en bucle **y** el VP9 mudo en bucle a la vez. La nota trae «radio arrancó en N ms; deriva radio; **deriva A/V**» |
| `75` | **MSE vp9** (H-6/S11): los 16 segmentos WebM de `v1-vp9` por `SourceBuffer` |
| `76` | **lote v1**: las tres de arriba seguidas |
| `1` | **lo que falta**: corre solo lo que la caja todavía no consagró — el techo, los dos videos, la pantalla entera y, si está publicado, el pack v1 |

**Herramientas**

| tecla | qué hace |
|---|---|
| `83` | **capa a ojo**: prende el rectángulo; si no hay nada sonando arranca VP9 en bucle. Si el aparato pide un gesto para reproducir, lo dice |
| `86` | borrar la caché |
| `73` | **pantalla entera a ojo**: la prende y la apaga, sin medir. Se sale con `73` otra vez o con `0` |
| `95` | reporte a pantalla completa, **en dos columnas**, para la foto |
| `88` | **cerrar el reporte** y volver a la pantalla de pruebas |
| `93` | repetir la última corrida |
| `0` | cortar: deja la pantalla en cero sin recargar (también sale de la pantalla entera) |
| `94` | volver al lanzador (o atrás en el historial) |

## Lo que quedó oculto, y qué dijo la caja

Todas estas teclas **funcionan igual**. Están fuera de la leyenda porque la caja
ya las contestó y repetirlas no agrega información.

| tecla | qué hace | qué ya dijo la caja |
|---|---|---|
| `80` | lote de la capa: seis corridas (sin canvas / rect a 15 fps / pantalla) sobre Baseline y VP9, más `blob:` y blob concatenado | **la capa no cuesta un cuadro**: 0 caídos en las seis filas, a 703×396 y a 560×315 |
| `81` | capa sobre Baseline: las tres cargas | ídem |
| `82` | capa sobre VP9: las tres cargas | ídem |
| `2` | las tres piezas progresivas sueltas | fluidas por hardware a 720p@15, 0–2 caídos de ~155 |
| `3` | pieza con alfa sobre fondo verde (desde H-18b son **papelitos** sobre transparencia total, ya no el disco con el video adentro) | **compone**: se ve el verde alrededor de la figura |
| `4` | los tres empaquetados (HLS-TS, HLS-CMAF, DASH) | HLS-TS nativo **sí** pero irregular al arrancar; DASH **no** |
| `5` | las cinco del paquete (MSE, Blob, orden, cambio, bucle) | MSE sí: 2.033 ms, 0 atascos |
| `6` | solo H.264 Main | **Main = Baseline** → el decodificador es hardware |
| `7` | solo VP9 (**es puerta**: espera 900 ms por `70`/`73`) | «perfecto, hasta más fluido» |
| `8` | cambio de pieza: VP9 → Baseline → VP9 → Baseline | 305 ms a VP9, más de 1 s a Baseline |
| `89` | **correr todo**, incluido lo consagrado | es la vieja «correr todo»; útil para una foto completa |
| `90` | solo HLS-CMAF | — |
| `91` | solo DASH | no reproduce en esta clase |
| `92` | reproducir desde memoria (`blob:`) | arranque 517 ms contra 2.985 por red: **el arranque lo mandan los bytes** |
| `96` | MSE: init + 16 segmentos por `SourceBuffer` | anda |
| `97` | blob concatenado: init + 16 segmentos en un `Blob` | equivale al archivo entero |
| `98` | orden alterado (1-8, 13-16, 9-12) por MSE y por Blob | **solo por MSE `sequence`**; por Blob «se tilda» |
| `99` | bucle de 60 s con `loop` | el `loop` progresivo quedó refutado |

## Si no entran los números (H-22)

Las dos páginas dicen **lo último que el aparato mandó por el teclado**: en
`ir.html` es la línea verde de abajo de todo; en `v0/` es el final del zócalo.
Dice tipo de evento, `keyCode`, `which`, `charCode`, `key`, `code` y **dónde
estaba el foco**.

- Si nunca sale de **`tecla 0: ninguna todavía`**, los eventos **no llegan a la
  página**: se los queda el sistema o el lanzador del aparato. Eso no se arregla
  desde acá, pero saberlo evita seguir buscando en el lugar equivocado.
- Si **cambia** y el número igual no hace nada, el dígito llega por un campo que
  falta contemplar, y la línea dice exactamente cuál.
- Si dice **`foco=INPUT`**, los números se los está comiendo el campo de texto:
  apretá **Volver** para soltarlo (en `ir.html` además aparece el aviso naranja).

Una foto de esa línea contesta la pregunta entera.

## Parámetros de la dirección

Se agregan a la URL, separados por `&` después de un `?`.

| parámetro | para qué |
|---|---|
| `?base=` | de dónde bajar las piezas, si no es la carpeta de la página |
| `?delay=` | milisegundos de espera del teclado (por defecto 900) |
| `?ir=` | a dónde manda la tecla `94` |
| `?renderer=canvas2d` | **solo en la raíz** (`iargen.com/player/`), no en esta página: la abre sin WebGL. Desde el lanzador es la tecla `6` |

## Nota sobre la fuente

La capa dibuja con **Hobo** (`v0/HoboStd.ttf`). No se puede preguntar por
`document.fonts` —devuelve una promesa y el piso de compatibilidad del proyecto
la prohíbe—, así que la página **mide**: compara el ancho de `MMMMM` contra el
de `iiiii` **pidiendo la misma familia**, hasta 3 segundos. Monospace le da a
toda letra el mismo avance, así que anchos distintos solo pueden venir de Hobo.
La cabecera del reporte
dice `fuente hobo` o `fuente fallback` con cuántos milisegundos tardó. Si dice
`fallback`, lo que se ve está dibujado en monospace y la medición no está
mintiendo sobre eso.

## El producto (`producto.html`, H-8a — 2026-09-05)

No es una página de pruebas: es **la forma del producto** (PLAN §2.7), para
mirarla entera y traer la foto. Al abrir, baja **una vez** las piezas del
guion a IndexedDB (con progreso arriba a la izquierda) y arranca sola: el loop
en bucle por **MSE desde la caché**, mudo, con la radio aparte. Todas las
teclas son de **una cifra** y disparan al instante. El zócalo de abajo dice
qué suena, de dónde salió (`cache` / `red`), vueltas, atascos, caídos,
cuántas piezas están residentes, `red si|no` y el tiempo prendido.

| tecla | qué hace |
|---|---|
| `1` | **loop por MSE** — el anillo: los segmentos desde la caché en modo `sequence`, sin fin. **Es el bucle del producto.** Mirar `vueltas` subir con `atascos 0` |
| `2` | **loop por blob** — la pieza entera desde memoria; al terminar vuelve a 0 y **mide la costura** (ms). Es la caída si no hay MSE |
| `3` | **loop nativo** — `loop` del navegador (ya refutado en la caja); para comparar |
| `4` | **incentivador** — los papelitos con alfa entran **encima**, suenan una vez y salen solos. Se mide el arranque desde la caché |
| `5` | **publicidad** — reemplaza al loop **con su propio audio**, la radio baja con una rampa, y **vuelve sola** al loop. Se miden `ida` y `vuelta` |
| `6` | **radio** — prende o apaga la ambiente (`<audio>` aparte, en bucle). Si el aparato pide un gesto, el reporte lo dice |
| `7` | **capa** — **cicla**: los números encima (15 fps, leyendo el reloj del video; cambian con el papel, `RULETA` durante el incentivador) → **números + la imagen girando** (H-23: el logo, `drawImage` rotado con el reloj del video, una vuelta cada 4 s, encima del alfa) → apagada. El zócalo dice `capa num`, `capa num+img` o `capa no`; el reporte trae el costo de cada pintada por carga y la línea `imagen` (de dónde salió y cuánto tardó en llegar) |
| `8` | **teclas** — muestra o esconde la leyenda |
| `9` | **reporte** — a pantalla completa, dos columnas, para la foto; `9` vuelve |
| `0` | **cortar** — para todo; `1` vuelve a arrancar |

**Parámetros:** `?modo=mse|blob|loop` fuerza el bucle; `?radio=no` no la
prende sola; `?capa=si` prende los números al abrir y `?capa=imagen` también
la imagen girando; `?giro=<segundos por vuelta>` (2 por defecto, `4` la
lenta); `?cada=<vsyncs por pintada>` (4 = 15 fps, `2` = 30 fps);
`?capak=<0..1>` achica el buffer del canvas (`0.5` = 640×360);
`?reloj=timeout` vuelve al timer viejo; `?tope=<MB>` y `?fraccion=<0..1>`
ajustan el presupuesto de residencia (SPEC §5.2); `?base=` como en `v0/`.

**Lo que hay que traer de la foto** (SPEC-VGEN §12): `1` durante ≥ 10 min y
`9`; después `5`, esperar que vuelva, `9`; `4`, `9`; y la segunda apertura
(`leidas N, guardadas 0`) con la red cortada y la página ya abierta.
**Y la prueba que faltaba (H-23):** ya **dentro del producto**, apretar `7`,
y otra vez `7` (no es el `77` de v0: son dos pulsaciones de la tecla `7` del
producto; el zócalo tiene que decir `capa num+img` y la imagen girar en el
medio), después `4`, esperar que el incentivador salga solo, `9`:
mirar la línea `capa numeros+imagen … ms med / … max`, la línea `imagen lista
logo.png 210x150` y los `caidos` del incentivador y del loop. Y el ojo: si la
imagen gira suave encima de los papelitos con alfa.

## El lanzador (`ir.html`)

Es un archivo suelto que vive en **otro servidor**, no en el bucket del player.
Sus teclas:

| tecla | a dónde va |
|---|---|
| `1` | `player/v0/` — esta página de pruebas |
| `2` | `player/` — la raíz (producto 1280@15) |
| `3` | `player/1280-15/` |
| `4` | `player/1280-12/` |
| `5` | `player/1920-10/` |
| `6` | **`player/?renderer=canvas2d`** — la raíz **sin WebGL**. Es el escape de W-26: la raíz elige WebGL en los primeros 240 ms y en la caja esa GPU no presenta (pantallazo blanco) |
| `7` | **`player/v0/producto.html`** — **el producto** (H-8a): loop + publicidad + incentivador + radio, desde la caché. Una cifra, dispara al instante |
| `90` | `player/v0/` con retardo de tecla de 1600 ms |
| `91` | `player/v0/` con retardo de tecla de 400 ms |
| `0` | foco en el campo para escribir un destino a mano |

Ninguna otra tecla empieza con `6`, así que dispara al instante: no hay que
esperar el retardo de los códigos de dos cifras.
