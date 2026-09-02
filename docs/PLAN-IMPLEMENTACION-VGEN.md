# Plan de implementación — `.vgen` sobre el `<video>` de los WebViews de TV box

> **Estado: vigente desde el 2026-09-01, escrito con el primer reporte de aparato
> en la mano** (la TV box del operador; transcripción textual en el
> [REGISTRO](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md), entrada «H-10: primer reporte
> de aparato»). Es el documento de **rumbo**: qué se construye, por qué en ese
> orden, y con qué criterio se cierra cada paso.
>
> Reparto con los demás documentos: el norte y los invariantes están en
> [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md); el diseño del formato en
> [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md); las suposiciones con su
> refutación en [`EMISION-V0.md`](EMISION-V0.md) §4; la tarea a ejecutar (archivo,
> acción, cierre) en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md); el
> estado vivo en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md). Este documento no
> repite nada de eso: los ordena.
>
> **Regla de lectura:** todo lo que acá se afirma tiene una fila de evidencia (§1)
> o está marcado como suposición con su refutación. Si algo no cae en ninguna de
> las dos, está mal escrito y se corrige.

---

## 0. El rumbo en una página

**Qué construimos.** Un paquete **`.vgen`** = **piezas de video ya codificadas**
(H.264 y VP9, 1280×720, cada una decodificable por sí sola y cortada en
segmentos de 1 s sobre cuadros clave) + **un manifiesto en texto tabulado** (qué
pieza va cuándo, con qué audio, dónde están los huecos) + **la capa de
intervención** (un canvas encima con números, texto, logo y datos vivos). Y un
**runtime ES5** que en cada aparato traduce ese paquete a lo que su `<video>`
acepta nativo, por el mejor camino que ese aparato tenga. Nada se decodifica en
JS; el aparato solo ejecuta.

**Lo que la caja ya decidió (reporte del 2026-09-01):**

1. A 1280×720 @15, **todo lo progresivo reproduce fluido por hardware** (0–2
   cuadros caídos de ~155 en 10 s, deriva ≤ 2 ms) **con la superficie de
   3840×2160 activa**. El carril `<video>` absorbe lo que hundió al player JS.
2. **El decodificador es hardware:** Main (CABAC + 8×8) reproduce igual que
   Baseline con 9 % menos bytes. Aliviar el bitstream no compra nada acá.
3. **El arranque lo manda la cantidad de bytes por red:** el mismo H.264 tarda
   2.985 ms por red y **517 ms desde memoria**; VP9, con la mitad de bytes,
   931 ms. La caché y la compresión son las dos palancas del arranque.
4. **VP9 reproduce** y es el camino de banda (−53,8 %). El contador de cuadros
   no lo ve; **el ojo del operador lo firmó**: «salió perfecto, hasta más
   fluido». Es el **camino principal** en la caja.
5. **HLS-TS nativo es irregular** (una vez 2,0 s; después «se traba mucho al
   iniciar»); HLS-fMP4 nativo es inservible (14,2 s); DASH nativo no existe.
   **MSE está declarado y sin probar.**
6. `blob:` reproduce → existe el camino A (perfil P0 confirmado). IndexedDB sí.
   Sin `requestVideoFrameCallback` ni `getVideoPlaybackQuality`: es Chromium 70.
7. **El alfa compone**: «aparece el verde alrededor, y dentro del círculo el
   video». El personaje sin fondo puede ir por video.

**La TV box es la clase principal** (decisión manual del operador, 2026-09-01:
«de momento el tv box es la base»). Lo que ganó en ella queda consagrado; la PC,
cuando se pruebe, es refutadora. Nombre del formato: **`.vgen`** (operador).

**Lo que sigue, en orden:** **H-13** (por dónde entra *el paquete*: MSE,
concatenación CMAF, intercambio de piezas y costura del bucle — con el pack ya
publicado, sin emitir nada) → **H-11** (canvas encima o al lado) → **H-12**
(caché) → **H-6** (matriz por bytes a igual look, con la fluidez como gate) →
**H-7** (spec) → **H-8** (muxer + player). **H-14** y **W-26** son
independientes. La regla de avance es la del §3: **la fluidez es un gate; los
bytes y el arranque son el objetivo.**

