# Auditoría H6 — Causal Graph

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.
Baseline de bytes probados: commit `04e88a67eb594e72f2391026aeaa1fa1cd70afec`.

## Alcance

H6 añade un grafo offline y content-addressed para responder qué posiciones
deben recalcularse cuando cambia un mercado, oráculo, modelo de intereses,
fuente de liquidez o ruta.

## Pruebas

- **20/20 pruebas H6 aprobadas**.
- **58/58 pruebas combinadas H4 + H5 + H6 aprobadas**.
- `python3 -m py_compile` aprobado para módulo y pruebas.

Se probaron cobertura obligatoria por posición, nodos/aristas duplicados,
aristas colgantes, tipos incompatibles, self-edges, ciclos, invalidación por
oráculo/mercado/liquidez, dependencias compartidas, aislamiento de nodos no
relacionados, evidencia obligatoria, orden canónico, compromiso alterado y
autoridades de ejecución siempre en falso.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| causal_graph.py | `27c56cfaf3c4bf9ffe5a0ae8108a73bdd7c1e7acca7909e1bc9bd6286cd66284` | `91d454cb8a767d7af7a2c59071e169ce9c153bb6` |
| test_causal_graph.py | `f5a28db416554865f013c694353dde65ab02447050c1a63bde82b71d94f53b1a` | `c48f685aa670d00239eadea96c5269f467499a6d` |
| CAUSAL_GRAPH_CONTRACT.md | `dc383ebbced81e7a7b6adc3b2a86c29e7aa156a291f69720b6534cebcac1bee4` | `12b64714ad2a692d0ee4c3829f46d50e79c36e79` |

La primera publicación del archivo de pruebas tuvo una diferencia de bytes
respecto al archivo local probado. La auditoría la detectó y el blob fue
reemplazado por los bytes exactos antes de cerrar H6.

## Bloqueos restantes del componente 7

1. El grafo no está poblado desde la totalidad del universo admitido.
2. No existe todavía una prueba de completitud contra todas las posiciones,
   mercados, oráculos, modelos de intereses, liquidez y rutas reales.
3. Falta replay temporal que demuestre que cada cambio invalida exactamente el
   conjunto correcto.
4. Falta integración directa con el Libro de órdenes para recalcular sólo las
   posiciones afectadas.
5. Falta la regresión completa Python/Rust del repositorio.

Por estas razones el componente 7 sólo puede pasar a **foundational_partial**.
No queda certificado y Census continúa abierto.

## Medición

H6 se considera 100% como hito de implementación offline únicamente después de
sincronizar inventario, assessment, aislamiento y read-back. El total de
componentes certificados continúa en **0/36**.
