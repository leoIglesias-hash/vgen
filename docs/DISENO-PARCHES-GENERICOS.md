# Diseño — parches genéricos de imagen (INT-003)

Estado: **diseño cerrado con el operador, 2026-08-28. En implementación.**
Es la generalización de INT-001 (implementada y cerrada en F7/S-5). Las tareas
ejecutables viven en `RUNBOOK-IMPLEMENTACION.md` §4-INT-003 y su avance en
`RUNBOOK-ESTADO.md` (Carril INT-003).

## 1. Pedido del operador (literal, 2026-08-28)

> Reemplazar, más allá de números, **zonas de video** con **imágenes que
> convertiremos al formato adecuado** y que luego serán lo que reemplace.
> Así podríamos usar **cualquier tipografía**, y un **random en el momento
> (línea de tiempo) y ubicación (x, y)** adecuados nos daría números al azar;
> pero también podría **reemplazar una ruleta al final de su giro** para que
> coincida en su totalidad con el juego (como ejemplo).

## 2. Lectura técnica

Hoy (F7) la unidad de asset es el **glifo**: 11 parches fijos de
`glyph_w × glyph_h`, cuantizados a las 10 entradas reservadas (246..255), en
slots de posición fija con ventana temporal `start..end`. El pedido pide tres
generalizaciones, en orden de dificultad:

1. **Parche = imagen arbitraria horneada offline** (tabla de N parches de
   tamaños heterogéneos).
2. **Selección dinámica de parche + posición + momento** (el dato elige qué
   parche va en qué slot; los lugares/momentos candidatos se declaran).
3. **Caso ruleta:** un parche grande elegido entre N variantes pre-horneadas.

## 3. Decisiones D1..D6 — RESUELTAS con el operador (2026-08-28)

| # | Decisión | Resolución |
|---|---|---|
| D1 | Paleta de los parches | **Ampliar la reserva a 32 entradas** (índices 224..255). Las 10 actuales (246..255) conservan índice y RGB — los glifos ya horneados siguen válidos y 255 sigue siendo transparente. Se agregan 22 colores de arte genérico en 224..245 (§4). INV-3 pasa a ser paramétrico: «toda celda ≥ 256−reserved es overlay». El encoder ya es genérico en `reserved` (regla `pal_size ≥ reserved+22`); la base queda con 224 colores por época |
| D2 | Presupuesto de área | **Se mantiene 5%… pero por frame, no total** (§5.4): en cualquier frame, la suma de áreas de slots cuya ventana lo incluye ≤ `cols*rows/20` (verificable estáticamente por barrido de eventos start/end). La suma TOTAL de áreas (RAM del buffer base) tiene su propio techo: ≤ `cols*rows/4`. Así entran muchos slots candidatos en momentos distintos sin subir el costo por frame del TV. La ruleta grande queda para la fase ASCLVID3 |
| D3 | Límite por parche | **Se mantiene `w*h ≤ 4096`** para la vía corta; techo global de datos de parches 256 KiB. La ruleta lo revisará junto con D6 |
| D4 | Posición | **Slots candidatos fijos** declarados y validados estáticamente; el dato solo elige qué campo activar y con qué valor. Novedad: dos slots pueden solaparse en el espacio **solo si sus ventanas temporales son disjuntas** (candidatos alternativos del mismo lugar en momentos distintos) |
| D5 | Formato del canal | **Generalizado y todo-numérico** (§6): los campos de dígitos viajan igual que hoy; los campos de elección viajan como `presencia(1) + valor(W)` con ancho fijo. La validación en 5 pasos y el serial monotónico no cambian |
| D6 | Versionado | **ASCLSLOT v2 ahora** (lo exige la tabla de parches heterogéneos); la **ruleta** (parche grande, paleta por época si hiciera falta) se diseña **una sola vez junto con `ASCLVID3`** en F6/S-4 |

## 4. Reserva ampliada — 32 entradas canónicas (224..255)

