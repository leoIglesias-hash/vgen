# Runbook de implementación — carril híbrido (mp4 + intervención)

Estado: **nace el 2026-09-01 con ASCILINE-hybrid.** Este archivo contiene SOLO las
reglas de ejecución y las tareas del paradigma nuevo. El runbook del paradigma
anterior (100 % JS: F10, F11, F8, DIAG-001 y opcionales, todas **suspendidas**)
está archivado verbatim en
[`historico/RUNBOOK-IMPLEMENTACION-asclv-js.md`](historico/RUNBOOK-IMPLEMENTACION-asclv-js.md);
si alguna se retoma, vuelve de ahí con decisión del operador, no se reescribe.

## 0. Reglas de ejecución (heredadas, siguen todas vigentes)

1. **Commits directos a `main`, un commit por tarea.** Mensaje: `<ID>: <título>`.
2. **Regresión antes de cerrar.** La máquina de trabajo no tiene Python ni Node
   **a propósito**: la regresión completa corre en GitHub Actions (workflow
   `regression`) en cada push. Una tarea se cierra solo con ese CI en verde.
3. **Fila de registro obligatoria** para toda tarea que cambie bytes o fluidez
   medible. La medición en la caja la hace el operador con las páginas de
   diagnóstico; su veredicto se transcribe textual.
4. **Una tarea no empieza si su precondición no está cerrada.**
5. **Ninguna tarea se cierra «porque compila».** El criterio de cierre está
   escrito y es verificable.
6. **Todo test nuevo se cablea en `tests/run_all.py` en el mismo commit.**
7. **Procedencia por sesión** en `RUNBOOK-ESTADO.md`.

## 1. El paradigma (decisión del operador, 2026-09-01)

- **El encoder no cambia de filosofía:** todo lo caro se decide offline. El
  `.asclv` sigue siendo el **máster** determinista (paleta, trellis, look); el
  **mp4 de distribución se emite desde él** (`ascl_decode.py --mp4`, hoy vía
  workflow `encode` con `preview=true`). El TV recibe H.264 y lo decodifica por
  **hardware** con `<video>`.
- **Dos capas:** el `<video>` es la base; la **intervención** (números, texto,
  logo, canal de datos en vivo) vive en un canvas encima que repinta **solo la
  zona intervenida**. Esto reemplaza al invariante de un-solo-layer del paradigma
  anterior, por decisión explícita del operador.
- **El player JS no muere:** queda como reproductor de escritorio/moderno y como
  banco de verificación del máster. No se le agregan features; se mantiene.
- Evidencia que sostiene todo esto: REGISTRO, DIAG-002/003 (2026-09-01) — en la
  caja real el JS da 290 ms/frame contra 66,7 de presupuesto y el
  `producto.mp4` (4,1 MB) *«reproduce muy bien»*.

## 2. Fase H — híbrido

Orden: H-0 → H-1 y H-2 (paralelizables) → H-3. Nada de H-3 se escribe sin H-1
aprobado por el operador.

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **H-0** | repo, `docs/` | crear `ASCILINE-hybrid` (clon con historia completa de ASCILINE-video, main + assets), mover a `docs/historico/` los diseños del paradigma JS, reescribir CLAUDE.md/runbooks/índices para el paradigma nuevo | repo en `leoIglesias-hash/ASCILINE-hybrid` con CI verde sobre este commit |
| **H-1** | `docs/DISENO-HIBRIDO.md` (nuevo) | diseño formal del player híbrido: (a) sincronía intervención↔video — el reloj pasa a ser `video.currentTime`, mapear frame lógico del sidecar a tiempo; (b) qué necesita la capa de intervención del máster (sidecar de slots/geometría hoy embebido en el envelope v3 — cómo viaja si el TV ya no descarga el `.asclv`); (c) distribución: CACHE-001 por contenido aplicado al mp4 (`producto.<sha12>.mp4` + puntero); (d) contrato de compatibilidad ES5 del nuevo player; (e) qué se degrada si el WebView no tiene `<video>` H.264 (¿fallback al player JS?) | documento aprobado por el operador; sin código |
| **H-2** | investigación + `tools/`, workflow `encode` | **investigación de reproducibilidad mp4**: qué parámetros de emisión H.264 (bitrate/CRF, profile/level, GOP/keyframes, two-pass, tamaño) dan la mejor fluidez en las cajas reales sin perder el look decidido por el encoder. Generar una matriz de variantes desde el máster vigente `dcd6afb6…1632a`, medirlas con `frontend/tv-video-test.html` en la caja (fps de decode, caídos, atascos, deriva) y con veredicto visual del operador | tabla de variantes en el REGISTRO con la medición de la caja por fila; receta de emisión elegida por el operador |
| **H-3** | `frontend/` (página nueva) | player híbrido mínimo: `<video>` con el mp4 de producto + canvas de intervención encima (reusa `overlay.js`/`textlayer.js`/`slots.js` — texto nativo, imagen, datachannel), sincronizado según H-1. ES5, gate de compatibilidad incluido | reproduce en la caja real con intervención activa y fluidez del carril video (veredicto del operador); depende de **H-1 cerrada** |
| **W-26** | `frontend/live-player.html` | (heredada, independiente del híbrido) la raíz publicada elige WebGL sin salida: aceptar `?renderer=` como las demás páginas y decidir el default para WebViews de TV box (en la caja medida, WebGL «dibuja» pero no presenta) | la raíz respeta `?renderer=canvas2d`; gate ES5 verde |

**Pendiente externo (no es tarea nuestra):** pedirle a la app de la caja que el
WebView reporte el tamaño real del panel — hoy da 3840×2160 sobre un panel de
1280×720 (9× de píxeles regalados al compositor, medido en DIAG-003). Beneficia
también al carril `<video>`.

## 3. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa (CI en verde sobre su push);
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si cambió bytes o fluidez, su fila está en el REGISTRO;
4. el commit lleva su ID;
5. si tocó el frontend, el gate ES5 pasa;
6. lo que requiere pantalla lo firma **el operador**, nadie más.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por
tarea. Ese archivo —no la memoria de nadie— es lo que le dice a la próxima
sesión dónde quedó todo.
