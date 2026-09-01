# ASCILINE-hybrid — guía de sesión (leer esto primero, siempre)

**Sucesor de `ASCILINE-video` desde el 2026-09-01, por decisión del operador.**

Construimos **un formato de video propio, códec-agnóstico, que se decide caro y
offline, se reproduce siempre por hardware, y se puede intervenir en vivo sin
re-codificar.** No es un player: es un **paquete + un contrato de reproducción**.

El encoder Python **offline** sigue decidiendo todo (paleta, trellis, look) y
emitiendo el `.ascl`/`.asclv` como **máster determinista**. Lo que cambió es el
transporte: al TV ya no viaja el `.asclv` para que un player JS lo decodifique;
viaja un paquete emitido desde ese máster cuyo video reproduce `<video>` con
decodificador de **hardware**, con la **intervención** (números, texto, logo,
canal en vivo) en un canvas encima — dos capas. Por qué: medido en la TV box
real, el player JS da 290 ms/cuadro contra 66,7 de presupuesto (cuello CPU),
mientras el mismo producto como mp4 de 4,1 MB *«reproduce muy bien»*
(DIAG-002/003, REGISTRO 2026-09-01).

**Encoder caro, decoder sin estrés.** La filosofía no cambió; cambió el músculo
que ejecuta: antes un intérprete JS, ahora un bloque de silicio.

## Arranque post-compact — en este orden, sin leer de más

1. [`docs/VISION-Y-OBJETIVOS.md`](docs/VISION-Y-OBJETIVOS.md) — **el norte**: qué
   construimos, de qué linaje sale cada pieza, invariantes y no-objetivos. Si se
   lee un solo documento de diseño, es este.
2. [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) — dónde quedó todo, próxima acción, bitácora.
3. [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md) — **solo la tarea a ejecutar** (fase H).
4. [`docs/EMISION-V0.md`](docs/EMISION-V0.md) — **el primer video**: qué le tomamos a cada códec y cuáles son las suposiciones, cada una con su refutación escrita.
5. [`docs/PLAN-DE-MEDICION.md`](docs/PLAN-DE-MEDICION.md) — el método: se mide **reproduciendo**, en varios aparatos, y el registro de aparatos.
6. [`docs/DISENO-FORMATO-ASCLH.md`](docs/DISENO-FORMATO-ASCLH.md) — el formato en obra, con la tabla de **decidido vs. gateado**.
7. [`docs/ejecutados/`](docs/ejecutados/) — lo ya cumplido con su evidencia; consultar, no releer.
8. [`docs/historico/`](docs/historico/README.md) — diseños del paradigma JS anterior; solo si una tarea suspendida se retoma.
9. [`docs/MAPA-DEL-PROYECTO.md`](docs/MAPA-DEL-PROYECTO.md) / [`docs/ASCL-format-spec.md`](docs/ASCL-format-spec.md) — solo si falta orientación estructural o la tarea toca bytes del máster.

## Modelo de trabajo (acordado con el operador; heredado sin cambios)

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
  @15). **Es el máster de entrada de toda la matriz de emisión (H-6).** Su
  emisión mp4 conocida: mismo workflow con **`preview=true`** → `producto.mp4`
  4.130.240 B (run 33532310754); vive local en `outputs/` (gitignored) —
  regenerable, nunca se supone.
- **Al cerrar cada etapa, levantar el player para el operador**: bajar el
  artifact del CI a `outputs/`, correr `tools/serve-local.ps1` (puerto 8123,
  `Cache-Control: no-store`, sirve `.mp4`) y avisarle que abra
  `http://localhost:8123/`.
- **Documentación siempre al día antes de cualquier compact.**

## Ayuda-memoria — no perder de vista nunca

1. **`<video>` es la única puerta al hardware.** Todo lo que emitamos termina en
   algo que `<video>` acepta **nativamente**. Nada se decodifica en CPU propia —
   ese camino ya se midió y se descartó. Si una idea no llega a `<video>`, no es
   un camino.
2. **La densidad decide el transporte.** Imagen densa a pantalla completa → va
   por el `<video>`. Contenido escaso (personaje, destello, números, ruleta) o
   reactivo a datos vivos → capa de intervención, cuyo costo es proporcional a su
   área, no a la pantalla.
