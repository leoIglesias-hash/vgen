# Diseño — intervención matricial local (INT-001)

Estado: propuesta de diseño, 2026-08-27. Sin implementación.
Documento requerido por `HOJA-DE-RUTA-TECNICA-V2.md` §12 antes de INT-002.

Fuentes de verdad que este documento respeta y no reemplaza:

| Tema | Documento |
|---|---|
| principios e invariantes | `PLAN-IMPLEMENTACION-OPTIMIZACION.md` |
| backlog, dependencias y gates | `HOJA-DE-RUTA-TECNICA-V2.md` |
| formato v1/v2 | `ASCL-format-spec.md` |
| estado canónico | `ESTADO-ACTUAL.md` |

## 1. Problema

Un video base pregrabado debe mostrar, en una zona declarada, valores que **no existen
al momento de codificar**: resultados de sorteo cargados en vivo. El caso de referencia es
un panel de 20 números de quiniela de dos dígitos.

La combinatoria del resultado completo es 100^20. Ese número es irrelevante: no se
predefine el resultado, se predefine el **alfabeto**. Con diez parches —los dígitos `0`
a `9`— y cuarenta posiciones declaradas se cubre el espacio completo.

La intervención ocurre sobre la misma matriz lógica y el mismo canvas. No se agrega una
capa DOM, un segundo canvas ni un segundo framebuffer.

## 2. Decisiones cerradas

| Decisión | Valor | Motivo |
|---|---|---|
| composición | índices de paleta escritos en `cells` | mantiene el overlay dentro de la matriz lógica; los gates de CRC existentes lo cubren sin categoría de test nueva |
| entradas de paleta reservadas | **10**, índices `246..255` | antialias horneado más colores de estado; cuesta 3,9% de la paleta |
| ubicación de la metadata | **sidecar** durante desarrollo, `ASCLVID3` al congelar | permite rediseñar el panel sin re-encodear el bundle |
| unidad de asset | glifo, no resultado | diez parches cubren toda la combinatoria |
| canal de datos | recurso estático diminuto por XHR | el servidor sigue sin calcular nada |

## 3. Invariantes

- **INV-1** — un canvas, una matriz lógica `cells`, un `putImageData`/`texSubImage2D`.
- **INV-2** — la memoria auxiliar es la suma de las áreas declaradas, nunca otro
  `cols * rows`.
- **INV-3** — ninguna celda del **video base** usa un índice `>= 246`. Es una propiedad
  verificable: toda celda con índice reservado es, por construcción, overlay.
- **INV-4** — los índices `246..255` denotan el mismo RGB en **todas** las épocas de
  paleta y en los cuatro modos (`global`, `block`, `adaptive`, `per-frame`).
- **INV-5** — el reader decodifica exactamente lo mismo con y sin overlay. La intervención
  ocurre después de `seek()` y antes de `draw()`; no modifica el decodificador.
- **INV-6** — sintaxis ES5.1. Sin `fetch`, `Promise`, `Worker`, `JSON` obligatorio ni
  API nueva del navegador.
- **INV-7** — un fallo del canal de datos nunca interrumpe la reproducción. Ante cualquier
  anomalía se conserva el último valor válido.

## 4. Reserva de paleta

### 4.1 Contrato

Los índices `246..255` quedan fuera del cuantizador. El encoder construye `pal_size - 10`
colores para el video y estampa las diez entradas reservadas al final, con valores RGB
fijos declarados por el operador.

Requiere `pal_size >= 32`: diez reservadas más un piso razonable para el video. Con
`pal_size` menor, el encoder rechaza la combinación con overlay.

### 4.2 Puntos del encoder que deben excluir el rango reservado

Este es el punto donde la reserva se rompe en silencio si se olvida un camino. Todos
estos ya existen y hoy tocarían las diez entradas:

