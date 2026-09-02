# Visión y objetivos — ASCILINE-hybrid

> **Este es el documento de norte del proyecto.** Si una sesión post-compact lee
> un solo archivo de diseño, lee este. Define qué construimos, con qué filosofía,
> qué tomamos prestado de dónde, y cuáles son los límites que no negociamos.
> Escrito el 2026-09-01 a partir del debate con el operador (REGISTRO, entrada
> «Debate de dirección: el formato propio»). Lo operativo vive en los runbooks;
> acá está el porqué.

---

## 1. Qué construimos, en una frase

**Un formato de video propio, códec-agnóstico, cuyo material se decide caro y
offline y se reproduce siempre por el hardware del dispositivo — y que se puede
intervenir en vivo sin volver a codificar nada.**

No es un player. No es un códec. Es un **paquete + un contrato de reproducción**
que en cada dispositivo termina alimentando una etiqueta `<video>` con lo mejor
que ese dispositivo sepa decodificar.

## 2. La frase madre (heredada, sin cambios)

> **Encoder caro, decoder sin estrés.**

Es la misma que sostenía ASCILINE cuando el decoder era JS nuestro. Lo único que
cambió es **quién ejecuta**: antes era un intérprete de JavaScript, ahora es un
bloque de silicio. La obligación es idéntica y hasta más estricta: el dispositivo
**no cuantiza, no decide, no compone nada caro**. Todo lo pensado ya vino
pensado desde el pipeline offline.

Corolario que se aplica a cada decisión de diseño: si algo se puede calcular
antes, se calcula antes. Si algo se puede evitar en runtime, se evita. El costo
en el TV se mide en **trabajo por segundo**, no en elegancia.

## 3. La regla física que ordena todo

> **`<video>` es la única puerta al hardware.**

Desde una página web no existe otra forma de tocar el decodificador de video del
aparato. Ni WebGL, ni WASM, ni un decoder propio: todo eso es CPU. Entonces:

**Todo lo que emitamos debe terminar en algo que `<video>` acepte de forma
nativa.** Esa es la restricción dura del proyecto, y a cambio es también la
fuente de su compatibilidad: donde haya un `<video>`, hay un camino para
nosotros.

De ahí se desprende la segunda regla estructural:

> **La densidad decide el transporte.** Imagen densa que ocupa la pantalla → va
> por el `<video>` (hardware). Contenido escaso —un personaje, un destello,
> números, una ruleta— o reactivo a datos vivos → va por la capa de intervención
> (matriz ASCILINE / canvas), cuyo costo es proporcional a su área, no a la
> pantalla.

Y la tercera, que es la versión nueva del viejo «hacer menos trabajo por frame»:

> **Pintar una vez, animar en el compositor.** Lo que se puede pre-renderizar se
> pre-renderiza; en runtime solo se *mueven* cosas (transformaciones CSS, que van
> por el compositor y no por la CPU) o se repintan rectángulos chicos. Repintar
> superficie completa por frame está prohibido: es exactamente lo que hundió al
> player 100 % JS en la caja medida.

## 4. De dónde sacamos cada cosa

El sistema no se inventa de cero: se compone de lo mejor de cuatro linajes, y
cada uno aporta algo que los otros no tienen.

| Linaje | Qué le tomamos | Por qué |
|---|---|---|
| **VP9 / AV1** | **compresión y primitivas de códec**: *golden frames* / alt-ref (frames de referencia que nunca se muestran → «fondo estático + primer plano» resuelto **dentro** del códec), **tiles** independientes (la vía limpia para intercambiar un rectángulo del cuadro), y **alfa real en WebM** (video transparente compuesto por el navegador, sin canvas ni CPU) | comprimen mucho mejor que H.264 y traen de fábrica cosas que en H.264 solo se aproximan con trucos. Además, si un aparato reproduce YouTube bien, casi seguro tiene **VP9 por hardware**: es el camino que YouTube usa en Android TV, o sea el camino *más* rodado del aparato, no el más exótico |
| **DASH** | **el modelo de datos y la intervención estructural**: *Periods* (una intervención = un Period), *AdaptationSets* (video y audio como pistas independientes → **cambiar solo la música** es cambiar de pista, no re-codificar), *Representations* (variantes del mismo contenido: códec, fps, densidad, o **el mismo segmento con otro contenido**), *SegmentTimeline* (duraciones variables por segmento), direccionamiento por rango de bytes (un archivo, muchos segmentos adentro), manifiesto extensible con espacio de nombres propio | es códec-agnóstico **por diseño** y su gramática es, literalmente, la del sistema intervenible que queremos. Adoptamos **su modelo, no su runtime**: no cargamos un player DASH, tomamos su forma de describir el contenido |
| **HLS** | **la validación de campo y el piso**: que un video sea una lista de piezas independientes está probado a escala planetaria; el segmento de inicialización separado; el piso de compatibilidad H.264 que existe en absolutamente todo | nos dice qué es seguro asumir sobre reproductores reales. Lo que **no** copiamos: sus segmentos de segundos y su ciclo de recarga de playlist |
| **ASCILINE** (lo nuestro) | **la base que habilita todo lo demás**: el máster `.ascl`/`.asclv` determinista, la paleta y el look decididos offline, la intervención matricial con índice transparente, y la **disciplina de medición** (mismo input → mismos bytes; una mejora sin fila registrada no existe) | es la ventaja competitiva real: **controlamos los píxeles antes de que entren al códec**. Ningún encoder genérico tiene eso. De ahí salen los macrobloques estáticos, el fps variable por escena y la paleta pensada para sobrevivir al submuestreo de color |

