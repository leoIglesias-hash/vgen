# Diseño de dithering selectivo offline

> **Diseño histórico.** La implementación actual incluye `off|selective|auto`, presupuesto
> de celdas, histéresis y guardas. Estado y resultados: `BENCHMARK-V1-ADAPTATIVO-OKLAB.md`
> y `REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`.

## Objetivo y alcance

Reducir bandas visibles al usar paletas pequeñas sin trasladar trabajo al navegador ni
romper la paridad Canvas2D/WebGL. El dithering se hornea en el encoder y el archivo
continúa almacenando índices de paleta normales. No requiere cambios en `.ascl` v1,
el reader, los renderers ni el costo algorítmico de reproducción.

La primera implementación se limita a `MODE_PIXEL`. Luego puede reutilizarse para el
plano de color de `MODE_ASCII_PAL`, pero nunca para elegir glifos.

## Decisiones obligatorias

- Usar dithering ordenado, determinista y selectivo.
- No usar Floyd–Steinberg, ruido aleatorio ni error diffusion: elevan la entropía,
  perjudican DELTA/zlib y pueden parpadear entre frames.
- Crear la paleta a partir del RGB sin dithering y aplicar el tramado después.
- Anclar el patrón a coordenadas absolutas; nunca variar su fase por frame o tile.
- Conservar exactamente la cuantización normal en texto, líneas y bordes protegidos.
- Someter cada candidato a límites explícitos de bytes y celdas modificadas.
- No agregar flags al contenedor: el resultado son índices de paleta comunes.

## Pipeline

```text
resize / soft-bake
→ crear paleta sin dithering
→ cuantización normal Q0
→ análisis de gradientes y bordes por tiles
→ candidato con dithering Q1
→ evaluar calidad, peso y estabilidad temporal
→ elegir Q0/Q1 por GOP
→ umbral temporal existente
→ codec RAW/ZLIB/DELTA existente
```

El orden respecto del umbral temporal deberá validarse con A/B. La propuesta inicial
es aplicar el umbral después del dithering para contener cambios pequeños; cada cambio
de paleta comienza con keyframe y reinicia ese estado.

## Detección automática por tiles

Tamaño inicial: 16×16 celdas. El análisis se realiza sobre el RGB ya redimensionado.
No hay detección semántica ni visión artificial.

Para cada tile se calculan:

- rango de color entre percentiles 5 y 95;
- diferencias horizontales y verticales RGB;
- residuo respecto de un box blur 5×5;
- segunda derivada/Laplaciano;
- densidad de bordes;
- error de la cuantización Q0.

Luminancia entera y determinista:

```text
Y = (77·R + 150·G + 29·B) >> 8
```

Un tile es candidato si tiene variación continua, poca textura, baja densidad de
bordes y Q1 mejora la reconstrucción suavizada frente a Q0. Umbrales iniciales a
calibrar:

- rango de color ≥ 8;
- RMS contra blur ≤ 6;
- píxeles protegidos < 10%;
- mejora de error de baja frecuencia ≥ 5–8%.

Para proteger bordes, incluido color con luminancia parecida, se usa el máximo
gradiente de R/G/B. Máscara inicial:

```text
gradiente RGB ≥ 24  o  Laplaciano ≥ 18
```

La máscara se dilata una celda. Q1 debe ser idéntico a Q0 dentro de ella. Si la
protección ocupa 10% o más del tile, se rechaza el tile completo. Esto protege texto,
números, líneas finas y contornos sin necesitar reconocerlos.

## Patrón y mezcla de paleta

Patrón recomendado: Bayer 4×4.

```text
 0  8  2 10
12  4 14  6
 3 11  1  9
15  7 13  5
```

Para cada color fuente se eligen dos colores cercanos de la paleta y se proyecta el
color sobre el segmento que forman. La cobertura se limita a cinco niveles para
favorecer patrones repetibles y compresión:

```text
0%, 25%, 50%, 75%, 100%
```

Se rechaza la pareja si sus colores están demasiado separados o desvían el tono. Para
evitar búsquedas costosas por píxel, cada paleta puede generar una LUT RGB de 5 bits
por canal:

```text
32 × 32 × 32 entradas → índice A, índice B, nivel de mezcla
```

Bayer 2×2 se conserva como variante `compact`: puede comprimir mejor, aunque el
patrón es más visible. Bayer 4×4 es el candidato de calidad.

## Estabilidad temporal

La aptitud del tile no se decide de forma aislada en cada frame:

- paleta global: analizar y fijar la decisión por GOP/keyframe;
- paleta por bloque: fijarla durante todo el bloque;
- paleta por frame: analizar en ventanas de aproximadamente un segundo.

Umbrales iniciales de histéresis: activar cuando el tile es apto en al menos 70% de la
ventana y desactivar por debajo de 45%. La máscara de bordes sí se recalcula por frame.

