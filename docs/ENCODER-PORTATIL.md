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

## 6. Ejecución (2026-09-06) — O2, antes de H-8, por decisión del operador

Operador: *«mejor vamos directo al P-008 mientras vamos a tratar de pensar
más ideas»*. De las tres preguntas de §5: (1) **O2 ahora**, no después de
H-8; (2) sin respuesta explícita → se ejecuta con la recomendación: **el CI
manda**, y el workflow lo hace cumplir comparando; (3) sin cambio:
`emitir-v1` sigue con `dos_pasadas=true` por defecto.

**Qué hay:**

| Pieza | Qué hace |
|---|---|
| `tools/portable/armar.py` | arma `vgen-portable/`: copia el Python embebido y el ffmpeg ya descomprimidos, **solo los `.py`** de `backend/` y `tools/` (+ `requirements.txt`), los scripts del bundle, `VERSIONES.tsv` (commit, fecha, Python, ffmpeg, receta v1, master pineado) y `MANIFEST-portable.tsv` (ruta, bytes, SHA-256 de cada archivo, ordenado). No baja nada. |
| `tools/portable/emitir.ps1` + `emitir.cmd` | la emisión v1 en Windows PowerShell 5.1: baja el master pineado una sola vez y lo verifica por SHA-256, suma `ffmpeg\bin` al PATH **de ese proceso**, corre el mismo `repo/tools/emit_v1.py` con la receta v1 (`-Receta`, `-Frames`, `-Out`, `-Master`/`-Sha256`/`-SinVerificar`), borra `work/` e imprime el SHA-256 de cada pieza. Sin argumentos = el pack v1 vigente en `outputs\v1`. |
| `tools/portable/py.cmd` | el intérprete embebido con el ffmpeg del bundle en el PATH del proceso: cualquier script del repo (la mitad A incluida). |
| `.github/workflows/portable.yml` | job **`armar`** (windows-latest): baja el zip oficial `python-<v>-embed-amd64`, habilita `import site`, `get-pip`, `pip install --only-binary` numpy/Pillow/OpenCV (+ zopfli si hay wheel), baja el ffmpeg estático (`ffmpeg_url`, por defecto gyan.dev **8.1.2** essentials; la 7.1.1 que se supuso primero no existe en el sitio: 404 en la corrida 34012175765) y **verifica que traiga libx264, libvpx-vp9, libopus y aac**, corre `armar.py` con el Python del bundle, prueba `py.cmd`, y con `gate=true` **emite con `emitir.ps1` bajo `powershell.exe` 5.1** (lo mismo que en la máquina del operador); zip con 7z → artifact **`vgen-portable`** (90 días) + `gate-windows`. Job **`linux`**: la misma receta como `emitir-v1` → `gate-linux`. Job **`comparar`**: tabla pieza por pieza IDENTICA/DISTINTA en el resumen; **falla si alguna difiere** (el bundle queda publicado igual, marcado «sirve para probar, no para publicar»). |
| `tests/test_portable_bundle.py` | arma un bundle con Python/ffmpeg falsos y verifica la carpeta, el manifest (SHA real de `emit_v1.py`), `VERSIONES.tsv`, y que **la receta v1 y el master pineado sean UNO** en `armar.py`, `emitir.ps1`, el workflow y `EMISION-V1.md`. Entra por `unittest discover` en `run_all.py`. |

**Lo que no cambia:** ni un byte de `backend/` ni de `tools/*.py`; el bundle
corre el mismo código. La regla de la máquina se mantiene: nada se instala,
nada toca PATH ni registro.

**Gate (el CI manda):** tres corridas el mismo día; el resultado está en §7.

## 7. El gate, leído (2026-09-06, corridas 34012175765 → 34012297378 → 34012545002)

