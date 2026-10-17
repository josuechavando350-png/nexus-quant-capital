# Coordinación local: qué se demostró

`EVM_LOCAL_PASS` para A1 y A2 C1: seis transacciones exitosas, deuda saldada, transferencias conciliadas y devolución U recibida. A1 ocupa seis bloques; A2 ocupa un bloque con índices 0–5. Ambos cobran **2,339,206 gas** con cash Morpho cero. El anticipo es 0.03 ETH, exclusivamente del financiador sintético; la EOA NQC comienza sin ETH, WETH ni garantía.

| Transacción | Nonce del emisor | Gas cobrado | Emisor |
|---|---:|---:|---|
| Anticipo A | 0 | 21,000 | Financiador |
| CREATE adaptador DEX | 0 | 411,179 | NQC |
| CREATE ejecutor | 1 | 1,362,395 | NQC |
| Liquidación | 2 | 502,632 | NQC |
| Devolución U | 3 | 21,000 | NQC |
| Pago builder de laboratorio | 1 | 21,000 | Financiador |

Base fee 1 gwei, priority fee 1 gwei, precio efectivo 2 gwei. Cap 3 gwei salvo retorno U, cuyo cap es exactamente 2 gwei para vaciar el saldo con límite 21,000. Los límites CREATE son 4,000,000 cada uno; liquidación 2,500,000. El anticipo mínimo para cubrir los prefijos a esos límites/caps y gas observado es 12,822,358,000,000,000 wei; el gas NQC realmente consumido es 4,594,412,000,000,000 wei. Cap, reserva y consumo no son intercambiables.

## Ajustes del nodo y límite de la prueba

Anvil 1.7.1 fijado por SHA-256; cadena 31337, Cancun, cuentas 0, sin fork, host 127.0.0.1, timestamp inicial 1800000000. El arnés usa `eth_sendUnsignedTransaction`, `evm_setAutomine(false)`, un timestamp/base fee explícitos y `evm_mine`. El orden base es `--order fifo`. Comando íntegro en cada escenario. `anvil_dropAllTransactions` vacía el pool local antes de cada candidato; los snapshots de estado no se usan como garantía de limpiar transacciones pendientes.

El pool estándar rechaza la transacción de la EOA aún vacía aunque su fondeo esté pendiente. Se necesita `--disable-pool-balance-checks` para introducir el candidato completo. **No se deshabilitan verificaciones EVM de saldo ni límites de gas/tamaño.** El control sin fondeo acepta el candidato en el pool modificado pero incluye cero transacciones. Esto prueba la diferencia entre admisión al pool y validez al construir el bloque; no reproduce la política de un relay real. Los cuatro controles están en `pool-admission-probe.json`.

U se calcula mediante una simulación local acotada del candidato y restauración del snapshot, antes de minar el bloque observado. Esa primera simulación se descarta y no se cuenta como operación adicional. No es una predicción garantizada de fee/estado del próximo bloque real.

## Evidencia independiente por índice

Cada recibo conserva transactionIndex/blockHash y cada llamada su call trace. `prestateTracer` con diffMode permite reconstruir ETH y las celdas de balance WETH/garantía por índice. Los slots se fijan contra las fuentes originales: Solmate balanceOf slot 3; Uniswap ERC20 balanceOf slot 1. Estos snapshots **no se deducen de los logs que luego se concilian**: los flujos CALL/Transfer y gas se contrastan contra el diff independiente. El estado final se vuelve a consultar por `eth_getBalance`/`balanceOf` y debe coincidir. Son observaciones del mismo nodo local, no pruebas de estado autenticadas de mainnet.

## Prefijos y política de selección

Anticipo solo: financiador −0.030042 ETH, NQC retiene 0.03 ETH de financiación, ninguna liquidación. Anticipo más despliegues: contratos incluidos y gasto irreversible dentro del bloque seleccionado, aunque no haya liquidación. Una liquidación revertida deja esos CREATE anteriores en estado; solo revierte su propia llamada. La devolución U puede fallar o ser omitida después de una liquidación exitosa.

`policy_exclusion.py` simula dos candidatos desfavorables (C2 sin cash; C1 a 21 gwei), restaura su estado de simulación, rechaza la selección y mina un bloque vacío: cero gas y saldos/nonces sin cambios. Esto representa **exclusión antes de inclusión**. No permite recuperar fondos después de un bloque minado, no es atomicidad EVM entre transacciones y no acredita política Titan/Quasar. Tampoco una restauración local equivale a una garantía de reorg en Ethereum.

Al cambiar orden a fees y elevar la priority fee del pago separado, el orden observado pasa a anticipo→CREATE→CREATE→liquidación→builder→U. No se supone que cualquier política de prioridad produzca el orden deseado. La identidad y posición final de cada transacción están en `A3_priority_change.json`.