En regiones donde la fuente casi no cambia, se compara el cambio temporal de Q1 con
el de la fuente y Q0. Si Q1 agrega parpadeo, ese tile vuelve a Q0. Este guard es
obligatorio con paleta por frame.

### Relación con las paletas

- `global`: máxima estabilidad y mejor DELTA; una sola LUT para el clip.
- `block`: opción recomendada. Cada bloque crea su paleta, comienza con paleta y
  keyframe completo, y habilita DELTA internamente. Probar bloques de `fps`, `2×fps`
  y `4×fps`; el valor inicial puede coincidir con `keyint`.
- `per-frame`: máxima adaptación cromática, pero paga paleta completa, impide DELTA
  de índices y es más propensa a flicker. Se conserva como opción y referencia, no
  como default.

La paleta por bloque usa la semántica v1 existente: `palCount > 0` actualiza la
paleta y el frame de inicio es completo. No requiere trabajo nuevo del runtime.

## Selección por presupuesto

La optimización debe realizarse por GOP, donde el estado DELTA queda contenido. Para
cada GOP se prueban:

- Q0 sin dithering;
- Q1 sobre el 25%, 50%, 75% y 100% de los tiles aptos, ordenados por ganancia
  visual/costo;
- opcionalmente Bayer 2×2 y 4×4.

Cada variante pasa por el codec real. Se miden bytes finales, celdas modificadas,
error visual suavizado y error temporal. Se elige la de mayor calidad que cumpla los
dos presupuestos:

- sobrepeso de video respecto de Q0;
- aumento de celdas modificadas respecto de Q0.

El segundo límite evita reducir bandas a costa de más trabajo DELTA o más tiles
sucios en dispositivos antiguos. El porcentaje de tamaño se calcula sobre el flujo
de video, no sobre el bundle con audio.

## Opciones CLI propuestas

```text
--dither off|selective|full
--dither-matrix 2|4
--dither-tile 16
--dither-max-overhead 2
--dither-change-overhead 5
--palette global|block|per-frame
--palette-block-frames 30
```

Interfaz simple del procesador:

- Desactivado.
- Selectivo compacto (Bayer 2×2).
- Selectivo equilibrado (Bayer 4×4, recomendado).
- Completo (diagnóstico, no recomendado para producción).

`--dither-max-overhead 2` permite como máximo 2% sobre Q0. Un perfil de tamaño
estricto usa 0%. Los umbrales de detección deben quedar como opciones avanzadas o de
laboratorio, no en la interfaz principal.

## Integración backend

Se recomienda un módulo `backend/dither.py` con funciones puras:

```text
edge_mask(rgb)
tile_scores(rgb, baseline_rgb)
build_temporal_plan(frames, baseline_indices)
make_pair_lut(palette)
apply_ordered_dither(rgb, baseline, palette, plan)
score_candidate(source, baseline, candidate)
```

`encoder.py` debe separar creación de paleta, cuantización e integración de celdas
para poder producir Q0 y Q1 sin duplicar lógica. La salida elegida entra al codec
actual como cualquier matriz de índices.

## Pruebas A/B

Fixtures sintéticos mínimos:

- gradiente gris y cromático con luminancia constante;
- gradiente radial;
- fondo plano con texto de un píxel;
- líneas finas y tablero;
- texto desplazándose sobre un gradiente;
- gradiente animado;
- corte brusco entre escenas.

Matriz principal: 64/128 colores; paleta global/block/per-frame; sin dithering,
selectivo 2×2, selectivo 4×4 y completo; con/sin `soft-bake`.

Métricas:

- bytes totales y por frame;
- distribución RAW/ZLIB/DELTA;
- cantidad de celdas modificadas;
- error RGB de baja frecuencia después de box blur;
- longitud/área de bandas constantes;
- error en bordes protegidos;
- flicker en píxeles de fuente estable;
- hash determinista de salida.

Criterios iniciales de aceptación:

- cero diferencias entre Q0 y Q1 dentro de la máscara de bordes;
- mejora ≥ 8% del error de baja frecuencia en tiles elegidos;
- bytes y celdas cambiadas dentro de sus presupuestos;
- flicker no más de 5% peor que Q0;
- salida byte-idéntica al repetir la misma codificación.

## Orden de implementación

1. Implementar y verificar paletas por bloque.
2. Separar cuantización Q0 de la creación de celdas.
3. Implementar máscara de bordes y score de gradientes por tile.
4. Implementar LUT de pares y Bayer selectivo 4×4; agregar 2×2 después.
5. Incorporar agregación temporal e histéresis.
6. Incorporar selección exacta por presupuestos al nivel de GOP.
7. Ejecutar y documentar A/B; calibrar umbrales antes de cambiar defaults.

Candidato inicial: paleta por bloque, 64 o 128 colores, tile 16, Bayer 4×4 y
sobrepeso máximo de video de 2%.
