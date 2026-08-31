# Diseño: pérdida adaptativa por suavidad (F10)

Objetivo: **dejar de repartir la pérdida en partes iguales**. Hoy `--near-lossless 8`
aplica el mismo presupuesto de distorsión a toda la imagen; el ojo, en cambio, detecta
banding **solo en zonas suaves**, y los bytes se ahorran sobre todo en zonas texturadas.
Estamos pagando el precio justo donde más se ve y cobrando poco.

Este documento es el carril de calidad que ataca el degradé del huevo de Telekino sin
resignar el ahorro que el operador ya adoptó.

---

## 1. Qué es realmente `--near-lossless 8`

No es el near-lossless de WebP (que reduce bits en zonas planas). En este proyecto es un
alias de dos presupuestos de trellis ([`resolve_near_lossless`](../backend/trellis.py)):

```python
--near-lossless 8  ==  --trellis-temporal 8 --trellis-spatial 8
```

Y el **trellis espacial** es el que crea las bandas. Su regla
([`apply_spatial_trellis`](../backend/trellis.py)) busca tiles que cruzan los umbrales de
opcode `(3, 5, 17)` y fusiona el **valor menos frecuente** para bajar de PAL8 a PAL4,
de PAL4 a PACK2, etc. En una rampa de sombra el valor menos frecuente **es** el escalón
intermedio de la rampa: fusionarlo es, literalmente, fabricar la banda.

La medición está registrada: pasar de trellis temporal 4 a near-lossless 8 costó
**+18 % de `proxy_banding`** (0,001345 → 0,001587) y −0,49 dB, a cambio de −12 % de
bytes. El operador lo adoptó a conciencia («mínima pérdida, aceptable»). F10 no propone
revertirlo: propone **quedarse con el ahorro y devolver el banding**.

---

## 2. La pieza que ya existe y no se está usando

[`smooth_gradient_weights`](../backend/perceptual_palette.py) calcula, con primera y
segunda derivada en Oklab, un mapa por píxel que vale ~1 en zonas planas, hasta
`1+gradient_boost` en **rampas suaves**, y se apaga en bordes fuertes
(`edge_guard = 1/(1+(g/0.080)⁴)`) y en discontinuidades de curvatura
(`smooth_guard = 1/(1+(curv/0.012)²)`).

Es exactamente el detector de «esto es un degradé, no un borde» que hacen falta las tres
tareas de abajo. Hoy **solo se usa para pesar las muestras del K-means**, y su parámetro
está fijo en 3.0 dentro del código.

Es análisis numérico O(H·W): sin modelos, sin reconocimiento de contenido, sin IA.
Compatible con el veto del proyecto sobre visión artificial.

---

## 3. E-25 — Mapa de suavidad reutilizable + `--gradient-boost`

**Archivos:** `backend/perceptual_palette.py`, `backend/encoder.py`,
`backend/make_clip.py`.

**Acción:** (a) exponer `--gradient-boost` (default 3.0, el valor actual) — quedó anotado
como pendiente opcional desde E-14 y es el knob que decide cuántas entradas de paleta se
gastan en degradés en vez de en detalle de alta frecuencia; (b) calcular el mapa de
suavidad **una vez por frame** y dejarlo disponible para las etapas siguientes, en vez de
recalcularlo por consumidor.

**Cierre:** con `--gradient-boost 3.0` la salida es **byte-idéntica** a la actual
(regla 5). Δbytes: solo con otros valores.

---

## 4. E-26 — Presupuesto de trellis modulado por suavidad

**Archivo:** `backend/trellis.py`.

**Acción:** el presupuesto pasa de escalar a **mapa por celda**:

```
budget_local = budget * (1 - k * suavidad_normalizada)
```

En la sombra del huevo el presupuesto cae casi a cero (el trellis no toca esas celdas);
en el pasto texturado o en una zona de ruido sube por encima del valor global. `k` es un
flag nuevo (`--near-lossless-shape`, default 0 = comportamiento actual exacto).

Aplica a las tres etapas del trellis, que ya reciben máscaras por celda (el mecanismo de
`protected_mask` de E-18 demuestra que el camino existe y está testeado).

**Cierre:** a **igual o menor** cantidad de bytes que el producto vigente,
`proxy_banding` baja de forma medible. Fila de registro obligatoria. La comparación es
contra `dcd6afb6…1632a` (24.458.884 B, 35,02 dB, banding 0,001522).

