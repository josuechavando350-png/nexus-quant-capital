# Auditoría H8 — Long-Tail Research Prioritizer

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H8 implementa priorización de **cobertura de investigación**, no selección de
trades. Usa frentes de Pareto sobre cuatro ejes explícitos: novedad del mercado,
tamaño, pertenencia a L2 y complejidad de ruta. No usa pesos arbitrarios ni
produce un score económico.

## Pruebas

- **19/19 pruebas H8 aprobadas**.
- `python3 -m py_compile` aprobado para módulo y pruebas.
- El acumulado de suites offline H4–H8 contiene 95 pruebas aprobadas en sus
  ejecuciones auditadas; esto no sustituye la regresión completa del repositorio.

Se probaron dominancia clara, trade-offs no dominados, frentes sucesivos,
determinismo, ausencia de score económico, duplicados, floats, tipos inválidos,
evidencia ausente, compromiso alterado, orden canónico, consultas desconocidas y
autoridades de ejecución siempre en falso.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| long_tail.py | `3a850a278bf1fafa79fac1f66c5f31795482f663d7696dfbd31d46e6d4bdd880` | `eb993febfc14d47b79d02316bfa88b78cb9cebf1` |
| test_long_tail.py | `77fecdd5e50efa12ed571cf036d7de3c5296cad20c7cd9622806e7a95158bf7d` | `9fe5686a028c4aa4ae9da06bbeb84bcb1c9c0a69` |
| LONG_TAIL_CONTRACT.md | `f317e43a5ff62cb441d49d297b25b19b329c87feedb51c39688ba2c127ed47e7` | `fc7ae9acd812db09f82f445992fe7976a2714123` |

Los Git blobs coinciden con `git hash-object` sobre los bytes probados.

## Límites de interpretación

Un frente Pareto indica sólo que un mercado no queda dominado por otro bajo los
cuatro ejes declarados. No implica mayor beneficio, probabilidad de captura,
prioridad de ejecución ni autorización de GO. El orden por market ID dentro de
un frente es exclusivamente determinista.

## Bloqueos restantes del componente 32

1. Poblar candidatos desde el universo completo de mercados admitidos.
2. Probar procedencia y actualidad de edad/tamaño/L2/complejidad de ruta.
3. Validar out-of-sample que esta lane mejora cobertura de oportunidades
   económicamente relevantes sin ocultar mercados excluidos.
4. Conectar resultados al Evidence Vault y medir sesgo/cobertura.
5. Ejecutar la regresión completa del repositorio.

Por ello el componente 32 sólo puede pasar a **foundational_partial**. Census
continúa abierto y el total certificado permanece en **0/36**.
