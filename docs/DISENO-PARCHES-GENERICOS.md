# Diseño — parches genéricos de imagen (INT-003, propuesta)

Estado: **pedido del operador, 2026-08-28. Sin diseño cerrado ni implementación.**
Es la generalización de INT-001 (que quedó implementada y cerrada en F7/S-5).
La próxima sesión arranca por acá si el operador lo confirma.

## 1. Pedido del operador (literal, 2026-08-28)

> Reemplazar, más allá de números, **zonas de video** con **imágenes que
> convertiremos al formato adecuado** y que luego serán lo que reemplace.
> Así podríamos usar **cualquier tipografía**, y un **random en el momento
> (línea de tiempo) y ubicación (x, y)** adecuados nos daría números al azar;
> pero también podría **reemplazar una ruleta al final de su giro** para que
> coincida en su totalidad con el juego (como ejemplo).

## 2. Lectura técnica

Hoy (F7) la unidad de asset es el **glifo**: 11 parches fijos de
`glyph_w × glyph_h`, cuantizados a las 10 entradas reservadas (246..255), en
slots de posición fija con ventana temporal `start..end`. El pedido pide tres
generalizaciones, en orden de dificultad:

1. **Parche = imagen arbitraria horneada offline.** El pipeline ya existe en
   embrión: `bake_glyphs.py` renderiza desde una fuente real (cualquier
   tipografía vía `--font`), downsamplea y cuantiza al rango reservado. La
   generalización es una tabla de N parches de tamaños heterogéneos (hoy el
   tamaño es uniforme y el área ≤4096 celdas por parche).
2. **Selección dinámica de parche + posición + momento.** El sidecar ya tiene
   por slot `x, y, start_frame, end_frame`: la "aleatoriedad" no necesita
   runtime nuevo, necesita que el **dato** (canal o generador local) elija
   *qué parche* va en *qué slot* y que existan slots declarados en los
   lugares/momentos candidatos. Alternativa más flexible: slots con posición
   variable dentro de una zona declarada (rompe la validación estática de
   solape → decidir).
3. **Caso ruleta:** un parche grande que reemplaza la zona de la ruleta en los
   frames finales del giro, elegido entre N variantes pre-horneadas (una por
   resultado posible), para que el video termine mostrando el resultado real
   del juego. Es INT-001 con parche grande + ventana temporal corta: el
   mecanismo de restauración/marcado ya lo soporta tal cual.

## 3. Decisiones abiertas (resolver ANTES de implementar)

| # | Decisión | Opciones | Tensión |
|---|---|---|---|
| D1 | Paleta de los parches | (a) solo las 10 reservadas (como hoy); (b) ampliar la reserva (>10 cuesta paleta base); (c) permitir que un parche use **índices base** de la época vigente, horneado por época offline | (a) limita a arte de 9 colores + transparencia — alcanza para tipografía, no para una ruleta fotográfica. (c) da paleta completa pero **rompe la verificabilidad de INV-3** ("toda celda ≥246 es overlay") y ata el parche a las épocas del clip (re-hornear si se re-encodea) |
| D2 | Presupuesto de área | mantener 5% de grilla (§6.3) o subirlo para parches grandes | una ruleta de 200×200 celdas en 768×432 es ~12%: el presupuesto actual la rechaza. El 5% protege RAM y costo por frame del TV — si se sube, medir en F8 |
| D3 | Límite por parche | hoy `glyph_w*glyph_h ≤ 4096` | una ruleta lo excede; subirlo infla el sidecar (sigue siendo chico: N parches × área) |
| D4 | Posición | slots fijos declarados (hoy) vs. zona + offset elegido por el dato | la posición por dato obliga a validar solape/grilla **en runtime** (hoy es estático); el random puede resolverse igual con muchos slots fijos candidatos y activación selectiva |
| D5 | Formato del canal | hoy: dígitos posicionales | generalizar a `slot_id → patch_id` mantiene la validación en 5 pasos (todo numérico, rangos declarados) |
| D6 | Versionado | extender ASCLSLOT v2 (sidecar) ahora, o esperar a `ASCLVID3` (F6/S-4) y diseñar una sola vez | dos migraciones de formato cuestan más que una; pero F6 aún no tiene fecha |

**Recomendación preliminar** (a validar con el operador): tipografía libre y
números random salen casi gratis con el mecanismo actual (D1=a, D4=slots
candidatos, D5 generalizado); la ruleta exige D1..D3 y conviene diseñarla
junto con `ASCLVID3` (D6) para no migrar el sidecar dos veces.

## 4. Qué NO cambia

- Un solo layer, una matriz, restauración antes de decodificar (INT-001 §9.2):
  el runtime de F7 (`overlay.js`) ya es agnóstico al contenido del parche —
  pinta índices y restaura bytes. La generalización es de **metadata y
  horneado**, no del bucle por frame.
- Validar todo antes de mutar; el dato de red jamás elige URL ni indexa fuera
  de las tablas declaradas; serial monotónico; INV-7.
- El costo se paga offline: los parches se hornean y cuantizan en el encoder;
  el TV solo copia índices.

## 5. Interacción con el roadmap

- **F3 (E-12..E-18)** sigue siendo el carril de compresión y no choca: solo
  debe respetar la reserva (ya cableado tras F7).
- **F6 (S-4 / ASCLVID3)** es el punto natural para congelar ASCLSLOT v2 si D6
  se decide "una sola migración".
- **F8** deberá medir MEM-001/costo con el parche más grande aprobado (D2/D3).