`backend/overlay_palette.py` pasa a exportar **dos** tablas: `RESERVED_RGB`
(10, compatibilidad) y `RESERVED_RGB_32` (32). Las últimas 10 filas de la de
32 son **bit-idénticas** a la de 10. Los 22 colores nuevos (arte genérico,
deterministas y documentados):

| Índice | RGB | Uso |
|---|---|---|
| 224 | (128, 0, 0) | rojo oscuro |
| 225 | (255, 0, 0) | rojo |
| 226 | (255, 128, 128) | rojo claro |
| 227 | (128, 64, 0) | marrón |
| 228 | (255, 128, 0) | naranja |
| 229 | (255, 255, 0) | amarillo |
| 230 | (128, 128, 0) | oliva |
| 231 | (0, 128, 0) | verde oscuro |
| 232 | (0, 255, 0) | verde |
| 233 | (128, 255, 128) | verde claro |
| 234 | (0, 128, 128) | verde azulado |
| 235 | (0, 255, 255) | cian |
| 236 | (0, 0, 128) | azul oscuro |
| 237 | (0, 0, 255) | azul |
| 238 | (128, 128, 255) | azul claro |
| 239 | (128, 0, 128) | púrpura |
| 240 | (255, 0, 255) | magenta |
| 241 | (255, 128, 192) | rosa |
| 242 | (255, 224, 189) | piel clara |
| 243 | (141, 85, 36) | piel oscura |
| 244 | (192, 192, 192) | plata |
| 245 | (255, 215, 0) | oro |

`make_clip --reserved` acepta `0`, `10` o `32`; con 32 estampa
`RESERVED_RGB_32` al final de cada época (INV-4 paramétrico) y protege el
panel igual que hoy. El costo de calidad de bajar la base de 246 a 224
colores se mide con `bench_ref` y se registra (regla 5).

## 5. ASCLSLOT v2 — spec binaria (little-endian)

La v1 (§7.1 de `DISENO-INTERVENCION-MATRICIAL.md`) sigue siendo válida y
soportada: `slots.js` y `make_slots.py` aceptan ambas versiones. La v2:

```
magic         8 B   "ASCLSLOT"
version       1 B   2
reserved      1 B   0 (canónico)
pal_reserved  1 B   N en 10..64 (reserva = 256−N .. 255)
flags         1 B   0 (canónico)
n_patches     2 B   u16 (1..512)
n_slots       2 B   u16 (1..1024)
n_fields      2 B   u16
crc32         4 B   zlib.crc32 del resto del archivo (byte 22 en adelante)
reserved_rgb  3*N B los N RGB de (256−N)..255
patch_dir     n_patches * 4 B    (w u16, h u16 por parche)
patch_data    Σ(w*h) B           (índices en [256−N .. 255]; 255 = transparente)
slot_table    n_slots * 17 B     (x,y,w,h u16; start,end u32; flags u8)
field_table   variable           (field_id u16, kind u8, count u8,
                                  slot_ids u16*count, min u32, max u32,
                                  pad u8, patch_base u16)
```

### 5.1 Parches

- `1 ≤ w*h ≤ 4096` por parche; `Σ(w*h) ≤ 262144` (256 KiB).
- Todo byte de parche está en `[256−N .. 255]`; 255 nunca se pinta.
- El `patch_id` es el índice en `patch_dir`. Parches no referenciados por
  ningún campo están permitidos (packs con variantes).

### 5.2 Slots

- Cada slot tiene sus **propias dimensiones** `w,h ≥ 1`; debe entrar en la
  grilla y `end ≥ start` (y `end < n_frames` si se conoce).
- **Solape:** dos slots que se solapan en el espacio deben tener ventanas
  temporales **disjuntas**; solape espacial + temporal se rechaza.

### 5.3 Campos

- `kind=0` (**dígitos**, semántica v1): `count` slots, todos con las mismas
  dimensiones; los parches `patch_base .. patch_base+10` existen y tienen esas
  mismas dimensiones (0..9 + vacío en +10); `pad ∈ {0,1}`;
  `max < 10^count`; `max ≥ min`.
