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

## Lo que se ve en pantalla (14 teclas)

**Lo que hay que probar**

| tecla | qué hace |
|---|---|
| `84` | caché: baja y guarda Baseline + VP9, las reproduce desde ahí y mide el techo en tandas de 5 MB |
| `85` | **desde caché**: la tecla de después de apagar y prender. ¿Siguen ahí? ¿Arranca sin red? |
| `87` | **dos videos a la vez** (H-18b): el loop VP9 abajo y los **papelitos con alfa encima, exactamente del mismo tamaño**. Si el aparato compone, se ve un solo video con papelitos. La fila trae los cuadros caídos de los dos |
| `70` | **pantalla entera** (H-20): el video ocupando toda la superficie, en cuatro escalones — solo, con la capa, con el efecto, y todo junto. La nota dice a qué tamaño quedó y si el WebView concedió la pantalla completa de verdad |
| `71` | **los dos a ojo** (H-21): los mismos dos planos del `87`, pero **a toda la superficie, en bucle y sin un solo corte**, para mirarlos el rato que haga falta. No mide: el zócalo va contando los caídos vivos de los dos. Se sale con `71` otra vez o con `0` |
| `1` | **lo que falta**: corre solo lo que la caja todavía no consagró — el techo, los dos videos y la pantalla entera |

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
| `90` | `player/v0/` con retardo de tecla de 1600 ms |
| `91` | `player/v0/` con retardo de tecla de 400 ms |
| `0` | foco en el campo para escribir un destino a mano |

Ninguna otra tecla empieza con `6`, así que dispara al instante: no hay que
esperar el retardo de los códigos de dos cifras.
