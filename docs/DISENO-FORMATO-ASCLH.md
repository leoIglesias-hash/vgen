# Diseño del formato `.asclh` — paquete híbrido intervenible

> **Estado: EN OBRA.** Este documento acumula el diseño del formato de
> distribución. Una parte está **decidida** (§10 lo marca fila por fila) y otra
> está **gateada por medición**: no se normaliza hasta que
> [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) devuelva la tabla de capacidades
> de aparatos reales. Escribir la spec normativa es la tarea **H-7**; hasta
> entonces esto es diseño, no contrato.
>
> Norte y filosofía: [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md).

---

## 1. Qué es `.asclh`

**Un contenedor de piezas + un manifiesto + una disciplina de autoría.** No es un
códec y no es un archivo de video: es una **biblioteca** de la que el dispositivo
arma, en el momento, algo que su `<video>` sabe reproducir por hardware.

Lleva adentro:

- **piezas de video** ya codificadas (H.264, VP9, …), cada una decodificable por
  sí sola;
- **pistas de audio** independientes e intercambiables;
- **sprites ASCILINE** (matriz indexada con transparencia) para lo escaso y lo
  vivo, que el video no puede hacer;
- **el guion**: qué va cuándo, dónde están los huecos, qué reacciona a datos;
- **metadatos del máster**: paleta, geometría, procedencia (hash del `.asclv`).

**Nombre y envelope provisorios:** extensión `.asclh`, magic `ASCLHYB1`.
Pendiente de confirmación del operador; no hay código que dependa de esto todavía.

**Relación con el máster:** el `.ascl`/`.asclv` **no se reemplaza**. Sigue siendo
el máster determinista offline donde vive la verdad (paleta, trellis, look,
reproducibilidad byte a byte). `.asclh` es lo que **viaja**, y se emite desde él.
Un `.asclh` siempre declara de qué máster salió.

## 2. Modelo de datos (tomado de DASH)

La jerarquía es la de DASH porque es exactamente la gramática de un contenido
intervenible. Los nombres se conservan a propósito, para poder razonar con
material ajeno.

```
Paquete (.asclh)
├── Cabecera        magic, versión, hash del máster, resolución base, paleta
├── Init            cabeceras de códec compartidas (una por códec presente)
├── Period[]        tramo temporal — LA UNIDAD DE INTERVENCIÓN ESTRUCTURAL
│   └── AdaptationSet[]     video | audio | sprites | datos
│       └── Representation[]   una variante concreta (códec, fps, contenido)
│           └── Segment[]        pieza decodificable, direccionada por rango de bytes
├── Sprites[]       matrices ASCILINE indexadas con índice transparente
├── Cues[]          guion: t → qué pieza, qué sprite, qué slot, qué dato
└── Huecos[]        geometría de las zonas que el encoder dejó planas para lo vivo
```

Qué compra cada nivel, en concreto:

- **Period** = *«acá pasa otra cosa»*. Insertar, quitar o cambiar un tramo es
  editar el manifiesto. Es el nivel N1 de la escalera de intervención.
- **AdaptationSet** = pistas independientes. **Cambiar solo la música es elegir
  otra Representation del AdaptationSet de audio.** Sin tocar un byte de video.
- **Representation** = variante. Sirve para tres cosas a la vez que normalmente
  se piensan por separado: distinto **códec** (compatibilidad), distinto **fps o
  densidad** (capacidad del aparato), y **distinto contenido** (nivel N3: el
  mismo segmento con otro número adentro).
- **Segment** = la pieza Lego. Decodificable sola, direccionada por offset+largo
  dentro del archivo único.

**Extensión propia:** `Sprites`, `Cues` y `Huecos` no existen en DASH; son lo que
ASCILINE aporta. Si algún día emitimos un MPD real, van en un espacio de nombres
propio que cualquier player ajeno ignora sin romperse.

## 3. Piezas intercambiables — por qué 1280×720 fijo

**Regla:** todas las piezas de video de un paquete comparten resolución, códec de
familia, perfil y nivel; por lo tanto comparten **cabecera de inicialización**
(SPS/PPS en H.264, la cabecera equivalente en VP9). Cada pieza arranca en un
cuadro clave cerrado.

Consecuencias, que son el corazón del sistema:

1. **Las piezas se concatenan en cualquier orden sin re-codificar** y el
   decodificador no percibe el corte. Eso es lo que hace posible N1 y N3.
2. **El decodificador se configura una sola vez.** Cambiar resolución a mitad de
   stream es una de las causas clásicas de tildado y crash en SoCs baratos: con
   resolución fija, nunca ocurre.
3. **La cabecera viaja una sola vez** para todo el paquete, no por segmento.

El operador fijó **1280×720** como resolución base del proyecto el 2026-09-01.
Sigue valiendo el principio de que la densidad se elige por clip — pero se elige
**dentro** del paquete (vía Representations de distinta calidad), no cambiando la
resolución del contenedor.