| Corrida | Qué pasó |
|---|---|
| **34012175765** (`c7a7088`) | Python embebido OK (numpy 2.4.6, Pillow 12.3.0, OpenCV 5.0.0, zopfli 0.4.3 con wheel). **404 en el ffmpeg**: el `7.1.1-essentials` que se supuso no existe en gyan.dev (el sitio publica `packages/ffmpeg-8.1.2-essentials_build.zip`; BtbN tiene tags `autobuild-<fecha>` pinneables como alternativa). Linux emitió bien. |
| **34012297378** (`5b3a3d2`) | Con **ffmpeg 8.1.2** el bundle se armó (zip **190,8 MB**), `emitir.ps1` corrió bajo `powershell.exe` 5.1 y emitió las tres piezas en **105 s** (Linux 69 s). Dos defectos encontrados por la corrida: (a) **el DASH quedó vacío en Windows** (`manifest.mpd` solo, «-1 segmentos»): el muxer `dash`/`hls` de ffmpeg ubica la carpeta del playlist buscando `/`, y con `\` deja init y segmentos en el directorio actual → `posix_path()` en `emit_pieces.py`/`emit_v1.py` (barras siempre; en Linux no cambia un byte); (b) el job `comparar` marcó DISTINTA hasta el mp3 idéntico (CRLF en los `.tsv` de Windows) y aun así pasó (el contador vivía en un subshell) → limpieza de `\r` y contador fuera del pipe. |
| **34012545002** (`aaff2a2`) | **DASH arreglado:** 18 archivos (manifest + init + **16 segmentos**), **2.831.164 B, el mismo total que Linux**. Windows 106 s, Linux 68 s. Tabla del gate: |

| pieza | Windows (bundle, ffmpeg 8.1.2 gyan) | Linux (CI, ffmpeg 6.1.1 Ubuntu) | veredicto |
|---|---|---|---|
| `v1-ambiente.mp3` | 183.353 B `c886263508da` | 183.353 B `c886263508da` | **IDÉNTICA** (es la pista del máster tal cual) |
| `v1-h264.mp4` | 5.254.451 B `175722d34d0f` | 5.254.272 B `7992b0cc75a2` | DISTINTA (+179 B) |
| `v1-vp9.webm` | 2.941.178 B `4b0714ed21ca` | 2.941.449 B `8adf852aa70a` | DISTINTA (−271 B) |

**Lo que dicen los números, con cuidado:**

1. **El bundle funciona de punta a punta** en Windows sin instalar nada: baja
   y verifica el máster, emite VP9+Opus, H.264+AAC, la radio y el DASH, e
   imprime los SHA. Es lo que el operador pidió («más rápido y sin
   instalar»); *más rápido* no es (106 s contra 68 del runner: el costo es
   ffmpeg, como decía §3), pero **no espera cola ni baja artifact**.
2. **Windows no emite los mismos bytes que Ubuntu** para VP9 y H.264, como
   se advirtió en §2.3: otro binario (x264/libvpx de otra versión y otro
   compilador). No es un defecto del bundle; es lo que se iba a medir.
3. **El bundle es determinista consigo mismo:** las corridas 2 y 3, en dos
   runners de Windows distintos, dieron **el mismo `4b0714ed21ca`** para VP9
   y **el mismo `175722d34d0f`** para H.264.
4. **El CI de Linux, en cambio, NO repitió el VP9 entre corridas:** run 2
   `86014f175105`, run 3 `8adf852aa70a` (mismos bytes, distinta huella). Es
   el Opus (punto flotante, sin `cpu-independent`) en CPUs de runner
   distintas — lo mismo que `emitir-v1` mide con sus dos pasadas. O sea: el
   «CI manda» de la pregunta 2 de §5 ya no era una huella fija para VP9+Opus.

**Lo que decide el operador (pregunta 2 de §5, ahora con evidencia):**

- **A — el CI manda (la recomendación original):** el bundle sirve para
  *ver* un pack en un minuto; lo que se publica y se pinea por contenido sale
  de `emitir-v1`. Costo: dos huellas por receta (local y CI), y la del CI
  cambia con el Opus según el runner.
- **B — el bundle manda:** el emisor del producto es el bundle, y **el CI
  corre el mismo bundle en un runner de Windows** (`portable` ya lo hace)
  para reproducir la huella: un solo binario, una sola huella, y la
  reproducibilidad se demuestra como en H-14b (dos runners, mismos bytes —
  ya ocurrió en las corridas 2 y 3). Costo: el emisor de referencia pasa a
  ser Windows + gyan 8.1.2 pinneado por URL, y cada cambio de ffmpeg es un
  cambio de huella declarado.

La recomendación cambia con el punto 4: **B**, porque es la única de las dos
donde el archivo que el operador emite en su máquina y el que el CI
reproduce son **el mismo**, que es la definición de árbitro que pide la
regla 5. Hasta que el operador decida, rige A.

**Cómo se baja:** Actions → `portable` → la corrida → artifact
**`vgen-portable`** (zip 190.785.339 B, SHA-256
`3bc08fe48462814c458c03452af99b314691bdd68d2ab9fe7c38d1282ac4de7d`, 90
días); descomprimir en cualquier carpeta y `emitir.cmd`. Nada más.
