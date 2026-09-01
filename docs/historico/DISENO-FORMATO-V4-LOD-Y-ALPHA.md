# Diseño: formato v4 — resolución por tile y transparencia (F11)

Dos features que comparten una sola revisión de formato, por la misma razón que F6
agrupó todo en v3: **cada versión nueva es un decoder nuevo desplegado en el TV**, y ese
costo se paga una vez, no dos.

- **LOD por tile** — densidad de celda variable dentro del mismo frame. Ataca el
  objetivo «1920 estresando menos el front»: baja bytes **y** trabajo del decoder a la vez.
- **Transparencia (ALPHA-001)** — pedido del operador (2026-08-31): poder pasar solo el
  personaje (por ejemplo el huevo de Telekino recortado) y obtener un clip con el resto
  transparente, componible sobre cualquier fondo.

---

## 1. Por qué el LOD gana en las dos direcciones

Es raro en este proyecto: casi todas las optimizaciones cambian bytes por calidad o
bytes por CPU. Esta no.

La mayor parte de un frame publicitario es fondo suave que no necesita densidad de celda
completa; el detalle vive en bordes, texto y logos. Un tile codificado a la mitad de
resolución en ambos ejes:

- pesa **un cuarto** de las celdas (menos bytes, y además comprimen mejor);
- le impone al decoder **un cuarto** de las lecturas (una lectura sirve a 4 escrituras);
- no toca el detalle donde el ojo lo busca.

Con la mitad de los tiles en LOD, las celdas efectivas caen a ~62 %. Aplicado al 1920,
que a 15 fps se estima en ~44 MB extrapolando la tasa por celda medida en S-7, quedaría
cerca de **29 MB — dentro del 75 % del mp4 fuente**, con detalle completo donde importa.

Es la versión medible y acotada de la idea del operador de «más densidad donde hace
falta», que quedó fuera de S-4 por ser cambio de formato.

## 2. Dónde ocurre la pérdida (decisión de arquitectura)

**El horneado va en el encoder; el codec sigue siendo lossless.**

El contrato C2 del proyecto dice que el transcode v1→v2/v3 es **exacto**: misma matriz,
mismo RGB, verificado por round-trip. Un opcode con pérdida lo rompería y volvería
sospechosa toda la cadena de verificación.

La solución es que el encoder **hornee** el LOD en la matriz de índices: en los tiles
elegidos, las celdas quedan replicadas en bloques 2×2 idénticos, dentro de la etapa de
cuantización, **antes** del trellis. A partir de ahí todo el pipeline es exactamente el
de hoy y sigue siendo lossless respecto de esa matriz.

Consecuencia práctica muy útil: **el beneficio de bytes se puede medir sin tocar el
formato**. Una matriz con bloques 2×2 idénticos ya comprime mejor con los opcodes
actuales (PACK/PAL/SPARSE encuentran menos valores distintos por tile). Por eso el
carril se parte en dos tareas con riesgos muy distintos:

| Tarea | Qué hace | Cambia formato | Gana |
|---|---|---|---|
| **E-30** | hornear el LOD en la matriz | **no** | bytes y calidad-por-byte |
| **F11-1** | opcode que lo codifica compacto | **sí (v4)** | bytes extra + **trabajo del decoder** |

E-30 se puede probar, medir y aprobar visualmente **antes** de comprometerse a un
formato nuevo. Si el operador no ve el trade, F11-1 no se hace y no se desplegó nada.

## 3. E-30 — Horneado del LOD

**Archivos:** `backend/encoder.py` (etapa de cuantización), `backend/make_clip.py` (flag).

**Selección por tile**, con medidas numéricas ya disponibles en el proyecto (energía de
gradiente y varianza local, el mismo tipo de descriptor que usa
[`adaptive_palette.py`](../backend/adaptive_palette.py)): un tile es candidato si su
detalle de alta frecuencia está por debajo de un umbral. **Sin reconocimiento de
objetos ni segmentación** — compatible con el veto del proyecto.

**Exclusión obligatoria de rampas suaves (interacción con F10):** los tiles de bajo
detalle de alta frecuencia son *exactamente* donde vive el banding, y promediar 2×2 y
recuantizar dentro de un degradé puede reintroducir los escalones que F10 acaba de
sacar. La selección usa el **mapa de suavidad de E-25** para distinguir «plano» (LOD
sí) de «rampa suave» (LOD no): un tile solo es candidato si es plano de verdad, no si
es un degradé sin textura. Es la misma distinción que hace el guard de E-27, aplicada
acá como filtro de candidatos.

**Reducción:** promedio en Oklab del bloque 2×2 de la fuente, cuantizado a la paleta una
sola vez, y el índice resultante replicado en las 4 celdas. Promediar en Oklab y no en
sRGB evita el corrimiento de luminancia en los bordes de bloque.