## 1. Lo que sabemos (evidencia, no opinión)

| # | Hecho | Evidencia | Consecuencia para el formato |
|---|---|---|---|
| **E1** | Decodificar en JS no llega a 15 fps en la caja (290 ms/cuadro contra 66,7) | DIAG-002/003, REGISTRO 2026-09-01 | `<video>` es la única puerta; nada se decodifica en CPU |
| **E2** | Lo progresivo (Baseline, Main, VP9, VP9+alfa) reproduce con 0–2 caídos de ~155 en 10 s, deriva ≤ 2 ms, sin atascos, con superficie 3840×2160 | reporte de la caja, filas 1–4 y `blob:` | la fluidez a 720p@15 está **saturada** en esta clase: pasa a ser **gate**, no objetivo |
| **E3** | Main = Baseline en fluidez (1/153 vs 0/156), −9,1 % bytes, arranca 172 ms antes | filas baseline / main | decodificador **hardware**. El eje «aliviar el bitstream» se abandona. La estructura estricta (GOP 15 cerrado, `refs=1`, sin B) se conserva **solo por segmentabilidad**, no por fluidez. Ojo: el par v0 aísla la entropía (los dos llevan `refs=1`, sin B); el tamaño del DPB sigue sin medirse |
| **E4** | Mismo archivo H.264: 2.985 ms por red, **517 ms** desde `blob:`; VP9 (mitad de bytes) 931 ms | filas baseline / blob / vp9 | **arranque ∝ bytes por red**; demux + decoder se configuran en ≤ 0,5 s. Caché = **−2,5 s**; VP9 = **−2 s** |
| **E5** | VP9 y HLS-TS arrancan y sostienen el reloj 10 s, pero `webkitDecodedFrameCount` no los cuenta (total 0); VP9+alfa sí cuenta (155) | filas vp9 / hls-ts / vp9-alpha | esos dos caminos van por una tubería que el contador no ve. Su fluidez **la firma el ojo**, y H-13 agrega un indicador que no dependa del contador |
| **E6** | HLS-TS nativo: 2.012 ms, 0 atascos, deriva 38 ms. HLS-fMP4 nativo: 14.223 ms, 2 atascos reales, deriva 95 ms. DASH nativo: error de carga | filas hls-ts / hls-fmp4 / dash | camino D en esta clase = **HLS-TS y nada más**: reserva **sin JS** para H.264 |
| **E7** | Los 16 segmentos CMAF decodifican desde el init compartido (154 cuadros contados) aunque el reproductor HLS de la plataforma los sirva mal | fila hls-fmp4 | las **piezas** CMAF valen para el decodificador; lo que falla es el *reproductor nativo* de fMP4, no las piezas |
| **E8** | MSE declarado (`avc1.42E01F`, `vp9`), IndexedDB sí, rVFC no, `getVideoPlaybackQuality` no, `canPlayType` HLS «maybe» / DASH «no» | cabecera del reporte | piso de APIs de la clase: **Chromium 70 sobre Android 9**. MSE es la puerta que falta probar |
| **E9** | Segmentos `hls-fmp4/` y `dash/` byte-idénticos uno a uno; remux CMAF +0,04 %, TS +2,6 % | H-9, run 33566441576 | un juego de piezas, N manifiestos: la tesis del formato, en bytes |
| **E10** | VP9 −53,8 % **y** byte-idéntico entre corridas; H.264 no determinista (+22 / −74 B) | H-9 / H-14 | VP9 es hoy el único carril que cumple el invariante 7 |
| **E11** | Superficie 3840×2160 sobre panel 1280×720 | DIAG-003 + reporte | externo (la app). El canvas de intervención se dimensiona **al panel**, nunca a la superficie |
| **E12** | Ojo del operador: VP9 «perfecto, hasta más fluido»; el alfa **compone** (verde alrededor, video en el círculo); HLS-TS «se traba mucho al iniciar» | respuestas del operador, REGISTRO 2026-09-01 | consagra VP9 y el alfa por video; saca el camino D del producto en esta clase |
| **E13** | «De momento el tv box es la base»; contenido = loop intervenido + publicidad que reemplaza y vuelve + incentivadores a demanda; nombre `.vgen` | decisiones del operador, REGISTRO 2026-09-01 | la caja **consagra**; los casos de uso de §2.7; el nombre del formato |

