# Economía comparable y límites

Se trabaja en enteros base-unit, sin sumar activos ni cadenas. Fechas de fuentes, hashes y unidades están en el ledger. `comparison_audit.py` reutiliza `economic_ledger.py`, `case_b_route_audit.py` y `monthly_census.py`, preservados en la rama base. La ausencia de un coste se conserva como desconocido. Un saldo preexistente, préstamo o depósito de fixture no es ingreso incremental.

## Partidas y responsables

| Partida | Aave/SVR | Robinhood | Morpho Ethereum |
|---|---|---|---|
| Prestamista/protocolo: principal y devolución | Incluidos en excedente local reportado; no replay nuevo | Deuda 194.034131 USDG en ruta histórica simulada | 26.039738525656992415 WETH repagados por tercero |
| Protocolo: colateral | Contabilizado en ensayo histórico fijo | wsNET→sNET→NET→USDG | 24.343983926960874121 ezETH |
| DEX: salida después de fees/impacto | Excedente ya neto flash/swap | Tributo NET raw 15442822 incorporado; USDG bruto residual 32060665 | Fluid paga 26.409680973611 ETH |
| NQC: capital inicial aportado | Exigido cero; ejecución financiada no probada | Exigido cero; fixtures no son capital externo real | Exigido cero; saldo del tercero no disponible a NQC |
| Sponsor: anticipo/reserva nativa | Positiva a fee cap, no comprometida | 0.1 ETH depósito + 0.01 ETH bundler de fixture | No comprometido |
| Arranque: creación/adaptadores/permisos | CREATE local incluida; ruta actual no válida | Despliegue excluido | C1 despliegue pendiente; C2 ruta/adaptadores pendientes |
| Proponente/builder/bundler | Puja/beneficiario real pendientes | Cobro a beneficiario fixture, propiedad separada | Coinbase 0.368092735714237547 ETH; atribución builder pendiente |
| Fallo incluido, top-up, parcial | Pérdida completa pendiente | Gas y paymaster cobrados en fallo | Sensibilidad de anticipo separado, no acuerdo |
| Stake, servicios y deuda contingente | DESCONOCIDO | DESCONOCIDO fuera de controles | DESCONOCIDO |
| Activos finales propios NQC y pasivos | Sin evidencia realizada | Sin evidencia realizada | Sin evidencia realizada |

No se restan de nuevo fees/slippage que ya están incluidos en la salida DEX. En Robinhood, la dirección del USDG y sus seis decimales se fijan en las fuentes de ruta; no se valora automáticamente a US$1. Falta conversión ejecutable a ETH/USD y derechos económicos. Tampoco se consolida el gas del pagador con el cobro del paymaster sin demostrar titularidad; véase [auditoría](SPONSORSHIP_REALITY_AUDIT.md).

## Aave/SVR: saldo previo no reemplazable por beneficio futuro

La fuente original, blob `129c1bef538c2a459a1a9d393efa837d698bb965`, limita bloque, hash padre y excedente exacto. El gate reejecutado devuelve `BLOCKED_NOT_A_PRODUCTION_SVR_BID_EXECUTOR`. La cifra **2273.989378 USDC** y gas local **3914680**, límite **5089056**, describen un ensayo histórico. No se ejecutó nuevamente su EVM.

Para EOA con cero ETH, el déficit previo `max(0, gasLimit×maxFee + value - balance)` resulta:

| maxFee hipotética, gwei | Anticipo mínimo ETH a fee cap | Comprometido por tercero |
|---:|---:|---|
| 3 | 0.015267168 | DESCONOCIDO |
| 10 | 0.050890560 | DESCONOCIDO |
| 35 | 0.178116960 | DESCONOCIDO |

Es reserva, no gas necesariamente consumido. Las tres sensibilidades heredadas usan ETH=US$2500 **ilustrativo**, no precio histórico verificado, y omiten costes desconocidos. Sus residuales positivos no acreditan G0/G2/G4. La puja competitiva no se deduce de cuánto excedente queda.

## Caso B: cota del tercero, no P&L de NQC

Ethereum 26190955/índice 1; tercero `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`.

| Movimiento | Importe ETH-equivalente salvo activo indicado |
|---|---:|
| Fluid ETH menos deuda WETH, envoltura nominal 1:1 | 0.369942447954007585 |
| Coinbase | −0.368092735714237547 |
| Residual incremental antes de gas | 0.001849712239770038 |
| Gas observado: 745509 × 266148625 wei | −0.000198416195275125 |
| Cota después de costes conocidos | **0.001651296044494913** |
| WETH previo del ejecutor, excluido del ingreso | 0.006392502690919791 WETH |

La equivalencia ETH/WETH no convierte propiedad separada ni financiación desconocida en beneficio. El estado y la conversión contrafactual NQC siguen sin reproducirse. No se certifica el P&L consolidado del tercero.

