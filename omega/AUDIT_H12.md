# Auditoría H12 — Candidate Coherence Gate

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H12 conecta seis artefactos Census ya sellados para impedir que piezas
individualmente válidas se combinen si pertenecen a bloques, posiciones,
mercados, oráculos, despliegues o versiones distintas.

Artefactos integrados:

1. Protocol Adapter Registry;
2. Truth Triad;
3. Causal Graph;
4. Liquidation Order Book;
5. Oracle Semantics Registry;
6. Opportunity Dossier.

El resultado permitido es únicamente `FOUNDATION_COHERENT`. No concede GO,
certificación, firma, broadcast, gasto, cierre de Census ni avance de fase.

## Pruebas H12

- **21/21 pruebas H12 aprobadas**.
- `python3 -m py_compile` aprobado para módulo y pruebas.

Cobertura: coherencia de chain/block/hash/state-root; Truth parity; subject =
position; posición→market/oracle del grafo; posición/oráculo del order book;
market/oracle del registry; family/chain/deployment/version del adapter; seis
capacidades evidence-bound; protocolo desconocido; tamper; compromiso
determinista y autoridades siempre en falso.

## Regresión offline conjunta

Se ejecutaron en el mismo directorio y proceso de importación las suites
auditadas H4–H12, usando los módulos cuyos Git blobs ya estaban fijados.

Resultado: **176/176 pruebas aprobadas, 0 failures, 0 errors**.

Esta regresión incluye:

- H4 Opportunity Vault;
- H5 Liquidation Order Book;
- H6 Causal Graph;
- H7 Oracle Semantics;
- H8 Long-Tail;
- H9 Protocol Adapters;
- H10 Truth Triad;
- H11 Competition Ledger;
- H12 Candidate Coherence.

No sustituye la regresión Python/Rust completa del repositorio.

## Incidencias detectadas por auditoría

1. Primer intento local: se copió una versión local antigua de `integrity.py`
   sin `read_regular`. La importación falló antes de ejecutar la lógica.
   Se sustituyó por el helper auditado del repo y la suite se repitió desde cero.
2. Primera publicación del archivo de pruebas omitió dos comentarios del archivo
   local probado. El blob no coincidió. La auditoría lo detectó y el archivo fue
   corregido antes de cerrar H12.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob final |
|---|---|---|
| `candidate_coherence.py` | `95fcab029fdfbb8e861afbd80c0f5a1e6e91e91fdbfc75f083f2ff6d967fbe5f` | `7309c909cebd199ea3ad86f9e8bb317201614c23` |
| `test_candidate_coherence.py` | `db9b1f13ebca26f75d1efae8d772a82ff33a51ad6248d58ee0dbcb2f2a6b47ab` | `737e0772397c68bfe5c90c470e2581d06eb3885c` |
| `CANDIDATE_COHERENCE_CONTRACT.md` | `a5dab1f0241cb8175deefe56fad3760e78ba8b7c2f2951810be7b6f75dcebd37` | `2aa60c42f59e67646718c0196f78a391f8f01e3f` |

## Límites

`FOUNDATION_COHERENT` sólo demuestra coherencia entre artefactos offline ya
existentes. No demuestra:

- adquisición actual de mercado;
- economía completa;
- competencia actual;
- Protocol/Fork Truth certificado para este productor;
- cobertura completa de posiciones;
- rentabilidad de NQC.

Por ello **H12 = 100% como hito offline**, mientras Omega sigue en **0/36
componentes certificados** y Census permanece abierto.
