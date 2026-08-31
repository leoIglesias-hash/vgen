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

## Próxima acción (actualizado 2026-08-31, plan nuevo aprobado por el operador)

Lo vivo, en orden. El cómo-se-llegó-acá está en la bitácora (al final), en
[`ejecutados/`](ejecutados/README.md) y en el
[`REGISTRO`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md); no hace falta releerlos para seguir.

**F9 (S-8): tareas cerradas y medidas, frontend publicado; falta portar W-20 a la página
que sirve la raíz.** Orden acordado
con el operador (Instancia 030): **F9 → F10 → F11 → F8 → DIAG-001**.

1. **F9 tiene TODAS sus tareas cerradas y medidas** (`W-16`..`W-20`; `W-21` sigue
   opcional). `W-19` cerró con el veredicto del operador —no distingue `soft` de
   `nearest`, así que el default sigue `nearest`, 1 tap y bit-idéntico— y `W-20` con su
   medición en pantalla real: **p95 14,90 ms contra 66,7 de presupuesto, drops 0**
   (Instancias 036 y 037). El ruido que el operador había reportado eran **dos defectos
   reales**, arreglados en `af6bfff`.
2. **Frontend PUBLICADO el 2026-08-31** (Instancia 038): 24 keys = (los 4 archivos que F9
   cambió + `tv-player.html` y `diagnostic-player.html`, nuevas) × las 4 carpetas, los 24
   verificados byte-idénticos al repo. **Aditiva: los otros 11 archivos conservan su
   `md5`**, overlay/textos/datachannel intactos. Antes se guardó en el repo lo que estaba
   vivo (`deploy/asciline-player/`: `worker.js`, los 15 archivos servidos y el manifiesto
   de las 71 keys) — el worker **no existía fuera de Cloudflare**.
3. **PENDIENTE PARA CERRAR F9: portar W-20 a `live-player.html`.** El manifiesto probó que
   `index.html` **es** `live-player.html`, no el `tv-player.html` que el MAPA llama
   «producción»: la raíz ya ganó W-17 y W-18 (van en los `reader*.js`/`render-*.js`
   compartidos), pero la cadencia y el pre-decode viven sólo en `tv-player.html`. Por la
   directiva del operador —«una actualización no pierde nada»— **no** se reemplaza una
   página por la otra (perdería overlay, textos y datachannel): se porta W-20. Después,
   resumen en `ejecutados/` y F9 cerrada.
   - La comparación `1280 soft` vs **`1920` nativo en el TV** se **movió a F8**, que es la
     fase de validación en TV físico; sigue decidiéndose **por video**. La medición de
     W-20 fue en GPU de PC a 1280@15: la holgura de 4,5× es el margen que F8 tiene que
     confirmar que le alcanza a un televisor.
3. **F10 (S-9)** — pérdida adaptativa por suavidad: E-25 → E-27 → E-26 → E-28. Ataca el
   degradé escalonado sin devolver el ahorro del near-lossless 8.
4. **F11 (S-10)** — formato v4: E-30 (LOD horneado, **sin** cambio de formato, medible
   solo) → E-31 (análisis de frames de solo-paleta, sin formato) → F11-1 (opcode
   `LOD2`) → F11-5 (paleta en delta, **solo si E-31 lo justifica**) → F11-2
   (**transparencia**, pedido del operador) → F11-3 (espejo JS + cross-test) → F11-4
   (barrido y adopción). Idea anotada sin tarea: **paletas por región** (gate: que E-25
   muestre saturación de las 256 entradas).
5. **F8 (S-6)** — validación física en TV, ya con F9-F11 adentro. **INT-005 sigue
   CONDICIONADO** a que los gates físicos fallen para el overlay nativo (dirección del
   operador 2026-08-30).
6. **DIAG-001** — causa del escalonado del huevo; **al final por decisión del operador**,
   y probablemente ya resuelto por F9/F10 para entonces.
7. **Del operador, en paralelo:** probar `https://iargen.com/player/` en el **celular y
   el Smart TV**. Ya aprobó el v3 a ojo en desktop («se ve igual», Instancia 029).
   Variantes para comparar: raíz = producto 1280@15 **v3**, `/player/1280-15/` (v2),
   `/player/1280-12/`, `/player/1920-10/`.
8. Opcionales sin fase: E-11 (flags de audio), W-15 (camino ASCII), W-21 (dirty en X),
   E-29 (costo de decode en la elección de tag). Menor: si se retoma el 960, re-medirlo
   con refit 5. Infra: si `publish-player` se vuelve habitual, migrar los pins a un
   `__pins.json` en el bucket.

Tareas con archivo, acción y criterio de cierre en el
[`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §3. Diseño en
[`DISENO-RENDER-INDEXADO.md`](DISENO-RENDER-INDEXADO.md),
[`DISENO-PERDIDA-ADAPTATIVA.md`](DISENO-PERDIDA-ADAPTATIVA.md) y
[`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md).

**Principio del operador (2026-08-31, extiende la regla 9):** la **resolución y los fps
son elegibles por video, siempre**, nunca fijados por una receta. El destino real son
televisores de 1920, así que toda grilla se estira; lo que se elige por video es cuánta
densidad conviene pagar, y comparar 1280 bien reconstruido contra 1920 nativo es parte
del trabajo de cada clip.

