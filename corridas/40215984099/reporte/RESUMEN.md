# Census del dinero · 2026-10-25

Ventana: **30 días** · cadenas: polygon, optimism, unichain, katana, hyperevm, worldchain, sonic, bsc, linea, scroll, sei, monad, celo, etherlink, hemi, ink, lisk, soneium, fraxtal, mode, plume, corn, tac, flare, cronos, xdc, kaia, zerog, abstract, morph, megaeth, robinhood, stable, tempo, arc, bitlayer, gensyn, eden · protocolos: Aave V3 y Morpho Blue.

> **Cobertura incompleta:** hyperevm (1/1 tramos, eventos cortados); linea (1/1 tramos, eventos cortados); scroll (1/1 tramos, eventos cortados); sei (1/1 tramos, eventos cortados); monad (1/1 tramos, eventos cortados); lisk (1/1 tramos, eventos cortados); soneium (1/1 tramos, eventos cortados); corn (1/1 tramos, eventos cortados); flare (1/1 tramos, eventos cortados); cronos (1/1 tramos, eventos cortados); abstract (1/1 tramos, eventos cortados); gensyn (1/1 tramos, eventos cortados). Ver la sección de cobertura.

## Respuesta corta

1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **$58.2 k** en 2,781 liquidaciones.
2. **¿Quién se lo lleva?** 107 liquidadores distintos; los 3 mayores se llevan **72%** del bono.
3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **1 bloques** (2 s) desde la última actualización del oráculo; **32%** en el mismo bloque.
4. **¿Qué porcentaje dejó al builder?** En L2 no hay builder; la propina de prioridad fue: arc —, hemi —, kaia 0%, katana 0%, megaeth 0%, morph —, optimism —, plume 0%, polygon 14%, robinhood 0%, unichain —, worldchain 0%.
5. **¿Cuánto se queda realmente el ganador?** En las 1,505 liquidaciones rastreables (54% del total): bono $913, el ganador se quedó **$633 (69%)** (de eso $0 lo mandó a su tesorería); a subastas de oráculo/OEV $0 (0%), al builder en directo $0, en propina $53, gas base $2, resto (deslizamiento, comisiones) $226. Fuera de la cuenta: sin medir 1,272 liq. ($57.1 k), sin rastro 2 ($243), refinanciaciones 2 ($1).

## ¿A dónde se va el bono?

Solo liquidaciones rastreables (todos los movimientos de tokens y ETH valuados). Cada contraparte que solo recibe se clasifica: builder del bloque, subasta compartida (OEV: la usan 2 o más liquidadores o es una subasta conocida) o tesorería del mismo bot (cuenta como del ganador). Lo que va a contrapartes que devuelven algo (swaps, préstamos) queda en Resto: deslizamiento y comisiones. "Sin rastro": ni el ganador ni un sumidero se quedaron con el bono. "Refinanciación": el colateral volvió al protocolo en la misma tx (no es dinero que se mueva).

| Cadena | Protocolo | Rastreables | Bono | Ganador | % | (tesorería) | OEV | Builder directo | Propina | Gas base | Resto | Sin medir · sin rastro · refin. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| arc | morpho | 0/5 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 5 ($0) · 0 ($0) · 0 ($0) |
| hemi | morpho | 0/3 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 3 ($0) · 0 ($0) · 0 ($0) |
| kaia | morpho | 0/1 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 1 ($2) · 0 ($0) · 0 ($0) |
| katana | morpho | 17/17 | $7 | $8 | 113% | $0 | $0 | $0 | $0 | $0 | -$1 | 0 ($0) · 0 ($0) · 0 ($0) |
| megaeth | morpho | 1/1 | $6 | $7 | 111% | $0 | $0 | $0 | $0 | $0 | -$1 | 0 ($0) · 0 ($0) · 0 ($0) |
| morph | morpho | 0/1 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 1 ($0) · 0 ($0) · 0 ($0) |
| optimism | morpho | 1/1 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 0 ($0) · 0 ($0) · 0 ($0) |
| plume | morpho | 486/745 | $28 | $24 | 86% | $0 | $0 | $0 | $0 | $1 | $2 | 259 ($1) · 0 ($0) · 0 ($0) |
| polygon | morpho | 3/34 | $47 | $12 | 26% | $0 | $0 | $0 | $49 | $0 | -$15 | 29 ($58) · 2 ($243) · 0 ($0) |
| robinhood | morpho | 0/292 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 290 ($56.7 k) · 0 ($0) · 2 ($1) |
| unichain | morpho | 2/2 | $0 | $0 | — | $0 | $0 | $0 | $0 | $0 | $0 | 0 ($0) · 0 ($0) · 0 ($0) |
| worldchain | morpho | 995/1679 | $826 | $582 | 70% | $0 | $0 | $0 | $4 | $0 | $240 | 684 ($317) · 0 ($0) · 0 ($0) |

