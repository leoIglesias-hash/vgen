# INT-003 — parches genéricos de imagen (vía corta) · cerrado 2026-08-28

Pedido del operador tras F7: reemplazar zonas de video con imágenes horneadas
(cualquier tipografía, random de momento/posición, y a futuro la ruleta que
coincide con el resultado). Decisiones D1..D6 resueltas con él en sesión;
diseño en [`../DISENO-PARCHES-GENERICOS.md`](../DISENO-PARCHES-GENERICOS.md).
La **ruleta** quedó explícitamente para `ASCLVID3` (F6/S-4).

## Tareas y commits

| ID | Qué | Commit |
|---|---|---|
| diseño | D1..D6 resueltas + spec ASCLSLOT v2 + plan A..F | `0222e98` |
| INT-003-A | reserva ampliada a 32 (224..255), cola F7 bit-idéntica; `--reserved 0/10/32` | `7156fd9` |
| INT-003-B | ASCLSLOT v2 en Python: parches heterogéneos, `kind` 0/1, presupuestos 5% por frame (barrido de eventos) + RAM 25%, solape espacial solo con ventanas disjuntas | `735eee3` |
| INT-003-C | `slots.js` espejo v2: corpus de 35 fixtures generado por Python, mismo veredicto y mensaje byte a byte | `5e03091` |
| INT-003-D | runtime v2 (`overlay.js` + `overlay_ref.py`): `values` u16 con `NONE`, campos de elección, dígito de presencia canónico; v1 byte-idéntico (suite F7 intacta); cruz Python/JS sobre clip real `reserved=32`; `datachannel.js` sin cambios | `8c3e55f` |
| INT-003-E | `bake_patches.py`: texto con cualquier TTF/color y PNG con alpha → nearest Oklab en 224..254, alpha→transparencia; determinista | `7f0e3d1` |
| INT-003-F | `make_patch_pack.py` (demo: panel v2 + 3 números grandes serif por tercios + palabra de elección), `live-player.html` paramétrico, workflow `overlay=off/panel/patches` | `da28408` |

## Evidencia clave

- **Instancia 015** (registro): costo de la reserva de 32 sobre el sintético
  −0,47 dB PSNR / +0,00092 Oklab, archivo ~5% menor (runs 33174111941 /
  33174113632).
- **Instancia 016** (registro): clip HQ `overlay=patches` publicado y
  verificado en navegador con números en tipografía libre apareciendo por
  tercios y palabra de elección por presencia.
- Byte-identidad cruzada v2: 8 frames Python/JS sobre clip real del encoder
  con `reserved=32` (`test_overlay_ref_v2.py` + `test_overlay_v2_cross.js`),
  cargas cruzando el keyframe, `clear()` byte-idéntico.
- Un sidecar v1 sigue siendo válido sobre un clip de 32 (la cola 246..255 no
  cambió) — compat probada en `test_reserved_extended.py`.

## Qué NO se hizo (a propósito)

- Ruleta (parche grande ~12%, D2/D3 revisados): diseño junto a `ASCLVID3` en
  F6/S-4, una sola migración de formato adicional.
- Gates físicos (p95, MEM-001) con el peor frame v2: F8, como estaba.
