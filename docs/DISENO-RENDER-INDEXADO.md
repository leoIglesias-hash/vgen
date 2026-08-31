# Diseño: render indexado y reconstrucción (F9)

Objetivo: **bajar el trabajo por frame del TV sin tocar un solo byte del archivo**, y
habilitar que una grilla de 1280 se estire a un panel de 1920 sin escalones.

Nada de lo que está acá cambia el formato ni exige re-encodear. Todo se prueba con el
clip que ya está en producción (`dcd6afb6…1632a`).

Precondición conceptual (regla 6 del mapa, invariante 3): **Canvas2D es el piso y
WebGL1 solo acelera.** Ninguna tarea de este documento agrega una función que Canvas2D
no pueda cumplir; las dos rutas siguen produciendo la misma imagen en modo `nearest`.

---

## 1. El problema, en números

El trabajo por frame es proporcional a las **celdas**, no a los píxeles de pantalla. Hoy
la expansión índice→RGB la hace la CPU en
[`ReaderV2.fillRGBARows`](../frontend/reader-v2.js) y recién después se sube el RGBA:

```js
for (i = start; i < end; i++) {
  pi = this.cells[i] * 3; c = i * 4;
  out[c] = this.palette[pi]; out[c+1] = this.palette[pi+1];
  out[c+2] = this.palette[pi+2]; out[c+3] = 255;
}
```

Son ~7 accesos a arrays y 2 multiplicaciones **por celda**. Con la escala del producto:

| Grilla | Celdas | Accesos por frame completo | RGBA a subir |
|---|---|---|---|
| 768×432 | 331.776 | ~2,3 M | 1,3 MB |
| 1280×720 | 921.600 | ~6,5 M | 3,7 MB |
| **1920×1080** | **2.073.600** | **~14,5 M** | **8,3 MB** |

Un keyframe a 1920 hace ese trabajo **entero** (`_markFull` → `fillRGBA` completo →
`putImageData`/`texImage2D` completo). El presupuesto a 15 fps es 66,7 ms. En el
1920@10 medido en S-7 hay 28 keyframes en 154 frames: uno cada ~5,5 frames. Esa es la
hipótesis principal de por qué el operador vio el 1920 «un poco trabado» pese a
aprobar su imagen.

---

## 2. W-16 — Medir primero (precondición de todo lo demás)

Regla 5/6 del proyecto: una mejora sin medición registrada no existe. Ninguna tarea de
F9 se puede cerrar sin este banco.

**Dos piezas:**

1. **`tools/bench_render.js`** — banco offline en Node, sin canvas, del mismo estilo que
   `tools/bench_inflate.js` y `tools/bench_reader_v2.js`. Mide la etapa de conversión
   índice→RGBA, que es CPU pura sobre typed arrays y no necesita navegador. Corpus
   determinista: grillas 768/1280/1920, tres perfiles (keyframe completo, delta disperso
   ~5 % de celdas, delta de tiles densos), paletas de 256 entradas. Reporta ms y MB/s por
   variante (camino actual vs LUT de W-17).
2. **`frontend/diagnostic-player.html`** (esto **es la tarea F8-1**, que se adelanta acá
   porque F9 la necesita) — ES5, separado de `tv-player.html`, con contadores por etapa:
   inflate, `_walkRegional`, conversión RGBA, blit/upload, y total por frame. Publica
   p50/p95, drops y frames tarde. Sin dependencias, sin `JSON`, sin `Map`.

**Cierre:** el banco corre en `tests/run_all.py` (regla 7) y publica su tabla en el CI;
el diagnostic abre en el TV y muestra números reales de las tres grillas.

**CERRADA el 2026-08-31** (`f1ccfa3`, CI verde). Además del banco y del diagnostic quedó
el workflow manual `bench-render` (corrida larga y comparación HEAD vs `baseline`), que
es el vehículo con el que se registran W-17 en adelante.

Tres decisiones que conviene no re-discutir:

1. **El CI publica la tabla, no la juzga.** El runner comparte CPU: una aserción de
   velocidad sería un test intermitente. El criterio duro del banco es la **paridad**
   byte a byte entre el camino vigente, el prototipo LUT y la reconstrucción completa.
