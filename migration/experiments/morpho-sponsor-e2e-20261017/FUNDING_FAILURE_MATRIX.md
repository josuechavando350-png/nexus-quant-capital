# Fallos y exposición de financiación

Todos son controles locales. Un revert revierte los cambios internos de esa transacción, pero conserva su gas cobrado. Las operaciones de fondeo/despliegue previamente incluidas permanecen. No se presume recuperación ni recurso contra el propietario.

| Caso | Gas total incluido | Delta ETH del sponsor | ETH retenido en EOA | WETH nuevo NQC |
|---|---:|---:|---:|---:|
| F01_none | 0 | 0.000000000000000000 | 0.000000000000000000 | 0.000000000000000000 |
| F02_topup_only | 21,000 | -0.030042000000000000 | 0.030000000000000000 | 0.000000000000000000 |
| F03_deploy_only | 1,794,574 | -0.030042000000000000 | 0.026452852000000000 | 0.000000000000000000 |
| F03_bad_create | 581,853 | -0.030042000000000000 | 0.028878294000000000 | 0.000000000000000000 |
| F04_healthy | 2,047,241 | -0.030042000000000000 | 0.026000712000000000 | 0.000000000000000000 |
| F05_one_wei_slippage | 2,154,432 | -0.030042000000000000 | 0.025733136000000000 | 0.000000000000000000 |
| F06_debt_shortfall | 2,278,754 | -0.030042000000000000 | 0.025733514000000000 | 0.000000000000000000 |
| F06_one_wei_underpay | 2,467,553 | -0.030042000000000000 | 0.025106894000000000 | 0.000000000000000000 |
| F07_sponsor_reject | 2,378,346 | -0.030042000000000000 | 0.025285308000000000 | 0.000000000000000000 |
| F08_proposer_reject | 2,385,052 | -0.030042000000000000 | 0.025271896000000000 | 0.000000000000000000 |
| F09_nonce | 1,794,574 | -0.030042000000000000 | 0.026452852000000000 | 0.000000000000000000 |
| F10_expired | 1,822,698 | -0.030042000000000000 | 0.026396604000000000 | 0.000000000000000000 |
| F10_reorg | 2,047,241 | -0.030042000000000000 | 0.026000712000000000 | 0.000000000000000000 |
| F11_dust | 2,540,785 | 0.043248948000000000 | 0.000000000000000000 | 0.159365645570551238 |
| F12_distinct_actors | 2,339,206 | 0.043321588000000000 | 0.000000000000000000 | 0.159365645570551238 |

F01 no incluye ninguna transacción: gasto on-chain cero; preparación/infraestructura externa UNKNOWN. No representa un rechazo observado por un relay. F02 deja A completo en la EOA; F03 lo deja reducido por CREATE. Ese saldo es anticipo retenido, no ingreso generado ni U devuelto. La pérdida de caja del sponsor no equivale a declarar todo el anticipo económicamente irrecuperable: la recuperación real y su obligación contractual son UNKNOWN.

F04 cambia el oracle a posición sana; F05 fija el mínimo un wei por encima de la salida. F06_debt_shortfall reduce capacidad DEX por una aportación externa y sincronización; el ejecutor protege el repago antes de consumir fondos. F06_one_wei_underpay usa un control deliberadamente defectuoso **distinto del ejecutor NQC**: vende en la DEX original, aprueba un wei menos del repago y Morpho original revierte el transferFrom. La venta interna también se revierte; logs finales vacíos y gas cobrado.

F07 rechaza el refund; F08 rechaza el pago directo al coinbase. El segundo receptor sí recibe priority fees por regla de protocolo aunque su fallback rechace ETH: no se confunde el tip fallido con esas tasas. No llega ningún pago al builder simulado en esos fallos. F09 usa nonce obsoleto y es rechazado por Anvil sin recibo ni gas nuevo; permanecen fondeo y CREATE.

F10_expired revierte por expiración. F10_reorg guarda una ejecución local exitosa, restaura el snapshot previo, cambia el oracle y ejecuta el fallo en la rama restaurada. El recibo huérfano se conserva por separado y se excluye del ledger canónico local; no acredita probabilidad ni recuperación en una reorg real.

F11 dona 1 WETH, 1 COLLATERAL y fuerza 1 ETH al ejecutor desde el preparador externo. Los tres inventarios permanecen intactos; el ingreso de la EOA es idéntico al ciclo limpio. Los costes de donar se imputan al donante, no se ocultan ni se cargan al sponsor. F12 repite el ciclo con las identidades explícitas sponsor ≠ builder ≠ proposer; el parentesco económico solo se declara entre sponsor y financiador, y entre remitente NQC y beneficiario, por definición del laboratorio.

CREATE positivo: adapter y ejecutor generan código; CREATE negativo: constructor con operador cero revierte, cobra gas y no produce ejecutor funcional. Controles adicionales: sender no autorizado, suma uint256 que desborda, reserva un wei insuficiente para refund+tip y payout que supera el margen. Todos revierten sin cambiar deuda/tokens/DEX; los gastos pertenecen a sus remitentes. El caso de sender incorrecto cobra ese intento al sponsor porque él es el sender deliberado del control.

Solo los ciclos exitosos ejecutan la devolución voluntaria del anticipo. En los fallos no se añade recuperación hipotética. La política de un tercero real respecto a reembolso, deuda, garantías y pérdidas sigue PENDIENTE.
