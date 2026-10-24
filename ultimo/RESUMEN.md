# Census del dinero · 2026-10-24

Ventana: **30 días** · cadenas: ethereum, base, arbitrum · protocolos: Aave V3 y Morpho Blue.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$1.37 M** en 3,529 liquidaciones.
2. **¿Quién se lo lleva?** 287 liquidadores distintos; los 3 mayores se llevan **39%** del bono.
3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **1 bloques** (2 s) desde la última actualización del oráculo; **17%** en el mismo bloque.
4. **¿Qué porcentaje dejó al builder?** Ethereum: **77%** del bono (propina + pago directo al coinbase, que incluye las pujas de Chainlink SVR). En L2 no hay builder; la propina de prioridad fue: arbitrum 0%, base 1%.
5. **¿Cuánto se queda realmente el ganador?** En las 3,066 liquidaciones rastreables (87% del total): bono $898.9 k, el ganador se quedó **$81.9 k (9%)** (de eso $28.5 k lo mandó a su tesorería); a subastas de oráculo/OEV $353.0 k (39%), al builder en directo $349.8 k, en propina $6,057, gas base $438, resto (deslizamiento, comisiones) $107.7 k. Fuera de la cuenta: sin medir 238 liq. ($71.7 k), sin rastro 56 ($19.8 k), refinanciaciones 169 ($380.9 k).

## ¿A dónde se va el bono?

Solo liquidaciones rastreables (todos los movimientos de tokens y ETH valuados). Cada contraparte que solo recibe se clasifica: builder del bloque, subasta compartida (OEV: la usan 2 o más liquidadores o es una subasta conocida) o tesorería del mismo bot (cuenta como del ganador). Lo que va a contrapartes que devuelven algo (swaps, préstamos) queda en Resto: deslizamiento y comisiones. "Sin rastro": ni el ganador ni un sumidero se quedaron con el bono. "Refinanciación": el colateral volvió al protocolo en la misma tx (no es dinero que se mueva).

| Cadena | Protocolo | Rastreables | Bono | Ganador | % | (tesorería) | OEV | Builder directo | Propina | Gas base | Resto | Sin medir · sin rastro · refin. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| arbitrum | aave | 235/242 | $27.0 k | $937 | 3% | $4 | $25.5 k | $0 | $13 | $10 | $529 | 3 ($0) · 4 ($303) · 0 ($0) |
| arbitrum | morpho | 30/46 | $73 | $74 | 101% | $0 | $0 | $0 | $0 | $0 | -$2 | 16 ($2) · 0 ($0) · 0 ($0) |
| base | aave | 192/194 | $17.6 k | $191 | 1% | $0 | $17.4 k | $0 | $31 | $4 | -$23 | 2 ($0) · 0 ($0) · 0 ($0) |
| base | morpho | 2339/2723 | $444.3 k | $69.3 k | 16% | $28.3 k | $310.1 k | $0 | $4,593 | $65 | $60.2 k | 163 ($23.1 k) · 52 ($19.5 k) · 169 ($380.9 k) |
| ethereum | aave | 158/159 | $393.2 k | $11.0 k | 3% | $97 | $1 | $334.0 k | $1,182 | $280 | $46.8 k | 1 ($0) · 0 ($0) · 0 ($0) |
| ethereum | morpho | 112/165 | $16.7 k | $417 | 2% | $107 | $0 | $15.8 k | $238 | $79 | $185 | 53 ($48.6 k) · 0 ($0) · 0 ($0) |

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| arbitrum | aave | 242 | $27.3 k | 32 | 88% | 9 · 104 · 533 | 27 | 0% | n/a |
| arbitrum | morpho | 46 | $75 | 16 | 83% | 687 · 919 · 8,649 | 235 | 6% | n/a |
| base | aave | 194 | $17.6 k | 33 | 91% | 1 · 46 · 366 | 91 | 0% | n/a |
| base | morpho | 2,723 | $867.8 k | 144 | 53% | 1 · 1 · 2 | 2 | 18% | n/a |
| ethereum | aave | 159 | $393.2 k | 41 | 84% | 0 · 1 · 111 | 12 | 42% | 85% |
| ethereum | morpho | 165 | $65.3 k | 52 | 88% | 0 · 11 · 1,286 | 132 | 33% | 25% |

