# NQC061 — ZERO-SWAP MIDNIGHT, SPONSOR SOLVENCY TRUTH

**Resultado: hipótesis técnica más específica; NO hay oportunidad rentable autenticada.** Investigación estrictamente offline sobre Ethereum (chain id 1), descendiente de NQC060. La nueva ruta se limita a Morpho Midnight *loan-as-collateral* (mismo ERC-20 de préstamo y colateral) en una liquidación posterior al vencimiento. Es importante porque se elimina **el swap de colateral para pagar la deuda**, no los costos de gas, remuneración del patrocinador ni pujas. No se ha demostrado un market/borrower auténtico, balance liquidable o beneficio capturable.

## Hallazgos procedentes de código primario de Morpho

Fuente oficial **morpho-org/morpho-bots**, commit anclado `08d0a415d6d027f7e401fd6a904b09bedb441668`, leído el 2026-10-19. Los SHA Git de los blobs se incluyen en `SOURCE_REVIEW.json`.

1. [README del bot Midnight](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/midnight-liquidation/README.md): lista Ethereum 1 y Base 8453, documenta que los mercados *loan-as-collateral* usan oráculo de identidad y **no requieren un agregador de swaps** para esa posición. Pero el propio bot ya contempla esta oportunidad: **cero evidencia de exclusividad o baja competencia**. Selecciona mercados `listed=true` con una whitelist, lee estado onchain antes de actuar, y exige EOA financiada, privada/firmante y un Executor ya desplegado. Esa última configuración NO es una solución para NQC con cuenta sin fondos.
2. [encode-call.ts](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/midnight-liquidation/src/execution/encode-call.ts): en un slot sin intercambio, la cola de callback solo requiere aprobación del token de deuda. `Midnight.liquidate` envía primero colateral al Executor, efectúa callback y cobra el repago; luego se barren saldos hacia el EOA. No infiere beneficio, premio económico, ETH inicial ni CREATE patrocinado.
3. [profitability.ts](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/midnight-liquidation/src/runner/profitability.ts): la prueba `viable` comprueba salida cotizada contra repago + `MIN_SURPLUS_BPS` (por defecto cero). Eso es **cobertura de repago pre-gas**, no beneficio final del searcher tras ETH, sponsor e inclusión.
4. [ranking.ts](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/midnight-liquidation/src/runner/ranking.ts): el equipo dice haber medido en un contexto de desarrollo una mediana de costo de ruta de 17.6 bp para cbBTC→USDC frente a incentivos alrededor de 20 bp. Diferencia aritmética **2.4 bp antes de gas y otros cargos**. **No** es una operación particular ni un valor de mercado general: no aplicar a otro activo ni proyectar USD.
5. [Contrato Midnight](https://docs.morpho.org/developers/contracts/midnight/): permite liquidación post-maturity y callback, pero el acceso puede estar bloqueado por `liquidatorGate`; la elegibilidad y la cantidad real exigen estado/código de bloque verificables.

## Trampa decisiva para gas sin capital

La ausencia de swap NO significa que la EOA firme gratis. La ruta todavía requiere un anticipo de ETH que cubra el **máximo necesario por prefijo firmado**, incluso si el gas consumido al final es menor.

La estrategia más fácil de modelar para el financiamiento podría ser un mercado **WETH como préstamo y también como colateral**, porque un *unwrap* verificado de WETH→ETH podría cubrir obligaciones nativas al terminar. **Esto es una condición algebraica, no una existencia de mercado o ruta patrocinada demostrada.** Para USDC/USDC, aunque no haya swap de colateral a token de deuda, sigue siendo necesario financiar y liquidar las obligaciones de gas en ETH: no sumar USDC + ETH ni afirmar «sin swaps» del paquete integral.

NQC debe distinguir:

- **Solvencia del anticipo:** la oferta del sponsor cubre la reserva `gasLimit×maxFee` de *cada prefijo* y posibles CREATE/value. No basta que el gasto posterior sea pequeño.
- **Costo neto:** del ingreso se resta el gas **real consumido** y las remuneraciones separadas; **no** se descuenta otra vez la reserva máxima. Requiere un flujo de recuperación del anticipo verificable, no-recuso y asignación de pérdidas.
- **Capital principal:** una recepción de colateral seguida del callback puede evitar adelantar la deuda cuando los activos realmente alcanzan; hay que autenticar el token, el saldo y la matemática del contrato.
- **Competencia:** Morpho ya ofrece bot sobre esta misma ruta; falta evidencia de pujas, éxito e inclusión, y no se presume margen para NQC.

El patrocinio de [Titan eth_sendBundle](https://docs.titanbuilder.xyz/api/eth_sendbundle) es condicional; no existe prueba de que patrocine un paquete concreto de NQC con la configuración Midnight, cubra CREATE o acepte un reemplazo de EOA sin fondos sin recurso personal. Tampoco se envió ningún bundle.

## Implementación NQC061

`zero_swap_gate.py` recibe descriptores (solo offline) de market/borrower con dirección exacta de activo, estado/gate, timestamp canónico, deuda, montos acotados e identidad de participantes. Todas las cantidades son **enteros base-unit en formato decimal**, jamás floats. Reglas:

1. Solo Ethereum 1, mismo contrato ERC-20 de préstamo y colateral, vencer estrictamente antes del bloque, deuda positiva, gate abierto o permiso probado, estado canónico documentado.
2. Comprobar cota superior `seized_max - repay_min - fee_min - bid_token_min` en un mismo ERC-20. Si es no positiva, rechazar solo el escenario. Una positiva no es P&L ni probabilidad.
3. Para un préstamo WETH con *unwrap* **explícitamente demostrado**, descontar gas **real**, remuneración sponsor y puja nativa, en wei, cuando todas las cotas estén disponibles y los buckets sean disjuntos. Jamás sumar ETH a USDC. Si no hay conversión demostrada, estado UNKNOWN.
4. Comprobar el límite de anticipo nativo contra la reserva máxima firmada **por separado**, no volver a restar la reserva como gasto final. Si no existe sponsor confirmado o se desconoce el límite, es UNKNOWN aunque el margen hipotético sea positivo.
5. `commercial_admission=false`, financier_committed=false, captura propia y responsabilidad personal desconocidas en todas las salidas. No admitir por fixtures.

**25 pruebas nuevas aprobadas localmente** (Python estándar; ver `validation.log`) y seis expedientes estrictamente **SINTÉTICOS** con resultados en `RESULTS.json`. Una fixture positiva solo demuestra que la fórmula puede producir un margen condicionado; no documenta mercado, liquidez, patrocinio ni profit. No se ejecutó verificador integral PFT/Census ni suites anteriores porque el checkout remoto original no estuvo disponible localmente; tampoco replay, RPC, wallets, firmas ni trading.

## Fuentes ausentes — no repetir el bloqueo

NQC060 ya intentó leer una lista pública Midnight y el lector la reportó inaccesible; NQC061 **no reintentó esa URL ni acudió a proveedores alternos**. Tampoco adquirió recibos, trazas o estado onchain en tiempo real. Hasta tener un paquete histórico legalmente permitido (direcciones, market, maturity, borrower, transferencia efectiva, repago, gas, remuneraciones y patrocinio), la selección de una operación disponible sigue **UNKNOWN**.

**Prioridad falsable:** encontrar un expediente publicado y permitido de **un solo caso Ethereum Midnight loan-as-collateral**, idealmente WETH/WETH, y comprobar si posee deuda posterior al vencimiento, acceso abierto, incentivo > obligaciones y ejecución del colateral-primero. Si no existe esa evidencia, suspender construcción adicional y concentrarse en la negociación documental del patrocinio con Titan.

**Conclusión:** GO para una investigación documental adicional y estrecha; UNKNOWN para beneficio y sponsor; NO-GO para ejecución financiera. Meta mensual USD 5k–45k NO ESTIMABLE. `main` protegido y repos previos permanecen intactos.
