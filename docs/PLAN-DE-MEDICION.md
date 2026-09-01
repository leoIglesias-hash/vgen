# Plan de medición — sondas, banco y registro de aparatos

> **Este documento es lo que desbloquea al formato.** Mientras la tabla de §5
> esté vacía, cualquier spec que escribamos es ficción prolija:
> [`DISENO-FORMATO-ASCLH.md`](DISENO-FORMATO-ASCLH.md) §10 marca todo lo que
> depende de acá. Tareas asociadas: **H-4** (sondas), **H-5** (banco), **H-6**
> (matriz de emisión) en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).

---

## 1. Por qué esto va primero

El proyecto ya se equivocó una vez por suponer capacidades: se construyó un
player 100 % JS acelerado durante toda una fase (F9, W-16..W-25, medido y
publicado) y en la caja real dio **290 ms por cuadro contra 66,7 de presupuesto**.
El trabajo estaba bien hecho; la suposición de base estaba mal.

La regla que sale de eso, y que ahora es invariante del proyecto:

> **Primero se mide el aparato, después se normaliza el formato.**

Y su corolario heredado, extendido del byte al cuadro:

> **Una mejora sin fila registrada no existe** — vale igual para reproducción.

## 2. Sonda de capacidades (H-4)

Una página que se abre en cualquier aparato y responde **sí/no** a una lista
cerrada. No mide velocidad: establece qué caminos **existen**. Es barata, y sin
ella no se puede elegir nada.

| # | Pregunta | Cómo se responde | Qué decide |
|---|---|---|---|
| 1 | ¿Qué códecs y contenedores reproduce? | `video.canPlayType` sobre la matriz H.264 (Baseline/Main/High) × mp4, VP8/VP9 × WebM, AV1, HEVC | qué emitimos y en qué orden de preferencia |
| 2 | ¿VP9 va por **hardware**? | reproducir una pieza VP9 y comparar cuadros caídos y consumo contra la misma en H.264 | si VP9 es el camino principal (hipótesis: sí, porque YouTube lo usa en Android TV y en esta caja YouTube anda bien) |
| 3 | ¿Compone **alfa en WebM**? | reproducir un WebM VP9 con canal alfa sobre un fondo de color y ver si se transparenta | si el personaje sin fondo va por video (costo ~0) o por sprite |
| 4 | ¿Tiene **MSE**? ¿qué tipos acepta? | `window.MediaSource` + `MediaSource.isTypeSupported` | si existe el camino B (clips largos, empalme en vivo) |
| 5 | ¿Reproduce desde **`blob:`**? | `URL.createObjectURL` de un mp4 chico en `<video>` | si existe el camino A (el piso de todo) |
| 6 | ¿**IndexedDB** guarda blobs y **persiste** entre arranques? | escribir, cerrar, reabrir, leer; anotar el cupo | si el paquete vive en el aparato o se baja siempre |
| 7 | ¿Existe **`getVideoPlaybackQuality()`** (o `webkitDroppedFrameCount`)? | detección directa | si podemos medir con números en vez de a ojo |
| 8 | ¿Existe **`requestVideoFrameCallback`**? | detección directa | si la sincronía de la intervención puede ser exacta |
| 9 | ¿Cuántos `<video>` **existen** vs. cuántos **reproducen** a la vez? | crear N elementos con `preload`, luego reproducirlos de a uno hasta que se rompa | el techo real de «3 videos»; son sesiones de decodificación, no DOM |
| 10 | ¿Un **canvas encima** del video le baja el fps? | medir con la pregunta 7, con y sin canvas encima, opaco y transparente | **intervención encima o al lado** — bifurcación de layout |
| 11 | ¿Tamaño real del panel vs. superficie del WebView? | `screen`, `devicePixelRatio`, `innerWidth` | cuánto píxel se está regalando (en la caja: 3840×2160 sobre panel de 1280×720) |
| 12 | ¿Reproduce **HLS/DASH nativo**? | `canPlayType` de los tipos de manifiesto | si existe el camino D en ese aparato |

**Criterio de cierre de H-4:** la tabla completa para la TV box **y** para dos o
tres aparatos más del operador (celular, Smart TV, escritorio), volcada a §5.

## 3. El banco de reproducción (H-5)

Donde la sonda dice *si se puede*, el banco dice *cuánto cuesta*. Crece desde
`frontend/tv-video-test.html`, que ya existe y ya mide fps de decodificación,
cuadros caídos, atascos y deriva.

