# Original - ejecución real bloqueada

## Identidad y herramientas

Productor de antecedente: run 39453561233 / job 118734415837 / commit b5f263c3b620c7ad8f81f3a205288f52b0baf605. Sus logs completos están en evidence/prior_run/log_118734415837.log. Los tres runs anteriores también se conservan íntegros como logs, sin inventar los cuerpos que no exportaron.

Fuente: source_bundle SHA256 712bc3461b04bb6411947ae0bed68704de2ff825e29ba05ee31d47f7c8918514; seis hashes verificados en evidence/SOURCE_INTEGRITY.json. Foundry 1.3.1 (commit 08d3a4ad4d78b62bcb897350803bf96fc2cf6cc9); solc 0.8.26+commit.8a97fa7a. Archivo oficial Foundry SHA256 baad3e1b06d6f310d210c93e95258a03d923fe610f8d0742138f2245f94abd7c; solc SHA256 d5f23436f443edb85d8e76906d12f0a86ce0490e7663a9e608efeb7a93f149ef. Compilación local original: exit 0, dos archivos en 2.34 segundos según salida del comando. Los replays posteriores reutilizaron esa compilación.

## Secuencia real de intentos

| Intento | Lecturas upstream nuevas | Resultado |
|---|---:|---|
| Metadato de altura local | 0 | setUp falla en eth_gasPrice. |
| Flag --gas-price histórico | 0 | Foundry sigue pidiendo eth_gasPrice al inicializar. |
| Altura y gas históricos locales | 37 | 36 respuestas HTTP 200; fallo de túnel en lectura 47 dRPC acumulada. |
| Reproducción offline posterior | 0 | Falla exactamente en el mismo slot ausente. |

La consulta inicial de saldo en este turno fue una lectura adicional exitosa, fuera de la tabla: total del turno 38 intentos. Total dRPC 47; PublicNode previo 6. Los primeros dos fallos locales no generaron reintentos upstream.

Comando económico intentado (rutas concretas completas en RESULT.json):

```bash
forge test --offline --use /ruta/verificada/solc --gas-price 302819782345   --match-contract HistoricalFlashReplayTest --match-test '^test_01_' -vvvv
```

El test mantiene createSelectFork por hash de la transacción objetivo: Foundry intenta el prefijo antes de tx1. No se sustituyó el preestado por el cierre del padre. Duración del intento: 114.864483932 s; exit 1; se detuvo en setUp, antes de la liquidación objetivo. No se obtuvo receipt local original, paridad final, traza económica completa ni comparación completa de gas/saldos.

Primer punto de divergencia: lectura histórica de storage 0x3, cuenta 0x111111125421ca6dc452d289314280a0f8842a65, bloque padre 21762896. No es un revert de protocolo, déficit de devolución ni cambio de precio: falta una dependencia de estado tras un rechazo de transporte.

Reproducción sin red:

```bash
python3 reproduce_offline.py /ruta/de/binarios/verificados
```

Resultado conservado: 46 respuestas exitosas disponibles; mismo primer acceso faltante; exit 1; cero red. El script de continuación online se publicó bloqueado por el estado terminal registrado. No ejecutar las copias históricas de fuentes como una nueva autorización de red.

## Lo contrastable y lo pendiente

Se conservaron y verificaron identidades de recibos, bloques, orden y transacciones; se decodificaron los eventos históricos y sus cantidades. Se leyó reserve0=38669555298186 y reserve1=16417414753955494219446 en slot 8 de V2 al padre, compatibles con el Sync/Swap original. Es evidencia más fuerte que una transcripción, pero no completa tx0.

No se ejecutaron las aserciones de oráculo, parámetros Morpho, saldo inicial del ejecutor original ni resultados finales: setUp no llegó a ellas. El recibo remoto con status 1 prueba el dato histórico reportado por RPC, no que el replay local haya pasado.