## Por cadena y protocolo

| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| arc | morpho | 5 | $0 | 4 | 100% | 21 · 21 · 21 | 11 | 0% | n/a |
| hemi | morpho | 3 | $0 | 1 | 0% | — · — · — | — | — | n/a |
| kaia | morpho | 1 | $2 | 1 | 100% | — · — · — | — | — | n/a |
| katana | morpho | 17 | $7 | 5 | 100% | 1 · 10,896 · 10,936 | 10,896 | 0% | n/a |
| megaeth | morpho | 1 | $6 | 1 | 100% | — · — · — | — | — | n/a |
| morph | morpho | 1 | $0 | 1 | 100% | — · — · — | — | — | n/a |
| optimism | morpho | 1 | $0 | 1 | 100% | — · — · — | — | — | n/a |
| plume | morpho | 745 | $29 | 9 | 83% | — · — · — | — | — | n/a |
| polygon | morpho | 34 | $348 | 5 | 97% | — · — · — | — | — | n/a |
| robinhood | morpho | 292 | $56.7 k | 68 | 74% | 206,400 · 351,484 · 486,795 | 35,568 | 0% | n/a |
| unichain | morpho | 2 | $0 | 1 | 100% | — · — · — | — | — | n/a |
| worldchain | morpho | 1,679 | $1,142 | 16 | 93% | 0 · 1 · 2 | 2 | 33% | n/a |

## Subasta vs. directa

"Subasta": lo pagado a terceros en ETH más la propina es ≥ 30% del bono (subasta de oráculo, builder o guerra de prioridad). "Directa": el ganador no pagó por el orden. "Sin medir": faltaron trazas o precios.

| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arc | sin_medir | 5 | $0 | — | — | — | 4 | 21 |
| hemi | sin_medir | 3 | $0 | — | — | — | 1 | — |
| kaia | sin_medir | 1 | $2 | — | — | — | 1 | — |
| katana | directa | 17 | $7 | $8 | 113% | $0 | 5 | 10,896 |
| megaeth | directa | 1 | $6 | $7 | 111% | $7 | 1 | — |
| morph | sin_medir | 1 | $0 | — | — | — | 1 | — |
| optimism | directa | 1 | $0 | $0 | — | $0 | 1 | — |
| plume | directa | 486 | $28 | $24 | 86% | $0 | 9 | — |
| plume | sin_medir | 259 | $1 | — | — | — | 2 | — |
| polygon | directa | 2 | $0 | $0 | — | $0 | 2 | — |
| polygon | sin_medir | 29 | $58 | — | — | — | 2 | — |
| polygon | sin_rastro | 2 | $243 | — | — | — | 1 | — |
| polygon | subasta | 1 | $47 | $12 | 26% | $12 | 1 | — |
| robinhood | refinanciacion | 2 | $1 | — | — | — | 1 | — |
| robinhood | sin_medir | 290 | $56.7 k | — | — | — | 67 | 351,484 |
| unichain | directa | 2 | $0 | $0 | — | $0 | 1 | — |
| worldchain | directa | 995 | $826 | $582 | 70% | $0 | 15 | 1 |
| worldchain | sin_medir | 684 | $317 | — | — | — | 10 | 1 |

## ¿Queda margen para un actor pequeño?

Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.

| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |
|---|---:|---|---:|---|---|---:|---:|---:|
| arc | 30.0 | 0 / 0 / 5 | $0 | 0 · $0 · — | 0 · $0 · — | 0 | — | — |
| hemi | 30.0 | 0 / 0 / 3 | $0 | 0 · $0 · — | 0 · $0 · — | 0 | — | — |
| kaia | 30.0 | 0 / 0 / 1 | $0 | 0 · $0 · — | 0 · $0 · — | 0 | — | — |
| katana | 30.0 | 17 / 17 / 17 | $8 | 0 · $0 · — | 0 · $0 · — | 5 | 10,896 | 60% |
| megaeth | 30.0 | 1 / 1 / 1 | $7 | 0 · $0 · — | 0 · $0 · — | 1 | — | — |
| morph | 30.0 | 0 / 0 / 1 | $0 | 0 · $0 · — | 0 · $0 · — | 0 | — | — |
| optimism | 30.0 | 1 / 1 / 1 | $0 | 0 · $0 · — | 0 · $0 · — | 1 | — | — |
| plume | 30.0 | 486 / 486 / 745 | $24 | 0 · $0 · — | 0 · $0 · — | 9 | — | — |
| polygon | 30.0 | 2 / 3 / 34 | $0 | 0 · $0 · — | 0 · $0 · — | 2 | — | — |
| robinhood | 30.0 | 0 / 0 / 292 | $0 | 0 · $0 · — | 0 · $0 · — | 0 | — | — |
| unichain | 30.0 | 2 / 2 / 2 | $0 | 0 · $0 · — | 0 · $0 · — | 1 | — | — |
| worldchain | 30.0 | 995 / 995 / 1679 | $582 | 16 · $470 · 60% | 1 · $104 · 100% | 15 | 1 | 39% |

"top": parte del neto que se llevó el mayor ganador de ese grupo. "≥ 2 bloques": liquidaciones que llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).