| Función | Archivo | Acción requerida |
|---|---|---|
| `make_global_palette` | `encoder.py:286` | construir `pal_size - 10` y concatenar las reservadas |
| `_kmeans_rgb_palette` / `_kmeans_rgb_numpy` | `encoder.py:248,271` | idem; el `lexsort` no debe reordenar las reservadas |
| `build_perceptual_palette` | `perceptual_palette.py:472` | Lloyd solo sobre las no reservadas |
| `_repair_palette_duplicates` | `perceptual_palette.py:384` | nunca reemplazar una entrada reservada |
| `gamut_map_oklab` | `perceptual_palette.py:125` | no aplicar a reservadas; sus RGB son literales |
| `_align_to_previous` | `perceptual_palette.py:360` | la estabilidad temporal no las mueve |
| refit de Lloyd (Tier 2) | propuesto | excluir del `bincount`/reasignación |
| `quantize_palette_rgb` | `encoder.py:498` | el video base no puede elegir `>= 246` (INV-3) |

### 4.3 Asignación sugerida de las diez entradas

| Índice | Rol |
|---|---|
| 246 | fondo del panel |
| 247..250 | cuatro niveles de antialias entre fondo y texto |
| 251 | texto base |
| 252 | texto destacado (último número cargado) |
| 253..254 | colores de estado por sorteo o resaltado |
| 255 | **transparente**: conserva la celda base, no se pinta |

El valor `255` como transparencia binaria es lo que permite que un glifo no sea un
rectángulo opaco: las celdas de fondo del glifo pueden dejar pasar el video base.

## 5. Tabla de glifos

- `glyph_w`, `glyph_h` en celdas, uniformes para todos los glifos.
- `n_glyphs = 11`: dígitos `0..9` más un glifo vacío en la posición `10`.
- Cada glifo son `glyph_w * glyph_h` bytes; cada byte es un índice en `246..255`.
- Tamaño total = `n_glyphs * glyph_w * glyph_h`.

A modo de referencia, con una grilla de 768x432 y glifos de 8x12 celdas la tabla completa
son **1.056 bytes**. Con glifos de 16x24 son 4.224 bytes. En ambos casos es despreciable
frente al bundle.

### 5.1 Horneado

Los glifos se generan offline desde una fuente real: render a resolución alta, downsample
al tamaño en celdas y cuantización del antialias a los niveles `247..250`. Es el paso que
diferencia un dígito legible de un dígito duro a esa escala. El resultado es determinista
y se versiona junto con la metadata.

## 6. Tabla de slots y campos

### 6.1 Slot

Un slot es la posición de **un** glifo.

```text
slot_id      uint16   identificador estable
x, y         uint16   esquina superior izquierda, en celdas
start_frame  uint32   primer frame en que el slot está activo
end_frame    uint32   último frame activo (inclusive)
flags        uint8    bit0 visible
```

El tamaño no se declara por slot: todo slot ocupa `glyph_w x glyph_h`.

### 6.2 Campo

Un campo agrupa slots consecutivos en un valor numérico validable. Es lo que permite
verificar "veinte números entre 0 y 99" en lugar de "cuarenta dígitos sueltos".

```text
field_id     uint16
slot_ids[]   uint16[]  en orden de escritura, más significativo primero
min, max     uint32    rango numérico aceptado
pad          uint8     0 = sin relleno, 1 = ceros a la izquierda
```

Para el caso de referencia: 40 slots, 20 campos de 2 slots cada uno, `min=0`, `max=99`,
`pad=1`.

### 6.3 Restricciones validables

- todo slot cae íntegramente dentro de la grilla;
- ningún par de slots se solapa;
- `n_slots <= 1024`;
- `glyph_w * glyph_h <= 4096`;
- todo byte de la tabla de glifos está en `246..255`;
- todo `slot_id` referenciado por un campo existe y aparece en un solo campo;
- la suma de áreas activas no supera el **5% de la grilla** (presupuesto de RAM y de
  trabajo por frame; ver §10).

