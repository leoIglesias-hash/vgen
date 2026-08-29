# F3 — carril de calidad del encoder (E-12 a E-18)

**Cerrada el 2026-08-29.** Siete tareas medidas; **una sola adoptada en el
producto**. Ese es el resultado honesto de la fase: la mayoría de las ideas
plausibles no sobrevivieron a su propia medición, y quedaron como opt-in
reproducibles en vez de entrar al fondo por inercia.

## Qué entró al producto

| ID | Qué | Resultado | Estado |
|---|---|---|---|
| E-12 | refit de paleta a la asignación real (Lloyd acotado, aceptación monótona) | **+1,17 dB y −0,59 % de bytes** sobre P-02 | **adoptado** (`--palette-refit 5`) |
| E-13 | cierre de Lloyd en dominio uint8 | PSNR igual, Oklab −0,5 %, bytes +0,36 % | medido, no adoptado (opt-in) |
| E-14 | paleta sobre todos los píxeles, dos pasadas | **RSS 886 → 433 MB (−51 %)**, Oklab −4,5 %, PSNR −0,27 dB | modo global, no es el modo de producto |
| E-15 | estabilidad temporal de paleta ×4 | fronteras −31 %/−93 % en sintético; en el clip real −1,25 % bytes y −1,04 dB por el blending | knob, producto sin cambios |
| E-16 | PairLUT exacto (muere el gate 555) | −0,21 dB, +4,1 % Oklab, +6 % bytes, +39 % tiempo | medido, no adoptado (opt-in `--dither-exact`) |
| E-17 | presupuesto de dither en bytes | mecanismo validado; decisión de producto elevada al operador | opt-in `--dither-byte-budget` |
| E-18 | interacción dither/threshold | corrige un bug real; no toca el producto | **corregido** |

**Fondo de producto al cierre:** `adef9e533b01fdd489ec6dacf1265f07072ecba8d15e88e79b7bd2dd5a5c05bb`
(17.379.859 B, 35,46 dB, Oklab 0,00732), 768 graphic-hq + `--palette-refit 5`,
dither auto. Reproducible desde `main`; P-02 sigue reproducible con el flag en 0.

## E-17 — el presupuesto funciona, la decisión no es numérica

Barrido de cuatro filas (evidencia textual completa en Instancia 023 del
registro):

| config | celdas tramadas | bytes `.asclv` | PSNR | Oklab | wall |
|---|---|---|---|---|---|
| dither auto (producto) | 392.508 | 17.379.859 | 35,46 | 0,00732 | 45:50 |
| budget 450 | 156.947 (40 %) | 17.246.050 | 35,57 | 0,00725 | 48:41 |
| budget 0 | 2 | 17.168.592 | 35,63 | 0,00721 | 49:04 |
| `--dither off` | 0 | 17.168.633 | 35,63 | 0,00721 | 44:21 |

Dos cosas quedaron demostradas:

1. **El knob es continuo y monótono.** 450 B/frame conserva el 40 % de las
   celdas tramadas —las mejor rankeadas por ganancia/costo, porque el recorte
   va por orden de aceptación— y cae proporcionalmente entre los extremos en
   las tres métricas. E-17 hace exactamente lo que prometía.
2. **`budget 0` no es una receta.** Difiere de `--dither off` en 41 bytes, es
   idéntico en todas las métricas, y tarda 4:43 más. Recorre y evalúa todos
   los tiles para terminar rechazándolos. Si el objetivo es no tramar, se
   apaga el dither.

**Por qué no se adoptó «sin dither» pese a ganar en las tres columnas.** Las
dos métricas de calidad registradas —`psnr_rgb_db` y `err_oklab_medio`— son
promedios de fidelidad **por píxel**. El dither cambia exactitud por píxel a
cambio de romper mesetas de color: por construcción esas métricas lo castigan,
y **ninguna de las dos ve banding**, que es lo único que el dither compra. El
ranking monótono hacia «off» es esperable y no es evidencia de que la imagen
se vea mejor. Adoptarlo por esos números habría apagado una función en
silencio llamándolo mejora de calidad.

Consecuencia estructural, anotada como propuesta: con el bench de hoy la regla
del proyecto —«una mejora sin fila registrada no existe»— **no puede aplicarse
a lo que el dither mejora**. Falta una columna de proxy de banding en
`tools/bench_ref.py`.

La elección **dither on / 450 / off** quedó del operador, con los `preview.mp4`
de las corridas 33231255094 y 33231247505. Si elige «off», la receta es
`--dither off` y el fondo pasa a `74be25ef…a011f9` (17.168.633 B, −1,23 % de
bytes, 1:29 menos de encode).

## E-18 — un bug real que el producto no estaba sufriendo

El threshold corre **después** del dither y revertía celdas al valor del frame
anterior cuando el color apenas se movía. Sobre una celda tramada eso deshacía
la decisión del dither y rompía el patrón Bayer de forma distinta en cada
frame — y era sistemático, porque una celda tramada difiere de su predecesora
justo por un vecino de paleta, exactamente la distancia que el threshold lee
como «sin cambio».

El revert ahora excluye lo que el dither movió (`keep &= ~dither_changed_mask`,
solo cuando `threshold > 0` y modo pixel), con contadores
`threshold_dither_protected_cells/_frames` que encoder y make_clip imprimen.

**No cambia el producto:** `--threshold` es 0 por defecto y el perfil HQ nunca
lo pasa, así que `adef9e53…` sigue byte-idéntico (regla 5). El bug estaba
esperando a quien combinara ambos flags.

## Regresión

CI en verde con **256 pruebas Python y 26 suites JS** (base de la fase: 244 y
26). Tests nuevos: `tests/test_dither_byte_budget.py` (8) y
`tests/test_dither_threshold.py` (3), este último autocalibrado —barre umbrales
hasta encontrar uno que realmente pise celdas tramadas— para no quedar vacío
si la paleta de kmeans cambia.

## Qué sigue

- **F5 — E-19**: congelar el orden canónico cuantizar → ditherear → trellis →
  emitir, absorbiendo `--threshold` como caso degenerado del trellis.
- **S-7**: barrido de resolución 768 → 1280 → 1920, agendado después de F5.
- Decisión abierta del operador: dither on/450/off, y el 960 si lo retoma
  (habría que re-medirlo con refit 5).
