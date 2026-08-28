# INT-004 — texto nativo en el mismo canvas (cerrado 2026-08-28)

Pedido del operador tras la demo INT-003: los números dentro de la matriz se
pixelan (el piso físico es la celda y el horneado v2 no tiene antialias).
Pregunta literal: «¿no se puede dibujar en el mismo canvas el texto? eso
sería ideal». Sí se puede: los TEXTOS se dibujan con `strokeText/fillText`
sobre el MISMO elemento canvas, después de pintar el frame; la matriz queda
para gráficos. Diseño en `DISENO-PARCHES-GENERICOS.md` §10.

## Tareas

| ID | Commit | Qué |
|---|---|---|
| INT-004-A | `21df177` | `frontend/textlayer.js` (ES5, sin dependencias): `ASCILINETextLayer.create(items)` todo-o-nada — item = caja en celdas (x,y,w,h), `size` (altura en celdas), `color`, `outline`, `font`, `align`, texto inicial; `setText(id,str)` valida y conserva el último estado válido (INV-7); `markDirty(reader)` marca vía `markRectDirty` las cajas con texto dentro de la grilla; `draw(ctx,cellPx)` pinta borde→relleno limitado al ancho de la caja (`maxWidth`) con cache de string de fuente y anclajes por `cellPx` (cero allocaciones en el camino caliente). Suite `test_textlayer.js` cableada en `run_all.py` en el mismo commit. |
| INT-004-B | `76ffe45` | Integración en `live-player.html`: con sidecar v2, cada campo de dígitos con slots grandes (≥20 celdas) se espeja como texto serif con borde al costado de su posición; el wrap de `overlay.setValues`/`overlay.clear` hace que TODO payload aceptado (botón «Simular carga» o canal de datos) alimente matriz y texto a la vez. `pickRenderer` elige Canvas2D cuando hay texto (regla 6: WebGL no gana funciones) con `pixelScale=zoom`. Orden por frame: `beforeSeek → seek → afterSeek → markDirty(texto) → renderer.draw → textLayer.draw`. |

## Desvío técnico (registrado en la bitácora)

En modo PIXEL el backing store del Canvas2D era cols×rows (zoom solo CSS): el
texto nativo se habría pixelado igual. Se agregó `renderer.pixelScale`
(opt-in, default 1 **byte-idéntico al histórico**): backing cols·s×rows·s,
frame chico con `putImageData` + un `drawImage` del canvas **sobre sí mismo**
(la spec exige snapshot del origen) — sin segundo canvas. Con escala el put es
siempre completo, y el player marca todas las cajas declaradas por frame para
que borrar un texto no deje fantasma. Cubierto por
`test_frontend_renderers.js` (backing, blit al mismo canvas, put completo con
dirty parcial, cuadro repetido re-copiado, normalización de escala inválida).

## Cobertura

- `test_textlayer.js` (suite nueva, 25.ª de JS): create todo-o-nada (30+
  rechazos), defaults, INV-7 en setText, cajas exactas de markDirty, escalado
  y anclajes por align, orden stroke→fill, cache por cellPx, clamp de
  lineWidth.
- `test_live_player_page.js`: orden por frame con texto, elección de renderer
  (WebGL solo sin texto), `pixelScale=zoom`, espejo alimentado por los mismos
  payloads, clear conjunto, solo-v2 y solo-slots-grandes.
- `test_frontend_renderers.js`: camino `pixelScale` completo + default 1 sin
  cambios.
- Gate ES5 (`test_frontend_compatibility.js`) escanea `textlayer.js` y el
  inline del player automáticamente.

## Propiedades aceptadas y documentadas

- El texto nativo NO vive en la matriz: no es byte-verificable ni queda en el
  video decodificado (a diferencia de los parches de INT-003).
- Con texto declarado el renderer es Canvas2D; WebGL sigue siendo solo
  aceleración del camino sin texto.
- El caso «video de fondo en loop + números arriba» queda cubierto por
  INT-004 solo (sin sidecar de parches, si se declaran items a mano).

Fix posterior (`07bc0da`, encontrado verificando el player en navegador):
«Limpiar panel» dibuja sin re-seek — `clear()` deja los rects restaurados
marcados y el seek del mismo frame los reseteaba (los dígitos persistían en
pantalla). Test de página fija el camino.

Regresión al cierre: 199 pruebas Python + 25 suites JS en verde
(commits `21df177`, `76ffe45` y `07bc0da`, workflow `regression`).
Verificado en navegador: attach «texto nativo: 3 campos espejados», carga
simulada actualiza matriz y texto juntos, zoom 2 = backing 1536×864, play
con textos persistentes sobre el video, clear deja el frame base limpio.