## Subasta vs. directa

"Subasta": lo pagado a terceros en ETH más la propina es ≥ 30% del bono (subasta de oráculo, builder o guerra de prioridad). "Directa": el ganador no pagó por el orden. "Sin medir": faltaron trazas o precios.

| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | directa | 217 | $803 | $739 | 92% | -$0 | 33 | 163 |
| arbitrum | sin_medir | 19 | $2 | — | — | — | 5 | 928 |
| arbitrum | sin_rastro | 4 | $303 | — | — | — | 2 | 9 |
| arbitrum | subasta | 48 | $26.2 k | $272 | 1% | $0 | 13 | 8 |
| base | directa | 1520 | $99.6 k | $67.5 k | 68% | $1 | 141 | 1 |
| base | refinanciacion | 169 | $380.9 k | — | — | — | 10 | 1 |
| base | sin_medir | 165 | $23.1 k | — | — | — | 31 | 1 |
| base | sin_rastro | 52 | $19.5 k | — | — | — | 8 | 2 |
| base | subasta | 1011 | $362.3 k | $2,025 | 1% | $0 | 44 | 1 |
| ethereum | directa | 131 | $3,942 | $3,542 | 90% | $0 | 43 | 106 |
| ethereum | sin_medir | 54 | $48.6 k | — | — | — | 10 | 106 |
| ethereum | subasta | 139 | $406.0 k | $7,835 | 2% | $0 | 48 | 0 |

## ¿Queda margen para un actor pequeño?

Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.

| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |
|---|---:|---|---:|---|---|---:|---:|---:|
| arbitrum | 30.0 | 217 / 265 / 288 | $739 | 7 · $698 · 67% | 1 · $477 · 100% | 33 | 163 | 95% |
| base | 30.0 | 1520 / 2531 / 2917 | $67.5 k | 343 · $66.0 k · 30% | 90 · $56.9 k · 34% | 141 | 1 | 43% |
| ethereum | 30.0 | 131 / 270 / 324 | $3,542 | 8 · $3,573 · 67% | 6 · $3,536 · 67% | 43 | 106 | 79% |

"top": parte del neto que se llevó el mayor ganador de ese grupo. "≥ 2 bloques": liquidaciones que llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).