**Instrumento principal:** `getVideoPlaybackQuality()` →
`totalVideoFrames` / `droppedVideoFrames`. Es el decodificador reportando su
propio trabajo. Reemplaza al «se ve bien / se ve mal» por un número — es el
equivalente de `tools/bench_ref.py`, pero del lado de la reproducción.

**Métricas por variante:**

| Métrica | Qué revela |
|---|---|
| cuadros caídos / totales | el veredicto duro de fluidez |
| tiempo hasta el primer cuadro | costo de arranque y de configuración del decodificador |
| deriva `currentTime` vs. reloj | si el aparato sostiene la cadencia |
| atascos (cuenta y duración) | picos de bitrate contra el buffer |
| comportamiento en bucle | costura al reiniciar |
| lo mismo **con la capa de intervención activa** | el costo real de las dos capas |

**Regla de firma:** todo lo que requiere pantalla **lo firma el operador**. El
banco produce números; el veredicto de imagen es suyo y se transcribe textual.

## 4. Matriz de emisión (H-6)

Del **mismo máster**, N variantes reproducibles y con hash, para medir con §3.
Los ejes:

| Eje | Valores a barrer | Hipótesis |
|---|---|---|
| **códec** | H.264 Baseline, H.264 Main, VP9 (+ AV1 donde exista) | VP9 comprime mucho mejor y puede ser el camino nativo de la caja |
| **fps** | fijo 15 vs. **variable por segmento** derivado del máster | el ahorro más grande y más barato: menos cuadros = menos trabajo, lineal |
| **bitrate / calidad** | escalones sobre el look del máster | dónde está el codo entre bytes y fluidez |
| **estructura** | tamaño de GOP, cuadros clave en los cortes, una sola referencia, sin cuadros B | menos memoria de decodificación (el recurso escaso de la caja) y menos latencia |
| **zonas estáticas** | máster con fondo idéntico bit a bit vs. sin esa garantía | si el encoder emite «no cambió» y la decodificación se desploma |
| **paleta** | actual vs. paleta separada en **luma** (consciente del 4:2:0) | si el submuestreo de color deja de dañar los bordes duros |

**Advertencia que hay que tener presente al leer los resultados:** muchos trucos
clásicos para aliviar H.264 (entropía más simple, filtro de bloques apagado) solo
rinden si el decodificador es **por software**. En hardware esas etapas son
silicio y son casi gratis; ahí lo que cuesta es **ancho de banda de memoria,
cantidad de cuadros, tamaño del buffer de referencias y picos de bitrate**. Por
eso la pregunta 2 de la sonda (hardware o software) **bifurca toda la matriz**, y
se responde antes de barrer.

**Criterio de cierre de H-6:** tabla de variantes en el REGISTRO con la medición
del aparato por fila, y la receta de emisión elegida **por perfil de
dispositivo** —no una sola receta global—, con el veredicto del operador.

## 5. Registro de aparatos

Se llena con H-4 y H-5. **Los perfiles P0..P3 de
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md) §7 se asignan desde esta tabla**,
no por criterio de nadie.

| Aparato | WebView / navegador | H.264 | VP9 | VP9 hw | alfa WebM | MSE | `blob:` | IndexedDB | calidad de repr. | rVFC | videos simultáneos | canvas encima | panel vs. superficie | Perfil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TV box (la de DIAG-002/003) | | ✓ (medido: el producto mp4 *«reproduce muy bien»*) | | | | | | | | | | | 1280×720 panel / 3840×2160 superficie | |
| _(celular del operador)_ | | | | | | | | | | | | | | |
| _(Smart TV del operador)_ | | | | | | | | | | | | | | |
| _(escritorio)_ | | | | | | | | | | | | | | |

Lo único ya medido de la caja está en el REGISTRO (DIAG-002/003, 2026-09-01): el
player 100 % JS da 290 ms/cuadro contra 66,7; el WebGL dibuja pero **no
presenta**; y `producto.mp4` (1280×720 @15, 4.130.240 B) *«reproduce muy bien»*
por `<video>` con decodificador de hardware.

## 6. Reglas del método

1. **Se mide antes de normalizar.** Ninguna decisión de formato entra en la spec
   sin una fila que la sostenga.
2. **Determinismo:** las variantes se generan desde el máster con parámetros
   registrados y hash; una variante que no se puede regenerar no se mide.
3. **Un eje por vez** cuando se pueda; si no, se anota la confusión en la fila.
4. **Lo que requiere pantalla lo firma el operador**, textual.
5. **Nada se estima.** Si un dato no se midió, la celda queda vacía — no se
   completa con lo probable.
6. **El ciclo se repite:** medir → emitir → medir → normalizar → volver a medir.
   El formato se descubre, no se decreta.
