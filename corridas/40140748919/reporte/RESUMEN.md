# Census del dinero · 2026-10-24

Ventana: **21/30 días** · cadenas: ethereum, base, arbitrum · protocolos: Aave V3 y Morpho Blue.

> **Cobertura incompleta:** base (7/10 tramos). Ver la sección de cobertura.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$539.3 k** en 948 liquidaciones.
2. **¿Quién se lo lleva?** 192 liquidadores distintos; los 3 mayores se llevan **66%** del bono.
3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **8 bloques** (4 s) desde la última actualización del oráculo; **12%** en el mismo bloque.
4. **¿Qué porcentaje dejó al builder?** Ethereum: **77%** del bono (propina + pago directo al coinbase, que incluye las pujas de Chainlink SVR). En L2 no hay builder; la propina de prioridad fue: arbitrum 0%, base 2%.
5. **¿Cuánto se queda realmente el ganador?** En las 814 liquidaciones rastreables (86% del total): bono $461.0 k, el ganador se quedó **$2.47 M (536%)** (de eso $2.52 M lo mandó a su tesorería); a subastas de oráculo/OEV $5.87 M (1274%), al builder en directo $236.7 k, en propina $2,295, gas base $371, resto (deslizamiento, comisiones) -$8.12 M. Fuera de la cuenta: sin medir 85 liq. ($48.8 k), sin rastro 2 ($155), refinanciaciones 47 ($29.4 k).

## ¿A dónde se va el bono?

Solo liquidaciones rastreables (todos los movimientos de tokens y ETH valuados). Cada contraparte que solo recibe se clasifica: builder del bloque, subasta compartida (OEV: la usan 2 o más liquidadores o es una subasta conocida) o tesorería del mismo bot (cuenta como del ganador). Lo que va a contrapartes que devuelven algo (swaps, préstamos) queda en Resto: deslizamiento y comisiones. "Sin rastro": ni el ganador ni un sumidero se quedaron con el bono. "Refinanciación": el colateral volvió al protocolo en la misma tx (no es dinero que se mueva).

| Cadena | Protocolo | Rastreables | Bono | Ganador | % | (tesorería) | OEV | Builder directo | Propina | Gas base | Resto | Sin medir · sin rastro · refin. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| arbitrum | aave | 239/242 | $27.3 k | $131.4 k | 482% | $130.4 k | $183.7 k | $0 | $13 | $10 | -$287.8 k | 3 ($0) · 0 ($0) · 0 ($0) |
| arbitrum | morpho | 30/46 | $73 | $743 | 1016% | $669 | $0 | $0 | $0 | $0 | -$671 | 16 ($2) · 0 ($0) · 0 ($0) |
| base | aave | 56/59 | $543 | -$3 | -1% | $0 | $11.7 k | $0 | $14 | $1 | -$11.2 k | 3 ($0) · 0 ($0) · 0 ($0) |
| base | morpho | 220/277 | $23.3 k | $3,280 | 14% | $306 | $16.6 k | $0 | $848 | $1 | $2,613 | 9 ($203) · 1 ($25) · 47 ($29.4 k) |
| ethereum | aave | 158/159 | $393.2 k | $2.21 M | 561% | $2.26 M | $5.66 M | $221.0 k | $1,182 | $280 | -$7.69 M | 1 ($0) · 0 ($0) · 0 ($0) |
| ethereum | morpho | 111/165 | $16.6 k | $130.7 k | 788% | $130.4 k | $3,562 | $15.6 k | $238 | $79 | -$133.6 k | 53 ($48.6 k) · 1 ($130) · 0 ($0) |

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| arbitrum | aave | 242 | $27.3 k | 32 | 88% | 9 · 104 · 533 | 27 | 0% | n/a |
| arbitrum | morpho | 46 | $75 | 16 | 83% | 687 · 919 · 8,649 | 235 | 6% | n/a |
| base | aave | 59 | $543 | 19 | 88% | 16 · 172 · 1,049 | 344 | 0% | n/a |
| base | morpho | 277 | $53.0 k | 56 | 87% | 1 · 1 · 2 | 2 | 3% | n/a |
| ethereum | aave | 159 | $393.2 k | 41 | 84% | 0 · 1 · 111 | 12 | 42% | 85% |
| ethereum | morpho | 165 | $65.3 k | 52 | 88% | 0 · 11 · 1,286 | 132 | 33% | 25% |

