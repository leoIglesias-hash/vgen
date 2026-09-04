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
seguidas: el `8` y el `9` son puertas, no acciones. La página muestra abajo a la
izquierda lo que se va tecleando (`8_`, `83_`) y ejecuta cuando pasan 900 ms sin
otra tecla, así que **una tecla de una cifra tarda un momento en salir**: es
normal, está esperando a ver si viene la segunda.

## Lo que se ve en pantalla (12 teclas)

| tecla | qué hace |
|---|---|
| `80` | lote de la capa: seis corridas (sin canvas / rect a 15 fps / pantalla) sobre Baseline y VP9, más `blob:` y blob concatenado |
| `81` | capa sobre Baseline: las tres cargas |
| `82` | capa sobre VP9: las tres cargas |
| `83` | **capa a ojo**: prende el rectángulo; si no hay nada sonando arranca VP9 en bucle. Si el aparato pide un gesto para reproducir, lo dice |
| `84` | caché: baja y guarda Baseline + VP9, las reproduce desde ahí y mide el techo en tandas de 5 MB |
| `85` | **desde caché**: la tecla de después de apagar y prender. ¿Siguen ahí? ¿Arranca sin red? |
| `86` | borrar la caché |
| `1` | **lo que falta**: corre solo lo que la caja todavía no consagró. Hoy es el techo de la caché |
| `95` | reporte a pantalla completa, para la foto |
| `93` | repetir la última corrida |
| `0` | cortar: deja la pantalla en cero sin recargar |
| `94` | volver al lanzador (o atrás en el historial) |

## Lo que quedó oculto, y qué dijo la caja

Todas estas teclas **funcionan igual**. Están fuera de la leyenda porque la caja
ya las contestó y repetirlas no agrega información.

| tecla | qué hace | qué ya dijo la caja |
|---|---|---|
| `2` | las tres piezas progresivas sueltas | fluidas por hardware a 720p@15, 0–2 caídos de ~155 |
| `3` | pieza con alfa sobre fondo verde | **compone**: se ve el verde alrededor y el video en el círculo |
| `4` | los tres empaquetados (HLS-TS, HLS-CMAF, DASH) | HLS-TS nativo **sí** pero irregular al arrancar; DASH **no** |
| `5` | las cinco del paquete (MSE, Blob, orden, cambio, bucle) | MSE sí: 2.033 ms, 0 atascos |
| `6` | solo H.264 Main | **Main = Baseline** → el decodificador es hardware |
| `7` | solo VP9 | «perfecto, hasta más fluido» |
| `8` | cambio de pieza: VP9 → Baseline → VP9 → Baseline | 305 ms a VP9, más de 1 s a Baseline |
| `89` | **correr todo**, incluido lo consagrado | es la vieja «correr todo»; útil para una foto completa |
| `90` | solo HLS-CMAF | — |
| `91` | solo DASH | no reproduce en esta clase |
| `92` | reproducir desde memoria (`blob:`) | arranque 517 ms contra 2.985 por red: **el arranque lo mandan los bytes** |
| `96` | MSE: init + 16 segmentos por `SourceBuffer` | anda |
| `97` | blob concatenado: init + 16 segmentos en un `Blob` | equivale al archivo entero |
| `98` | orden alterado (1-8, 13-16, 9-12) por MSE y por Blob | **solo por MSE `sequence`**; por Blob «se tilda» |
| `99` | bucle de 60 s con `loop` | el `loop` progresivo quedó refutado |

## Parámetros de la dirección

Se agregan a la URL, separados por `&` después de un `?`.

| parámetro | para qué |
|---|---|
| `?base=` | de dónde bajar las piezas, si no es la carpeta de la página |
| `?delay=` | milisegundos de espera del teclado (por defecto 900) |
| `?ir=` | a dónde manda la tecla `94` |

## Nota sobre la fuente

La capa dibuja con **Hobo** (`v0/HoboStd.ttf`). No se puede preguntar por
`document.fonts` —devuelve una promesa y el piso de compatibilidad del proyecto
la prohíbe—, así que la página **mide**: compara el ancho del mismo texto en
`Hobo, monospace` contra `monospace`, hasta 3 segundos. La cabecera del reporte
dice `fuente hobo` o `fuente fallback` con cuántos milisegundos tardó. Si dice
`fallback`, lo que se ve está dibujado en monospace y la medición no está
mintiendo sobre eso.
