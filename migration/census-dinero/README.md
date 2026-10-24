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
| Se queda realmente | Todos los movimientos de tokens y ETH que entran o salen del liquidador (firmante, contrato y cuentas sin código que en esa tx solo tratan con ellos) valuados a mercado, menos gas. Ya descuenta venta del colateral, flash loans, subastas de oráculo y builder. |
| Ruta | `subasta` si lo pagado a terceros en ETH más la propina es ≥ 30% del bono; `directa` si no; `sin_medir` si faltaron trazas o precios, o si el neto quedó fuera de [−(bono + gas + 25%), bono + 25%] (`realized_anomaly`). |
| Contrato de entrada | Si la tx llama a un contrato distinto del liquidador: `compartida` (subasta conocida o usado por ≥ 2 liquidadores; su saldo es de terceros) o `propia` (un solo liquidador; su saldo cuenta como del ganador). |

Por mercado agrega bono, neto, ganadores únicos, participación del mayor,
mediana de bloques y de propina, y lo clasifica como virgen, disputado o muerto
con los umbrales iniciales de `config.Thresholds`.

## Cómo se corre

Se ejecuta en GitHub Actions al empujar un cambio de `run.json` en la rama
`feat/census-dinero-20261024` (una corrida nueva cancela la que esté en curso).

`run.json` fija la ventana (`days`, `end_utc`) y en cuántos **tramos** se parte cada
cadena (`tramos`). El job `plan` reparte la ventana por timestamp: cada tramo cubre
los bloques con `inicio <= timestamp < fin`, sin huecos ni solapes, y corre en su
propio job (máximo 20 a la vez, 350 min cada uno). El job `report` junta los tramos,
deduplica y publica en la rama `census-dinero/resultados`:
`corridas/<run>/<cadena>/<tramo>/{log.txt,meta.json,liquidaciones.jsonl}` y el
reporte en `corridas/<run>/reporte/` y `ultimo/RESUMEN.md`.

Antes de recolectar, cada tramo corre una **sonda** de proveedores (`sonda.py`):
latencia, rango máximo de `eth_getLogs`, si responde `eth_call` en el bloque más
viejo (nodo de archivo) y si traza transacciones viejas. Con eso cada método va
solo a quien lo sirve. El resultado queda en `meta.json` (`sonda`,
`rpc_providers`, `phases_s` con el tiempo de cada fase, `trace_errors`).

Usa RPC públicos por defecto. Si existen los secrets `NQC_CENSUS_RPC_ETHEREUM`,
`NQC_CENSUS_RPC_BASE` y `NQC_CENSUS_RPC_ARBITRUM` (URLs separadas por coma), se
prueban junto con los públicos. Sus URLs nunca se escriben en los resultados:
aparecen como `secretoN (dominio)`.

Cada tramo guarda además `evidencia.json`: tx, recibo, traza y código de las cuentas de
una muestra de 5 transacciones. El job `report` corre `verificar`, que recalcula esas
transacciones con código aparte del recolector desde dos fuentes (la evidencia cruda y
la API de Blockscout, cuando responde) y publica `VERIFICACION.md`. Con
`{"modo": "verificar", "corrida": <run_id>}` en `run.json` solo se verifica una corrida
anterior, sin recolectar.

Si se acaba el tiempo o se cancela, el tramo guarda lo que tenga y lo marca
(`events_complete`, `time_budget_hit`, `interrupted`, `oracle_status: sin_cobertura`).

Local, sin red:

```
cd migration/census-dinero
python3 -m unittest discover -s tests
python3 check_isolation.py
python3 -m census_dinero plan --run-json run.json
```

Solo librería estándar de Python. Los únicos métodos RPC permitidos son de
lectura (`rpc.ALLOWED_METHODS`); cualquier método de firma o envío se rechaza.