## Subasta vs. directa

"Subasta": lo pagado a terceros en ETH más la propina es ≥ 30% del bono (subasta de oráculo, builder o guerra de prioridad). "Directa": el ganador no pagó por el orden. "Sin medir": faltaron trazas o precios.

| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | directa | 166 | $88 | $873 | 996% | -$0 | 29 | 282 |
| arbitrum | sin_medir | 19 | $2 | — | — | — | 5 | 928 |
| arbitrum | subasta | 103 | $27.3 k | $131.2 k | 482% | $2 | 22 | 9 |
| base | directa | 161 | $6,199 | $3,293 | 53% | $0 | 52 | 5 |
| base | refinanciacion | 47 | $29.4 k | — | — | — | 3 | 2 |
| base | sin_medir | 12 | $203 | — | — | — | 10 | 192 |
| base | sin_rastro | 1 | $25 | — | — | — | 1 | — |
| base | subasta | 115 | $17.6 k | -$17 | -0% | $0 | 18 | 1 |
| ethereum | directa | 96 | $54.0 k | $1.92 M | 3563% | $0 | 35 | 145 |
| ethereum | sin_medir | 54 | $48.6 k | — | — | — | 10 | 106 |
| ethereum | sin_rastro | 1 | $130 | — | — | — | 1 | — |
| ethereum | subasta | 173 | $355.8 k | $412.5 k | 116% | $0 | 53 | 1 |

## ¿Queda margen para un actor pequeño?

Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.

| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |
|---|---:|---|---:|---|---|---:|---:|---:|
| arbitrum | 30.0 | 166 / 269 / 288 | $873 | 6 · $850 · 52% | 2 · $694 · 84% | 29 | 282 | 95% |
| base | 21.0 | 161 / 276 / 336 | $3,293 | 16 · $3,194 · 95% | 4 · $2,880 · 100% | 52 | 5 | 59% |
| ethereum | 30.0 | 96 / 269 / 324 | $1.92 M | 13 · $1.92 M · 99% | 5 · $1.92 M · 99% | 35 | 145 | 81% |

"top": parte del neto que se llevó el mayor ganador de ese grupo. "≥ 2 bloques": liquidaciones que llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).

