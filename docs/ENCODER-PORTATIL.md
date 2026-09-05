# El encoder fuera del CI — evaluación (2026-09-05, turno nocturno)

> **Pedido del operador (2026-09-05, noche):** *«deberíamos pensar en mejorar
> el encoder para que sea más rápido y corra sin instalar Python ni Node en
> Windows, porque lo basamos en una idea para ejecutar una tarea y ahora
> necesitamos otro resultado como VP9… de esta manera dejamos de usar tanto el
> CI de GitHub»*. Y su propio orden: *«capaz conviene mejorar la reproducción
> del video para probar más cosas mañana y recién con un producto más pulido
> trabajar en el encoder»*.
>
> Esto es la evaluación, no la tarea. **Decisión pendiente del operador** (§5).

## 1. Qué es hoy «el encoder», en dos mitades

| Mitad | Qué hace | Con qué | Cuánto tarda en CI |
|---|---|---|---|
| **A — el máster** | mp4 del cliente → `.asclv` (paleta Oklab, K-means, trellis, near-lossless, Zopfli) | **Python + numpy**, `backend/` | minutos largos por clip (es el «encoder caro» a propósito) |
| **B — la emisión** | `.asclv` → piezas VP9 / H.264 / audio / segmentos (`tools/emit_pieces.py`, `emit_v1.py`, `emit_matrix.py`) | **Python (decodifica el máster a rgb24) + ffmpeg** (libvpx, x264, remux) | ~1 min (v1), ~10 min (matriz) |

Lo que el operador ve como «ahora necesitamos otro resultado como VP9» es la
mitad **B**. La mitad **A** no cambió de resultado: sigue emitiendo el máster.

## 2. Tres hechos que cambian el cálculo

1. **Los minutos del CI ya no cuestan.** Desde el 2026-09-05 el repo `vgen` es
   **público**, y en GitHub los minutos de Actions en repos públicos son
   gratis para runners estándar. El motivo «dejar de usar tanto el CI» pasa de
   costo a **comodidad y latencia**: cada emisión son 1–2 minutos de espera y
   una bajada de artifact, no dinero.
2. **La regla «esta máquina no tiene Python ni Node, a propósito»** existe para
   que **toda** regresión pase por el CI y no por «en mi máquina anda». Un
   encoder local que corra sin Python instalado **no rompe la regla** si es
   **portátil** (una carpeta, sin instalador, sin PATH) y si **el CI sigue
   siendo el que valida** (misma receta, mismos bytes: invariante 7).
3. **El determinismo está saldado en CI, no en Windows.** `cpu-independent=1`
   (H-14b) y `+bitexact` dan el mismo archivo en cuatro CPUs de runner
   (Linux, ffmpeg de Ubuntu). Un ffmpeg **de Windows** es otro binario, otra
   versión de libvpx/x264: **puede** dar otros bytes con la misma receta. Si el
   producto se emite local, la huella que pinea la residencia (§5 de la spec)
   sería la del binario de Windows, y habría que **verificar** que coincida
   con la del CI antes de publicar — o aceptar que la fuente de verdad pasa a
   ser la máquina del operador.

## 3. Las opciones, honestas

