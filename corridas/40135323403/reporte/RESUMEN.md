# Census del dinero · 2026-10-24

Ventana: **2 días** · cadenas: ethereum, base, arbitrum · protocolos: Aave V3 y Morpho Blue.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$51.8 k** en 356 liquidaciones.
2. **¿Quién se lo lleva?** 59 liquidadores distintos; los 3 mayores se llevan **58%** del bono.
3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **1 bloques** (2 s) desde la última actualización del oráculo; **25%** en el mismo bloque.
4. **¿Qué porcentaje dejó al builder (Ethereum)?** **103%** del bono (propina + pago directo al coinbase).
5. **¿Cuánto se queda realmente el ganador?** En las 346 liquidaciones con medición completa (97% del total): bono $46.1 k, el ganador se quedó **$2,677 (6%)**; a subastas de oráculo/OEV $28.0 k (61%), al builder en directo $14.3 k, en propina $338, gas base $25, resto (deslizamiento, comisiones) $784.

## ¿A dónde se va el bono?

Solo liquidaciones con medición completa (todos los movimientos de tokens y ETH de la transacción valuados). OEV = ETH pagado a terceros que no son el builder del bloque (subastas de oráculo como SVR/Atlas). Resto = bono − todo lo anterior: deslizamiento al vender, comisiones, pagos en tokens.

| Cadena | Protocolo | Medidas | Bono | Ganador | % | OEV | Builder directo | Propina | Gas base | Resto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | aave | 15/15 | $4,013 | $117 | 3% | $3,532 | $0 | $1 | $1 | $362 |
| arbitrum | morpho | 3/3 | $0 | -$0 | — | $0 | $0 | $0 | $0 | $0 |
| base | aave | 62/62 | $5,177 | $4 | 0% | $4,966 | $0 | $3 | $1 | $203 |
| base | morpho | 222/231 | $23.1 k | $2,554 | 11% | $19.5 k | $0 | $149 | $3 | $929 |
| ethereum | aave | 23/23 | $9,319 | $164 | 2% | $1 | $9,878 | $0 | $14 | -$739 |
| ethereum | morpho | 21/22 | $4,485 | -$162 | -4% | $0 | $4,428 | $184 | $6 | $29 |

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| arbitrum | aave | 15 | $4,013 | 6 | 98% | 8 · 8 · 9 | 2 | 0% | n/a |
| arbitrum | morpho | 3 | $0 | 2 | 100% | 1 · 1 · 1 | 0 | 0% | n/a |
| base | aave | 62 | $5,177 | 7 | 100% | 16 · 116 · 366 | 232 | 0% | n/a |
| base | morpho | 231 | $23.7 k | 29 | 79% | 0 · 1 · 2 | 2 | 28% | n/a |
| ethereum | aave | 23 | $9,319 | 10 | 93% | 0 · 0 · 1 | 0 | 74% | 106% |
| ethereum | morpho | 22 | $9,577 | 12 | 96% | 0 · 0 · 96 | 0 | 55% | 100% |

## Subasta vs. directa

"Subasta": lo pagado a terceros en ETH más la propina es ≥ 30% del bono (subasta de oráculo, builder o guerra de prioridad). "Directa": el ganador no pagó por el orden. "Sin medir": faltaron trazas o precios.

| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | directa | 8 | $115 | $110 | 96% | $0 | 4 | 8 |
| arbitrum | subasta | 10 | $3,898 | $7 | 0% | $0 | 4 | 8 |
| base | directa | 170 | $2,827 | $2,576 | 91% | -$0 | 28 | 1 |
| base | sin_medir | 9 | $559 | — | — | — | 6 | 0 |
| base | subasta | 114 | $25.5 k | -$19 | -0% | -$0 | 11 | 1 |
| ethereum | directa | 16 | $201 | $4 | 2% | $0 | 9 | 96 |
| ethereum | sin_medir | 1 | $5,092 | — | — | — | 1 | — |
| ethereum | subasta | 28 | $13.6 k | -$1 | -0% | $0 | 12 | 0 |