### Bots que ganan por fuera de subastas

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ethereum | `0xf6860780cd7b673a37cfc2716efd3742e09aedde` | 1 | 1 | $53.6 k | $1.92 M | 3584% | $1.92 M | 0 | 1 | aave-v3-core sUSDe→USDtb (1) |
| base | `0x759915f8e7b07a5c0a3a3a7ee52ee3643feea0d3` | 1 | 3 | $5,784 | $2,669 | 46% | $312 | 1 | 2 | Morpho cbZEC/USDC lltv 62.5% (3) |
| ethereum | `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | 1 | 5 | $22 | $591 | 2642% | $4 | 164 | 4 | Morpho PT-sUSDat-27AUG2026/USDC lltv 91.5% (1); Morpho sUSDS/USDT lltv 94.5% (1); Morpho srRoyUSDC/USDC lltv 91.5% (1) |
| arbitrum | `0xd12810b19b596347a3afac206d3ca65d08594b3f` | 1 | 1 | $23 | $584 | 2493% | $584 | 0 | 1 | Morpho WETH/USDC lltv 86.0% (1) |
| base | `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | 1 | 8 | $25 | $228 | 916% | $0 | 1,232 | 5 | Morpho stEUR/jEUR lltv 94.5% (2); Morpho stkWELL/USDC lltv 62.5% (2); aave-v3-base WETH→GHO (2) |
| ethereum | `0xe7cd2fa44cce16e70867338f7b9fd60ad3b9d4b5` | 1 | 1 | $193 | $173 | 89% | $173 | — | 1 | Morpho STONE/WETH lltv 94.5% (1) |
| ethereum | `0x950fd558f47e234a2fde23b7d61f7ccdbcb4a86f` | 2 | 2 | $7 | $134 | 1851% | $67 | 0 | 2 | Morpho wsrUSD/USDT lltv 94.5% (1); Morpho weETH/USDC lltv 86.0% (1) |
| arbitrum | `0x76c5e81b7727eed71db2ab8767c86631e91dea0e` | 1 | 1 | $4 | $110 | 2495% | $110 | 1 | 1 | Morpho WETH/USDC lltv 86.0% (1) |
| ethereum | `0x41e8e31ee3f52c3b9f5a971c0c7be27950b9732e` | 1 | 1 | $109 | $103 | 95% | $103 | — | 1 | Morpho ONDO/USDC lltv 62.5% (1) |
| base | `0x08aa4e537685976fd60e5dac44662ef5aa9314bf` | 1 | 5 | $125 | $86 | 69% | $18 | 1 | 1 | Morpho cbXRP/USDC lltv 62.5% (5) |
| ethereum | `0x00acd5005200e7009beb000000e35e1e002b5565` | 1 | 25 | $7 | $79 | 1083% | $0 | 222 | 12 | Morpho USD0USD0++/USDC lltv 86.0% (5); Morpho beraSTONE/WETH lltv 91.5% (4); Morpho WETH/USDC lltv 86.0% (2) |
| base | `0x121445f4b770e30f2b497b57fc10d4fca201a61b` | 1 | 2 | $13 | $72 | 539% | $36 | 1 | 1 | Morpho cbZEC/USDC lltv 62.5% (2) |
| arbitrum | `0x0dc76a8cdc8194e2ed4810e729cea63d4b864104` | 1 | 1 | $2 | $69 | 4547% | $69 | 1,106 | 1 | aave-v3-arbitrum WETH→wstETH (1) |
| ethereum | `0x15d741be449a179a82d30d66fb262262e6d72ec0` | 1 | 1 | $3 | $61 | 2397% | $61 | — | 1 | Morpho SPYx/AUSD lltv 86.0% (1) |
| base | `0xcee740502c9e84118e4a13efc085dff70784863d` | 1 | 1 | $69 | $61 | 89% | $61 | 1 | 1 | Morpho cbZEC/USDC lltv 62.5% (1) |
| arbitrum | `0x48daab9f7ed6e3184c26d9ddaccc356d52d6237f` | 1 | 1 | $1 | $54 | 4569% | $54 | 120 | 1 | aave-v3-arbitrum WETH→LUSD (1) |
| base | `0x5f7839483dd404a45c6d5d8ba462617228638c68` | 1 | 16 | $56 | $44 | 79% | $2 | 1 | 1 | Morpho cbXRP/USDC lltv 62.5% (16) |
| base | `0xf851cf19a7f8acd384c71cf2717a232c63b31cdd` | 1 | 1 | $44 | $34 | 78% | $34 | 1 | 1 | Morpho cbZEC/USDC lltv 62.5% (1) |
| arbitrum | `0xa7a840e20821abc8b147a3919b07337fda39ce89` | 1 | 2 | $33 | $34 | 101% | $17 | 25,324 | 2 | Morpho GLV [WETH-USDC]/USDC lltv 77.0% (1); Morpho GLV [WBTC-USDC]/USDC lltv 77.0% (1) |
| ethereum | `0x1f2f10d1c40777ae1da742455c65828ff36df387` | 1 | 4 | $3 | $31 | 1135% | $6 | 4,379 | 2 | Morpho beraSTONE/WETH lltv 91.5% (2); aave-v3-core PT-sUSDE-27NOV2025→USDT (1); Morpho sUSDe/DAI lltv 91.5% (1) |

