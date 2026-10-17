# Directiva 003 — financiación y liquidación en una EVM local

**LOCAL_SYNTHETIC_E2E_PASS**, exclusivamente en chain 31337: el operador empieza con cero ETH/tokens, recibe un anticipo externo simulado, despliega adapter y ejecutor, liquida contra Morpho original, convierte en Uniswap V2 original, repaga, remunera a sponsor y proponente y devuelve el anticipo sobrante mediante otra transacción. No es replay histórico, aceptación de Titan/Quasar, inclusión competitiva ni ingreso realizado.

Rama: `research/nqc-morpho-sponsor-e2e-20261017`. Base inmutable: `544fd2d16d0b1cf1018dce006702a7abcbf0d0c6`. Todos los archivos nuevos están en este directorio. Los módulos anteriores y sus certificados permanecen intactos. El estado de continuidad de esta entrega está en `RESEARCH_STATUS.md`, sin sobrescribir el de la investigación anterior.

## Reproducción

Se necesitan los checkouts públicos fijados y los binarios enumerados en `REGRESSION_AND_REPRODUCE.md`. No se usan claves: Anvil genera **cero cuentas**, solo escucha en loopback, no hace fork ni conoce un RPC exterior. El programa crea su propio proceso efímero y lo detiene en `finally`. Las peticiones `eth_sendUnsignedTransaction` son mensajes de prueba a ese proceso; no contienen firmas ni se transmiten a una red pública.

Desde la raíz del repositorio, ajustar únicamente los paths absolutos al entorno:

```sh
export NQC_WORKSPACE=/workspace/scratch/f380716a269b
export NQC_TOOLCHAIN="$NQC_WORKSPACE/nqc-toolchain"
export NQC_PYTHON="$NQC_WORKSPACE/nqc-python/bin/python"
export NQC_EXPERIMENT=migration/experiments/morpho-sponsor-e2e-20261017
"$NQC_PYTHON" "$NQC_EXPERIMENT/build_local.py" --workspace "$NQC_WORKSPACE" --toolchain "$NQC_TOOLCHAIN"
"$NQC_PYTHON" "$NQC_EXPERIMENT/run_e2e.py" --anvil "$NQC_TOOLCHAIN/node_modules/@foundry-rs/anvil-linux-amd64/bin/anvil"
"$NQC_PYTHON" "$NQC_EXPERIMENT/reconcile.py"
"$NQC_PYTHON" "$NQC_EXPERIMENT/sensitivity.py"
"$NQC_PYTHON" -m unittest discover -v -s "$NQC_EXPERIMENT" -p 'test_*.py'
"$NQC_PYTHON" "$NQC_EXPERIMENT/select_candidates.py"
```

El último comando imprime la selección sin cambiar el lock. La reproducción EVM regenera evidencia local: usar un checkout de revisión si se quieren preservar los bytes publicados. `build/` se excluye de Git; bytecodes, fuentes y compiladores se identifican mediante `evidence/build-manifest.json`. La contabilidad completa, sin floats, está en `ACTOR_SETTLEMENT_LEDGER.json` y sus recibos/trazas de respaldo en `evidence/`.

## Alcance y límites

- Estado, oracle, capital externo, precios de gas y reparto de remuneraciones son fixtures explícitas. No representan una oportunidad observada ni una cotización de financiación.
- Las transacciones se incluyen en bloques locales sucesivos. Se comprueba la atomicidad **dentro de la liquidación** y la falta de atomicidad de una secuencia interrumpida; no se emula un relay ni una garantía de inclusión conjunta.
- El timestamp génesis 1800000000 es una constante sintética para reproducibilidad, no una observación de mercado ni una marca temporal de captura.
- Morpho arranca con cero WETH disponible para flash loan; la venta del colateral adelantado por `liquidate` obtiene el repago antes del `transferFrom` final. El protocolo conserva su deuda y la DEX su liquidez reales dentro del escenario.
- El ciclo base es positivo; el mismo ciclo a 21 gwei efectivos es negativo para el sponsor. Ambos resultados son reproducidos, pero sintéticos.
- Caso B: `BLOCKED_PRESTATE`. Doce candidatos históricos: `UNRATED_MISSING_WITNESS`. Ingreso propio certificado: US$0. Potencial mensual: **NO ESTIMABLE**.

No se contactaron relays, proveedores ni financiadores, no hubo firmas, despliegues públicos, transferencias financieras ni gastos. La lectura/publicación de código en GitHub no cambia este límite.