**Lo que todavía no se sabe** —y por eso no se afirma—: cómo se ve la
**costura** entre segmentos y en el bucle, cuánto tarda un **cambio de pieza a
demanda**, cuánto cuesta el **canvas encima**, si **MSE** reproduce, cuánto
**persiste** IndexedDB. Cada uno tiene su tarea en §4.

## 2. Definición del producto

### 2.1 El paquete

Lo decidido en [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md) §1–§4, con
lo que la caja agregó:

- **Piezas de video**, una columna por códec: **H.264 Baseline** (el piso, y el
  único que entra en HLS-TS) y **VP9** (banda y arranque). Ambas 1280×720,
  GOP 15 cerrado, cuadro clave en cada segmento de 1 s, init compartido por
  códec. Codificar es caro y se hace una vez; **segmentar es un remux** (E9).
- **Manifiesto en texto tabulado**, nunca JSON (gate ES5). Describe piezas,
  segmentos, roles, hashes, y —cuando existan— pistas de audio, cues y huecos.
  El `MANIFEST.tsv` del pack v0 es su embrión.
- **Capa de intervención**: un canvas, dimensionado al panel, con lo que ya
  existe (`overlay.js`, `textlayer.js`, `slots.js`, `datachannel.js`).
- **Procedencia**: todo paquete declara el hash del máster `.asclv` del que
  salió.

### 2.2 El runtime (ES5 estricto)

Cinco responsabilidades, en este orden, y ninguna más:

1. **Detectar** — por detección directa (`MediaSource.isTypeSupported`,
   `indexedDB`, `URL.createObjectURL`, `canPlayType`) y **probando**: la tabla de
   perfiles por *user agent* es una pista, nunca la verdad.
2. **Obtener** — caché primero (IndexedDB, pineo por contenido), red después;
   siempre verificando el hash.
3. **Alimentar `<video>`** por el camino elegido (§2.3).
4. **Intervenir** — un canvas, sincronía por `currentTime` en un loop propio.
5. **Reportar** — las mismas columnas del banco (§3.1) disponibles con una tecla
   también en producción: cada aparato del parque deja su fila.

### 2.3 Los caminos, ya con la evidencia de la caja

| Camino | Mecanismo | En la caja | Rol en el formato | Qué lo mata |
|---|---|---|---|---|
| **A — `blob:`** | archivo entero en memoria (de caché o de red) → `URL.createObjectURL` → `src` | ✓ **517 ms**, 2/155; **S10 ✓** (Blob CMAF `init+16` = archivo, 1.286 ms, a re-medir) | **el piso y el camino de la caché.** Con **S10** es también el de la intervención N1 *offline*: concatenar las piezas elegidas antes de crear el Blob | memoria: el paquete entero vive en RAM; techo a medir en H-12 |
| **B — MSE** | `MediaSource` + un `SourceBuffer` por códec; segmentos anexados por XHR | ✓ **H-13: 2.033 ms por red, 156 cuadros, 0 atascos**; `sequence` cose 1-8,13-16,9-12 sin atasco; `changeType` sí | **la intervención estructural en vivo** (cambiar la próxima pieza sin bajar todo ni recrear el Blob); clips largos | si no reproduce o atasca (**S9**) → N1 se hace por A o por D |
| **C — progresivo por red** | `src` directo a la pieza | ✓ 2.985 ms H.264 / 931 ms VP9 | primer uso sin caché; el más simple | el arranque: se mitiga con VP9, desaparece con A |
| **D — HLS-TS nativo** | playlist `.m3u8` + segmentos TS; **la plataforma cose** | **irregular**: 2.012 ms una vez; después «se traba mucho al iniciar» (operador) | **fuera del producto en esta clase**; queda como columna para otras | solo H.264, +2,6 % bytes, tubería opaca (sin contadores), sin VP9, y arranque no confiable |
| ~~HLS-fMP4 nativo~~ | | ✗ 14,2 s, atascos | **refutado en la caja** | — |
| ~~DASH nativo~~ | | ✗ error | **refutado en la caja** (esperable: DASH vive sobre MSE) | — |

