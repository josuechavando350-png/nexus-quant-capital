# NQC: 21 slots verificados y conciliación económica retrospectiva

21 octubre 2026. Investigación; NO replay completo, NO beneficio NQC demostrado.

## Evidencia recibida

ZIP `NQC_MORPHO_21SLOTS_RESULTADOS_20261021T201919839928Z.zip`, SHA-256 `b5801d1155442230d19eb1ac38295da2cd4caa15f1d31ed62ea3594bc5e3f62b`. Verificados CRC, manifiesto y las 21 pruebas de Morpho contra el estado padre 25,666,957: 18 inclusiones y 3 exclusiones de valores cero. Se recalcularon hashes de cabeceras padre/objetivo y de los bytes firmados EIP-1559 de la transacción `0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2`. Los 53 eventos coinciden con la normalización anterior. No se verificó consenso/finalidad, inclusión del recibo ni recuperación de firmante.

## Cálculos reproducidos

Aplicando las fórmulas enteras de Morpho fijadas a `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`:

- Colateral padre: 3520.189382262310704247 PT (18 decimales del catálogo anterior).
- Deuda a partir de totales almacenados, ANTES de nueva acumulación: 3220.923540 USDC. No es deuda actualizada al timestamp del padre.
- Con tasa histórica observada en el recibo y timestamp objetivo: deuda 3220.954251 USDC, exactamente igual a Liquidate. Las 2929329463624198 acciones de deuda fueron repagadas.
- Interés del mercado liquidado: 0.144548 USDC en 2556 segundos; parte de incremento del prestatario: 0.030711 USDC.
- Colateral incautado: 3305.257748749184918001 PT; remanente calculado: 214.931633513125786246 PT.
- Segundo mercado: 37976639.627801 USDC contablemente no prestados. Participaciones del adaptador equivalentes a 83839314.575196 USDC antes de nueva acumulación; no todo ese importe es retirable simultáneamente.
- Retiro observado: 3305.262344 USDC. Interés del mercado de retiro: 7.998219 USDC en 24 segundos. Acciones quemadas calculadas: 3041008266525406, idénticas al recibo.

Las tasas proceden del recibo, NO de una ejecución independiente del IRM. Liquidez contable y participaciones suficientes NO certifican saldo real ERC-20, autorizaciones, condiciones de bóvedas ni toda la ruta.

## Umbral del oráculo: inferencia, no lectura directa

La fórmula de liquidación y el colateral incautado implican un precio entero dentro de `999993968776204378630476 .. 999993968776204378630778` (303 valores posibles). En todo ese intervalo, deuda máxima permitida: 3220.953858 USDC. Diferencia con la deuda actualizada: **0.000393 USDC**.

Esto es una inferencia inversa condicionada a la fórmula y el recibo. No acredita el valor del oráculo independientemente ni elegibilidad en el timestamp padre. No es beneficio de trading. No asumir precio de 1 USDC ni reemplazar los redondeos.

El excedente histórico del tercero continúa siendo 84.308093 USDC antes de costes completos; no es P&L de NQC. `nqc_net_profit=null`, `titan_acceptance=null`, captura prospectiva no acreditada.

## Programa preparado para Termux

`NQC_DIAGNOSTICO_EVM.pyz`, SHA-256 `829657d4e25f1f73f67dc94dab999e5447eb587f688a5204e561e67e1cd5291b`, 23818 bytes. Distribuido como adjunto de conversación junto con `NQC_AUDITORIA_21SLOTS_20261021.zip`. No está integrado en el motor ni incorporado como binario en este commit.

Con `--consultar` hace HASTA CINCO lecturas: precio del oráculo, borrowRateView con los totales probados, código del ejecutor histórico, prueba de su cuenta y finalmente eth_call del original. Todas fijadas al bloque PADRE 25666957; cero firmas/envíos, overrides, fondos inventados, trazas, reintentos o cambios de proveedor. Para el eth_call original se conservan el emisor, calldata, gas y comisiones históricos. No es una variante NQC ni prueba de capital cero.

La última consulta es un diagnóstico de ejecución en el PADRE, no una reproducción exacta del contexto OBJETIVO 25666958. Un retorno exitoso no verifica gas, logs ni beneficio; un revert no demuestra inviabilidad. Los resultados incluyen este límite. Usa NQC_RPC_URL o entrada oculta y genera un ZIP nuevo en Descargas; no guarda el endpoint.

## Verificación y alcance de publicación

43 pruebas nuevas aprobadas: 23 de evidencia/aritmética y 20 de transporte y seguridad con fixtures sintéticos. Reejecutadas 40 anteriores (31+9), aprobadas. Las impresiones HTTP 200 de los tests son simuladas, no llamadas Alchemy. Cero nuevas consultas RPC Ethereum en esta auditoría. No se ejecutaron Solidity, Foundry, replay completo, Rust ni verificador global de aislamiento: no hay checkout completo local. El acceso al registro npm falló por DNS; no se instaló un motor EVM.

Este commit añade SOLO este documento de continuidad. Código, pruebas, entradas originales, resultados y manifiesto se conservan en el paquete descargable, no se presentan como publicados íntegramente en GitHub. No cambia main, ejecutores, fuentes históricas ni workflows.

Reproducir el paquete: `python -B verify.py` (offline, sin API). Próxima entrada: el ZIP generado por el diagnóstico Termux. La prioridad sigue siendo ejecutar y conciliar la operación completa; estas comprobaciones no autorizan mainnet.

Fuentes: archivos originales aportados por el propietario; Morpho.sol, MathLib.sol, SharesMathLib.sol, ConstantsLib.sol e IIrm.sol en el commit fijado; https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-call .