2. **La instrumentación vive entera en `diagnostic-player.html`**, envolviendo métodos de
   la instancia del reader: ningún archivo de producción se modifica para medir, así que
   lo medido es exactamente lo que corre en el TV. (`fillRGBA` delega en `fillRGBARows`:
   sin guarda de reentrada la conversión se contaba dos veces y el blit quedaba en cero.)
3. **El clip sintético del banco es v2 a propósito:** la etapa medida es idéntica en v2 y
   v3; el SPARSE diferencial de v3 cambia el walk, no la conversión.

Medición inicial (CI, Node 20, 4 repeticiones; tabla completa en el REGISTRO,
Instancia 032): la conversión de un **keyframe a 1920 cuesta 11,0 ms** en el runner —y un
TV viejo está un orden de magnitud por debajo de esa CPU—, y el prototipo de W-17 rinde
**1,3×–3,3×** según el perfil, ≈2,2× en los dos casos que dominan (keyframe y tiles
densos). El perfil disperso es el que menos gana, y no por la LUT: `fillRGBAChanged`
recorre todo `dirtyCellBits` aunque cambie el 5 % de las celdas — es el hueco de W-21.

---

## 3. W-17 — LUT de paleta en `Uint32`

Reemplaza 3 lecturas + 4 escrituras de byte por **1 lectura de LUT + 1 escritura de
palabra**.

**Construcción** (una vez por paleta, no por frame): `pal32 = new Uint32Array(256)`,
donde cada entrada empaqueta RGBA en el orden de bytes de la máquina. La endianness se
detecta **una sola vez** escribiendo un valor conocido en un `Uint32Array` y leyéndolo
por su vista de bytes; no se asume little-endian.

**Escritura**: una vista `Uint32Array` sobre el buffer del destino. Para Canvas2D el
destino es `imgData.data`, cuyo `buffer` empieza en offset 0 y tiene longitud múltiplo
de 4; para WebGL es el `Uint8Array` propio. Si por cualquier motivo la vista no se puede
crear, **se conserva el camino de bytes actual** — el fallback no es opcional, es parte
del contrato con WebViews viejos.

**Restricciones ES5 que aplican** (gate `tests/test_frontend_compatibility.js`):
`Uint32Array` está permitido; `Uint8ClampedArray` **no se puede nombrar** en el código,
pero no hace falta nombrarlo (se accede vía `imgData.data.buffer`); `.fill()` de
TypedArray está prohibido, así que la LUT se llena con un `for`.

**Cierre:** salida **byte-idéntica** a la actual sobre el corpus del banco (test de
paridad, no inspección visual) y mejora medida en `bench_render.js`. Beneficia a
Canvas2D y a WebGL por igual, y es la que hace barata la transparencia de F11-2 (el
alpha sale de la LUT, sin costo extra por celda).

---

## 4. W-18 — Textura de índices y paleta en el shader (la apuesta principal)

Hoy el fragment shader es un passthrough (`gl_FragColor = texture2D(u_tex, v_uv)`) y la
GPU no sabe que existe una paleta. La conversión la paga la CPU y sube 4 bytes por celda.

**Cambio:** subir `reader.cells` **tal cual** como textura de índices de 1 byte y hacer
el lookup en el shader contra una textura de paleta de 256×1.

| | Hoy | Con W-18 |
|---|---|---|
| Conversión en CPU | `fillRGBA*` sobre todas las celdas sucias | **ninguna** |
| Bytes subidos por frame completo (1920) | 8,3 MB | **2,07 MB** |
| Buffer `rgba` residente | 8,3 MB | **no se reserva** |
| Subida parcial | `texSubImage2D` de la banda RGBA | `texSubImage2D` de la banda de `cells` (subarray, sin copia) |

**Detalles que deciden si funciona o no** (los tres son causa típica de fallo silencioso):

1. **`gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)`** antes de subir la textura de índices. El
   default es 4 y una textura de 1 byte por texel con ancho no múltiplo de 4 se sube
   corrida. 1280 y 1920 son múltiplos de 4, pero 768/640/otras grillas del operador
   pueden no serlo, y la directiva es que el front acepte cualquier resolución.
