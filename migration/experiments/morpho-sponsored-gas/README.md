> **Estado vigente — 2026-10-17 UTC:** 136 pruebas Python y 41 pruebas Solidity
> aprobadas localmente (132/39 fue el punto de control anterior), más 9 pruebas
> de aislamiento. Consulte [RESEARCH_STATUS.md](RESEARCH_STATUS.md),
> [REPRODUCE.md](REPRODUCE.md) y [RESEARCH_FINDINGS.md](RESEARCH_FINDINGS.md).
> Las secciones anteriores por fecha se conservan como historial: sus menciones
> de Solidity pendiente no describen la verificación actual. El fork histórico,
> el patrocinio y la viabilidad con $0 continúan pendientes.

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

## Reconciliación histórica añadida — 2026-10-16

Se incorporó \`historical_receipt_gate.py\` y \`tests/test_historical_receipt_gate.py\`, un nuevo control exclusivamente de lectura. El caso fijado corresponde a la liquidación ajena de Morpho del 2026-10-14 (bloque \`26190955\`, transacción \`0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b\`).

- Comprueba identidad de transacción/bloque/contrato, fecha, gas y reconciliación de transferencias ERC-20.
- Gas observado: \`745509 * 266148625 = 198416195275125 wei\`.
- Diferencia de flujo observada de WETH: \`26409680973611000000 - 26039738525656992415 - 368092735714237547 = 1849712239770038\` unidades mínimas. **NO** se identifica como ganancia de NQC ni como saldo neto final del liquidador.
- El recibo del liquidador es de **un tercero**. No demuestra renta del builder, patrocinio de gas, prestate disponible a NQC, ruta DEX repetible ni carrera de inclusión.
- Estado de salida deliberado: \`RECEIPT_RECONCILED_INCOMPLETE_NO_PROFIT_AUTHORITY\`, \`certified=false\`, \`live_executable=false\` y \`profit_estimate=null\`; termina con código 2 (bloqueado).
- Diez regresiones nuevas fuerzan rechazo de hashes, costos o flujos modificados. Resultado en este entorno: **44/44 pruebas Python aprobadas**. Esto no implica certificación de Solidity ni fork.

\`\`\`sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 historical_receipt_gate.py observations/ethereum_morpho_2026-10-14_complex_winner.json
# La segunda instrucción devuelve exit 2 adrede; no eleva una transacción ajena a autoridad.
\`\`\`

### Bloqueo siguiente, sin alterarlo artificialmente

1. Compilar y ejecutar Foundry 0.8.24 sin cambiar fuente histórica certificada (toolchain no instalada en el entorno de esta sesión).
2. Obtener un RPC de archivo o una prueba independiente de prestate anterior al ganador, y ejecutar el contrato contra **Morpho Blue auténtico**.
3. Medir una conversión de collateral a token de deuda en el estado anterior; las transferencias observadas de un ganador NO son una cotización para NQC.
4. Verificar por separado el **saldo del builder**, no solo \`block.coinbase\`. Las páginas de Titan y Quasar documentan patrocinio condicional, pero no prueban patrocinio de la transacción de despliegue de este experimento ni aceptación de nuestro bundle.
5. Solo después: evaluar orden de llegada y captura, sin afirmar P&L histórico de NQC.

Sin firmas, fondos, despliegues, mutaciones de \`main\` o workflows activos.


## Revisión del patrocinio separado (octubre 2026)

**Problema corregido en el prototipo experimental:** mandar ETH a \`block.coinbase\` puede remunerar al proponente/validador del bloque; por sí solo **no** reembolsa al builder que financia la transacción. El contrato ahora distingue \`sponsorRefundRecipient\`/\`sponsorRefundWei\` de \`coinbaseTipWei\`. Rechaza beneficiarios que sean el propio operador o \`block.coinbase\`, y exige que la conversión efectiva a WETH cubra ambos pagos, además del repago del préstamo y el beneficio mínimo.

**El dato clave sigue sin demostrarse:** no tenemos una dirección verificada por Titan o Quasar que acepte reembolsos, ni un recibo firmado o una ejecución privada que demuestre que su motor cuenta ese pago como ingreso del patrocinador. El cambio solo evita mezclar dos partidas contables diferentes. No debe usarse una dirección arbitraria o tomada de una suposición.

El filtro conservador \`bundle_gate.py\` incluye ahora además:

- \`sponsor_refund_recipient\` y \`sponsor_refund_wei\`: reembolso **candidato**, aún sujeto a verificación independiente de identidad y recepción.
- \`sponsor_topup_gas_limit\` y \`sponsor_topup_max_fee_per_gas_wei\`: costo máximo modelado de la **transacción adicional** con que el builder financiaría la EOA. Es independiente de DEPLOY y EXECUTE.
- Se rechaza si reembolso directo o valor medido del builder es inferior al adelanto, el gas del top-up y el margen mínimo exigido.
- El tip a \`block.coinbase\` nunca se añade al saldo del builder como ganancia demostrada.
- Una muestra autodeclarada \`HISTORICAL_BUNDLE_TRACE\` puede, como máximo, obtener \`MODEL_SCREEN_PASS_ONLY\`; jamás emite autorización de producción. Los booleanos del JSON no son prueba criptográfica.

**Pruebas:** el espejo local de trabajo ejecutó 51 pruebas Python, todas aprobadas, con \`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q -s tests -p 'test_*.py'\`. La rama GitHub contiene 51 métodos de prueba equivalentes, pero no se ejecutó un runner oficial sobre el commit remoto. Foundry / solc 0.8.24 no están instalados en este entorno; las pruebas Solidity añadidas siguen **sin compilar y sin ejecutar**.

**Condiciones abiertas e innegociables:** demostrar (1) despliegue y ejecución financiados por un builder real dentro del mismo bundle, (2) aceptación de su dirección de reembolso, (3) estado auténtico anterior a una liquidación Morpho, (4) liquidez y ruta de conversión ejecutables a ese estado, (5) rentabilidad neta y posibilidad temporal de captura. Esta rama es exclusivamente investigación; sin firmas, gasto, despliegues ni activación de workflows.


## Verificación histórica del mercado Morpho mediante EIP-1898

Nuevo control de solo lectura: `historical_prestate_probe.py` y `tests/test_historical_prestate_probe.py`. Derivan y verifican el ID del mercado involucrado en la liquidación externa del **26 de junio de 2026**:

- ID calculado con **KECCAK-256** (no SHA3 de NIST), sobre cinco campos ABI de Morpho Blue: `0x582fdc4176da0ab5c65e086603ab9ecd9188e889e16efef6e35854cf14e15065`.
- Identidad del bloque padre: `25402185`, hash `0x976caf9ddb8d59e24460f7aabe760d96e2dc96f56b3ff0d89d6c1d7359dce670`.
- Preparan tres `eth_call` no mutantes: `idToMarketParams`, `market` y `position`, todos anclados mediante **EIP-1898 blockHash y requireCanonical=true**.
- Fallan si cambia la configuración del mercado, un hash, una respuesta ABI, un saldo o el resultado no corresponde a la misma petición.
- El caso original tiene **índice de transacción 226 en su bloque**. El estado padre **no es el estado anterior exacto a esa transacción**; incluso tres respuestas válidas no certifican que NQC hubiera podido liquidar, que existiera una ruta DEX rentable o que el builder financiara gas.
- Sin RPC de archivo explícitamente configurado, el resultado es `BLOCKED_NO_ARCHIVE_RPC` (código 2). No se recurre a `latest`, claves pagadas ni endpoints no autorizados.

Para verificar el trabajo localmente con el equipo disponible:

```bash
cd migration/experiments/morpho-sponsored-gas
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q -s tests -p 'test_*.py'
python3 historical_prestate_probe.py
# El segundo comando termina con código 2 si no hay acceso archivístico.
# Opcional y de SOLO LECTURA, si ya se dispone de RPC histórico:
NQC_ARCHIVE_RPC_URL='https://<RPC_ARCHIVE_EXISTENTE>' python3 historical_prestate_probe.py
```

**Resultado verificable de esta sesión:** **67/67 pruebas Python aprobadas en el espejo local**, incluyendo 16 pruebas nuevas de identidad del mercado, ABI y anclaje contra el bloque padre. La igualdad exacta de blobs de los tres archivos nuevos se verificó por SHA Git en el repositorio remoto. Esto **no significa** que haya pruebas Foundry superadas ni acceso a estados históricos reales: el compilador `forge`/`solc` y el RPC archivístico no estaban disponibles.

El mock Solidity ahora separa la liquidez ficticia de una entidad externa de prueba y comprueba que el operador empiece con `0 ETH` y `0 WETH`. **Tampoco constituye un reemplazo de una cotización o ruta DEX real.** Continúa sin compilar ni ejecutarse.

**Siguiente decisión técnica:** disponer de Foundry/solc verificados y una fuente de archivo que permita reconstruir el estado anterior exacto a una transacción Morpho, luego realizar la liquidación con adaptador DEX real y contabilizar los pagos del builder por separado. Sin ello, NQC permanece sin autorización de producción y con P&L `NO_DEMOSTRADO`.

## Morpho post-accrual exact math (research-only)

New files: morpho_liquidation_math.py and tests/test_morpho_liquidation_math.py.

Source semantics checked against the official Morpho Blue repository, pinned to commit 9cf6d5b844625ba108e36d1cf911f5d2faf7c136:
- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol
- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/SharesMathLib.sol
- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/MathLib.sol
- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/ConstantsLib.sol

The read-only Python model computes virtual shares/assets (10^6 / 1), Solidity-compatible integer roundings, healthy/unhealthy status, liquidation incentive (maximum 1.15 WAD), exact repaid shares/assets and seized collateral using the 10^36 oracle price scale, and uint256 overflows. It requires authenticated POST-INTEREST-ACCRUAL values at decision time. It does not accrue interest, obtain oracle quotes or DEX swap prices, certify the path in a real fork, estimate capture probability or prove any profit.

One SYNTHETIC example returns 300 repaid assets and 638 seized collateral units. These numbers are invented unit-test fixtures, NOT a real liquidation. Tests explicitly prevent healthy positions, excess repayment, over-seizure, arithmetic overflow and invalid numeric types from passing. Local total after adding twelve math regressions: 79/79 Python tests PASS. No remote CI run was executed for this commit.

The parent-block probe still fails closed without an authenticated archive RPC; the actual state prior to the historical winner must be reproduced. Compiled Solidity, fork parity, builder acceptance and realized NQC P&L remain UNKNOWN / NOT CERTIFIED.



## Protección contra bloqueos por donaciones no solicitadas

**Revisión de seguridad experimental:** la versión anterior de \`NqcMorphoSponsoredLiquidation.sol\` exigía que los balances del ejecutor fuesen exactamente cero antes de entrar. Cualquier persona puede transferirle tokens ERC-20 sin permiso, y el ETH puede llegar incluso por vías que no ejecutan el método \`receive\`. Un saldo mínimo ajeno podía inutilizar indefinidamente ese ejecutor.

La rama experimental ahora toma una instantánea de los cuatro saldos iniciales (token de deuda, colateral, WETH y ETH) y exige conservarlos **exactamente iguales al finalizar** la operación. Durante Morpho \`onMorphoLiquidate\`, solo se vende el colateral recibido después de la instantánea; al reembolsar gas y pagar ganancias solo se utiliza el incremento neto posterior. La condición de $0 de capital propietario se interpreta como **cero activos propios gastados**: un token enviado por un tercero no es capital utilizable ni un beneficio del operador.

Se añadieron pruebas Solidity \`testUnsolicitedTokensAndForcedEthArePreserved\`, \`testDonationsCannotFakeMinimumSwapOutput\`, \`testForcedEthCannotSubsidizeBuilderRefund\` y \`testDonationsCannotSubsidizeMissingProfit\`. Son **pruebas fuente, aún sin compilar ni ejecutar** por ausencia de Foundry y Solidity 0.8.24. Ningún resultado de estas pruebas debe anunciarse como aprobado.

**Math engine:** el módulo separado \`morpho_liquidation_math.py\` y sus doce regresiones calculan, con aritmética entera y entradas post-acumulación, valores teóricos de una liquidación Morpho. No sustituyen un estado auténtico de cadena ni una ejecución reproducida en fork.

**Estado local al verificar el conjunto:** 79 pruebas Python aprobadas (tipadas, históricas y sintéticas). 0 pruebas Solidity ejecutadas; 0 forks históricos completos ejecutados; 0 bundles patrocinados aceptados y 0 ganancias certificadas. Las pruebas Python no elevan ningún permiso de producción. No se habilita CI, se preserva \`main\`, no se usan fondos ni transacciones reales.

## Bundler3 no-deployment research update

See NO_DEPLOY_BUNDLER3_DESIGN.md. Source snapshot for the legacy deployed
Bundler3 adapter path is pinned to morpho-org/bundler3 commit
b4014349e3527f44ceaab697b26e29f2b11457f3. Official Morpho docs say
Bundler3 was deprecated in favor of Bundles in September 2026; it remains
deployed, but a new liquidation workflow should NOT assume it is supported.

Official Ethereum deployment addresses used only for source research:
- Bundler3: 0x6566194141eefa99Af43Bb5Aa71460Ca2Dc90245
- EthereumGeneralAdapter1: 0x4A6c312ec70E8747a587EE860a0353cd42Be0aE0
- ParaswapAdapter: 0x03b5259Bd204BfD4A616E5B79b0B786d90c6C38f

The adapter exposes onMorphoFlashLoan, but does NOT expose onMorphoLiquidate.
A candidate no-deployment route therefore uses Morpho flashLoan -> the
GeneralAdapter's callback -> Bundler3.reenter -> direct Morpho.liquidate with
EMPTY data (collateral to Bundler3, repayment pulled from Bundler3). This is
a proposed call graph, not an executed route or safe/approved integration.

New research-only ABI encoder: bundler3_abi.py. It deterministically creates
the nested Call[] ABI layout, the hash checked during reentrance, and
no-callback Morpho liquidation calldata. It deliberately rejects skipRevert
and invalid encoded arguments. It DOES NOT construct a complete profitable
route, send a bundle, deploy a contract or provide a builder sponsorship
agreement. Independent Solidity parity, actual DEX route, allowance cleanup,
flash repayment and builder payout verification are still mandatory.

Local tests after the ABI and exact-math additions: 91/91 Python tests passed.
These are local unit tests only. No Solidity compilation, real fork,
canonical prestate, builder acceptance or NQC profit is certified.

A potential advantage of a verified no-deployment path is a **single**
externally sponsored transaction rather than two (deploy + execute), but the
actual gas savings, safety and economics have NOT been measured.
