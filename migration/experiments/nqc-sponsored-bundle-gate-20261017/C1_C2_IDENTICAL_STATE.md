# C1 frente a C2: primer ciclo local completo

`evidence/identical-state-comparison.json` exige igualdad de parent hash, timestamp, parámetros y totales Morpho, posición, oráculo, reservas DEX y balances de actores base. Para ambos escenarios comparados otro prestatario devuelve 8 WETH mediante `Morpho.repay` original, antes del snapshot: no es financiación de NQC. El saldo cash disponible es exactamente 8 WETH. Se mantienen iguales R=0.05 ETH, tip=0.04 ETH y builder de laboratorio=0.002 ETH.

| Medida por recibos | C1 callback | C2 flash |
|---|---:|---:|
| Transacciones primer ciclo | 6 | 8 |
| Gas primera operación completo | 2,325,526 | 5,196,129 |
| Gas de liquidación | 488,952 | 407,191 |
| Gas CREATE específico de la ruta | 1,773,574 | 4,725,938 |
| Costo total gas a 2 gwei, ETH | 0.004651052 | 0.010392258 |
| Margen caja financiador, ETH | 0.043348948 | 0.037607742 |
| Margen con oportunidad de laboratorio 1 bp, ETH | 0.043345948 | 0.037604742 |
| WETH nuevo NQC | 0.159365645570551238 | 0.159365645570551238 |
| Anticipo mínimo a caps/límites de esta ejecución, wei | 12,822,358,000,000,000 | 25,795,554,000,000,000 |
| Flash principal requerido | 0 | 8 WETH |

C2 ahorra 81,761 gas en la liquidación pero cuesta 2,870,603 gas más en el primer ciclo. A 2 gwei, reduce el margen del financiador en 0.005741206 ETH. No se comparan medidas calientes de llamadas con recibos completos. C1 cash cero cobra 13,680 gas más que C1 cash ocho: el estado de balance que pasa de cero a no cero afecta el costo, por lo que no se mezclan ambos denominadores.

## Flujos y repagos

C1: Morpho entrega 9.278589654372535368 de garantía antes del callback; el adaptador vende contra reservas originales V2 1000/900 y recibe 8.249365645570551238 WETH. Se reservan 8 WETH para el pull de deuda Morpho, 0.09 se desenvuelve para R+tip y 0.159365645570551238 se entrega a NQC. El cash inicial de Morpho no se presta. La obligación de deuda se paga al terminar el callback.

C2: Morpho adelanta 8 WETH a EthereumGeneralAdapter1, que autoriza la reentrada exacta a Bundler3. Bundler usa esos 8 para liquidar **sin callback de liquidación**, recibe/vende la misma garantía, entrega 8.09 al adapter, desenvuelve 0.05/0.04 para las mismas remuneraciones y entrega el mismo residual WETH a NQC. Morpho cobra después 8 WETH al adapter para cerrar el flash, sin comisión flash en la versión original fijada. Deuda y flash son obligaciones diferentes, ambas satisfechas. Cash final Morpho: 16 WETH desde 8; no se confunde el principal prestado con ingreso.

Con cash 0 y con 8 WETH menos un wei, C2 revierte. Gas del ciclo fallido: 4,881,122; financiador pierde 0.011762244 ETH aun recuperando U. Los despliegues y pago separado al builder permanecen. C1 sí completa con cash cero. Esta diferencia de viabilidad es real **en la fixture local con código original**; no demuestra disponibilidad ni captura de una oportunidad histórica.

## Fuentes y alcance de las dependencias

Morpho y V2 coinciden en bytecode de creación con Directiva 003 corregida. Bundler3 y EthereumGeneralAdapter1 se recompilan sin alteraciones desde `b4014349...`, solc 0.8.28, optimizador 999999/viaIR/Cancun. Bundler3 está deprecado; se usa como referencia experimental, no como recomendación de integración nueva.

El constructor de EthereumGeneralAdapter1 consulta `stETH()` y `underlying()` para ramas Lido/wrapper ajenas a esta ruta WETH. Se utiliza un helper explícito `ConstructorMetadataFixture` que solo devuelve direcciones; se cobran sus 101,658 gas de despliegue. **No se han validado las ramas Lido/wrapper, sus contratos desplegados ni compatibilidad mainnet de sus direcciones.** El helper no implementa préstamo, liquidación, callback, repago, intercambio ni unwrap; esas operaciones ejecutan los contratos originales. El adaptador DEX LabV2Adapter también es auxiliar NQC, de costo medido en ambas rutas.

Bundler y bridge terminan sin activos; sus allowances transitorios de deuda/garantía quedan cero. El GeneralAdapter conserva allowance máximo a Morpho según el upstream, y sus permisos de entrada siguen sujetos a Bundler. Se registran ese permiso persistente y el borrado de initiator/reenterHash. No se transforma esa comprobación en auditoría de seguridad de toda la infraestructura.

## Variante hipotéticamente predesplegada

Con Bundler, EthereumGeneralAdapter1, bridge y metadata desplegados previamente por el actor setup, C2 cobra 470,191 gas en cuatro transacciones y deja al financiador +0.047059618 ETH. **No tiene costo inicial cero**: la preparación conserva recibos de 4,725,938 gas de despliegues, pagados por otro actor; asignarlos al primer intento resta 0.009451876 ETH y devuelve el margen total a 0.037607742 ETH. No se presume que el bridge exista ya en mainnet. C1 predesplegado bajo esta misma variante: NOT_RUN; no se declara superioridad de C2 a partir de esta comparación asimétrica.

La construcción de Morpho, pool y mercado es setup sintético externo compartido, separado de los costos del primer uso NQC. No se propone desplegar esos protocolos en producción. La suma de todos sus costos de laboratorio está preservada en setup.json.
