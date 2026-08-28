# INT-006 — fondo sin reserva + texto standalone + imagen nativa (2026-08-28)

Pedido del operador (post-demo INT-004): re-procesar el fondo sin la
intervención de píxeles con números (ya no sirve: el texto es nativo), con
la máxima calidad de las herramientas existentes, dejando las fuentes
activas interviniendo; después, probar la intervención con una imagen.

## INT-006-A — fondo HQ `overlay=off` (dispatch, sin cambios de código)

- Dos encodes del workflow `encode` (`overlay=off`, zopfli, tile 16,
  adaptive/kmeans-oklab, dither auto, 15 fps, v2), fuente TKN-2443 de la
  rama `assets` (verificada byte-idéntica al archivo local del operador,
  blob `c92958d3…`):
  - **graphic-hq 768** (run 33193293258): 17.482.270 B,
    `ebfe2eb4…4b36` — **reproduce byte a byte la referencia P-02/E-08**
    (determinismo confirmado); PSNR 34,29 / Oklab 0,00793. La base
    recupera los 256 colores (+0,24 dB vs el clip de parches).
  - **graphic-ultra 960** (run 33193299286): 25.003.004 B,
    `31348a83…5688`; PSNR 34,40 / Oklab 0,00776 — +0,11 dB a +43 % de
    bytes. Queda como dato; el 768 sigue de producto (valores del
    operador prevalecen).
- `outputs/`: clip 768 instalado (SHA verificado); `clip.slots` y
  `data.txt` viejos **borrados**. Registro: Instancia 017.

## INT-006-B — texto nativo standalone (`49e2b4a` + fix `2c81856`)

- `frontend/textfeed.js` (ES5): `ASCILINETextFeed.create(capa, campos)`
  → `{digitCount, setValues}` — la MISMA interfaz que consume
  `datachannel.js` (sin cambios). Todo-o-nada: forma validada antes de
  probar ids; payload completo validado (longitud exacta, solo dígitos
  ASCII) antes de escribir un solo campo; `create` deja los campos
  vacíos (estado inicial determinista).
- live-player: sin overlay de matriz (sin sidecar, attach nulo, sidecar
  rechazado o clip sin paleta completa) declara 3 campos de 2 dígitos por
  tercios (dimensionados por cols/rows, serif dorada con borde);
  «Simular carga» y el canal de datos los alimentan; `data.txt` ausente =
  canal con backoff (INV-7). Limpiar en standalone vacía los textos y
  repinta sin re-seek.
- Suite `test_textfeed.js` (mock + capa real + compatibilidad con
  `datachannel._handleText`) cableada en `run_all.py` (26 suites JS);
  `test_live_player_page.js` cubre el modo standalone.
- CI rojo intermedio en `49e2b4a`: un backtick en un comentario del
  script inline volteó el gate ES5 del test de página; fix hacia
  adelante `2c81856` (verde).

## INT-006-C — imagen del operador, decisión D7 = (a) nativa (`3e51ce8`)

- El operador entregó `inputs/logonuevo150.png` (logo TeleKino con alfa).
  **D7 resuelta en (a)**: `outputs/logo.png` (opcional) se dibuja con
  `drawImage` sobre el MISMO canvas después del texto — caja en celdas
  (cols/4, aspecto preservado, esquina superior derecha) marcada sucia
  cada frame; solo activa con texto declarado (renderer ya Canvas2D con
  `pixelScale`); 404 = nada cambia (INV-7). Cero costo de paleta; el
  gráfico no es byte-verificable (misma propiedad documentada que el
  texto). (c) INT-005/época sigue como definitivo para la ruleta; (b)
  reserva 32 disponible si hiciera falta byte-verificación antes de F6.
- Verificado en navegador sobre el clip de parches Y sobre el fondo
  nuevo: logo nítido y persistente en play/pausa/zoom/clear.

## Cierre de etapa

Player local (serve-local, puerto 8123, no-store) con el fondo nuevo:
attach standalone, carga simulada cambia los 3 números, zoom 2 nítido
(backing 1536×864), limpiar restaura el fondo con el logo, consola limpia
salvo los 404 esperados. Regresión: 199 pruebas Python + 26 suites JS en
verde (commits `49e2b4a` rojo→`2c81856`, `3e51ce8`, `bd32e3d`).
