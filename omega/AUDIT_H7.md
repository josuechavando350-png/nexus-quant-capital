# Auditoría H7 — Oracle Semantics / Depeg Radar

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H7 añade un registro offline de semántica de oráculos. La clasificación sólo
puede provenir de evidencia explícita: nunca infiere semántica por símbolo,
nombre o reputación de un activo.

## Pruebas

- **18/18 pruebas H7 aprobadas**.
- **76/76 pruebas combinadas H4 + H5 + H6 + H7 aprobadas**.
- `python3 -m py_compile` aprobado.

Se probaron MARKET_PRICE vs EXCHANGE_RATE, exposición combinada collateral/debt,
clases desconocidas, duplicados, referencias a oráculos ausentes, evidencia
faltante, pares base/quote inválidos, compromiso alterado, orden canónico,
consultas desconocidas, ausencia de heurísticas por nombre/símbolo y autoridades
de ejecución siempre en falso.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| oracle_semantics.py | `602e260b5120a503e7df28018f3176a7f39619ae864aa2a608b38bd7aed72ac0` | `8555f5c69ab15705e358b142f193ef56166575ee` |
| test_oracle_semantics.py | `bfed041950262f73596f12d0447f09cee78bbb59121b55e216c9630553dcaaf1` | `6e87796b63d9a93a01d07094f32c4116c0de38c4` |
| ORACLE_SEMANTICS_CONTRACT.md | `daa60c264b7c1ee2e6269577fc40f15992dfd0247aaddf3ad5fb432e8397b563` | `10a2bc7ca9e13dc9e18d19cce086637ccac466b4` |

Todos los Git blobs coinciden con `git hash-object` sobre los archivos que
pasaron las pruebas locales.

## Límite semántico

`EXCHANGE_RATE` significa únicamente que un depeg spot no se refleja
directamente por ese oráculo. No significa que la posición sea imposible de
liquidar: deuda, acumulación de intereses, cambios en la tasa, otros oráculos o
reglas de protocolo pueden seguir alterando su salud.

## Bloqueos restantes del componente 10

1. Poblar semántica protocol-specific para todos los oráculos del alcance.
2. Probar bytecode/configuración/versiones que justifican cada clase.
3. Replay de eventos históricos de depeg y falsos positivos.
4. Conectar cambios semánticos al Causal Graph y Order Book.
5. Regresión completa del repositorio.

Por ello el componente 10 sólo puede pasar a **foundational_partial**. No queda
certificado y Census continúa abierto.