---

## 5. E-27 — Guard anti-banding del trellis espacial

**Archivo:** `backend/trellis.py`.

**Acción:** no fusionar el valor menos frecuente cuando el tile es una rampa suave. Es
una condición de guarda sobre el mismo mapa: si la suavidad media del tile supera un
umbral, el tile se salta (queda exacto) aunque cruzara un umbral de opcode.

Justificación de por qué esto no cuesta casi nada: E-23 midió que el trellis espacial en
solitario aporta **−0,32 % de bytes**. Renunciar a él en la fracción de tiles que son
rampa suave es, a lo sumo, unas décimas de por mil — a cambio de eliminar la causa
directa del escalonado en degradés.

**Cierre:** `proxy_banding` baja, bytes prácticamente iguales (< 0,1 % de diferencia).

---

## 6. E-28 — Dither dirigido a mesetas, con presupuesto en bytes

**Archivos:** `backend/dither.py`, `backend/encoder.py`.

**Contexto obligatorio:** el operador **ya rechazó el dither** el 2026-08-29 («sin dither
se ve igual que con dither, nos quedamos con ese ahorrando»). Esa decisión se respeta y
esta tarea **no la revierte**: lo que se rechazó fue un dither global que costaba
**211.226 B (1,23 % del archivo)** y −0,17 dB sobre un 768 donde no había banding
visible.

Lo que se propone es otra cosa: tramar **solo las mesetas detectadas** —el degradé del
huevo, del orden de décimas de por ciento de las celdas— con `--dither-byte-budget` en
valores muy bajos, seleccionando por el mapa de suavidad y **aceptando por
`proxy_banding`**, la métrica que en aquel momento no existía y que por diseño no castiga
al dither (a diferencia del PSNR y del error Oklab medio, que son promedios por píxel y
lo castigan por construcción).

La maquinaria ya está entera: `apply_calibrated_dither` con histéresis temporal,
presupuesto de celdas y bisección determinista sobre presupuesto de bytes. Lo único
nuevo es la **selección dirigida** y el criterio de aceptación.

**Cierre:** decisión visual del operador con previews, como todas las de este carril. Si
vuelve a decir que no se nota, se descarta **con evidencia nueva** en vez de heredada.
Esta vez la pregunta es distinta: no «¿se ve mejor el clip?» sino «¿desapareció el
escalonado del huevo?».

---

## 7. E-29 — Costo de decodificación en la elección de tag (opcional)

**Archivo:** `backend/ascl_v2.py`.

El transcode elige el tag **solo por bytes**. Pero los tags no cuestan lo mismo en el TV:
un `PREDICT_DELTA` que ahorra 200 bytes le impone al decoder **dos pasadas completas
sobre todas las celdas** (2 × 2,07 M a 1920), donde un `REGIONAL_DELTA` con SPARSE le
habría impuesto una escritura por celda cambiada.

**Acción:** penalizar los tags caros con un peso pequeño en la comparación, de modo que
solo ganen cuando el ahorro de bytes sea real y no marginal. Es el hueco más claro del
pipeline y pesa el triple a 1920.

**Cierre:** bytes ≈ iguales (< 0,2 %), peor caso por frame medible menor en
`bench_reader_v2.js`. Opcional: no bloquea nada.

---

## 8. Lo que este carril NO toca

- **No revierte el near-lossless 8.** El ahorro adoptado se conserva; lo que cambia es
  *dónde* se cobra.
- **No reintroduce el dither global.** E-28 es dirigido y con presupuesto, y su cierre
  es visual.
- **No cambia el formato.** Todo F10 emite ASCL v3 exactamente igual que hoy; el decoder
  del TV no se entera.
- **No usa IA ni segmentación.** El mapa de suavidad son dos derivadas en Oklab.

## 9. Orden de ejecución

E-25 (habilita el resto) → E-27 (la más barata y la que ataca la causa directa) →
E-26 (la de mayor techo) → E-28 (decisión visual) → E-29 (opcional).

Cada una es un run de encode del producto (~1 h de runner a 1280) más su fila de
registro. Conviene medirlas sobre el 1280@15 v3 vigente para que la comparación sea
directa contra el producto.