### Bots que ganan por fuera de subastas

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| worldchain | `0x352109400458bf3e951f3147c71bec5845b1ee3c` | 1 | 89 | $532 | $404 | 76% | $0 | 0 | 16 | Morpho WLD/USDC lltv 77.0% (79); Morpho WBTC/USDC lltv 86.0% (7); Morpho WETH/USDC lltv 86.0% (3) |
| worldchain | `0xf8e00ed238692b5f5b2a05a5d4b6672272e396a9` | 4 | 23 | $121 | $106 | 88% | $0 | 0 | 3 | Morpho WLD/USDC lltv 77.0% (18); Morpho WBTC/USDC lltv 86.0% (3); Morpho WETH/USDC lltv 86.0% (2) |
| worldchain | `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | 2 | 24 | $105 | $29 | 28% | $0 | 0 | 4 | Morpho WLD/USDC lltv 77.0% (19); Morpho WBTC/USDC lltv 86.0% (5) |
| worldchain | `0x5fd52383db85758d9bec63f5a40c7f0bcbc9dc80` | 5 | 451 | $49 | $28 | 56% | $0 | 2 | 16 | Morpho WLD/USDC lltv 77.0% (336); Morpho WBTC/WLD lltv 86.0% (46); Morpho WETH/WLD lltv 86.0% (36) |
| plume | `0x72497cfe78eedbc9d9f73510b72c9c2199b2a09e` | 1 | 8 | $18 | $17 | 94% | $0 | — | 6 | Morpho nALPHA/pUSD lltv 91.5% (5); Morpho nCREDIT/pUSD lltv 91.5% (2); Morpho nTBILL/pUSD lltv 91.5% (1) |
| worldchain | `0xb3044425cc1f75f05b35ab53611f4b325aafbb36` | 4 | 4 | $8 | $7 | 93% | $0 | 0 | 2 | Morpho WBTC/USDC lltv 86.0% (2); Morpho WLD/USDC lltv 77.0% (2) |
| megaeth | `0xb10ff755b35db703d2c2a4c2632015254dfa73e1` | 1 | 1 | $6 | $7 | 111% | $7 | — | 1 | Morpho wiTRY/USDm lltv 77.0% (1) |
| katana | `0xfbf7559998b9a2b3ec8621ee9e48e2a36b7ce6ba` | 9 | 9 | $6 | $5 | 89% | $0 | 1 | 6 | Morpho LBTC/vbWBTC lltv 91.5% (7); Morpho wstETH/vbETH lltv 94.5% (1); Morpho KAT/vbUSDC lltv 62.5% (1) |
| worldchain | `0x3439682f62c7ffc1ecf95dc48b2a893f340a64c1` | 4 | 177 | $4 | $4 | 94% | $0 | 0 | 17 | Morpho WLD/USDC lltv 77.0% (177) |
| katana | `0xcbe3ad3bd665871eadbbf85ca94d2d7e2b32a66d` | 1 | 1 | $1 | $2 | — | $2 | 1 | 1 | Morpho avKAT/vbUSDC lltv 62.5% (1) |
| plume | `0xcbe3ad3bd665871eadbbf85ca94d2d7e2b32a66d` | 1 | 10 | $2 | $2 | 97% | $0 | — | 6 | Morpho WETH/pUSD lltv 86.0% (8); Morpho nALPHA/pUSD lltv 91.5% (2) |
| plume | `0xd720c8dd1c9b98d232350cc8e97bd2d8d05a7fc7` | 1 | 136 | $2 | $2 | 86% | $0 | — | 6 | Morpho nALPHA/pUSD lltv 91.5% (68); Morpho nCREDIT/pUSD lltv 86.0% (36); Morpho nTBILL/pUSD lltv 91.5% (20) |
| plume | `0x199a4c6cc0d901b036163fac90ef6a5eda9be8d1` | 4 | 263 | $3 | $2 | 52% | $0 | — | 17 | Morpho WETH/pUSD lltv 86.0% (182); Morpho nALPHA/pUSD lltv 91.5% (81) |
| worldchain | `0xe81073d32b7c85624dfb9a0420385a9a8860f3a6` | 1 | 2 | $2 | $1 | 72% | $1 | 2 | 2 | Morpho WBTC/WLD lltv 86.0% (1); Morpho WLD/USDC lltv 77.0% (1) |
| plume | `0xaba996f3f6170a85a31d7f8f4b54816e141278f8` | 1 | 45 | $1 | $1 | 88% | $0 | — | 3 | Morpho nALPHA/pUSD lltv 91.5% (45) |
| worldchain | `0x5f17a8598b72f6788dc8711f33a3d0a24f8e60bd` | 1 | 69 | $1 | $1 | — | $0 | 1 | 12 | Morpho WLD/USDC lltv 77.0% (49); Morpho WETH/WLD lltv 86.0% (12); Morpho WBTC/WLD lltv 86.0% (6) |
| worldchain | `0xcbe3ad3bd665871eadbbf85ca94d2d7e2b32a66d` | 1 | 6 | $3 | $1 | 18% | $0 | 1 | 5 | Morpho WLD/USDC lltv 77.0% (3); Morpho WBTC/WLD lltv 86.0% (3) |
| plume | `0x087fc07f6b3c396dc75dfb14360c6a7012b0ee92` | 1 | 2 | $1 | $1 | 51% | $0 | — | 2 | Morpho nALPHA/pUSD lltv 91.5% (2) |
| worldchain | `0x00751dde4231e5abdb569eb182b249628c085bec` | 1 | 17 | $1 | $1 | — | $0 | 0 | 10 | Morpho WLD/USDC lltv 77.0% (15); Morpho WETH/WLD lltv 86.0% (1); Morpho WBTC/WLD lltv 86.0% (1) |
| katana | `0xe29b7303937fac8f7f24670c7cc08005ac14ebe9` | 1 | 3 | $0 | $0 | — | $0 | 10,936 | 1 | Morpho yvvbUSDT/dUSD lltv 86.0% (3) |

### Contratos que pagan por el orden (subastas)

| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| polygon | `0xc14e…7d98` | 1 | 1 | $47 | $12 | 26% | $49 | — |

### ¿A quién va el ETH que sale del liquidador?

"compartido": cobra de 2 o más liquidadores (subasta). "swap": devolvió tokens (pago de un swap con ETH nativo, p. ej. el PoolManager de Uniswap V4; no es OEV). "un_solo_liquidador": puede ser la tesorería del mismo bot.

| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |
|---|---|---|---:|---:|---:|---|

## Saturación de mercados

Vírgenes: **4** · disputados: **19** · muertos: **0** · con muestra insuficiente (<3): 34.

### Los 15 mercados que más dejaron a sus ganadores

| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| robinhood | Morpho wsNET/USDG lltv 62.5% | 202 | $46.4 k | $0 | — | 0 | 36 | 51% | — | disputada |
| robinhood | Morpho USDe/USDG lltv 91.5% | 36 | $6,598 | $0 | — | 0 | 10 | 99% | — | disputada |
| robinhood | Morpho PONS/USDG lltv 38.5% | 7 | $2,053 | $0 | — | 0 | 6 | 44% | 247,395 | disputada |
| robinhood | Morpho USDe/USDG lltv 91.5% | 1 | $600 | $0 | — | 0 | 1 | 100% | — | muestra_insuficiente |
| robinhood | Morpho Index/USDG lltv 38.5% | 8 | $398 | $0 | — | 0 | 7 | 58% | 473,978 | disputada |
| worldchain | Morpho WLD/USDC lltv 77.0% | 1424 | $536 | $348 | 95% | 821 | 16 | 73% | 1 | disputada |
| robinhood | Morpho DELTA/USDG lltv 38.5% | 2 | $260 | $0 | — | 0 | 2 | 100% | 452,578 | muestra_insuficiente |
| robinhood | Morpho PONS/USDG lltv 62.5% | 6 | $242 | $0 | — | 0 | 2 | 97% | — | disputada |
| polygon | Morpho WBTC/USDC lltv 86.0% | 1 | $201 | $0 | — | 0 | 1 | 100% | — | muestra_insuficiente |
| worldchain | Morpho WBTC/USDC lltv 86.0% | 45 | $331 | $106 | 42% | 24 | 5 | 58% | 1 | disputada |
| worldchain | Morpho WETH/USDC lltv 86.0% | 56 | $222 | $99 | 63% | 41 | 7 | 76% | 1 | disputada |
| robinhood | Morpho STEERUV417/USDG lltv 38.5% | 1 | $69 | $0 | — | 0 | 1 | 100% | 578,483 | muestra_insuficiente |
| robinhood | Morpho CASHCAT/USDG lltv 62.5% | 3 | $54 | $0 | — | 0 | 2 | 100% | — | disputada |
| polygon | Morpho vDEMKAMALANO/USDC lltv 77.0% | 11 | $47 | $0 | — | 0 | 1 | 100% | — | virgen |
| worldchain | Morpho WBTC/WLD lltv 86.0% | 75 | $53 | $28 | 54% | 57 | 6 | 92% | 2 | disputada |

### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)

- polygon · Morpho vDEMKAMALANO/USDC lltv 77.0%: 11 liq., real $0, ganador 0x52a2…bab6
- katana · Morpho yvvbUSDT/dUSD lltv 86.0%: 3 liq., real $0, ganador 0xe29b…ebe9
- hemi · Morpho rETH/msETH lltv 91.5%: 3 liq., real $0, ganador —
- polygon · Morpho 0x357661f9/USDC lltv 62.5%: 17 liq., real -$0, ganador 0x9439…53d0

## Por tamaño del bono

| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |
|---|---:|---:|---:|---:|---:|---:|
| $0–$10 | 2,573 | $124 | $0 | 96% | 1,485 | 81 |
| $10–$100 | 89 | $306 | $12 | 60% | 17 | 22 |
| $100–$1,000 | 55 | $203 | $101 | 73% | 2 | 21 |
| $1,000–$10.0 k | 13 | $0 | — | — | 0 | 6 |
| ≥ $10.0 k | 0 | — | — | — | — | — |

## ¿Por dónde entran? (contrato llamado por la transacción)

Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, es una subasta o un enrutador compartido, no el bot de alguien.

| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |
|---|---|---:|---:|---:|---:|---:|---:|
| worldchain | `0x5fd5…dc80` | 785 | 5 | $49 | 56% | $0 | 0% |
| plume | `0x199a…e8d1` | 342 | 4 | $3 | 52% | $0 | 0% |
| plume | `0xd720…7fc7` | 316 | 1 | $3 | 86% | $0 | 0% |
| worldchain | `0x3439…64c1` | 289 | 4 | $9 | 94% | $0 | 0% |
| worldchain | `0x5f17…60bd` | 130 | 1 | $1 | — | $0 | 0% |
| worldchain | `0x3521…ee3c` | 126 | 1 | $753 | 76% | $0 | 0% |
| robinhood | `0x1977…8fa4` | 107 | 75 | $23.7 k | — | $0 | 0% |
| worldchain | `0xf8e0…96a9` | 99 | 4 | $202 | 88% | $0 | 0% |
| worldchain | `0x5ac9…95bd` | 71 | 3 | $106 | 28% | $0 | 0% |
| worldchain | `0xe741…f432` | 63 | 1 | $0 | — | $0 | 0% |
| plume | `0xaba9…78f8` | 45 | 1 | $1 | 88% | $0 | 0% |
| worldchain | `0x12b7…52f4` | 36 | 1 | $0 | — | $0 | 0% |
| robinhood | `0x085b…48c0` | 25 | 25 | $47 | — | $0 | 0% |
| robinhood | `0x7251…7cee` | 20 | 11 | $10.7 k | — | $0 | 0% |
| worldchain | `0x0075…5bec` | 20 | 1 | $1 | — | $0 | 0% |

## Ganadores principales (por bono)

- `0x3586aa1db9523bb223916b8ec0405261c8a625e1` — $23.7 k (41%)
- `0x72512e63c0c70797b96902228fa8acc1211b7cee` — $10.7 k (18%)
- `0x7961e142750f3b44bf8b844d433c387b8cbb316f` — $7,379 (13%)
- `0xad389f432f7ce2d3f2c57f0083915cf1f364af95` — $3,265 (6%)
- `0x5589d381e74e49eb15af6caf1920c0804c5e3653` — $1,905 (3%)
- `0x5820e320fd59b275f783ee7bded23fd05620a214` — $1,321 (2%)
- `0xf5623988974e9fd63be3b896c0e975f2ffd74f54` — $1,043 (2%)
- `0xd1cdc4027a3befc9f577768d121a265171338b42` — $950 (2%)
- `0x53a340f48e3a0b67adb76c892750586cd3a7ca50` — $905 (2%)
- `0xffc4eacab4c39145daca6961ceb72d91f28ecbac` — $826 (1%)

## Cobertura de la medición

| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| polygon | 1/1 | 30.0 | 34 | 34 | 5 (15%) | 0 (0%) | debug_traceTransaction: 34 | oráculo 0, mercado 68, sin 0 | 0 |
| optimism | 1/1 | 30.0 | 1 | 1 | 1 (100%) | 0 (0%) | debug_traceTransaction: 1 | oráculo 0, mercado 2, sin 0 | 0 |
| unichain | 1/1 | 30.0 | 2 | 2 | 2 (100%) | 0 (0%) | debug_traceTransaction: 2 | oráculo 0, mercado 4, sin 0 | 0 |
| katana | 1/1 | 30.0 | 17 | 17 | 17 (100%) | 5 (29%) | debug_traceTransaction: 17 | oráculo 0, mercado 34, sin 0 | 0 |
| hyperevm | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| worldchain | 1/1 | 30.0 | 1679 | 1635 | 995 (59%) | 1679 (100%) | blockscout: 1023, trace_transaction: 18 | oráculo 0, mercado 1617, sin 1103 | 0 |
| sonic | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| bsc | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| linea | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| scroll | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| sei | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| monad | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| celo | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| etherlink | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| hemi | 1/1 | 30.0 | 3 | 0 | 0 (0%) | 0 (0%) | blockscout: 3 | oráculo 0, mercado 3, sin 3 | 0 |
| ink | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| lisk | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| soneium | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| fraxtal | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| mode | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| plume | 1/1 | 30.0 | 745 | 745 | 486 (65%) | 0 (0%) | blockscout: 109, no_medido: 3 | oráculo 0, mercado 1119, sin 0 | 0 |
| corn | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| tac | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| flare | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| cronos | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| xdc | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| kaia | 1/1 | 30.0 | 1 | 1 | 0 (0%) | 0 (0%) | no_medido: 1 | oráculo 0, mercado 2, sin 0 | 0 |
| zerog | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| abstract | 1/1 | 0.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| morph | 1/1 | 30.0 | 1 | 1 | 0 (0%) | 0 (0%) | no_medido: 1 | oráculo 0, mercado 2, sin 0 | 0 |
| megaeth | 1/1 | 30.0 | 1 | 1 | 1 (100%) | 0 (0%) | debug_traceTransaction: 1 | oráculo 0, mercado 2, sin 0 | 0 |
| robinhood | 1/1 | 30.0 | 292 | 292 | 0 (0%) | 28 (10%) | no_medido: 246 | oráculo 0, mercado 537, sin 1 | 0 |
| stable | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| tempo | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| arc | 1/1 | 30.0 | 5 | 1 | 0 (0%) | 1 (20%) | no_medido: 1, sin_enriquecer: 3 | oráculo 0, mercado 2, sin 0 | 0 |
| bitlayer | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| gensyn | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |
| eden | 1/1 | 30.0 | 0 | 0 | 0 (—) | 0 (—) | — | oráculo 0, mercado 0, sin 0 | 0 |

Netos fuera de rango (no se cuentan como medidos; revisar a mano): robinhood `0xf9463d5df6be57e07ac2508a833ec0cc3520727154a0d0709670c5bfaec175cc` bono $425, neto $728 (USDG +727.924); robinhood `0xf62910ad45edc074b43080c9bbf6a639be73037383ed73a8392262717cdf3f87` bono $386, neto $627 (USDG +626.759); robinhood `0xc409c18338d1666ac1a5fd33b3729b1724afc9327d36217db7d3c3f10fe1db82` bono $300, neto $626 (USDG +910.72); robinhood `0x4258042324961a4f8ba803aeb56b3cf9f2d077fc5ffe1605282d41fe662181a4` bono $134, neto $175 (USDG +174.624); robinhood `0xc409c18338d1666ac1a5fd33b3729b1724afc9327d36217db7d3c3f10fe1db82` bono $133, neto $278 (USDG +910.72); robinhood `0x5ac61946b228e5a850062716c38a9ffa95fded9274ec32e3ea112b0ce2fb30b0` bono $99, neto $190 (USDG +253.91); robinhood `0x8872cd3629311652636010f432766472463c5a09c8bd9e3d54fc5eb118c68626` bono $74, neto $124 (USDG +124.06); robinhood `0x5362d77208452da536630212224d3895e60e608cc5018bee57c6d0cea7c4d824` bono $68, neto $119 (USDG +118.681).

Errores de trazas más comunes: worldchain: trace_transaction: failed to apply blockhash contract call: database error: Database error: state at block #3 (2039); worldchain: debug_traceTransaction: HTTP 401 en worldchain-mainnet.g.alchemy.com (7); worldchain: trace_transaction: HTTP 401 en worldchain-mainnet.g.alchemy.com (5); worldchain: debug_traceTransaction: Invalid method debug_traceTransaction (3); plume: debug_traceTransaction: HTTP 401 en rpc.plume.org (20); plume: trace_transaction: HTTP 401 en rpc.plume.org (16); robinhood: trace_transaction: trace_transaction is not available without an API key on this endpoint (standard eth_/net_ (12); robinhood: debug_traceTransaction: the network is busy, please try again in a moment (11).

## Qué NO dice este census

- "Se queda" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que ganarles la carrera o la subasta.
- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se ve como pago a terceros y sale menor (y la liquidación puede clasificarse como "subasta").
- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye el deslizamiento de vender el colateral.
- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost (Arbitrum) se pagan por fuera de la transacción y no se ven aquí.
- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).
- No reconcilia todas las posiciones del alcance (puerta "cobertura del mercado" de Omega): solo mide las liquidaciones que sí ocurrieron.
- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.
