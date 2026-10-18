# NQC666 R2 — registro previo de la hipótesis

Base inmutable: fef142e0310c72ebc1f634e5b5c3f445fe6c4b4e. R1 y NQC666 no se editan.
Hipótesis: vencimientos simultáneos cuestan O(K log 256) en el selector anterior.
Tras 16 líderes inválidos, dos barridos y reconstrucción O(256) pueden reducir ese
coste. No se asume que ganen con uno o pocos vencimientos. Se fija 16 antes de medir.

Semántica: mismo candidato, desempate menor slot, misma invalidación de generaciones,
mismo estado de prioridad observable incluso si el tiempo retrocede. Sólo quitar
los inválidos que el selector anterior habría visitado antes del primer válido.
Defensa financiera final reutilizada directamente desde nqc666::engine::guard.
No saltar comprobaciones financieras, matemáticas, temporales o de financiación.

Medir el original y la variante con igual compilación O3/fat LTO/overflow checks,
afinidad permitida de un CPU, orden intercalado reproducible, CLOCK_MONOTONIC_RAW,
control vacío, muestras individuales sin restar overhead ni descartar máximos.
Entradas sintéticas: 256 slots, ráfagas de 0,1,8,16,64,128,255 líderes vencidos;
rotación del superviviente y valores/tiempos variables. Registrar p50/p95/p99/p99.9/max.
Comparar selección + defensa final (precarga fuera del reloj), ciclo completo de
256 actualizaciones + selección/defensa (precarga dentro), y el recorrido R1 ordinario
con matemática/adaptador/evento/selección/defensa. Registrar alcance de cada ventana.
No confundir estas ventanas con red/builder/EVM/inclusión ni con 5 ns.

La selección muta estado: exponer el resultado completo y el motor a black_box dentro
de la ventana, consumir salida después, comparar checksums y pruebas de continuación.
Aceptar únicamente si preserva equivalencia, mejora el caso de ráfaga y documenta
regresiones normales y de cola. No elegir por un máximo aislado en una VM no controlada.
Si no mejora justificadamente, conservarlo como experimento rechazado sin promoción.

## Enmienda posterior al piloto, antes de la matriz final

El piloto de 8 corridas/40.000 muestras y sus fuentes se conserva íntegro en
`evidence/pilot`. El umbral 16 sin comprobar el siguiente líder empeoró la mediana
con 16 vencidos (661→1.712 ns); con 255 mejoró (6.810→2.965 ns). Se rechaza como
versión elegida. El resultado NO se borra ni mezcla con el nuevo diseño.

Nueva hipótesis explícita: recuperar tras 64 descartes, sólo cuando el siguiente
líder también esté vencido. Probar además la eliminación de la primera escritura
redundante del ranking durante un evento. Cada error temprano conserva rank=0;
ningún callback/hilo puede observar el estado intermedio del propietario único.

Ablación: original / sólo lote / sólo escritura única / combinación. Tres
repeticiones intercaladas, 20.000 muestras por ráfaga y ciclo; 200.000 por pipeline.
Incluir 0,1,8,16,64,65,96,128,255 expiraciones para hacer visible el coste inmediatamente
por encima del umbral. Ciclos de 256 updates con 0/255 expiraciones y pipeline R1
ordinario. 144 corridas, 5.040.000 muestras previstas. No atribuir al lote el efecto
de la escritura única. No asumir que una variante domina todas las cargas.
