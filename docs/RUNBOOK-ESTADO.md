# Estado de ejecución del runbook

Este archivo es la memoria entre sesiones. Se actualiza **al cerrar cada tarea**, no al
final del día. La próxima sesión de trabajo —humana o asistida— arranca leyendo este
archivo, no reconstruyendo el contexto.

Reglas de uso:

1. Una fila por tarea del [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).
   Al cerrarse una fase completa, sus tablas se archivan verbatim en `ejecutados/`
   y acá queda el resumen por carril (sección «Tareas cerradas»).
2. Estados válidos: `pendiente`, `en curso`, `cerrada`, `bloqueada (<por qué>)`,
   `archivada (<evidencia>)`, `opcional`.
3. Una tarea `cerrada` cumple la definición de terminado del runbook §5; no se marca antes.
4. Toda decisión que desvíe del runbook se anota en la bitácora de abajo con fecha y
   motivo. El runbook no se edita en silencio.

## Próxima acción (actualizado 2026-09-01 — DECISIÓN TOMADA: nace ASCILINE-hybrid)

**El operador decidió la dirección el 2026-09-01: el proyecto adopta el carril
mp4/híbrido y continúa en este repo, `leoIglesias-hash/ASCILINE-hybrid`** (clon
con la historia completa de `ASCILINE-video` — `main` + `assets` —; el repo
anterior queda congelado como antecesor, con un aviso de continuación). Sus
palabras: *«el paradigma cambió… necesitamos trabajar con mp4 pero logrando
mejoras de reproductividad, y para eso tendremos que hacer nuevas
investigaciones»*.

El porqué, medido en la caja real (REGISTRO, DIAG-002/003, 2026-08-31..09-01):

- el player 100 % JS **no llega a 15 fps ahí** (FRAME p50 290 ms contra 66,7 de
  presupuesto; el cuello es CPU — `inflate` solo ya come el presupuesto — y la
  vista 1:1 solo mejora ~20 %); además el WebGL de esa GPU **no presenta**
  (pantallazos blancos; canvas2d limpio);
- el mismo producto decodificado a H.264 (`producto.mp4`: el `.asclv` máster
  `dcd6afb6…1632a` → 1280×720 @15, 4.130.240 B) *«reproduce muy bien»* por
  `<video>` con decodificador de **hardware** — y pesa **6× menos** que el
  `.asclv` (17 %) y 10,6 % del mp4 fuente.

**El paradigma nuevo:** el encoder sigue decidiendo todo offline y el `.asclv`
sigue siendo el **máster** determinista; lo que viaja al TV es el **mp4 emitido
desde ese máster** (`preview=true` del workflow `encode`), y la **intervención**
(números, texto, logo, canal en vivo) va en un canvas encima — dos capas, por
decisión del operador. El player JS queda como reproductor de escritorio y banco
de verificación del máster: se mantiene, no crece.

Lo vivo, en orden (cuerpos en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2):

1. **H-0 — repo nuevo + reorganización de docs: CERRADA con este commit.** Los
   diseños y planes del paradigma JS pasaron **verbatim** a
   [`historico/`](historico/README.md); F10, F11, F8, DIAG-001 y las opcionales
   quedan **suspendidas** (no borradas: recuperables con decisión del operador).
2. **H-1 — `DISENO-HIBRIDO.md`** (diseño formal, sin código): sincronía
   intervención↔video, cómo viaja el sidecar si el TV ya no baja el `.asclv`,
   distribución del mp4 con CACHE-001 por contenido, fallback si no hay `<video>`.
3. **H-2 — investigación de reproducibilidad mp4** (paralelizable con H-1):
   matriz de emisión H.264 (bitrate/CRF, profile/level, GOP, two-pass) desde el
   máster vigente, medida en la caja con `frontend/tv-video-test.html` y cerrada
   con veredicto del operador.
4. **H-3 — player híbrido mínimo** (`<video>` + canvas de intervención reusando
   `overlay.js`/`textlayer.js`/`slots.js`): **solo con H-1 aprobada.**
5. **W-26** (heredada, independiente): la raíz publicada elige WebGL sin salida —
   aceptar `?renderer=` y decidir el default para WebViews de TV box.
6. Externo: pedirle a la app de la caja que el WebView reporte el panel real
   (hoy da 3840×2160 sobre un panel de 1280×720 = 9× de píxeles regalados).

**Principio del operador (2026-08-31, sigue vigente):** la **resolución y los
fps son elegibles por video, siempre**, nunca fijados por una receta. Aplica
igual a la emisión del mp4: densidad y fps se eligen por clip.

**Estado de fases: F0-F9 completas y verificadas (paradigma anterior; resúmenes
en [`ejecutados/`](ejecutados/README.md)); DIAG-002/003 cerradas con decisión;
abierta la fase H (H-0 cerrada, H-1/H-2 próximas); F10/F11/F8/DIAG-001
suspendidas.** El detalle: tabla de tareas abajo y las tablas archivadas.

**Receta de producto vigente (2026-08-31, S-4 cerrada):** defaults del workflow
`encode` + **`format=v3`** + **`tile=sweep`** + **`--cols 1280`** en extra —
1280×720 @15 fps graphic-hq, adaptive kmeans-oklab, dither off, zopfli, overlay=off,
`--palette-refit 5 --near-lossless 8 --cols 1280` →
**`dcd6afb6…1632a`** (24.458.884 B, 35,02 dB, **62,8 % del mp4 fuente**; el sweep
elige regional 32 con trellis espacial 16; ~1 h de runner, RSS 1,6 GB). Instalado en
`outputs/` y servido como raíz de iargen.com/player/ vía puntero CACHE-001.

