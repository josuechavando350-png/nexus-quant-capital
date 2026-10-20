# Resultado real de ejecución — 20-oct-2026 UTC

## Dictamen

**Compilación aprobada e identidad del bloque corroborada. Replay EVM original y variante sin principal NO ejecutados. Rentabilidad NQC NO demostrada.**

Caso único: Ethereum, bloque 21,762,897, índice 1, transacción `0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb`.

## Evidencia de los tres jobs terminados

| Run / job | Productor | Resultado |
|---|---|---|
| [39379436674](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39379436674) / 118484897870 | 7ebc7ab9e18feed6e2dd429c17b8a58d7581d3d4 | Foundry y Solc verificados por hash; dos archivos Solidity compilaron en 2.15 s. La primera lectura eth_chainId agotó 20 s. Una solicitud. |
| [39379758996](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39379758996) / 118485932064 | 5790950a67ebdab0b04f638034cda513f5e0364a | Compilación repetida correcta en 2.07 s. Identidad de Ethereum y bloques padre/objetivo recibidos y comprobados. La cuarta lectura, eth_getTransactionReceipt, devolvió null. |
| [39380596580](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39380596580) / 118488590873 | 7943fea26dc94fef6b59d11cf8787be16beca240 | Diagnóstico distinto por hash de bloque: eth_getBlockReceipts respondió HTTP 200 y null. Se detuvo tras una lectura; no ejecutó las otras dos previstas ni EVM. |

**Seis solicitudes RPC totales al mismo origen, https://ethereum-rpc.publicnode.com. No hubo repetición automática, cambio de proveedor, reinicio de cupos agotados, claves, firmas ni operaciones financieras. Todos los jobs terminaron; no hay vigilancia o replay corriendo en segundo plano.**

Extractos seleccionados leídos mediante el conector de GitHub (no una descarga íntegra de los logs):

```
RUN 39379758996
Compiling 2 files with Solc 0.8.26
Solc 0.8.26 finished in 2.07s
Compiler run successful!
ANCHOR_CHECKS {"parent_hash": true, "target_hash": true, "parent_link": true, "height": true, "timestamp": true, "base_fee": true, "prefix": true, "target_index": true, "count": true}
STOP Closed: Closed: Missing historical result: eth_getTransactionReceipt

RUN 39380596580
HTTP 200; body_bytes=38
Closed: Missing historical result: eth_getBlockReceipts
receipts_recovered=false; historic_code_received=false
baseline_replayed=false; variant_tested=false
```

La compilación usa Foundry 1.3.1 y Solc 0.8.26+commit.8a97fa7a oficiales, con hashes fijados y comprobados. No se alteraron los archivos Solidity originales ni los resultados esperados para obtener aprobación.

## Alcance de los resultados

Pasaron las nueve comprobaciones de hash padre, hash objetivo, enlace padre, altura, timestamp, base fee, transacción precedente, índice de la liquidación y total de 41 transacciones. Esto corrobora identidad y contexto de bloque; no equivale a un recibo, una prueba de estado ni la ejecución de la variante.

El nodo no entregó los recibos por ninguna de las dos consultas probadas. La especificación de Ethereum admite null cuando no se encuentra un recibo; no significa transacción revertida ni prueba que la operación histórica no existiera. La causa concreta sigue desconocida. Geth documenta retención independiente y limitada del índice de transacciones; se investigó como hipótesis y no quedó confirmada. No se omite el requisito del recibo ni se sustituye con datos inventados.

**No se alcanzaron lecturas de código, almacenamiento o saldos históricos de cuentas. Su disponibilidad sigue sin comprobarse. No se midió gas de la variante. No hay patrocinador aceptado ni beneficio neto NQC nuevo.** Los 1.9154 ETH de la contabilidad previa no fueron producidos ni cobrados por estas ejecuciones.

## Aislamiento y límites

En cada job: nueve pruebas de aislamiento del baseline y doce pruebas del transporte pasaron. Son las mismas pruebas repetidas, no 63 pruebas económicas distintas. Ocho casos sintéticos adicionales de selección de recibos pasaron localmente. Ninguno demuestra ingresos.

main conserva `16e352225ba8a6a931834c4edf3d86d9a2924b7d`; se creó un workflow aislado nuevo bajo revisión específica y no se reactivaron los 106 heredados. El verificador global original rechaza el nuevo árbol por su workflow activo (`forbidden active/client tree`): se registra esa diferencia y no se declara certificación global. Cero fondos de wallet utilizados, firmas, transacciones difundidas o servicios de pago contratados. No se llamaron Blockscout, Triport ni Desktop Commander en este trabajo de ejecución.

Los cuerpos RPC completos quedaron en runners efímeros; sus hashes aparecen en logs, pero no fueron recuperados íntegramente al contenedor. No presentar esos hashes como sustituto de los cuerpos ausentes. Hash del registro de consultas del segundo job: `8ebc19ea586880d00b6d72f2a03a11057d43140cdfff993e335561b9570911af`. Hash del registro del diagnóstico por bloque: `cb1715a58f071385b29bde0c0f34eb6040a8300c623fa06bee72fa56c8a9d912`.

## Siguiente condición — mismo caso, no otro censo

Obtener una fuente autorizada que entregue el recibo exacto, las transacciones precedente/objetivo y código/storage/saldos/nonces al bloque padre 21,762,896; o un testigo completo verificable del preestado. Antes de relanzar hay que comprobar esa cobertura. No se ha verificado otra fuente ni se contratará un servicio por suposición. La reconstrucción original debe pasar antes de probar la variante; después deben medirse costos completos y financiación. commercial_admission=false, canary_enabled=false, realized_NQC_profit=null.

**Bueno:** ya funcionaron el servidor, las herramientas, la compilación y la lectura de bloques reales. **Malo respecto a la meta comercial:** no se completó la ejecución ni se demostró dinero. Prueba no aprobada por evidencia incompleta, no refutada por pérdida económica.

## Referencias primarias consultadas

- https://ethereum.github.io/execution-apis/api/methods/eth_getTransactionReceipt/
- https://ethereum.github.io/execution-apis/api/methods/eth_getBlockReceipts/
- https://geth.ethereum.org/docs/fundamentals/command-line-options
- https://ethereum.publicnode.com/

La evidencia primaria de los resultados son los tres jobs enlazados, no las referencias técnicas generales.
