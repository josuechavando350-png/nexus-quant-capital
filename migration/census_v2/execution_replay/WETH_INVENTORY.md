# WETH: inventario inicial exigido por el orden observado

Análisis offline del 10 de octubre de 2026 sobre los nueve casos WETH completos.
Se vuelven a autenticar recibos, trazas y conciliación por cuentas antes de
procesar 50 movimientos WETH, manteniendo las mismas 97 filas transacción/cuenta.
No se consultan RPC ni se modifican fuentes originales. La nueva dependencia y
el ledger previo se fijan al commit `97c65411e8cdd4d3fc48f7d766b3824b6685d9d4`;
las dependencias anteriores conservan sus propios compromisos exactos.

## Resultado material

El ejecutor del rango histórico 4, `0x29452e8332912533130fb708984722d92184284f`,
necesita un saldo inicial de **al menos 3,379,677,466,555,340 wei WETH** bajo la
semántica de eventos observada. El retiro en el log 39 pide 99,498,524,160,438,628
wei, después de un delta acumulado de sólo 96,118,846,693,883,288 wei. La diferencia
no está financiada por esas entradas. No se atribuye a capital propio de Nexus;
identifica un requisito que una ruta admisible tendría que explicar. La política
MXN 2,000 es exclusivamente para gas y no proporciona este inventario.

| Rango retrospectivo | Mínimo WETH inicial del ejecutor, wei | Log que fija el mínimo positivo |
| ---: | ---: | ---: |
| 1 | 0 | — |
| 2 | 0 | — |
| 3 | 0 | — |
| 4 | 3,379,677,466,555,340 | 39 |
| 5 | 0 | — |
| 6 | 0 | — |
| 7 | 0 | — |
| 8 | 0 | — |
| 9 | 0 | — |

En las 97 filas hay **21 mínimos positivos**; en **15** el mínimo por orden es
mayor de lo que mostraría el delta final por sí solo. Por ejemplo, en el caso 5
la cuenta Balancer entrega 342,642,361,343,309,991 wei WETH en el log 13 y termina
con delta cero tras la devolución. Ese cero final no elimina el inventario que
el prestamista necesitó adelantar. Los requisitos de cuentas externas permanecen
separados: no se suman como capital del operador, capacidad global ni obligaciones
propias. No se atribuye identidad económica a una dirección por su patrón de flujo.

## Método y límites

Para cada débito de cantidad `q`, con delta acumulado previo `d`, el saldo inicial
debe ser al menos `max(0, q-d)`. El mayor requisito de la secuencia fija el mínimo
de esa cuenta. Una transferencia se debita antes de acreditarse incluso cuando
emisor y receptor coinciden. Un retiro debita WETH; no se vuelve a acreditar como
WETH por aparecer ETH en la traza. Approval no cambia balances. Depósitos o eventos
WETH desconocidos no se omiten: detienen este consumidor de alcance limitado.

Cada fila conserva el primer ingreso observado, delta final, mínimo inicial y
el débito que lo exige; los movimientos conservan dirección, cantidad y log.
Todos los deltas finales coinciden exactamente con la conciliación anterior.
Los recibos vinculan transacción, bloque y posición; logs removidos, repetidos,
desordenados o malformados se rechazan. Estos son mínimos **condicionados a la
semántica WETH/eventos y a la evidencia observada**, no pruebas de balances de
estado, almacenamiento ni bytecode completo en cada preestado.

Un mínimo cero del ejecutor no prueba financiación disponible para Nexus: puede
depender de liquidez ajena, derechos de llamada, otros activos, garantías, rutas
o acuerdos no autenticados. Tampoco prueba gas inicial, costes completos,
propiedad común, beneficio, captura ni conocimiento contemporáneo. Ninguna de
las nueve clasificaciones `INSUFFICIENT_EVIDENCE` se promueve. No se alcanza
10/20, 15/20 o 20/20 y Census permanece abierto.

## Reproducción y validación

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/reconcile_weth_inventory.py \
  --out /absolute/path/fresh-weth-inventory
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/execution_replay -p 'test_*.py' -v
```

Dos ejecuciones producen ledger e informe idénticos. El SHA-256 del ledger es
`a47c6449950f0ab4efdc5e864bdca04513399d39daccc71aeb0cfc5b34c0df94`.
Pasan los 50 controles Python afectados, incluidos ocho nuevos. La secuencia
de cada cuenta pasa con su mínimo; reducir en un wei cualquiera de los 21
mínimos positivos la hace fallar. El caso de autotransferencia es una prueba
sintética de semántica, no cobertura de mercado añadida. También pasan nueve
pruebas de aislamiento y la comprobación de los 637 objetos originales, con
cero workflows activos. Logs e informes exactos constan en `weth-inventory/`.
Rust y Solidity no cambiaron ni se volvieron a ejecutar en este incremento.
