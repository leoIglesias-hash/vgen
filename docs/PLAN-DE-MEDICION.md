# Plan de medición — se mide **reproduciendo**, y nunca en un solo aparato

> **Reescrito el 2026-09-01** por decisión del operador: la sonda sintética (H-4)
> se descartó porque hubiera fijado el formato contra **una sola TV box**. El
> método ahora es: **emitir el primer video por suposición, reproducirlo en varios
> aparatos, corregir**. Las suposiciones y sus refutaciones están escritas en
> [`EMISION-V0.md`](EMISION-V0.md). Tareas: **H-9** (emitir), **H-10**
> (reproducir y reportar), **H-6** (matriz) en
> [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).

---

## 1. Las dos lecciones que ordenan el método

**Primera (2026-09-01, DIAG-002/003):** el proyecto ya se equivocó por suponer
capacidades. Se aceleró un player 100 % JS durante toda una fase (F9, W-16..W-25,
medido y publicado) y en la caja real dio **290 ms por cuadro contra 66,7 de
presupuesto**. El trabajo estaba bien hecho; la suposición de base estaba mal.

**Segunda (2026-09-01, misma tarde):** la reacción a esa lección casi nos hace
cometer el error simétrico — *medir una caja y diseñar el formato contra ella*.
Un formato que solo sirve donde se lo midió no es un formato.

De las dos juntas sale el método:

> **Se supone explícito, se reproduce en varios aparatos, y recién ahí se
> normaliza.** Una suposición escrita como suposición no es deuda: es una
> hipótesis con refutación. Una suposición escrita como norma sí lo es.

Y su corolario duro:

> **Ningún aparato solo define el formato.** Un aparato puede **refutar** (si algo
> no anda ahí, no anda) pero no puede **consagrar**. Para normalizar hace falta
> que gane en al menos **dos clases** de aparato — o que lo fije el operador.

## 2. Qué se mide reproduciendo (reemplaza a la sonda)

No hay página de cuestionario. La página que reproduce el pack v0 (**H-10**)
reporta esto **como subproducto de reproducir material real**, y se abre en todos
los aparatos del operador:

| Dato | Cómo sale de la reproducción | Qué decide |
|---|---|---|
| qué piezas **dice** que puede | `canPlayType` sobre las filas del `MANIFEST.tsv` | orden de preferencia declarado (a contrastar con el real) |
| qué pieza **arrancó de verdad** | evento `playing` + `currentTime` avanzando | el orden de preferencia real, que es el que vale |
| cuadros caídos / totales | `getVideoPlaybackQuality()` o `webkitDroppedFrameCount` | el veredicto duro de fluidez |
| tiempo hasta el primer cuadro | del `play()` al primer avance | costo de arranque y de configuración del decodificador |
| deriva `currentTime` vs. reloj | comparación en el loop | si el aparato sostiene la cadencia |
| atascos y costura del bucle | eventos `waiting` / `seeking` al reiniciar | picos de bitrate contra buffer |
| **hardware o software** | Main vs. Baseline: si la más comprimida no cuesta más, es silicio | **bifurca toda la matriz H-6** |
| alfa en WebM | la pieza con alfa sobre un fondo de color: ¿se transparenta? | si el personaje sin fondo va por video o por sprite |
| `blob:` reproduce | reproducir una pieza desde `URL.createObjectURL` | si existe el camino A (el piso de la caché) |
| panel real vs. superficie | `screen`, `devicePixelRatio`, `innerWidth` | cuánto píxel se regala (en la caja: 3840×2160 sobre panel de 1280×720) |
| **HLS / DASH nativo** | **reproduciendo** `hls-ts/`, `hls-fmp4/` y `dash/` en un `<video>`, no preguntando `canPlayType` | el **camino D**. Donde exista, el muxer ES5 (H-8) puede sobrar: la plataforma hace la costura sola, sin MSE |
| segmentación sin recodificar | los mismos empaquetados: si reproducen, las piezas se intercambian de verdad | valida la afirmación central del formato en hardware real |
| MSE / rVFC / IndexedDB | detección directa, en la misma página | caminos B, sincronía exacta, persistencia |

**Por qué `canPlayType` no cuenta como evidencia para HLS:** los WebViews de
Android suelen devolver cadena vacía para `application/vnd.apple.mpegurl` aunque
la plataforma reproduzca, y Safari devuelve `"maybe"`. Es una declaración, no un
hecho — justo lo que este plan dejó de aceptar. Se prueba tocando.

**Regla de firma:** todo lo que requiere pantalla **lo firma el operador**. La
página produce números; el veredicto de imagen es suyo y se transcribe textual.