## 4. fps variable — gratis, y es el ahorro más grande

En un contenedor, **la duración de cada cuadro es un dato de la tabla de tiempos,
no del bitstream**. Entonces:

- una pieza se **retimea sin re-codificar** (acelerar, frenar, sostener);
- **cada segmento puede tener su propio fps**: una escena casi estática a 3 fps y
  una de acción a 30, en el mismo clip;
- **el costo de decodificación baja de forma lineal con la cantidad de cuadros
  realmente decodificados** — probablemente el ahorro más grande y más barato de
  todo el sistema.

Y lo decide el encoder solo: el máster ya sabe dónde hay movimiento (detección de
cortes, tiles que cambian). **El fps por segmento se deriva del máster**, no se
elige a mano.

## 5. Emisiones de runtime — cómo llega el paquete a `<video>`

Un `.asclh` no se le da al `<video>`: se **traduce** a lo que ese aparato acepte.
Cuatro caminos, del más compatible al más capaz. Cuál existe en cada aparato lo
dice **reproducir el pack v0** ([`EMISION-V0.md`](EMISION-V0.md)), no un
cuestionario.

| Camino | Cómo | Requiere | Para qué |
|---|---|---|---|
| **A — mp4 progresivo en memoria** | el muxer arma un MP4 estándar con las piezas elegidas, `Blob`, `URL.createObjectURL`, `video.src` | `Blob` + `<video>` (casi todo) | **el piso.** Clips cortos. Cero red tras la descarga |
| **B — fMP4 por MSE** | el muxer emite fragmentos y los va anexando a un `SourceBuffer` | MSE | clips largos (no cabe todo en memoria), empalme en vivo, cambio de pieza sin corte |
| **C — WebM directo** | las piezas VP9 se envuelven en WebM; incluye el caso **alfa** | VP9 + WebM (+ alfa si el aparato la compone) | mejor compresión y **video transparente sin CPU** |
| **D — nativo** | en aparatos con HLS/DASH nativo, servir la emisión correspondiente desde red | soporte nativo | Smart TVs donde ese camino es el más aceitado |

**Ninguno de los cuatro decodifica nada en JS.** El muxer solo **acomoda bytes**:
copia unidades ya codificadas y arma tablas. Es la operación que hacen los
remuxers de HLS en el navegador, y cuesta un orden de magnitud menos que
decodificar.

## 6. El muxer

Componente nuevo, en el frontend, **ES5 estricto**. Responsabilidades:

- leer el manifiesto del `.asclh` y resolver qué piezas corresponden;
- armar las estructuras del contenedor de salida (tablas de muestras, duraciones,
  offsets) — **sin tocar el contenido de las piezas**;
- entregar un `Blob` (camino A) o fragmentos (camino B);
- rearmar rápido cuando la intervención N1 cambia la selección.

Restricciones que lo definen:

- **cero decodificación, cero recodificación**;
- **cero dependencias** (el proyecto no usa librerías en el frontend);
- **presupuesto de memoria explícito**: el camino A sostiene el paquete y la
  salida a la vez; ese límite es lo que decide cuándo hay que ir al camino B.

Diseño detallado: pendiente de H-7/H-8, después de que la medición diga qué
caminos existen en los aparatos reales.

## 7. Audio — «cambiar solo la música»

Es el caso más fácil de todo el sistema, no el más difícil.

- **Camino inmediato, sin muxer:** un `<audio>` separado del `<video>`. Usa un
  decodificador distinto (audio y video son bloques separados), no compite por la
  sesión de video, y cambiar de tema es cambiar un `src`. Sincronía suficiente
  para música de fondo.
- **Camino integrado:** el audio como AdaptationSet dentro del paquete, muxeado
  junto al video. Cuesta más muxer y se justifica solo si hace falta sincronía
  fina (que la música de fondo no necesita).

**Decisión de diseño:** arrancar con el camino separado. Muxear el audio solo si
la medición muestra deriva perceptible.

## 8. Caché y distribución

Objetivo: **después de la primera vez, cero red.** Las wifi de los locales fallan
y el clip no puede depender de ellas.

- **Pineo por contenido**, heredado de CACHE-001: la URL lleva el hash, el
  contenido es inmutable y solo un puntero chico se revalida. Ya está probado en
  producción con el `.asclv`.
- **Almacenamiento en el aparato:** descarga por XHR (con progreso), guardado
  como blob en **IndexedDB** —API de eventos, entra en ES5— y reproducción desde
  `blob:`. La clave es el hash: paquete nuevo = clave nueva, y las viejas las
  borramos nosotros.
- **Degradación:** si IndexedDB no persiste, se cae a memoria por sesión; si
  `blob:` no reproduce, al camino B o a red directa. Lo decide la reproducción
  (H-10/H-12), aparato por aparato.
- **En la app (APK):** el mismo paquete descargado nativamente a disco. **El
  manifiesto es el mismo en los dos casos** — la web es el contrato, el APK es
  una optimización, nunca una dependencia.