**Orden de preferencia del runtime (regla, no gusto):** con caché → **A**. Sin
caché → **C** (VP9 si reproduce, si no Baseline) mientras se baja para la
próxima vez. **B** existe (H-13): es **el camino del bucle y del intercambio de piezas** (por `loop` progresivo la costura se ve: 3 `waiting` en 60 s; por Blob en otro orden el demuxer se tilda). **D**
no se usa en esta clase (irregular); queda como columna para otras.

### 2.4 Códec

**VP9 al frente donde reproduzca** (banda, arranque y determinismo: E4, E5,
E10); **H.264 Baseline como piso** y único carril de D. **Doble emisión
siempre**: el formato es códec-agnóstico y el aparato elige. VP9 quedó
**consagrado en la clase principal** el 2026-09-01: el ojo lo firmó («salió
perfecto, hasta más fluido», E12) y el operador fijó la caja como clase
principal (§3.3).

### 2.5 Intervención

- **N1 (elegir piezas)** por A, B o D. Es lo primero que el formato promete y lo
  que H-13 pone a prueba en hardware.
- **N2 (canvas encima)** sujeto a H-11 (encima o al lado). El alfa por video
  **compone en la caja** (S4): el personaje sin fondo puede ir por video.
- **Sincronía:** sin rVFC en esta clase, el loop lee `currentTime` (no
  `timeupdate`, que va a ~4 Hz). Tolerancia declarada: **≥ 1 cuadro (66 ms a
  15 fps)** para toda intervención «de evento»; la «de cuadro» se hornea en el
  encoder, nunca se persigue en el TV.

### 2.6 Audio (operador, 2026-09-01: «va con audio… tipo radio… publicidades o contenido hablado intercediendo… sincronicidad en algunos momentos»)

Dos clases de audio, porque piden sincronías distintas:

| Clase | Dónde vive | Sincronía | Ejemplo |
|---|---|---|---|
| **Ambiente («radio»)** | `<audio>` aparte, continuo, independiente de la pieza de video; cambiar la música = cambiar un `src` | ninguna | música de fondo, radio |
| **Propio de una pieza** | **muxeado dentro de la pieza** (video + audio en el mismo mp4/webm); mientras suena, la ambiente baja con una rampa | exacta, la hace el mismo `<video>` | publicidad hablada, ruleta con locución |
| **Cue sobre el loop** | clip de audio disparado por el manifiesto cuando `currentTime` pasa por t | ≥ 1 cuadro (66 ms) — «de evento» | una locución en el segundo t del loop; si hiciera falta más fino, se muxea en una variante (N3) |

Suposiciones nuevas **S13** (pieza con audio muxeado reproduce sin perder
fluidez) y **S14** (`<audio>` + `<video>` simultáneos sin deriva perceptible):
se miden con la emisión v1 (H-6), que suma la pista del máster a las piezas.

### 2.8 Qué aporta el máster ASCILINE al `.vgen` (pregunta del operador: «¿aplicamos las compresiones de ASCILINE antes del formato vgen?»)

**Ya se aplican, y no se pueden no aplicar:** toda pieza se emite **desde el
máster `.asclv`**; paleta, trellis, near-lossless y cortes están decididos antes
de que el códec vea un píxel. Lo que cambió es **qué compran**: en el paradigma
JS aceleraban el decoder; en el híbrido el decodificador es hardware y en la
caja la fluidez ya está saturada (E2), así que ahí no hay velocidad que ganar.
Compran **bytes** (una imagen de paleta estable y zonas planas se codifica
mucho más chica), y bytes es **arranque y caché** (E4). Y compran **información
que ningún encoder genérico tiene**: cortes (cuadros clave ahí), zonas que no
cambian (bytes casi nulos), huecos para lo vivo. H-6 explota eso eje por eje.
F10 (pérdida adaptativa) sigue suspendida; mejoraría el look igual, porque el
video hereda los píxeles del máster.

### 2.7 Casos de uso del producto (operador, 2026-09-01)