**Player EN PRODUCCIÓN** (infra propia, nada preexistente tocado): bucket R2 +
Worker `asciline-player`, ruta `iargen.com/player*`, espejo
`asciline-player.iargen.workers.dev`. **Copia de lo desplegado, en el repo:**
[`deploy/asciline-player/`](../deploy/asciline-player/README.md) — `worker.js` verbatim,
los archivos servidos y `MANIFEST.tsv` con las 71 keys. Subir clips o frontend SIN
redeploy: acuñar `UPLOAD_TOKEN` por la API, `PUT /__upload/<key>` con `x-upload-token`
+ `x-sha256` (R2 verifica el digest), verificar lo servido y **quemar** el token.
**Ningún token se persiste jamás** — por eso no hay workflow de publicación de frontend
(exigiría un secret de GitHub). Ojo: el worker desplegado **no tiene** autorización por
contenido, aunque `publish-player` la asuma; ese workflow no funcionaría hoy. Detalle:
[`ejecutados/2026-08-31-S7-resolucion-y-deploy-player.md`](ejecutados/2026-08-31-S7-resolucion-y-deploy-player.md).

## Cómo ver lo ya implementado (para no pisarse)

- **La sección «Tareas cerradas» de abajo** resume los carriles; las tablas completas
  (una fila por tarea con estado, commit y evidencia) están archivadas verbatim en
  [`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md).
  Si una tarea figura `cerrada`, no se re-implementa: se extiende.
- [`ejecutados/`](ejecutados/README.md): resumen operativo por fase o lote cerrado.
- [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md): el porqué
  de cada decisión, por Instancia (append-only).
- Los SHA de todos los clips medidos: sección «Referencias de clips» al final.

## Procedencia del código

| Sesión | Fecha | Base de trabajo | Notas |
|---|---|---|---|
| planificación | 2026-08-27 | snapshot ZIP `ASCILINE-video-main` (referencias `archivo:línea` del runbook corresponden a este árbol) | auditoría, diseño INT-001, plan y runbook; sin cambios de código |
| implementación 1 | 2026-08-27 | mismo snapshot, git local `5493455` (baseline) | 8 tareas cerradas; parches en `entrega-2026-08-27/patches/`, aplicables con `git am` sobre el repo real |
| sincronización | 2026-08-27 | clon real en `Escritorio\\repo` (baseline == snapshot, verificado) | `git am` no se aplicó; los 22 archivos finales se escribieron directo en el árbol de trabajo. Historia por tarea preservada solo en los parches; el repo la recibe como un commit |
| implementación 2 | 2026-08-27 | clon real de GitHub, `906b010` | máquina sin Python/Node **a propósito**: la regresión se valida en GitHub Actions en cada push; commits directos a `main`, un commit por tarea |
| F6 (S-4) | 2026-08-30 | `main` en `ae5f574` (post-deploy del player) | arranca la revisión única de formato; orden elegido F6-1 → F6-3 → F6-2 → F6-4 (el barrido definitivo de tile corre sobre el codec v3 final) |
| fase H (H-0) | 2026-09-01 | clon de `ASCILINE-video` en `f89abcd` (cierre del diagnóstico DIAG-002/003) → repo nuevo `leoIglesias-hash/ASCILINE-hybrid` | historia completa preservada (`main` + `assets`); mismo modelo de trabajo (CI-only, commits directos a `main`) |

> Al iniciar cada sesión de implementación: agregar una fila con el commit o snapshot
> sobre el que se trabaja. Si el árbol cambió desde el 2026-08-27, localizar las
> referencias por nombre de función, no por número de línea.

## Tareas abiertas (fase H, plan del 2026-09-01)

Una fila por tarea (regla 1). El cuerpo de cada una —archivo, acción, criterio de
cierre— está en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2.

| ID | Fase | Qué | Estado | Δbytes |
|---|---|---|---|---|
| H-0 | H | repo `ASCILINE-hybrid` + docs reorganizadas al paradigma mp4/híbrido | **cerrada 2026-09-01** (este commit) | no |
| H-1 | H | `DISENO-HIBRIDO.md`: sincronía intervención↔video, sidecar, distribución CACHE-001 del mp4, fallback | pendiente | no |
| H-2 | H | investigación de reproducibilidad mp4: matriz de emisión H.264 desde el máster, medida en la caja | pendiente | sí (mp4) |
| H-3 | H | player híbrido mínimo (`<video>` + canvas de intervención) | pendiente (precondición: H-1) | no |
| W-26 | — | escape `?renderer=` en la raíz publicada + default para TV box | pendiente | no |

**Suspendidas por el cambio de dirección (2026-09-01)** — recuperables verbatim de
[`historico/RUNBOOK-IMPLEMENTACION-asclv-js.md`](historico/RUNBOOK-IMPLEMENTACION-asclv-js.md)
solo con decisión del operador: E-25..E-28 (F10), E-30/E-31/F11-1..5 (F11),
F8-1..5 (validación física del player JS), DIAG-001, y las opcionales
E-11/W-15/W-21/E-29. Nota para si se retoma F10: el mp4 hereda los píxeles del
`.asclv`, así que la calidad del máster (anti-banding) sigue teniendo efecto en
el producto híbrido.

## Tareas cerradas (archivadas 2026-08-31)

Las tablas completas de tareas cerradas (una fila por tarea con commit, fecha y
notas técnicas, **verbatim**) se archivaron en
[`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md)
para mantener corto este archivo. Regla intacta: si una tarea figura `cerrada`, no se
re-implementa — se extiende. Resumen por carril:

