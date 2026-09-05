# Propuestas — el espacio para pensar el formato entre varios

> Este archivo existe para que cualquiera pueda **proponer una idea, verla
> discutida y verla medida**. El proyecto avanza por evidencia, no por
> opinión: una propuesta se adopta cuando tiene **una fila** —bytes, cuadros
> caídos, milisegundos de arranque, SSIM— y un aparato o el ojo del operador la
> firmó. Hasta entonces es una apuesta escrita, y eso también vale: v0 nació
> así (`docs/EMISION-V0.md` §1).
>
> Cómo se decide en este proyecto: [`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md)
> §3 (gates, qué se optimiza, «ningún aparato solo define el formato»). Qué es
> el formato: [`docs/VISION-Y-OBJETIVOS.md`](docs/VISION-Y-OBJETIVOS.md).

## Cómo proponer

El repositorio es **público de solo lectura**: se puede leer todo, clonar todo
y correr todo, pero nadie de afuera escribe en él. Las ideas entran por
**issues**; este archivo lo mantiene el equipo del proyecto.

1. **Abrí un issue** con el título `Propuesta: <título corto>` y el cuerpo de
   la plantilla de abajo (los seis campos). No hace falta código: hace falta el
   problema, la idea y **cómo se mediría**.
2. Si la idea tiene una pregunta medible, el equipo la copia acá con su número
   (`P-0nn`), en estado `🟡 propuesta`, con el enlace al issue. La discusión
   sigue en el issue.
3. Cuando hay acuerdo sobre **cómo se mediría**, pasa a `🔵 en estudio` y se
   le asigna una tarea (`H-nn`) en
   [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md).
4. Con la fila medida, pasa a `🟢 adoptada` (y entra al diseño o a la spec) o a
   `⚪ descartada` **con el porqué escrito**. Nada se borra: una idea descartada
   con su evidencia vale tanto como una adoptada.

Si preferís mandar código, podés hacerlo desde un *fork* como pull request;
se lee como una propuesta más —con la misma plantilla en la descripción— y
no se integra sin su fila. Lo que necesita pantalla (una TV, una caja) lo
firma el operador del proyecto, que es quien tiene los aparatos.

**Lo que hace buena a una propuesta** (lo que se le va a pedir):

| Campo | Qué se espera |
|---|---|
| **Problema** | qué duele hoy, con número si lo hay (bytes, ms, cuadros) |
| **Idea** | qué se haría, en dos o tres frases |
| **Qué compra** | bytes · arranque · residencia · look · intervención · robustez |
| **Qué cuesta** | tiempo de emisión, complejidad del runtime, riesgo en aparatos viejos |
| **Cómo se mide** | qué fila lo prueba, en qué aparato, con qué gate de §3.1 |
| **Qué la refutaría** | el resultado que la tira abajo, escrito **antes** de medir |

**Reglas de la casa que ninguna propuesta puede saltear**

- El frontend es **ES5.1 estricto** (`tests/test_frontend_compatibility.js`):
  sin `fetch`, `Promise`, `JSON`, arrow, `let/const`, template strings. El
  parque tiene WebViews de Chromium 70 y eso no es negociable.
- **`<video>` es la única puerta al hardware.** El player 100 % JS ya se midió
  en la caja y no llega (DIAG-003); no se vuelve ahí.
- **Determinismo:** mismo máster → mismos bytes, en cualquier máquina. Una
  pieza que cambia de huella sin cambiar de contenido rompe la residencia.
- **Todo lo caro se paga offline.** El aparato solo ejecuta.
- **La caja (Chromium 70, decodificador hardware) es la clase principal;** el
  Smart TV es la segunda. Lo que la caja refuta, cae; lo que solo el Smart TV
  consagra, es mejora opcional por aparato.

## Plantilla

```
### P-0nn · <título corto> · 🟡 propuesta · <fecha> · <quién>

- **Problema:**
- **Idea:**
- **Qué compra:**
- **Qué cuesta:**
- **Cómo se mide:**
- **Qué la refutaría:**
- **Discusión / estado:** (se completa en el PR)
```

Estados: `🟡 propuesta` → `🔵 en estudio (H-nn)` → `🟢 adoptada` | `⚪ descartada (porqué)`.

---

## Propuestas abiertas

Las primeras salen de lo que el proyecto ya tiene anotado como pregunta y no
como tarea. Están acá para que el formato se vea en uso y para que alguien las
tome.

### P-001 · Tres planos de video a la vez · 🔵 en estudio · 2026-09-04 · operador + sesión

- **Problema:** con dos planos (`<video>` base + `<video>` con alfa) la caja va
  perfecta; con tres, el contador de la caja marca 17/155 (11 %) pero **ese
  contador ya demostró que miente** y el ojo del operador dice que se ven
  perfecto. No se sabe si el 11 % es real.
- **Idea:** arbitrar en el **Smart TV** (Chrome 142, `getVideoPlaybackQuality`
  de verdad): tecla `1` y después `95`.
- **Qué compra:** poder hacer que **dos efectos** sean video a la vez (papelitos
  + personaje), sin canvas.
- **Qué cuesta:** nada de emisión; solo una foto.
- **Cómo se mide:** fila `entera:todo` en el Smart TV, gate caídos ≤ 3 %.
- **Qué la refutaría:** el Smart TV también cae ≥ 3 % → el presupuesto de
  composición queda en dos planos + canvas.
- **Discusión / estado:** pedido al operador, no bloquea nada.

### P-002 · Sincronía de cuadro exacta con `requestVideoFrameCallback` · 🟡 propuesta · 2026-09-04 · sesión

- **Problema:** la intervención en el canvas se sincroniza por `currentTime`
  en un loop propio (±1 cuadro). En el Smart TV existe `rvfc` (`rvfc si`).
- **Idea:** cuando `rvfc` existe, dibujar la capa desde el callback de cuadro;
  cuando no, el loop de siempre. Mejora **opcional por aparato**, nunca
  requisito.
- **Qué compra:** texto y logo clavados al cuadro en los aparatos nuevos.
- **Qué cuesta:** dos caminos en `overlay.js`; el gate ES5 obliga a detectar
  la función sin suponerla.
- **Cómo se mide:** deriva capa/video en ms, en las dos clases de aparato.
- **Qué la refutaría:** que el callback cueste cuadros caídos en el Smart TV.

### P-003 · Paletas por región en el máster · 🟡 propuesta · 2026-08-31 · anotada en la Instancia 031

- **Problema:** el máster usa 256 colores para todo el cuadro; en escenas con
  dos zonas de color muy distintas, la paleta se reparte y aparece banding.
- **Idea:** paleta por tile o por región (E-25 tiene el análisis de saturación
  de las 256 como *gate*). El `.vgen` hereda los píxeles: mejoraría el look
  de cada pieza sin tocar el códec.
- **Qué compra:** look. **Qué cuesta:** encoder Python más caro (se paga una
  vez), formato v4 del máster.
- **Cómo se mide:** PSNR/SSIM contra la fuente en `tools/bench_ref.py`, y el
  ojo del operador en el degradé del huevo.
- **Qué la refutaría:** que las 256 no estén saturadas (E-25) — entonces el
  banding viene de otro lado (DIAG-001).

### P-004 · Cadencia variable para clips con quietud real · ⚪ descartada para el máster actual · 2026-09-05 · H-6

- **Problema:** S6 suponía que omitir cuadros iguales ahorra bytes.
- **Medido (H-6, matriz `cadencia`):** el máster de producto tiene **1 cuadro
  exactamente igual** al anterior de 231, y 4 «casi iguales»; forzar cuadros
  clave por tiempo con cadencia variable **subió** los bytes de VP9 un 36 %.
- **Estado:** descartada **para este máster**. Queda abierta para clips con
  quietud real (tableros, carteles): ahí la matriz se corre de nuevo, porque
  **resolución, fps y cadencia se eligen por video, no por receta**.

### P-005 · Audio por MSE junto con el video · 🟡 propuesta · 2026-09-05 · H-6

- **Problema:** S11 (VP9 por MSE) se mide **solo video**; una pieza con audio
  propio que entre por MSE necesita el audio en el mismo `SourceBuffer`
  (`vp9,opus`) o en uno aparte.
- **Idea:** emitir los segmentos WebM con audio muxeado y probar
  `isTypeSupported('video/webm; codecs="vp9,opus"')` en la caja.
- **Qué compra:** el camino B (MSE) completo para piezas habladas.
- **Cómo se mide:** fila `mse:vp9+opus`, gates de arranque y atascos.
- **Qué la refutaría:** que la caja no acepte el MIME con dos códecs en un
  buffer → el audio propio va solo por pieza entera (camino A/C).

### P-006 · Audio sin recodificar: el mp3 del máster tal cual dentro del mp4 · 🟡 propuesta · 2026-09-05 · H-6

- **Problema:** los encoders de audio (AAC, Opus) son de punto flotante y no
  tienen `cpu-independent`: dos máquinas pueden emitir bytes distintos, y la
  residencia pinea por contenido.
- **Idea:** en mp4, muxear el **mp3 del máster byte a byte** (`-c:a copy`,
  `mp4a.6B`) en vez de AAC. Determinista por construcción.
- **Qué compra:** determinismo total. **Qué cuesta:** depende de que el
  demuxer del WebView acepte MP3 en MP4 (Chromium sí; hay que probar la caja).
- **Cómo se mide:** la comparación de dos pasadas del workflow `emitir-v1`
  (si AAC ya sale idéntico, la propuesta no hace falta) y una fila en la caja.
- **Qué la refutaría:** `canPlayType('video/mp4; codecs="avc1…, mp4a.6B"')`
  vacío en la caja.

### P-007 · La matriz como herramienta por video, no como receta · 🟡 propuesta · 2026-09-05 · H-6

- **Problema:** la matriz H-6 se corrió sobre **un** máster; la receta que
  salió (VP9 crf 38, H.264 High con B) es de ese clip.
- **Idea:** que `emitir-v1` corra la matriz reducida (crf ±3, cadencia) sobre
  cada máster nuevo y elija por SSIM contra la tolerancia, dejando la fila en
  el manifiesto. La regla 9 del proyecto ya lo dice para resolución y fps.
- **Qué compra:** bytes por clip sin intervención humana; el look lo sigue
  firmando el operador.
- **Qué cuesta:** ~10 minutos de runner por máster.
- **Qué la refutaría:** que la elección automática elija un crf que el
  operador rechace a ojo dos veces seguidas.

---

## Adoptadas

*(vacío — la primera que llegue con su fila se muda acá con el enlace a su tarea)*

## Descartadas

- **P-004** (cadencia variable) — para el máster actual; ver arriba.
