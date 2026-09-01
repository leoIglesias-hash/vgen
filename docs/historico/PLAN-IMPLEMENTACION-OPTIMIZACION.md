# Plan de implementacion - calidad, eficiencia y compatibilidad

Fecha de inicio: 2026-08-11  
Rama: `feature/quality-optimization`  
Base recuperable: commit `1c2c0b2`

La ejecución posterior al cierre de las mejoras v1 se controla desde
`docs/HOJA-DE-RUTA-TECNICA-V2.md`. Allí están dependencias, entregables, métricas y
gates; este documento conserva principios y arquitectura.

## 1. Principios no negociables

1. El `.asclv` sigue siendo un unico recurso cacheable.
2. Se acepta mas costo offline si reduce bytes, RAM o CPU durante la reproduccion.
3. Canvas2D y WebGL1 reciben la misma matriz final y ofrecen la misma funcionalidad.
4. Canvas2D es el piso; WebGL1 es solamente un presentador acelerado opcional.
5. El frontend distribuido usa sintaxis ES5.1, valida en runtimes ECMAScript 2015.
6. No son requisitos: Promise, fetch, Worker, WASM, WebGL2, Service Worker o Streams.
7. FPS, cantidad de celdas, cantidad de colores y reconstruccion son editables por clip.
8. No se implementa deteccion, segmentacion ni rotacion especial de objetos.
9. La intervencion local futura usa slots explicitos sobre la matriz, nunca otra capa DOM.

Estado al 2026-08-22:

- Fase A implementada y validada en la rama de trabajo.
- Fase B implementada y calibrada: paleta global/por frame/por bloque/adaptativa,
  K-means RGB/Oklab, estabilidad temporal y dithering auto con presupuesto. Todo el
  analisis ocurre offline y la salida sigue siendo ASCL v1.
- Frontend TV de validacion implementado: precarga del artefacto local en una ruta estable, fullscreen y
  play con teclas 1-8/click/toque, descarga manual, loop y fallback Canvas2D.
- Fase E tiene un harness base cubierto por regresión; faltan la instrumentación/exportación
  de métricas y la validación en los Smart TV/WebViews reales.
- ASCLV2 exacto por tiles/predictores, ReaderV2 y factory dual están implementados y
  verificados localmente. Su promoción depende de TV-02.
- Los slots de intervención matricial permanecen en diseño y requieren una revisión
  posterior del formato; no forman parte del envelope ASCLV2 actual.

## 2. Controles de calidad

Los controles manuales siempre tienen prioridad. Los perfiles solo completan valores no
indicados por el usuario.

| Control | Funcion |
|---|---|
| `--cols N` | Cantidad de columnas de la matriz; las filas conservan el aspecto. |
| `--palette-size N` | Colores disponibles, entre 1 y 256 (se conserva el rango v1). |
| `--fps N` | FPS objetivo exactos del clip. |
| `--profile detail` | Prioriza mas celdas y una paleta menor. |
| `--profile balanced` | Equilibrio entre resolucion y color. |
| `--profile graphic` | 640 columnas y 256 colores para animacion, logos y gradientes. |
| `--profile graphic-hq` | 768 columnas y 256 colores; candidato de alta calidad. |
| `--profile graphic-ultra` | 960 columnas y 256 colores; techo de calidad medido. |
| `--profile color` | Menos celdas y mas colores. |
| `--profile custom` | Usa solamente valores manuales. |
| `--palette-algorithm median-cut|fast-octree|kmeans-rgb|kmeans-oklab` | Trabajo offline dedicado a elegir mejor los colores. |
| `--palette adaptive` | Renueva por distribucion Oklab, sin IA ni deteccion de objetos. |
| `--adaptive-min-frames/--adaptive-max-frames` | Limites variables; 5/10 por defecto de calidad. |
| `--adaptive-stability-max` | Amortigua cambios de paleta; 0,25 por defecto. |
| `--perceptual-lut-bits 0|3..7` | Oklab exacto o LUT offline de mayor velocidad. |
| `--dither auto` | Acepta tramado solo con mejora numerica, presupuesto e histeresis. |
| `--reconstruction nearest|soft` | Presentacion sugerida al player; no cambia los frames. |
| `--bake-smoothing none|soft` | Suavizado calculado offline antes de cuantizar. |

La recomendacion `soft` se guarda en el bit 4 de `flags` (`0x10`). Readers anteriores
ignoran el bit y mantienen su comportamiento; el player actualizado lo usa como valor
inicial y permite cambiarlo durante la reproduccion.

## 3. Fases

### Fase A - Fundacion compatible sobre v1