## 5. Objetivos macro

1. **Un formato propio, códec-agnóstico desde el día uno.** Las piezas van
   etiquetadas por códec; el dispositivo elige lo mejor que sepa reproducir. Hoy
   emitiremos H.264 y VP9; mañana AV1 se suma como una columna más, sin
   rediseñar nada.
2. **Reproducción siempre por hardware, en todo lo que tenga un `<video>`.** El
   piso universal (H.264 Baseline 720p) tiene que andar en cualquier cosa; por
   encima, cada aparato aprovecha lo suyo.
3. **Intervención en vivo sin re-codificar.** Cuatro niveles, del gratis al
   experimental (§6). Incluye el caso concreto que pidió el operador: **cambiar
   solo la música de un modelo**.
4. **Decodificación de bajo estrés.** El material se mastea *para que decodificar
   sea barato*: fps variable por escena, zonas estáticas idénticas bit a bit,
   una sola referencia, sin reconfiguraciones, paleta que no pelea con el
   submuestreo 4:2:0.
5. **Sin red después de la primera vez.** El paquete se baja una vez, se pinea
   por contenido y vive en el dispositivo. Las redes wifi de los locales fallan;
   el clip no puede depender de ellas.
6. **Mejora continua guiada por medición.** El formato no se diseña de una: se
   **descubre midiendo** en aparatos reales, y cada mejora deja su fila. Ver
   [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md).

## 6. La escalera de intervención

Lo que prometemos y lo que investigamos, ordenado de lo seguro a lo arriesgado.
El diseño debe resolver cada caso en el nivel **más bajo posible**.

| Nivel | Qué es | Costo en el TV | Riesgo |
|---|---|---|---|
| **N1 — estructural** | elegir qué piezas se reproducen, en qué orden, con qué duración y con qué audio (Periods / AdaptationSets / Representations). Los datos vivos eligen la variante | rearmar el manifiesto: milisegundos | ninguno |
| **N2 — composición encima** | sprites ASCILINE con alfa, texto y datos en el canvas de intervención, cayendo en **huecos horneados por el encoder** (el máster deja zonas planas donde sabe que va lo vivo). Alternativa superior donde exista: video WebM con alfa, compuesto por el navegador | proporcional al **área intervenida**, no a la pantalla | bajo |
| **N3 — variantes pre-codificadas** | si lo vivo tiene que estar *dentro* del video con su misma calidad, se codifican las N variantes de ese segmento y se elige una | cero (es N1 aplicado a un segmento) | ninguno técnico; cuesta offline y en bytes |
| **N4 — sub-cuadro** | intercambiar los bytes de una región del bitstream sin re-codificar (tiles en VP9/AV1; slices en H.264) | cero | **alto — línea de investigación.** Si sale, es intervención de píxel en vivo sin CPU. Si no sale, N1–N3 ya cubren los casos de uso |

**El límite honesto (N5, imposible):** tocar un píxel arbitrario del video en
vivo requiere re-codificar, y re-codificar en el TV no va a pasar. Todo diseño
que dependa de eso está mal planteado y hay que bajarlo a N1–N3.

## 7. Perfiles de dispositivo

