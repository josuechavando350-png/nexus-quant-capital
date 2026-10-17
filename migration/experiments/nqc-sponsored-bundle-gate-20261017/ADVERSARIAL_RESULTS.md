# Controles adversariales ejecutados

Todos los resultados son locales; una reversión esperada supera el control sin acreditar liquidación exitosa. Los casos de Directiva 003 se reejecutaron y se identifican como controles reproducidos, no descubrimientos nuevos.

| Escenario | Gas cobrado | Caja financiador (wei) | WETH nuevo NQC (unidades) | Estado del criterio local |
|---|---:|---:|---:|---|
| A1_six_blocks | 2339206 | 43321588000000000 | 159365645570551238 | MODEL_ONLY favorable |
| A2_C1_zero_cash | 2339206 | 43321588000000000 | 159365645570551238 | MODEL_ONLY favorable |
| A2_C1_cash8 | 2325526 | 43348948000000000 | 159365645570551238 | MODEL_ONLY favorable |
| C2a_cash8 | 5196129 | 37607742000000000 | 159365645570551238 | MODEL_ONLY favorable |
| C2b_cash0 | 4881122 | -11762244000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| C2b_cash_below | 4881122 | -11762244000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| C2_hypothetical_predeployed | 470191 | 47059618000000000 | 159365645570551238 | MODEL_ONLY favorable |
| A2_C1_high_gas | 2339206 | -1123326000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| A3_topup_only | 21000 | -30042000000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_deploy_only | 1794574 | -30042000000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_bad_create | 581853 | -30042000000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_healthy | 2062644 | -6125288000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_slippage_one_wei | 2196432 | -6392864000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_refund_reject | 2420346 | -6840692000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_proposer_reject | 2427052 | -6854104000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_expired | 1864698 | -5729396000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_wrong_nonce | 453179 | -32084000000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_return_reject | 2339350 | 17916000000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| A3_omit_return | 2318206 | 17916000000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| A3_excess_no_return | 2318206 | -252084000000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| A3_excess_returned | 2339206 | 43321588000000000 | 159365645570551238 | MODEL_ONLY favorable |
| A3_low_tip | 2344772 | 43310456000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| A3_omit_deploy | 88064 | -2176128000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| A3_fee_discrepancy | 2318206 | 17874000000000000 | 159365645570551238 | REFUTED_UNDER_ASSUMPTIONS |
| R003_one_wei_underpay | 2467553 | -30042000000000000 | 0 | REFUTED_UNDER_ASSUMPTIONS |
| R003_dust | 2540785 | 43248948000000000 | 159365645570551238 | MODEL_ONLY favorable |
| A3_priority_change | 2339206 | 43300588000000000 | 159365645570551238 | MODEL_ONLY favorable |

Las direcciones, snapshots, conceptos F/O y cada gas payer están en el ledger. Para cada escenario, su JSON conserva recibos incluidos, errores RPC y candidatos aceptados en pool pero no incluidos. No se inventan recibos para estas dos últimas categorías.

**Resultados que impiden extrapolar un PASS:** un CREATE fallido consume gas; una posición saludable, expiry, slippage de un wei, R rechazado o proponente que revierte deshacen la liquidación, pero no sus transacciones anteriores. `R003_one_wei_underpay` revierte el pull original Morpho después de ejecutar el swap: el swap también se deshace. `R003_dust` conserva 1 ETH, 1 WETH y 1 garantía donados al ejecutor, sin contarlos en el residual nuevo. Estos dos controles usan bloques sucesivos; sus versiones en un solo bloque no se ejecutaron.

**U no recibido:** `A3_return_reject` incluye realmente la devolución y la revierte, con gas cobrado; U recibido es cero. `A3_omit_return` no la envía. En ambos la EOA retiene financiación, no beneficio nuevo. Con anticipo excesivo de 0.3 ETH y U omitido, el financiador pierde 0.252084 ETH mientras NQC conserva WETH positivo. El criterio rechaza el escenario.

**Cap distinto de precio efectivo:** con cap 4 gwei, base 2 y priority 1, las operaciones de negocio se minan a 3 gwei, pero el U calculado descontando solamente gas efectivo no deja la reserva máxima para su propia transacción. U queda fuera del bloque. El log no lo convierte en devolución.

**Permisos y código:** se registran los allowances remanentes de C2; su permiso máximo a Morpho es upstream, no se oculta. Si se omiten los CREATE y se llama a una dirección sin código, el recibo puede tener status=1 sin cambiar la deuda: el criterio ahora exige cierre efectivo de posición. La prueba de nonce duplicado conserva el error RPC y las transacciones pendientes no incluidas.

**Pagos y política:** tip de un wei bajo el umbral hipotético completa en EVM, pero se rechaza por la política del laboratorio. No existe aquí un mínimo de tip impuesto por consenso. El cambio de prioridad mueve el fee builder antes de U; se conserva el orden observado. Los dos controles de exclusión seleccionan un bloque vacío, sin cobrar gas, tras descartar únicamente la simulación local.

**Fallos de implementación corregidos:** el segundo intento se detuvo al encontrar que el retorno de un escenario anterior permanecía en el pool tras restaurar estado. Se añadió vaciado explícito y comprobación de pool vacío entre candidatos, sin alterar verificaciones EVM. `attempt-2-failed.log` conserva el error. Una prueba asumía que el fee mayor se movería antes de la liquidación; Anvil lo movió antes de U, después de liquidar. Se corrigió la afirmación para comparar el orden realmente observado; `attempt-3-test-failure.log` conserva el fallo. Ninguno se cuenta como resultado satisfactorio antes de su corrección y repetición.

El primer intento aislado A2 sí pasó (`first-coordinated-attempt.log`). La ejecución final tiene 27 escenarios y 149 recibos de sus trayectorias observadas, no 149 oportunidades ni operaciones en Ethereum. Los cuatro probes de pool y los dos controles de exclusión se contabilizan aparte. Las simulaciones descartadas para planificar U no aumentan el conteo.
