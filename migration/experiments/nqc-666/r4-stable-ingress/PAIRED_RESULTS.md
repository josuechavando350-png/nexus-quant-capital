# Contraste emparejado del ingreso

12.288 pares / 24.576 ventanas, sin cambios de código respecto de la matriz principal.
Se alterna exactamente cuál versión corre primero; cada par usa la misma entrada.
Corpus: los mismos 16 paquetes R3, con un precio supuesto determinista por caso.
No hay descartes; todos los resultados aceptados de cada par coinciden.

| Camino | Mediana ns | p95 ns | p99 ns | p99.9 ns | Máximo ns |
|---|---:|---:|---:|---:|---:|
| R3 + nativo | 2.541.813 | 3.864.912 | 5.339.998 | 9.224.710 | 19.125.877 |
| R4 + nativo | 2.562.253 | 3.820.316 | 5.116.015 | 8.700.450 | 23.964.258 |

En este contraste la mediana R4 es +0,80%, p99 −4,19%, p99.9 −5,68%, pero el
máximo es **+25,30%**. R4 fue más rápido en 5.861 de 12.288 pares. La mediana de
la diferencia dentro de cada par (R4 menos R3) fue +9.464 ns; p95 +586.102 ns,
p99 +1.566.071 ns y extremos −12.869.055 / +16.614.328 ns. Los valores de esa
diferencia no son una estimación pura del coste de instrucciones adicionales:
siguen interviniendo planificación, caché y carga del host.

La regresión de colas de la primera matriz no se reproduce uniformemente bajo este
orden, y el máximo empeora en la nueva medición. Por tanto, los datos respaldan un
coste adicional pequeño de mediana en este contraste y **variabilidad temporal no
resuelta**, no una garantía de estabilidad ni una mejora universal de rendimiento.
Se mantienen ambas mediciones; no se sustituye una por la otra ni se atribuye la causa
a la VM como si estuviera demostrada.

Ejecución 2026-10-19 00:45:31–00:46:36 UTC, CPU 0, biblioteca con el mismo SHA-256
de la matriz. Los plazos de aceptación 50/5 ms no descartaron ningún intento en este
ensayo; la demora máxima observada permanece publicada.

Reproducir después de compilar la biblioteca:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/paired_ingress.py \
  --library /tmp/nqc666-r4-run/target/release/libnqc_666_stable_ingress.so \
  --out /tmp/nqc666-r4-paired
```

Verificar los resultados entregados:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_paired.py
```

`evidence/paired/raw.zip` conserva todos los tiempos y estados. `result.json` incluye
hashes, diferencias por pares resumidas, controles de reloj y hashes del código que
debe permanecer idéntico al medido.