Manteniendo conversión, deuda, coinbase y gas usado, el máximo precio entero que deja resultado estrictamente positivo es **2481140052 wei/gas**; la prueba existente verifica también el siguiente wei. A 1 gwei quedan 0.001104203239770038 ETH; a **3 gwei: −0.000386814760229962 ETH**; a 5: −0.001877832760229962; a 10: −0.005605377760229962. Son sensibilidades antes de obligaciones desconocidas. Reducir coinbase alteraría la hipótesis competitiva y no demuestra inclusión.

## C1 contra C2: ventaja de liquidez, no superioridad económica acreditada

C1 recibe colateral durante `onMorphoLiquidate`, lo convierte y permite cobrar la deuda al terminar: no necesita que Morpho adelante WETH en ese caso. C2 toma primero flash; necesita cash agregado suficiente del token en Morpho, además del flujo de repago. En el ensayo de 8 WETH, faltar un wei revierte. Ambas necesitan colateral/DEX ejecutables y gas financiado. La arquitectura C1 no elimina el riesgo de conversión ni costes.

Los 516339 gas C1 frente a 400205 C2 son mediciones **brutas locales** de llamadas en entorno preparado, excluyendo intrinsic/calldata, despliegue, financiación y Fluid real. No se extrapolan a producción ni se asume C2 utilizable por ser contratos desplegados: Bundler3 está deprecado y hay que validar compatibilidad/mantenimiento/adaptadores. No se escribieron nuevos ejecutores porque no cerrarían financiación ni preestado.

El control V2 original conserva reservas 1000/900 y repago 8 WETH: salida 8.249365645570551238, margen 0.249365645570551238. Con ese precio coherente con oráculo, aun profundidad infinita limita el margen a aproximadamente 0.325678496868 WETH: el presupuesto 0.5 ETH queda **REFUTADO para ese escenario**.

## Censo y recurrencia

Selección congelada el 17/oct/2026 04:46:42.618444 UTC, fin exclusivo 17/oct/2026 00:00 UTC. Ventana 30 días: [17/sep,17/oct); ventana 7 días: [10/oct,17/oct). Cadena 1, todos los eventos Liquidation devueltos por la API, sin filtro de activo o beneficio. Paginación hacia ambos sentidos y consulta 7d coinciden; no hay prueba independiente de cobertura total de cadena. Las ventanas se solapan.

`comparison.json` conserva clasificación individual de **143 eventos / 141 transacciones**; 7d tiene 29/28. Hay 43 eventos con bad debt y 15 activos de deuda; 7 eventos con deuda WETH no significan 7 oportunidades compatibles. Estados por transacción:

| Etapa | Resultado |
|---|---|
| Observada/parseada como registro API | 141 |
| Recibo cruzado RPC/API | 1 (B); 22 no disponibles; 118 no solicitados |
| Primera barrera no superada | Replay auténtico propio: 141 |
| Compatibles / evaluables / financiables / capturables | DESCONOCIDO en cada etapa, no conteo cero de oportunidades reales |
| Económicamente admitidas por evidencia disponible | 0 |
| Capturadas por NQC | 0 |

No hay probabilidades de ganar, intentos perdidos ni distribución de márgenes completos. Las direcciones de liquidadores no identifican personas ni pujas perdedoras. RMC016, Census V2 y T36/T37/T38 son poblaciones/certificaciones distintas; no se suman a este censo.

## Sensibilidad mensual — no pronóstico

Se reutiliza `required_wins`: `ceil((T+F)/m)`, donde m es margen USD realmente neto por victoria, F costes fijos. Tabla con **m hipotético y F=0 solamente como cota inferior de requisitos**, no presupuesto medido. Fallos deben estar incluidos en m o agregarse por separado.

| Objetivo neto mensual | m=US$10 | m=US$50 | m=US$100 | m=US$500 |
|---:|---:|---:|---:|---:|
| US$1000 | 100 | 20 | 10 | 2 |
| US$5000 | 500 | 100 | 50 | 10 |
| US$10000 | 1000 | 200 | 100 | 20 |
| US$50000 | 5000 | 1000 | 500 | 100 |

Son victorias netas necesarias, no cantidad de señales ni tasa de captura asumida. Para el primer mes debe añadirse despliegue/onboarding/servicios y toda pérdida no incluida; depósito, stake y reserva deben estar disponibles **antes** del intento aunque no sean gasto definitivo. No se amortizan para ocultar capital inicial. Sin m observado y financiación, ninguna fila es expectativa defendible.

Categorías: **A** ingreso propio certificado US$0; **B** cero replays propios positivos económicamente admitidos (Robinhood tiene contrafactual condicionado, no cambia ese conteo); **C** sensibilidades explícitas; **D** expectativa mensual **NO ESTIMABLE**.
