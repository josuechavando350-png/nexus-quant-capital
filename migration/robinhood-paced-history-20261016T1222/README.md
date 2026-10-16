# Historia ampliada con presupuesto y frecuencia globales

**Resultado:** captura real única terminada el 16/oct/2026, 12:32:06.107–12:33:18.986 UTC. Se amplió el índice, se autenticó el target y se congeló la cohorte antes de tres lecturas actuales. No se detectaron candidatos en esta muestra. La rentabilidad sigue sin demostrar.

## Prerregistro y trazabilidad

El [protocolo 91b61a9](https://github.com/josuechavando350-png/nexus-quant-capital/commit/91b61a95541e5950772a7c919060df3a477d6821), árbol `f3049191f240e002a372f08ce68f30737861af42`, se publicó antes de la primera consulta. Sus reglas y fuentes no se modificaron después. Base PR18: `9063049967530a682d28d94af5ff17cf46c7bd66`.

La selección fue una ventana contigua, independiente de salud y liquidaciones conocidas. Se mantuvieron todas las cuentas, también las de deuda cero. Se reutilizaron helpers puros, no los mains históricos con ventanas antiguas.

| Incremento | Bloques | Borrow | Cuentas nuevas respecto a la fuente |
|---|---:|---:|---:|
| Historia 88246281–88646280 | 400000 | 30 | 13 |
| Cola 90037170–90080877 | 43708 | 6 | 2 |
| Acumulado 88246281–90080877 | 1834597 | 97 | 46 cuentas totales |

Se conservaron el archivo fuente original, el prefijo histórico separado y el estado unido antes del catch-up. Los segmentos anteriores conservan eventos, respuestas y checkpoints; la unión recalcula únicamente su enlace `previous_segment_sha256`, no se afirma identidad byte a byte de enlaces reconstruidos. La auditoría reproduce exactamente los cuatro archivos de estado.

Fuente nueva: [evidence/pilot/registry.json](evidence/pilot/registry.json), estado `valid_prefix`, target completo y autenticado.

- Raíz: `e9dfe58703e31d07eb8a61be6ee46f62d5b13679c7e78feb286ce47e4d88ceca`.
- SHA256 del archivo: `8cbbeac9381cfdb0a011bd5a74a06c80b07cc755e999b50b42e920dbe0a05dba`.
- Raíz de entrada PR18: `8740288f2899e8fc2056d56291ad5369f8c37d46a1e8139a5b41f3501601aaf0`.

## Cobertura, no ingresos

Tres hashes únicos, bloques 90081042, 90081053 y 90081064. En los tres: 46 cuentas, 39 con deuda y siete sin deuda; cero candidatos y cero cuentas calculadas como liquidables. Tail posterior al anchor todavía sin indexar: 165–187 bloques.

| Conjunto, evaluado en los mismos hashes | Porcentaje de totalBorrowShares |
|---|---:|
| Cohorte anterior de 31 cuentas | 20.6888815586% |
| Aporte de 13 cuentas históricas nuevas | 2.9052802626 puntos |
| Aporte de dos cuentas nuevas de cola | 0.2178171798 puntos |
| Cohorte ampliada | 23.8119790010% |
| Pendiente | 76.1880209990% |

No se atribuye a cuentas nuevas la variación de la cohorte anterior respecto de PR18. El denominador conciliado por hash fue `871006767554225010` borrowShares; observadas `207403948587013662`, faltantes `663602818967211348`. Son participaciones de deuda, no dólares ni beneficio. La ausencia de candidatos solo describe esta cohorte y estos tres bloques: no demuestra ausencia universal de oportunidades.

## Frecuencia, latencia y límites

194 métodos RPC/194 HTTP, cero errores: 4 verificaciones, 152 historia, 25 cola, cuatro autenticación y nueve observación. Duración journal 72.878522032 s; proceso 72.887374589 s. Las esperas sumaron 45.936183325 s, incluidas en el presupuesto único de 900 s. Separación mínima real de despachos locales 350.155201 ms, cero infracciones; un solo presupuesto de 512 métodos y una sesión persistente, sin rotación ni rescate.

Las tres adquisiciones completas después de indexar tardaron **929.917, 1107.513 y 1050.535 ms**, desde antes de admitir la cabecera hasta verificar el estado. Mediana 1050.535 ms; solo 1/3 ≤1 s. Desde despacho local, excluyendo la espera inicial: 753.122–814.130 ms. Esa métrica secundaria no sustituye a la primaria.

Intervalos de despacho de cabeceras: 1051.116 y 1052.184 ms. Intervalos de solicitud de admisión: 934.162 y 1109.527 ms. La variación del último tiempo de respuesta permite un intervalo de admisión aislado menor; no prueba cadencia sostenida subsegundo. Son solo tres observaciones de cobertura, no un nuevo benchmark de transportes.

Las nueve peticiones de observación reutilizaron el socket cliente, en la misma sesión que la preparación y mediante el proxy existente. No hubo adquisición fría de observación: los 4011.439 ms de la primera petición corresponden a preparación, no a un ciclo completo. No se prueba conexión backend, cuota futura ni SLA. No se midieron ruta, envío, inclusión, gas, EntryPoint/AA, Nitro/DA, bundler, patrocinio financiado o ingresos.

## Verificación y evidencia

96 pruebas offline antes de consultar, incluidas 10 nuevas del flujo y fallos en las 43 fronteras RPC sintéticas; siete pruebas independientes del informe real después: **103 pruebas distintas aprobadas**. Paradas HTTP/JSON/RPC, presupuesto, reorgs, conservación tras unir y antes de catch-up y separación global entre fases están cubiertas. Las trazas de `evidence/synthetic/` son artificiales, nunca fuentes del índice real.

Replay offline real aprobado; fuentes registradas y seis manifiestos PR13–PR18 intactos. 377 blobs originales intactos, 106 workflows deshabilitados y cero activos. Rust/Solidity sin cambios ni ejecución nueva. Recibos: [verification/preflight.json](evidence/verification/preflight.json), [verification/post-capture.json](evidence/verification/post-capture.json), [process-receipt.json](evidence/process-receipt.json).

Resultados reproducibles sin RPC: [audit.json](evidence/audit.json), [summary.json](evidence/summary.json), [journal](evidence/pilot/journal.jsonl), [ledger HTTP](evidence/pilot/requests.json), [admisiones](evidence/pilot/admissions.json), respuestas originales y `MANIFEST.sha256`.

Confianza técnica alta en los archivos y la reconciliación de esta muestra; evidencia comercial insuficiente. Siguiente intervalo histórico contiguo: 87846281–88246280, bajo otro protocolo publicado antes de medir. Próxima cola desde 90080878. No relanzar este runner terminado. Si aparecen candidatos, estudiar supervivencia y el ciclo completo con todos los costes y patrocinio prepagado; no autoriza transacciones.
