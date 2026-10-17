# Compatibilidad condicional C1 / Titan / Quasar

Corte documental: 2026-10-17. Se consultaron páginas públicas, **ningún relay**.
Fuentes y fragmentos mínimos: `evidence/public-sources.json`.

[Titan API](https://docs.titanbuilder.xyz/api/eth_sendbundle), sección schema/Sponsored Bundles;
[Quasar API](https://docs.quasar.win/api/eth_sendbundle), mismas secciones.
D = DOCUMENTADO; NV = NO VERIFICADO en las fuentes consultadas.

| Campo/comportamiento | Titan | Quasar |
|---|---|---|
| `txs` | D: transacciones firmadas; vacío permite cancelar | D: transacciones firmadas |
| `blockNumber` | D: hexadecimal, opcional, bloque actual por defecto | D: igual |
| `minTimestamp` | D: límite inferior del slot | D: límite inferior |
| `maxTimestamp` | NV en schema consultado | D: límite superior |
| `revertingTxHashes` | D: permite revertir o descartar | D: permite revertir |
| `droppingTxHashes` | D: permite descartar, no revertir | D: igual |
| `replacementUuid` | D: identificador de 16 bytes | D: UUID |
| `replacementSeqNumber` | D: creciente; cero/omitido usa recepción | D: igual |
| `refundPercent` | D: 0–99; recompensa final/seleccionada | D: 0–99; texto menciona recompensa total |
| `refundRecipient` | D: destinatario; defecto primer remitente | D: igual |
| Selector refund | NV: `refundIndex` en descripción; `refund_tx_hashes` en estructura Rust | D: `refundTxHashes`, máximo uno; defecto última tx |
| Refund insuficiente para su gas | D: descarta bundle | NV en página consultada |
| Disparador patrocinio | D: `LackOfFundForGasLimit` | D: igual |
| Alcance económico publicado | D: gas y value, condicionado a incremento builder | D: gas, condicionado a incremento builder; value NV |
| Beneficiario autenticado C1 / monto / no recurso | NV | NV |

La ambigüedad del selector Titan y de base del refund Quasar queda abierta; el manifiesto deja refund **sin configurar**. No resolverla inventando una API.

El [artículo oficial enlazado por Titan](https://titanbuilder.substack.com/p/titan-tech-teatime-1), 2023-07-03, sección Sponsored Bundles, describe simulación, evaluación de fondos/beneficio, transferencia propia antepuesta y entrada al conjunto de candidatos. DOCUMENTADO: existe esa descripción de prepend. INFERENCIA: podría financiar una EOA cero antes de nonce 0. NV: cobertura exacta de dos CREATE, reserva por prefijo, monto A, devolución U, destinatario y compromiso sobre esta secuencia. Ser candidato no garantiza inclusión. No se extrapola el artículo a una implementación actual auditada.

## Aplicación al manifiesto, análisis propio

| Condición C1 | Clasificación | Consecuencia |
|---|---|---|
| Dos CREATE, liquidación, U; anticipo primero | PROBADO LOCAL | V06, cinco recibos en un bloque Anvil |
| Cuenta NQC vacía, financiador con dinero externo | PROBADO LOCAL | ETH/token inicial NQC cero; builder tiene 100 ETH **sintéticos** |
| R dirigido a otro actor | INCOMPATIBLE BAJO CONDICIONES | V05: builder pierde 0.004636412 ETH a 2 gwei |
| R al builder de laboratorio | PROBADO LOCAL / MODEL_ONLY | V06: +0.045363588 ETH de caja |
| R a builder real | NO VERIFICADO | Destinatario real null, no sustituir por 0x…1004 |
| Tip a coinbase | PROBADO LOCAL como ingreso del proponente | No acredita titularidad builder |
| Refund API frente a `sponsorRefundWei` | INFERENCIA contable de direcciones opuestas | No compensarlos ni denominarlos el mismo pago |
| U enviada desde anticipo ya disponible | PROBADO LOCAL | No requiere otro subsidio de value; requiere precio/A exactos |
| Quasar financia value adicional | NO VERIFICADO | Ausencia de texto no equivale a prohibición |
| Listas revert/drop vacías | Política local conservadora | No son seguro, garantía de rollback ni aceptación |
| Firmas/aceptación/costos externos/no recurso | NO VERIFICADO | NOT_TESTED / UNKNOWN |

El manifiesto es intención offline unsigned, no un body RPC válido. El override del pool Anvil sólo permite estudiar prefijos; no reproduce la lógica interna de los operadores.
