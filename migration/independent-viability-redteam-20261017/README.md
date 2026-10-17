# NQC — Auditoría económica independiente / Directiva 002

**17 de octubre de 2026. Investigación parcial con verificaciones offline reproducibles.**
Ninguna arquitectura supera G1–G5. P&L propio certificado: US$0; expectativa mensual: NO ESTIMABLE.

## Lectura recomendada

1. [DIRECTOR_HANDOFF.md](DIRECTOR_HANDOFF.md): primera página de decisiones, hallazgos y tres solicitudes concretas para Astra.
2. [SPONSOR_NO_RECOURSE_AUDIT.md](SPONSOR_NO_RECOURSE_AUDIT.md) y [FAILURE_LIABILITY_MATRIX.md](FAILURE_LIABILITY_MATRIX.md): quién financia y quién soporta cada fallo.
3. [INDEPENDENT_ECONOMIC_LEDGER.md](INDEPENDENT_ECONOMIC_LEDGER.md): balances, frontera exacta B, conciliación Robinhood y T-01…T-10.
4. [TEMPORAL_COMPETITION_AUDIT.md](TEMPORAL_COMPETITION_AUDIT.md) y [CENSUS_BIAS_REPORT.md](CENSUS_BIAS_REPORT.md): causalidad, relojes, filtros y faltantes.
5. [CROSS_STRATEGY_KILL_MATRIX.md](CROSS_STRATEGY_KILL_MATRIX.md): estados G1–G5 y decisiones Morpho, Aave/SVR y Robinhood.
6. [SCALE_AND_MAGNITUDE_AUDIT.md](SCALE_AND_MAGNITUDE_AUDIT.md): búsqueda histórica acotada y unidades que no deben sumarse.
7. [BASELINE_AND_DRIFT.md](BASELINE_AND_DRIFT.md), [SOURCE_LEDGER.json](SOURCE_LEDGER.json) y [EXECUTION_LOG.md](EXECUTION_LOG.md): referencias, trazabilidad, errores y límites.

## Reproducción local

Python 3.12 fue la versión usada; los scripts utilizan sólo biblioteca estándar. No necesitan red, claves, proveedor, dependencias descargadas ni credenciales. Desde esta carpeta:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_accounting_audit
PYTHONDONTWRITEBYTECODE=1 python3 accounting_audit.py --output /tmp/nqc-accounting-reproduced.json
PYTHONDONTWRITEBYTECODE=1 python3 census_audit.py --output /tmp/nqc-census-reproduced.json
```

Resultado esperado: 25 pruebas contables; 10 guardrails PASS; 12 grupos de censo y 46 blobs originales verificados. Los diez guardrails se solapan con la suite: no son diez pruebas independientes adicionales. La salida 0 significa que terminó la auditoría local, no que una operación sea comercialmente admisible.

El segundo comando conserva UNKNOWN para obligaciones, atribución y elegibilidad no demostradas. El tercero conserva TEMPORALIDAD_NO_DEMOSTRADA y UNKNOWN_NOT_TRUE. Esas etiquetas son resultados correctos, no errores a convertir en verdadero.

## Archivos de evidencia

| Ruta | Propósito |
| --- | --- |
| evidence/accounting_inputs.json | Cantidades y snapshots necesarios de fuentes fijadas; incluye su procedencia |
| evidence/accounting_results.json | Reconstrucción, sensibilidad, consolidación y controles |
| evidence/accounting_test_output.txt | Registro anterior SUPERSEDED y validación final corregida |
| evidence/census_inputs/ | 46 JSON fuente y manifiesto de identidad |
| evidence/census_audit_results.json | Conteos, filtros, concentración, recibos y tiempos |
| evidence/final_validation.json | Reejecución final del coordinador con comandos y outputs |
| evidence/*sources*.json y evidence/sources_ledger.json | Módulos de procedencia conservados por especialidad |
| evidence/base_git_tree.json y evidence/baseline_heads.json | Inventario Git leído antes de publicar |
| FILE_MANIFEST.json | Paths, bytes, SHA-256 y Git blob de los archivos del paquete, salvo el manifiesto mismo |

El paquete descargable incluye además PUBLICATION_RECEIPT.json y su evidencia de read-back, fuera de la carpeta del commit para evitar una referencia circular al propio SHA. Las comprobaciones de identidad no prueban consenso, estado EVM o control económico de una dirección.

## Límites que forman parte del resultado

No se leyó el PDF maestro de relevo ausente. No se auditó un informe futuro de Astra. No hubo replay EVM nuevo, operación firmada, llamada de admisión, gasto o contacto. El verificador de aislamiento original quedó bloqueado por insumos faltantes; la conservación de archivos para publicar se comprueba aparte mediante árboles Git.

La conversión inicial de dos cargos Robinhood a wei tuvo un error propio de factor 1000. Está corregido y cubierto por una prueba desde los decimales originales; se preserva el registro previo. No afecta el caso B ni se atribuye a Astra.

La rama nueva deriva del SHA de auditoría y sólo añade esta carpeta. El resultado de publicación debe leerse en su recibo, no inferirse del nombre de la rama o de que existan archivos locales.