- Controles de perfil, celdas y colores con validacion y precedencia documentada.
- Reconstruccion `nearest`/`soft` equivalente en Canvas2D y WebGL1.
- Canvas PIXEL con backing store igual a la grilla; zoom solamente visual.
- Suavizado offline horneado opcional.
- Muestreo de FPS exacto (sin saltos enteros que alteren la duracion).
- Reader sin copias completas del bundle.
- Inflate con buffers tipados reutilizables.
- Pruebas de sintaxis ES5 y round-trip de archivos v1.

Aceptacion:

- Los `.asclv` existentes siguen abriendo.
- Un archivo nuevo sigue abriendo en el player anterior.
- `nearest` conserva la imagen actual.
- `soft` funciona en ambos renderers y puede seleccionarse manualmente.
- No se crea un canvas 4K/8K al reproducir una matriz 1080p.

### Fase B - Paletas temporales y dithering

- Paleta por frame, por bloque temporal fijo y por bloques adaptativos definidos con
  metricas cromaticas numericas.
- El operador fija grilla, FPS, colores y algoritmo; no existe un selector automatico de
  calidad ni una clasificacion de segmentos por IA o revision humana.
- Una paleta nueva siempre comienza en keyframe para mantener seek seguro.
- Dithering ordenado y estable, aplicado solo en gradientes que lo necesiten.
- Sin ruido aleatorio por frame ni dependencia del renderer.

Deteccion de gradientes propuesta:

1. medir rango local de luminancia, magnitud de gradiente y proxy de banding por tile;
2. construir un candidato Bayer determinista solo ante variacion suave;
3. excluir zonas planas y bordes fuertes con umbrales numericos;
4. medir mejora del proxy y cantidad exacta de celdas modificadas;
5. aceptarlo solo si supera la mejora minima, cabe en el presupuesto y respeta la
   histeresis temporal configurada.

La seleccion automatica por clip de colores, resolucion o FPS fue descartada: esos valores
permanecen explicitos. Solo queda pendiente agregar un presupuesto directo de bytes al
dithering. La duracion de paleta ya es adaptativa y el dither ya tiene presupuesto exacto
de celdas e histeresis.

### Fase C - Formato v2 por tiles adaptativos

- Reader dual v1/v2.
- Matriz logica unica de indices.
- Tiles fijos de 16x16 en esta revision.
- Comandos implementados: `SKIP_RUN`, `SOLID`, `SPARSE`, `MASK`, `PACK1`, `PACK2`,
  `PAL4` y `PAL8`, con envolturas regionales crudas/zlib y predictores reversibles.
- `PACK1`, `PACK2`, `PAL4` y `PAL8` cubren paletas locales de 2, 3-4, 5-16 y hasta
  256 indices respectivamente.
- Lista comun de tiles sucios para Canvas2D y WebGL1.
- Eleccion exhaustiva offline de la representacion exacta mas pequena para la misma
  matriz ya aprobada; el fallback v1 por frame impide crecimiento.

El encoder puede consumir mas CPU. El decoder valida y ejecuta la representación ya
elegida —incluidos predictores reversibles—, pero no evalúa candidatos ni calidad
perceptual durante la reproducción.

### Fase D - Motor local de intervencion matricial

- Slots declarados por coordenadas explicitas durante el encode.
- Assets bitmap incluidos en el mismo `.asclv`.
- API ES5 con callbacks: `setSlot`, `setSlotAtFrame`, `clearSlot`.
- Aplicacion en cada dispositivo durante la reproduccion.
- Buffer temporal limitado al rectangulo del slot, nunca un segundo framebuffer.
- Sin deteccion de objetos, rotacion, ramas de rueda ni overlays DOM.

### Fase E - Validacion y seleccion de defaults

El frontend `tv-player.html` y el artefacto HQ permiten medir sin controles de laboratorio
en pantalla. Esta fase no prueba casos para decidir calidad ni alimenta un selector. En
cada familia de Smart TV/WebView se reproducen perfiles fijados manualmente —primero 640
y 768— con la misma fuente aprobada y ambos renderers cuando esten disponibles.

Por ejecucion fisica se registran:

- bytes totales y KB/s;
- tiempo de descarga, parse y decode p50/p95;
- tiempo Canvas2D y WebGL1;
- RAM pico por componente;
- frames descartados;
- cache fria/caliente y revalidacion del nombre estable;
- igualdad de la matriz comun antes de presentar;
- resultado en las Smart TV/WebViews reales.

Una revision visual puede aceptar o rechazar el artefacto ya elegido por el operador, pero
no ordena automaticamente perfiles ni convierte una conclusion de un clip en default.

## 4. Fuera de alcance inicial

- Vision artificial y deteccion de objetos.
- Rotacion o escalado geometrico en runtime.
- Gaussian blur en el navegador.
- Motion vectors que requieran dos framebuffers completos.
- zstd, Brotli o WASM como dependencia obligatoria.
- Reconstruccion 2x en el navegador. Puede investigarse mas adelante como operacion
  offline del procesador de PC si las mediciones lo justifican.
