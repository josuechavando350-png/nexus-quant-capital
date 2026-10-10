# Qué se demostró y qué exige USD 1,500–3,500 netos diarios

Revisión del 10 de octubre de 2026 UTC, desde el head
`154137de8c998e39a2097473eac6cf92cda465fa`. Responde a la petición del usuario
de recuperar los hallazgos ya demostrados y comprobar si muchas operaciones
pequeñas sostienen esa meta. Se interpreta el objetivo como ganancia neta de
NQC, después de todos los costes, no volumen de préstamos ni facturación bruta.

## El avance anterior sí contiene evidencia económica

El usuario tenía razón al recordar muchos mercados ya estudiados. El inventario
D08 no se reduce a WETH ni a los 53 pares de liquidación: esta revisión vuelve
a recorrer **523,491 registros originales**, con identidad, direcciones e índices
sin duplicados y cobertura exacta de sus índices. Son **523,424 pools de Uniswap
V2 y 67 reservas de Aave V3**, en Ethereum al bloque 26,095,351.

En la etapa de reconstrucción de estado, 522,696 pools V2 avanzan y 728 se
rechazan; las 67 reservas avanzan. El productor etiqueta 503,975 pools V2 como
`LIQUID` y 19,449 como `ZERO_LIQUIDITY_NOT_ROUTABLE`. Esas etiquetas no demuestran
profundidad suficiente para una operación ni ganancias. La compatibilidad de
ejecución probada de tokens sigue en cero en ese productor; se conservan sus
no-afirmaciones de ejecución, rentabilidad, semántica de transferencia y frescura
del oráculo. Este recuento autentica el inventario retenido, sin nueva certificación.

También existe un readback completo anterior de **1,045,459 registros de fuentes
de capital**, sobre 3,757,728,513 bytes originales. Se fija ese resultado y su hash;
no se vuelve a ejecutar aquí ese flujo completo ni se interpreta cada registro
como un mercado rentable independiente. Esta base amplia ya construida debe
alimentar el análisis de rutas antes de atribuir el problema a falta de mercados.

Los últimos resúmenes destacaban ejecución y financiación, pero omitían una
cifra material ya reconciliada en `SERVER_RECOVERY.md`: **USD 138,045.17469031
de diferencial bruto valorado al oráculo durante 30 días**. Esta revisión
reproduce la aritmética desde los archivos originales, no desde esa frase.

| Evidencia conservada | Qué demuestra | Qué no demuestra |
| --- | --- | --- |
| 523,424 pools V2 y 67 reservas Aave recontados | Inventario y decisiones de reconstrucción de estado en el ancla | Historial económico de 30 días de todos los pools ni ejecución rentable |
| 1,045,459 registros de fuentes de capital | Universo de financiación retenido y leído en el trabajo anterior | Un millón de oportunidades distintas o acceso de Nexus ya certificado |
| 139 liquidaciones en 127 transacciones | Actividad histórica ejecutada, cantidades y recibos conciliados | Que Nexus las detectara a tiempo o pudiera ganarlas |
| 67 reservas/activos y 53 pares observados | Diversidad dentro del pool Aave V3 Ethereum declarado | 53 protocolos/redes independientes o todo el mercado global |
| USD 2,929,719.1061261 de principal observado | Tamaño del principal liquidado a precios de referencia | Beneficio ni capital propio necesario en todos los casos |
| USD 138,045.17469031 de diferencial bruto al oráculo | Aritmética histórica de colateral menos deuda dentro del alcance | Venta realizable de ese colateral o beneficio neto capturable |
| USD 1,144.134260592713842029 de gas observado | Coste de gas de los ganadores, contado una vez por transacción | Costes completos de Nexus ni pagos de todos los intentos fallidos |
| Préstamos y fork controlado ya reproducidos | Mecanismos concretos de financiación y ejecución | Capacidad operativa, ingreso diario o rentabilidad certificada |