## 9. La capa de intervención

Sobrevive del paradigma anterior, con su costo ahora proporcional al área y no a
la pantalla. Reusa lo que ya existe y está probado: `overlay.js`, `textlayer.js`
(texto nativo Canvas2D), `slots.js`, `datachannel.js`.

- **Un solo canvas**, Canvas2D, dimensionado **al panel real** — nunca a la
  superficie que da el WebView (en la caja medida son 3840×2160 sobre un panel de
  1280×720: un canvas a esa escala sería letal).
- **Sincronía por `video.currentTime`** en un loop de animación (no por
  `timeupdate`, que va a ~4 Hz). Donde exista `requestVideoFrameCallback`, la
  sincronía pasa a ser exacta.
- **Dos clases de sincronía, y hay que distinguirlas siempre:** *de evento* (en
  el segundo 7 aparece el número) es barata y cubre casi todo; *de cuadro* (la
  intervención tiene que calzar con algo que se mueve) es cara y frágil — se
  resuelve **en el encoder**, horneando el hueco, no en el TV.
- **Sprites ASCILINE** para personajes, destellos y objetos con transparencia,
  con **movimiento como metadato**: un sprite + una trayectoria cuesta lo mismo
  quieto que cruzando la pantalla. Es algo que un mp4 no puede hacer.
- **Donde el aparato componga alfa por video (camino C), ese es el camino
  preferido** para el personaje transparente: costo de CPU ~cero.

**Incógnita crítica:** si poner un canvas encima del `<video>` le baja el fps al
video (puede sacarlo de su plano de hardware). Si la medición dice que sí, el
diseño se adapta: la intervención vive **al lado** del video, no encima. Es una
bifurcación de layout, y hay que conocerla antes de dibujar una sola pantalla.

## 10. Decidido vs. gateado por medición

| Tema | Estado |
|---|---|
| Resolución base 1280×720, fps variable | **decidido** (operador, 2026-09-01) |
| Formato códec-agnóstico desde el diseño | **decidido** (operador, 2026-09-01) |
| Modelo de datos tomado de DASH (Period / AdaptationSet / Representation / Segment) | **decidido** |
| `.asclh` envuelve, no reemplaza, al máster `.asclv` | **decidido** |
| Piezas con cabecera compartida y cuadro clave propio | **decidido** |
| fps por segmento derivado del máster | **decidido** (falta cuantificar el ahorro) |
| Escalera de intervención N1–N3 | **decidido** |
| Audio: `<audio>` separado primero, muxear solo si hay deriva | **decidido** |
| **Manifiesto en texto tabulado, nunca JSON** | **decidido** — el gate ES5 prohíbe `JSON`; se parsea con `split` |
| Nombre `.asclh` / magic `ASCLHYB1` | provisorio — confirma el operador |
| Qué códecs emitimos y en qué orden de preferencia | **gateado por el pack v0** (H-9/H-10): ¿VP9 existe? ¿Main sale gratis, o sea hardware? |
| Camino de runtime por perfil (A/B/C/D) | **gateado** (¿`blob:`? ¿MSE? ¿WebM alfa?) — lo responde reproducir v0 |
| Persistencia del paquete | **gateado** por **H-12** (¿IndexedDB persiste y cuánto?) |
| Intervención encima o al lado del video | **gateado** por **H-11** (¿el canvas encima cuesta cuadros?) |
| Techo de planos de video simultáneos | **gateado** (sesiones de decodificación) |
| Nivel N4 (intercambio sub-cuadro) | **investigación**, no cimiento |
| Layout binario del contenedor | **H-7**, después de todo lo anterior |

## 11. Preguntas abiertas anotadas

Sin tarea todavía; se anotan para no perderlas:

- **Paleta consciente del 4:2:0.** Todos los códecs submuestrean el color. Para
  arte plano con bordes duros eso es veneno, y puede explicar parte del
  escalonado que veníamos persiguiendo. Elegir la paleta de modo que los colores
  se separen sobre todo en **luma** haría que el submuestreo casi no dañe. Es una
  restricción nueva para el K-means y no la aplica nadie más.
- **Zonas estáticas idénticas bit a bit** para que el encoder las emita como
  «no cambió» — bytes casi nulos y decodificación casi nula. Nuestro pipeline
  indexado puede garantizarlo; un encoder genérico no.
- **Cuadros sostenidos escritos a mano**, sin pasar por el encoder: sostener una
  imagen N segundos por unas decenas de bytes.
- **Golden frames de VP9** como forma nativa de «fondo estático + primer plano».
- **F10 (pérdida adaptativa), suspendida, sigue teniendo efecto:** el video
  hereda los píxeles del máster. Si se retoma, mejora el producto híbrido igual.
- **Composición offline de escenas** cuando el layout se conoce de antemano:
  «tres videos» que en realidad son uno solo, resuelto por el encoder.