## ¿Queda margen para un actor pequeño?

Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.

| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |
|---|---:|---|---:|---|---|---:|---:|---:|
| arbitrum | 2.0 | 8 / 18 / 18 | $110 | 2 · $110 · 100% | 0 · $0 · — | 4 | 8 | 83% |
| base | 2.0 | 170 / 284 / 293 | $2,576 | 8 · $2,559 · 84% | 2 · $2,407 · 89% | 28 | 1 | 44% |
| ethereum | 2.0 | 16 / 44 / 45 | $4 | 0 · $0 · — | 0 · $0 · — | 9 | 96 | 73% |

"top": parte del neto que se llevó el mayor ganador de ese grupo. "≥ 2 bloques": liquidaciones que llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).

### Bots que ganan por fuera de subastas

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | `0xa1018068bb72f2b9f309267ed48767b8ac19be93` | 1 | 1 | $2,281 | $2,147 | 94% | $2,147 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0x5ef5ffc16baacc0f97ec5e5284ef9b1487264170` | 1 | 1 | $271 | $260 | 96% | $260 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| arbitrum | `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | 1 | 3 | $115 | $110 | 96% | $53 | 10 | 1 | aave-v3-arbitrum WBTC→USDC (3) |
| base | `0x4b5f9d861d15961cc0108ca9c1462cd38aaf571e` | 1 | 2 | $75 | $68 | 91% | $34 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (2) |
| base | `0x97c4e986d7c270f4951cc09e6de0bc66d4778c24` | 1 | 3 | $51 | $43 | 85% | $13 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (3) |
| base | `0x3b5e286bd3f7b6b3c858665a368866ca254e85e9` | 1 | 1 | $44 | $42 | 95% | $42 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0x37a4341548526400abea62e8bd481856366c9b71` | 1 | 2 | $20 | $15 | 75% | $7 | 0 | 2 | Morpho AERO/USDC lltv 62.5% (2) |
| base | `0xaa9e48dadf4ae8472b67f1da0326623266c17443` | 1 | 1 | $5 | $6 | 117% | $6 | — | 1 | Morpho wbCOIN/USDC lltv 86.0% (1) |
| ethereum | `0xe08d97e151473a848c3d9ca3f323cb720472d015` | 1 | 2 | $5 | $4 | 78% | $2 | 0 | 1 | Morpho PT-slvlUSD-25SEP2025/lvlUSD lltv 91.5% (1); Morpho cbBTC/USDC lltv 86.0% (1) |
| base | `0xc5d32cc840373a5541f07fd108311d35492764d6` | 5 | 12 | $7 | $2 | 27% | $0 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (12) |
| base | `0x7a08760fa8897a6574bbbe7511217d2a06664d44` | 1 | 1 | $1 | $1 | — | $1 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0xd8413bf7e7782b536abdeebbcb9e7c4fc481e2e7` | 1 | 1 | $1 | $1 | — | $1 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0xdb9c0247c67fa19e4e730fae129a346ba6f3093f` | 2 | 4 | $0 | $0 | — | $0 | — | 1 | Morpho WETH/WETH lltv 62.5% (4) |
| base | `0x8407699e359ae158bd7ec0668600cc19a79f17c3` | 1 | 1 | $0 | $0 | — | $0 | 1 | 1 | aave-v3-base WETH→GHO (1) |
| base | `0xcd74023f92b529a9b933ca73c89f9412d4984a46` | 1 | 1 | $1 | $0 | — | $0 | 1 | 1 | Morpho cbZEC/USDC lltv 62.5% (1) |
| ethereum | `0xc2f175d0568b7f7142c969ed418f5022b9392348` | 1 | 1 | $0 | $0 | — | $0 | 7 | 1 | Morpho WBTC/USDC lltv 86.0% (1) |
| base | `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | 1 | 4 | $0 | $0 | — | $0 | 9 | 2 | aave-v3-base WETH→GHO (2); Morpho cbETH/USDC lltv 77.0% (1); aave-v3-base WETH→WETH (1) |
| base | `0xdb61a25516b4480df393d7bfe2d8e33fdaaf079a` | 7 | 21 | $10 | $0 | 1% | $0 | 1 | 2 | Morpho JitoSOL/USDC lltv 62.5% (5); Morpho SOL/USDC lltv 62.5% (5); Morpho cbLTC/USDC lltv 62.5% (4) |
| base | `0x859bcb5d6951930ec2680ab02a9ec04a47f350f2` | 1 | 1 | $0 | $0 | — | $0 | — | 1 | Morpho WETH/WETH lltv 62.5% (1) |
| ethereum | `0x00acd5005200e7009beb000000e35e1e002b5565` | 1 | 6 | $1 | $0 | 7% | $0 | 2,504 | 2 | Morpho PT-srUSDe-2APR2026/USDC lltv 91.5% (2); Morpho beraSTONE/WETH lltv 91.5% (1); Morpho sDOLA/USDC lltv 91.5% (1) |

