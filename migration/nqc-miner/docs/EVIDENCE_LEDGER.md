# NQC Miner — Ledger de evidencia

Corte: 22 de octubre de 2026.

Este ledger separa evidencia durable, evidencia auxiliar, planes no ejecutados y
observaciones transitorias. Ningún elemento cambia de clase por aparecer en una
conversación, log parcial o reporte humano.

| Evidencia | Clase | Estado | Qué demuestra | Qué NO demuestra |
|---|---|---|---|---|
| `evidence/offline-20261022/` | durable / software | PASS histórico | Primera batería offline del Miner | Estado del delta actual |
| `evidence/offline-native-ca-20261022/` | durable / software | PASS histórico | 136 Rust + 38 Python, Clippy, formato e aislamiento después del ajuste TLS | Que los cambios HTTP, rand y binder posteriores compilen o pasen la suite |
| `evidence/public-20261022/` | durable / integración fallida | FAIL preservado | El intento original se detuvo; journal con 0 registros y 0 scopes completos | Actividad mainnet o cobertura |
| `evidence/public-crosscheck-20261022/aave-ethereum.json` | auxiliar / fuente independiente | CORROBORADO | 3 transacciones únicas exitosas con `liquidationCall` en la ventana Ethereum y hashes extremos de la ventana | Conteo exacto de logs del Miner, rentabilidad, cobertura o saturación |
| `evidence/public-retry-20261022/config.template.json` | plan | NO EJECUTADO | Alcance y ventanas de la repetición propuesta, con identidad ligada en runtime | Lectura RPC, eventos o resultados |
| `evidence/binder-python-20261022.json` | durable / módulo aislado | PASS 6/6 | El binder rechaza identidades sucias/operativas y sobrescrituras | Suite Python completa, Rust o RPC |
| `evidence/supply-chain-review-20261022.json` | revisión dirigida | PASS PARCIAL | Ranges 2026 revisados; rand 0.8.5 remediado a 0.8.6 | `cargo audit`/grafo completo o compilación del lock nuevo |

## Observaciones no admisibles como evidencia durable

Durante una ejecución temporal se observó un conteo de cinco eventos en Ethereum.
No existe en esta rama un journal durable/versionado de esa ejecución. Por tanto,
**ese conteo se excluye de métricas, cobertura, calibración, progreso y cualquier
afirmación de resultado**. Solo podrá recuperarse si se repite con el pipeline
actual y queda verificado por `verify-journal`.

## Regla de admisión

Una afirmación operacional necesita, como mínimo:

1. archivo versionado o artefacto durable con propietario/run_id;
2. identidad del código y del Cargo.lock;
3. integridad verificada;
4. alcance explícito de cadena/contrato/bloques;
5. estado completo, no provisional;
6. clase de datos explícita;
7. ninguna contradicción por reorg o proveedor;
8. para economía, precios/costes/eligibilidad y resultado observables.

La evidencia auxiliar puede corroborar hechos puntuales, pero nunca cerrar por sí
sola una salida de fase.