> *«Vamos a tener diversidad: un contenido en loop, alguna publicidad que
> reemplace eso temporalmente y luego volvería al loop; el loop es el intervenido
> con los números seguramente; luego incentivadores tipo ruleta que tiene otra
> intervención pero es un video que entra y sale de acuerdo a lo que el usuario
> pida.»*

Calzan uno a uno con el modelo del formato:

| Caso | Qué es en el paquete | Nivel | Qué exige |
|---|---|---|---|
| **Loop** | la pieza base, en bucle todo el día, con los **números** encima | N2 sobre N1 | costura del bucle invisible (S12); canvas encima sin costar cuadros (H-11) |
| **Publicidad** | otra pieza que **reemplaza** al loop un rato y **vuelve** | N1 programado | cambio de pieza sin corte visible; vuelta al loop en el punto correcto |
| **Incentivador** (ruleta) | una pieza que **entra y sale a demanda del usuario**, con **su propia** intervención | N1 a demanda + N2 | **latencia de cambio a demanda acotada** (gate nuevo, §3.1); cues por pieza en el manifiesto |

Consecuencias que se vuelven requisitos:

1. **Todas las piezas residentes** en el aparato (H-12): el cambio a demanda no
   puede esperar a la red.
2. **La latencia de cambio de pieza** es métrica de primera clase, junto al
   arranque. H-13 la mide (cambio a demanda y vuelta al loop) con lo ya
   publicado.
3. **Un solo canvas, contenido por pieza**: el manifiesto lleva las cues de cada
   pieza; al cambiar de pieza cambia lo que el canvas dibuja, no el canvas.
4. Con VP9 consagrado y HLS-TS irregular, **los caminos del producto son A y
   B**; H-13 decide cuál hace el cambio de pieza.

## 3. Reglas de decisión

### 3.1 Gates de reproducción

**Aprobados por el operador el 2026-09-01** («apruebo tus gates… el de los
cuadros ponelo un poquito más flexible, solo poquito; si yo veo que se ve feo
aviso»). Un camino o una variante *pasa* en un aparato si, en 10 s de
reproducción:

| Métrica | Pasa si | De dónde sale el umbral |
|---|---|---|
| arranque desde caché (A) | ≤ 1.000 ms | `blob:` 517 ms |
| arranque por red (C / D) | ≤ 3.000 ms | Baseline 2.985 (al límite), VP9 931, HLS-TS 2.012; HLS-fMP4 14.223 **falla** |
| cuadros caídos | ≤ **3 %** de los contados | máximo observado 2/155 = 1,3 %; el operador pidió «un poquito más flexible» que el 2 % propuesto |
| atascos reales (`waiting` **después** del arranque) | 0 | todo lo que anduvo: 0; HLS-fMP4: 2 |
| deriva reloj − media | ≤ 50 ms / 10 s | 38 pasa, 95 falla |
| congelados (muestras de 100 ms sin avance) | 0 | nuevo en H-13: para los caminos que el contador no ve |
| cambio de pieza a demanda (pedido → primer cuadro de la otra pieza) | ≤ 1.000 ms | el incentivador entra «de acuerdo a lo que el usuario pida»; `blob:` arranca en 517 ms |
| ojo del operador | «fluido» / «sin costura» / «verde» | lo que ningún contador mide — y el gate último: «si veo que se ve feo aviso» |

### 3.2 Qué se optimiza

En la clase medida la fluidez está **saturada** (E2). Por lo tanto la
optimización es de **bytes a igual look** y de **arranque**, con los gates de
3.1 como condición. Una variante que baja bytes y rompe un gate **no existe**.

### 3.3 Normalización

Un aparato **refuta**; dos clases **consagran**; el operador **fija** (VISION
§8.11). **Decisión del operador, 2026-09-01: la TV box es la clase principal**
(«de momento el tv box es la base, porque en PC seguramente corra todo»). Lo que
gana en la caja queda **consagrado**; la PC, cuando se pruebe, es refutadora.

### 3.4 Una visita a la caja, un lote de preguntas

Cada tarea de medición deja la página lista con **todas** sus teclas antes de
pedirle al operador que vaya. No se le pide un viaje por pregunta.

