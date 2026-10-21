# Replay original — BLOQUEADO ANTES DE EJECUTAR EVM

Caso: Ethereum 1, bloque 25666958, padre 25666957, índice 0,
`0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2`.

**No hay PASS de replay, receipt local, gas reproducido ni primera instrucción EVM fallida.**
La primera dependencia ausente es el RPC histórico autorizado: `NQC_RPC_URL` no está configurado.
La puerta de entrada se ejecutó y terminó con código 2; ver `evidence/replay_input_gate.json`.

## Lo recuperado y lo ausente

| Pieza | Resultado de esta ejecución |
|---|---|
| Rama y HEAD remoto inicial | Verificados: `research/pt-stcusd-evidence-20261021`, `ef42fa89eb990817892f468ed038b37ed5a21821` |
| Contexto de los dos bloques | Metadatos nuevos del indexador; hashes enlazados y timestamps separados por 12 segundos |
| Cabeceras RPC completas / roots | Ausentes. Los metadatos indexados no las sustituyen |
| Calldata completa / transacción original | No recuperadas |
| Receipt completo / 53 logs crudos | No recuperado; se conserva la normalización anterior de 53 eventos |
| ABI Morpho | Recuperado del explorador; no acredita runtime al bloque padre |
| Bytecode / implementaciones / slots históricos | No recuperados |
| Prestate / call trace / state diff | No recuperados |
| Liquidez y posiciones de ambos mercados | No medidas al padre |
| Foundry | 1.8.5 descargado; SHA-256 del archivo y binarios registrados y verificados |
| Solidity | Binario 0.8.26 existente verificado contra `ethereum/solc-bin`; no se compiló un ejecutor nuevo |
| Fork original / comparación EVM | No iniciados por falta de inputs |

Las respuestas exactas de PublicNode y dRPC son HTTP 403, cuerpo `error code: 1010`.
No se obtuvo ni `eth_chainId`; no pueden interpretarse como rechazo del método de archivo.
Alchemy recibió **cero solicitudes**: falta el secreto, por lo que no hay respuesta de Alchemy que clasificar.
Blockscout REST rechazó el acceso a la traza y solicitó reconfiguración con clave PRO.
No se reinicializó la sesión ni se reintentó tras inspeccionar ese rechazo.
Las llamadas nativas ya emitidas devolvieron metadatos y ABI, con contador de cuota disponible;
esa discrepancia de superficies queda preservada, no se usó para eludir el rechazo.

## Condiciones de fidelidad aún pendientes

Un fork al cierre del padre no equivale por sí solo al preestado de la transacción 0.
Debe incorporar el timestamp, basefee, coinbase, gas limit, prevRandao y contexto histórico de BLOCKHASH,
además de las transiciones de sistema aplicables antes de las transacciones.
La configuración Mainnet fijada de Geth tiene Osaka activo para este timestamp; se requiere verificar
también EIP-4788/EIP-2935 y cualquier otra transición activa que afecte al conjunto de estado utilizado.
Las retiradas de consenso y operaciones de fin de bloque no deben adelantarse al preestado.
La configuración archivada tiene BPO2 activo; no se verificó experimentalmente el contexto de blobs del replay.

El cierre futuro exige comparar el original contra su receipt auténtico: éxito, 53 logs byte a byte,
gasUsed 1870816, movimientos, cambios de cuentas/slots, saldos por transacción y las dependencias llamadas.
Estos valores de gas siguen procediendo de la transcripción anterior, no de un receipt nuevo.
Un `prestateTracer` contiene los valores tocados, no pruebas criptográficas; debe delimitarse su cobertura
y contrastarla con el padre y las transiciones del bloque. El conjunto de cuentas de la variante puede ser mayor.

`src/preflight.py` valida inputs sin declarar ejecución. Incluso su resultado
`INPUTS_PRESENT_EVM_AND_PROOFS_NOT_VERIFIED` no certifica estado, EVM ni rentabilidad.
No se escribió un ejecutor sustituyendo la ruta Pendle/cUSD/bóvedas por mocks.

Referencias: `evidence/mainnet_chainspec.json`, Geth commit `1c6b3104fad2f37b016770c0a66b03831a1f5d70`;
https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers ;
https://github.com/ethereum/EIPs/blob/master/EIPS/eip-4788.md ;
https://github.com/ethereum/EIPs/blob/master/EIPS/eip-2935.md .
