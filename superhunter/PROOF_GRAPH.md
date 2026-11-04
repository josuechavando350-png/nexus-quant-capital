# Prueba causal del laboratorio local (v1)

Este módulo **no** afirma hallar vulnerabilidades. Une evidencias ya verificadas de un circuito fijo de regresión local: identidad del código original, autorización de DIABLO, entradas numéricas, ejecución real de NQC, referencia independiente, bitácora y veredicto. Las cinco muestras son sintéticas.

## Evidencia enlazada

`local-lab` emite un quinto artefacto, `proof-graph.json`, con **24 nodos**:

- 2 procedencias de código ancladas a Git blobs de DIABLO y NQC.
- Para cada uno de 5 casos, 4 nodos: autorización, entrada, resultado NQC y comparación independiente (20 nodos).
- Una bitácora DIABLO y un veredicto local (2 nodos).

Cada nodo tiene ID, dependencias declaradas y SHA-256 de la evidencia. Su hash incorpora el dominio del protocolo. El hash raíz incorpora todos los hashes de nodo, en orden. La verificación reconstruye el grafo completo desde los artefactos y compara campo por campo. Además verifica la cadena de hashes de DIABLO, los eventos semánticos y el solucionador numérico contra un oráculo independiente.

## Ejecución

```bash
python3 -m superhunter local-lab --out /tmp/superhunter-proof-001
python3 -m superhunter verify-lab --bundle /tmp/superhunter-proof-001
python3 -m unittest discover -s superhunter/tests -v
```

El resultado satisfactorio contiene `proof_graph_root`, `cases_passed=5` y `vulnerability_confirmed=false`. El quinto archivo y los cuatro anteriores están cubiertos por `COMPLETE.json`. La ausencia del grafo impide validar un paquete nuevo.

## Tests negativos

Las pruebas específicas modifican la raíz, los nodos, las dependencias, el orden de autorización, el hash de la entrada, la salida NQC, la exclusión de alcance, los IDs de ejecución y la afirmación de autenticidad. También vuelven a sellar un paquete manipulado para comprobar que no basta con cambiar el hash del manifiesto.

## Límites

Un SHA-256 **no es una firma**, ni demuestra que un productor externo sea auténtico; un adversario con capacidad de sustituir código y todos los artefactos puede rehacer el grafo. La reconstrucción de las relaciones garantiza consistencia y exhaustividad del caso local **dentro del código y los artefactos verificados**, no una prueba universal del mundo real. Este circuito no abre RPC, no usa Forge, no ejecuta contratos de terceros y no demuestra impacto económico de vulnerabilidades. Ningún elemento de las 50 capacidades nuevas queda certificado simplemente por este grafo.

Los 50 objetivos ya tienen un registro separado `capabilities.json` y un control de QA `quality.py`; `proof_graph.py` añade un requisito de integridad a esa arquitectura, sin duplicar el catálogo.
