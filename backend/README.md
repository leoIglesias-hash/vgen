# Backend offline

El backend crea y verifica archivos; no se despliega en el Smart TV ni en el servidor de
reproducción estática.

## Entradas activas

- `make_clip.py`: interfaz principal video/imagen → ASCLV1 o ASCLV2.
- `encoder.py`: encoder ASCL v1 y opciones de calidad offline.
- `ascl_v2.py` + `regional_codec_v2.py`: transcode/codec exacto v2.
- `ascl_bundle.py`: envelope ASCLV1/2, info, pack y unpack.
- `ascl_decode.py`: decoder de referencia y previews.
- `benchmark_quality_v1.py`: inspección estructural y métricas reproducibles.
- `verify_v1_v2.js`: igualdad RGBA/audio usando los readers reales.

La orden normal es:

```bash
python make_clip.py ../inputs/video.mp4 --out ../outputs/video.asclv
```

## Helpers históricos

`_encode_opt.py` y `_encode_resumable.py` pertenecieron a una etapa temprana de procesos
reanudables. Se retiraron del árbol publicable porque cargaban checkpoints `pickle` desde
un nombre predecible en el directorio temporal compartido. No forman parte de la API ni
del pipeline actual; siguen recuperables en el historial Git anterior a v0.2.

`generar_1080_y_variantes.bat` también es un helper histórico: requiere que la fuente se
pase como argumento y no inicia ningún servidor.
