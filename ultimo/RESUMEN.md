# Census del dinero · 2026-10-24

Ventana: **30 días** · cadenas: ethereum, base, arbitrum · protocolos: Aave V3 y Morpho Blue.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$1.11 M** en 3,529 liquidaciones.
2. **¿Quién se lo lleva?** 287 liquidadores distintos; los 3 mayores se llevan **46%** del bono.
3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **1 bloques** (2 s) desde la última actualización del oráculo; **17%** en el mismo bloque.
4. **¿Qué porcentaje dejó al builder?** Ethereum: **80%** del bono (propina + pago directo al coinbase, que incluye las pujas de Chainlink SVR). En L2 no hay builder; la propina de prioridad fue: arbitrum 0%, base 1%.
5. **¿Cuánto se queda realmente el ganador?** En las 3,122 liquidaciones con medición completa (88% del total): bono $1.02 M, el ganador se quedó **-$21.0 k (-2%)**; a subastas de oráculo/OEV $659.2 k (64%), al builder en directo $157.2 k, en propina $4,567, gas base $164, resto (deslizamiento, comisiones) $224.8 k.

## ¿A dónde se va el bono?

Solo liquidaciones con medición completa (todos los movimientos de tokens y ETH de la transacción valuados). OEV = ETH pagado a terceros que no son el builder del bloque (subastas de oráculo como SVR/Atlas). Resto = bono − todo lo anterior: deslizamiento al vender, comisiones, pagos en tokens.

| Cadena | Protocolo | Medidas | Bono | Ganador | % | OEV | Builder directo | Propina | Gas base | Resto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | aave | 239/242 | $27.3 k | $933 | 3% | $25.6 k | $0 | $13 | $10 | $758 |
| arbitrum | morpho | 30/46 | $73 | $74 | 101% | $0 | $0 | $0 | $0 | -$2 |
| base | aave | 185/194 | $17.0 k | $173 | 1% | $16.8 k | $0 | $28 | $3 | $7 |
| base | morpho | 2521/2723 | $784.6 k | $33.5 k | 4% | $385.4 k | $0 | $4,242 | $71 | $361.3 k |
| ethereum | aave | 80/159 | $182.4 k | -$55.8 k | -31% | $231.4 k | $144.0 k | $48 | $59 | -$137.3 k |
| ethereum | morpho | 67/165 | $13.6 k | $154 | 1% | $37 | $13.2 k | $236 | $21 | -$8 |

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| arbitrum | aave | 242 | $27.3 k | 32 | 88% | 9 · 104 · 533 | 27 | 0% | n/a |
| arbitrum | morpho | 46 | $75 | 16 | 83% | 687 · 919 · 8,649 | 235 | 6% | n/a |
| base | aave | 194 | $17.6 k | 33 | 91% | 1 · 46 · 366 | 91 | 0% | n/a |
| base | morpho | 2,723 | $867.8 k | 144 | 53% | 1 · 1 · 2 | 2 | 18% | n/a |
| ethereum | aave | 159 | $182.4 k | 41 | 92% | 0 · 0 · 41 | 0 | 53% | 79% |
| ethereum | morpho | 165 | $13.6 k | 52 | 79% | 0 · 7 · 981 | 84 | 33% | 98% |

## Subasta vs. directa

"Subasta": lo pagado a terceros en ETH más la propina es ≥ 30% del bono (subasta de oráculo, builder o guerra de prioridad). "Directa": el ganador no pagó por el orden. "Sin medir": faltaron trazas o precios.

| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arbitrum | directa | 217 | $1,050 | $735 | 70% | -$0 | 32 | 163 |
| arbitrum | sin_medir | 19 | $2 | — | — | — | 5 | 928 |
| arbitrum | subasta | 52 | $26.3 k | $273 | 1% | $0 | 15 | 9 |
| base | directa | 1626 | $338.9 k | $31.7 k | 9% | $0 | 144 | 1 |
| base | sin_medir | 211 | $83.9 k | — | — | — | 37 | 1 |
| base | subasta | 1080 | $462.7 k | $1,966 | 0% | $0 | 48 | 1 |
| ethereum | directa | 74 | $1,204 | $885 | 74% | $0 | 24 | 100 |
| ethereum | sin_medir | 177 | $2 | — | — | — | 56 | 106 |
| ethereum | subasta | 73 | $194.8 k | -$56.5 k | -29% | $0 | 31 | 0 |

## ¿Queda margen para un actor pequeño?

Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.

| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |
|---|---:|---|---:|---|---|---:|---:|---:|
| arbitrum | 30.0 | 217 / 269 / 288 | $735 | 7 · $698 · 67% | 1 · $477 · 100% | 32 | 163 | 95% |
| base | 30.0 | 1626 / 2706 / 2917 | $31.7 k | 278 · $31.2 k · 28% | 53 · $23.3 k · 43% | 144 | 1 | 44% |
| ethereum | 30.0 | 74 / 147 / 324 | $885 | 6 · $895 · 73% | 4 · $871 · 73% | 24 | 100 | 78% |

"top": parte del neto que se llevó el mayor ganador de ese grupo. "≥ 2 bloques": liquidaciones que llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).

### Bots que ganan por fuera de subastas

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | `0x97c4e986d7c270f4951cc09e6de0bc66d4778c24` | 2 | 60 | $8,851 | $8,551 | 97% | $63 | 2 | 2 | Morpho WETH/USDC lltv 86.0% (30); Morpho cbXRP/USDC lltv 62.5% (26); Morpho cbETH/USDC lltv 77.0% (3) |
| base | `0x759915f8e7b07a5c0a3a3a7ee52ee3643feea0d3` | 3 | 10 | $13.1 k | $8,549 | 65% | $319 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (5); Morpho cbZEC/USDC lltv 62.5% (3); Morpho WETH/USDC lltv 86.0% (2) |
| base | `0xc4bfb65f09174569eac5d849fec32431d0d0fc51` | 32 | 139 | $7,905 | $3,334 | 42% | $14 | 1 | 2 | Morpho cbXRP/USDC lltv 62.5% (122); Morpho WETH/USDC lltv 86.0% (17) |
| base | `0xa1018068bb72f2b9f309267ed48767b8ac19be93` | 1 | 1 | $2,281 | $2,147 | 94% | $2,147 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0xaa9e48dadf4ae8472b67f1da0326623266c17443` | 24 | 28 | $3,155 | $2,034 | 64% | $2 | 2 | 2 | Morpho cbXRP/USDC lltv 62.5% (22); Morpho WETH/USDC lltv 86.0% (4); Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0x5ef5ffc16baacc0f97ec5e5284ef9b1487264170` | 1 | 6 | $1,153 | $1,132 | 98% | $188 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (6) |
| base | `0x35302b7ab4346aec5a91234d492b0033b3004bb6` | 1 | 12 | $1,269 | $1,110 | 87% | $55 | 0 | 2 | Morpho cbETH/USDC lltv 77.0% (12) |
| base | `0xcee740502c9e84118e4a13efc085dff70784863d` | 35 | 43 | $5,348 | $1,066 | 20% | $16 | 2 | 2 | Morpho cbXRP/USDC lltv 62.5% (40); Morpho JitoSOL/USDC lltv 62.5% (2); Morpho cbZEC/USDC lltv 62.5% (1) |
| base | `0x9a039ccdb7cfa560e004419f3aa7a552e040e88c` | 8 | 85 | $1,578 | $825 | 52% | $3 | 1 | 3 | Morpho cbXRP/USDC lltv 62.5% (44); Morpho WETH/USDC lltv 86.0% (37); Morpho SOL/USDC lltv 62.5% (3) |
| ethereum | `0x875a5cf56ebce1c6fb84d24495728e6d6f39a0be` | 1 | 2 | $856 | $576 | 67% | $288 | 0 | 1 | aave-v3-core WETH→USDC (2) |
| base | `0x7a08760fa8897a6574bbbe7511217d2a06664d44` | 4 | 21 | $548 | $547 | 100% | $1 | 0 | 5 | Morpho cbETH/USDC lltv 77.0% (13); Morpho cbXRP/USDC lltv 62.5% (6); Morpho SOL/USDC lltv 62.5% (1) |
| base | `0xe9674a87681bda6f5eaceabe61c01537e4283137` | 1 | 47 | $557 | $504 | 91% | $2 | 0 | 3 | Morpho cbETH/USDC lltv 77.0% (43); Morpho cbXRP/USDC lltv 62.5% (2); Morpho AERO/USDC lltv 62.5% (1) |
| arbitrum | `0x9355ec6d797b6c8b73de9b52fffdb3bfa6d05fdb` | 2 | 4 | $465 | $477 | 103% | $0 | 60 | 3 | aave-v3-arbitrum ARB→USD₮0 (1); aave-v3-arbitrum USDC→USDC (1); aave-v3-arbitrum WETH→WETH (1) |
| base | `0x30e91ff0bb5220f9df82a52841602de44f2eeab3` | 2 | 97 | $370 | $317 | 86% | $1 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (97) |
| base | `0x5feae2565fdc0034ca64461c32d95c9e8eb95652` | 1 | 1 | $281 | $288 | 102% | $288 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (1) |
| base | `0xe1f760baef51d0736482e5ddfab7fe3c4444a47b` | 1 | 2 | $268 | $250 | 93% | $125 | 0 | 1 | Morpho cbETH/USDC lltv 77.0% (2) |
| base | `0xbc7de03893e2da1af83fe43ad38ab38e4b211e63` | 1 | 20 | $260 | $231 | 89% | $9 | 0 | 2 | Morpho cbETH/USDC lltv 77.0% (20) |
| base | `0xf4c350640d8537888e62bb4f6b2d2123efe6a64f` | 1 | 1 | $191 | $191 | 100% | $191 | — | 1 | Morpho yoUSD/USDC lltv 91.5% (1) |
| base | `0x979f9365d88e5ffd359f3701af184e69d1adb923` | 1 | 12 | $164 | $187 | 114% | $1 | 2 | 1 | Morpho WETH/USDC lltv 86.0% (6); Morpho cbDOGE/USDC lltv 62.5% (4); Morpho cbXRP/USDC lltv 62.5% (2) |
| ethereum | `0xe7cd2fa44cce16e70867338f7b9fd60ad3b9d4b5` | 1 | 1 | $193 | $173 | 89% | $173 | — | 1 | Morpho STONE/WETH lltv 94.5% (1) |

