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
3. [`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md) — **el rumbo**: evidencia medida, caminos de runtime, gates numéricos, orden de tareas y decisiones pendientes del operador. Vigente desde el primer reporte de aparato (2026-09-01).
4. [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md) — **solo la tarea a ejecutar** (fase H).
5. [`docs/EMISION-V0.md`](docs/EMISION-V0.md) — **el primer video**: qué le tomamos a cada códec y cuáles son las suposiciones, cada una con su refutación escrita y su veredicto por aparato (§4.b/§4.c).
6. [`docs/PLAN-DE-MEDICION.md`](docs/PLAN-DE-MEDICION.md) — el método: se mide **reproduciendo**, en varios aparatos, y el registro de aparatos.
7. [`docs/DISENO-FORMATO-VGEN.md`](docs/DISENO-FORMATO-VGEN.md) — el formato en obra, con la tabla de **decidido vs. gateado**.
8. [`docs/ejecutados/`](docs/ejecutados/) — lo ya cumplido con su evidencia; consultar, no releer.
9. [`docs/historico/`](docs/historico/README.md) — diseños del paradigma JS anterior; solo si una tarea suspendida se retoma.
10. [`docs/MAPA-DEL-PROYECTO.md`](docs/MAPA-DEL-PROYECTO.md) / [`docs/ASCL-format-spec.md`](docs/ASCL-format-spec.md) — solo si falta orientación estructural o la tarea toca bytes del máster.

> ## ▶ Próxima acción: **P-008 (encoder portátil) en ejecución: leer el gate del workflow `portable`**; después, más ideas con el operador; H-24 / radio / H-7 / H-8 en la cola
>
> **2026-09-06 (tarde) — P-008 EJECUTADA hasta el CI** (operador: *«mejor
> vamos directo al P-008»*): `tools/portable/` + workflow **`portable`**
> (arma `vgen-portable/` en Windows: Python embebido + ffmpeg estático + el
> mismo `backend/`/`tools/`, artifact 90 días; **gate** = emite el pack v1
> con el bundle bajo PowerShell 5.1 y con Linux y compara SHA-256, el CI
> manda) + `tests/test_portable_bundle.py`. Nada se instala en la máquina.
> Detalle: [`docs/ENCODER-PORTATIL.md`](docs/ENCODER-PORTATIL.md) §6-7.
>
> **2026-09-06 — H-23 APARCADA:** con `reloj raf` la caja la vio *«un poco
> más trabada todavía… es algo de la capacidad del TV box»*. Lo que cuesta
> es presentar el canvas a 15/s encima de dos videos en esa GPU.
> **🔴 NO se reemplaza por un tercer video** (H-25 RECHAZADA por el
> operador): el tercer elemento es **interactivo** —la ruleta— y un video es
> contenido cerrado, no responde. **Regla: la interacción vive en la capa;
> nunca se reemplaza por una pieza de video.** Los videos (loop, publicidad,
> incentivador) son contenido; la capa es donde el aparato responde. Se
> retoma cuando el operador lo pida (ideas anotadas en REGISTRO 2026-09-06,
> sin tarea). Decisión: **«trabajemos en otras cosas»** → H-24 → radio →
> H-7 → H-8 → P-008.
>
> **Turno nocturno del 2026-09-05:** **H-8a EJECUTADA hasta la pantalla** —
> `frontend/producto.html`, la forma del producto entera desde la caché del
> aparato (loop por **anillo MSE** `sequence`, publicidad que reemplaza y
> vuelve, incentivador con alfa encima, radio en rampa, capa por papel, teclas
> de **una cifra**, reporte a dos columnas), con `GUION.tsv`, `ring()` en
> `vgenfeed.js` y la residencia **H-15** en `vgencache.js`; CI verde y
> **publicada en `v0/`** (tecla `77` desde `v0/`, `7` desde el lanzador).
> **H-23 (2026-09-05, al volver el operador):** la prueba que faltaba — la
> **imagen girando** (`logo.png`, `drawImage` rotado) encima del incentivador
> con alfa: la tecla `7` **cicla** números → números + imagen → apagada, con el
> costo por pintada en el reporte (PC: 0,20 ms med / 2,2 max a 1280×720).
> Publicada. **Foto de la caja del 2026-09-05 (REGISTRO «la foto de la
> caja»): H-8a se sostiene** (anillo 8 vueltas, 0 atascos, 3/1870 caídos;
> `leidas 5, guardadas 0`), v1 VP9 «joya», incentivador 627/684 ms (el
> operador lo ve lento → propuesta H-24: efecto armado), radio pide gesto.
> **H-23 quedó sin prender**: es `7` dos veces DENTRO del producto, luego `4`.
> **Foto 4 (con `7` `7`): «se traba al girar, de eso no hay duda»** — pintada
> 1,67 ms (barata) pero **206 ticks tardíos, gap 562 ms**, y la capa cuesta
> caídos (loop 1,5 %, incentivador 7,5 %). → **H-23c publicada: la capa en el
> vsync** (`requestAnimationFrame` 1 de 4; `?cada=2`, `?capak=0.5`,
> `?reloj=timeout`). **Con `reloj raf` siguió trabada (2026-09-06) → H-23
> aparcada; NO se reemplaza por video (la ruleta es interacción).**
> **H-7 es BORRADOR 0.1** ([`docs/SPEC-VGEN.md`](docs/SPEC-VGEN.md)): describe
> lo que el prototipo ejecuta, marca ⏳ lo no reproducido y pide la firma del
> operador con la lista de §12. **El encoder quedó evaluado, no hecho**
> ([`docs/ENCODER-PORTATIL.md`](docs/ENCODER-PORTATIL.md), P-008). Manual del
> producto en [`docs/MANUAL-TECLAS-V0.md`](docs/MANUAL-TECLAS-V0.md) «El
> producto». Detalle: REGISTRO «turno nocturno» y
> [`RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) §Próxima acción.
>
> **H-6 EJECUTADA el 2026-09-05** hasta la pantalla (matriz de 28 variantes +
> **emisión v1 con audio**, publicada en `v0/`, teclas `72`/`74`/`75`/`76`;
> [`docs/EMISION-V1.md`](docs/EMISION-V1.md)). Falta la **foto** de la caja y
> del Smart TV (`76` + `95`) y el ojo del operador sobre `v1-vp9` (crf 38) y
> `v1-h264` (High con B): las dos están **al borde** de la tolerancia de look
> a propósito y el escalón anterior ya está medido. Detalle en
> [`RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) §Próxima acción.
>
> **El repo se llama `vgen` desde el 2026-09-05** (`leoIglesias-hash/vgen`;
> la carpeta local sigue siendo `Escritorio\ASCILINE-hybrid`) y es **público
> de solo lectura**: las ideas de afuera entran por *issue* y viven en
> [`PROPUESTAS.md`](PROPUESTAS.md). Nadie de afuera escribe; lo que necesita
> pantalla lo firma el operador.
>
> **🔴 Al leer material escrito la mañana del 2026-09-04:** la regla «el
> presupuesto de composición es DOS planos, no tres» **fue RETIRADA esa misma
> noche**. **Los tres planos están habilitados** (video base + pieza alfa +
> canvas): el contador de la caja está desacreditado y el ojo del operador firmó
> que se ven perfecto. REGISTRO, entrada «el contador dice 11 % y el ojo dice
> perfecto».

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
10. **Las páginas se usan con un CONTROL REMOTO, no con un mouse.** En un WebView
    de TV el click exige mover un puntero emulado y el scroll se hace con
    flechas, así que: **cada acción tiene una tecla numérica**, **todo entra en
    una sola pantalla** (`overflow: hidden`, geometría calculada en JS — nada de
    `object-fit`, que no existe en WebViews viejos) y **nada crece hacia abajo**
    (un segundo `<video>` ya empujó una vez la tabla fuera de pantalla). El
    reporte se lee a pantalla completa porque en una TV **no se puede copiar
    texto**: se fotografía. La leyenda de teclas es además el botón táctil, para
    el celular.
11. **Los valores manuales del operador prevalecen** sobre cualquier automatismo.
    Y **el player JS anterior se mantiene, no crece**: queda como reproductor de
    escritorio y banco de verificación del máster (las 4 páginas + `playloop.js`).
    W-26 (escape `?renderer=canvas2d`) **cerrada en código** el 2026-09-02;
    el operador decidió el 2026-09-04 **terminarla**: auditar y republicar la
    raíz (W-26b).

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
- **En curso — fase H.** H-0 cerrada (nace este repo). **H-1..H-5 REEMPLAZADAS**
  (H-1..H-3 por el debate de alcance; H-4/H-5 porque una sonda sintética habría
  fijado el formato contra **una sola TV box** — se arranca **emitiendo**). IDs
  no reusables. **H-9 CERRADA 2026-09-01**: el pack v0 existe, está medido en
  bytes y publicado (resumen:
  [`docs/ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md`](docs/ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md)).
  **H-10 tiene la TV box medida (2026-09-01)** — reporte transcripto en el
  REGISTRO — y queda abierta para las otras clases o la decisión manual del
  operador. Lo vivo, en orden (rumbo completo en
  [`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md)):
  **H-13 CERRADA 2026-09-01 noche** (`frontend/vgenfeed.js` + teclas
  `96`/`97`/`98`/`8`/`99`; la caja dijo: MSE sí —2.033 ms, 0 atascos—, Blob
  `init+16` = archivo, intercambio de orden solo por MSE `sequence`, bucle por
  `loop` refutado, cambio a demanda 305 ms a VP9 y >1 s a Baseline → muxer A =
  concatenación, B = MSE `sequence`; REGISTRO «H-13: reporte de la caja»),
  **H-11 CERRADA 2026-09-04: ENCIMA** (0/155 caídos con canvas a 15 fps) y
  **H-12 CERRADA en lo que decide** (persiste al cierre de la app, cuota
  225 MB, 25 MB entran).

  **La cola acordada el 2026-09-04 está TERMINADA en código y publicada.** Las
  cinco, en orden:

  1. **H-14b** — `cpu-independent=1` en la receta de x264, pack re-emitido y
     **54 keys de `v0/` republicadas**. Las dos piezas H.264 dan el mismo
     archivo en **cuatro CPUs** de runner y las dos VP9 salieron byte-idénticas
     a las del 09-01 → **invariante 7 saldado**. CERRADA.
  2. **H-12b** — el techo se mide **sumando tandas de 5 MB** (antes 50 MB de
     una vez cerraban la app), la cuota declarada se reporta primero, `83`
     arranca VP9 en bucle y los caídos no pueden ser negativos.
  3. **H-16** — **Hobo por defecto** en la capa (detección midiendo `MMMMM`
     contra `iiiii`), página en tres columnas con la tabla alta, **13 teclas a
     la vista** y el resto en [`docs/MANUAL-TECLAS-V0.md`](docs/MANUAL-TECLAS-V0.md);
     el `1` corre solo lo no consagrado y «correr todo» se mudó al `89`.
  4. **W-26b** — raíz **auditada** (64 rutas, 56 ya iguales) y las 8 del player
     republicadas. Medido: sin `?renderer=canvas2d` la raíz pasa **240 ms en
     WebGL** al abrir, que es el pantallazo blanco de la caja. **W-26 y W-26b
     CERRADAS esa misma noche en la caja**: *«sigue andando trabado pero sin
     pantallazos»*. Lo trabado es el **player 100 % JS**, ya medido acá en
     DIAG-003 (p50 233–290 ms contra 66,7; cuello en CPU, no en WebGL): no es un
     defecto nuevo, es la razón por la que existe este repo.
  5. **H-18** — un **segundo `<video>` con alfa encima** del loop (tecla `87`),
     **rehecho como H-18b** (abajo).

  **La foto de la caja del 2026-09-04 (noche) cerró dos:** el techo aguanta
  **50 MB en tandas de 5 MB con la app viva** (era un defecto de la prueba,
  confirmado) y **Hobo entra** en Chromium 70 —`fuente hobo (166 ms)`—, así que
  **H-16 queda CERRADA**. Y dijo algo que no esperábamos: **los dos planos de
  video se sostienen en la caja, y mejor que en la PC** (2/155 abajo, 2/138
  arriba). Sobre esa foto el operador pidió dos cosas más, hechas el mismo día:

  6. **H-18b** — la prueba de dos videos estaba **mal armada**, por dos razones
     distintas: el de arriba iba **encogido y corrido**, y la pieza con alfa
     llevaba **el RGB del propio máster**, así que superpuesta exacta habría
     sido indistinguible de lo de abajo. Ahora va **exactamente sobre el otro**
     y lleva **papelitos sobre transparencia total** —contenido que no existe
     abajo—. El generador usa **enteros y ondas triangulares, nunca `sin`/`cos`**:
     1 ULP entre dos libm cambiaría los bytes de la pieza (invariante 7).
     **Pack re-emitido**: las otras seis piezas salieron byte-idénticas en otro
     runner (segunda confirmación del invariante después de H-14b) y solo se
     republicaron **tres keys**.
  7. **H-20** — **a pantalla entera** (teclas `70`/`73`), que es la última
     pregunta grande sin medir: en la caja «entera» no es 720p sino **4K de
     escalado**. Cuatro escalones —solo, con capa, con efecto, todo junto—
     porque importa dónde se rompe, no un número. Y el **reporte en dos
     columnas** con el `88` para volver: la foto anterior cortó en la novena
     fila, y en una TV lo que no entra no existe. Abre la **tercera puerta** del
     mando (`7`).

  **H-18b y H-20 quedaron CERRADAS con la segunda foto del 2026-09-04**, y de
  ahí sale una **regla de diseño**: dos planos de video se sostienen (2/154 y
  1/141 → **un efecto puede SER video**), la superficie 4K **no le cuesta al
  `<video>`** (0–1 de 155 él solo; la escala el hardware) y la API de fullscreen
  ni se concedió ni hizo falta.

  **Con los tres planos el contador salta a 17/155 —idéntico en dos corridas—,
  pero el ojo del operador firmó *«todo junto… se ven perfecto»*, y eso manda:
  los TRES PLANOS ESTÁN HABILITADOS** (video base + pieza alfa + canvas). La
  caja **consagra**, y el contador de esta clase está desacreditado: la cabecera
  dice `quality no`, el número sale de `webkitDroppedFrameCount`, el mismo que
  en E5 informaba `total 0` con VP9 andando perfecto. **Una regla escrita la
  mañana del 2026-09-04 («dos planos, no tres») quedó sin efecto esa noche**;
  el salto del cuarto escalón queda anotado para un aparato donde `quality`
  exista. Cuando hornear el efecto salga gratis, se hornea: por barato, no por
  miedo (DISENO §9).

  **La red (E16):** la caja **no puede arrancar sin red** —la app tiene
  validaciones intermedias que la piden—, así que ese escenario **se descarta**
  y se diseña **con** el arranque conectado. Cortarla en el medio tampoco prueba
  residencia. La prueba que discrimina: red cortada con la página **ya abierta**
  y recién ahí `85` (IndexedDB → `blob:`, cero red); la cabecera y las filas
  `cache:*` ahora declaran **`red si|no`** para que la foto lo pruebe sola.

  8. **H-21** — el operador pidió mirar los dos planos **sin los cortes de la
     medición** (*«se corta el video cuando son dos superpuestos… un loop de
     los dos videos superpuestos, en pantalla grande»*). Los cortes eran del
     `70`, que corre cuatro escalones y para entre uno y otro. Tecla **`71`**:
     los dos planos a toda la superficie, **en bucle y sin un solo corte**,
     hasta que se apague; no agrega fila —no mide, muestra— pero el zócalo
     lleva los **caídos vivos de los dos**. Porque «2,6 % de caídos» y «se ve
     fluido dos minutos» son dos datos distintos, y el segundo lo firma el ojo.

  9. **H-22** — en el WebView de un **Smart TV con Android** no entraba ningún
     número, **ni por control remoto ni por un pad USB**. Dos causas posibles,
     las dos atacadas: el dígito llegando por un campo que no mirábamos
     (`digitOf` preguntaba solo por `keyCode`) y el `<input>` quedándose con el
     foco —el mismo defecto del `<textarea>` de H-20—. **La primera quedó
     confirmada sin ir al aparato:** el navegador de esta sesión reproduce el
     síntoma y la línea de diagnóstico nueva lo escribió sola: `keydown kc=0
     w=0 cc=0 key=9 code= foco=BODY`. Ahora hay **cuatro caminos** para leer un
     dígito (`keyCode` 48–57, 96–105, **`key`**, `code`/`charCode`), `keypress`
     como plan B con guarda, y el campo fuera del recorrido del foco. **Lo que
     sobrevive a la tarea es la línea de diagnóstico** —fija en `ir.html`, en el
     zócalo de `v0/`—: separa dos fallas que se ven idénticas, «los eventos no
     llegan a la página» (no se arregla desde acá) de «llegan por otro campo»
     (sí), y hasta hoy no se podían distinguir sin viajar.

  **H-22 CERRADA con la foto del Smart TV** (*«anda aun mejor asi que pasa
  perfecto»*), y ahí aparece algo grande: **una SEGUNDA CLASE de aparato, que
  sí sabe contar**. Noblex, Android 11, **Chrome 142**: `quality si`, `rvfc si`,
  cuota **2.637 MB** (12× la caja), `v0-vp9-alpha` **0/156 con deriva 0**. Es
  **el aparato que puede arbitrar E15** —si el 11 % de los tres planos era costo
  real o un artefacto del `webkitDroppedFrameCount` roto de la caja— apretando
  `70`. Y `rvfc` habilita sincronía de cuadro exacta, **como mejora opcional por
  aparato, nunca como requisito**. **La caja sigue siendo la clase principal:**
  el formato se diseña contra el piso, no contra el techo.

  **Queda UNA SOLA VISITA a la caja** (qué traer: `RUNBOOK-ESTADO.md`): `85` con
  la red cortada, `83` sola, y `71` como opcional. Después de
  ~~H-6~~ (ejecutada 2026-09-05: matriz + v1 publicada; falta la foto con
  `76`/`95`) y de **H-8a** (el player del producto como prototipo, ejecutado
  la noche del 2026-09-05; falta la foto con `7` del lanzador) siguen la
  **firma de H-7** (spec `SPEC-VGEN.md`, borrador 0.1, con **H-15** residencia
  adentro) y **H-8** (muxer ES5 + archivo único). Externo: pedir
  a la app que el WebView reporte el panel real (hoy 3840×2160 sobre 1280×720).
