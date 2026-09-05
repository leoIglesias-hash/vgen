# SPEC-VGEN — el formato `.vgen`, borrador 0.1 (H-7)

> **Estado: BORRADOR para la firma del operador.** Escrito la noche del
> 2026-09-05 (turno nocturno, sin aparato). Nada de este documento es contrato
> hasta que el operador lo apruebe; hasta entonces es la spec **tal como el
> prototipo la ejecuta**. Cada regla cita la fila que la sostiene (E-nn del
> [`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md), S-nn de
> [`EMISION-V0.md`](EMISION-V0.md)/[`EMISION-V1.md`](EMISION-V1.md), entradas
> del [REGISTRO](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md)). Lo que no tiene fila
> reproducida en **dos clases de aparato** va marcado **⏳ gateado** y no se
> normaliza (VISION §8: ningún aparato solo define el formato).
>
> **Lo que este borrador ya ejecuta:** `frontend/producto.html` (H-8a) consume
> exactamente §3, §4, §5 y §6 sobre el pack publicado en `v0/`. Si la spec y el
> prototipo discrepan, gana el prototipo hasta que la spec se firme, y la
> discrepancia se anota acá.

---

## 0. Vocabulario

| Término | Qué es |
|---|---|
| **máster** | el `.ascl`/`.asclv` determinista de donde sale todo (paleta, look, cortes). No viaja al aparato |
| **paquete** | lo que viaja: piezas + manifiestos + guion. Hoy un **directorio** (§2.1); mañana un archivo único (§2.2, ⏳) |
| **pieza** | un archivo de video o audio que `<video>`/`<audio>` reproduce **solo**, por hardware |
| **representación segmentada** | la misma pieza partida en `init` + `chunk-*` (remux, sin recodificar), para el bucle por MSE |
| **rango** | `[offset, largo]` de un segmento dentro de un buffer único (§5.3) |
| **guion** | qué pieza hace cada **papel** del producto (loop, incentivador, publicidad, radio) |
| **residencia** | las piezas guardadas en el aparato (IndexedDB), de donde se reproduce siempre |
| **capa** | el único canvas encima del video, con lo vivo |
| **clase de aparato** | la TV box (Chromium 70, **consagra**), el Smart TV (Chrome 142, arbitra), la PC (refuta) |

## 1. Principios normativos

1. **`<video>` es la única puerta al hardware.** Toda pieza termina en algo que
   `<video>` acepta nativamente; nada se decodifica en CPU (VISION §3; DIAG-003).
2. **Encoder caro, decoder sin estrés.** El aparato no cuantiza ni decide: elige
   entre lo ya emitido (E13).
3. **Determinismo:** mismo máster + mismos parámetros → mismos bytes, en
   cualquier códec. Se verifica con dos pasadas, no se supone (H-14b, E19).
4. **Texto tabulado, nunca JSON.** Manifiestos y guion se parsean con `split`;
   el gate ES5 prohíbe `JSON` (DISENO §10).
5. **Se supone explícito, se reproduce, y recién ahí se normaliza.** Una regla
   entra a esta spec con **dos clases de aparato** que la sostengan; una sola
   puede refutarla (VISION §8).
6. **Los valores manuales del operador prevalecen** sobre cualquier automatismo
   (prioridades, tope de residencia, códec elegido).

## 2. El paquete

### 2.1 Forma de hoy (borrador 0.1): un directorio servido por HTTP

```
v0/
├── MANIFEST.tsv          piezas del pack v0            (§3)
├── MANIFEST-v1.tsv       piezas del pack v1 (se anexa) (§3)
├── GUION.tsv             papeles del producto          (§4)
├── producto.html         el player mínimo (H-8a)
├── keypad.js  vgenfeed.js  vgencache.js
├── <pieza>.webm | .mp4 | .mp3
└── <representación>/     init.<ext> + chunk-00001..N.<ext> (+ manifest.mpd / stream.m3u8)
```

- Todo vive bajo **un mismo prefijo**; las rutas de los manifiestos son
  relativas a él. `?base=` permite apuntar a otro prefijo (banco local).
- **Pineo por contenido:** cada pieza lleva su `sha256` en el manifiesto; la
  clave de residencia es `id + "." + sha12` (§5.1). Una pieza re-emitida con
  otros bytes es **otra clave**; una re-emisión byte-idéntica no invalida nada
  (H-14b hizo esto posible).
- Los manifiestos y el guion se sirven **sin caché** (no-store) o con un
  puntero revalidable; las piezas pueden servirse `immutable` (CACHE-001).

### 2.2 Forma futura: archivo único `.vgen` — ⏳ gateado

Magic `VGEN` + versión, cabecera (hash del máster, base, paleta), tabla de
rangos por representación y las piezas concatenadas. **Los rangos que hoy la
residencia arma en memoria (§5.3) son exactamente esa tabla**: el archivo único
es la serialización de lo que el prototipo ya hace. Se normaliza cuando el
muxer de H-8 lo emita y dos clases lo reproduzcan desde `blob:` y por MSE.
Nombre `.vgen` fijado por el operador (2026-09-01).

## 3. Manifiesto de piezas (`MANIFEST*.tsv`)

Emitido por `tools/emit_pieces.py` / `tools/emit_v1.py`. Columnas **exactas**,
en este orden, separadas por tabulador:

| # | columna | contenido |
|---|---|---|
| 1 | `id` | identificador estable de la pieza (`v1-vp9`, `v0-vp9-alpha`, …) |
| 2 | `role` | rol de emisión (`base`, `alpha`, `stream`, `v1`, `radio`, `stream-v1`); informativo, el producto usa el guion |
| 3 | `mime` | **lo que se le pasa a `canPlayType`** (pieza entera) o a `addSourceBuffer` (representación) |
| 4 | `file` | ruta relativa al prefijo; en una representación segmentada, su `manifest.mpd`/`stream.m3u8` |
| 5 | `bytes` | tamaño total (de la representación: la suma de sus archivos); es lo que suma el presupuesto (§5.2) |
| 6 | `sha256` | huella del archivo (de la representación: la del conjunto); **obligatoria** |
| 7 | `note` | texto libre; en una representación segmentada **lleva `N segmentos`** |

Cabecera: líneas `#` con `master <sha256 del .asclv>`, `base WxH fps cuadros` y
la `receta` de emisión. Varios manifiestos se **anexan sin duplicar ids** (v1
sobre v0: el primero gana).

**Layout de una representación segmentada** (lo que emite ffmpeg por remux,
E19): `init.<ext>` + `chunk-%05d.<ext>`, con `<ext>` = `webm` si el MIME del
SourceBuffer contiene `webm`, si no `m4s`. Cuántos chunks hay lo dice el guion
(`chunks`), no se lista el directorio.

## 4. Guion (`GUION.tsv`)

Una fila por **papel**. Columnas exactas:

| # | columna | contenido |
|---|---|---|
| 1 | `rol` | `loop` · `incentivador` · `publicidad` · `radio` |
| 2 | `id` | id de la pieza en el manifiesto |
| 3 | `residente` | `si` \| `no` (§5) |
| 4 | `prioridad` | entero, **menor = antes** (§5.2); lo fija el operador a mano |
| 5 | `segmentos` | id de la representación segmentada de esa misma pieza, o `-` |
| 6 | `chunks` | cuántos `chunk-*` tiene, o `-` |
| 7 | `mse` | MIME para el `SourceBuffer` del bucle, o `-` |
| 8 | `nota` | texto libre |

Semántica de los papeles (PLAN §2.7, decisión del operador 2026-09-01):

- **`loop`** — puede repetirse. El orden es la **preferencia** (E13: VP9 base,
  H.264 Baseline piso). El aparato toma **el primero cuyo `mime` dé
  `canPlayType` no vacío** (`maybe` y `probably` valen: lo que decide es
  reproducir). **Solo ese** candidato y su representación segmentada quedan
  residentes; los otros se marcan `no elegido`.
- **`incentivador`** — pieza con alfa que entra **encima** del loop en un segundo
  `<video>` del mismo rectángulo, suena **una vez** y sale sola (H-18b).
- **`publicidad`** — pieza que **reemplaza** al loop en el mismo `<video>`, con
  **su propio audio muxeado** (S13), y **vuelve sola** al loop al terminar.
- **`radio`** — pista de ambiente en un `<audio>` aparte, en bucle, con rampa de
  volumen cuando la publicidad suena (§7).

Cada papel existe a lo sumo una vez salvo `loop`. Si un papel falta o su pieza
no está en el manifiesto, el producto lo **declara** (`no esta`) y sigue.

## 5. Residencia (H-15)

Requisito del operador (2026-09-04): prendido ≥ 16 h/día, **baja una vez** y
reproduce **siempre desde el aparato**; nada de «falso streaming»; el arranque
es **con red** (E16) y lo que se exige es que después los bytes salgan del
aparato.

### 5.1 Clave y registro

- Base IndexedDB `vgen`, store `piezas`, `keyPath = key`.
- `key = id + "." + sha256[0..12)` (`VGenCache.keyFor`).
- Registro: `{ key, id, sha, mime, bytes, data (ArrayBuffer), rangos, at }`.
  Se guardan **ArrayBuffers**, no Blobs (clon estructurado universal); el Blob
  se arma al reproducir.

### 5.2 Presupuesto y plan

- `presupuesto = min(tope, fracción × cuota_declarada)`; **tope 150 MB,
  fracción 0,5** por defecto; sin cuota declarada manda el tope. Manuales:
  `?tope=<MB>`, `?fraccion=<0..1>`.
  *Por qué el tope:* la cuota declarada **no es un gate** (la caja dice 13/225 MB
  y después 43/225 con la base vacía; REGISTRO 2026-09-04 noche).
- **Plan:** las piezas `residente: si` se ordenan por `prioridad` (empate: orden
  del guion) y se toman **mientras entren**; la **primera que no entra corta
  el plan** y todo lo que sigue va «por red» — no se cuela una pieza chica
  saltando una grande, porque el orden lo fijó el operador.
- Lo `residente: no` y lo que quedó afuera se reproduce **por red** (`src`
  directo) y se declara así en el reporte.

### 5.3 Rangos: un solo buffer por representación

Una representación segmentada se guarda como **un registro** cuyo `data` es
`init + chunk-1 + … + chunk-N` pegados, con `rangos = [[offset, largo], …]`
(`VGenCache.join`); el rango 0 es el init. Al reproducir, cada segmento es una
**vista** `Uint8Array(data, offset, largo)` sin copia (`VGenCache.part`), que
es lo que `appendBuffer` acepta. **Los mismos bytes sirven enteros (Blob,
camino A) y de a pedazos (anillo MSE, camino B).** Es la tabla de rangos del
archivo único (§2.2), ya en uso.

### 5.4 Bajada

Secuencial, una parte por vez, con progreso a pantalla (`onProgress`): en la
TV una bajada de 9 MB sin progreso parece colgada. Lo que ya está no toca la
red (`cache`); lo que falta se baja (`red`); lo que no entra o falla se declara
(`error: <nombre>`) y esa pieza va por red. Evidencia: persiste al cierre de la
app (H-12), 50 MB en tandas de 5 MB con la app viva (H-12b).

### 5.5 ⏳ Gateado en residencia

- **Chequeo diario del manifiesto** (a lo sumo una bajada por día): hoy el
  prototipo asegura la residencia **al abrir**; la política de «una vez por
  día» se normaliza cuando haya un aparato corriendo días.
- **Borrado de claves viejas** (`prune`): el prototipo **no borra nada** —
  conviven con lo que la página de pruebas guardó con `84`. Política pendiente.
- **Presupuesto por clase** (la caja 225 MB, el Smart TV 2.637 MB): los
  defaults salen de la caja; el operador los ajusta a mano.

## 6. Reproducción (el contrato del runtime)

### 6.1 Elección de códec
Orden del guion + `canPlayType` (§4). VP9 base, Baseline piso (E13). Main solo
como detector de hardware (E2). H.265 no evaluado; AV1 columna futura.

### 6.2 El bucle: anillo MSE en modo `sequence`
- **Normativo (S12, H-13):** el bucle del producto es un `SourceBuffer` en modo
  `sequence` al que se anexan `init` una vez y los segmentos 1..N **en anillo**
  (`VGenFeed.ring`). El modo `sequence` reescribe tiempos en orden de anexo: la
  vuelta no tiene costura de tiempos.
- Se anexa **solo cuando hace falta**: si lo bufereado por delante supera
  `ahead` (4 s) se espera; lo ya visto se borra con `remove` cuando queda a más
  de 2×`keep` (12 s) atrás. Un anillo que corre 16 h no acumula nada.
- **`loop` nativo está refutado** en la clase principal (3 `waiting`/60 s,
  H-13) y **no se usa en producto**; el prototipo lo deja en la tecla `3` solo
  para comparar.
- **Caída:** sin MSE o sin representación segmentada, la pieza entera desde
  `blob:` con reinicio al `ended`, **midiendo la costura** (ms entre `ended` y
  el siguiente avance). ⏳ La costura aceptable la fija el ojo del operador.

### 6.3 Publicidad
Cambio por `src` a la pieza residente (`blob:`), **destapada** (su audio
muxeado), radio a 0,1 con rampa; al `ended`, vuelta al loop **en la misma
modalidad** y radio a 1. Se miden **ida** (pedido → primer avance) y **vuelta**.
Gate: ≤ 1 s desde caché (PLAN §3.1; E4: 517 ms desde `blob:` en la caja).

### 6.4 Incentivador
Segundo `<video>` **exactamente sobre el loop** (H-18b), pieza alfa residente,
`loop=false`, sale al `ended`. Cuenta sus propios cuadros. Tres planos
habilitados por el ojo del operador (H-20).

### 6.5 Radio
`<audio>` aparte, `loop=true`, volumen con **rampa** (pasos de 0,05 cada 50 ms).
Si el aparato exige un gesto, se **declara** (`el aparato pide un gesto`) y la
tecla `6` la prende.

### 6.6 La capa
Un solo canvas, buffer **al panel** (`k = screen.width / innerWidth`, tope 1;
en la caja 1280/3840), 15 fps, **contenido por papel** (loop: número + aguja;
incentivador: `RULETA`; publicidad: etiqueta), **lee `currentTime` del video
en cada pintada** (H-11): una pintada tardía muestra lo correcto, después.
Fuente Hobo por `@font-face`, cae a `monospace`, llegada detectada midiendo
`MMMMM` contra `iiiii` (H-16).

**Imagen encima (H-23, ⏳ la caja):** la capa puede girar una imagen
(`drawImage` con `translate/rotate`, ángulo = `currentTime` del video, una
vuelta cada 4 s) sobre el incentivador con alfa. La imagen se pide **una
vez**, al primer uso; si no llega, se dibuja un emblema en un canvas aparte y
se gira ese (el reporte dice cuál). Se limpia solo el cuadrado de su
diagonal, nunca el canvas entero. Cada pintada se cronometra por carga
(`numeros`, `numeros+imagen`: media, máximo, cantidad) para que la foto diga
cuánto cuesta la imagen y no solo si se ve.

### 6.7 Vigilancia
- `play()` **reintentado cada 2 s** mientras el video esté en pausa sin haberla
  pedido (pestaña oculta, política de gestos), y **contado** (`reintentos`,
  `pausado`): un aparato que pausa solo es un dato.
- Zócalo **a 1 Hz**, nunca por cuadro (regla 3); reporte en texto plano a dos
  columnas para la foto (H-20).
- Contadores de cuadros: `getVideoPlaybackQuality` si existe, si no los
  `webkit*FrameCount`; restas negativas = base perdida → absolutos (H-12b).

### 6.8 Mando
En el producto, **teclas de una cifra**, todas instantáneas: `1` anillo MSE,
`2` blob con costura, `3` loop nativo (comparación), `4` incentivador,
`5` publicidad, `6` radio, `7` capa (cicla números → números + imagen girando
→ apagada), `8` leyenda, `9` reporte, `0` cortar.

## 7. Audio: tres clases (DISENO §7, operador 2026-09-01)

| Clase | Camino | Sincronía | Estado |
|---|---|---|---|
| ambiente («radio») | `<audio>` aparte, en bucle | ninguna | S14 medida en la PC (deriva A/V en `74`); ⏳ caja |
| propio de una pieza | muxeado en la pieza (Opus en WebM, AAC en mp4) | exacta | S13 emitida en v1 (E19); ⏳ caja |
| cue sobre el loop | clip disparado por `currentTime` | ≥ 1 cuadro | ⏳ sin implementar |

## 8. Perfil → camino de runtime

| Perfil | Detecta | Camino del loop | Evidencia |
|---|---|---|---|
| P0 piso | `<video>` + Baseline + `Blob` | pieza entera `blob:` con costura | S10 (Blob = archivo) en la caja |
| P1 | + VP9 por hardware | ídem con VP9 | «perfecto, hasta más fluido» (operador) |
| P2 | + MSE + IndexedDB | **anillo MSE desde rangos residentes** | S9/S12 en la caja (CMAF); ⏳ VP9 por MSE (`75`) |
| D nativo (HLS/DASH) | `canPlayType` | **fuera del producto** | HLS-TS «se traba mucho al iniciar» (operador) |

## 9. Determinismo y huellas

- x264 con `cpu-independent=1`: **cuatro CPUs = un archivo** (H-14b).
- libvpx-vp9 con `-threads 1` + `+bitexact`: idéntico entre runners (H-18b).
- Audio: AAC/Opus son de punto flotante; dos pasadas en la misma máquina son
  idénticas (E19); entre CPUs distintas **⏳** (P-006 propone mp3 tal cual).
- La huella de una pieza es su `sha256`; la residencia pinea por ella.

## 10. Fuera de este borrador (⏳)

Sprites ASCILINE con transparencia y trayectoria; cues finos `t → acción`;
huecos horneados por el encoder; variantes N3; intercambio sub-cuadro N4; el
archivo único (§2.2); AV1/HEVC; el muxer offline ES5 (H-8 lo emite: hoy el
paquete lo emite Python en CI).

## 11. Trazabilidad

| Regla | Fila que la sostiene |
|---|---|
| `<video>` única puerta | DIAG-003 (290 ms/cuadro en JS vs «reproduce muy bien») |
| VP9 base, Baseline piso | E13; operador 2026-09-04 |
| Bucle por MSE `sequence`, `loop` nativo refutado | H-13 (REGISTRO «H-13: reporte de la caja»), S12 |
| Blob concatenado = archivo | S10 |
| Capa encima, lee `currentTime` | H-11 (0/155 caídos) |
| Imagen girando por `drawImage` sobre el alfa, medida por pintada | H-23 (PC: 0,20 ms med / 2,2 max a 1280×720; ⏳ la caja) |
| Efecto = video con alfa, mismo rectángulo | H-18b (2/154, 1/141) |
| Tres planos | H-20 + ojo del operador («se ven perfecto») |
| Persistencia y techo de residencia | H-12, H-12b (50 MB en tandas) |
| Cuota declarada no es gate | REGISTRO 2026-09-04 noche |
| Arranque ∝ bytes por red; gate desde caché | E4, PLAN §2.9 |
| Determinismo | H-14b, E19 |
| Texto tabulado | DISENO §10 |
| Mando de una cifra | H-22 (cuatro caminos para el dígito) |

## 12. Qué tiene que devolver el aparato para firmar este borrador

Con `producto.html` (`9` para la foto), en la caja **y** en el Smart TV:

1. **Loop por anillo MSE** (`1`): ≥ 10 minutos, `atascos 0`, caídos ≤ 3 %,
   `vueltas` creciendo; el ojo sin ver la costura.
2. **Publicidad** (`5`): `ida` y `vuelta` ≤ 1.000 ms desde caché; la radio baja
   y vuelve.
3. **Incentivador** (`4`): `arranco` ≤ 1.000 ms, compone encima, sale solo.
4. **Residencia**: segunda apertura con `leidas N, guardadas 0`; y con la red
   cortada y la página ya abierta, `1` sigue sonando (`red no`).
5. **Radio**: `arranco` sin gesto, o declarado.
6. **Imagen girando** (`7` `7`, después `4`): `capa numeros+imagen` con su
   costo por pintada, `imagen lista logo.png`, los `caidos` del incentivador y
   del loop no peores que sin la imagen, y el ojo: gira suave encima del alfa.

Lo que falle refuta la regla correspondiente de §6 y vuelve a ⏳.