**Estado de fases: F0-F7 completas y verificadas; S-1..S-5 y S-7 cerradas; abiertas
S-8 (F9, en ejecución), S-9 (F10), S-10 (F11) y S-6 (F8).** El detalle de cada cierre:
tabla de fases abajo, [`ejecutados/`](ejecutados/README.md) y las tablas archivadas.

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

> Al iniciar cada sesión de implementación: agregar una fila con el commit o snapshot
> sobre el que se trabaja. Si el árbol cambió desde el 2026-08-27, localizar las
> referencias por nombre de función, no por número de línea.

## Tareas abiertas (plan del 2026-08-31, Instancia 030)

Una fila por tarea (regla 1). El cuerpo de cada una —archivo, acción, criterio de
cierre— está en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §3.

| ID | Fase | Qué | Estado | Δbytes |
|---|---|---|---|---|
| W-16 | F9 | banco `bench_render.js` + `diagnostic-player.html` (F8-1 adelantada) | **cerrada 2026-08-31** (`f1ccfa3`) | no |
| W-17 | F9 | LUT `Uint32` de paleta en la conversión RGBA | **cerrada 2026-08-31** (`8cecc7b`) | no |
| W-18 | F9 | textura de índices + paleta en el shader (WebGL) | **implementada 2026-08-31** (`07a94e2`); paridad GL/2D verificada (delta 0) | no |
| W-19 | F9 | reconstrucción de 4 taps (modo `soft`) + escalado entero de diagnóstico | **CERRADA 2026-08-31** (`07a94e2` + `af6bfff`): el operador **no distingue `soft` de `nearest`** en PC → **default `nearest`** (1 tap, bit-idéntico); `soft` queda disponible por video. El `1280 soft` vs `1920` en TV se mueve a **F8** (Instancia 036) | no |
| W-20 | F9 | cadencia de presentación y pre-decode del keyframe | **CERRADA 2026-08-31** (`798203a`+`1cb0e38`): medida por el operador en pantalla real sobre el clip de producción — **p95 14,90 ms contra 66,7 de presupuesto (22 %), drops 0 y tarde 0 en 497 presentaciones**; `rgba` en 0,00 y `pre-key` p95 14,10 **fuera** del presupuesto sin causar drops (Instancia 037) | no |
| W-21 | F9 | dirty rect en X | opcional — **candidata a dejar de serlo**: W-17 mostró que en deltas dispersos el costo dominante es barrer todo `dirtyCellBits`, no escribir | no |
| E-25 | F10 | `--gradient-boost` + mapa de suavidad reutilizable | pendiente | solo con valores ≠ 3.0 |
| E-27 | F10 | guard anti-banding del trellis espacial | pendiente | sí |
| E-26 | F10 | `--near-lossless-shape`: presupuesto modulado por suavidad | pendiente | sí |
| E-28 | F10 | dither dirigido a mesetas con presupuesto en bytes | pendiente | sí |
| E-29 | F10 | costo de decodificación en la elección de tag | opcional | sí |
| E-30 | F11 | `--lod-tile`: horneado 2×2 en tiles de bajo detalle (**sin** cambio de formato; excluye rampas suaves con el mapa de E-25) | pendiente | sí |
| E-31 | F11 | análisis offline de frames candidatos a solo-paleta (fundidos/flashes); gate de F11-5 | pendiente | no |
| F11-1 | F11 | opcode `0x08 LOD2` | pendiente | sí |
| F11-5 | F11 | paleta en frame delta / tag `PALETTE_ONLY` (v4) | **condicionada a E-31 + operador** | sí |
| F11-2 | F11 | transparencia: `cell_fmt 4` (paleta RGBA), `--alpha`, `--alpha-levels` | pendiente | sí |
| F11-3 | F11 | espejo JS, despacho por versión, `test_v4_cross.js`, fuzzing | pendiente | no |
| F11-4 | F11 | barrido, previews y adopción del producto v4 | pendiente | sí |
| F8-1..5 | F8 | validación física en TV (**F8-1 ya entregada dentro de W-16**: `frontend/diagnostic-player.html`) | pendiente | no |
| DIAG-001 | — | causa del escalonado del huevo (**al final**, decisión del operador) | pendiente | no |

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
| S-6 | validación física (F8) | pendiente | | |
| S-8 | **F9 — aceleración del frontend** (W-16..W-21) | en curso | 2026-08-31 | no toca bytes ni formato: se valida contra el clip en producción. Arranca por W-16 (medición). Diseño: [`DISENO-RENDER-INDEXADO.md`](DISENO-RENDER-INDEXADO.md) |
| S-9 | **F10 — pérdida adaptativa por suavidad** (E-25..E-29) | pendiente | | emite v3 igual que hoy. Diseño: [`DISENO-PERDIDA-ADAPTATIVA.md`](DISENO-PERDIDA-ADAPTATIVA.md) |
| S-10 | **F11 — formato v4: LOD por tile + transparencia** (E-30, F11-1..4) | pendiente | | una sola revisión de formato para las dos features; depende de F9 cerrada. Diseño: [`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md) |
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