- **Lo que la caja dijo (2026-09-01, Android 9 / Chromium 70):** todo lo
  progresivo reproduce **fluido por hardware** a 720p@15 con la superficie 4K
  activa (0–2 caídos de ~155 en 10 s); **Main = Baseline → decodificador
  hardware**; **el arranque lo manda la cantidad de bytes por red** (H.264
  2.985 ms por red, **517 ms** desde `blob:`, VP9 931 ms); **VP9 reproduce**
  (el contador no lo ve: su fluidez la firma el ojo); **HLS-TS nativo sí**,
  HLS-fMP4 inservible, DASH no; **MSE declarado y sin probar**; IndexedDB sí;
  sin rVFC. Consecuencia: **la fluidez es un gate, los bytes y el arranque son
  el objetivo**; VP9 al frente donde reproduzca, H.264 Baseline de piso.
  **Ojo del operador (mismo día):** VP9 «perfecto, hasta más fluido»; el alfa
  **compone**; HLS-TS «se traba mucho al iniciar» (camino D fuera del producto).
  **«De momento el tv box es la base»** → la caja es la **clase principal** y
  consagra; la PC refuta. Contenido real = **loop intervenido + publicidad que
  reemplaza y vuelve + incentivadores a demanda** (plan §2.7). Nombre del
  formato: **`.vgen`**. **Audio sí** («tipo radio» + hablado con sincronía en
  momentos → ambiente en `<audio>` aparte, el propio de una pieza muxeado en
  ella; plan §2.6). **Gates aprobados** (caídos ≤ 3 %; plan §3.1). Las
  compresiones ASCILINE se aplican **siempre** (toda pieza sale del máster) y
  compran bytes, no velocidad de decodificación (plan §2.8). **Visita del
  2026-09-04 (REGISTRO «Visita a la caja 2026-09-04»):** VP9 base y Baseline
  secundario; **residencia** como requisito (prendido ≥ 16 h/día, baja una vez
  al día, reproduce siempre desde el aparato, sin «falso streaming»; plan
  §2.9); muxer A = concat / B = MSE; **Hobo** fuente por defecto de la capa
  (`inputs/HoboStd.ttf`, git-ignorada). Los arranques por red variaron 3× entre
  visitas → el gate de arranque solo se exige desde caché o `blob:`. **No hay
  decisiones pendientes**; el operador debe la foto tras apagar y prender + `85`.