| Carril | Tareas | Estado | Resumen en ejecutados |
|---|---|---|---|
| Preparación | P-01..P-04 | cerradas 2026-08-27 | [`F0`](ejecutados/2026-08-27-F0-base-congelada.md) |
| E — encoder | E-01..E-24 (E-11 **opcional**, pendiente) | cerradas 2026-08-27..30 | [`F0`](ejecutados/2026-08-27-F0-base-congelada.md) · [`F1`](ejecutados/2026-08-27-F1-paleta-reservada-glifos-sidecar.md) · [`F2`](ejecutados/2026-08-28-F2-compresion-e08-10.md) · [`F3`](ejecutados/2026-08-29-F3-carril-calidad.md) · [`F5`](ejecutados/2026-08-30-F5-trellis-near-lossless.md) |
| W — frontend | W-01..W-14 (W-15 **opcional**, pendiente) | cerradas 2026-08-27..28 | [`W-01..05`](ejecutados/2026-08-27-W01-05-frontend.md) · [`F4`](ejecutados/2026-08-28-F4-frontend-w06-14.md) |
| F7 — runtime overlay (S-5) | F7-1..F7-4 + integración | cerradas 2026-08-28 | [`F7`](ejecutados/2026-08-28-F7-runtime-overlay.md) |
| INT-003 — parches genéricos | A..F | cerradas 2026-08-28 | [`INT-003`](ejecutados/2026-08-28-INT-003-parches-genericos.md) |
| INT-004 — texto nativo | A..B | cerradas 2026-08-28 | [`INT-004`](ejecutados/2026-08-28-INT-004-texto-nativo.md) |
| INT-006 — fondo sin reserva | A..C | cerradas 2026-08-28 | [`INT-006`](ejecutados/2026-08-28-INT-006-fondo-sin-reserva.md) |
| INT-007 — tipografía + logo giratorio | A..B | cerradas 2026-08-29 | [`F5`](ejecutados/2026-08-30-F5-trellis-near-lossless.md) |
| F6 — formato v3 (S-4) | F6-1..F6-4 | cerradas 2026-08-30..31 | [`F6`](ejecutados/2026-08-31-F6-formato-v3-S4.md) |

## Sincronización y fases finales

