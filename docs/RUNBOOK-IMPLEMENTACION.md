# Runbook de implementación — formato propio híbrido

Estado: **nace el 2026-09-01 con ASCILINE-hybrid; alcance ampliado el mismo día
tras el debate de dirección con el operador.** Este archivo contiene SOLO las
reglas de ejecución y las tareas del paradigma nuevo.

El runbook del paradigma anterior (100 % JS: F10, F11, F8, DIAG-001 y opcionales,
todas **suspendidas**) está archivado verbatim en
[`historico/RUNBOOK-IMPLEMENTACION-asclv-js.md`](historico/RUNBOOK-IMPLEMENTACION-asclv-js.md);
si alguna se retoma, vuelve de ahí con decisión del operador, no se reescribe.

**Antes de ejecutar cualquier tarea de acá, leer
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md)** — es el norte del proyecto y
lo que evita que una sesión post-compact se desvíe.

## 0. Reglas de ejecución (heredadas, siguen todas vigentes)

1. **Commits directos a `main`, un commit por tarea.** Mensaje: `<ID>: <título>`.
2. **Regresión antes de cerrar.** La máquina de trabajo no tiene Python ni Node
   **a propósito**: la regresión completa corre en GitHub Actions (workflow
   `regression`) en cada push. Una tarea se cierra solo con ese CI en verde.
3. **Fila de registro obligatoria** para toda tarea que cambie bytes o fluidez
   medible. La medición en aparatos la hace el operador con las páginas de
   diagnóstico; su veredicto se transcribe textual.
4. **Una tarea no empieza si su precondición no está cerrada.**
5. **Ninguna tarea se cierra «porque compila».** El criterio de cierre está
   escrito y es verificable.
6. **Todo test nuevo se cablea en `tests/run_all.py` en el mismo commit.**
7. **Procedencia por sesión** en `RUNBOOK-ESTADO.md`.
8. **Nada se normaliza en el formato sin una medición que lo sostenga**
   (regla nueva, 2026-09-01; ver [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §6).

## 1. El paradigma (decisión del operador, 2026-09-01)

Resumen ejecutable; el desarrollo está en
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md).

- **Construimos un formato propio, códec-agnóstico**, que se decide caro y
  offline y se reproduce **siempre por hardware**, y que se puede **intervenir en
  vivo sin re-codificar**. No es un player: es un paquete + un contrato de
  reproducción.
- **`<video>` es la única puerta al hardware**: todo lo que emitamos termina en
  algo que `<video>` acepta nativamente. Nada se decodifica en CPU propia.
- **Composición de linajes:** de **VP9/AV1** la compresión y las primitivas
  (golden frames, tiles, alfa en WebM); de **DASH** el modelo de datos y la
  intervención estructural (Periods, AdaptationSets, Representations); de **HLS**
  el piso de compatibilidad probado; de **ASCILINE** el máster determinista, la
  intervención matricial y la disciplina de medición.
- **Encoder caro, decoder sin estrés.** La filosofía madre no cambió; cambió
  quién ejecuta: antes un intérprete JS, ahora un bloque de silicio.
- **Base 1280×720 con fps variable** (operador): fijar la resolución es lo que
  vuelve intercambiables a las piezas y evita que el decodificador se reconfigure.
- **Dos capas:** `<video>` base + **un** canvas de intervención. Reemplaza al
  invariante de un-solo-layer del paradigma anterior.
- **El player JS no muere:** queda como reproductor de escritorio y banco de
  verificación del máster. Se mantiene, no crece.
- Evidencia que sostiene todo: REGISTRO, DIAG-002/003 (2026-09-01) — en la caja
  real el JS da 290 ms/cuadro contra 66,7 de presupuesto y el `producto.mp4`
  (4,1 MB) *«reproduce muy bien»*.

## 2. Fase H — formato híbrido

