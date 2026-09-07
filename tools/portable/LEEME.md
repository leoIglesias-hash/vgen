# vgen-portable — el encoder fuera del CI (P-008)

Una carpeta. No instala nada: ni Python, ni ffmpeg, ni PATH, ni registro.
Descomprimir donde se quiera y usar desde ahí.

## Emitir el pack v1 del master producto

```
emitir.cmd
```

Baja el master (`clip.dcd6afb66907.asclv`, verificado por SHA-256, una sola
vez; queda en `work\`), corre el mismo `tools/emit_v1.py` que el CI con la
receta v1 vigente, y deja en `outputs\v1\`:

| pieza | qué es |
|---|---|
| `v1-vp9.webm` | VP9 + Opus (la base) |
| `v1-h264.mp4` | H.264 High + AAC (el piso) |
| `v1-ambiente.mp3` | la pista del master suelta (radio) |
| `dash-vp9\` | VP9 segmentado por remux (MSE) |
| `MANIFEST-v1.tsv` | id, bytes, SHA-256, MIME de cada pieza |

Al final imprime el **SHA-256 de cada pieza**. Ese número se compara contra
el resumen del workflow `portable` en GitHub, que emite con **este mismo
bundle** en dos runners de Windows y publica `pack-v1` solo si los dos dieron
los mismos bytes. **El bundle manda** (P-008b, decisión del operador
2026-09-06): si el SHA local coincide con el del resumen, el pack local **es**
el pack publicado. Si no coincide, algo cambió en la máquina (otro
`VERSIONES.tsv`, otro máster, otra receta): mandar las dos líneas de abajo.
La emisión de Linux del CI (`emitir-v1`) es otro ffmpeg y da otros bytes; es
informativa (docs/ENCODER-PORTATIL.md §7-8).

## Variantes

```
emitir.cmd -Out D:\packs\v1
emitir.cmd -Master C:\otro\master.asclv -Sha256 <hex>      (o -SinVerificar)
emitir.cmd -Receta "--vp9-crf 34 --h264-profile high --h264-crf 23 --h264-bframes 3 --h264-refs 4"
emitir.cmd -Frames 30                                       (corte de humo, ~10 s)
```

La receta se escribe igual que en `docs/EMISION-V1.md` §3; sin `-Receta` es
la v1 vigente (`VERSIONES.tsv`, fila `receta_v1`).

## Cualquier otro script del repo

```
py.cmd repo\tools\emit_pieces.py master.asclv --out outputs\v0
py.cmd repo\backend\encoder.py --help
```

`py.cmd` es el Python embebido con el ffmpeg del bundle en el PATH de ese
proceso. Sirve para la mitad A (el máster) y la B (la emisión). Para la B el
bundle es el emisor de referencia; para la A el CI (`regression`) sigue
verificando byte-identidad del máster.

## Qué hay adentro

`VERSIONES.tsv` dice de qué commit salió, con qué Python y qué ffmpeg.
`MANIFEST-portable.tsv` tiene el SHA-256 de cada archivo del bundle. Si algo
no anda, mandar esas dos líneas y la salida de `emitir.cmd`.