### 3.5 Lo que el contador no ve, lo firma el ojo

Y la página lo **dice** en la fila («contador ciego») en vez de mostrar un `0`
que parece bueno.

### 3.6 Nada entra a la spec (H-7) sin fila

Ni por analogía, ni por «es lo normal», ni por `canPlayType`.

## 4. Fases y tareas

Orden: **H-13 → H-11 → H-12 → H-6 → H-7 → H-8**; **H-14**, **W-26** y lo que
falte de **H-10** corren aparte. Cuerpos ejecutables (archivo, acción, cierre)
en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2.

| Tarea | Pregunta que le hace al aparato | Entrega | Cierra cuando |
|---|---|---|---|
| **H-10** (queda abierta para las otras clases) | lo mismo que ya contestó la caja | filas de celular / Smart TV / escritorio | el operador las corre, **o** fija a mano la caja como clase que consagra (§6) |
| **H-13 — por dónde entra el paquete** (**CERRADA 2026-09-01 noche**; REGISTRO «H-13: reporte de la caja») | ¿MSE reproduce los segmentos CMAF ya publicados (**S9**)? ¿`init + segmentos` concatenados en un Blob reproduce como archivo (**S10**)? ¿las piezas se **intercambian** sin costura (**S12**)? ¿el **bucle** cose sin `waiting`? ¿cuánto tarda un **cambio de pieza a demanda** y la vuelta al loop (§2.7)? ¿existe `SourceBuffer.changeType`? | `v0.html` crece con teclas `9x`: MSE H.264, Blob concatenado, intercambio de orden, bucle de 60 s, cambio a demanda entre dos piezas (VP9 ↔ Baseline) y vuelta; columna «congelados»; «atascos» descuenta el `waiting` inicial; fila marcada «contador ciego» cuando corresponde; **no pausa al terminar la medición** (el símbolo de play que vio el operador). **Cero emisión nueva**: todo sale del pack publicado | filas en el REGISTRO por camino con las columnas de §3.1; S9/S10/S12 marcadas; gate ES5 verde; y **queda escrito qué camino implementa el muxer (H-8)** |
| **H-11 — encima o al lado** | ¿un canvas que repinta encima del `<video>` le cuesta cuadros (**S5**)? | misma página: canvas de intervención con tres cargas (nada / rectángulo chico a 15 fps / pantalla completa una vez), sobre Baseline y VP9 | caídos con y sin canvas en la tabla; la decisión **encima / al lado** escrita en DISENO §9 |
| **H-12 — caché** | ¿IndexedDB persiste tras reiniciar? ¿hasta qué tamaño? ¿arranca en ≤ 1 s desde ahí? | XHR con progreso → `Blob` → IndexedDB → `blob:`; pineo por hash; borrado de claves viejas; prueba de techo (10 / 25 / 50 MB) | el pack sobrevive a un reinicio y arranca dentro del gate; techo y degradación escritos |
| **H-6 — matriz por bytes a igual look** | ¿cuántos bytes menos a igual gate? por eje: VP9 (CRF, `cpu-used`), **fps variable por segmento** (S6 → bytes, ya no fluidez), H.264 piso relajado (Main/High, `refs`, B dentro del GOP cerrado), zonas estáticas, paleta 4:2:0. Incluye una fila de **referencia** con los defaults de ffmpeg (el `producto.mp4`) bajo los mismos contadores | emisión **v1**: cada variante con sus segmentos (CMAF para H.264, WebM segmentado para VP9 → **S11**) | tabla en el REGISTRO con medición por aparato; **receta por perfil**, firmada por el operador |
| **H-14 — determinismo H.264** | (no es del aparato) ¿el encoder es no determinista o depende de la máquina? | la misma pieza dos veces en la misma corrida; `lscpu` en el log | causa establecida con evidencia; invariante 7 cumplido o redefinido por escrito |
| **H-7 — spec `SPEC-VGEN.md`** | — | contenedor, manifiesto tabulado, segmentos, sprites, cues, huecos, mapa perfil → camino | aprobada por el operador; cada decisión trazable a una fila |
| **H-8 — muxer ES5 + player mínimo** | ¿reproduce el paquete real con intervención activa en la caja? | **lo que H-13 dejó en pie (decidido 2026-09-01 noche): A = `concat()` en orden canónico para piezas enteras desde caché; B = alimentador MSE en `sequence` para el bucle y el intercambio; cambio a demanda por `src` con la pieza residente (VP9) o por B con `changeType`; D no.** Era: concatenador CMAF (A), alimentador MSE (B), generador de playlist (D); `<audio>` separado; canvas de intervención | veredicto del operador en la caja; gate ES5 verde |
| **W-26** | — | `?renderer=` en la raíz publicada | gate ES5 verde |

