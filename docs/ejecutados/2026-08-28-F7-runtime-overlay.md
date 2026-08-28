# F7 — Runtime de la intervención matricial (S-5), cerrado 2026-08-28

Lote completo del runtime del overlay (INT-001): el mecanismo que escribe
resultados en vivo como índices de paleta reservados (246..255) sobre la misma
matriz de celdas del video, sin segundo canvas ni capa DOM. Cada commit con CI
`regression` en verde. Evidencia de medición: Instancia 014 del registro.

## Piezas

| Pieza | Archivo(s) | Commit |
|---|---|---|
| F7-1 estado y orden por frame (§9.2) + F7-2 API ES5 | `frontend/overlay.js`, `tests/test_overlay_runtime.js` | `b5775d0`+`34f72b6` |
| F7-3 canal de datos (5 pasos, serial monotónico, backoff ≤5 min) | `frontend/datachannel.js`, `tests/test_overlay_datachannel.js` | `df6229a` |
| F7-4 referencia Python + verificación cruzada byte-idéntica | `backend/overlay_ref.py`, `tests/test_overlay_ref.py`, `tests/test_overlay_cross.js` | `35a54b3` |
| Integración encoder: `--reserved 10`, panel canónico, workflow | `backend/overlay_palette.py`, `backend/overlay_panel.py`, `backend/make_clip.py`, `tools/make_panel.py`, `.github/workflows/encode.yml` | `7954bc8`+`fe055de` |
| Página del runtime real (reemplaza la demo de laboratorio) | `frontend/live-player.html`, `tests/test_live_player_page.js` | `243600b` |
| Dither excluye los rects del panel (INT-001 §11) | `backend/dither.py` (`protected_rects` en `apply_calibrated_dither`), `encoder.encode_video(protect_panel=…)` | `fe055de`+`0d6d7d7` |

## Contratos que quedaron demostrados

- **Orden por frame obligatorio**: restaurar → decodificar → guardar/pintar/
  marcar. El test incluye el control negativo (saltear la restauración +
  cambio de valor ⇒ la matriz diverge).
- **Byte-identidad**: reproducción con overlay y `clear()`/seek atrás/reinicio
  de loop deja `cells` idéntico a la reproducción sin overlay; y el runtime JS
  es byte-idéntico a la referencia Python sobre un clip real del encoder con
  `reserved=10` (8 frames, cargas cruzando un keyframe).
- **Todo-o-nada e INV-7**: datos inválidos (longitud, caracteres, serial
  repetido o retrocedido, campo fuera de rango, respuesta vacía o gigante) no
  escriben nada, conservan el último estado válido y nunca interrumpen la
  reproducción; backoff solo ante error de red, acotado a 5 minutos.
- **Un solo layer e INV-2**: `overlay.base`/`overlay.values` se reservan una
  vez en `attach` (identidad verificada tras el loop); el marcado usa
  `markRectDirty` de W-13 (unión de rect anterior y actual).
- **Defensa de despliegue**: `attach` exige paleta completa (256) y cola
  246..255 idéntica al `reserved_rgb` del sidecar; un sidecar viejo junto a un
  video nuevo simplemente no activa el overlay.
- **Dither y panel**: con `--reserved 10`, las celdas dentro de los 40 rects
  del panel son idénticas al encode con dither off (selective vía encoder y
  auto directo, ambos con control de no-vacuidad).

## Uso de producto

- Encode con overlay: workflow `encode` con `overlay=on` → publica
  `clip.asclv` (paleta con reserva) + `clip.slots` (panel de 20 números de dos
  dígitos, dos filas de diez, geometría `backend/overlay_panel.py`).
- Reproducción local: `tools/serve-local.ps1` + `frontend/live-player.html`
  (`http://localhost:8123/live-player.html`), que además consulta
  `outputs/data.txt` (`<serial8>|<40 dígitos>\n`) cada 15 s.

## Pendiente diferido (decidido, no olvidado)

- Costo p95 y MEM-001 con overlay: se miden en el TV real (F8-2/F8-4).
- Migración del sidecar a `ASCLVID3`: F6 (S-4).
- Trellis (F5): debe excluir los rects del panel — mecanismo ya plumbeado.