### Contratos que pagan por el orden (subastas)

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ethereum | `0xbde3…5c64` | 4 | 4 | $166.4 k | $151.6 k | 91% | $2.79 M | 2,551 |
| ethereum | `0x6f28…5443` | 1 | 1 | $5,092 | $121.3 k | 2381% | $4,970 | — |
| arbitrum | `0x3e7a…d288` | 2 | 3 | $3,791 | $102.5 k | 2703% | $49.5 k | 8 |
| ethereum | `0xa000…c777` | 1 | 1 | $2,769 | $61.7 k | 2229% | $64.1 k | 0 |
| ethereum | `0x7e9c…11af` | 2 | 2 | $2,790 | $60.3 k | 2161% | $61.5 k | 0 |
| ethereum | `0xd128…4b3f` | 9 | 27 | $11.1 k | $49.6 k | 446% | $216.2 k | 0 |
| arbitrum | `0xd128…4b3f` | 7 | 16 | $1,477 | $26.5 k | 1795% | $31.0 k | 8 |
| ethereum | `0x1f2f…f387` | 1 | 6 | $1,154 | $10.0 k | 870% | $21.2 k | 71 |
| ethereum | `0x9813…58b7` | 1 | 1 | $167 | $6,587 | 3933% | $147 | — |
| ethereum | `0x2945…284f` | 10 | 19 | $2,598 | $3,833 | 148% | $59.9 k | 1 |
| ethereum | `0xa8b7…47fc` | 1 | 1 | $128 | $3,223 | 2515% | $2,848 | 1 |
| ethereum | `0x98a2…22ef` | 1 | 1 | $50 | $1,206 | 2390% | $47 | 0 |

### ¿A quién va el ETH que sale del liquidador?

"compartido": cobra de 2 o más liquidadores (subasta, builder). "un_solo_liquidador": puede ser la tesorería del mismo bot; si lo es, ese pago es ganancia y no OEV.

| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |
|---|---|---|---:|---:|---:|---|
| ethereum | `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97` | builder | $282.7 k | 122 | 44 | no |
| ethereum | `0x000000000004444c5dc75cb358380d2e3de08a90` | compartido | $249.4 k | 11 | 9 | no |
| base | `0x1c6ec84518b859ae6a96c7dd0c78048be7def976` | compartido | $43.8 k | 150 | 12 | no |
| ethereum | `0xdadb0d80178819f2319190d340ce9a924f783711` | builder | $35.5 k | 44 | 26 | no |
| ethereum | `0xd87f3d6c5624e8b02be13c2c92f8511b88b94d96` | builder | $26.1 k | 2 | 2 | no |
| arbitrum | `0xab6deeaf17d69f091e6fe8e9f472a69c7112ce45` | compartido | $25.5 k | 56 | 12 | no |
| ethereum | `0x6adb3bab5730852eb53987ea89d8e8f16393c200` | builder | $5,003 | 2 | 2 | no |
| ethereum | `0x396343362be2a4da1ce0c1c210945346fb82aa49` | builder | $469 | 8 | 8 | no |
| ethereum | `0x97dec872013f6b5fb443861090ad931542878126` | un_solo_liquidador | $110 | 1 | 1 | no |
| ethereum | `0x2aae699ed04bbbd068f67a5b3c813ebb35f2c9e8` | un_solo_liquidador | $100 | 1 | 1 | no |
| arbitrum | `0x35c43aff60e94a64799782574f179d4865e9b377` | un_solo_liquidador | $35 | 1 | 1 | no |
| arbitrum | `0xde632c3a214d5f14c1d8ddf0b92f8bcd188fee45` | un_solo_liquidador | $26 | 1 | 1 | no |
| arbitrum | `0xe40a526a79b704a1de69907905ae6f60966a966e` | un_solo_liquidador | $11 | 1 | 1 | no |
| ethereum | `0xfb74767c1ce1aada0a0e114441173b57f8c1571b` | builder | $10 | 2 | 2 | no |
| arbitrum | `0x360e68faccca8ca495c1b759fd9eee466db9fb32` | un_solo_liquidador | $7 | 1 | 1 | no |

## Saturación de mercados