El estado histórico `RMC016_CONSERVATIVE_REALIZABLE_CAPACITY_PASS` conserva
capacidad realizable positiva admitida igual a cero y probabilidad de captura
con límite inferior cero. Su PASS certifica la regla conservadora de ese
productor y alcance; no acredita ingresos positivos ni se hereda como una nueva
certificación. Cero admitido tampoco significa prueba de imposibilidad.

## La media oculta concentración y días débiles

Ventana fuente: **2026-09-01 05:23:35Z a 2026-10-01 05:23:35Z**, Ethereum
25,880,316–26,095,351. Los 30 periodos de 24 horas arrancan en el ancla;
no son días de calendario de Ciudad de México.

Todos los importes siguientes son referencias históricas del conjunto observado,
restando **solamente gas**, con todos los ganadores incluidos. No son P&L NQC.

| Medida | Resultado |
| --- | ---: |
| Total bruto menos sólo gas | USD 136,901.04 |
| Media por periodo diario | USD 4,563.37 |
| Mediana por periodo diario | USD 493.82 |
| Periodos que alcanzan USD 1,500 en esta referencia | 9 de 30 |
| Periodos que alcanzan USD 3,500 en esta referencia | 6 de 30 |
| Periodos sin transacciones observadas | 2 de 30 |
| Participación de la mayor transacción en el bruto | 56.42% |
| Participación de las tres mayores en el bruto | 80.04% |
| Participación de las diez mayores en el bruto | 91.28% |

Por tanto, la media de USD 4,563 no demuestra un mínimo diario de USD 1,500.
La concentración tampoco acredita que podamos capturar las operaciones grandes.
La referencia no es un límite superior de todas las oportunidades posibles:
faltan oportunidades no ejecutadas, otros mercados y otras estrategias.

## ¿La suma vino de muchas operaciones pequeñas?

Usando únicamente el remanente positivo después de gas como criterio de tamaño,
sin fingir que es beneficio completo:

| Banda acumulada por transacción | Transacciones en 30 días | Remanente total | Media diaria de la banda |
| --- | ---: | ---: | ---: |
| Más de USD 0 y hasta USD 25 | 36 | USD 188.79 | USD 6.29 |
| Más de USD 0 y hasta USD 50 | 39 | USD 335.37 | USD 11.18 |
| Más de USD 0 y hasta USD 100 | 49 | USD 1,038.08 | USD 34.60 |
| Más de USD 0 y hasta USD 250 | 58 | USD 2,543.61 | USD 84.79 |

Las bandas se solapan: no se suman. La selección es retrospectiva, no una regla
predictiva ni una prueba fuera de muestra. Tampoco mide principal pequeño.
En este conjunto, el resultado agregado grande vino principalmente de pocas
operaciones grandes. No queda demostrada la tesis de generar los objetivos
diarios sumando exclusivamente pequeños remanentes en este pool y ventana.

## Escala necesaria para la nueva meta

USD 1,500–3,500 netos diarios equivalen a USD 45,000–105,000 en 30 días.
La tabla siguiente es sólo aritmética condicional. El neto supuesto incorpora
todos los costes atribuibles, fallos y costes compartidos prorrateados una vez.

| Neto real supuesto por operación capturada | Capturas diarias para USD 1,500 | Capturas diarias para USD 3,500 |
| --- | ---: | ---: |
| USD 20 | 75 | 175 |
| USD 50 | 30 | 70 |
| USD 100 | 15 | 35 |
| USD 250 | 6 | 14 |

El conjunto completo observado tiene 127 transacciones en 30 días: 4.23 por día
entre todos los ganadores, de todos los tamaños. No hay evidencia aquí de 30–70
capturas NQC diarias a USD 50 netos. El objetivo exige verificar una frecuencia
y una participación sustancialmente mayores en un universo ampliado, o una
distribución de márgenes distinta. No se asigna una probabilidad del 80%.

## Implicación para la investigación