- `kind=1` (**elección**): `count == 1`, `pad == 0` (canónico); los parches
  `patch_base .. patch_base+(max−min)` existen y tienen las dimensiones del
  slot; `max−min ≤ 511`.
- Un slot aparece en a lo sumo un campo. Slots sin campo nunca se pintan.

### 5.4 Presupuestos (reemplazan al 5% total de v1)

- **Por frame (costo del TV):** para todo frame `f`,
  `Σ w*h de slots con start ≤ f ≤ end` ≤ `cols*rows/20` (5%). Se verifica
  estáticamente con un barrido de eventos `start`/`end+1`.
- **Total (RAM del buffer base):** `Σ w*h de todos los slots` ≤ `cols*rows/4`.

### 5.5 Canonicidad (regla 8 del proyecto)

Bytes `reserved`/`flags` ≠ 0, `kind ∉ {0,1}`, `kind=1` con `pad ≠ 0` o
`count ≠ 1`, CRC inválido, tablas truncadas o bytes sobrantes → rechazo total,
sin carga parcial (contrato C3).

## 6. Canal de datos v2 (extiende §8 de INT-001)

Mensaje: `<serial de 8 dígitos>|<payload>\n`, **solo caracteres 0..9**, `|` y
`\n` — la validación en 5 pasos y el serial monotónico de `datachannel.js`
quedan intactos (solo cambia la longitud esperada, que ya la provee
`overlay.digitCount`).

Payload por campo, en el orden de la tabla:

- `kind=0`: `count` dígitos, valor posicional (idéntico a v1).
- `kind=1`: `1 + W` dígitos con `W = len(str(max))`:
  - presencia `0` → el slot queda **vacío** (no se pinta); canónico: los `W`
    dígitos de valor deben ser `0` (otro valor se rechaza);
  - presencia `1` → `min ≤ valor ≤ max`; se pinta el parche
    `patch_base + (valor − min)`.

El «random de momento y ubicación» lo produce el **generador del dato**: elige
qué campos de elección activa (posición) y cuándo cambia el archivo (momento),
siempre dentro de los slots/ventanas declarados. El player jamás valida
geometría en runtime.

## 7. Runtime v2 (overlay.js / overlay_ref.py)

- `values` pasa a `Uint16Array` (índice de parche por slot) con centinela
  `NONE = 65535` → el slot no se pinta, no se guarda base y no se marca sucio.
- Valores iniciales: campos de dígitos → parche vacío (`patch_base+10`,
  byte-idéntico a v1); campos de elección y slots sin campo → `NONE`.
- `setField(fieldId, valor)` sirve para ambos kinds; `clearField` vuelve a
  vacío/`NONE`. `setValues(payload)` valida TODO el payload (incluida la
  canonicidad de presencia) antes de aplicar nada (INV-7).
- El orden por frame §9.2 (restaurar → seek → guardar/pintar/marcar) y la
  ausencia de allocaciones en el camino caliente **no cambian**. Los offsets
  de parche y de base por slot se precalculan en `attach` (sumas prefijas).
- `attach` verifica la cola de paleta contra `reserved_rgb` usando `N` del
  sidecar: `pal[(256−N)*3 ..]` — con un sidecar v1 se comporta exactamente
  como hoy (N=10).

## 8. Qué NO cambia

- Un solo layer, una matriz, restauración antes de decodificar (INT-001 §9.2).
- Validar todo antes de mutar; el dato jamás elige URL ni indexa fuera de las
  tablas declaradas; serial monotónico; INV-7.
- El costo se paga offline: los parches se hornean y cuantizan en el encoder;
  el TV solo copia índices.
- Canvas2D piso, WebGL1 acelera; ES5.1 estricto.

## 9. Interacción con el roadmap

- **F3 (E-12..E-18):** el refit debe excluir la reserva vigente
  (paramétrica: 246.. o 224..).
- **F6 (S-4 / ASCLVID3):** ahí se diseña la **ruleta** (parche grande, D2/D3
  revisados, posible paleta por época) — una sola migración adicional.
- **F8:** mide MEM-001/costo con el peor frame del presupuesto v2 (5%).