Vírgenes: **3** · disputados: **49** · muertos: **14** · con muestra insuficiente (<3): 162.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ethereum | aave-v3-core sUSDe→USDtb | 1 | $53.6 k | $1.92 M | 3584% | 1 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | aave-v3-core weETH→USDT | 1 | $166.3 k | $151.6 k | 91% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | Morpho USDe/DAI lltv 86.0% | 1 | $5,092 | $121.3 k | 2381% | 0 | 1 | 100% | — | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum ARB→USDC | 6 | $3,127 | $72.8 k | 2329% | 2 | 5 | 100% | 8 | disputada |
| ethereum | aave-v3-core WETH→USDC | 28 | $19.9 k | $61.8 k | 311% | 1 | 10 | 41% | 1 | muerta |
| ethereum | aave-v3-lido WETH→USDC | 1 | $2,769 | $61.7 k | 2229% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | Morpho sNUSD/USDC lltv 91.5% | 42 | $48.0 k | $0 | — | 0 | 2 | 100% | — | disputada |
| arbitrum | aave-v3-arbitrum USDC→WETH | 3 | $654 | $29.1 k | 4457% | 2 | 3 | 100% | 183 | disputada |
| ethereum | aave-v3-core AAVE→USDT | 5 | $2,429 | $27.3 k | 1125% | 1 | 5 | 66% | 0 | muerta |
| ethereum | aave-v3-core WETH→USDT | 33 | $29.6 k | $15.3 k | 52% | 3 | 14 | 71% | 0 | muerta |
| ethereum | aave-v3-core LINK→USDC | 5 | $970 | $14.4 k | 1488% | 0 | 3 | 61% | 0 | disputada |
| arbitrum | aave-v3-arbitrum WETH→USDC | 69 | $2,285 | $12.6 k | 552% | 38 | 14 | 44% | 18 | muerta |
| arbitrum | aave-v3-arbitrum WETH→USD₮0 | 7 | $857 | $12.3 k | 1436% | 0 | 3 | 88% | 9 | disputada |
| ethereum | Morpho PT-cUSD-29JAN2026/USDC lltv 91.5% | 2 | $209 | $6,595 | 3160% | 0 | 2 | 80% | — | muestra_insuficiente |
| ethereum | aave-v3-core WETH→USDG | 1 | $86 | $3,805 | 4440% | 0 | 1 | 100% | 1 | muestra_insuficiente |

### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)

- ethereum · aave-v3-core WETH→USDe: 3 liq., real $13, ganador 0xc4dd…ca1e
- base · aave-v3-base USDbC→USDC: 3 liq., real -$0, ganador 0xf80b…c47f
- arbitrum · Morpho thBILL/USDC lltv 94.5%: 9 liq., real -$0, ganador 0x4716…e252

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |
|---|---:|---:|---:|---:|---:|---:|
| $0–$10 | 626 | $2,572 | $0 | 428% | 402 | 141 |
| $10–$100 | 166 | $24.0 k | $0 | 422% | 13 | 52 |
| $100–$1,000 | 106 | $82.6 k | $1 | 293% | 4 | 40 |
| $1,000–$10.0 k | 37 | $346.3 k | $5 | 525% | 1 | 16 |
| ≥ $10.0 k | 9 | $2.02 M | $305 | 559% | 1 | 7 |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |
|---|---|---:|---:|---:|---:|---:|---:|
| base | `0x583d…9b77` | 150 | 9 | $46.8 k | -0% | $43.8 k | 82% |
| arbitrum | `0x8ad1…86c1` | 64 | 9 | $26.6 k | 490% | $25.5 k | 98% |
| arbitrum | `0x58ea…2073` | 44 | 1 | $0 | — | $0 | 0% |
| arbitrum | `0x24c1…d006` | 37 | 1 | $0 | — | $0 | 0% |
| arbitrum | `0x6c24…8f5e` | 36 | 7 | $41 | 100% | $0 | 0% |
| ethereum | `0xe683…31ba` | 35 | 1 | $48.0 k | — | $0 | 0% |
| ethereum | `0x00ac…5565` | 32 | 1 | $15 | 1063% | $0 | 19% |
| ethereum | `0xd128…4b3f` | 27 | 9 | $11.1 k | 446% | $12.4 k | 100% |
| arbitrum | `0x5ac9…95bd` | 25 | 2 | $117 | 99% | $0 | 12% |
| ethereum | `0xbbbb…ffcb` | 22 | 9 | $655 | 86% | $0 | 0% |
| base | `0xa7cb…c837` | 19 | 1 | $0 | — | $0 | 0% |
| ethereum | `0x2945…284f` | 19 | 10 | $2,598 | 148% | $2,475 | 100% |
| arbitrum | `0x48da…237f` | 18 | 1 | $28 | 379% | $33 | 94% |
| base | `0x5f78…8c68` | 16 | 1 | $56 | 79% | $0 | 0% |
| base | `0x405f…d8d3` | 15 | 1 | $0 | — | $0 | 0% |

## Ganadores principales (por bono)