### Contratos que pagan por el orden (subastas)

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ethereum | `0x854a…57ab` | 1 | 2 | $689 | $153 | 22% | $675 | 0 |
| base | `0xcd74…4a46` | 1 | 1 | $114 | $74 | 65% | $39 | 0 |
| ethereum | `0x2945…284f` | 2 | 2 | $1,411 | $14 | 1% | $1,377 | 0 |
| base | `0x2ea8…907f` | 1 | 1 | $1,384 | $13 | 1% | $1,261 | 1 |
| ethereum | `0x5ac9…95bd` | 2 | 4 | $2,999 | $7 | 0% | $3,151 | 0 |
| arbitrum | `0x3e7a…d288` | 2 | 2 | $3,137 | $7 | 0% | $2,777 | 8 |
| base | `0xbd0d…0005` | 4 | 12 | $3,335 | $6 | 0% | $3,250 | 2 |
| ethereum | `0x1633…5d41` | 1 | 1 | $70 | $3 | 4% | $70 | 0 |
| base | `0x5ac9…95bd` | 1 | 1 | $7 | $3 | 44% | $3 | 976 |
| ethereum | `0x875a…a0be` | 1 | 1 | $91 | $2 | 2% | $87 | 0 |
| base | `0xc5d3…64d6` | 2 | 2 | $4 | $1 | 27% | $2 | 0 |
| arbitrum | `0x92e1…2b3e` | 1 | 1 | $79 | $1 | 1% | $75 | 8 |

### ¿A quién va el ETH que sale del liquidador?

"compartido": cobra de 2 o más liquidadores (subasta, builder). "un_solo_liquidador": puede ser la tesorería del mismo bot; si lo es, ese pago es ganancia y no OEV.

| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |
|---|---|---|---:|---:|---:|---|
| base | `0x1c6ec84518b859ae6a96c7dd0c78048be7def976` | compartido | $24.5 k | 143 | 6 | no |
| ethereum | `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97` | builder | $12.0 k | 24 | 11 | no |
| ethereum | `0x6adb3bab5730852eb53987ea89d8e8f16393c200` | builder | $4,969 | 1 | 1 | no |
| arbitrum | `0xab6deeaf17d69f091e6fe8e9f472a69c7112ce45` | compartido | $3,521 | 11 | 4 | no |
| ethereum | `0xdadb0d80178819f2319190d340ce9a924f783711` | builder | $2,286 | 6 | 5 | no |
| arbitrum | `0xe40a526a79b704a1de69907905ae6f60966a966e` | un_solo_liquidador | $11 | 1 | 1 | no |
| ethereum | `0x396343362be2a4da1ce0c1c210945346fb82aa49` | builder | $9 | 1 | 1 | no |
| ethereum | `0x000000000004444c5dc75cb358380d2e3de08a90` | un_solo_liquidador | $1 | 1 | 1 | no |
| base | `0x498581ff718922c3f8e6a244956af099b2652b2b` | un_solo_liquidador | $0 | 1 | 1 | no |

