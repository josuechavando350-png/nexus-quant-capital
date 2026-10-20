# RLUSD/FXRP — evaluación comercial: dos rutas de venta y primera página de deudores (19-oct-2026)

**Dictamen: ninguna captura rentable demostrada para NQC. Ruta directa FXRP→RLUSD identificada, pero sin cotización ejecutable.**

## 1. La venta histórica no acredita quién recibió el dinero

La [interfaz oficial Morpho](https://app.morpho.org/ethereum/variable/0x4fa31e3f8ba345227d44e1cf48559eea53a90dd5311dc006984c060f2f311d96/rlusd-fxrp) muestra la liquidación del **15 de octubre de 2026, 02:28:59**, con **1,717.97 RLUSD** repagados y **1,432.43 FXRP** incautados, liquidador abreviado `0xBdE3...5c64` y transacción abreviada `0x4df1...ecca`.

El [historial FXRP/USDT de WhatToFarm](https://whattofarm.io/de/pairs/ethereum-uniswapv-fxrp-usdt-created-2026-02-17) registraba un *sell* en el mismo instante de **1,432.43 FXRP** por aproximadamente **1,815.70 USDT**, con hash abreviado `0x4d...ecca` y maker `0x473...13E1`. Es una **correlación entre dos páginas indexadas**, no verificación criptográfica del recibo ni trazado de todos los destinatarios. El liquidador y el maker aparecen con identidades abreviadas diferentes; pueden ser contratos intermediarios, pero no debe asumirse que tengan un mismo beneficiario.

El diferencial **USDT−RLUSD = 97.73** es SOLO una resta hipotética si 1 USDT equivale efectivamente a 1 RLUSD. Falta saber dónde quedaron los USDT y cómo se financió el repago de RLUSD en el orden EVM real. No tenemos gas, puja, prima, sponsor, saldo final ni titularidad. **El titular económico y beneficio neto son UNKNOWN.**

## 2. Encontramos otra salida: directo de FXRP a RLUSD

[DeFiLlama lista](https://investors.defillama.com/yields/pool/bb78714b-5da3-5298-8009-da2451208e67) una piscina Uniswap V3 **FXRP/RLUSD de comisión 0.30% y TVL reportado alrededor de US$3.05m** en un snapshot indexado. Su enlace a [Uniswap](https://app.uniswap.org/positions/create/v3?chain=mainnet&currencyA=0x8292bb45bf1ee4d140127049757c2e0ff06317ed&currencyB=0xce6170ea245dc8d1f275a710a062b70f125f0110&fee=%7B%22feeAmount%22%3A3000%7D) fija Ethereum, RLUSD y FXRP en ese nivel de comisión. [Ripple](https://docs.ripple.com/products/stablecoin/developer-resources/rlusd-on-ethereum) identifica el token proxy RLUSD Ethereum `0x8292Bb45bf1Ee4d140127049757C2E0fF06317eD`.

Un indexador público enlaza el pool a `0x42271fca1fa435b176d46a5544b2698a1e261782`; el destino dio **403** en el primer intento, no se reintentó. La dirección no fue autenticada por runtime/código. Fuentes de indexación discrepan en métricas de liquidez; no asumir que una cifra de TVL sea *liquidez activa en el rango*.

En la liquidación de 1,432.43 FXRP, el límite aritmético es **1.199339583784 RLUSD/FXRP de salida efectiva** para cubrir solamente 1,717.97 RLUSD de deuda. Si solo se simula descontar una comisión de 0.30%, el precio antes de esa comisión debería superar **1.202948429071 RLUSD/FXRP**, sin aún contar impacto de precio y obligaciones adicionales. Son **umbrales**, no cotizaciones.

La UI de Morpho muestra una referencia de oráculo de **1 FXRP = 1.29 RLUSD** al consultar el mercado, pero **no es el precio de una venta ejecutable** para 1,432.43 FXRP ni el precio histórico de la liquidación. Hay que verificar estado de ticks, liquidez activa, cantidad exacta de RLUSD recibida y salida simultánea en el callback; tampoco hay patrocinio Titan confirmado.

## 3. ¿Existe una posición liquidable hoy?

La primera página de la [UI de posiciones de Morpho](https://app.morpho.org/ethereum/variable/0x4fa31e3f8ba345227d44e1cf48559eea53a90dd5311dc006984c060f2f311d96/rlusd-fxrp) muestra diez prestatarios, con health factors reportados desde **1.209 hasta 2.091**. Ninguno de **esos diez** tiene HF ≤ 1. La menor cifra visible corresponde a `0x7864...7Ac2` con deuda aproximada **151,880.61 RLUSD**, y HF **1.209**. La UI dice **página 1 de 6**: por tanto, otras posiciones **no están cubiertas** y NO afirmamos que el mercado entero esté sano. Esto es un snapshot indexado, NO un cálculo canónico ni una oportunidad previa a la decisión.

La misma tabla de liquidaciones del mercado identifica diversos liquidadores históricos (al menos `0xBdE3...`, `0xbD32...` y `0x950f...`). **No tenemos base para sostener competencia baja**.

## 4. Decisión de negocio

- **GO documental:** existe una ruta de colateral potencialmente directa al token de deuda, por examinar antes que una ruta con conversión USDT→RLUSD.
- **HOLD comercial:** ninguna venta FXRP→RLUSD exacta de 1,432.43 FXRP se ha cotizado, ninguna oportunidad actual demostrada ni patrocinio Titan aceptado.
- **NO-GO ejecución:** cero capital, cero gas, cero wallets, cero firmas, cero transacciones, cero contactos externos.
- **STOP:** no mejorar el bot hasta ver output ejecutable RLUSD neto de swap, gas/pujas y estado de liquidez respaldado con fuente permitida.

Este estudio actualiza exclusivamente una **auditoría comercial existente**; no abre una nueva versión NQC, no modifica código ni altera `main`. Originales PFT/Census, verificadores y regresiones no ejecutados. Solo se hicieron controles de identidad/consistencia de datos declarativos; ninguna prueba EVM ni cotización real.

**Próximo movimiento:** verificar una salida FXRP→RLUSD de tamaño exacto en el instante de la oportunidad y, de haber resultado favorable, costear financiación y competencia; en caso contrario descartar este mercado y estudiar el siguiente por evidencia comercial, no generar más tecnología.
