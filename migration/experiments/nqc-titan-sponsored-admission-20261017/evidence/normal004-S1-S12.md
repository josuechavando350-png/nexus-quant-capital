# NQC — Matriz adversarial S1–S12: costos y obligaciones

**Fuente:** `evidence/F01..F12*.json` y `run-index.json` de SHA 937a833..., contrastados con `C1_success.json` y `C1_high_gas.json`. Sólo los aspectos especificados se sustentan en ejecución sintética. Escenarios contractuales contra Titan/Quasar permanecen UNKNOWN; **no asumir owner_liability=0**.

Actores de laboratorio: sponsor 0x...1002, remitente NQC 0x...1003, builder simulado 0x...1004, proponente 0x...1005. El anticipo base es A=0,03 ETH, no fondos disponibles a NQC en Ethereum. Gastos de red a 2 gwei efectivos en los ejemplos base. U significa **devolución realmente recibida** por sponsor, no saldo aparcado en la EOA. Las pérdidas personales son siempre UNKNOWN salvo el contraejemplo S7 con pasivo > 0 explícito.

| Caso | Secuencia y evidencia | Saldo/caja y gas local | Recuperación U y acreedor | Evaluación sin recurso |
|---|---|---|---|---|
| S1 — no inclusión | `F01_none`: 0 tx, 0 gas on-chain | Sin saldo alterado en ese ensayo; gastos externos no medidos | U no aplica; comisión fuera de cadena UNKNOWN | PENDIENTE, no afirmar garantía de coste externo nulo |
| S2 — sólo anticipo | `F02_topup_only`: fondeo incluido, ejecución omitida | Sponsor pierde 0,030042 ETH de caja; EOA retiene 0,03 ETH, gas 21.000×2 gwei | **U=0 recibida**; no existe prueba de recuperación ni de quién exigiría restitución | PENDIENTE; saldo retenido ≠ ingreso de NQC |
| S3 — CREATE revertido | `F03_bad_create`: top-up, adapter, CREATE ejecutor revertido | 581.853 gas total (incluido fondeo); EOA final 0,028878294 ETH; sponsor −0,030042 ETH | U=0; cualquier recuperación exige operación y pagador nuevos | PENDIENTE |
| S4 — posición sana | `F04_healthy`: create pagado y liquidación revertida tras cambio de oráculo | Gas local de 2.047.241 unidades incluye una tx de setup ajena; remitente termina con 0,026000712 ETH | U=0; la liquidación no revierte funding/CREATE anteriores | PENDIENTE |
| S5 — slippage/deuda | `F05_one_wei_slippage`, `F06_one_wei_underpay`: liquidación revierte | `F05` 2.154.432 gas total; no ingreso de swap final de la operación revertida; financiación ya ocurrió | U=0; sin sponsor refund | PENDIENTE |
| S6 — éxito y refund sponsor | `C1_success`: 6 tx exitosas, repago + tip + pago builder | 2.339.206 gas, A=0,03, U=0,025405588, R=0,05, sponsor +0,043321588 ETH | **U cobrada**; sin pasivos de laboratorio en Morpho, pero recurso externo NO demostrado | PENDIENTE para términos reales |
| S7 — utilidad positiva + deuda personal | Contraejemplo de contabilidad independiente, no transacción de Astra | El excedente NQC puede ser positivo; si hay factura/garantía/recurso >0 | Acreedor externo puede conservar derecho contra fundador | **FAIL G0 categórico** |
| S8 — inclusión parcial/reorg | `F10_reorg` con orphans excluidos; `F03_deploy_only` parcial | Saldos cambian dependiendo de rama canónica; tx independientes no se revierten automáticamente | Recuperaciones/clawbacks UNKNOWN | PENDIENTE |
| S9 — gas más alto | `C1_high_gas`: todas las tx pasan a 21 gwei | 2.339.206 gas; sponsor **−0,001123326 ETH** de caja, **−0,001153326 ETH** con cargo oportunidad local; NQC mismo WETH | U=0,251758674 por mayor anticipo A=0,3; hay pérdida sponsor | PENDIENTE (se refuta rentabilidad bajo parámetros C1 altos) |
| S10 — receptor refund/tip rechaza | `F07_sponsor_reject`, `F08_proposer_reject` | Tx liquidation revertida con gas cobrado, gas total 2.378.346 / 2.385.052 respectivamente | U=0; tip/refund no reciben la transferencia revertida | PENDIENTE |
| S11 — sponsor y builder distintos vs mismos | `F12_distinct_actors`: distintos; mismo dueño sólo modelado hipotéticamente | Distintos: sponsor +0,043321588 y builder +0,002; si mismo titular, conjunto +0,045321588 | La transferencia de 0,002 se cancela al consolidar, no genera ingreso externo duplicado | PENDIENTE titularidad real |
| S12 — mismo bloque pero tx separadas | Protocolo propuesto; **NO hay seis tx en mismo bloque en C1** | Orden y nonces compatibles no implican rollback total | Builder puede controlar política de inclusión; EVM sólo revierte cada tx | PENDIENTE, sin aceptación real |

### Quién financia y quién puede perder

C1: el sponsor paga fondeo, anticipo (que se devuelve parcialmente) y fee al builder, mientras que la EOA paga gas de sus cuatro tx **desde el anticipo**. En S2/S3/S4/S5/S8/S10, un fondeo incluido conserva un coste irreversible aunque la liquidación no ocurra; el saldo sin gastar de la EOA sólo pasa a U cuando existe una devolución efectiva. S9 demuestra pérdida del financiador **aun con margen bruto positivo del operador**.

### Condición operativa no satisfecha

Necesitamos documentación verificable que demuestre quien puede repetir/recuperar cada anticipo, cómo se cubren reverts, pérdida por gas, depósito/stake y pasivos diferidos, y que el fundador **no** responderá en ninguno de S1–S12. Eliminar supuestos no equivale a encontrar esos términos. Ningún escenario de laboratorio establece una oferta de Titan/Quasar.