### Contratos que pagan por el orden (subastas)

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| base | `0xd128…4b3f` | 10 | 167 | $52.6 k | $1,481 | 3% | $47.7 k | 1 |
| ethereum | `0x875a…a0be` | 1 | 5 | $22.5 k | $432 | 2% | $19.7 k | 0 |
| base | `0x2ea8…907f` | 5 | 9 | $21.5 k | $211 | 1% | $16.8 k | 2 |
| arbitrum | `0x754b…acd5` | 1 | 1 | $17.5 k | $201 | 1% | $17.3 k | 9 |
| base | `0x40fe…3d88` | 1 | 3 | $361 | $195 | 54% | $157 | 1 |
| ethereum | `0x854a…57ab` | 1 | 3 | $693 | $153 | 22% | $679 | 1 |
| ethereum | `0x6f28…5443` | 1 | 1 | $5,092 | $80 | 2% | $4,970 | — |
| base | `0xd2c7…3077` | 1 | 1 | $114 | $76 | 66% | $39 | 1 |
| base | `0xcd74…4a46` | 1 | 1 | $114 | $74 | 65% | $39 | 0 |
| base | `0x6109…f9f7` | 1 | 10 | $6,547 | $71 | 1% | $6,219 | 1 |
| base | `0x30e9…eab3` | 1 | 27 | $93 | $53 | 57% | $39 | 0 |
| ethereum | `0x789e…3f79` | 2 | 2 | $4,651 | $48 | 1% | $4,668 | 0 |

### ¿A quién va el ETH que sale del liquidador?

"compartido": cobra de 2 o más liquidadores (subasta, builder). "un_solo_liquidador": puede ser la tesorería del mismo bot; si lo es, ese pago es ganancia y no OEV.

| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |
|---|---|---|---:|---:|---:|---|
| base | `0x1c6ec84518b859ae6a96c7dd0c78048be7def976` | compartido | $400.8 k | 1156 | 29 | no |
| ethereum | `0x000000000004444c5dc75cb358380d2e3de08a90` | compartido | $231.4 k | 4 | 4 | no |
| ethereum | `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97` | builder | $99.0 k | 77 | 27 | no |
| ethereum | `0xdadb0d80178819f2319190d340ce9a924f783711` | builder | $27.0 k | 18 | 13 | no |
| ethereum | `0xd87f3d6c5624e8b02be13c2c92f8511b88b94d96` | builder | $26.1 k | 1 | 1 | no |
| arbitrum | `0xab6deeaf17d69f091e6fe8e9f472a69c7112ce45` | compartido | $25.5 k | 56 | 12 | no |
| ethereum | `0x6adb3bab5730852eb53987ea89d8e8f16393c200` | builder | $5,003 | 2 | 2 | no |
| base | `0x498581ff718922c3f8e6a244956af099b2652b2b` | compartido | $1,365 | 5 | 4 | no |
| arbitrum | `0x35c43aff60e94a64799782574f179d4865e9b377` | un_solo_liquidador | $35 | 1 | 1 | no |
| arbitrum | `0xde632c3a214d5f14c1d8ddf0b92f8bcd188fee45` | un_solo_liquidador | $26 | 1 | 1 | no |
| base | `0x9af4392e4f4575d3155fec6efb34e878b04384c4` | un_solo_liquidador | $12 | 16 | 1 | no |
| arbitrum | `0xe40a526a79b704a1de69907905ae6f60966a966e` | un_solo_liquidador | $11 | 1 | 1 | no |
| ethereum | `0x396343362be2a4da1ce0c1c210945346fb82aa49` | builder | $9 | 3 | 3 | no |
| arbitrum | `0x360e68faccca8ca495c1b759fd9eee466db9fb32` | un_solo_liquidador | $7 | 1 | 1 | no |
| arbitrum | `0x996b6b6818a20d8ec256cab85ee4119710912c57` | un_solo_liquidador | $6 | 1 | 1 | no |