Una metadata que no cumple se rechaza entera. No hay carga parcial ni corrección
silenciosa.

## 7. Transporte de la metadata

### 7.1 Fase sidecar (desarrollo)

Recurso estático `clip.slots` publicado junto al `.asclv`, cacheable con el mismo criterio
que el video. Estructura binaria:

```text
magic        8 B    "ASCLSLOT"
version      1 B    1
reserved     1 B    0
pal_reserved 1 B    10
n_glyphs     1 B
glyph_w      2 B
glyph_h      2 B
n_slots      2 B
n_fields     2 B
reserved_rgb 30 B   los diez RGB de 246..255, para verificación cruzada
crc32        4 B    sobre el resto del archivo
glyph_table  n_glyphs * glyph_w * glyph_h
slot_table   n_slots * 13 B
field_table  variable
```

`reserved_rgb` permite que el player verifique que el sidecar corresponde a la paleta del
bundle: si los diez RGB no coinciden con los del `.ascl`, el overlay no se activa. Es la
defensa contra servir un sidecar viejo junto a un video nuevo.

### 7.2 Fase ASCLVID3 (congelado)

Envelope de 20 B con tres longitudes:

```text
magic       8 B   "ASCLVID3"
ascl_len    4 B
audio_len   4 B
meta_len    4 B
```

Se conserva la regla actual: `20 + ascl_len + audio_len + meta_len == filesize` exacto, sin
bytes sobrantes. La sección `meta` es el sidecar de §7.1 sin su magic ni su CRC propio,
cubierto por el CRC del ASCL interior.

Los readers actuales rechazan `ASCLVID3` por magic desconocido, de forma limpia y sin leer
basura. Es el comportamiento correcto: un player viejo no debe reproducir un clip cuyo
panel no puede pintar.

## 8. Canal de datos en vivo

### 8.1 Formato

Texto plano de longitud fija, sin `JSON`:

```text
<serial>|<dígitos>\n
```

`serial` son ocho dígitos decimales monotónicos (identificador de carga). `dígitos` son
exactamente `sum(len(slot_ids))` caracteres `0..9`. Para el caso de referencia, 40. El
recurso completo pesa unos 50 bytes.

Se elige texto de longitud fija sobre JSON deliberadamente: el parseo es `charCodeAt` en
un bucle acotado, no depende de `JSON.parse`, y la validación de longitud es previa a
cualquier interpretación.

### 8.2 Consulta

XHR `GET` cada 15-30 s sobre la misma URL con token anti-caché, servido con
`Cache-Control: no-store`. Sin `fetch`, sin Promise, sin Worker, sin Service Worker.
Backoff exponencial acotado ante error de red, con techo de 5 minutos.

### 8.3 Validación

En orden, antes de tocar un solo píxel:

1. `Content-Length` o `responseText.length` dentro del tamaño exacto esperado;
2. todos los caracteres del bloque de dígitos en el rango `0x30..0x39`;
3. `serial` numérico y **estrictamente mayor** al último aceptado;
4. cada campo, reconstruido, dentro de `[min, max]`;
5. índice de glifo calculado como `charCodeAt(i) - 48`, con clamp a `0..9`.

Ante cualquier fallo se conserva el último estado válido y se registra el motivo. El dato
de red **nunca** elige una URL, nunca indexa fuera de la tabla de once glifos, nunca se
evalúa y nunca se inserta en el DOM.

El `serial` estrictamente creciente impide que una caché intermedia reintroduzca un
resultado viejo.

## 9. Runtime

### 9.1 Estado

```text
overlay.active        bool
overlay.rects         geometría efectivamente pintada en el frame anterior
overlay.restoreValid  bool   hay un rect pintado pendiente de restaurar
overlay.base          Uint8Array   suma de áreas activas
overlay.values        Uint8Array   índice de glifo por slot
```

### 9.2 Orden por frame