Primero reutilizar el inventario Ethereum amplio que ya existe: cruzar mercados
y fuentes de financiación con compatibilidad de tokens, rutas de conversión,
liquidez realizable y costes completos. Medir oportunidades históricas de las
familias que superen esos filtros; un recuento de pools no sustituye ese historial.
La comparación actual de 127 ganadores corresponde a liquidaciones Aave, no
a oportunidades de arbitraje de los 523,424 pools. No extrapolar su insuficiencia
como prueba de imposibilidad de todo el inventario.

Para cada mercado o familia adicional, medir la distribución diaria completa,
incluyendo ceros, fallos,
competencia y costes; no seleccionar sólo días favorables. Comparar una cartera
de pequeños márgenes con otra que admita oportunidades mayores cuando cumplan
los mismos límites y pruebas. No restringir tamaños por intuición ni sumar rutas
que comparten una misma oportunidad, liquidez o recursos.

La meta debe evaluarse por separado como promedio y como mínimo diario. Una
estrategia con promedio positivo puede tener días sin ingresos o con pérdidas.
Los datos actuales no establecen que ninguna de las dos metas se cumpla; tampoco
descartan todas las estrategias futuras. Sigue la prioridad documental de
`STRATEGY_EXPANSION.md`, condicionada a datos propios de cada mercado.

Los ocho costes omitidos del productor histórico incluyen financiación, swaps,
impacto de precio, pagos competitivos fuera del gas y fallos. Sus precios son
de estado del bloque, no necesariamente previos a la transacción; no prueban
cuándo Nexus conocía la oportunidad. No se convierten ganancias de competidores
en nuestras ganancias. Los MXN 2,000 siguen siendo un presupuesto acumulado sólo
para gas; cero principal, colateral o garantías propios. No hubo gasto ni envíos.

## Evidencia y reproducción

`analyze_daily_capacity.py` fija los consumidores al commit de entrada, autentica
el archivo central y vuelve a ejecutar sus uniones y economía de 139 eventos.
Luego verifica conservación entre las 127 transacciones y los 30 periodos.
Los hashes, importes enteros, fracciones exactas y no-admisiones quedan en
`evidence/daily-capacity/report.json`; cada periodo queda en `daily.jsonl`.

`audit_market_inventory.py` autentica el ZIP D08 original de 79,599,487 bytes,
SHA-256 `9431ea07144ae78e68e0ffcc7f650fa32068ee63fb53ca41ff8a062b87845913`,
contra el readback fijado al head de entrada. Recorre y verifica el hash de los
478,607,674 bytes del manifiesto de mercados, conserva el productor exacto
`36c732a36789e1967ce7178010889427ad7cf0f2` y su árbol, y verifica unicidad,
índices completos y conservación con las métricas fuente. Guarda el resultado
en `evidence/daily-capacity/market-inventory.json`. No reejecuta el productor
histórico de reconstrucción de estado ni autentica nuevos estados on-chain.

El archivo fuente `original-temporal-core.zip`, 988,991 bytes, SHA-256
`cc51fc5c9a3ea76daa59d42cc5eef6aed3909955d1bf5a68795ac3bf5b210ede`, está
dentro del paquete durable identificado por `evidence/server-recovery/retention.json`.
No se modifican las fuentes originales ni se necesita red para reproducir:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/analyze_daily_capacity.py \
  --core /absolute/path/original-temporal-core.zip --out /tmp/nqc-daily-review-new
TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_daily_capacity.py \
  --core /absolute/path/original-temporal-core.zip -v
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/audit_market_inventory.py \
  --d08 /absolute/path/11237887761.zip --output /tmp/nqc-market-inventory-new.json
```

Esta revisión recupera un hallazgo omitido en los resúmenes y precisa su
distribución. No añade mercados certificados, no cambia las clasificaciones,
no acredita ingresos y no alcanza un hito por sí misma. Census sigue abierto.
