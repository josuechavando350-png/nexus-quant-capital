# Census del dinero · 2026-10-24

Ventana: **2 días** · cadenas: arbitrum · protocolos: Aave V3 y Morpho Blue.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$4,316** en 18 liquidaciones. Después de gas y pagos al builder les quedó **$4,314** (antes del costo de vender el colateral).
   **Lo que realmente se quedaron**, sumando todos los movimientos de tokens y ETH de cada transacción (venta del colateral, flash loan, pujas a subastas de oráculo, builder y gas): **$59**, el **2%** del bono (medido en 61% de las liquidaciones). Pagado en ETH a terceros (subastas y builders): $3,156.
2. **¿Quién se lo lleva?** 8 liquidadores distintos; los 3 mayores se llevan **98%** del bono.
3. **¿En cuántos bloques?** Mediana de **8 bloques** (2 s) desde la última actualización del oráculo; **0%** ocurren en el mismo bloque.

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Real | % quedó | A terceros | Ganadores | Top 3 | Bloques | Seg. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | aave | 15 | $4,316 | $59 | 2% | $3,156 | 6 | 98% | 8 | 2 |
| arbitrum | morpho | 3 | $0 | -$0 | -665% | $0 | 2 | 100% | 1 | 0 |

Real: lo que se quedaron los liquidadores en las transacciones con medición completa. Bloques y segundos: mediana desde la última actualización del oráculo involucrado.

## Saturación de mercados

Vírgenes: **0** · disputados: **2** · muertos: **0** · con muestra insuficiente (<3): 7.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| arbitrum | aave-v3-arbitrum WBTC→USDC | 5 | $232 | $53 | 65% | 3 | 54% | 8 | disputada |
| arbitrum | aave-v3-arbitrum ARB→USDC | 1 | $3,320 | $6 | 0% | 1 | 100% | 7 | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WBTC→USD₮0 | 1 | $79 | $1 | 1% | 1 | 100% | 8 | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WETH→USD₮0 | 2 | $341 | $0 | 0% | 1 | 100% | 8 | muestra_insuficiente |
| arbitrum | Morpho WETH/USD₮0 lltv 86.0% | 1 | $0 | $0 | — | 1 | 100% | 1 | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WETH→DAI | 1 | $0 | $0 | 25% | 1 | 100% | 8 | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WETH→WETH | 1 | $0 | $0 | — | 1 | 100% | 8 | muestra_insuficiente |
| arbitrum | Morpho PT-USDai-20NOV2025/USDC lltv 91.5% | 2 | $0 | -$0 | -665% | 1 | 100% | — | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WETH→USDC | 4 | $343 | -$1 | -0% | 2 | 96% | 8 | disputada |

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Ganadores |
|---|---:|---:|---:|---:|---:|
| $0–$10 | 7 | -$0 | -$0 | -1% | 5 |
| $10–$100 | 8 | $54 | $0 | 21% | 5 |
| $100–$1,000 | 2 | -$1 | -$1 | -0% | 1 |
| $1,000–$10.0 k | 1 | $6 | $6 | 0% | 1 |
| ≥ $10.0 k | 0 | — | — | — | — |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y se queda con mucho en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros |
|---|---|---:|---:|---:|---:|---:|
| arbitrum | `0x8ad1…86c1` | 12 | 5 | $4,190 | 0% | $3,156 |
| arbitrum | `0x5ac9…95bd` | 3 | 1 | $126 | 87% | $0 |
| arbitrum | `0x2384…f8a1` | 2 | 1 | $0 | -665% | $0 |
| arbitrum | `0x9355…5fdb` | 1 | 1 | $0 | — | $0 |

## Ganadores principales

- `0x3e7a65a9394e289dd23d9b393a8f8e02be62d288` — $3,341 (77%)
- `0xd12810b19b596347a3afac206d3ca65d08594b3f` — $754 (17%)
- `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` — $126 (3%)
- `0x92e1bce22f594657dc373b103559d32e2abc2b3e` — $79 (2%)
- `0xac27cbd94bfa3db2da4a94f4881572692f6adedd` — $15 (0%)
- `0x3f2097279b1c83f75ff55434418df4d74900a979` — $0 (0%)
- `0x9355ec6d797b6c8b73de9b52fffdb3bfa6d05fdb` — $0 (0%)
- `0x2384923d232eccecb03e329d919f3e1b6dbcf8a1` — $0 (0%)

## Cobertura de la medición

| Cadena | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Tiempo agotado |
|---|---:|---:|---:|---:|---|---|---|
| arbitrum | 18 | 18 | 11 | 16 | debug_traceTransaction: 11, no_medido: 6 | oráculo 4, mercado 46, sin 0 | no |

## Qué NO dice este census

- "Real" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir "Real" se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y el "Real" sale menor.
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); "Real" ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) y la recaptura de Chainlink SVR (Aave en Ethereum) se pagan por fuera y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