**Estabilidad temporal:** la decisión LOD de un tile usa histéresis (como
`TemporalDitherState` en `dither.py`): un tile no puede alternar entre LOD y detalle
frame a frame, porque eso produciría pulsación visible y además rompería las cadenas
DELTA.

**Flag:** `--lod-tile <umbral>` (0 = apagado, default). Δbytes: sí.

**Cierre:** el default reproduce la salida actual **byte a byte**; con el flag activo,
bytes menores y decisión visual del operador sobre el preview. Fila de registro.

## 4. F11-1 — Opcode `LOD2`

**Archivo:** `backend/regional_codec_v2.py` + espejo en `frontend/reader-v2.js`.

Los opcodes actuales llegan hasta `0x07` (PAL8); el espacio `0x08..0xFF` está libre.

```
0x08 LOD2 ++ <sub-stream del tile a (tile/2)x(tile/2)>
```

El sub-stream reutiliza **los mismos candidatos** ya implementados (SOLID, SPARSE, MASK,
PACK1, PACK2, PAL4, PAL8) sobre la sub-grilla; no se inventa una codificación nueva. El
decoder decodifica la sub-grilla y escribe cada valor en sus 4 celdas.

**Restricciones que el decoder valida (regla: el decoder confía en cero campos):**

- `tile_size` par (los seis del sweep lo son: 4, 8, 12, 16, 24, 32);
- el tile debe estar **completo**: los tiles truncados del borde derecho o inferior,
  cuando la grilla no es múltiplo del tile, **no admiten LOD2** y se rechazan;
- el sub-stream debe consumir exactamente sus bytes (canonicidad, igual que hoy).

**Elección:** por longitud binaria real, igual que todos los demás candidatos. `LOD2`
solo se ofrece cuando la matriz **ya tiene** los bloques 2×2 idénticos (E-30 los
horneó), así que su adopción nunca pierde información: es un empaquetado exacto de lo
que ya está ahí.

## 5. F11-2 — Transparencia (ALPHA-001)

### 5.1 Cómo entra en el formato, sin romper nada

El header ASCL tiene el byte 19 = `cell_fmt`, que hoy vale 3 en modo PIXEL (bytes por
entrada de paleta). El reader actual hace `if (h.cellFmt !== 3) fail("cell_fmt
invalido")` y `palBytes = palCount * 3`.

Eso da la propiedad que queremos gratis: **un clip con paleta RGBA (`cell_fmt = 4`) es
rechazado limpiamente por todo decoder anterior**, en vez de decodificarse como basura.
Combinado con `version = 4`, el rechazo es doble y explícito.

```
cell_fmt = 3  ->  paleta RGB   (todo lo existente, sin cambios)
cell_fmt = 4  ->  paleta RGBA  (solo version >= 4)
```

El reader nuevo calcula `palBytes = palCount * cellFmt` y acepta `cellFmt` 4 únicamente
con versión ≥ 4. El resto del formato —tags, opcodes, predictores, tabla de offsets,
CRC— **no cambia**: un índice sigue siendo un byte por celda.

### 5.2 Alpha cuantizado, no binario

Un alpha binario (transparente/opaco) daría bordes dentados en una silueta curva — el
mismo tipo de escalón que estamos combatiendo en el resto del plan. Como la paleta pasa
a ser RGBA, el alpha por entrada sale gratis:

- `--alpha-levels N` (default 4: 0, 85, 170, 255; `N = 2` da el binario).
- Los píxeles con alpha 0 van todos a **una única entrada transparente** con color fijo
  (negro) para que la salida sea determinista.
- Los píxeles de borde (alpha intermedio) se cuantizan contra entradas que llevan su
  nivel de alpha.
- El K-means corre **solo sobre los píxeles con alpha > 0** y sobre color **no
  premultiplicado**: un fondo transparente no debe arrastrar el color de la paleta.

El reparto del presupuesto de 256 entradas entre tramo opaco y entradas de borde es un
parámetro explícito, del mismo estilo que `--reserved` del overlay.

### 5.3 Lectura de la fuente

`iter_video_frames` usa `cv2.VideoCapture`, que **descarta el canal alpha**. Hace falta
un camino de lectura nuevo: ffmpeg a `rawvideo/rgba` (o secuencia PNG). Formatos fuente
razonables: WebM/VP9 con alpha, MOV ProRes 4444, secuencia PNG.

`--alpha` activa ese camino; sin el flag, todo el pipeline es el de hoy, bit a bit.

### 5.4 Decoder

- **Conversión:** con la LUT `Uint32` de W-17 el alpha **no cuesta nada**: ya viene
  empaquetado en la entrada de la LUT. Sin W-17 habría que escribir un byte más por
  celda. Es la razón por la que F11-2 va después de F9.