**Regla de dependencia:** H-7 no empieza sin H-13 **y** H-11 cerradas; H-8 no
empieza sin H-7 aprobada. H-12 y H-6 pueden correr en paralelo con H-11 si el
operador tiene visitas a la caja disponibles (§3.4).

## 5. Riesgos y deudas conocidas

| Riesgo / deuda | Estado | Qué lo contiene |
|---|---|---|
| **H.264 no determinista** (invariante 7) | abierta, H-14 | mientras tanto VP9 es el carril reproducible; los SHAs de H.264 se citan con la salvedad |
| **Contadores ciegos** para VP9 y HLS-TS en la caja | conocida | firma del ojo + columna «congelados» (H-13) + fila marcada |
| **Sin rVFC** → sincronía por `currentTime` | de la clase (Chromium 70) | tolerancia ≥ 1 cuadro declarada; lo de cuadro se hornea offline |
| **MSE sin probar**; `changeType` desconocido | H-13 | si no hay `changeType`, cambiar de códec exige recrear el `MediaSource`; A y D son el respaldo |
| **Camino A retiene el paquete en RAM** | H-12 | techo medido, no supuesto; B es la salida si no cabe |
| **Superficie 4K sobre panel 720p** | externo (la app) | el canvas se dimensiona al panel; el `<video>` ya demostró absorberla |
| **Un solo aparato medido** | H-10 | el operador fijó la caja como clase principal (consagra); la PC, cuando se pruebe, refuta |
| **Audio sin probar en la caja** (pack v0 mudo) | H-6 v1 (S13, S14) | dos clases definidas en §2.6: ambiente en `<audio>` aparte; el propio de una pieza, muxeado en ella |
| **`producto.mp4` (defaults) nunca se midió con contadores** | H-6, fila de referencia | la comparación 2,3× hoy es de bytes, no de fluidez |

## 6. Decisiones que necesita el operador

**Respondidas el 2026-09-01** (textuales en el REGISTRO, entrada «Respuestas del
operador al primer reporte»): **1** alfa → compone (S4); **2** VP9 «perfecto,
hasta más fluido», HLS-TS «se traba mucho al iniciar» (D fuera del producto);
**3** la TV box es la clase principal (consagra); **5** contenido = loop
intervenido + publicidad que reemplaza y vuelve + incentivadores a demanda
(§2.7); **7** nombre **`.vgen`**.

**Respondidas también (misma tarde):** **4** audio → sí, «tipo radio» +
publicidades/contenido hablado con sincronía en algunos momentos (diseño en
§2.6); **6** gates aprobados, con caídos «un poquito más flexible» → 3 %
(§3.1). Y una pregunta más, respondida en §2.8: las compresiones ASCILINE se
aplican **siempre**, porque toda pieza sale del máster.

**No queda ninguna decisión pendiente del operador.** Lo que sigue es ejecutar
H-13 (§4).

## 7. Cómo se mantiene este documento

- Cada reporte de aparato nuevo agrega o corrige filas en **§1** y en
  [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §5, y actualiza el veredicto de
  cada suposición en [`EMISION-V0.md`](EMISION-V0.md) §4.b.
- Cada tarea cerrada mueve su fila de **§4** al ejecutado correspondiente y deja
  acá una línea.
- Si una decisión del operador (§6) cambia el orden, se cambia **§0** y **§4**
  en el mismo commit, con la fila de bitácora en `RUNBOOK-ESTADO.md`.
- Nada de este documento se copia a la spec (H-7): la spec cita filas, no
  párrafos.
