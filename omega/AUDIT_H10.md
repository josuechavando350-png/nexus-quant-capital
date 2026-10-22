# Auditoría H10 — Truth Triad

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H10 añade paridad exacta de tres vías por sujeto y estado: reconstrucción
eventos/storage, lectura directa de contrato y replay EVM. No sustituye el
Protocol/Fork runtime certificate.

## Pruebas

- **20/20 pruebas H10 aprobadas**.
- `python3 -m py_compile` aprobado.
- El acumulado de suites offline H4–H10 contiene 135 pruebas aprobadas en sus
  ejecuciones auditadas; no sustituye la regresión completa del repositorio.

Se probaron paridad exacta, mismatch de una vía, ausencia/duplicación de lanes,
lanes desconocidos, independencia de fuentes y productores, anchors inválidos,
semántica ausente, tamper, orden canónico, autoridades en falso, cobertura batch
completa, sujetos duplicados/ausentes y prohibición explícita de reclamar PFT.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| truth_engine.py | `26c4fde76d599837d6c6fb664e9167532fdccf102afb5f892ed62d7693f07777` | `9a08c35a5b0965b07f8187ab4b2b5ea51407cca1` |
| test_truth_engine.py | `8d5055f111fdc81f22ecff1fb2433bc42a8ab7f2795ac1c75b3a6e83b55a70ca` | `67eb1c8c4cf1405d3cef4c72f6a9a14030614d24` |
| TRUTH_TRIAD_CONTRACT.md | `a55afcae9647b0ed9f0ab4cf3e535d3dcc787f9df7d3eddc26e3824dcc7a14c5` | `0e114bc6395746382ba8e6b026426e7868987e9e` |

Los Git blobs coinciden con los bytes probados.

## Límites

`PARITY` significa igualdad exacta de commitments de las tres vías; no significa
que el productor actual esté recertificado. El tracked PFT original continúa
NOT_CLOSED para este productor independiente hasta el runtime closeout apropiado.

## Bloqueos restantes del componente 6

1. Poblar triadas desde fuentes reales independientes para todos los sujetos.
2. Probar cobertura completa del alcance real.
3. Reestablecer el runtime closeout PFT vinculado a este repo/head/tree.
4. Ejecutar PFT/forks y replay EVM completo.
5. Regresión completa del repositorio.

Por ello el componente 6 sigue **foundational_partial**, no certificado.