- **WebGL:** contexto con `alpha: true` (hoy pide `alpha: false`) **solo cuando el clip
  lo declara**, porque la composición con alpha tiene costo. Con la textura de paleta de
  W-18 el alpha ya viaja en el canal A de esa textura: el shader no cambia.
- **Canvas2D:** `putImageData` escribe el alpha directamente, sin trabajo extra.
- **Página:** el fondo del `stage` deja de ser negro fijo cuando el clip es
  transparente. Lo decide el header, nunca una config del player.

### 5.5 Interacción con la paleta reservada del overlay

La reserva de overlay ya define el índice 255 como «transparente, nunca se pinta»
([`overlay_palette.py`](../backend/overlay_palette.py)). Con paleta RGBA esa entrada pasa
a tener alpha 0 **de verdad**, lo cual unifica las dos nociones de transparencia en una
sola. La primera versión **prohíbe combinar `--alpha` con `--reserved`** (error explícito
al validar opciones) hasta que ese cruce tenga su propio test; no se resuelve por
inferencia.

### 5.6 Efecto lateral esperado sobre el peso

Un clip de personaje sobre fondo transparente debería pesar **mucho menos** que uno con
fondo: los tiles completamente transparentes son `SOLID` de un único índice, y las
cadenas de `SKIP_RUN` se vuelven larguísimas. Vale medirlo y anotarlo: es un caso de uso
donde el formato luce especialmente bien.

## 6. F11-3 — Decoder JS espejo y verificación cruzada

Igual que F6-3 hizo con v3:

- `frontend/reader-v2.js` acepta versión 4, `cellFmt` 4 y el opcode `LOD2`;
- `frontend/reader-factory.js` despacha;
- `backend/ascl_bundle.py` admite un `.ascl` v4 dentro del envelope (revisar la
  validación de versiones; el envelope `ASCLVID3` no necesita cambiar);
- `tests/test_v4_cross.js` verifica que Python y JS producen la **misma matriz y el
  mismo RGBA** sobre artefactos sintéticos con LOD y con alpha;
- fuzzing del opcode nuevo y de la paleta RGBA (todo campo nuevo entra al fuzzing).

## 7. F11-4 — Re-encode del producto y adopción

Barrido sobre el clip real (1280 y 1920), fila de registro por variante, previews al
operador y decisión visual. Si se adopta, el producto pasa a v4 y se publica con el
puntero CACHE-001, igual que el cierre de S-4.

## 8. Compatibilidad, en una línea

| Decoder | Clip v3 | Clip v4 (LOD) | Clip v4 (alpha) |
|---|---|---|---|
| Anterior a F11 | reproduce | rechaza por versión | rechaza por versión **y** por `cell_fmt` |
| Posterior a F11 | reproduce | reproduce | reproduce |

Ningún clip se decodifica «a medias»: o se reproduce entero o se rechaza con excepción
tipada. Es el mismo contrato que gobierna el resto del formato.

## 9. Orden de ejecución

**E-30** (horneado, sin formato, medible y aprobable solo) → **E-31** (análisis de
candidatos de solo-paleta, sin formato — ver §11) → **F11-1** (opcode) → **F11-5**
(permiso de paleta en delta, **solo si E-31 lo justifica**) → **F11-2** (alpha) →
**F11-3** (espejo JS y cross-tests) → **F11-4** (barrido, previews, adopción).

F11 completo depende de F9 cerrada: la LUT `Uint32` (W-17) es lo que hace que el alpha
sea gratis, y la textura de paleta (W-18) es lo que lo hace gratis también en WebGL.

## 10. Idea anotada para probar en v4, sin tarea asignada: paletas por región

Idea del operador (2026-08-31), a evaluar **cuando toque hacer v4** y solo si se
demuestra el problema que resuelve (ver el gate al final).

**Qué es.** Mantener el índice de 1 byte por celda, pero permitir **N paletas de 256**
en el mismo frame, con un **selector de paleta por tile**: cada tile de la grilla lleva
1 byte que dice contra qué paleta se resuelven sus índices. Es la versión espacial del
modo `block` que ya existe en versión temporal. Multiplica los colores simultáneos del
frame **solo donde hace falta**, sin tocar el peso del plano de índices ni un solo
opcode — que es exactamente el costo que hace inviable pasar la paleta a 512.

**El punto clave del ahorro: la región rica es dueña exclusiva de sus tiles.** Los
tiles se **particionan** entre los grupos de paleta, nunca se superponen. Cuando una
zona rica en colores se separa con su propia paleta, el grupo base **no codifica nada
debajo de ella**: ahí queda un hueco, no una segunda versión de esas celdas. El ahorro
corre en las dos direcciones — el grupo base no gasta bytes en describir esa región, y
sus 256 entradas de paleta tampoco se gastan en los colores de la zona rica, quedando
enteras para el resto de la imagen. No hay capas ni doble decode: una sola matriz, un
solo canvas, cada celda se resuelve una única vez (invariante 2 intacto).

