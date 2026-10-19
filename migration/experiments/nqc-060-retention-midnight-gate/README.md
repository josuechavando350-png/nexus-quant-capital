# NQC060 — Retención económica: Morpho Midnight en Ethereum

**Resultado: nueva hipótesis documentada, NO nueva mina rentable acreditada.** Se conservan NQC054–059 y el `commercial_admission=false`. Se investiga cómo evitar rutas cuya puja consume casi todo el margen, sin suponer que las minas nuevas tienen menos competidores.

## Descubrimiento con valor informativo

Las [fuentes oficiales de Morpho](https://morpho.org/blog/the-morpho-effect-september-2026) informan que **Morpho Midnight opera en Ethereum** (además de otras cadenas). A diferencia de las liquidaciones solo por caídas de precio, Midnight permite liquidar **cualquier deuda pendiente después de vencer**, aunque la posición estuviera sana antes, según [la documentación oficial](https://docs.morpho.org/learn/concepts/midnight/liquidations/). El incentivo de liquidación (`LIF`) aumenta durante los 60 minutos posteriores al vencimiento; **no** significa que exista margen neto positivo en esos 60 minutos, ni que se haya medido la curva exacta en un contrato concreto. Antes o al instante exacto del vencimiento, la ruta *post-maturity* no es elegible.

Según [la documentación del contrato Midnight](https://docs.morpho.org/developers/contracts/midnight/), en la opción con callback los activos incautados se envían al `receiver`, se invoca `onLiquidate`, y después se cobran los tokens de deuda al callback. **Hipótesis NQC:** recibir colateral, venderlo atómicamente y devolver la deuda, con patrocinio adicional del gas; la opción no garantiza liquidez, ruta real, cobertura de CREATE ni una financiación aceptada. Revisar también `liquidatorGate`, que puede restringir el acceso.

**Advertencia competitiva:** [Morpho ya publica un bot de liquidaciones Midnight](https://github.com/morpho-org/morpho-bots/blob/main/bots/midnight-liquidation/README.md) compatible con Ethereum y Base. No sabemos cuántos competidores operan realmente ni cuánto ofrecen. **No se demuestra que sea una mina menos competida.** Se prioriza para *investigar* por ser un mecanismo diferente y documentado en la cadena 1, no por expectativa monetaria.

La documentación antigua de un SDK aún dice que Midnight es Base-only; prevalecen para alcance de investigación las fuentes más recientes que anuncian Ethereum, la documentación de contratos y el bot oficial. **No se adquirió código canónico ni estado de mercado de un bloque concreto**.

## Resultados de selección

| Ruta | Condición relevante | Resultado NQC hoy |
|---|---|---|
| Midnight vencimiento, Ethereum 1 | Otra causa de liquidación, callback con colateral antes de repago, gas aún externo | **GO investigación**, utilidad y competencia **UNKNOWN** |
| Morpho Blue, Ethereum 1 | Callback de NQC conocido; caso B muestra puja severa | Conservar como referencia; beneficio NQC **UNKNOWN** |
| Aave Ethereum con SVR | Subastas explícitas muy disputadas; LlamaRisk reportó 93 ganadores distintos hasta marzo 2026 | Despriorizar primer experimento, no afirmar que es imposible |
| Aave SVR Atlas, Base/Arbitrum | Estudio de gobernanza documenta depósito de gas en token nativo de solvers | Incompatible con política **sin fondos/bond** salvo un tercero verificable |

Fuente [LlamaRisk en gobernanza de Aave, marzo 2026](https://governance.aave.com/t/arfc-aave-chainlink-svr-multi-network-expansion-base-arbitrum/24241): 93 ganadores distintos históricos de SVR y alrededor de 53% de recaptura media de OEV en su desglose. **No son métricas de competidores en Morpho Midnight**. Otro dato de esa fuente: en Atlas los solvers aportan un depósito nativo para gas, incluso cuando una operación puede fallar.

## ¿Qué construimos?

`retention.py` es un filtro estrictamente **offline**: examina la elegibilidad *post-maturity* en Ethereum, estado de la puerta de liquidación, deuda pendiente y cotas conservadoras de venta y obligaciones **en unidades enteras del mismo token de préstamo**. Descarta solo cuando la cota superior de una ruta ya es no positiva tras costes monetarios mínimos identificados. No convierte ETH gas en WETH o USDC, no inventa una oferta de sponsor, no considera ganancia una cota superior positiva y nunca habilita ejecución comercial.

Si un caso trae un importe de venta sin incluir fees de ruta, se rechaza su entrada: se exige importe **neto ya descontando comisiones de swap**, para evitar doble resta. Los pagos al builder y sponsor no se contabilizan como cero; si siguen desconocidos, `UNKNOWN` permanece. Las pruebas de código usan situaciones **SINTÉTICAS**, no oportunidades observadas.

### Regresión contra Morpho B (NQC054)

NQC054 registró un margen venta menos deuda de **0.369942447954007585 ETH** con transferencia a coinbase de **0.368092735714237547 ETH** (≈ **99.5%** de ese margen) y gas de **0.000198416195275125 ETH**. Residuo limitado antes de otras obligaciones: **0.001651296044494913 ETH**. Financiar íntegramente la deuda con prima de 1 bp dejaría **−0.0009526778080707862415 ETH** bajo condiciones idénticas de puja/venta/gas. **No invalida colateral primero C1**. Son datos heredados y la prueba local solo confirma aritmética, no autentica otra vez el preestado/recibo.

## Adquisición y parada

La [API pública documentada de Midnight](https://docs.morpho.org/developers/api/morpho-midnight/) permitiría enumerar mercados y posiciones de Ethereum, pero **una única lectura pública desde este entorno resultó inaccesible**; no hubo reintento ni uso de otro proveedor. No tenemos un borrower verificablemente vencido, saldo de deuda autenticado, precio de venta ejecutable ni fees aplicables. Identificar el endpoint no equivale a adquirir datos o tener proveedor autorizado.

**Para avanzar** hace falta un expediente completo y permitido: mercado desplegado y `liquidatorGate`, maturity, borrower con deuda estrictamente posterior al vencimiento, LIF real, colateral entregado, venta efectiva, fees, repago, gas/sponsor, bids, cuentas beneficiarias y evidencia competitiva. Solo cuando exista conviene una simulación EVM y después Shadow prospectivo autorizado. Si ese expediente no es accesible con los recursos y permisos existentes, suspender hipótesis sin generar infraestructura adicional.

**Titan:** financiación automática documentada para ciertos bundles en Ethereum, no demostrada para la ruta Midnight/CREATE, ni para operaciones SVR ni ausencia de recurso personal. Titan no ha comprometido fondos para NQC. No confundir el hecho de usar la cadena correcta con aceptación del paquete concreto.

## Validación, permisos y trazabilidad

Se ejecutaron **15 pruebas Python locales** en Python 3.13.5, todas PASS tras corregir un número esperado en el test de prima de 1 bp (sin alterar datos fuente); un intento inicial tuvo ese test fallido, conservado conceptualmente en `STATUS.json`. Se reprodujo el resultado de Morpho B y se probaron casos de madurez estricta, puertas, valores desconocidos, cotas negativas, entrada sin fees netos, activos y cadenas incompatibles, y no reconocimiento indebido de ingresos.

**No ejecutados:** verificador de aislamiento original y regresiones integrales NQC055-059 porque el checkout completo de GitHub no estaba accesible desde el entorno local (falló la resolución DNS); tampoco se ejecutaron EVM replays, RPC, firma, bundles, despliegues o trading. Publicación solo añade archivos nuevos dentro de `migration/experiments/nqc-060-retention-midnight-gate/`; no modifica main ni experimentos previos.

Las metas netas mensuales USD 5k–45k siguen **NO ESTIMABLES**. NQC no tiene ningún beneficio capturado demostrado ni patrocinador comprometido. Mantener presupuesto de gas propio futuro con tope de 2,000 MXN solo después de Canary autorizada; Census y Shadow con cero fondos; Triport 0/8 conocido, inaccesible hasta acreditar controles.

**Decisión:** GO para investigación documental acotada; UNKNOWN para rentabilidad y financiación; NO-GO para ejecución real.