3. **Pintar una vez, animar en el compositor.** Cero repintado de superficie
   completa por cuadro; cero mutación de DOM dentro del loop. **Presupuesto de
   capas: ≤1 `<video>` base, ≤1 canvas que repinta, ≤2 elementos que solo se
   transforman.** Todo dato vivo se dibuja **dentro** del canvas, nunca como
   nodos: los WebViews se degradan con la cantidad de DOM.
4. **Encoder caro, decoder sin estrés.** El TV nunca cuantiza ni decide. La
   fluidez se compra en la **emisión** (códec, fps por segmento, estructura), no
   degradando la imagen que el encoder ya decidió.
5. **Piezas intercambiables:** **1280×720 base fija** con **fps variable por
   segmento** (decisión del operador, 2026-09-01). Fijar la resolución es lo que
   permite que las piezas compartan cabecera y se concatenen sin re-codificar, y
   evita que el decodificador se reconfigure a mitad de stream. La densidad se
   sigue eligiendo por clip, pero **dentro** del paquete (vía Representations).
6. **Retrocompatibilidad JS:** todo frontend en sintaxis **ES5.1 estricta**
   (gate `tests/test_frontend_compatibility.js`): sin `fetch`/`Promise`/`Worker`/
   `WASM`/`JSON`/arrow/`let`/`const`/template strings. Las APIs nuevas que
   usamos (IndexedDB, MSE, Blob) son de **eventos**, no de promesas: entran sin
   romper el gate.
7. **Se supone explícito, se reproduce, y recién ahí se normaliza.** Arrancar
   suponiendo es el método (pack v0); lo prohibido es que una suposición entre a
   la spec sin haberse reproducido. Y **ningún aparato solo define el formato**:
   uno puede refutar, para consagrar hacen falta dos clases de aparato. Nada se
   estima: si no se midió, la celda queda vacía. **Lo que requiere pantalla lo
   firma el operador**, textual.
8. **Determinismo:** mismo máster + mismos parámetros → mismos bytes emitidos, en
   cualquier códec. Byte-idéntico se verifica, no se supone.
9. **Validar antes de mutar; corrupción = excepción tipada.** Y **canonicidad
   forzada del máster**: uvarint no canónico, padding ≠ 0 u offsets no crecientes
   se rechazan. Nada de eso se relaja por el formato nuevo.
10. **Los valores manuales del operador prevalecen** sobre cualquier automatismo.
    Y **el player JS anterior se mantiene, no crece**: queda como reproductor de
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
- **En curso — fase H.** H-0 cerrada (nace este repo). **H-1..H-3 reemplazadas**
  por el debate de dirección (el alcance pasó a «formato propio códec-agnóstico»)
  y **H-4/H-5 reemplazadas** la misma tarde por decisión del operador: la sonda
  sintética hubiera fijado el formato contra **una sola TV box**; se arranca
  **emitiendo**. IDs no reusables. Lo vivo, en orden: **H-9** pack v0
  (**próxima acción**), **H-10** reproducirlo en varios aparatos, **H-11**
  intervención encima o al lado, **H-6** matriz, **H-12** caché, **H-7** spec
  `SPEC-ASCLH.md`, **H-8** muxer ES5 + player. **W-26** independiente. Externo:
  pedir a la app que el WebView reporte el panel real (hoy 3840×2160 sobre
  1280×720).
- **Las suposiciones del pack v0 están escritas con su refutación** en
  [`docs/EMISION-V0.md`](docs/EMISION-V0.md) §4. Las dos grandes: si YouTube anda
  bien en la caja, esa caja tiene **VP9 por hardware** (VP9 sería su camino más
  rodado, no el exótico); y la pieza **H.264 Main es el detector de hardware vs.
  software** — si la más comprimida no cuesta más, el bitstream no es el cuello y
  toda la matriz se reorienta a cantidad de cuadros y ancho de banda.
- **Suspendidas** (recuperables de `docs/historico/` solo con decisión del
  operador): F10 (pérdida adaptativa — ojo: seguiría mejorando el producto, que
  hereda los píxeles del máster), F11 (formato v4), F8, DIAG-001, opcionales.