```text
1. si overlay.restoreValid -> escribir overlay.base sobre cells en overlay.rects
2. reader.seek(target)                      // puede decodificar varios frames
3. guardar cells de los rects activos en overlay.base; overlay.restoreValid = true
4. escribir los glifos correspondientes a overlay.values
5. marcar sucios: unión de overlay.rects anterior y actual
6. renderer.draw(...)
```

El paso 1 **antes** del paso 2 es lo que impide que una cadena DELTA se calcule sobre
píxeles contaminados. Es el punto crítico de todo el diseño.

### 9.3 Keyframes y seek

No hace falta un flag especial para keyframes. Como la restauración ocurre siempre antes
de cualquier decodificación y el guardado siempre después, un keyframe que reescribe la
matriz completa queda cubierto: lo restaurado se sobrescribe y lo guardado es la base
nueva.

`restoreValid` es falso únicamente en el primer frame y después de `clearSlot`.

Con el atajo a keyframe propuesto en el endurecimiento del reader v1, `seek()` puede
decodificar varios frames internamente. Por eso la restauración va **fuera** de `seek()`,
no dentro del bucle de decodificación.

### 9.4 Marcado de celdas sucias

Ambos readers necesitan una entrada simétrica:

```text
Reader.prototype.markRectDirty(x0, y0, w, h)
```

En `ReaderV1` marca bits del bitset de celdas. En `ReaderV2` marca celdas exactas y
promueve a tile cuando el rectángulo cubre un tile completo, respetando la disyunción
celda/tile existente.

Debe marcarse la **unión** del rect anterior y el actual: las celdas restauradas también
cambiaron respecto de lo presentado.

### 9.5 API ES5

```text
ASCILINEOverlay.attach(reader, meta)     -> instancia o null si meta inválida
overlay.setField(fieldId, value)          // valor numérico, validado contra min/max
overlay.setValues(digitString)            // carga completa validada
overlay.clearField(fieldId)               // pinta el glifo vacío
overlay.clear()                           // restaura y desactiva
overlay.beforeSeek(); overlay.afterSeek() // pasos 1 y 3-5
overlay.detach()
```

Sin callbacks, sin closures retenidas por frame, sin allocaciones en el camino caliente:
`overlay.base` y `overlay.values` se reservan una vez en `attach`.

## 10. Costo

Con 40 slots de 8x12 celdas sobre una grilla de 768x432 (331.776 celdas):

| Concepto | Por frame |
|---|---:|
| celdas del overlay | 3.840 |
| restaurar | 3.840 escrituras en `cells` |
| guardar | 3.840 lecturas + escrituras en `overlay.base` |
| pintar | 3.840 escrituras en `cells` |
| conversión RGBA extra | 3.840 celdas |
| RAM auxiliar | 3.840 B + 40 B |

Las 3.840 celdas del overlay son **1,16%** de la grilla. El presupuesto del 5% de §6.3 deja
margen de más de cuatro veces el caso de referencia.

### 10.1 Optimización del video base

Si la zona del panel es plana en el video fuente, esos tiles se resuelven como `SOLID` o
`SKIP_RUN` en v2 y casi no pesan. Conviene diseñar el video base con el panel ya liso: se
gana en bytes y el rect base se vuelve predecible. Los elementos fijos del panel —rótulos
`1` a `20`, título, bordes— se hornean en el video base y no son overlay.

## 11. Interacción con las optimizaciones propuestas

| Optimización | Efecto | Acción |
|---|---|---|
| Zopfli en lugar de `zlib.compress(9)` | ninguno | — |
| búsqueda de `tile_size` | ninguno | el marcado de tiles ya es genérico |
| keyframes en cortes de escena | ninguno | — |
| **trellis / near-lossless** | **conflicto** | excluir los rects de slot; el base bajo el panel no puede derivar |
| **dither `auto`** | **conflicto** | excluir los rects de slot vía el mecanismo `protected` existente |
| refit de paleta / Lloyd en uint8 | **conflicto** | excluir índices `246..255` (§4.2) |
| estabilidad temporal de paleta | **conflicto** | excluir índices `246..255` |
| atajo a keyframe en reader v1 | favorable | la restauración vive fuera de `seek()` (§9.3) |
| rollback transaccional de `seek` | favorable | ante excepción, el overlay no quedó escrito |
| single-pass en `_walkRegional` | ninguno | — |

