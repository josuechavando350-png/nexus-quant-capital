# NQC065 — ZERO-CAPITAL ROUTE DECISION FOR THE NQC064 HISTORICAL MORPHO CASE

**Dictamen: TWO_DOCUMENTED_PRINCIPAL_FREE_HYPOTHESES / ECONOMICALLY_CONDITIONAL / ZERO_REALIZED_NQC_PROFIT.**

Esta investigación parte exactamente de NQC064 (commit `bd6f657bd69d1fb59656d185d95cdb5a13554694`), transacción histórica de otro searcher [Ethereum bloque 21762897](https://etherscan.io/tx/0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb), de febrero de 2025. No se ejecutó operación, no se usó RPC ni fondos. El objetivo es probar qué *condiciones* harían posible reemplazar los **266.862310264246861824 WETH** que el ejecutor original ya tenía disponibles para la primera venta.

## Hallazgo principal: dos alternativas al capital propio

**C1 — Colateral primero, sin flash loan.** El código oficial fijado de [Morpho Blue `Morpho.sol`](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol) demuestra la secuencia `liquidate`: Morpho transfiere el colateral al `msg.sender`, llama a `onMorphoLiquidate` si `data` no está vacío y después recoge los activos de deuda (`safeTransferFrom`). Esto permite *proponer* una reordenación de los tres intercambios visibles en NQC064:

1. Llamar a Morpho `liquidate` para recibir **94,718.231775052038007708 UNI** antes de adelantar USDC, si la elegibilidad/oráculo/mercado/bytes históricos lo permiten.
2. Dentro del callback, vender UNI por **281.407578800167103862 WETH** en Uniswap V3 **SI** se reprodujera la cotización histórica.
3. Cambiar **266.862310264246861824 WETH** por **616,687.327559 USDC** en Uniswap V2 **SI** esa transacción encuentra exactamente las mismas reservas efectivas y ruta.
4. Permitir que Morpho cobre **616,687.327558 USDC** al terminar el callback. Sobraría polvo de **0.000001 USDC**, sin convertirlo en ETH de forma imaginaria.
5. Con la diferencia **14.545268535920242038 WETH**, desembolsar el incentivo histórico vinculado a beaverbuild, **12.447536358167279703 ETH** mediante WETH unwrap y, bajo la consolidación de cuentas y gas histórico de NQC064, quedaría **1.915425887007584330 ETH equivalente** ANTES de nuevas obligaciones.

El **capital WETH inicial necesario sería cero** exclusivamente **si** un replay auténtico confirma esta reordenación. No lo confirma un cálculo de cantidades. La tx original hizo el intercambio WETH→USDC **antes** de Morpho; invertirlo puede cambiar lectura de oráculos, la validez de la liquidación, el estado de pools, gas, rutas de swap, llamadas/reentrancia y pagos; la comparación de dos pools diferentes no sustituye simulación EVM exacta. No se ha localizado el paquete histórico completo para verificarla. Tampoco elimina el anticipo ETH **inicial** de gas.

**C2 — Flash loan WETH a comisión 0 del protocolo Morpho Blue.** En el mismo [commit oficial fijado](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol), `flashLoan(token, assets, data)` transfiere los tokens al solicitante, ejecuta `onMorphoFlashLoan(assets,data)` y cobra exactamente **assets**, sin añadir prima. [La referencia de Morpho Blue](https://docs.morpho.org/developers/contracts/blue/) explica `flashFee=0` y que el máximo depende del balance real de Morpho.

Así, un préstamo de **266.862310264246861824 WETH** podría aportar el capital de la operación original, **solo si** Morpho tenía al menos ese saldo en el preestado histórico y el callback anidado liquidación/intercambios/repago supera un replay EVM. La comisión de protocolo teórica sería **0 WETH**, pero gas adicional, patrocinio, inclusión, riesgos y competencia siguen sin precio. No se autenticó liquidez histórica ni el estado de ese contrato. `flashFee=0` no significa ejecución gratuita.

Una opción Aave V3 `flashLoanSimple` sigue siendo alternativa, pero [la documentación oficial](https://www.aave.com/docs/aave-v3/guides/flash-loans) indica que su prima inicial fue **0.05% (5 bp)**, modificable por gobernanza, y `FLASHLOAN_PREMIUM_TOTAL` es la fuente dinámica. Aplicar 5 bp aquí es **solo una sensibilidad**, jamás afirmación de precio disponible en aquel bloque o actualmente. Esa prima ilustrativa sería **0.133431155132123430 WETH** con cálculo entero truncado y dejaría **1.781994731875460900 ETH equivalente** antes del aumento de gas, sponsor y demás costos.

## Lo que el margen realmente tolera

Partiendo del residuo de NQC064, el máximo deterioro **solo de la salida UNI→WETH**, si el resto de los importes y pagos se mantiene *exactamente* igual, es **68.065895 bp = 0.68065895%** de sus **281.407578800167103862 WETH** obtenidos. Con el cargo Aave ilustrativo de 5 bp sobre el principal, baja a **63.324333 bp = 0.63324333%**. A una caída del 1% en la venta del UNI, el residuo ya sería **negativo** antes de nuevas obligaciones.

Estas cotas NO modelan el efecto de la reordenación sobre los precios de los pools ni sobre las pujas de otros operadores. El precio histórico fue de otra época y el margen no es capturable hoy. El pago a `beaverbuild` podría no ser sustituible por remuneración a Titan al mismo importe; no atribuir builder = proposer automáticamente.

## Puertas para convertir hipótesis en pruebas

1. **Evidencia canónica histórica y preestado:** bloque padre 21762896, transacción anterior (txIndex=1), forks y transiciones, contrato ejecutor, implementación Morpho/oráculo, balances UNI/WETH/USDC, transacciones/pools V2/V3, recibo, traza. La transcripción Etherscan de NQC064 y su hash de blob Git NO autentican consenso.
2. **Replay EVM de C1:** realmente recibir UNI, ejecutar los swaps en orden opuesto, conseguir USDC suficiente y liquidar con callback. Medir gas extra y rutas, no extrapolar la cotización a partir de una sola swap observada.
3. **Alternativa flash:** si C1 fracasa, verificar saldo histórico WETH de Morpho y ejecutar flash anidado con el préstamo completo, aprobaciones, devolución y todas las obligaciones. Si el saldo fuese insuficiente, NO afirmar capital sin fondos.
4. **Patrocinio nativo inicial:** aprobación de Titan para **un bundle firmado específico** con EOA inicialmente sin ETH, prefijos gasLimit×maxFee, CREATE si hace falta, pago+devolución del sponsor, builder/proposer y no-recurso del propietario (actualmente UNKNOWN). [Titan patrocinio condicional](https://docs.titanbuilder.xyz/api/eth_sendbundle) no es una oferta a NQC.
5. **Captura presente:** una liquidación nueva disponible antes del bloque y observación Shadow de quién gana y quién pierde, con costos de fallos y P&L controlado por NQC. Un caso del año 2025 ya ejecutado no es capturable.

## Resultado y detención responsable

El código `capital_routes.py` calcula únicamente conservación por activo y sensibilidad de la misma operación histórica bajo supuestos **contrafactuales**; nunca ejecuta EVM. Se verificó que `case.json` conserva **exactamente** el blob Git NQC064 `49eb050d7429d5cdb3bc17ebd9ecf3e2485681bc`; el algoritmo rechaza nombres de activos, cantidades, unidades y financiación inventadas. **26 pruebas locales Python pasan**. Las regresiones históricas y verificador de aislamiento completos no se ejecutaron por no disponer del checkout integral, al igual que los replays. Los outputs están en `RESULTS.json` y la procedencia en `SOURCE_MANIFEST.json`.

Sin paquete EVM canónico autorizado, **detener** nuevas simulaciones equivalentes. No instalar infraestructura genérica para resolver la ausencia de evidencia. Ninguna llamada Triport (0 conocidas/8 vitalicias), RPC, transacción, firma, contacto, deploy o gasto fue autorizado ni efectuado.

**Decisión:** GO para adquisición **legítima y autorizada** del expediente histórico completo, UNKNOWN para C1/C2 reales y patrocinio, **NO-GO comercial**; `commercial_admission=false`; ganancia neta propia **no demostrada**. Próximo paso: conseguir datos preestado/orden/reservas de modo permitido para una prueba EVM de C1; si esa vía no se permite o no existe, esperar términos efectivos de Titan y suspender ejecución.
