# ASCILINE-hybrid — guía de sesión (leer esto primero, siempre)

**Sucesor de `ASCILINE-video` desde el 2026-09-01, por decisión del operador.**
El encoder Python **offline** sigue decidiendo todo (paleta, trellis, look) y
emitiendo el `.ascl`/`.asclv` como **máster determinista**; lo que cambió es el
transporte: al TV ya no viaja el `.asclv` para que un player JS lo decodifique,
sino el **mp4 (H.264) emitido desde ese máster**, reproducido por `<video>` con
decodificador de **hardware**, con la **intervención** (números, texto, logo,
canal en vivo) en un **canvas encima** — dos capas. Por qué: medido en la TV box
real, el player JS da 290 ms/frame contra 66,7 de presupuesto (cuello CPU),
mientras el mismo producto como mp4 de 4,1 MB *«reproduce muy bien»*
(DIAG-002/003, REGISTRO 2026-09-01). Encoder caro, TV que solo ejecuta: la
filosofía no cambió, cambió el músculo que ejecuta.

## Arranque post-compact — en este orden, sin leer de más

1. [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) — dónde quedó todo, próxima acción, bitácora.
2. [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md) — **solo la tarea a ejecutar** (fase H).
3. [`docs/ejecutados/`](docs/ejecutados/) — lo ya cumplido con su evidencia; consultar, no releer.
4. [`docs/historico/`](docs/historico/README.md) — diseños del paradigma JS anterior; solo si una tarea suspendida se retoma.
5. [`docs/MAPA-DEL-PROYECTO.md`](docs/MAPA-DEL-PROYECTO.md) / [`docs/ASCL-format-spec.md`](docs/ASCL-format-spec.md) — solo si falta orientación estructural o la tarea toca bytes del máster.

## Modelo de trabajo (acordado con el operador; heredado sin cambios 2026-09-01)

- **Esta máquina no tiene Python ni Node, a propósito.** Toda la regresión se
  valida en **GitHub Actions** (workflow `regression`) en cada push. Una tarea se
  cierra **solo con CI en verde**; si CI falla, se corrige hacia adelante.
- **Commits directos a `main`**, un commit por tarea, mensaje `<ID>: <título>`.
- **Remoto de trabajo: `origin` = `leoIglesias-hash/ASCILINE-hybrid`** (privado;
  los minutos de Actions se facturan al dueño y el Pro está ahí). El repo
  antecesor `ASCILINE-video` (en `leoIglesias-hash` y `tablerosapp-ctrl`) queda
  **congelado**; si el operador quiere espejo/destino final del híbrido, lo pide.
- Los videos de producto **no se commitean a `main`** (`.gitignore` lo impone).
  El clip HQ fuente vive en `inputs/TKN-2443-GANADOR- 15seg-.mp4` local y en la
  rama huérfana **`assets`** (migrada al repo nuevo).
- **Máster vigente** (receta S-4, 2026-08-31): workflow `encode` defaults +
  `format=v3` + `tile=sweep` + extra `--palette-refit 5 --near-lossless 8
  --cols 1280` → `.asclv` `dcd6afb6…1632a` (24.458.884 B, 35,02 dB, 1280×720
  @15). **Su emisión mp4**: mismo workflow con **`preview=true`** →
  `producto.mp4` 4.130.240 B (run 33532310754); vive local en `outputs/`
  (gitignored) — regenerable, nunca se supone.
- **Al cerrar cada etapa, levantar el player para el operador**: bajar el
  artifact del CI a `outputs/`, correr `tools/serve-local.ps1` (puerto 8123,
  `Cache-Control: no-store`, sirve `.mp4`) y avisarle que abra
  `http://localhost:8123/`.
- **Documentación siempre al día antes de cualquier compact.**

## Ayuda-memoria — no perder de vista nunca

1. **Retrocompatibilidad JS:** todo frontend en sintaxis **ES5.1 estricta**
   (gate `tests/test_frontend_compatibility.js`): sin `fetch`/`Promise`/`Worker`/
   `WASM`/`JSON`/arrow/`let`/`const`/template strings. Vale igual para el player
   híbrido nuevo.
2. **Dos capas, y solo dos (decisión del operador, 2026-09-01):** `<video>`
   hardware como base + **un** canvas de intervención encima que repinta solo la
   zona intervenida. Reemplaza al invariante de un-solo-layer del paradigma
   anterior. Jamás DOM overlay adicional ni un canvas por elemento. El canvas de
   intervención es **Canvas2D** (en la caja medida, WebGL no presenta).
3. **La optimización cara va offline:** el TV nunca cuantiza ni decide. La
   fluidez se compra en la **emisión** del mp4 (H-2), no degradando la imagen
   que el encoder ya decidió.
4. **Validar todo antes de mutar; corrupción = excepción tipada.** Aplica al
   máster y a todo parser nuevo (sidecar del híbrido incluido).
5. **Determinismo y medición:** mismo input → mismos bytes, también para el mp4
   emitido. Una mejora sin fila del REGISTRO no existe; byte-idéntico se
   verifica, no se supone. Las mediciones de la caja las firma **el operador**.
6. **Ningún buffer nuevo proporcional al frame por cuadro** en el loop estable
   de la capa de intervención.
7. **Canonicidad forzada del formato máster:** uvarint no canónico, padding ≠ 0
   u offsets no crecientes se **rechazan**. Nada de eso se relaja por el híbrido.
8. **Los valores manuales del operador prevalecen** sobre cualquier automatismo.
   **Resolución y fps son elegibles POR VIDEO, nunca fijados por receta** — vale
   también para la emisión del mp4.
9. **El player JS anterior se mantiene, no crece:** queda como reproductor de
   escritorio y banco de verificación del máster (las 4 páginas + `playloop.js`).
   Única deuda activa ahí: **W-26** (escape `?renderer=` en la raíz).

## Estado (resumen grueso — el detalle vive en RUNBOOK-ESTADO)

- **Heredado cerrado y verificado (paradigma anterior, F0-F9 + deploy):** no
  re-implementar; resúmenes en `docs/ejecutados/`, diseños en `docs/historico/`,
  porqués en el REGISTRO. Player JS EN PRODUCCIÓN en `https://iargen.com/player/`
  (R2 + Worker `asciline-player`; subidas con token efímero + `x-sha256`,
  siempre quemado después).
- **DIAG-002/003 cerradas con decisión (2026-09-01):** el diagnóstico completo
  de la TV box terminó en la adopción del híbrido y este repo. Cuadro de
  evidencia en el REGISTRO; herramientas que quedaron:
  `frontend/tv-video-test.html` y el diagnostic con sección Pantalla/escala.
- **En curso — fase H:** H-0 cerrada (este repo). Siguen **H-1**
  (`DISENO-HIBRIDO.md`, sin código) y **H-2** (investigación de
  reproducibilidad mp4: matriz de emisión H.264 medida en la caja con
  `frontend/tv-video-test.html`), paralelizables; **H-3** (player híbrido
  mínimo) solo con H-1 aprobada; **W-26** independiente. Externo: pedir a la
  app que el WebView reporte el panel real (hoy 3840×2160 sobre 1280×720).
- **Suspendidas** (recuperables de `docs/historico/` solo con decisión del
  operador): F10 (pérdida adaptativa — ojo: seguiría mejorando el mp4, que
  hereda los píxeles del máster), F11 (formato v4), F8, DIAG-001, opcionales.
