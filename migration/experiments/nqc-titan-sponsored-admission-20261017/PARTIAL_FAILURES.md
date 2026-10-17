# Fallos parciales y responsabilidad

Mapeo a S1–S12 de **Directiva 004 normal**, copia íntegra `evidence/normal004-S1-S12.md`. Procede del ZIP NQC_DIRECTIVA_004_EXPEDIENTE.zip del usuario, no de un commit publicado; hashes en SOURCE_LOCK. No convertir sus referencias antiguas a seis bloques en afirmaciones sobre esta ejecución.

| Caso normal | Evidencia reutilizada / nueva | Pérdida, devolución y estado |
|---|---|---|
| S1 no inclusión | 004 `policy-exclusion.json` | Cero transacciones elegidas; saldos/nonces locales inalterados. Costo comercial externo UNKNOWN |
| S2 sólo anticipo | 004 A3_topup_only; nueva V07 | V07 builder −52,000,000,000,000 wei; NQC retiene 10,000,000,000,000 wei, U=0; 4 tx pendientes |
| S3 CREATE revertido | 004 A3_bad_create | Gas cobrado y anticipo previo permanecen; no liquidación |
| S4 posición sana | 004 A3_healthy | No deuda reembolsada, liquidación revierte; rechazo local |
| S5 slippage/repago | 004 A3_slippage_one_wei / R003_one_wei_underpay | Reversión; no conversión ni ingreso neto asentados de esa llamada |
| S6 éxito/refund | V06, 5 tx nuevas | R=0.05, U=0.025405588 ETH al financiador; caja +0.045363588 ETH; términos externos UNKNOWN |
| S7 utilidad y deuda personal | Gate con obligación hipotética positiva | REFUTED aun con saldo positivo; no se afirma que tal deuda exista |
| S8 parcial/reorg | 004 A3_deploy_only; reorg de 003 sólo leído | CREATE pueden permanecer. No se reejecutó reorg en 005; garantía externa UNKNOWN |
| S9 gas alto | 004 A2_C1_high_gas reconciliada | Financiador separado −0.001123326 ETH; agrupación hipotética +0.000876674. No intercambiables |
| S10 receptor rechaza | 004 A3_refund_reject, A3_proposer_reject, A3_return_reject | La llamada fallida no genera R/tip/U cobrado. Gas sí; no contabilizar intentos como transferencia |
| S11 identidades | V05 frente a V06 | Misma liquidación; V05 paga R a externo y builder pierde 0.004636412 ETH. V06 lo recibe y gana en fixture |
| S12 mismo bloque | 004 + V07, recibos por índice | No rollback entre transacciones. Listas revert/drop no cubren pérdidas; rechazo local no obliga al builder |

Otros controles reutilizados: A3_wrong_nonce, A3_expired, A3_fee_discrepancy, A3_priority_change, A3_omit_deploy, A3_omit_return. `status=1` con llamada a cuenta sin código no basta: se exige reducción/cierre de deuda, ingreso nuevo y devolución recibida. En A3_fee_discrepancy el cap impide incluir U aun cuando el cálculo de gas efectivo parezca cubrirlo.

`evidence/gate-results.json` conserva U realmente recibida, saldo de anticipo retenido, fallo y SHA por control. Los efectos EVM nuevos se ejecutaron sólo para V05/V06/V07. Los otros son conciliaciones offline de recibos publicados; ningún fallo viejo se presenta como reejecutado.

En todos los casos, recurso comercial contra el fundador: **UNKNOWN**. Ni el ledger ni una lista RPC vacía constituyen una póliza o acuerdo de financiación.
