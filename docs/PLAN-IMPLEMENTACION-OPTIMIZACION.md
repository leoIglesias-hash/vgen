# Plan de implementacion - calidad, eficiencia y compatibilidad

Fecha de inicio: 2026-08-11  
Rama: `feature/quality-optimization`  
Base recuperable: commit `1c2c0b2`

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

Estado al 2026-08-11:

- Fase A implementada y validada en la rama de trabajo.
- Fase B iniciada: paleta global, por frame y por bloque temporal ya disponibles.
- Dithering selectivo es el siguiente cambio de codigo; tiles v2 y slots permanecen en diseño.

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
| `--profile color` | Menos celdas y mas colores. |
| `--profile custom` | Usa solamente valores manuales. |
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

- Paleta por frame, por bloque temporal y por escena.
- El encoder prueba alternativas y elige por relacion calidad/peso.
- Una paleta nueva siempre comienza en keyframe para mantener seek seguro.
- Dithering ordenado y estable, aplicado solo en gradientes que lo necesiten.
- Sin ruido aleatorio por frame ni dependencia del renderer.

Deteccion de gradientes propuesta:

1. medir rango local de luminancia y magnitud de gradiente por tile;
2. aplicar dithering solo si hay variacion suave y riesgo de banding;
3. excluir texto, bordes fuertes y zonas planas;
4. comparar el peso comprimido con y sin dithering;
5. conservarlo solo si la mejora visual supera el costo configurado.

### Fase C - Formato v2 por tiles adaptativos

- Reader dual v1/v2.
- Matriz logica unica de indices.
- Tiles de 16x16 y 32x32 evaluados offline.
- Comandos candidatos: `REPEAT`, `SKIP`, `SOLID`, `SPARSE`, `PAL4`, `PAL8`, `ZLIB`.
- Paleta local de 4 bits (`PAL4`) o indices de 8 bits (`PAL8`) en la v2 minima.
- Packing de 5, 6 y 7 bits se agrega solo si los benchmarks demuestran una ganancia neta
  frente al costo de desempaquetado en dispositivos viejos.
- Lista comun de tiles sucios para Canvas2D y WebGL1.
- Eleccion exhaustiva offline del candidato mas pequeno que cumpla calidad.

El encoder puede consumir mas CPU; el decoder solo copia, desempaqueta o infla el
candidato ya elegido.

### Fase D - Motor local de intervencion matricial

- Slots declarados por coordenadas explicitas durante el encode.
- Assets bitmap incluidos en el mismo `.asclv`.
- API ES5 con callbacks: `setSlot`, `setSlotAtFrame`, `clearSlot`.
- Aplicacion en cada dispositivo durante la reproduccion.
- Buffer temporal limitado al rectangulo del slot, nunca un segundo framebuffer.
- Sin deteccion de objetos, rotacion, ramas de rueda ni overlays DOM.

### Fase E - Validacion y seleccion de defaults

Variantes iniciales a producir sobre los clips de prueba:

| Variante | Celdas | Colores | Reconstruccion | Bake |
|---|---:|---:|---|---|
| referencia | 320x180 | 256 | nearest | none |
| equilibrada | 640x360 | 128 | soft | none |
| detalle 64 | 960x540 | 64 | soft | none |
| detalle 128 | 960x540 | 128 | soft | none |
| horneada 64 | 640x360 o superior | 64 | nearest | soft |
| adaptativa | 960x540 | 64-128 | soft | segun tile |

Por variante se registran:

- bytes totales y KB/s;
- tiempo de encode;
- tiempo p50/p95 de decode;
- tiempo Canvas2D y WebGL1;
- RAM pico estimada;
- frames descartados;
- PSNR/SSIM y revision visual;
- igualdad de la matriz comun antes de presentar;
- resultado en las Smart TV/WebViews reales.

## 4. Fuera de alcance inicial

- Vision artificial y deteccion de objetos.
- Rotacion o escalado geometrico en runtime.
- Gaussian blur en el navegador.
- Motion vectors que requieran dos framebuffers completos.
- zstd, Brotli o WASM como dependencia obligatoria.
- Reconstruccion 2x en el navegador. Puede investigarse mas adelante como operacion
  offline del procesador de PC si las mediciones lo justifican.
