# Slither: importación de alertas con fuentes verificables

## Alcance implementado

El módulo `static_review.py` lee resultados JSON ya existentes de Slither y una
lista explícita de fuentes. No ejecuta Slither, solc, Forge, código Solidity,
RPC, compiladores ni comandos de un repositorio externo. No genera exploits,
PoCs, Candidates de explotación ni hallazgos confirmados. Es un adaptador
funcional de datos y revisión, no el motor completo de análisis estático.

Se verifican el SHA-256 del reporte y de cada fuente; rutas relativas de un
inventario explícito; rangos de bytes UTF-8 y líneas; detectores declarados;
impacto y confianza del productor. Se agrupan alertas equivalentes por detector,
repositorio/commit declarado y testigos de ubicación, conservando descripciones,
repeticiones e índices originales. Si dos registros equivalentes discrepan en
su clasificación, la importación se rechaza: no se elige la severidad más alta
para aparentar impacto. Las ubicaciones ausentes permanecen incompletas.

DIABLO aporta su AuditLog original para registrar importación, fuentes y salida.
El verificador reconstruye resultados, deduplicación y reporte desde los bytes
originales y contrasta los eventos. Los textos de presentación usan el filtro
de privacidad existente. **Todo el bundle sigue siendo privado**: incluye el
reporte original y los snapshots de fuentes; no garantiza ausencia de secretos.

## Interfaz

```bash
python3 -m superhunter import-slither \
  --report /directorio-privado/slither.json \
  --context /directorio-privado/context.json \
  --sources /checkout-local-autorizado \
  --out /directorio-privado/alertas-nuevas

python3 -m superhunter verify-slither \
  --bundle /directorio-privado/alertas-nuevas

python3 -m superhunter initiatives
```

`context.json` usa el esquema siguiente. Los hashes deben calcularse sobre los
bytes reales: los marcadores de esta explicación NO son valores válidos.

```json
{
  "schema_version": 1,
  "scope_id": "bounty-proyecto-autorizado",
  "repository": {"repo": "owner/repo", "commit": "40 caracteres hexadecimales"},
  "tool": {"name": "slither", "version": "version declarada del productor"},
  "detectors": ["naming-convention"],
  "report_sha256": "sha256 del JSON original",
  "sources": {"contracts/Example.sol": "sha256 de esa fuente"},
  "input_kind": "external-report"
}
```

`synthetic-format-fixture` identifica datos de prueba de formato. No sustituye
una ejecución de Slither. La identidad de repositorio, commit, scope y versión
es declarada; el importador NO consulta Git ni verifica la autorización real
ni la procedencia del proceso productor. Las rutas absolutas que aparezcan en
metadatos no se abren. Las dependencias fuera de la lista se rechazan.

## Estados y límites

- `STATIC_REVIEW_REQUIRED`: alertas con ubicaciones vinculadas a los snapshots.
- `INCOMPLETE_SOURCE_BINDING`: faltan ubicaciones; no se simula una prueba válida.
- `NO_ALERTS_IN_SUPPLIED_REPORT`: el array recibido estaba vacío, no código seguro.
- `TOOL_ERROR`: el productor declaró un error; nunca se presenta como análisis limpio.
- `STATIC_IMPORT_ERROR`: datos incompatibles, alterados o IO inválido.

Código de salida 0: normalización completa, no ausencia de vulnerabilidades.
Código 1: productor fallido o localizaciones incompletas. Código 2: entrada/IO
inválida. `vulnerability_confirmed`, `scanner_execution_verified`,
`scope_authorization_verified`, `repository_commit_verified`,
`producer_authenticated` y `code_certified_safe` permanecen en false.

Las entradas tienen límites: 64 fuentes, 8 MB combinados, 2 MB por artefacto,
1,000 alertas, 128 elementos por alerta, 4,096 elementos totales y 32 MB de rangos
mapeados acumulados. No se truncan silenciosamente. Se rechazan symlinks,
traversal, claves JSON duplicadas y números no finitos. Las salidas son nuevas,
con permisos 0700/0600, fuera del checkout; no se sobrescriben originales.

El verificador comprueba consistencia, no firma o autenticidad remota. Quien
controle todos los inputs puede fabricar un reporte consistente; por eso no
existe promoción a hallazgo probado. Tampoco se comprueban root cause,
explotabilidad, pérdida económica, severidad oficial o elegibilidad de bounty.

## Documentación de formato consultada

- https://github.com/crytic/slither/wiki/JSON-output
- https://crytic.github.io/slither/slither/core/source_mapping/source_mapping.html

El esquema documentado usa posiciones y longitudes en **bytes**, no índices de
caracteres Python. El importador es una implementación independiente del lector
de formato; no incorpora código, binarios ni detectores de Slither. No se ha
instalado ni ejecutado Slither o solc en esta entrega. La compatibilidad evaluada
es la del subconjunto de esquema documentado con fixtures explícitos; falta una
prueba de integración con salida de una versión real del analizador.

## Continuidad de los resúmenes

`research_initiatives.json` conserva los 25 IDs (5 referentes × R1/R2/R3/D1/D2),
el PDF y página de origen, hashes de ambos documentos, vínculos con los 50
requisitos y tests que sostienen avances parciales. No son 25 implementaciones
vacías. `research_plan.py` valida y presenta ese registro; el reporte conjunto
incluye INITIATIVES.md. Los 27 requisitos y 50 capacidades no se reemplazan.