| Opción | Qué es | Qué compra | Qué cuesta | Riesgo |
|---|---|---|---|---|
| **O1 — seguir en CI** | nada nuevo | cero trabajo; minutos gratis; determinismo probado | 1–2 min por emisión + bajar el artifact | ninguno |
| **O2 — bundle portátil** | carpeta `vgen-portable/` con **Python embebido** (el zip oficial `python-3.x-embed-amd64`, sin instalar), numpy en `site-packages`, **ffmpeg estático** y un `emitir.cmd`/`.ps1` que corre la **misma** `tools/emit_v1.py` | emisión local en ~1 min sin esperar; **el mismo código** que el CI (cero reescritura); sirve para A y para B | armar el bundle (~1 sesión); ~150 MB en disco; **verificar bytes contra el CI** una vez por versión de ffmpeg | que el ffmpeg de Windows dé otros bytes → se detecta comparando SHA y se decide qué binario manda |
| **O3 — decoder en C# + ffmpeg** | portar el lector del `.asclv` (v3: ASCLVID3, deflate, tiles, SPARSE) a C# compilado al vuelo por PowerShell (`Add-Type`, .NET ya viene en Windows) y pipear rgb24 a ffmpeg | ni siquiera Python embebido; **solo B** | reescribir un decoder que ya existe dos veces (Python y ES5) y mantener tres; tests nuevos | duplicar lógica = divergencia silenciosa; no acelera nada (el costo es ffmpeg) |
| **O4 — encoder nuevo (A)** | reescribir la mitad A en algo más rápido (numba/C/Rust) | máster en segundos en vez de minutos | semanas; **cambia bytes del máster** salvo esfuerzo enorme de paridad | pierde la reproducibilidad acumulada; no es lo que el operador pidió («versiones anteriores las vamos a tener igual») |

**Sobre «más rápido»:** en B, el tiempo es **ffmpeg** (libvpx `-cpu-used 2` a
`-threads 1` por determinismo). La matriz H-6 lo midió (EMISION-V1 §1):
`cpu-used 4` tarda 31 s contra 36 y **cuesta +2,9 % de bytes**; `cpu-used 0`
tarda 4,6× por −1,6 %. No hay velocidad gratis ahí: la receta queda en 2. En
A, el tiempo es K-means + trellis en numpy: solo se acelera reescribiendo (O4)
o perfilando dentro de Python. **Ninguna de las dos mitades se acelera por
correr en Windows en vez de en el runner.**

## 4. Recomendación

**O2, después de H-8, y sin sacar al CI de su lugar.**

- **Qué:** un bundle portátil (`tools/portable/` + workflow que lo arma y lo
  publica como artifact: Python embebido + numpy + ffmpeg estático de
  Windows + `emitir.ps1`). El operador lo baja una vez, lo descomprime en una
  carpeta, y `emitir.ps1 master.asclv --vp9-crf 38 …` le deja el pack v1 en
  `outputs/` en un minuto. **Sin instalar nada** (nada toca PATH ni el
  registro); la regla de la máquina se mantiene.
- **Cuándo:** cuando la receta del paquete esté firmada (H-7 → H-8): hoy
  cada emisión es también una **medición** (matriz, autocontrol, dos pasadas),
  y eso es exactamente lo que el CI hace bien y una máquina sola no.
- **Gate:** el bundle **emite los mismos SHA-256** que el workflow `emitir-v1`
  para la receta vigente, verificado en el primer uso y en cada cambio de
  ffmpeg. Si no coinciden, el binario del CI manda y el bundle se corrige
  (pinnear la misma versión de libvpx/x264), nunca al revés.
- **Qué NO hacer:** O3 (tercer decoder) ni O4 (encoder nuevo) — el primero
  duplica lo que ya está probado y el segundo rompe lo que el operador dijo
  que quiere conservar.

**Lo que sí acorta la espera hoy, sin tocar bytes:** que `emitir-v1` corra
**sin la segunda pasada** cuando no cambió la receta (el determinismo ya está
probado para esa receta) — baja el run de ~2,5 min a ~1,2. Es una casilla del
workflow (`dos_pasadas=false`), ya existe.

## 5. Lo que decide el operador

1. ¿O2 después de H-8, como se recomienda? ¿O antes?
2. Si un ffmpeg de Windows diera **otros bytes** que el CI con la misma receta,
   ¿qué manda: el CI (se corrige el bundle) o la máquina del operador (se
   re-pinea el producto con esa huella)? La recomendación es **el CI**.
3. ¿Se corre `emitir-v1` con `dos_pasadas=false` por defecto mientras la receta
   no cambie? Ahorra un minuto por emisión; la doble pasada vuelve en cada
   cambio de receta.

Anotado como **P-008** en [`../PROPUESTAS.md`](../PROPUESTAS.md).
