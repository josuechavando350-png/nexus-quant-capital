# SUPERHUNTER — Auditoría de evidencia y recorridos dirigidos de cadenas críticas

**Estado:** componente real de análisis **offline**, no una PoC ofensiva ni una confirmación de impacto. Complementa el motor `critical_chain.py`, con verificación independiente de los expedientes privados y de sus fuentes previas (forense, correlación de journals y replay EVM).

## Qué calcula realmente

Para cada hipótesis previamente verificada, busca el **camino dirigido de mayor longitud** dentro del DAG de observaciones y dependencias. Si varios caminos empatan, prefiere el que tiene menos aristas sin referencia local verificable y después desempata por orden lexicográfico. Devuelve:

- `directional_witness`: secuencia de observaciones conectada mediante relaciones declaradas, **no prueba causal**.
- `uncovered_nodes`: partes de una cadena ramificada que no pueden representarse por ese único recorrido; no son descartadas.
- `unsupported_observations` y `unsupported_declared_links`: brechas exactas, con referencias localmente verificadas o contradichas.
- `contradictory_source_ids`: fuentes cuya propia verificación forense informa contradicciones temporales.
- `proof_obligations`: trabajos pendientes (alcance, origen de evidencia, observaciones, dependencias, ramas, reproducción y verificación independiente de impacto).

Este motor NO genera payloads, no contacta terceros, no acredita autenticación del productor o permiso de pruebas activas, no resuelve causalidad y no convierte la suma de severidades leves/medias en una vulnerabilidad crítica confirmada. La utilidad del ranking anterior se conserva intacta; los nuevos resultados son *auditoría de estructura y vacíos de evidencia*.

## Uso con artefactos privados (nunca subir los originales)

```sh
python3 -m superhunter audit-chain-paths \
  --triage /privado/triage-previamente-verificado \
  --sources /privado/source-map.json \
  --out /privado/auditoria-de-caminos-nueva

python3 -m superhunter verify-chain-paths \
  --bundle /privado/auditoria-de-caminos-nueva \
  --triage /privado/triage-previamente-verificado \
  --sources /privado/source-map.json
```

`verify-chain-paths` vuelve a invocar **los verificadores efectivos** del triaje y sus fuentes, reconstruye la auditoría, verifica los hashes de sus archivos, la identidad de fuentes Python, el recibo y el informe. Rechaza un `critical_impact_confirmed=true` falsificado aunque se haya recalculado el manifiesto. La integridad por hash no sustituye autenticidad/firmas ni custodia independiente.

## Límites y siguiente gate

La semántica del grafo es declarada por el investigador; un recorrido completo no demuestra un camino de ataque real. Una cadena de múltiples ramas puede ser válida como hipótesis pero exige **experimentos adicionales**. Máximos heredados: 8 fuentes, 128 observaciones, 128 aristas, 32 candidatos y 12 observaciones por candidato. Este módulo requiere primero evidencia local; para pasar al siguiente nivel falta un protocolo de reproducción independiente en laboratorio autorizado y verificación del impacto tangible sobre sistemas propios.