**Orden: H-4 → H-5 → H-6 → H-7 → H-8.** Las tres primeras son medición y
habilitan a las dos últimas; **nada de H-7 se escribe como norma sin la tabla de
H-4/H-5, y nada de H-8 sin H-7 aprobado por el operador.** W-26 es independiente
y se puede tomar en cualquier momento.

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **H-0** | repo, `docs/` | **CERRADA 2026-09-01** (`8dae1e5`). Crear `ASCILINE-hybrid` (clon con historia completa, main + assets), mover a `docs/historico/` los diseños del paradigma JS, reescribir CLAUDE.md/runbooks/índices | repo en `leoIglesias-hash/ASCILINE-hybrid` con CI verde ✔ |
| **H-1..H-3** | — | **REEMPLAZADAS** el 2026-09-01 por el debate de dirección (mismo día, después de H-0). Eran: diseño del player híbrido, investigación de emisión H.264, player mínimo. Su contenido está absorbido y ampliado en H-4..H-8: el alcance pasó de «un player híbrido con mp4» a «un formato propio códec-agnóstico». **No se reusan estos IDs** | — |
| **H-4** | `frontend/probe.html` (nuevo) | **sonda de capacidades**: responder la lista cerrada de [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §2 (códecs, VP9 por hardware, alfa WebM, MSE, `blob:`, IndexedDB, instrumentos de medición, videos simultáneos, canvas encima, panel real, HLS/DASH nativo). Sin dependencias, ES5, autocontenida para poder abrirla en cualquier aparato | tabla de §5 del plan llena para la TV box **y** 2-3 aparatos más del operador; volcada al REGISTRO |
| **H-5** | `frontend/tv-video-test.html` (crece) | **banco de reproducción**: medir con `getVideoPlaybackQuality()` cuadros caídos/totales, tiempo al primer cuadro, deriva, atascos, costura de bucle — y lo mismo **con la capa de intervención activa**. Números, no impresiones | el banco corre en la caja y devuelve las métricas de [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §3 sobre una variante conocida; veredicto del operador transcripto |
| **H-6** | workflow `encode` + `tools/` | **matriz de emisión multi-códec** desde el máster vigente `dcd6afb6…1632a`: barrer los ejes de [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §4 (códec, fps fijo vs. variable por segmento, bitrate, estructura, zonas estáticas, paleta consciente del 4:2:0). Variantes reproducibles y con hash | tabla de variantes en el REGISTRO con la medición del aparato por fila; **receta elegida por perfil de dispositivo** (no una sola global), firmada por el operador |
| **H-7** | `docs/SPEC-ASCLH.md` (nuevo) | **spec normativa del formato**: layout binario del contenedor, manifiesto, direccionamiento de segmentos, sprites, cues, huecos, y el mapa perfil → camino de runtime. Cierra las filas «gateadas» de [`DISENO-FORMATO-ASCLH.md`](DISENO-FORMATO-ASCLH.md) §10 con lo que devolvieron H-4..H-6. Sin código | spec aprobada por el operador; toda decisión trazable a una fila medida |
| **H-8** | `frontend/` + `backend/` | **muxer ES5 + player híbrido mínimo**: emisor del paquete offline, muxer que arma la salida en el aparato (camino A y/o B según H-4), `<video>` + canvas de intervención reusando `overlay.js`/`textlayer.js`/`slots.js`/`datachannel.js`. Incluye el caso «cambiar solo la música» | reproduce en la caja real con intervención activa y con la fluidez del carril video (veredicto del operador); gate ES5 verde; depende de **H-7** |
| **W-26** | `frontend/live-player.html` | (heredada, independiente) la raíz publicada elige WebGL sin salida: aceptar `?renderer=` como las demás páginas y decidir el default para WebViews de TV box | la raíz respeta `?renderer=canvas2d`; gate ES5 verde |

**Pendiente externo (no es tarea nuestra):** pedirle a la app de la caja que el
WebView reporte el tamaño real del panel — hoy da 3840×2160 sobre un panel de
1280×720 (9× de píxeles regalados al compositor, medido en DIAG-003). Beneficia
también al carril `<video>`.

**Anotado sin tarea** (en [`DISENO-FORMATO-ASCLH.md`](DISENO-FORMATO-ASCLH.md)
§11): nivel N4 de intervención (intercambio sub-cuadro por tiles/slices), cuadros
sostenidos escritos a mano, golden frames de VP9, composición offline de escenas,
y la nota de que F10 —suspendida— seguiría mejorando el producto porque el video
hereda los píxeles del máster.

## 3. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa (CI en verde sobre su push);
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si cambió bytes o fluidez, su fila está en el REGISTRO;
4. el commit lleva su ID;
5. si tocó el frontend, el gate ES5 pasa;
6. lo que requiere pantalla lo firma **el operador**, nadie más;
7. si es una tarea de medición, **ninguna celda quedó estimada**: o está medida o
   está vacía.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por
tarea. Ese archivo —no la memoria de nadie— es lo que le dice a la próxima
sesión dónde quedó todo.
