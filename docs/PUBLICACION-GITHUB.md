# Preparación para GitHub

Estado: código y documentación preparados localmente; no hay remote ni push realizado.

## Qué debe publicarse

- código de `backend/`, `frontend/` y `tests/`;
- documentación activa y evidencia sintética reproducible sin videos de producto;
- workflow de regresión de `.github/workflows/tests.yml`;
- fixture sintético pequeño de `inputs/synthetic.mp4` y fixtures de `tests/fixtures/`.

`outputs/clip.asclv` está ignorado a propósito. El código se clona y prueba sin ese
binario. Para distribuir la demo exacta se adjunta `clip.asclv` al release asociado al tag
`asclv2-exact-hq-v0.2` y se verifica su SHA-256:

```text
6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A
```

## Decisiones requeridas antes de un repositorio público

### 1. Historial con videos

El árbol actual ya no contiene los resultados antiguos, pero el historial Git local
conserva cuatro ASCLV de 12,1 a 17,9 MB. Una publicación con toda la historia permite
recuperarlos aunque estén borrados de `HEAD` y transfiere aproximadamente 56 MiB de
objetos.

- Repositorio privado: puede conservarse la historia completa y su capacidad de rollback.
- Repositorio público: confirmar derechos sobre esos videos o crear una historia pública
  saneada. El repositorio local completo debe conservarse como respaldo; no se reescribe
  sin autorización expresa.

La elección también cambia el alcance del benchmark HQ. Con historia/artefactos
autorizados, el V1 del tag v0.1 permite regenerar y verificar el V2. Con una historia
pública saneada, `BENCHMARK-V2-HQ-768.md` queda como evidencia histórica no regenerable,
salvo que el V1 se publique aparte con autorización. El smoke sintético y toda la CI
siguen siendo reproducibles en ambos casos.

### 2. Licencia y procedencia

Este proyecto declara una relación conceptual con
[`YusufB5/ASCILINE`](https://github.com/YusufB5/ASCILINE): la implementación se presenta
como standalone, pero este cierre no incluye todavía una auditoría independiente código a
código ni identifica el commit upstream relevante. Su
[`LICENSE`](https://github.com/YusufB5/ASCILINE/blob/main/LICENSE) es una licencia
personalizada basada en MIT con una restricción de publicidad. Antes de elegir una licencia
propia hay que completar esa trazabilidad, determinar si existe código o una porción
sustancial derivada y confirmar que el uso previsto sea compatible.

No se agrega una licencia automáticamente. Publicar sin `LICENSE` conserva los derechos
por defecto, pero no aclara permisos de uso o contribución. La elección debe ser explícita
del titular y, si corresponde, revisada legalmente.

### 3. Identidad y reproducibilidad

Los checkpoints locales actuales usan la identidad Git técnica
`ASCILINE Local <asciline@local>`. Antes de recibir contribuciones se debe configurar la
identidad pública que el titular quiera mostrar. No se reescriben autores históricos de
forma automática.

`backend/requirements.txt` expresa mínimos compatibles, no un lock byte-exacto. La CI
comprueba que el código siga funcionando con una instalación actual. Un benchmark formal
debe registrar las versiones efectivas de Python, Node, Pillow, NumPy, OpenCV y FFmpeg;
solo entonces conviene congelar un archivo de entorno específico de esa medición.

## Gate de release

1. Ejecutar `python tests/run_all.py --require-release-artifact`; este gate valida también
   el SHA-256 exacto del HQ.
2. Ejecutar `python backend/ascl_bundle.py info outputs/clip.asclv`.
3. comprobar tamaño y SHA-256 contra `docs/ESTADO-ACTUAL.md`;
4. probar `tv-player.html` en el servidor PHP con `./outputs/clip.asclv`;
5. validar el menú de renovación y las cabeceras ETag/Cache-Control;
6. decidir repositorio público/privado, política del historial y licencia;
7. recién entonces configurar el remote y sincronizar `main` y el tag.

## Lo que GitHub Actions valida

El workflow queda configurado para probar Python 3.8 y 3.11, instalar las dependencias del
encoder y ejecutar 115 pruebas Python y 11 suites JavaScript con Node 20. No descarga el
clip de demostración ni inicia servidores. La prueba de página TV valida la ruta relativa
aun cuando el asset no esté en el clon; el gate local estricto valida además envelope,
longitudes, audio y hash. La primera corrida remota verde debe sumarse al registro tras el
push.