## Saturación de mercados

Vírgenes: **3** · disputados: **18** · muertos: **1** · con muestra insuficiente (<3): 51.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | Morpho cbETH/USDC lltv 77.0% | 58 | $3,447 | $2,622 | 91% | 46 | 17 | 66% | 0 | disputada |
| ethereum | aave-v3-core AAVE→USDC | 2 | $689 | $153 | 22% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | Morpho USDe/DAI lltv 86.0% | 1 | $5,092 | $0 | — | 0 | 1 | 100% | — | muestra_insuficiente |
| arbitrum | aave-v3-arbitrum WBTC→USDC | 5 | $220 | $111 | 50% | 3 | 3 | 52% | 8 | disputada |
| ethereum | aave-v3-core WETH→USDT | 8 | $2,786 | $14 | 0% | 0 | 2 | 51% | 0 | disputada |
| base | Morpho cbZEC/USDC lltv 62.5% | 3 | $1,401 | $13 | 1% | 1 | 3 | 99% | 1 | disputada |
| base | Morpho AERO/USDC lltv 62.5% | 3 | $20 | $11 | 56% | 2 | 2 | 98% | 0 | disputada |
| arbitrum | aave-v3-arbitrum ARB→USDC | 1 | $3,117 | $6 | 0% | 0 | 1 | 100% | 7 | muestra_insuficiente |
| base | Morpho wbCOIN/USDC lltv 86.0% | 1 | $5 | $6 | 117% | 1 | 1 | 100% | — | muestra_insuficiente |
| ethereum | Morpho cbBTC/USDC lltv 86.0% | 2 | $1,115 | $6 | 1% | 1 | 2 | 100% | 0 | muestra_insuficiente |
| ethereum | Morpho cbBTC/USDT lltv 86.0% | 1 | $2,991 | $5 | 0% | 0 | 1 | 100% | — | muestra_insuficiente |
| ethereum | Morpho WBTC/USDT lltv 86.0% | 2 | $161 | $5 | 3% | 0 | 2 | 56% | 0 | muestra_insuficiente |
| base | aave-v3-base cbBTC→USDC | 3 | $860 | $3 | 0% | 0 | 2 | 95% | 2 | disputada |
| base | Morpho cbHYPE/USDC lltv 62.5% | 2 | $9 | $3 | 34% | 0 | 2 | 78% | 488 | muestra_insuficiente |
| ethereum | Morpho mMEV/USDC lltv 91.5% | 1 | $5 | $1 | 33% | 0 | 1 | 100% | — | muestra_insuficiente |

### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)