## Saturación de mercados

Vírgenes: **2** · disputados: **65** · muertos: **14** · con muestra insuficiente (<3): 179.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | Morpho cbETH/USDC lltv 77.0% | 471 | $32.5 k | $13.7 k | 45% | 396 | 46 | 34% | 0 | disputada |
| base | Morpho cbXRP/USDC lltv 62.5% | 778 | $325.3 k | $12.7 k | 5% | 482 | 51 | 19% | 2 | disputada |
| base | Morpho WETH/USDC lltv 86.0% | 538 | $92.8 k | $3,253 | 4% | 271 | 34 | 64% | 1 | disputada |
| base | Morpho cbZEC/USDC lltv 62.5% | 61 | $11.8 k | $2,880 | 24% | 24 | 17 | 49% | 1 | disputada |
| ethereum | aave-v3-core sUSDe→USDtb | 1 | $53.6 k | $1,660 | 3% | 0 | 1 | 100% | 0 | muestra_insuficiente |
| ethereum | aave-v3-core WETH→USDT | 33 | $29.0 k | $591 | 2% | 4 | 14 | 72% | 0 | muerta |
| ethereum | aave-v3-core WETH→USDC | 28 | $5,995 | $563 | 9% | 5 | 10 | 60% | 0 | muerta |
| arbitrum | aave-v3-arbitrum ARB→USD₮0 | 1 | $465 | $477 | 103% | 1 | 1 | 100% | 4 | muestra_insuficiente |
| base | Morpho JitoSOL/USDC lltv 62.5% | 217 | $20.0 k | $256 | 1% | 78 | 22 | 33% | — | disputada |
| arbitrum | aave-v3-arbitrum WBTC→WBTC | 2 | $17.5 k | $201 | 1% | 1 | 2 | 100% | 146 | muestra_insuficiente |
| base | Morpho yoUSD/USDC lltv 91.5% | 3 | $200 | $194 | 97% | 1 | 3 | 95% | — | disputada |
| base | Morpho cbETH/USDC lltv 86.0% | 2 | $201 | $189 | 94% | 1 | 2 | 99% | 2 | muestra_insuficiente |
| ethereum | Morpho STONE/WETH lltv 94.5% | 1 | $193 | $173 | 89% | 1 | 1 | 100% | — | muestra_insuficiente |
| base | aave-v3-base WETH→USDC | 79 | $16.4 k | $154 | 1% | 46 | 18 | 50% | 2 | muerta |
| ethereum | aave-v3-core AAVE→USDC | 7 | $689 | $152 | 22% | 1 | 4 | 100% | 1 | muerta |

### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)