**Por qué el TV casi no se entera.** En Canvas2D es elegir qué LUT de W-17 usar por
tramo de tile (una decisión por tile, no por celda). En WebGL, la textura de paleta de
W-18 pasa de 256×1 a 256×N y una mini-textura de selectores (una celda por tile, del
orden de KB) le dice al shader qué fila mirar: un lookup extra por píxel. El selector
pesa ~KB por keyframe, contra los MB que costaría cualquier índice más ancho.

**Costos conocidos.** (a) Es cambio de formato: el frame carga N paletas + el mapa de
selectores — por eso viaja en v4, con el mismo despliegue de decoder que ya se paga.
(b) Si un tile cambia de paleta entre frames, sus índices cambian de significado y hay
que re-emitirlo entero: la asignación necesita histéresis temporal, el mismo mecanismo
de `TemporalDitherState` que ya planea usar E-30. (c) El encoder se encarece (asignar
tiles a grupos es clustering por similitud de color, **numérico, sin segmentación ni
reconocimiento de objetos** — compatible con el veto del proyecto); ese costo se paga
offline, como todo.

**Gate para promoverla a tarea.** Solo si E-25 (`--gradient-boost`) muestra que algún
frame real **satura** las 256 entradas (error de cuantización alto con la paleta
agotada). Lo medido hasta hoy atribuye el escalonado a trellis espacial (F10) y
estirado fraccionario (W-19), no a falta de colores; si esas dos vías lo resuelven,
esta idea queda anotada y no se ejecuta.

## 11. Carril anotado para v4: frames de solo-paleta (E-31 → F11-5)

Fundidos, flashes y cambios globales de luz son hoy el **peor caso simultáneo en bytes
y en trabajo del front**: cuando toda la imagen se oscurece un poco, todas las celdas
cambian de color, así que o el delta toca todo, o el detector de cortes dispara y cada
frame de la transición sale como keyframe (los 28 keyframes en 154 frames del 1920
medido en S-7 son sospechosos de esto — verificable en E-31). A 1920 eso es la subida
completa frame tras frame, justo donde más se notan los drops.

Pero un fundido no cambia la *estructura* de la imagen: cambia la **paleta**. Los
índices podrían quedar idénticos y transformarse solo las 256 entradas.

**Mecanismo:** el encoder detecta cuando el frame N ≈ una transformada global en Oklab
del frame N−1 (ajuste de una transformada escalar/afín + residuo — dos pasadas
numéricas, sin IA, compatible con el veto). Si el residuo pasa, emite un frame de
**solo-paleta**: celdas todas SKIP (unos pocos bytes) + la paleta transformada
re-emitida (768 B). Entra como un candidato más en la escalera de costos: gana solo
cuando su error y su longitud real lo justifican, como todo lo demás.

Por frame de fundido a 1920: hoy cientos de KB y 2,07 M de escrituras + subida
completa; con esto **~800 B** y un rebuild de la LUT de 256 entradas (W-17) o la
re-subida de la textura de paleta de 1 KB (W-18). Es la aplicación más pura de
«encoder caro, decoder trivial», y mejora la fluidez percibida exactamente en los
tramos donde hoy se acumulan los drops.

**Por qué necesita v4:** el formato lo prohíbe explícitamente — «los tags delta no
pueden emitir paleta» (validado en [`reader-v2.js`](../frontend/reader-v2.js), regla
heredada de v1 §Paleta). Levantar esa prohibición de forma acotada (un permiso
gateado por `version >= 4`, o un tag nuevo `PALETTE_ONLY`) es cambio de formato, y
viaja gratis en la misma revisión v4 que ya se paga por LOD y alpha.

**Des-riesgo antes de tocar el codec, mismo patrón que E-30:**

| Tarea | Qué hace | Cambia formato | Cierre |
|---|---|---|---|
| **E-31** | análisis offline: contar los frames del clip real que son candidatos (residuo de transformada bajo umbral) y cuántos bytes cuestan hoy. Δbytes: no (solo reporta) | **no** | tabla de candidatos + techo de ahorro en bytes y en subidas evitadas; fila de registro |
| **F11-5** | permiso de paleta en frame delta (o tag `PALETTE_ONLY`), gateado por versión ≥ 4; espejo JS + fuzzing en F11-3 | **sí (v4)** | round-trip exacto; solo se ejecuta si E-31 muestra techo real y el operador aprueba |

Si E-31 dice que el clip real casi no tiene candidatos, F11-5 no se hace y v4 sale sin
este permiso: la canonicidad no se relaja «por si acaso».
