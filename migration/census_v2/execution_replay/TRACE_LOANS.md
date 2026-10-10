# Préstamos observados en trazas: entrega, callback y devolución

Readback offline del 10 de octubre de 2026. Se analizan las **127 transacciones**
históricas completas y se concilian **49 llamadas en 46 transacciones**, con
**98 transferencias** correspondientes en sus recibos. No se adquieren datos
nuevos ni se modifica la evidencia original. La dirección de la ruta observada
es `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb`.

Las trazas retenidas la representan como `flashLoan` y muestran tres llamadas
hijas, en orden: `transfer`, `onMorphoFlashLoan` y `transferFrom`. Para cada una,
coinciden activo, prestatario, principal y devolución entre llamadas y logs.
Los datos del callback coinciden con los de la llamada inicial. En cada recibo
hay una única entrega y una única devolución que cumplen esas coordenadas;
se comprueba el orden y se impide reutilizar una transferencia para dos préstamos.

## Qué se aclara

El registro anterior decodificaba eventos Aave/Balancer. Su ausencia en una
transacción no probaba ausencia de financiación. Este consumidor añade otra
ruta explícita de observación sin modificar ni reemplazar ese registro.

En los nueve casos WETH previamente analizados, esta ruta aparece en los rangos
1, 3, 6, 7 y 8. El rango 3 tiene dos llamadas, en activos diferentes; las unidades
no se suman. El caso 5 conserva por separado su préstamo Balancer ya conciliado.
Los casos sin coincidencias aquí no se clasifican como libres de financiación.

| Activo exacto | Llamadas observadas |
| --- | ---: |
| `0x1f9840a85d5af5bf1d1762f925bdaddc4201f984` | 1 |
| `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599` | 3 |
| `0x4c9edd5852cd905f086c759e8383e09bff1e68b3` | 2 |
| `0x514910771af9ca656af840dff83e8264ecf986ca` | 4 |
| `0x6b175474e89094c44da98b954eedeac495271d0f` | 2 |
| `0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0` | 2 |
| `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | 13 |
| `0xae78736cd615f374d3085123a210448e74fc6393` | 1 |
| `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | 12 |
| `0xdac17f958d2ee523a2206206994597c13d831ec7` | 9 |

En las 49 parejas, la cantidad devuelta coincide con la entregada. Eso fija en
cero la diferencia entre **esas dos transferencias**. `complete_financing_fee_raw`
sigue `null`: no prueba que todas las comisiones, pagos laterales u obligaciones
sean cero. La ruta histórica tampoco acredita acceso de Nexus, liquidez disponible
antes de decidir, compatibilidad general del token ni capacidad concurrente.

## Compromisos y límites

El archivo original de trazas tiene SHA-256
`9323bf262e1f9695fcfc68a96a10b1a2e987544d3395c046aa31b13271a60c92`.
Recibos, conciliación previa y dependencias se autentican contra objetos Git
inmutables; las fuentes conservan su pin `fb49a9c46bb52997c689ba2b7f183c4e536a9cb9`
y el consumidor auxiliar se fija a `59f4f9e83d015f5f14466cee88a5e9dbfa049665`.
El informe contiene tamaños y SHA-256 de todos esos insumos. Cada fila conserva
transacción, bloque/hash/posición, miembro de traza, hash de recibo y líneas/logs.

Se reconstruye el contexto de llamada, incluido delegatecall, para identificar
al prestatario; no se confunde la dirección de implementación con la cuenta.
Se rechazan ancestros revertidos, formas no soportadas, diferencias de gas o
identidad, cambios en el callback, destinatarios/cantidades distintos, logs
repetidos o desordenados y ambigüedad de correspondencia.

Los nombres de métodos son **etiquetas del render histórico de la traza**.
No se convierten en una prueba del ABI, selector, bytecode desplegado o estado
exacto. El emparejamiento identifica transferencias únicas con las coordenadas
esperadas; no autentica por sí solo la asociación EVM de cada log a un frame.
No se reconstruyen todos los balances ni se supone comportamiento estándar
universal por la forma ERC20 del evento. Siguen pendientes otras rutas, costes,
obligaciones, financiación admisible y captura. Las 127 filas mantienen
`INSUFFICIENT_EVIDENCE`, sin beneficio completo ni admisión para Nexus.

## Reproducción

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/reconcile_trace_loans.py \
  --out /absolute/path/fresh-trace-loans
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/execution_replay -p 'test_*.py' -v
```

Dos readbacks producen bytes idénticos. SHA-256 del ledger:
`693b9e497337c13563a374c44d0bdeac7c4bb172c4d16e708813df8c2862cbca`.
Pasan 58 controles Python afectados, incluidos ocho nuevos, y nueve pruebas de
aislamiento. Se verifican los 637 objetos originales y cero workflows activos.
No hubo fallos de pruebas en este incremento. El caso sintético delegatecall
valida el tratamiento de contexto; no añade cobertura histórica. Rust y Solidity
no cambiaron ni se ejecutaron. Evidencia y logs en `trace-loans/`.

El incremento no satisface 10/20, 15/20 o 20/20, no cambia el límite acumulado
MXN 2,000 exclusivamente para gas y no cierra Census.