| ID | Qué | Estado | Fecha | Notas |
|---|---|---|---|---|
| S-1 | merge de F0 | cerrada | 2026-08-27 | historial lineal en el snapshot; equivale al merge |
| S-2 | habilitar artefactos `tile_size` ≠ 16 | cerrada | 2026-08-27 | W-08 en verde: `ReaderV2` abre los seis tamaños; E-09 puede generar artefactos |
| S-3 | desbloquear E-10 | cerrada | 2026-08-28 | W-02 estaba en verde desde la sesión 1; E-10 ejecutada y cerrada |
| S-4 | revisión única de formato (F6) + barrido definitivo de `tile_size` | cerrada | 2026-08-31 | F6-1/2/3/4 cerradas (Carril F6) y acto de cierre ejecutado: producto **1280@15 v3 tile=sweep** = `dcd6afb6…1632a` (24.458.884 B = 62,8 %, 35,02 dB, run 33352859235; sweep eligió regional 32/espacial 16 también a 1280), instalado en `outputs/` y publicado como raíz de iargen.com/player/ (puntero CACHE-001, reproducción v3 verificada en navegador). v3 ADOPTADO como formato de producto |
| S-5 | runtime del overlay (F7) | cerrada | 2026-08-28 | F7-1..F7-4 + integración en verde; gates de INT-002 cubiertos por la regresión (Instancia 014). Los dos gates físicos (costo p95 y MEM-001 en TV) se miden en F8-2/F8-4, donde el plan ya los prevé con y sin overlay |
| S-6 | validación física (F8) | **suspendida** (cambio de dirección 2026-09-01) | | era la validación del player JS en TV; el híbrido tendrá la suya (H-3) |
| S-8 | **F9 — aceleración del frontend** (W-16..W-25) | cerrada | 2026-08-31 | medida y publicada (28 keys). Diseño archivado: [`historico/DISENO-RENDER-INDEXADO.md`](historico/DISENO-RENDER-INDEXADO.md) |
| S-9 | **F10 — pérdida adaptativa por suavidad** (E-25..E-28) | **suspendida** (cambio de dirección 2026-09-01) | | diseño archivado: [`historico/DISENO-PERDIDA-ADAPTATIVA.md`](historico/DISENO-PERDIDA-ADAPTATIVA.md); si se retoma sigue valiendo — el mp4 hereda los píxeles del máster |
| S-10 | **F11 — formato v4: LOD por tile + transparencia** (E-30, F11-1..5) | **suspendida** (cambio de dirección 2026-09-01) | | diseño archivado: [`historico/DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](historico/DISENO-FORMATO-V4-LOD-Y-ALPHA.md); su motivación principal (aliviar el decoder JS) desapareció con el híbrido |
| H | **fase H — híbrido mp4 + intervención** (H-0..H-3, W-26) | en curso | 2026-09-01 | H-0 cerrada (nace este repo); cuerpos en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2 |
| S-7 | barrido de resolución 768 → 1280 → 1920 con el stack completo | cerrada | 2026-08-31 | Instancia 028: tres escalones aprobados a ojo; **producto = 1280 @15 fps** (`2a9201bf…b778`, 63 % de la fuente; el 1920 descartado por fluidez a 10 fps, no por imagen — vuelve a más fps como prueba futura y el front debe procesar cualquier resolución). Hallazgo central: la tasa por celda CAE al subir resolución (0,1451 → 0,1144 → 0,1023 B/celda/frame). Re-encode del producto diferido al cierre de S-4 (v3 + tile ganador) |

## Referencias de clips (SHA-256)

Todos los clips medidos, del vigente al histórico. «Reproducible» = re-encodear desde
`main` con esos flags devuelve ese SHA byte a byte (regla 5, verificada — nunca supuesta).

**Producto vigente (S-4/S-7 cerradas, 2026-08-31): 1280 @15 fps, formato v3,
tile=sweep (espacial 16 + regional 32) = `dcd6afb6…1632a`**
(`dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a`, 24.458.884 B =
**62,8 % del mp4 fuente**, 35,02 dB, Oklab 0,00901, err_temporal 0,00713,
proxy_banding 0,001522, run 33352859235, wall 59:54, RSS 1,6 GB; instalado en
`outputs/` con SHA verificado y publicado en iargen.com/player/ vía puntero
CACHE-001; reproducible con los defaults del workflow + `format=v3` + `tile=sweep`
+ extra `--palette-refit 5 --near-lossless 8 --cols 1280`).

Producto anterior 768 (near-lossless 8, v2 tile 16): `b081f4ba…f6a05e` (11.304.137 B,
35,10 dB, Oklab 0,00897, err_temporal 0,00705, proxy_banding 0,001587, run
33321490398, reproducible con los defaults pelados del workflow). Su transcodificación
v3 tile 32 (F6-2): `6f28a459…8784` (bundle 11.261.986 B, misma calidad, byte-idéntica
en dos runs) · diagonal espacial-32 `8b5d0f1e…e738` (11.276.362 B, peor, descartada).

Barrido S-7 (Instancia 028, cerrada): 1280@15 v2 `2a9201bf…b778` (24.530.460 B,
35,02 dB, run 33325334610 — antecesor directo del producto vigente) · 1280@12
`27ae0019…e828` (21.196.032 B, 34,95 dB, run 33326623591) · 1920@10 `87160987…8d4e`
(32.838.265 B, 34,81 dB, run 33333170964).

Candidatos y filas históricas: near-lossless 6 `db32e8c4…2157` (11.951.807 B, 35,37 dB)
y 5 `157bccf0…4c44` (12.339.798 B, 35,48 dB), no elegidos · near-lossless 4
`5a45592b…92d0` (12.840.889 B, ≈ producto temporal 4) · temporal 4 `221de28f…0373`
(12.846.465 B, 35,59 dB, tres runs byte-idénticos, producto anterior — reproducible con
`extra = --palette-refit 5 --trellis-temporal 4`) · temporal 2 `63fb7aae…adde`
(14.315.422 B, 35,75 dB, aprobado y superado el mismo día) · temporal 10 `5db38f9d…`
(10.778.521 B, 34,81 dB, descartado) · espacial 8/16 `28edb2ad…`/`c84dfe92…`
(Instancia 026, sin adopción en solitario) · base E-21 sin trellis `41c94170…79d5`
(17.170.673 B, 35,63 dB, dos runs byte-idénticos, reproducible con
`extra = --palette-refit 5`) · sin dither pre-E-21 `74be25ef…011f9` (17.168.633 B, fila
histórica: el emisor cambió con E-21 y ya no se reproduce desde main) · tramado refit 5
`adef9e53…c05bb` (17.379.859 B, 35,46 dB, reproducible con dither=auto) · dither budget
450 `aabd518a…8bf6` (17.246.050 B, descartado) · budget 0 `909ba629…f68e` (descartado:
41 B más que `off` y 4:43 más lento) · refit 5 + uint8-refine 3 `a95d0bbc…acbf`
(E-13 medido sin adoptar) · refit 3 `514be81e…a01aff` · dither exacto E-16
`0ed4cbbe…92f5` (medido sin adoptar) · P-02 sin refit `ebfe2eb4…4b36` (17.482.270 B,
reproducible con el flag en 0) · ultra 960 sin refit `31348a83…5688` (25.003.004 B,
superado; re-medir con refit 5 si se retoma) · panel v1 `7da584f1…5a51d` · parches v2
`c315a13a…8e63` + sidecar `678b392d…2c56` (demo INT-003/004). Los detalles de cada fila
están en el REGISTRO, por Instancia.

**Byte-identidad, historia** (regla 5): los runs 33220236164 (post-E-16), 33233492257
(post-E-18) y 33235096580 (post-E-19/E-20) reprodujeron byte a byte `adef9e53…c05bb`;
la Instancia 027 reprodujo `41c94170…` y `221de28f…` con el emisor post-E-24. Desde
E-21 el SHA de producto se movió **a propósito** (Instancia 024). Regresión vigente:
**342 pruebas Python (327 + 12 de F6-3 + 3 de F6-4) y 27 suites JavaScript**
(+`test_v3_cross`; CI verde de `6fd23b6`).

## Bitácora de decisiones de ejecución (historial append-only)

> Esta sección es historial: se agrega al pie, nunca se relee entera. Las filas del
> 2026-08-27 al 2026-08-30 se archivaron verbatim en
> [`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md);
> las decisiones nuevas se siguen anotando ACÁ, al pie de esta tabla.

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-08-31 | **F6-2 cerrada con los runs A/B del barrido 2D** (Instancia 029): run A (33350852865, espacial 16 + sweep regional) reprodujo **byte a byte** el `6f28a459…8784` del sweep original — regla 5 verificada también para el pipeline v3 completo — y run B (33350856477, espacial 32 + sweep regional) reprodujo el `8b5d0f1e…` del acoplado-32, confirmando que esa diagonal es la misma configuración y que es PEOR (+14.376 B). Ganador global: **espacial 16 + regional 32** (bundle 11.261.986 B = −0,37 % vs producto 768 v2, calidad idéntica). Decisión de receta: la config mixta se pinnea con `tile=sweep` (la elección del sweep es determinista) en vez de agregar un flag que decouple los dos ejes — cero código nuevo y el sweep documenta la elección en el log | con la fila de F6-2 la adopción de v3 quedó decidida y **el acto de cierre de S-4 se despachó en el momento**: run 33352859235 = encode único del producto 1280@15 (S-7) en `format=v3` + `tile=sweep` + extra `--palette-refit 5 --near-lossless 8 --cols 1280`. Al terminar: fila en el REGISTRO, instalación en `outputs/` y publicación al player con puntero CACHE-001 |
| 2026-08-31 | **S-4 CERRADA — v3 adoptado y el producto pasa a 1280@15 v3** (`dcd6afb6…1632a`, run 33352859235, wall 59:54, RSS 1,6 GB): el sweep a 1280 eligió el MISMO ganador que a 768 (regional 32, espacial 16, 58.456 tiles fusionados), y el v3 le ganó 71.576 B a su antecesor v2 `2a9201bf…` con calidad idéntica (35,02 dB). Instalación y publicación en el mismo acto: `outputs/` (clip + versionado + puntero) y subida al player raíz por la vía manual (token rotado vía API, 3 PUTs con `x-sha256` verificado por R2 — clip immutable + puntero + fallback `clip.asclv` actualizado —, token quemado con un valor aleatorio no registrado). Verificación en producción: puntero → `clip.dcd6afb66907.asclv` (Content-Length 24.458.884, immutable 1 año) y reproducción real en navegador (badge `ASCL v3 1280x720 @15fps`, frames avanzando, logo INT-007 girando) | primer v3 en producción: cierra S-4 con UNA sola versión nueva de decoder desplegada y el criterio del operador cumplido (su 1280@15 elegido en S-7, ahora 62,8 % de la fuente). Los subplayers 1280-15/1280-12/1920-10 conservan sus clips v2 como variantes; el operador puede comparar v2 vs v3 en el mismo dominio. Sigue F8 (TV físico) |
| 2026-08-31 | **Plan nuevo: F9, F10, F11 y DIAG-001** (Instancia 030). Auditoría completa del encoder, del frontend y del historial de ideas para no repetir lo descartado; el operador aprobó cuatro carriles y agregó uno. **F9** (front, sin tocar bytes): la conversión índice→RGBA cuesta ~14,5 M accesos por keyframe a 1920 y sube 8,3 MB — se ataca con LUT `Uint32`, textura de índices con lookup en el shader, reconstrucción de 4 taps y pacing. **F10**: la pérdida se reparte hoy en partes iguales, cuando el banding solo se ve en zonas suaves; se modula por el mapa de suavidad que ya existe y no se usa fuera del K-means. **F11**: LOD por tile (gana bytes **y** trabajo del decoder a la vez) y **transparencia** (feature nueva pedida por el operador), agrupadas en una sola revisión de formato v4. **DIAG-001** (escalado del huevo) queda **al final** por decisión explícita del operador | orden F9 → F10 → F11 → F8 → DIAG-001: F9 primero porque su ciclo de prueba dura minutos contra el clip ya publicado, en vez de una hora de runner. Se agrega el principio de que resolución y fps son elegibles **por video**, nunca fijados por receta (extiende la regla 9). Tres documentos de diseño nuevos; ninguna tarea empieza sin su medición (W-16 es precondición dura de F9) |
| 2026-08-31 | **Limpieza de documentación post-cierre** (pedido del operador: «ordená y limpiá manteniendo el historial, perdiendo lo mínimo posible»): las tablas completas de tareas cerradas (P/E/W/F7/INT-003..007/F6) y las filas de bitácora 2026-08-27..30 se movieron **verbatim** (extracción por rangos de línea, no transcripción) a `ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`; el estado quedó con lo vivo + resumen por carril + referencias de clips intactas (376 → ~180 líneas). El runbook de implementación perdió S-4/F6 y S-7 (cerradas) y quedó solo con F8 + opcionales; se agregó el ejecutado faltante de S-7 + deploy del player; índices y CLAUDE.md al día | cero pérdida: movido, no borrado — la evidencia canónica sigue siendo REGISTRO + ejecutados/; mismo patrón que la poda del 2026-08-30. Las «Referencias de clips» NO se archivan: son consulta activa (regla 5) |
| 2026-08-31 | **Revisión del plan + dos ideas nuevas anotadas para v4** (Instancia 031): el operador pidió el parecer sobre los diseños y una idea más. Se anotaron (a) **frames de solo-paleta** (E-31 análisis sin formato → F11-5 condicionada: fundidos/flashes como transformada de paleta, ~800 B por frame en vez de cientos de KB) y (b) **paletas por región** (idea del operador: N paletas de 256 con selector por tile, partición sin superposición — la región rica es dueña exclusiva de sus tiles y el fondo queda hueco debajo; gate: saturación real de las 256 en E-25). Descartado el salto a paleta de 512 (rompe el byte por celda: reescribir todos los opcodes, +30-70 % de bytes, doble subida). Ajustes de detalle cableados: E-30 excluye rampas suaves con el mapa de E-25; E-26 se mide contra el producto post-E-27; W-20 pre-decodifica **solo** keyframes | las dos ideas quedan con gate explícito para no relajar canonicidad ni cambiar formato «por si acaso»; lo medido sigue atribuyendo el escalonado a trellis (F10) y estirado fraccionario (W-19), no a falta de colores. El plan de ejecución no cambia: arranca W-16 |
| 2026-08-31 | **W-16 cerrada: F9 ya tiene banco** (Instancia 032, commit `f1ccfa3`, CI verde). `tools/bench_render.js` mide la conversión índice→RGBA sobre tres grillas × tres perfiles y compara el camino de bytes vigente contra el prototipo LUT `Uint32`; `frontend/diagnostic-player.html` (**F8-1 adelantada**) desglosa inflate/walk/RGBA/blit por frame con p50/p95, drops y tarde. Medición: keyframe a 1920 = **11,0 ms de pura conversión** en runner de CI; la LUT da **1,3×–3,3×** (≈2,2× en keyframe y tiles densos). Paridad byte a byte verificada en los 9 casos | el banco **publica** la tabla y **no** juzga tiempos (el runner comparte CPU: sería un test intermitente); lo que falla el CI es la paridad. La instrumentación vive entera en la página de diagnóstico, envolviendo métodos de la instancia: ningún archivo de producción se modifica para medir, así que lo medido es lo que corre en el TV. W-17 queda justificada con números antes de escribirse |
| 2026-08-31 | **W-17 cerrada: LUT `Uint32` en los dos readers** (Instancia 033, commit `8cecc7b`, CI verde). Medido con `bench-render` HEAD vs baseline `f1ccfa3` **en la misma corrida**: keyframe a 1920 **11,4 → 5,7 ms** (2,0×), tiles densos 6,2 → 3,3 (1,9×), disperso 1,14 → 0,85 (1,33×). Salida **byte-idéntica**, verificada corriendo los dos caminos sobre el mismo reader y el mismo frame | el destino es el selector del camino (vista `Uint32` alineada → palabra; Array plano o desalineado → bytes), y eso hace que la paridad sea comprobable sin duplicar corpus. La LUT se cachea por identidad de paleta, no por frame. El disperso gana poco porque el costo dominante es barrer todo `dirtyCellBits`: es el argumento para que **W-21 deje de ser opcional** |
| 2026-08-31 | **W-18 + W-19 implementadas** (Instancia 034, commit `07a94e2`, CI verde): en PIXEL la GPU recibe los **índices** (`LUMINANCE`) y la paleta como textura 256×1; el lookup y la mezcla de 4 taps viven en el shader. Verificado con **contexto WebGL real**: `paridad GL/2D: OK (delta max 0, camino indexado)` y etapa `rgba` en **0,00 ms** con el clip de producción. Decisión tomada acá, que el diseño no fijaba: en `soft` el **backing store sigue al tamaño de presentación** (si midiera lo mismo que la grilla, la mezcla sería un no-op y el estirado lo seguiría haciendo el compositor) | los tres modos de fallar en silencio quedaron con test: `UNPACK_ALIGNMENT` en 1, medio texel al indexar la paleta y `highp` con caída a `mediump`. La textura de índices **nunca** se filtra con LINEAR. **W-19 no se marca cerrada**: su criterio es el veredicto visual del operador en el TV, y eso no lo puede firmar nadie más |
| 2026-08-31 | **W-20 implementada, F9 con todo su código escrito** (Instancia 035, `798203a` + `1cb0e38`, CI verde). (a) La fase de presentación avanza con el reloj del **display** y se corrige lento contra el audio, que sigue siendo el maestro; un desvío > 2 cuadros resincroniza de una. (b) El próximo **keyframe** se decodifica en el tiempo muerto y se adopta **intercambiando readers**, no copiando celdas. Las dos piezas se apagan con `?pacing=off` y `?predecode=off` | el «buffer alterno de `cells`» del diseño terminó siendo un segundo reader sobre los mismos bytes: cada uno queda internamente consistente, así que no hubo que abrirle a la maquinaria dirty un modo fuera de línea ni tocar el invariante 4. Cuesta otro `cells` (2 MB a 1920) → **anotado para MEM-001**. El CI falló una vez por una aserción que exigía un bloque de texto **contiguo**: se reescribió por contenido y orden, que es lo que la propiedad realmente dice |
| 2026-08-31 | **Ruido reportado a ojo por el operador → dos defectos reales, y W-19 cerrada** (Instancia 036, commit `af6bfff`, CI verde). El CI estaba en verde y aun así había ruido en pantalla: (a) `_drawIndexed` cacheaba la vista de la banda sucia **solo por rango de filas**, así que tras un intercambio de readers de W-20 subía a la GPU las celdas del **reader anterior** (franjas con imagen de otro momento, a la cadencia de los keyframes); (b) la mezcla de 4 taps de `soft` necesita la fracción de una coordenada de hasta ~1920 texeles, imposible en `mediump`, y la caída a `mediump` era un fallback de compilación: el shader compilaba y dibujaba basura. Ahora la clave del cache incluye el **origen** del buffer y `soft` exige `highp` real (`getShaderPrecisionFormat`), si no dibuja `nearest` y el HUD lo avisa. Con eso puesto el operador vio «se ve igual» en `nearest` **y** en `?rec=soft`, y `paridad GL/2D: OK` en el navegador de su PC | dos lecciones que valen más que el arreglo: cachear por **rango** una vista sobre un buffer reemplazable es un alias silencioso —la identidad del buffer es parte de la clave—, y una caída de precisión es un fallback válido para **compilar** pero una fuente de basura para **calcular**. Consecuencia de producto: si el operador no distingue 4 taps de 1 tap, no se paga → **default `nearest`**, `soft` disponible por video. El `1280 soft` vs `1920` en TV se mueve a **F8**, que es la fase de TV físico; mantenerlo como bloqueo de F9 sería pedirle a esta fase un gate de la siguiente |
| 2026-08-31 | **W-20 cerrada con medición del operador en pantalla real** (Instancia 037). Clip de producción, `1280x720@15 · webgl/nearest · pacing on`, 497 presentaciones: **p95 de decode+render 14,90 ms contra 66,7 de presupuesto (22 %), drops 0, tarde 0**, `paridad GL/2D OK delta max 0`. Con W-19 cerrada el día anterior por veredicto visual, **F9 queda con todas sus tareas medidas** y su único pendiente es publicar el frontend | tres confirmaciones que valen más que el total: (a) `rgba` marcó **0,00 ms con el clip real** — W-18 no era efecto de banco, la conversión índice→RGBA desapareció del presupuesto; (b) `pre-key` marcó p95 **14,10 ms**, casi un frame entero, **con 0 drops**: el pre-decode corre en tiempo muerto como se diseñó, y publicarlo en fila aparte fue lo que permitió verificarlo en vez de suponerlo; (c) **el cuello de botella se movió a `inflate`** (8,70 de los 14,90 del frame, ~58 %) — después de W-17/W-18 lo caro es descomprimir, no convertir ni dibujar, y eso ordena cualquier optimización futura (`W-21` toca `walk`, ya en 3,20). Lo que la medición NO dice: es GPU de PC a 1280@15, no un TV; la holgura de 4,5× es justo el margen que **F8** debe confirmar |
| 2026-08-31 | **Frontend de F9 publicado, y directiva del operador sobre qué es una actualización** (Instancia 038). El operador fijó: «**no deberíamos perder cosas con las actualizaciones, porque son eso, actualizaciones; deben ser mejoras de lo que ya tenemos**», y además: guardar en el repo lo vivo de Cloudflare **antes** de tocarlo, y publicar con las herramientas ya cargadas en vez de pedirle pasos manuales. Se hizo primero la copia (`deploy/asciline-player/`: `worker.js` verbatim —**no existía fuera de Cloudflare**—, los 15 archivos servidos con sus `md5` iguales a los `etag` de R2, y `MANIFEST.tsv` con las 71 keys) y después la subida de 24 keys, las 24 verificadas byte-idénticas al repo; los 11 archivos no tocados conservan su `md5` | las dos directivas corrigieron el rumbo: yo proponía reemplazar el `live-player.html` publicado por `tv-player.html` (habría borrado overlay, textos y datachannel) y una ruta por CI con un secret pegado a mano. El manifiesto además desmintió al MAPA: **`index.html` ES `live-player.html`** en las 4 carpetas, y `tv-player.html` no estaba publicado en ninguna key; las variantes tienen copias byte-idénticas del código, así que toda actualización va a las 4 carpetas. Token efímero acuñado por API y **quemado** después (viejo → 403); el workflow `publish-frontend` se descartó y borró porque exigía persistir un secret. Consecuencia abierta: la raíz ganó W-17/W-18 pero **no W-20**, que vive en otra página → se porta, no se reemplaza |
| 2026-08-31 | **CI BLOQUEADO POR FACTURACIÓN DE GITHUB, no por código.** El commit `5fdfade` (solo docs) falló con los tres jobs muertos **a los 2 segundos y sin ejecutar ningún paso**. La anotación del run lo dice literal: «The job was not started because recent account payments have failed or your spending limit needs to be increased». El último commit que sí corrió y quedó **verde es `45122df`**, que ya incluye todo el código de F9 y la publicación | esto **frena el modelo de trabajo entero**: la regla es que una tarea cierra solo con CI en verde, y esta máquina no tiene Python ni Node para validar local. Mientras no se resuelva el límite de gasto en «Billing & plans», ningún cambio de código se puede dar por cerrado — se puede escribir, no verificar. Acción del operador, fuera del repo. Diagnóstico: los jobs sin pasos y con 2 s de duración son arranque fallido, no test roto; la anotación vive en `check-runs/<job>/annotations`, no en los logs (que vuelven vacíos) |
| 2026-08-31 | **Un solo motor de reproducción para las cuatro páginas** (Instancia 039, `3c46d3d` + `2753fd1` + `26b4170` + `1fe95a9`, **sin CI: sigue bloqueado**). El operador pidió «fusionar los backgrounds del front para que todos los reproductores tengan todas las mejoras». La cadencia y el pre-decode de W-20 estaban **copiados** en `tv-player.html` y en `diagnostic-player.html`, y **ausentes** en `live-player.html` —que es lo que sirve la raíz publicada— y en `player.html`. Se extrajo la maquinaria a `frontend/playloop.js` (W-22, con `tests/test_playloop.js`), se pasaron las dos páginas que la tenían (W-23) y la estrenaron las dos que no (W-24). Además W-25: el gate ES5 descartaba un `<script>` si la **coincidencia entera** contenía `src=`, así que un `var src=DEFAULT_SRC;` bastaba para que `player.html` y `diagnostic-player.html` no se analizaran nunca | tres cosas que la fusión hizo posibles y la copia impedía: (a) la raíz **por fin** tiene la cadencia, que era el único pendiente de F9; (b) el diagnostic mide **literalmente** el código de producción —antes medía una copia parecida, y una medición sobre otro código no dice nada del producto—; (c) el intercambio de readers convive con el overlay: va **entre `beforeSeek` y `afterSeek`** con `overlay.rebind(reader)` en el medio, porque la base guardada pertenece al reader que se va y restaurarla sobre el que llega escribiría celdas de otro cuadro. El gate nuevo no verifica el mecanismo sino la propiedad: **adoptar y no adoptar tienen que dar exactamente las mismas celdas**. Verificado sin CI hasta donde se puede: las 4 páginas cargan el clip de producción servido local sin errores de consola (overlay, texto e imagen activos), y las expresiones del gate ES5 corridas aparte sobre los 6 archivos tocados no dan hallazgos |
| 2026-08-31 | **La suscripción a Pro no destrabó el CI, y probablemente sea por a qué cuenta se factura.** El operador se suscribió a Pro; se relanzó el run bloqueado y se empujaron cuatro commits: los tres jobs vuelven a morir a los 2 s con la **misma** anotación de pagos/límite de gasto. Dato que lo explica: el repo es **privado** y su dueño es **`tablerosapp-ctrl`** (cuenta de usuario), mientras que quien empuja es **`leoIglesias-hash`** — GitHub cobra los minutos de un repo privado **al dueño del repo** | de ahí las dos salidas, las dos del operador: Pro + método de pago válido + límite de gasto > 0 **en `tablerosapp-ctrl`**, o hacer el repo **público** (minutos ilimitados). El token de esta sesión (scopes `gist, repo, workflow`) no puede leer la facturación de esa cuenta, así que el diagnóstico es estructural, no medido: se confirma o se descarta abriendo Billing & plans de `tablerosapp-ctrl` |
| 2026-08-31 | **El repo de trabajo se mudó a `leoIglesias-hash` y con eso el CI se destrabó** (Instancia 040). El operador: «me suscribí a Pro con `leoIglesias-hash`, ya está, hice cagada… ahora podrías descargar el proyecto y subirlo a mi github, para poder seguirlo desde ahí; luego lo sincronizamos cuando tengamos puntos de guardado, y al terminar dejo todo en `tablerosapp-ctrl`». Se creó **`leoIglesias-hash/ASCILINE-video`** (privado, vía API con la credencial ya guardada en el Credential Manager) y se espejó **todo**: `main`, `assets` (los insumos de encode), `feature/quality-optimization` y los **7 tags**. Remotos renombrados: **`origin` = el repo del operador** (donde se empuja y corre el CI), **`ctrl` = `tablerosapp-ctrl`** (destino final, se sincroniza en los puntos de guardado). El run de `866f2f1` corrió **completo y verde** (`py3.8`, `py3.11`, `py3.11 + zopfli`, 52 s), contra los 2 s sin ejecutar un paso de las últimas cuatro instancias | **confirma el diagnóstico de la Instancia 039 sin necesidad de leer facturación**: los minutos de un repo privado se cobran al **dueño del repo**, así que el Pro en `leoIglesias-hash` no servía mientras el repo fuera de `tablerosapp-ctrl`. Mudar el repo era además la salida más barata: no expone el código (sigue privado), no depende de arreglar pagos en una cuenta ajena y deja el original intacto como destino. Se canceló a mano el run que la rama vieja disparó de arrastre. Con el CI de vuelta, **W-22..W-25 pasan de `en curso (CI bloqueado)` a `cerrada`** y F9 queda con un solo pendiente: publicar |
| 2026-08-31 | **F9 CERRADA: frontend publicado en las cuatro carpetas, 28 keys** (Instancia 040). El operador aprobó publicar de forma explícita. El número de keys **se auditó en vez de estimarse**: se bajaron los 18 archivos de las 4 carpetas y se comparó SHA-256 contra el repo — 4 diferían (`live-player.html`/`index.html`, `tv-player.html`, `diagnostic-player.html`, `overlay.js`), 2 daban 404 (`playloop.js`, `player.html`) y los 12 restantes estaban idénticos. 7 por carpeta × 4 = **28**, contra las «25» que decían los runbooks. Subida con token efímero + `x-sha256` (R2 recalcula el digest), las 28 verificadas byte a byte después, token quemado | dos cosas para la próxima: (a) **auditar lo servido antes de publicar** es barato (68 GETs) y corrige una cuenta escrita a mano que ya estaba mal; (b) el burn del secret **tarda unos segundos en propagar** — el primer `PUT` con el token viejo devolvió `200` y recién el siguiente dio `403`. Dar por quemado un token con una sola prueba es un falso negativo de seguridad |
| 2026-08-31 | **DIAG-002 abierta y puesta ADELANTE DE TODO: pantallazos blancos en TV box** (reporte del operador, Instancia 040). Probó el player en un **WebView de TV box** y ve **flashes blancos entre las imágenes**: «eso es algo crítico… es muy grave y deberíamos estudiarlo». Se registra antes de investigar para que el reporte no se pierda | un flash blanco en un televisor rompe el producto: pesa más que cualquier ganancia de bytes o de milisegundos, así que se adelanta a F10. Dato de encuadre que **no** hay que perder: lo que el operador probó es lo que estaba publicado **antes** de esta instancia, o sea la raíz **sin** cadencia ni pre-decode. Si el motor nuevo mejora, empeora o no cambia el síntoma **hay que medirlo, no suponerlo** — y el nuevo `playloop.js` recién ahora está en la raíz |
| 2026-09-01 | **DECISIÓN DE DIRECCIÓN TOMADA + H-0: nace `ASCILINE-hybrid`** — el operador adoptó el carril mp4/híbrido tras el cuadro final de DIAG-002/003 («el paradigma cambió… necesitamos trabajar con mp4 pero logrando mejoras de reproductividad»). Se creó `leoIglesias-hash/ASCILINE-hybrid` (privado) clonando la historia completa (`main` + `assets`); los diseños/planes del paradigma JS se movieron **verbatim** a `docs/historico/` con README propio; runbooks, índice y CLAUDE.md reescritos para la fase H (H-1 diseño, H-2 investigación mp4, H-3 player híbrido, W-26 heredada); F10/F11/F8/DIAG-001 y opcionales quedan **suspendidas**, recuperables solo con decisión del operador | el repo anterior (`ASCILINE-video`) queda congelado como antecesor con aviso de continuación; conserva su valor como historia y evidencia. La filosofía no cambia: el encoder caro decide offline y el `.asclv` sigue de máster — cambia el transporte (mp4 emitido del máster, decodificado por hardware en el TV) y el invariante de un-solo-layer pasa a dos capas (video + canvas de intervención) por decisión explícita del operador. La rama `feature/quality-optimization` vieja no se migró (estancada; vive en los remotos del repo anterior) |
