# Estudio local de tiempo de QA

Commit ejecutado: `b35feb7b87f3833c99806f38a945666e278659dc`.
Código: `7b8e6779373bb4cc21f81015865feb5de82a9acc268f4163a1475e99f29b0980`.

Doce pares, con orden alternado, sobre el mismo código y las mismas pruebas.
La comparación mide el adaptador completo frente a QA con dos verificaciones adicionales.
Ambos modos usan el mismo entorno con SDK instalado; el modo base omite la instrumentación exterior.
Las pruebas internas de QA permanecen idénticas, incluidas sus pruebas de telemetría.

| Modo | Corridas | Mediana (s) | p95 empírico (s) | Mínimo (s) | Máximo (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 12 | 380.502 | 389.707 | 377.332 | 389.707 |
| sdk | 12 | 379.348 | 383.654 | 375.993 | 383.654 |

| Par | Orden | Base (s) | Adaptador (s) | Diferencia (s) | Diferencia (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | baseline → sdk | 378.418 | 380.785 | +2.367 | +0.625 |
| 2 | sdk → baseline | 380.425 | 379.269 | -1.156 | -0.304 |
| 3 | baseline → sdk | 389.707 | 382.630 | -7.077 | -1.816 |
| 4 | sdk → baseline | 380.580 | 377.559 | -3.021 | -0.794 |
| 5 | baseline → sdk | 378.151 | 379.396 | +1.245 | +0.329 |
| 6 | sdk → baseline | 380.651 | 383.654 | +3.003 | +0.789 |
| 7 | baseline → sdk | 387.413 | 383.583 | -3.830 | -0.989 |
| 8 | sdk → baseline | 377.332 | 381.048 | +3.715 | +0.985 |
| 9 | baseline → sdk | 387.672 | 378.208 | -9.465 | -2.441 |
| 10 | sdk → baseline | 379.573 | 379.300 | -0.273 | -0.072 |
| 11 | baseline → sdk | 380.939 | 378.867 | -2.072 | -0.544 |
| 12 | sdk → baseline | 379.030 | 375.993 | -3.037 | -0.801 |

Mediana de diferencias pareadas: -1.614 s (-0.424%).

Se verificaron 24 expedientes QA y 192 recibos de workers: 2833 pruebas por corrida, sin cambiar sus grupos.
Son 67992 ejecuciones repetidas de 2833 identidades de prueba, no pruebas distintas adicionales.
Se comprobaron también los doce expedientes de telemetría. El verificador lee y recalcula recibos; no vuelve a ejecutar las suites.

El p95 usa el rango más próximo (ceil(0.95 × n)); con doce muestras es el máximo observado.
No estima con precisión la cola de una población ni acredita un SLO de producción.
El orden alternado reduce un sesgo de orden simple, pero no controla ruido del host o cachés del sistema.
Entre las corridas doce y trece hubo un intervalo de 222.917 s, que incluye la pausa prevista de respaldo y sus comprobaciones.
Ese intervalo no forma parte del tiempo individual de las corridas; puede cambiar las condiciones del host o sus cachés.
Una diferencia positiva o negativa es observacional: no identifica por sí sola el costo causal del SDK.
Se incluyen importación, comprobaciones de dependencias, spans en memoria y escritura del expediente del adaptador.
No se mide exclusivamente el costo de crear spans, ni se certifica autenticidad de productores.
Collector continúa sin una integración acreditada por este experimento. El avance global de SuperHunter no se calcula.

## Identidad y alcance de la entrega

Este cierre solo modifica documentación. Las mediciones ejecutaron el commit de PR #90 indicado arriba; el cierre documental posterior conserva exactamente el mismo digest ejecutable. No se atribuye una nueva ejecución a ese commit documental.

- Plan SHA-256: `9c91c6ad0a7645d1d1cdfabffd533fbd519f43ba585300462ea1f7ee1a50ac30`.
- Manifiesto final de colección SHA-256: `09adbe8db02c69957eabd08e4e4938374cebf3763a063c3d33807ea9055eda64`.
- Manifiesto del análisis SHA-256: `56bb0e0bb98537c5027f35dad776473295070e8c4fe28a6bffc045bfdec2d511`.
- Máximo de pared observado por worker: 87.363 s. Se conservaron los límites de 180 s de pared, 90 s CPU, 2 GiB y 20 MiB por archivo.
- Evidencia: `SUPERHUNTER_MEDICION_QA_24_CORRIDAS_20261108.zip`. Incluye plan, 24 expedientes y mediciones, 192 recibos originales, doce expedientes de telemetría, logs, referencia, análisis y helpers.

El revisor sin SDK comprobó los expedientes y reconstruyó los 24 logs agregados desde sus ocho logs originales. Revalidó inventarios, fuentes y bytes al terminar. Los hashes permiten cotejar bytes; no autentican al productor. La revisión no reejecutó las suites.

El respaldo parcial de doce corridas se verificó antes de guardarlo. El primer archivo guardado quedó incompleto; se rechazó, se reconstruyó desde los expedientes originales intactos y se sustituyó por una copia completa verificada. El diagnóstico y el respaldo corregido quedan identificados en la evidencia. La pausa entre las corridas doce y trece incluye ese trabajo, fuera de sus tiempos individuales.

La mediana de diferencias en segundos y la mediana de porcentajes se calculan por separado a partir de las doce parejas. No se descartan diferencias negativas. Estas observaciones no cierran la identificación causal del overhead ni un p95 poblacional fiable. El candidato externo #26 conserva su estado documental; no se promueve por estos resultados.

La aceptación nativa Slither/Geth/EELS de PR #90 permanece como evidencia separada del mismo código. Este estudio de QA no repite esos perfiles nativos ni elimina la omisión histórica `latent_revocation`. Rust/PFT/Census no se reejecutaron ni recertificaron.

## Revisión de la evidencia

Con el código exacto de PR #90, los tres helpers contiguos y un entorno de revisión sin SDK, ejecutar el analizador sobre `study/` y `reference-qa/` del archivo. La salida debe ser nueva y estar fuera del repositorio y de `study/`.

```sh
/ruta/python-sin-sdk -I -B /ruta/evidencia/helpers/analyze_paired_qa_timing.py /ruta/repositorio /ruta/evidencia/study /ruta/evidencia/reference-qa /ruta/revision-nueva 09adbe8db02c69957eabd08e4e4938374cebf3763a063c3d33807ea9055eda64
```

`REPRODUCE.md` del archivo detalla los requisitos y la disposición de carpetas para repetir la medición con datos nuevos. No sobrescribir esta colección.

## Próximo incremento verificable

Definir un esquema cerrado de telemetría de QA con campos mínimos, validar su redacción sobre datos sintéticos y comprobarlo localmente antes de diseñar exportación a Collector. El estudio actual mide el adaptador completo; la exportación, su política de datos y la integración de Collector siguen pendientes.