- base · Morpho JitoSOL/USDC lltv 62.5%: 16 liq., real $1, ganador 0xdb61…079a
- base · Morpho cbDOGE/USDC lltv 62.5%: 8 liq., real $0, ganador 0xdb61…079a
- base · Morpho SOL/USDC lltv 62.5%: 21 liq., real -$1, ganador 0xdb61…079a

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |
|---|---:|---:|---:|---:|---:|---:|
| $0–$10 | 248 | -$181 | -$0 | -55% | 181 | 40 |
| $10–$100 | 60 | $272 | $0 | 11% | 9 | 17 |
| $100–$1,000 | 32 | $486 | $0 | 4% | 2 | 9 |
| $1,000–$10.0 k | 15 | $2,099 | $0 | 7% | 1 | 9 |
| ≥ $10.0 k | 0 | — | — | — | — | — |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |
|---|---|---:|---:|---:|---:|---:|---:|
| base | `0x583d…9b77` | 143 | 9 | $25.4 k | -0% | $24.5 k | 74% |
| base | `0x16e4…7b19` | 47 | 1 | $0 | — | $0 | 0% |
| base | `0x659b…7a08` | 21 | 6 | $11 | -34% | $0 | 0% |
| base | `0xc5d3…64d6` | 18 | 5 | $14 | 27% | $0 | 14% |
| arbitrum | `0x8ad1…86c1` | 12 | 5 | $3,898 | 0% | $3,532 | 83% |
| base | `0xf4b7…7f47` | 12 | 2 | $3 | -504% | $0 | 8% |
| base | `0x418c…bdfc` | 12 | 2 | $105 | -8% | $0 | 0% |
| ethereum | `0xd128…4b3f` | 11 | 3 | $3,857 | 0% | $4,553 | 100% |
| ethereum | `0x00ac…5565` | 7 | 1 | $4 | 10% | $0 | 14% |
| base | `0x5ac9…95bd` | 5 | 1 | $7 | 44% | $0 | 20% |
| base | `0xdb9c…093f` | 4 | 2 | $0 | — | $0 | 0% |
| ethereum | `0x5ac9…95bd` | 4 | 2 | $2,999 | 0% | $3,151 | 100% |
| arbitrum | `0x5ac9…95bd` | 3 | 1 | $115 | 96% | $0 | 0% |
| base | `0x97c4…8c24` | 3 | 1 | $51 | 85% | $0 | 0% |
| arbitrum | `0x2384…f8a1` | 2 | 1 | $0 | — | $0 | 0% |

## Ganadores principales (por bono)

- `0xdb61a25516b4480df393d7bfe2d8e33fdaaf079a` — $12.9 k (25%)
- `0xd12810b19b596347a3afac206d3ca65d08594b3f` — $12.3 k (24%)
- `0x6f28ca8cb6b35f0cf2b4a47739f14d0205f35443` — $5,092 (10%)
- `0xeef1b06e23a39f05b6b34ff1052d7a6ca3a00005` — $4,471 (9%)
- `0xbd0dd817c608e552d5f1ae701ab6c4da4fb00005` — $3,335 (6%)
- `0x3e7a65a9394e289dd23d9b393a8f8e02be62d288` — $3,137 (6%)
- `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` — $3,120 (6%)
- `0xa1018068bb72f2b9f309267ed48767b8ac19be93` — $2,281 (4%)
- `0x29452e8332912533130fb708984722d92184284f` — $1,411 (3%)
- `0x2ea89fc4b65ed6fa0494b6c9b15403bf1137907f` — $1,384 (3%)

## Cobertura de la medición

| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| ethereum | 2/2 | 2.0 | 45 | 45 | 44 (98%) | 34 (76%) | debug_traceTransaction: 36 | oráculo 102, mercado 2, sin 0 | 0 |
| base | 2/2 | 2.0 | 293 | 293 | 284 (97%) | 269 (92%) | trace_transaction: 39, debug_traceTransaction: 115, no_medido: 9 | oráculo 648, mercado 0, sin 0 | 0 |
| arbitrum | 1/1 | 2.0 | 18 | 18 | 18 (100%) | 16 (89%) | debug_traceTransaction: 17 | oráculo 50, mercado 0, sin 0 | 0 |

Netos fuera de rango (no se cuentan como medidos; revisar a mano): ethereum `0x7fc99655e7684a79c434f4722e0dc4fb9b092ae7e6cfb69e918eafef4516a5cd` bono $5,092, neto $121.3 k (DAI +81.0535, USDC +121203).

Errores de trazas más comunes: base: debug_traceTransaction: HTTP 408 en base.drpc.org (109); base: debug_traceTransaction: HTTP 429 en base.drpc.org (38); base: trace_transaction: HTTP 429 en base.drpc.org (37); base: trace_transaction: HTTP 408 en base.drpc.org (10).

## Qué NO dice este census

- "Se queda" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y sale menor (y la liquidación puede clasificarse como "subasta").
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) se pagan por fuera de la transacción y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- No reconcilia todas las posiciones del alcance (puerta "cobertura del mercado" de Omega): solo mide las liquidaciones que sí ocurrieron.
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