El mismo paquete, la mejor emisión que cada aparato aguante. **Qué perfil le toca
a cada dispositivo sale de la medición, no del criterio de nadie**
([`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md)).

| Perfil | Qué asume | Qué habilita |
|---|---|---|
| **P0 — piso** | `<video>` + H.264 Baseline 720p + `blob:` | reproducción básica, intervención por canvas2d, caché en memoria |
| **P1** | + VP9/WebM por hardware | mucha menos banda para la misma imagen; golden frames; **alfa por video** si el aparato la compone |
| **P2** | + MSE, + IndexedDB persistente, + más de un decodificador simultáneo | clips largos por fragmentos, empalme en vivo, caché entre arranques, dos planos de video |
| **P3** | + AV1, + tiles, + `requestVideoFrameCallback` | mejor compresión, sincronía exacta de la intervención, camino a N4 |

**Resolución base del proyecto: 1280×720, con fps variable** (decisión del
operador, 2026-09-01). No es una preferencia estética: fijar la resolución es lo
que hace que **todas las piezas compartan cabecera y sean intercambiables**, y
evita que el decodificador se reconfigure a mitad de stream —una causa clásica de
tildado en SoCs baratos. El fps, en cambio, es libre y **variable por segmento**,
porque en el contenedor la duración de cada cuadro es un dato, no bitstream: se
retimea sin re-codificar, y menos cuadros es menos trabajo de decodificación, de
forma lineal.

## 8. Invariantes del proyecto

Reemplazan y continúan a los del paradigma anterior. Se verifican, no se suponen.

1. **Todo termina en `<video>` nativo.** Nada de decodificar video en CPU
   propia. Si un camino no llega a `<video>`, no es un camino.
2. **La densidad decide el transporte** (denso → video; escaso o vivo → capa de
   intervención).
3. **Pintar una vez, animar en el compositor.** Cero repintado de superficie
   completa por cuadro; cero mutación de DOM dentro del loop.
4. **Presupuesto de capas explícito:** ≤1 `<video>` base, ≤1 canvas que repinta,
   ≤2 elementos que solo se transforman. Los WebViews se degradan con la
   cantidad de DOM: todo dato vivo se dibuja **dentro** del canvas, nunca como
   nodos.
5. **Piezas intercambiables:** misma resolución y misma cabecera de códec en
   todo el paquete, cada pieza decodificable por sí sola. Sin eso, no hay N1.
6. **Retrocompatibilidad JS:** frontend en **ES5.1 estricto** (gate
   `tests/test_frontend_compatibility.js`). Las APIs que usamos (IndexedDB, MSE,
   Blob) son de eventos, no de promesas: entran sin romper el gate.
7. **Determinismo:** mismo máster + mismos parámetros → mismos bytes emitidos,
   en cualquier códec. Verificado, no supuesto.
8. **Validar antes de mutar:** parser corrupto = excepción tipada; nunca un
   estado a medias.
9. **Los valores manuales del operador prevalecen** sobre cualquier automatismo.
   Y **lo que requiere pantalla lo firma el operador**, nadie más.
10. **Una mejora sin fila registrada no existe** — ahora también para
    reproducción, no solo para bytes.
11. **Ningún aparato solo define el formato.** Un aparato puede **refutar** (si
    algo no anda ahí, no anda) pero no puede **consagrar**: para normalizar hace
    falta que gane en al menos dos clases de aparato, o que lo fije el operador.
    Es el invariante que evita el error simétrico al de F9: sobreajustar el
    formato a la única caja que tenemos a mano (operador, 2026-09-01).

## 9. Qué NO es este proyecto

Escrito para que ninguna sesión futura lo intente:

- **No inventamos un códec.** El silicio entiende lo que entiende. Inventamos
  todo lo que lo rodea.
- **No escribimos un encoder H.264/VP9 desde cero.** Manejamos encoders
  existentes desde el máster: nosotros decidimos keyframes, fps por segmento,
  zonas estáticas, paleta y estructura; ellos ejecutan. (La excepción legítima:
  generar a mano cuadros triviales —«no cambió nada»— que ningún encoder emite
  óptimamente.)
- **No cargamos un player DASH/HLS.** Tomamos su modelo de datos, no su runtime.
- **No decodificamos video en JS.** Ese camino ya se midió y se descartó
  (DIAG-002/003).
- **No hacemos crecer el player JS anterior.** Se mantiene como reproductor de
  escritorio y banco de verificación del máster.
- **No *normalizamos* sobre suposiciones.** Arrancar suponiendo sí: es el método
  (se emite el primer video con las bondades conocidas de cada códec y se corrige
  reproduciéndolo). Lo prohibido es que una suposición entre a la spec sin
  haberse reproducido — y sin haberlo hecho en **más de un aparato**. Toda
  suposición vive con su refutación escrita en [`EMISION-V0.md`](EMISION-V0.md) §4.
- **No diseñamos el formato contra un solo aparato.** La TV box es el **piso de
  referencia**, no el objetivo.

## 10. Cómo se avanza

Un ciclo, repetido:

**suponer explícito → emitir desde el máster → reproducirlo en varios aparatos →
corregir la suposición → normalizar lo que ganó → volver a emitir.**

La primera vuelta es el **pack v0** ([`EMISION-V0.md`](EMISION-V0.md)): las
bondades conocidas de cada códec, escritas como apuestas con su refutación al
lado, y un primer video que se abre en la caja, el celular, el Smart TV y el
escritorio. Las tareas están en
[`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2 (fase H). El diseño
del formato que va saliendo de ese ciclo se acumula en
[`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md), que marca explícitamente
qué está **decidido** y qué está **gateado por medición**.