- `0xbde3e91f09a9489f1b53eaa21eb32c89b2fd5c64` — $166.4 k (31%)
- `0xf6860780cd7b673a37cfc2716efd3742e09aedde` — $139.3 k (26%)
- `0xe683b8ee2710eabcbf347b7cb0735cda11ef31ba` — $48.0 k (9%)
- `0x875a5cf56ebce1c6fb84d24495728e6d6f39a0be` — $23.5 k (4%)
- `0x3ae5122d62e78dc14b98d8d30aca4faf9d1f1bba` — $21.0 k (4%)
- `0xd12810b19b596347a3afac206d3ca65d08594b3f` — $20.8 k (4%)
- `0x63f74441bf49b1dd716b93d30e74cc8a621459e9` — $20.8 k (4%)
- `0x754bedb7d53876b07fe55c4a021b4a21de4bacd5` — $17.5 k (3%)
- `0x8b61f5925f4515edb0b7b76c38036aaf9a818472` — $16.7 k (3%)
- `0xeef1b06e23a39f05b6b34ff1052d7a6ca3a00005` — $14.7 k (3%)

## Cobertura de la medición

| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| ethereum | 3/3 | 30.0 | 324 | 324 | 270 (83%) | 208 (64%) | debug_traceTransaction: 300 | oráculo 770, mercado 13, sin 0 | 0 |
| base | 7/10 | 21.0 | 336 | 334 | 324 (96%) | 289 (86%) | no_medido: 6, debug_traceTransaction: 184, trace_transaction: 3 | oráculo 611, mercado 16, sin 2 | 0 |
| arbitrum | 3/3 | 30.0 | 288 | 288 | 269 (93%) | 273 (95%) | debug_traceTransaction: 265 | oráculo 795, mercado 0, sin 0 | 0 |

Liquidaciones cuya tx pagó por el orden más de 1.5× su bono (probable liquidación de otro protocolo o arbitraje en la misma tx; el pago completo cuenta como OEV/builder): ethereum: 110, base: 6, arbitrum: 74.

Netos fuera de rango (no se cuentan como medidos; revisar a mano): ethereum `0x97113645e8aae912a8cc6ea3f476b4349ec3298473683d819f55013b52444e90` bono $180, neto $1,070 (ynETHx +2.70133, msETH -2.88781); ethereum `0x8037223f3d4290e91e63e5a9c97ecc238201ec2df8307d59a62b96716dc179b8` bono $118, neto $734 (ynETHx +1.77939, msETH -1.90242); ethereum `0xdc687eefd6408705860dae9522647643bcb3c324e390c0abebdf19eafd127355` bono $100, neto $857 (ETH +0.318399); ethereum `0x4bd6a34c6bc48a8d0e41cc1bf003feb1ed82c861da254eda053259ed0d8d191d` bono $94, neto $557 (ynETHx +1.40615, msETH -1.50322); ethereum `0xbc783801c22ef7604dd637b99bdcfc3dc12dd97fc3c0e286a495ee67792c3f1e` bono $61, neto $370 (ynETHx +0.92113, msETH -0.984718); ethereum `0x87f0e8242f3e52a0acaf05a4fee22b3cf6af88a8eed8ec648cc37605951027df` bono $3, neto -$128 (sNUSD +123.626, USDC -128.231); arbitrum `0xb5eefa72cfbcb01ca2e4a860677f7e92968d6f40bf15ff8fd65a23276969d50a` bono $1, neto -$47 (PT-USDai-18JUN2026 +48.6253, USDC -47.3854); ethereum `0x96d31552654be3ba9bbc9205dd48c64b6d8e2db71b25bf189908934ec3d7d40f` bono $1, neto -$46 (sNUSD +44.1223, USDC -45.7657).

Errores de trazas más comunes: base: debug_traceTransaction: HTTP 429 en base.drpc.org (57); base: debug_traceTransaction: HTTP 408 en base.drpc.org (27); base: trace_transaction: HTTP 429 en base.drpc.org (10); base: trace_transaction: HTTP 408 en base.drpc.org (3).

## Qué NO dice este census

- "Se queda" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y sale menor (y la liquidación puede clasificarse como "subasta").
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) se pagan por fuera de la transacción y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- No reconcilia todas las posiciones del alcance (puerta "cobertura del mercado" de Omega): solo mide las liquidaciones que sí ocurrieron.
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
