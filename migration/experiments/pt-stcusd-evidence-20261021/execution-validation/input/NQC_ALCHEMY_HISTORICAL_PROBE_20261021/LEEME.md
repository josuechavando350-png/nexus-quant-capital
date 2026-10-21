# NQC — Prueba de RPC histórico (21 octubre 2026)

**Objetivo:** obtener datos auténticos de Ethereum Mainnet para la liquidación histórica PT-stcUSD/USDC, bloque 25,666,958, primera transacción `0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2`.

**Contenido:** `probe.py`, pruebas locales. No lleva claves API ni endpoint específico del propietario. Solo envía consultas de lectura de una lista cerrada, nunca transacciones. No toca GitHub, wallets, Titan ni despliegues.

**Estado en este entorno:** se intentaron tres consultas reales (chainId, cabecera padre y transacción), sin éxito por `Temporary failure in name resolution` antes de contactar Alchemy. Eso no certifica ni refuta que la clave funcione. Las pruebas `unittest` usan respuestas simuladas expresamente y no sustituyen blockchain.

## Ejecución con acceso a internet (Python >= 3.10)

En tu propio terminal, tras crear o rotar la clave en el panel de Alchemy:

```sh
export NQC_RPC_URL='https://eth-mainnet.g.alchemy.com/v2/TU_CLAVE_NUEVA'
python3 probe.py --output nqc_archive_probe_output
python3 -m unittest discover -v -s tests
```

En PowerShell:

```powershell
$env:NQC_RPC_URL = 'https://eth-mainnet.g.alchemy.com/v2/TU_CLAVE_NUEVA'
py probe.py --output nqc_archive_probe_output
py -m unittest discover -v -s tests
```

Solo si el uso/cuota permitida de Alchemy admite trazas históricas:

```sh
python3 probe.py --trace --output nqc_archive_trace_output
```

Este modo agrega dos llamadas: `debug_traceTransaction(prestateTracer)` y `(callTracer)` que pueden costar más unidades de cómputo. El script limita cada resultado a 30MB y guarda resultados crudos en archivos. No subas la carpeta de salida sin revisar sus contenidos. Nunca añadas el endpoint a README, commits, issues ni capturas. Rota la clave que apareció en el chat, sin necesidad de compartir la nueva.

Los datos de `report.json` permiten distinguir: cadena equivocada; método no admitido; falta de capacidad archivística; errores HTTP/red; cabeceras y recibo auténticos. Los datos por sí solos aún no son una reproducción en EVM, no prueban ganancia ni aceptación por Titan.

Referencias: https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-get-proof y https://alchemy-api-docs.readme.io/reference/debug-tracetransaction
