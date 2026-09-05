# Índice de documentación

Reorganizado el **2026-09-01** (H-0, nace ASCILINE-hybrid): los diseños y planes
del paradigma 100 % JS se movieron **verbatim** a [`historico/`](historico/README.md)
(sin pérdida; antes de eso, las podas 2026-08-30/31 dejaron lo retirado en el
historial Git). El mismo día, tras el debate de dirección, se sumó la
documentación objetiva del proyecto nuevo (visión, formato, plan de medición).
Si dos documentos se contradicen, prevalecen en este orden: **visión → medición →
spec de formato → estado de ejecución → diseño en obra → registro de decisiones**.

## El norte (leer antes que nada)

| Documento | Función |
|---|---|
| [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md) | **qué construimos y por qué**: la frase madre («encoder caro, decoder sin estrés»), la regla física (`<video>` es la única puerta al hardware), de qué linaje sale cada pieza (VP9 compresión · DASH modelo de datos · HLS piso · ASCILINE la base), objetivos macro, escalera de intervención N1–N4 con su límite, perfiles de dispositivo, invariantes y **no-objetivos** |

## Para trabajar (en este orden)

| Documento | Función |
|---|---|
| [`../PROPUESTAS.md`](../PROPUESTAS.md) | **el espacio de ideas** (2026-09-05): plantilla de propuesta (problema · idea · qué compra · qué cuesta · cómo se mide · qué la refutaría), estados, y las abiertas P-001..P-007. Las ideas de afuera entran por *issue*; el repo es público de solo lectura |
| [`../CLAUDE.md`](../CLAUDE.md) | arranque de sesión: identidad del proyecto, modelo de trabajo, ayuda-memoria, estado grueso |
| [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md) | **el archivo vivo**: próxima acción y máster vigente arriba, tabla de tareas de la fase H, referencias de clips por SHA, bitácora al final |
| [`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md) | **el rumbo** (vigente desde el primer reporte de aparato, 2026-09-01): evidencia medida fila por fila, los caminos de runtime con lo que la caja dijo de cada uno, **gates numéricos** de reproducción, el orden H-13 → H-11 → H-12 → H-6 → H-7 → H-8 y las decisiones que necesita el operador |
| [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) | reglas de ejecución + las tareas de la fase H (H-9 cerrada; H-10 abierta con la caja medida; H-13, H-11, H-12, H-6, H-7, H-8, H-14, W-26) |
| [`EMISION-V0.md`](EMISION-V0.md) | **el primer video**: qué le tomamos a cada códec (las «bondades»), las piezas del pack v0 con sus parámetros, y la tabla de **suposiciones con su refutación escrita**. Es lo que se corrige reproduciendo |
| [`EMISION-V1.md`](EMISION-V1.md) | **H-6 (2026-09-05)**: la matriz por bytes a igual look (28 variantes, qué enseña cada eje, el autocontrol contra v0), la receta v1 (VP9 crf 38 + Opus; H.264 High+3B crf 23 + AAC; radio mp3; `dash-vp9/`), las teclas `72`/`74`/`75`/`76` y qué refutaría cada suposición |
| [`SPEC-VGEN.md`](SPEC-VGEN.md) | **H-7, BORRADOR 0.1 (2026-09-05, turno nocturno)**: la spec del formato tal como el prototipo la ejecuta — paquete como directorio (archivo único gateado), manifiesto de piezas, **guion** de papeles, **residencia** (clave, presupuesto, plan por prioridad, rangos), el contrato de reproducción (anillo MSE, publicidad, incentivador, radio, capa, vigilancia), perfil → camino, trazabilidad regla → fila y **qué tiene que devolver el aparato para firmarla** |
| [`ENCODER-PORTATIL.md`](ENCODER-PORTATIL.md) | **evaluación (2026-09-05)** del pedido «encoder más rápido y sin instalar Python ni Node»: las dos mitades (máster / emisión), tres hechos (minutos gratis, la regla de la máquina, el determinismo es del binario), cuatro opciones y la recomendación (bundle portátil **después de H-8**, con el CI como árbitro de bytes). Decisión pendiente del operador |
| [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) | **el método**: se mide **reproduciendo** y **nunca en un solo aparato**; qué reporta la página de v0, las métricas del banco, los ejes de la matriz y el registro de aparatos |
| [`ejecutados/`](ejecutados/README.md) | resumen por fase cerrada (paradigma anterior) con su evidencia; se consulta, no se relee |
| [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md) | bitácora append-only: el porqué de cada decisión y cada medición, incluidos el cambio de dirección y el debate del 2026-09-01 |

## Diseño de lo que está en obra (fase H)

| Documento | Función |
|---|---|
| [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md) | el formato de distribución `.vgen`: modelo de datos tomado de DASH, piezas intercambiables, fps variable, caminos de runtime, muxer, caché, capa de intervención. **§10 marca fila por fila qué está decidido y qué está gateado por medición**; §11 guarda las ideas anotadas sin tarea |
| `SPEC-VGEN.md` | **H-7, todavía no existe**: la spec normativa (layout binario, manifiesto, segmentos, sprites, cues). Se escribe recién con H-13 y H-11 cerradas y filas en ≥2 clases de aparato (o decisión del operador) |

## Referencia técnica (sigue vigente en el híbrido)

| Documento | Función |
|---|---|
| [`ASCL-format-spec.md`](ASCL-format-spec.md) | contrato binario normativo del **máster** ASCL/ASCLV (v1/v2; envelope v3 en el REGISTRO de F6). El máster no se reemplaza: el formato nuevo lo envuelve |
| [`MAPA-DEL-PROYECTO.md`](MAPA-DEL-PROYECTO.md) | grafo de composición, flujo, contratos e invariantes (escrito para el paradigma anterior; su parte de encoder sigue válida) |
| [`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md) | la intervención: paleta reservada, slots, canal en vivo, runtime — la capa que sobrevive encima del video |
| [`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md) | ASCLSLOT v2, parches, texto nativo (INT-003/004) — referenciado por el código del overlay |
| [`DESPLIEGUE.md`](DESPLIEGUE.md) | layout de hosting estático, cabeceras y caché para el TV |

## Histórico

| Documento | Función |
|---|---|
| [`historico/`](historico/README.md) | los 9 diseños/planes/runbook del paradigma JS, verbatim, con README que dice qué fue cada uno y en qué estado se archivó (F9 ejecutada; F10/F11 suspendidas sin ejecutar; etc.) |

Las herramientas offline y helpers están en [`../backend/README.md`](../backend/README.md);
el resumen por versión en [`../CHANGELOG.md`](../CHANGELOG.md). Los documentos
retirados el 2026-08-30 (pre-histórico) siguen recuperables del historial Git
(`git log --diff-filter=D -- docs/`).
