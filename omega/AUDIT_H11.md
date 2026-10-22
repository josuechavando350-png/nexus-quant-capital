# Auditoría H11 — Competition & Margin Ledger

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H11 añade el esquema por transacción que faltaba para Competitor Intelligence y
la métrica decisiva: ganador, bloque de oráculo, bloque ganador, bono,
builder payment, gas, otros costos observados y evidencia.

## Pruebas

- **20/20 pruebas H11 aprobadas**.
- `python3 -m py_compile` aprobado.
- El acumulado de suites offline H4–H11 contiene 155 pruebas aprobadas en sus
  ejecuciones auditadas; no sustituye la regresión completa.

Se probaron retraso exacto, share del builder en WAD, margen observado, negativos,
desconocidos como null, completitud de costos, orden oracle→winner, duplicados,
direcciones inválidas, floats, bonus cero, summary parcial, no atribución a NQC,
tamper, orden canónico y autoridades en falso.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| competition_ledger.py | `a44450fb8f759a37b046a3b986a28af1c80c016e6528f710e32ffac4e35952e4` | `dacc3bfa847c7ab07fa5a3284c5a66755bb6225d` |
| test_competition_ledger.py | `28261d8c875ed5e91e8d51a1d9f83c7b03435f77827f9b9f7df0491b006c659b` | `340b4d8b71e651baee26b7938867daf9b63ae7fa` |
| COMPETITION_LEDGER_CONTRACT.md | `e87becaf869369ddec9836aa94bf0437f0844d8bce9f6d32eb65ff64b48e7a76` | `6991b7bcf69eced0d9fbe4d14faa65ee4a29b994` |

Los Git blobs coinciden con los bytes probados.

## Límites

El ledger implementa forma y aritmética, pero no inventa filas históricas. El
agregado RMC-016 sigue siendo agregado hasta que receipts/oracle events produzcan
filas autenticadas. Una fila histórica siempre declara
`nqc_execution: false` y P&L de NQC null.

## Bloqueos restantes

1. Materializar las 127 transacciones históricas en filas autenticadas.
2. Vincular cada una con el oracle update correspondiente.
3. Reconciliar builder payments y costos completos por transacción.
4. Añadir counterfactual de detección NQC y oportunidades perdidas.
5. Refrescar cobertura sobre mercado actual y ejecutar regresión completa.

Componentes 24 y 25 permanecen **historical_partial**, no certificados.