2. **Centro de texel al indexar la paleta.** El índice llega normalizado a [0,1]; la
   coordenada correcta es `idx * (255/256) + (0.5/256)`. Sin la corrección de medio
   texel, los colores salen corridos una entrada.
3. **Precisión.** `mediump` resuelve ~2⁻¹⁰ y los 256 niveles necesitan pasos de 1/255:
   entra, pero sin margen. El fragmento declara `highp` cuando está disponible
   (`#ifdef GL_FRAGMENT_PRECISION_HIGH`) y cae a `mediump` si no.

**Formato de textura:** `LUMINANCE`/`UNSIGNED_BYTE` para los índices (se lee `.r`),
`RGBA`/`UNSIGNED_BYTE` 256×1 para la paleta, ambas `NEAREST` + `CLAMP_TO_EDGE` (NPOT en
WebGL1 no admite mipmaps ni `REPEAT`). La paleta se re-sube solo cuando cambia
(keyframe con paleta nueva), 1 KB por vez.

**Fallback obligatorio:** si el shader no compila, si `LUMINANCE` no se acepta o si la
sonda de `getError` marca fallo en la primera subida, el renderer **conserva el camino
RGBA actual completo** (que no se borra). Igual que hoy, cualquier fallo de WebGL cae a
Canvas2D sin romper la reproducción.

**Expectativa honesta:** los TVs más viejos —los que más necesitan la aceleración— son
también los más propensos a caer al fallback. Por eso el valor esperado de F9 no
descansa solo en W-18: **W-17 y W-20 mejoran el piso Canvas2D en todos los
dispositivos**, y W-18 acelera además donde la GPU lo permite. La frase operativa es
«W-18 acelera donde puede; W-17 acelera en todos».

**Cierre:** paridad de píxeles con Canvas2D en modo `nearest` (test automatizado sobre
un frame sintético leído con `readPixels`), más la medición del banco y del diagnostic.
La imagen no cambia: esto acelera, no agrega función.

---

## 5. W-19 — Reconstrucción: cómo se estira 1280 a un panel de 1920

**Contexto del operador (2026-08-31):** el destino real son televisores de 1920, así que
**toda grilla se va a estirar sí o sí**. La grilla y los fps son elegibles por video y
nunca fijos (regla 9); lo que este punto define es que la *calidad del estirado* deje de
ser un accidente del compositor.

Hoy el escalado lo hace el navegador sobre el elemento canvas, con
`image-rendering: pixelated` (default `nearest`) y factor fraccionario: 1280→1920 es
×1,5, o sea **una de cada dos columnas duplicada y la otra no**. Sobre siluetas curvas y
degradés eso agrega escalones que no están en el archivo.

**Dos modos, explícitos:**

- **`nearest`** — 1 tap. Idéntico a hoy, bit a bit. Sigue siendo el default hasta que el
  operador decida lo contrario mirando el TV.
- **`soft`** — **4 taps NEAREST sobre los índices, 4 lookups de paleta, mezcla bilineal
  de los RGB resultantes.** El orden importa y no es negociable: interpolar índices
  produce colores arbitrarios (el índice 100 entre el 99 y el 101 no tiene relación de
  color con ellos). Por eso `LINEAR` sobre la textura de índices **está prohibido**, y
  por eso W-18 y W-19 se implementan juntas: la primera rompe el modo `soft` actual si
  la segunda no la acompaña.

**Asimetría declarada:** el modo `soft` ya difiere hoy entre renderers (WebGL usa
`LINEAR` sobre RGBA, Canvas2D delega en `image-rendering: auto` del compositor). Con
W-19 el shader lo hace correctamente y Canvas2D conserva su camino. Ambos suavizan; la
calidad no es idéntica. Esto se documenta como diferencia conocida, no se descubre en el
TV.

**Herramienta de comparación, no de producto:** `fitCanvas` gana un modo de **escalado
entero** (×1, ×2 con letterbox) accesible por query string. No es candidato a producto
—desperdicia panel— pero es la única forma de ver el aporte del filtro aislado del
remuestreo fraccionario.