El mecanismo de exclusión ya existe: `dither.py` maneja regiones protegidas mediante
`edge_mask`, `selective_tile_mask` y `selected &= ~protected`. Los rects de slot se suman
a esa máscara.

## 12. Gates

### INT-001 (diseño)

- metadata inválida rechazada entera, sin carga parcial;
- `reserved_rgb` del sidecar coincide con la paleta del bundle o el overlay no se activa;
- toda restricción de §6.3 con un fixture que la viola.

### INT-002 (runtime)

- un canvas y una matriz lógica;
- CRC de `cells` con overlay idéntico en Canvas2D y WebGL1;
- restauración exacta al hacer `clear()`, `seek()` hacia atrás y al reiniciar el loop:
  `cells` byte-idéntico a la reproducción sin overlay;
- costo p95 de la intervención por debajo del 10% del presupuesto de frame;
- RAM auxiliar acotada por las áreas declaradas, medida, no supuesta;
- un `field_id` o un dígito inválido no escribe fuera de su slot;
- la reproducción continúa intacta con el canal de datos caído, con datos corruptos y con
  datos repetidos;
- ninguna asignación de buffer proporcional al frame durante el loop estable.

## 13. Pruebas a agregar

Python:

- reserva de paleta preservada byte a byte a través de las cuatro estrategias y de todas
  las épocas de un clip adaptativo;
- INV-3: ninguna celda del video base con índice `>= 246`;
- dither y trellis no tocan celdas dentro de un rect de slot;
- validación de sidecar: cada restricción de §6.3 con su fixture negativo;
- horneado de glifos determinista y reproducible.

JavaScript:

- restauración exacta: reproducir N frames con y sin overlay y comparar `cells`;
- seek hacia atrás, loop y salto a keyframe con overlay activo;
- unión de rects sucios cubre restauración y pintado;
- validación del canal: longitud incorrecta, caracteres no numéricos, serial repetido,
  serial retrocedido, campo fuera de rango, respuesta vacía, respuesta gigante;
- el gate de sintaxis ES5 alcanza los archivos nuevos.

Referencia cruzada:

- el decoder Python reproduce la matriz con overlay dada la misma metadata y la misma
  cadena de datos, byte-idéntica a la del reader JavaScript.

## 14. Fuera de alcance

- rectángulos con solapamiento;
- glifos de tamaño variable dentro de un mismo clip;
- overlay en modos `ascii-*`; esta revisión es `mode pixel` únicamente;
- animación del overlay entre frames; el valor cambia por evento, no por cuadro;
- cualquier detección visual, rotación o escalado geométrico en runtime;
- capa DOM, segundo canvas o segundo framebuffer.

## 15. Orden de ejecución propuesto

1. reserva de paleta en el encoder y sus exclusiones (§4.2), con sus tests;
2. horneado de glifos y generador de sidecar;
3. validador de sidecar en Python y en JavaScript, con fixtures negativos;
4. runtime del overlay y `markRectDirty` en ambos readers;
5. canal de datos con su validación y su backoff;
6. medición en Smart TV real dentro de VAL-001, con y sin overlay;
7. congelar el diseño y migrar el sidecar a `ASCLVID3`.

Los pasos 1 y 2 deben completarse **antes** de implementar el trellis y el refit de paleta:
esas optimizaciones necesitan conocer el rango reservado y los rects protegidos, y
reescribirlas después cuesta más que ordenarlas ahora.
