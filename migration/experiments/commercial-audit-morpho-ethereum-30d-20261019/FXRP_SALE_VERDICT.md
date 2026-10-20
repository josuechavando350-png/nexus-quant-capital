# VENTA REAL DE FXRP CORRELACIONADA — 15 OCT 2026
**Decisión comercial: la salida del colateral es observable; el beneficio neto sigue SIN DEMOSTRAR.**

[Morpho (https://app.morpho.org/ethereum/variable/0x4fa31e3f8ba345227d44e1cf48559eea53a90dd5311dc006984c060f2f311d96/rlusd-fxrp)] reporta una liquidación Ethereum (1) el 2026-10-15 a las 02:28:59: **1,717.97 RLUSD** repagados, **1,432.43 FXRP** incautados, liquidador `0xBdE3...5c64`, transacción `0x4df1...ecca`.

[WhatToFarm (https://whattofarm.io/de/pairs/ethereum-uniswapv-fxrp-usdt-created-2026-02-17)] registra el mismo instante y volumen de FXRP, prefijo/sufijo de hash compatibles `0x4d...ecca`, y **venta del FXRP por ~1,815.70 USDT** en Uniswap V3 (pool `0x539bAc0745de77f8bFF38326eEcB8c36553e6C58`). El `maker` aparece `0x473...13E1` y **NO coincide visiblemente** con el liquidador de Morpho. Esto es una **correlación histórica por dos indexadores**, no autenticación del recibo canónico íntegro ni prueba del beneficiario.

**Corrección monetaria:** Morpho mostraba una diferencia de valoración de **US$138.67** que NO es un precio de venta ejecutado. El flujo de venta fue en **USDT**, mientras la deuda se repagó en **RLUSD**, así que el valor simple **97.73** es SOLO una diferencia hipotética a tipo USDT:RLUSD 1:1, ANTES de gas, puja, financiación y otras obligaciones. Cobertura = `1815.70 * tasa_real_RLUSD/USDT >= 1717.97 + costes_restantes_RLUSD`. Tasa de equilibrio sin otros costos ~**0.94617503 RLUSD/USDT**. Si se gastaran otros 100 RLUSD equivalentes a 1:1, el modelo termina **−2.27 RLUSD equivalentes**.

La comisión de AMM de la venta real ya está incluida en el importe USDT reportado y NO debe restarse otra vez. Falta el recibo íntegro para conocer si esa venta pagó realmente la deuda, si hubo USDT→RLUSD, flash loan, gas, coinbase/tip privado, patrocinio, fallos y titularidad.

**Rutas adicionales documentadas, aún no cotizadas:** [Uniswap V3 RLUSD/FXRP](https://investors.defillama.com/yields/pool/bb78714b-5da3-5298-8009-da2451208e67) 0.30% y TVL ~$3.05M; [Curve Ethereum](https://www.curve.finance/dex/ethereum/pools?sortBy=rewardsBase) lista RLUSD/USDC y DAI/USDC/USDT. TVL no equivale a profundidad utilizable al tamaño ni prueba el camino de la transacción.

**GO documental:** FXRP tiene una salida históricamente observada en el mismo expediente. **UNKNOWN económico:** no tenemos ingreso neto de ningún operador auditado, ni ruta sin principal demostrada, ni sponsor Titan confirmado. **NO-GO comercial:** NQC no ejecutó esta operación ni puede capturar ahora una transacción pasada. No construir más bot. Próximo dato decisivo = traza completa, adjudicación de flujos y obligaciones por una fuente permitida; si no está disponible, priorizar oportunidades prospectivas.

Protecciones: `commercial_admission=false`, sin nueva RPC, gasto, firmas, contactos ni alteraciones de `main`. Validación aritmética Decimal de 21 afirmaciones; no EVM replay ni verificador original.