- ethereum · aave-v3-core WETH→USDe: 3 liq., real $0, ganador —
- arbitrum · Morpho thBILL/USDC lltv 94.5%: 9 liq., real -$0, ganador 0x4716…e252

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |
|---|---:|---:|---:|---:|---:|---:|
| $0–$10 | 1,998 | $835 | $0 | 23% | 1,434 | 194 |
| $10–$100 | 767 | $6,672 | $0 | 25% | 319 | 83 |
| $100–$1,000 | 441 | $14.5 k | $0 | 11% | 139 | 62 |
| $1,000–$10.0 k | 132 | $13.9 k | $0 | 4% | 20 | 31 |
| ≥ $10.0 k | 15 | -$56.9 k | $0 | -11% | 2 | 10 |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |
|---|---|---:|---:|---:|---:|---:|---:|
| base | `0x583d…9b77` | 1353 | 10 | $558.9 k | 0% | $400.8 k | 81% |
| base | `0xc4bf…fc51` | 139 | 32 | $7,905 | 42% | $0 | 0% |
| base | `0x30e9…eab3` | 124 | 2 | $463 | 80% | $0 | 22% |
| base | `0x9a03…e88c` | 85 | 8 | $1,578 | 52% | $0 | 0% |
| base | `0xb445…14b2` | 70 | 24 | $29.2 k | -0% | $0 | 0% |
| arbitrum | `0x8ad1…86c1` | 64 | 9 | $26.6 k | 1% | $25.5 k | 72% |
| base | `0x16e4…7b19` | 62 | 1 | $0 | — | $0 | 0% |
| base | `0x89d5…3fec` | 60 | 10 | $32 | 60% | $0 | 0% |
| base | `0x97c4…8c24` | 60 | 2 | $8,851 | 97% | $0 | 0% |
| base | `0xe967…3137` | 54 | 1 | $593 | 88% | $0 | 13% |
| base | `0xaf16…f182` | 46 | 1 | $96 | -20% | $0 | 0% |
| arbitrum | `0x58ea…2073` | 44 | 1 | $0 | — | $0 | 0% |
| base | `0x2b68…778f` | 44 | 2 | $1,541 | -1% | $0 | 0% |
| base | `0xcee7…863d` | 43 | 35 | $5,348 | 20% | $0 | 0% |
| base | `0x561b…fc54` | 43 | 7 | $140 | 67% | $0 | 0% |

## Ganadores principales (por bono)

- `0x03bdf75d11237c0560f48527f360640d9c7ddcaa` — $222.7 k (20%)
- `0x4c0f054ff82accb847d59e3b6b3d46f1ceef19f4` — $152.2 k (14%)
- `0xf6860780cd7b673a37cfc2716efd3742e09aedde` — $139.3 k (13%)
- `0xc921309ba3fe346db84b7fd9959ae82d924bbf04` — $86.3 k (8%)
- `0xbd0dd817c608e552d5f1ae701ab6c4da4fb00005` — $71.0 k (6%)
- `0xd12810b19b596347a3afac206d3ca65d08594b3f` — $63.4 k (6%)
- `0x8b61f5925f4515edb0b7b76c38036aaf9a818472` — $60.4 k (5%)
- `0x3ae5122d62e78dc14b98d8d30aca4faf9d1f1bba` — $53.5 k (5%)
- `0xac5c4ccfc12b2b85c091d12e78d675e888ce10c4` — $29.2 k (3%)
- `0x875a5cf56ebce1c6fb84d24495728e6d6f39a0be` — $23.3 k (2%)

## Cobertura de la medición

| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| ethereum | 3/3 | 30.0 | 324 | 153 | 147 (45%) | 108 (33%) | debug_traceTransaction: 138, sin_enriquecer: 162 | oráculo 367, mercado 5, sin 0 | 0 |
| base | 10/10 | 30.0 | 2917 | 2915 | 2706 (93%) | 2621 (90%) | trace_transaction: 295, debug_traceTransaction: 1030, no_medido: 67 | oráculo 5344, mercado 17, sin 2 | 0 |
| arbitrum | 3/3 | 30.0 | 288 | 288 | 269 (93%) | 273 (95%) | debug_traceTransaction: 265 | oráculo 795, mercado 0, sin 0 | 0 |

Liquidaciones cuya tx pagó por el orden más de 1.5× su bono (probable liquidación de otro protocolo o arbitraje en la misma tx; el pago completo cuenta como OEV/builder): ethereum: 7, base: 2, arbitrum: 1.

Netos fuera de rango (no se cuentan como medidos; revisar a mano): arbitrum `0xb5eefa72cfbcb01ca2e4a860677f7e92968d6f40bf15ff8fd65a23276969d50a` bono $1, neto -$47 (PT-USDai-18JUN2026 +48.6253, USDC -47.3854).

Errores de trazas más comunes: base: debug_traceTransaction: HTTP 408 en base.drpc.org (619); base: trace_transaction: HTTP 408 en base.drpc.org (577); base: debug_traceTransaction: HTTP 429 en base.drpc.org (394); base: trace_transaction: HTTP 429 en base.drpc.org (267); arbitrum: debug_traceTransaction: historical state is not available (21).

## Qué NO dice este census

- "Se queda" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y sale menor (y la liquidación puede clasificarse como "subasta").
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) se pagan por fuera de la transacción y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- No reconcilia todas las posiciones del alcance (puerta "cobertura del mercado" de Omega): solo mide las liquidaciones que sí ocurrieron.
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