**Cierre:** el operador compara en el TV, sobre el mismo video, tres presentaciones:
1280 `nearest` (hoy), 1280 `soft` con 4 taps, y 1920 nativo `nearest`. La pregunta que
esto responde —y que hoy no se puede responder— es si el 1920 vale su costo o si un 1280
bien reconstruido lo iguala por menos de la mitad de trabajo. **La respuesta se decide
por video, nunca de una vez para siempre.**

---

## 6. W-20 — Cadencia de presentación y pre-decode

Dos problemas distintos que se manifiestan igual («se traba»).

**(a) Judder.** `loop()` muestra el frame en el primer rAF donde
`floor(audio.currentTime * fps)` cambia. En TVs viejos `audio.currentTime` avanza a
saltos gruesos, así que a 10 fps sobre un panel de 60 Hz los frames caen en 5/7/6/6
refrescos en vez de 6/6/6/6. Una cadencia irregular se percibe peor que un fps bajo
constante — y el 1920@10 se descartó exactamente por eso.

Solución: acumulador de fase que ancle la presentación a la cadencia del display, con
corrección **lenta** contra el audio (el audio sigue siendo el reloj maestro; lo que
cambia es que deja de decidir el instante exacto de cada cuadro).

**(b) Jank de keyframe.** El loop se re-arma a 60 Hz para un video de 15 fps: **tres de
cada cuatro callbacks solo miran el reloj y vuelven a agendar**. Ese tiempo está libre y
hoy se tira. Con la tabla de offsets el player sabe dónde está el próximo keyframe.

Solución: decodificar por adelantado, en el tiempo muerto, el próximo keyframe a un
**buffer alterno de `cells`**. Es un buffer fijo reservado al abrir el clip, no uno
nuevo por cuadro: **no viola el invariante 7** («ningún buffer nuevo proporcional al
frame por cuadro»). Cuesta `cols*rows` bytes (2 MB a 1920), contra los 8,3 MB de RGBA
que W-18 libera.

**Alcance acotado a keyframes, a propósito:** un keyframe no depende del estado actual,
así que adelantarlo es seguro por construcción. Adelantar un *delta* exigiría una base
definida (snapshot de `cells` en un instante exacto) sin comprometer la
transaccionalidad del invariante 4, y el jank medible está en los keyframes. Si el
diagnostic mostrara que los deltas densos también pinchan el presupuesto, el pre-decode
de deltas se diseña aparte, con su propio análisis de base — no se improvisa dentro de
W-20.

**Cierre:** en el diagnostic, sobre 1920, drops < 0,1 % y p95 del par decode+render bajo
el presupuesto de frame. Es el gate `TV-02` de F8 aplicado antes de tiempo, a propósito.

---

## 7. W-21 — Dirty rect en X (menor, opcional dentro de F9)

La subida al canvas es una banda de **ancho completo**:
`putImageData(imgData, 0, 0, 0, y0, cols, y1-y0+1)` y
`texSubImage2D(..., 0, y0, texW, hh, ...)`. Dos celdas sucias, una en la fila 5 y otra en
la 715, cuestan un frame entero de subida. El dirty set ya tiene resolución de tile y de
celda; se colapsa a filas porque `x0/x1` **no se calculan en ningún lado**.

Agregarlos es barato y rinde en contenido con acción localizada (la ruleta girando, un
logo, el panel de números). Cierre: misma imagen, subida medida menor en un corpus con
cambios localizados.

---

## 8. Orden de ejecución y por qué

| Paso | Tarea | Depende de | Requiere re-encode |
|---|---|---|---|
| 1 | **W-16** medición | — | no (**cerrada** 2026-08-31, `f1ccfa3`) |
| 2 | **W-17** LUT Uint32 | W-16 | no |
| 3 | **W-18** textura de índices | W-16, W-17 | no |
| 4 | **W-19** reconstrucción | W-18 (acopladas) | no |
| 5 | **W-20** cadencia y pre-decode | W-16 | no |
| 6 | W-21 dirty en X | W-16 | no |

Todo F9 se valida contra el clip que ya está en producción. Es la única fase del
proyecto donde el ciclo de prueba dura minutos en vez de una hora de runner, y por eso
va primero.
