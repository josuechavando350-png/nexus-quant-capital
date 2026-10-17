# Resultado EVM y contabilidad

## Contratos y condiciones

Fuentes reconstruidas desde blobs Git, sin modificaciones de protocolos:

| Componente | Fuente fijada | Alcance |
|---|---|---|
| Morpho Blue | `9cf6d5b844625ba108e36d1cf911f5d2faf7c136` | Core original; constructor, mercado, supply, borrow, liquidate y callback ejecutados |
| Uniswap V2 Pair / token de pruebas ERC20 upstream | `6a9e7c97860676e0992f22a49665760444c1cdf5` | AMM original, 997/1000 y reservas mutables; el colateral **no** es ezETH real |
| Solmate WETH | `8d910d876f51c3b2585c9109409d601f600e68e1` | Implementación upstream, depósitos ETH respaldados; **no** bytecode WETH9 mainnet |
| NQC | Contrato previo, sin cambios | Autenticación, mínimos, approvals y preservación de inventario intactos |
| LabSupport | Este directorio | Oracle controlado, factory, adapter V2; rechazo de ETH y underpayment solo como controles |

`build-manifest.json` conserva blobs, SHA-256, compiladores y bytecode. Los hashes de runtime realmente desplegado están en `setup.json`. Estos datos prueban fuente original, no equivalencia byte por byte con despliegues mainnet.

Se alineó el optimizador Morpho a las 200 pasadas de la referencia anterior. `original-bytecode-parity.json` verifica ahora igualdad exacta del creation bytecode Morpho y V2 con esos builds fijados. El primer commit de medición `9188d693...` usó 999999 pasadas para Morpho; sus cifras se conservan en Git y se contrastan en `optimizer-alignment.json`. Las mediciones siguientes son las corregidas.

El setup externo aporta 2,000 ETH al preparador, 1 ETH al sponsor y 1 ETH a cada actor que necesita pagar gas de preparación. El preparador deposita 1,002 ETH en WETH: 100 financian al prestamista, 900 la DEX y 2 quedan fuera de NQC. El mercado tiene 10 unidades de colateral y deuda de 8 WETH para el prestatario objetivo; otro prestatario toma los 92 WETH restantes contra 200 unidades de garantía. La liquidez Morpho queda en cero. El oracle cambia explícitamente de 2 a 0.9 WETH/unidad; el precio inicial de la DEX es también 0.9, reservas 1,000/900. IRM cero: no se afirma reconstrucción histórica de intereses. El gas de preparar protocolos y reservas se registra como coste del fixture externo, no como coste de una integración con contratos ya existentes. Sí se incluyen ambos despliegues nuevos de NQC.

## Ciclo positivo reproducido

| Magnitud | Base units / resultado |
|---|---:|
| Garantía vendida | 9.278589654372535368 COLLATERAL |
| Conversión ejecutada | 8.249365645570551238 WETH |
| Deuda devuelta a Morpho | 8 WETH |
| Excedente antes de asignaciones | 0.249365645570551238 WETH |
| WETH desenvuelto para pagos | 0.09 WETH |
| Reembolso directo al sponsor | 0.05 ETH |
| Tip al proponente | 0.04 ETH |
| Saldo NQC final nuevo | **0.159365645570551238 WETH**, 0 ETH |

El contrato anterior reservaba 0.1 WETH y devolvía 0.01 ETH al operador en el escenario comparable. Aquí se reserva exactamente refund+tip=0.09 para separar el sobrante de financiación del ingreso nativo: cambia el vector WETH/ETH, no se crea margen económico adicional.

La comisión V2 y el impacto ya están contenidos en la salida. `exact-sensitivity.json` descompone con fracciones el valor inicial, comisión marginal y reducción por impacto/redondeo; **no** vuelve a restarlos. El techo a profundidad infinita permanece aproximadamente 0.325678496868 WETH, inferior a la antigua asignación de 0.5 ETH. No se elevó el precio para hacer pasar el caso.

| Transacción local | Gas cobrado |
|---|---:|
| Fondeo sponsor→EOA | 21,000 |
| CREATE adapter | 411,179 |
| CREATE ejecutor | 1,362,395 |
| Liquidación completa | 502,632 |
| Devolución de anticipo | 21,000 |
| Pago separado sponsor→builder simulado | 21,000 |
| **Total** | **2,339,206** |

Con baseFee=1 gwei, priorityFee=1 gwei y cap=3 gwei, el coste efectivo total es 0.004678412 ETH. El cap no es gasto. La EOA recibe A=0.03 ETH; paga 0.004594412 ETH de gas y devuelve U=0.025405588 ETH **con recibo exitoso**. Sponsor paga además 0.000042 ETH de fondeo, 0.000042 ETH del pago al builder y 0.002 ETH de remuneración de este.

`M_sponsor = 0.05 + 0.025405588 − 0.03 − 0.000042 − 0.002042 = 0.043321588 ETH`.

Coste de oportunidad de laboratorio explícito: ceil(A/10000)=0.000003 ETH por secuencia, sin anualización ni afirmación de tasa comercial. Margen ajustado: **0.043318588 ETH**. El builder simulado recibe 0.002 ETH de una transferencia separada; el proponente recibe el tip y las priority fees. No se consolidan esas direcciones. Los costes comerciales de cada entidad permanecen UNKNOWN.

El cap agregado del gas de la EOA es 0.031542 ETH, superior al anticipo 0.03. La secuencia local sí cabe porque cada transacción libera su reserva no gastada antes de la siguiente. El filtro anterior que suma todos los caps es conservador y puede bloquear este estado; no es contradicción con el cobro observado ni evidencia de política de admisión real.

## Refutación del margen del sponsor bajo gas mayor

Con baseFee=20 gwei, priorityFee=1 gwei, cap=30 gwei y A=0.3 ETH, el ciclo también liquida y repaga. El gas total cuesta 0.049123326 ETH; el sponsor termina en **−0.001123326 ETH** de caja, o **−0.001153326 ETH** después del cargo de oportunidad 1 bp. NQC mantiene el mismo WETH final. Por tanto, EVM_LOCAL_PASS no implica que financiar sea rentable.

Manteniendo gas y A base fijos, la frontera aritmética estricta del sponsor después de oportunidad es 20.518500722 gwei: +93,268 wei en la frontera; un wei/gas adicional da −2,245,938 wei. Ese cálculo **no** acredita saldo inicial suficiente a esa tasa ni gas invariable ante otros parámetros.

## Atomicidad y alcance de la comparación C1/C2

Las trazas y logs se reconcilian independientemente con snapshots para cada actor y activo en cada transacción. Se excluyen ramas revertidas, se contabilizan quema de base fee y crédito de priority fee, y no se suman las transacciones huérfanas del control de reorg a la rama restaurada. No se usan firmas ni nodos de producción.

Los 17 tests existentes del core original se reejecutaron: C1 funciona sin cash Morpho; C2 con flash necesita al menos los 8 WETH del préstamo. Ambas requieren conversión suficiente y revierten con mercado insuficiente. Los 516,339/400,205 anteriores eran gas de marcos de llamada calientes, **no** recibos de esta secuencia. No se comparan con los 502,632 cobrados aquí para declarar superioridad. La primera operación C2 con fondeo, despliegues/adaptadores y devolución completa está **NOT_RUN** en este estudio. Bundler3 deprecado, disponibilidad/configuración de adaptadores y seguridad siguen siendo requisitos, no ventajas asumidas.

La ventaja de C1 probada es una menor exigencia de cash del token de deuda dentro de Morpho, no una ventaja económica/captura certificada. No hay principal flash que se pueda contar como beneficio en C1.