- **Herramientas de la fase H, ya hechas — no re-implementar:**
  `tools/emit_pieces.py` + workflow `emitir-v0` (emiten el pack desde el máster,
  con los empaquetados HLS/DASH por remux), `frontend/v0.html` (una sola
  pantalla, sin scroll, un solo `<video>`, mando numérico),
  `frontend/keypad.js` (el mando **compartido**), `frontend/vgenfeed.js` (las tres
  puertas del paquete: MSE, Blob concatenado, cambio por `src`; lo reusa H-8) y
  `frontend/ir.html` (lanzador
  autocontenido que vive en **otro servidor**, no en el bucket).
- **Las suposiciones del pack v0 están escritas con su refutación** en
  [`docs/EMISION-V0.md`](docs/EMISION-V0.md) §4, y su veredicto en la caja en
  §4.b: el detector de Main **ya habló** (hardware → la matriz se reorienta a
  bytes y arranque); VP9 reproduce pero falta el ojo; el alfa está pendiente del
  ojo; nuevas S9..S12 (MSE, Blob concatenado, VP9 por MSE, intercambio/bucle)
  en §4.c, **ya juzgadas por H-13** (S9 consagrada, S10 en dos clases, S12 por
  MSE sí / por Blob no, bucle por `loop` refutado).
- **Suspendidas** (recuperables de `docs/historico/` solo con decisión del
  operador): F10 (pérdida adaptativa — ojo: seguiría mejorando el producto, que
  hereda los píxeles del máster), F11 (formato v4), F8, DIAG-001, opcionales.
