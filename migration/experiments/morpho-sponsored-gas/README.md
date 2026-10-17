# NQC — Morpho Blue + builder-sponsored gas | experimento aislado

**Estado a 2026-10-16:** Investigación en curso, sin certificación ni autorización de mainnet. Este directorio es independiente de las fuentes históricas certificadas de NQC. Ninguna línea modifica PFT, RMC o T36. NO contiene claves, RPC de pago, transacciones firmadas, despliegues ni workflows activos.

## Conclusión de ingeniería confirmada

- Morpho Blue `liquidate` envía el colateral al `msg.sender`, invoca `onMorphoLiquidate` cuando hay `data`, y después cobra `repaidAssets` mediante `transferFrom`. Referencia [Morpho.sol](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol).
- [Titan](https://docs.titanbuilder.xyz/api/eth_sendbundle) y [Quasar](https://docs.quasar.win/api/eth_sendbundle) documentan bundles patrocinados para EOAs sin ETH, sujetos a una devolución económica suficiente al builder.
- Nuestro ejecutor histórico `ci/nqc-t36/contracts/src/NqcFlashFundingExecutor.sol` **solo admite Aave V3 y Balancer V2**. No es compatible automáticamente con Morpho.
- Ningún dato anterior demuestra que una liquidación de Morpho sea capturable por NQC. El archivo `fixtures/illustrative.json` es deliberadamente sintético.

## Qué se ha construido

- `preflight.py`: filtro económico **determinista, fail-closed, solo lectura, sin red ni dependencias externas**. Evita asumir que los tokens de ganancia pagan gas. Requiere conversión explícita al ETH, adelanto de gas por el builder y margen positivo para ambos. Un escenario sintético queda siempre bloqueado.
- `tests/test_preflight.py`: pruebas de regresión que obligan a bloquear financiación deficiente, riesgo de ejecución, capital aportado artificialmente, ruta no simulada y falsa certificación.
- `contracts/NqcMorphoSponsoredLiquidation.sol`: **borrador experimental NO compilado en este entorno** de ejecutor con callback de Morpho, swaps estrictamente medidos, saldo inicial cero, gas-tip desde ETH obtenido en la propia operación y beneficio mínimo al operador. No es apto para producción, no está auditado y NO prueba compatibilidad con Titan/Quasar. Requiere pruebas Foundry independientes y un adaptador real autorizado.

## Ejecutar las pruebas disponibles

```sh
python3 -m unittest discover -v -s tests -p 'test_*.py'
python3 preflight.py fixtures/illustrative.json
```

El segundo comando retorna código 2 (BLOCKED) deliberadamente: hay 6 faltantes. El reporte numérico de ejemplo **no es una ganancia**. Los nombres de tokens no especifican decimales porque las entradas son siempre unidades enteras mínimas de cada activo.

## Barreras abiertas: no enviar bundles reales

1. **DEPLOYMENT:** con cero ETH de origen, demostrar que Titan o Quasar admite un bundle atómico que despliegue el contrato y después lo ejecute, o identificar un executor previamente desplegado bajo condiciones seguras. El código por sí solo no prueba esto.
2. **FORK:** obtener un bloque histórico real de Morpho Ethereum, prestate reproducible y par liquidable. Compilar Solidity 0.8.24 con Foundry y probar la llamada contra *Morpho real*, no un mock.
3. **LIQUIDEZ:** conectar un adaptador de swaps (solo venues admitidos) y obtener salida real del colateral a token de deuda, y salida de parte del excedente a WETH/ETH, incluidas comisiones y price impact. Nunca aceptar como salida vendible un precio de oráculo.
4. **SPONSOR ECONOMICS:** confirmar mediante simulación de bundle cómo calcula cada builder su balance incremental. **Enviar ETH a `block.coinbase` puede remunerar al validador, no necesariamente al builder.** El importe nominal de `coinbaseTipWei` en el contrato NO sustituye una medición de ingresos del builder. Testear ambas rutas de manera independiente.
5. **COMPETITION:** timestamp de oportunidad y comparación frente al primer liquidador ganador. Repetir una liquidación después de que un tercero ganó no prueba que NQC pudiera capturarla.
6. **SCOPE:** no elevar `MODEL_SCREEN_PASS_ONLY` a certificación, P&L realizado, garantía de inclusión o permiso para firmar. Mantener NQC original congelado hasta superar estas barreras.

## Criterio de continuación

- **PASS técnico futuro:** Morpho original ejecuta correctamente la liquidación en fork anterior a transacción con una EOA y contrato inicialmente sin fondos, se liquida deuda y un modelo de patrocinio verificado demuestra builder solvente + saldo positivo para NQC.
- **PASS económico futuro:** simulación con ruta DEX real, gas y builders reales, y comparación temporal con ganadores; ninguna evidencia se fabrica para superar gates.
- **STOP:** despliegue sin patrocinio, ingresos del builder no verificables, falta de liquidez o costo que excede beneficio.

## Primera transacción histórica recuperada (no rentable certificada)

`observations/ethereum_morpho_2026-06-26_seed.json` preserva los campos de una liquidación Morpho **real y exitosa de otro operador** en Ethereum: [tx 0x0a2f...](https://etherscan.io/tx/0x0a2f442acfb350d6d93002038b454ead40ffcf28a777b291cbaec1746d8aa2f1), bloque **25402186**, hash `0x8691c49e741bb2432a31ef9fe708d18ad4f343c12f171c8ec1ae07510e3a3a09`. Reproduce exactamente el gas observado: **182,780 × 1,771,490,340 wei = 323,793,004,345,200 wei**. Esto demuestra conciliación de recibo, **no rentabilidad**. La transacción llevaba `data=0x`, por lo que **no se usó el callback** que queremos probar. Está conservada como candidato de referencia para elegir casos y como prueba de NO inferir valores de NQC a partir de un ganador histórico.

## Caso reciente detectado: ejecución compleja de Morpho (2026-10-14)

Se encontró una segunda operación auténtica en Ethereum, [tx `0x46300e...`](https://eth.blockscout.com/tx/0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b), bloque `26,190,955` hash `0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8`. Un liquidador **externo** procesó aproximadamente 24.34398 EZETH de garantía y devolvió aproximadamente 26.0397385 WETH al protocolo. Aparecen 26.4096809 WETH acuñados por envolver ETH y **0.3680927 WETH retirados a ETH**, con diferencia no explicada de 0.0018497 WETH. Gas pagado: 745,509 unidades a 266,148,625 wei, equivalente a 0.000198416195275125 ETH; prioridad de gas registrada: **cero**.

**Hallazgo:** el mercado sí muestra liquidaciones con rutas complejas y movimiento bruto considerable. **No es prueba de beneficio capturado por NQC ni de patrocinio automático**: no tenemos el detalle completo de transferencias nativas, reparto de builders, caja final del ejecutor ni la ruta reproducida en fork. No convertir el ETH retirado de WETH en beneficio neto sin conciliar toda la transacción.

## Incremento experimental 2026-10-16 — integración de repositorio

- Se agregó `bundle_gate.py` y `fixtures/synthetic_two_transaction_bundle.json`: modelo de financiación de **dos transacciones** consecutivas desde la misma EOA inicialmente sin ETH (`DEPLOY_EXECUTOR` + `EXECUTE_LIQUIDATION`). Exige cubrir los límites de gas de **ambas**, no solo el gas de liquidación. No presume que un builder financie despliegues: `builder_sponsored_deployment_supported=false` impide la promoción.
- `bundle_gate.py` **no** considera automáticamente una transferencia a `block.coinbase` como ingresos para Titan/Quasar. La elegibilidad requiere una simulación con estado económico del builder medido independientemente, todavía no disponible.
- El borrador `contracts/NqcMorphoSponsoredLiquidation.sol` fue corregido para manejar **préstamos denominados en WETH**, como el caso histórico EZETH/WETH del 14 de octubre, y ahora utiliza efectivamente `Plan.minLoanOut` como protección de salida en callback.
- `tests-solidity/NqcMorphoSponsoredLiquidationMock.t.sol` aporta una prueba **pendiente de ejecución** de la ruta WETH, rechazo por salida insuficiente y bloqueo de prefinanciación del ejecutor. Usa un Morpho y un adapter falsos; incluso si se compila y pasan las pruebas, **no certificará** ejecución contra Morpho real, gas patrocinado, beneficio capturable ni ganancia en mainnet.
- No se encontró Foundry ni compilador Solidity 0.8.24 en el entorno local utilizado. No se instalaron dependencias de pago, no se habilitó CI y no se realizaron llamadas de trading ni despliegue.

Pruebas efectivamente ejecutadas en el entorno disponible:

```sh
python3 -m unittest discover -v -s tests -p 'test_*.py'
# 34/34 PASS; validación de modelos y aritmética de dos recibos externos.
python3 bundle_gate.py fixtures/synthetic_two_transaction_bundle.json
# Sale con código 2 y estado BLOCKED deliberadamente (la entrada es sintética).
```

Para ejecutar pruebas adicionales si se dispone localmente de Foundry y solc 0.8.24:

```sh
forge test --root . --match-contract NqcMorphoSponsoredLiquidationMockTest -vv
```

**Siguiente barrera técnica:** un fork en `26,190,954` (prebloque del caso real, distinto de un prestate de orden exacto dentro del bloque), con `Morpho.sol` y pool DEX reales, además de un replay de recepción y ganancia efectiva del builder. Es indispensable demostrar disponibilidad temporal anterior al ganador. Si las dos transacciones requieren creación de otro adaptador, el modelo de dos transacciones también debe ampliarse para contabilizarla. Ningún archivo de esta rama emite una autorización de mainnet.