### Bots que ganan por fuera de subastas

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | `0xac5c4ccfc12b2b85c091d12e78d675e888ce10c4` | 24 | 70 | $29.2 k | $17.3 k | 59% | $42 | 1 | 2 | Morpho cbXRP/USDC lltv 62.5% (46); Morpho SOL/USDC lltv 62.5% (13); Morpho WETH/USDC lltv 86.0% (10) |
| base | `0xa00003b2e58e808bcb536041045a5d0f7750c777` | 1 | 1 | $11.2 k | $9,660 | 87% | $9,660 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0x97c4e986d7c270f4951cc09e6de0bc66d4778c24` | 2 | 60 | $8,851 | $8,551 | 97% | $63 | 2 | 2 | Morpho WETH/USDC lltv 86.0% (30); Morpho cbXRP/USDC lltv 62.5% (26); Morpho cbETH/USDC lltv 77.0% (3) |
| base | `0x759915f8e7b07a5c0a3a3a7ee52ee3643feea0d3` | 3 | 10 | $13.1 k | $8,549 | 65% | $319 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (5); Morpho cbZEC/USDC lltv 62.5% (3); Morpho WETH/USDC lltv 86.0% (2) |
| base | `0xcb8d367fbfcef1a652bd9322523d03be1169f800` | 4 | 4 | $6,490 | $5,383 | 83% | $1,220 | 1 | 1 | Morpho cbXRP/USDC lltv 62.5% (4) |
| base | `0xc4bfb65f09174569eac5d849fec32431d0d0fc51` | 32 | 136 | $7,802 | $3,333 | 43% | $15 | 1 | 2 | Morpho cbXRP/USDC lltv 62.5% (119); Morpho WETH/USDC lltv 86.0% (17) |
| ethereum | `0x7e9cca6d42a076e02b063a7e4d8249452b7211af` | 1 | 1 | $2,597 | $2,562 | 99% | $2,562 | 0 | 1 | aave-v3-core WETH→USDC (1) |
| base | `0xa1018068bb72f2b9f309267ed48767b8ac19be93` | 1 | 1 | $2,281 | $2,147 | 94% | $2,147 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0xaa9e48dadf4ae8472b67f1da0326623266c17443` | 21 | 24 | $3,139 | $2,026 | 65% | $3 | 2 | 2 | Morpho cbXRP/USDC lltv 62.5% (19); Morpho WETH/USDC lltv 86.0% (3); Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0x5feae2565fdc0034ca64461c32d95c9e8eb95652` | 2 | 2 | $1,342 | $1,311 | 98% | $655 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (2) |
| base | `0x5ef5ffc16baacc0f97ec5e5284ef9b1487264170` | 1 | 6 | $1,153 | $1,132 | 98% | $188 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (6) |
| base | `0x35302b7ab4346aec5a91234d492b0033b3004bb6` | 1 | 12 | $1,269 | $1,110 | 87% | $55 | 0 | 2 | Morpho cbETH/USDC lltv 77.0% (12) |
| base | `0xcee740502c9e84118e4a13efc085dff70784863d` | 31 | 39 | $5,059 | $1,010 | 20% | $16 | 2 | 2 | Morpho cbXRP/USDC lltv 62.5% (38); Morpho cbZEC/USDC lltv 62.5% (1) |
| base | `0x9a039ccdb7cfa560e004419f3aa7a552e040e88c` | 8 | 85 | $1,578 | $825 | 52% | $3 | 1 | 3 | Morpho cbXRP/USDC lltv 62.5% (44); Morpho WETH/USDC lltv 86.0% (37); Morpho SOL/USDC lltv 62.5% (3) |
| base | `0x1af6740124b83e9ab5fe7df812a108d9a6b1c2d4` | 1 | 5 | $920 | $753 | 82% | $181 | 1 | 1 | Morpho cbXRP/USDC lltv 62.5% (5) |
| base | `0xe1f760baef51d0736482e5ddfab7fe3c4444a47b` | 2 | 4 | $665 | $638 | 96% | $141 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (4) |
| ethereum | `0x875a5cf56ebce1c6fb84d24495728e6d6f39a0be` | 1 | 2 | $856 | $576 | 67% | $288 | 0 | 1 | aave-v3-core WETH→USDC (2) |
| base | `0x7a08760fa8897a6574bbbe7511217d2a06664d44` | 4 | 20 | $547 | $546 | 100% | $1 | 0 | 5 | Morpho cbETH/USDC lltv 77.0% (13); Morpho cbXRP/USDC lltv 62.5% (6); Morpho cbLTC/USDC lltv 62.5% (1) |
| base | `0xe9674a87681bda6f5eaceabe61c01537e4283137` | 1 | 47 | $557 | $504 | 91% | $2 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (43); Morpho cbXRP/USDC lltv 62.5% (2); Morpho AERO/USDC lltv 62.5% (1) |
| arbitrum | `0x9355ec6d797b6c8b73de9b52fffdb3bfa6d05fdb` | 2 | 4 | $465 | $477 | 103% | $0 | 60 | 3 | aave-v3-arbitrum ARB→USD₮0 (1); aave-v3-arbitrum USDC→USDC (1); aave-v3-arbitrum WETH→WETH (1) |

### Contratos que pagan por el orden (subastas)

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ethereum | `0xf686…edde` | 1 | 2 | $139.3 k | $6,611 | 5% | $103.9 k | 0 |
| base | `0xd128…4b3f` | 10 | 165 | $43.7 k | $1,503 | 3% | $39.6 k | 1 |
| ethereum | `0x875a…a0be` | 1 | 6 | $22.6 k | $432 | 2% | $19.8 k | 0 |
| ethereum | `0xbde3…5c64` | 4 | 4 | $166.4 k | $304 | 0% | $150.6 k | 2,551 |
| base | `0x2ea8…907f` | 4 | 8 | $20.6 k | $211 | 1% | $16.1 k | 2 |
| arbitrum | `0x754b…acd5` | 1 | 1 | $17.5 k | $201 | 1% | $17.3 k | 9 |
| base | `0x40fe…3d88` | 1 | 3 | $361 | $195 | 54% | $157 | 1 |
| ethereum | `0x854a…57ab` | 1 | 3 | $693 | $153 | 22% | $679 | 1 |
| ethereum | `0xb82a…97d4` | 1 | 1 | $972 | $117 | 12% | $860 | 1 |
| ethereum | `0xa000…c777` | 1 | 1 | $2,769 | $89 | 3% | $2,598 | 0 |
| ethereum | `0x63f7…59e9` | 1 | 4 | $20.8 k | $87 | 0% | $19.2 k | 709 |
| ethereum | `0x6f28…5443` | 1 | 1 | $5,092 | $80 | 2% | $4,970 | — |

### ¿A quién va el ETH que sale del liquidador?

"compartido": cobra de 2 o más liquidadores (subasta, builder). "un_solo_liquidador": puede ser la tesorería del mismo bot; si lo es, ese pago es ganancia y no OEV.

| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |
|---|---|---|---:|---:|---:|---|
| base | `0x1c6ec84518b859ae6a96c7dd0c78048be7def976` | compartido | $441.7 k | 1196 | 29 | no |
| ethereum | `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97` | builder | $282.7 k | 122 | 44 | no |
| ethereum | `0x000000000004444c5dc75cb358380d2e3de08a90` | compartido | $249.4 k | 11 | 9 | no |
| ethereum | `0xdadb0d80178819f2319190d340ce9a924f783711` | builder | $35.5 k | 44 | 26 | no |
| ethereum | `0xd87f3d6c5624e8b02be13c2c92f8511b88b94d96` | builder | $26.1 k | 2 | 2 | no |
| arbitrum | `0xab6deeaf17d69f091e6fe8e9f472a69c7112ce45` | compartido | $25.5 k | 56 | 12 | no |
| ethereum | `0x6adb3bab5730852eb53987ea89d8e8f16393c200` | builder | $5,003 | 2 | 2 | no |
| base | `0x498581ff718922c3f8e6a244956af099b2652b2b` | compartido | $1,330 | 4 | 3 | no |
| ethereum | `0x396343362be2a4da1ce0c1c210945346fb82aa49` | builder | $469 | 8 | 8 | no |
| ethereum | `0x97dec872013f6b5fb443861090ad931542878126` | un_solo_liquidador | $110 | 1 | 1 | no |
| ethereum | `0x2aae699ed04bbbd068f67a5b3c813ebb35f2c9e8` | un_solo_liquidador | $100 | 1 | 1 | no |
| arbitrum | `0x35c43aff60e94a64799782574f179d4865e9b377` | un_solo_liquidador | $35 | 1 | 1 | no |
| arbitrum | `0xde632c3a214d5f14c1d8ddf0b92f8bcd188fee45` | un_solo_liquidador | $26 | 1 | 1 | no |
| base | `0x9af4392e4f4575d3155fec6efb34e878b04384c4` | un_solo_liquidador | $12 | 16 | 1 | no |
| arbitrum | `0xe40a526a79b704a1de69907905ae6f60966a966e` | un_solo_liquidador | $11 | 1 | 1 | no |

## Saturación de mercados

Vírgenes: **2** · disputados: **64** · muertos: **15** · con muestra insuficiente (<3): 179.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | Morpho RSS/USDC lltv 77.0% | 2 | $222.7 k | $0 | — | 0 | 2 | 100% | — | muestra_insuficiente |
| ethereum | Morpho sNUSD/USDC lltv 91.5% | 42 | $48.0 k | $0 | — | 0 | 2 | 100% | — | disputada |
| base | Morpho cbXRP/USDC lltv 62.5% | 778 | $325.3 k | $36.0 k | 16% | 450 | 51 | 19% | 2 | disputada |
| base | Morpho cbETH/USDC lltv 77.0% | 471 | $32.5 k | $26.0 k | 87% | 392 | 46 | 34% | 0 | disputada |
| ethereum | aave-v3-core wstETH→USDC | 10 | $86.3 k | $4,939 | 6% | 3 | 9 | 99% | 1 | muerta |
| base | Morpho WETH/USDC lltv 86.0% | 538 | $92.8 k | $3,355 | 4% | 257 | 34 | 64% | 1 | disputada |
| ethereum | aave-v3-core WETH→USDC | 28 | $19.9 k | $3,140 | 16% | 8 | 10 | 41% | 1 | muerta |
| base | Morpho cbZEC/USDC lltv 62.5% | 61 | $11.8 k | $2,879 | 32% | 19 | 17 | 49% | 1 | disputada |
| ethereum | aave-v3-core sUSDe→USDtb | 1 | $53.6 k | $1,660 | 3% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | aave-v3-core WETH→USDT | 33 | $29.6 k | $629 | 2% | 8 | 14 | 71% | 0 | muerta |
| arbitrum | aave-v3-arbitrum ARB→USD₮0 | 1 | $465 | $477 | 103% | 1 | 1 | 100% | 4 | muestra_insuficiente |
| ethereum | aave-v3-core weETH→USDT | 1 | $166.3 k | $296 | 0% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| base | Morpho JitoSOL/USDC lltv 62.5% | 217 | $20.0 k | $208 | 2% | 58 | 22 | 33% | — | disputada |
| arbitrum | aave-v3-arbitrum WBTC→WBTC | 2 | $17.5 k | $201 | 1% | 1 | 2 | 100% | 146 | muestra_insuficiente |
| base | Morpho yoUSD/USDC lltv 91.5% | 3 | $200 | $194 | 97% | 1 | 3 | 95% | — | disputada |

### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)

- ethereum · aave-v3-core WETH→USDe: 3 liq., real $0, ganador 0xc4dd…ca1e
- arbitrum · Morpho thBILL/USDC lltv 94.5%: 9 liq., real -$0, ganador 0x4716…e252

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |
|---|---:|---:|---:|---:|---:|---:|
| $0–$10 | 2,076 | $965 | $0 | 27% | 1,436 | 217 |
| $10–$100 | 810 | $7,373 | $1 | 29% | 280 | 98 |
| $100–$1,000 | 475 | $20.5 k | $3 | 16% | 128 | 74 |
| $1,000–$10.0 k | 144 | $35.4 k | $4 | 11% | 20 | 34 |
| ≥ $10.0 k | 19 | $17.7 k | $296 | 4% | 1 | 13 |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |
|---|---|---:|---:|---:|---:|---:|---:|
| base | `0x583d…9b77` | 1353 | 10 | $558.9 k | 0% | $441.8 k | 85% |
| base | `0xc4bf…fc51` | 139 | 32 | $7,905 | 43% | $0 | 0% |
| base | `0x30e9…eab3` | 124 | 2 | $463 | 79% | $0 | 22% |
| base | `0x9a03…e88c` | 85 | 8 | $1,578 | 52% | $0 | 0% |
| base | `0xb445…14b2` | 70 | 24 | $29.2 k | 59% | $0 | 0% |
| arbitrum | `0x8ad1…86c1` | 64 | 9 | $26.6 k | 1% | $25.5 k | 73% |
| base | `0x16e4…7b19` | 62 | 1 | $0 | — | $0 | 0% |
| base | `0x89d5…3fec` | 60 | 10 | $32 | 62% | $0 | 0% |
| base | `0x97c4…8c24` | 60 | 2 | $8,851 | 97% | $0 | 0% |
| base | `0xe967…3137` | 54 | 1 | $593 | 88% | $0 | 13% |
| base | `0xaf16…f182` | 46 | 1 | $96 | 80% | $0 | 0% |
| arbitrum | `0x58ea…2073` | 44 | 1 | $0 | — | $0 | 0% |
| base | `0x2b68…778f` | 44 | 2 | $1,541 | -1% | $0 | 0% |
| base | `0xcee7…863d` | 43 | 35 | $5,348 | 20% | $0 | 0% |
| base | `0x561b…fc54` | 43 | 7 | $140 | 67% | $0 | 0% |

## Ganadores principales (por bono)

- `0x03bdf75d11237c0560f48527f360640d9c7ddcaa` — $222.7 k (16%)
- `0xbde3e91f09a9489f1b53eaa21eb32c89b2fd5c64` — $166.4 k (12%)
- `0x4c0f054ff82accb847d59e3b6b3d46f1ceef19f4` — $152.2 k (11%)
- `0xf6860780cd7b673a37cfc2716efd3742e09aedde` — $139.3 k (10%)
- `0xc921309ba3fe346db84b7fd9959ae82d924bbf04` — $86.3 k (6%)
- `0xbd0dd817c608e552d5f1ae701ab6c4da4fb00005` — $71.0 k (5%)
- `0xd12810b19b596347a3afac206d3ca65d08594b3f` — $68.7 k (5%)
- `0x8b61f5925f4515edb0b7b76c38036aaf9a818472` — $60.4 k (4%)
- `0x3ae5122d62e78dc14b98d8d30aca4faf9d1f1bba` — $53.5 k (4%)
- `0xe683b8ee2710eabcbf347b7cb0735cda11ef31ba` — $48.0 k (3%)

## Cobertura de la medición

| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| ethereum | 3/3 | 30.0 | 324 | 324 | 270 (83%) | 208 (64%) | debug_traceTransaction: 300 | oráculo 770, mercado 13, sin 0 | 0 |
| base | 10/10 | 30.0 | 2917 | 2915 | 2735 (94%) | 2621 (90%) | debug_traceTransaction: 1250, no_medido: 74, trace_transaction: 68 | oráculo 5159, mercado 17, sin 2 | 0 |
| arbitrum | 3/3 | 30.0 | 288 | 288 | 269 (93%) | 273 (95%) | debug_traceTransaction: 265 | oráculo 795, mercado 0, sin 0 | 0 |

Liquidaciones cuya tx pagó por el orden más de 1.5× su bono (probable liquidación de otro protocolo o arbitraje en la misma tx; el pago completo cuenta como OEV/builder): ethereum: 7.

Netos fuera de rango (no se cuentan como medidos; revisar a mano): ethereum `0x97113645e8aae912a8cc6ea3f476b4349ec3298473683d819f55013b52444e90` bono $180, neto $1,070 (ynETHx +2.70133, msETH -2.88781); ethereum `0x8037223f3d4290e91e63e5a9c97ecc238201ec2df8307d59a62b96716dc179b8` bono $118, neto $734 (ynETHx +1.77939, msETH -1.90242); ethereum `0xdc687eefd6408705860dae9522647643bcb3c324e390c0abebdf19eafd127355` bono $100, neto $857 (ETH +0.318399); ethereum `0x4bd6a34c6bc48a8d0e41cc1bf003feb1ed82c861da254eda053259ed0d8d191d` bono $94, neto $557 (ynETHx +1.40615, msETH -1.50322); ethereum `0xbc783801c22ef7604dd637b99bdcfc3dc12dd97fc3c0e286a495ee67792c3f1e` bono $61, neto $370 (ynETHx +0.92113, msETH -0.984718); ethereum `0x87f0e8242f3e52a0acaf05a4fee22b3cf6af88a8eed8ec648cc37605951027df` bono $3, neto -$128 (sNUSD +123.626, USDC -128.231); arbitrum `0xb5eefa72cfbcb01ca2e4a860677f7e92968d6f40bf15ff8fd65a23276969d50a` bono $1, neto -$47 (PT-USDai-18JUN2026 +48.6253, USDC -47.3854); ethereum `0x96d31552654be3ba9bbc9205dd48c64b6d8e2db71b25bf189908934ec3d7d40f` bono $1, neto -$46 (sNUSD +44.1223, USDC -45.7657).

Errores de trazas más comunes: base: debug_traceTransaction: HTTP 408 en base.drpc.org (1042); base: debug_traceTransaction: HTTP 429 en base.drpc.org (539); base: trace_transaction: HTTP 408 en base.drpc.org (475); base: trace_transaction: HTTP 429 en base.drpc.org (270).

## Qué NO dice este census

- "Se queda" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y sale menor (y la liquidación puede clasificarse como "subasta").
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) se pagan por fuera de la transacción y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- No reconcilia todas las posiciones del alcance (puerta "cobertura del mercado" de Omega): solo mide las liquidaciones que sí ocurrieron.
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
