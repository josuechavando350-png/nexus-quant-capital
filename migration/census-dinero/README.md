# Census del dinero

Responde las cuatro preguntas del Census de Sovereign Radar Omega (cap. 5) y la
métrica de saturación del Miner (componente 7), con datos reales:

1. ¿Cuánto dinero pagan las liquidaciones?
2. ¿Quién se lo lleva?
3. ¿En cuántos bloques después de la actualización del oráculo?
4. ¿Cuánto se queda el builder y cuánto le queda al ganador?

Alcance: Aave V3 (core, Lido, EtherFi en Ethereum; Base; Arbitrum) y Morpho Blue
(Ethereum, Base, Arbitrum). Direcciones verificadas en `census_dinero/config.py`.

## Qué mide por liquidación

| Campo | Cómo se obtiene |
|---|---|
| Bono USD | Aave: colateral recibido − deuda pagada, con el precio del oráculo de Aave en ese bloque. Morpho: deuda pagada × (LIF − 1), con LIF = min(1.15, 1/(1 − 0.3·(1 − LLTV))). Si no hay nodo de archivo, precio de mercado de DefiLlama. |
| Ganador | Campo `liquidator` / `caller` del evento, más el EOA que firmó. |
| Bloques desde oráculo | Última `AnswerUpdated` / `NewTransmission` de los feeds detrás de la fuente de precio del activo (proxy de Chainlink, adaptadores CAPO, feeds del oráculo de Morpho). |
| Pago al builder | Propina de prioridad + ETH/WETH enviado directo al coinbase (callTracer, trace_transaction o Blockscout). Solo Ethereum tiene subasta de builders. |
| Neto del ganador | Bono − gas total − pagos directos. No descuenta el deslizamiento al vender el colateral. |

Por mercado agrega bono, neto, ganadores únicos, participación del mayor,
mediana de bloques y de propina, y lo clasifica como virgen, disputado o muerto
con los umbrales iniciales de `config.Thresholds`.

## Cómo se corre

Se ejecuta en GitHub Actions al empujar un cambio de `run.json` en la rama
`feat/census-dinero-20261024`. Cada cadena corre en su propio job y publica en la
rama `census-dinero/resultados`; el reporte final queda en `ultimo/RESUMEN.md` y
en el resumen de la corrida de Actions.

Usa RPC públicos por defecto. Si existen los secrets `NQC_CENSUS_RPC_ETHEREUM`,
`NQC_CENSUS_RPC_BASE` y `NQC_CENSUS_RPC_ARBITRUM` (URLs separadas por coma), se
prueban primero.

Local, sin red:

```
cd migration/census-dinero
python3 -m unittest discover -s tests
python3 check_isolation.py
```

Solo librería estándar de Python. Los únicos métodos RPC permitidos son de
lectura (`rpc.ALLOWED_METHODS`); cualquier método de firma o envío se rechaza.