## 3. Métricas del banco

Cuando una variante hay que compararla contra otra (H-6), se usan siempre las
mismas columnas, sobre el mismo aparato y en el mismo orden:

| Métrica | Qué revela |
|---|---|
| cuadros caídos / totales | fluidez |
| tiempo hasta el primer cuadro | arranque y configuración del decodificador |
| deriva contra reloj | si sostiene la cadencia |
| atascos (cuenta y duración) | picos de bitrate contra buffer |
| bytes de la pieza | el precio de esa fluidez |
| lo mismo **con la capa de intervención activa** | el costo real de las dos capas (H-11) |

## 4. Matriz de emisión (H-6) — se barre **después** de v0

v0 elige el terreno; la matriz optimiza dentro de él. Los ejes, en orden de
ahorro esperado:

| Eje | Valores | Estado |
|---|---|---|
| **códec** | H.264 Baseline / Main / VP9 (+ AV1 cuando exista aparato) | **es v0** — el resto de la matriz depende de su resultado |
| **cantidad de cuadros** | fijo 15 vs. **variable por segmento** derivado del máster | el ahorro más grande y más barato si S6 se sostiene |
| **estructura** | GOP, cuadros clave en los cortes, `refs=1`, sin B | mide S2 (memoria de decodificación) |
| **bitrate / calidad** | escalones sobre el look del máster | dónde está el codo entre bytes y fluidez |
| **zonas estáticas** | máster con fondo idéntico bit a bit vs. sin esa garantía | lo que ningún encoder genérico puede garantizar y nosotros sí |
| **paleta** | actual vs. paleta separada en **luma** (consciente del 4:2:0) | si el submuestreo de color deja de dañar los bordes duros |

**Advertencia al leer los resultados:** los trucos clásicos para aliviar H.264
(entropía más simple, filtro de bloques apagado) solo rinden si el decodificador
es **por software**. En hardware esas etapas son silicio y son casi gratis; ahí
lo que cuesta es **ancho de banda de memoria, cantidad de cuadros, tamaño del
buffer de referencias y picos de bitrate**. Por eso v0 lleva la pieza Main: es el
detector, y su resultado reorienta la matriz entera.

**Cierre de H-6:** tabla de variantes en el REGISTRO con la medición **por
aparato** por fila, y la receta elegida **por perfil de dispositivo** —no una
receta global—, firmada por el operador.

## 5. Registro de aparatos

Se llena reproduciendo el pack v0 (H-10). **Los perfiles P0..P3 de
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md) §7 se asignan desde esta tabla**,
y ninguna fila sola alcanza para normalizar nada (§1).

| Aparato | WebView / navegador | Baseline | Main | VP9 | alfa WebM | `blob:` | MSE | IndexedDB | cuadros caídos | rVFC | canvas encima | panel vs. superficie | Perfil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TV box (la de DIAG-002/003) | | ✓ (el `producto.mp4` *«reproduce muy bien»*) | | | | | | | | | | 1280×720 panel / 3840×2160 superficie | |
| _(celular del operador)_ | | | | | | | | | | | | | |
| _(Smart TV del operador)_ | | | | | | | | | | | | | |
| _(escritorio)_ | | | | | | | | | | | | | |

Lo único ya medido de la caja está en el REGISTRO (DIAG-002/003, 2026-09-01): el
player 100 % JS da 290 ms/cuadro contra 66,7; el WebGL dibuja pero **no
presenta**; y `producto.mp4` (1280×720 @15, 4.130.240 B) *«reproduce muy bien»*
por `<video>` con decodificador de hardware.

## 6. Reglas del método

1. **Se supone explícito, se reproduce, y recién ahí se normaliza.** Toda
   suposición vive en [`EMISION-V0.md`](EMISION-V0.md) §4 con su refutación
   escrita. Ninguna entra en la spec sin haberse reproducido.
2. **Ningún aparato solo define el formato.** Refutar, sí; consagrar, no.
3. **Determinismo:** las variantes se generan desde el máster con parámetros
   registrados y hash; una variante que no se puede regenerar no se mide.
4. **Un eje por vez** cuando se pueda; si no, se anota la confusión en la fila.
5. **Lo que requiere pantalla lo firma el operador**, textual.
6. **Nada se estima.** Si un dato no se midió, la celda queda vacía — no se
   completa con lo probable.
7. **El ciclo se repite:** suponer → emitir → reproducir en varios aparatos →
   corregir → normalizar lo que ganó → volver a emitir. El formato se descubre,
   no se decreta.
