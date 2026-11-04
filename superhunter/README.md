# SUPERHUNTER — integración en NQC

Hay dos recorridos separados. No deben confundirse sus resultados.

## 1. Ejecución nativa local

`local-lab` ejecuta componentes originales de DIABLO (Target, ScopeGuard y
AuditLog) junto con el solucionador de capacidad RMC-016 de NQC. Compara sus
resultados con una implementación numérica independiente y produce evidencia.
Los cuatro archivos de origen se preservan byte a byte y se verifican antes
de cargarlos. Todo vive bajo `superhunter/` en NQC.

```bash
python3 -m superhunter local-lab --out /tmp/superhunter-local-001
python3 -m superhunter verify-lab --bundle /tmp/superhunter-local-001
```

Son cinco casos numéricos fijos y controles negativos; **no es el Hunter
completo ni una reconstrucción de vulnerabilidades**. Las cantidades son
sintéticas. `LOCAL_INTEGRATION_PASS` acredita esas regresiones, no un Finding,
una severidad ni una recompensa. Detalles, dependencias y límites del worker:
[LOCAL_LAB.md](LOCAL_LAB.md).

## 2. Intercambio offline de evidencias

`export-diablo` convierte un Finding nativo existente en Candidate unverified.
Requiere contexto explícito: scope_id, repo, commit, chain, chain_id,
fork_block, block_hash, family y poc_path (archivo.t.sol::test_nombre).
No deduce autorización ni ejecución a partir del texto de un reporte.

```bash
python3 -m superhunter export-diablo finding.json context.json forge.log \
  --out /directorio-privado/solicitud-nueva
python3 -m superhunter import-nqc solicitud.json respuesta.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/revision-nueva
```

La respuesta NQC requiere schema_version=1, request_sha256, chain_id y la
Reconstruction completa. Es un contrato de recepción de evidencia existente,
no un productor automático de reconstrucciones de contratos.
`Admission` conserva scope, forge, nqc, duplicate y severity. El archivo de
reconstrucción debe vincular también severidad, confianza y notas.

El modo legacy permanece disponible:

```bash
python3 -m superhunter candidate.json reconstruction.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/revision-nueva
```

Este recorrido devuelve EXPORTED_UNVERIFIED, REJECTED, INCOMPLETE o
REVIEW_REQUIRED. No emite REPORT_READY ni Finding confirmado. Los hashes
comprueban bytes, no la veracidad del productor. target_bound, run_ok,
confianza y nombres de revisores siguen siendo declaraciones externas.
El cierre histórico Protocol/Fork no se admite como Reconstruction.

## Pruebas y operación

```bash
python3 -m unittest discover -s superhunter/tests -v
```

Suite de esta entrega: 157 pruebas ejecutadas, sin fallos, errores ni omisiones.
El laboratorio necesita Linux/POSIX, Python 3.11+ y PyYAML 6.0.3; no instala
dependencias automáticamente. Los demás adaptadores usan la librería estándar.

Las salidas requieren una carpeta nueva y privada; no se sobrescriben.
COMPLETE.json se escribe al final con hashes. No guardar casos sensibles en
este repositorio público. Código de salida 0 significa ejecución/revisión
completada, nunca vulnerabilidad confirmada.

No hay integración autónoma de los motores de búsqueda de vulnerabilidades,
Forge, forks, RPC, firma, broadcasts ni envíos de reportes. No se heredan
certificaciones históricas de NQC. VALIDATION.md, validation-results.json,
local-validation.json y LOCAL_LAB.md conservan las entregas anteriores.
El resultado actual está en quality-validation.json y QUALITY_GATE.md.

## Comprobación conjunta y checklist de capacidades

La entrega 4 añade `check`, `verify-check` y `capabilities`, más validación
semántica entre la bitácora DIABLO y los cálculos NQC. Suite ampliada: 157 tests
aprobados frente a 102 de la entrega previa.
Ver [QUALITY_GATE.md](QUALITY_GATE.md) y [CAPABILITIES.md](CAPABILITIES.md).
Ninguna de las 50 capacidades se declara completa por pasar estas pruebas.

## Grafo causal verificable entre componentes

La ejecución `local-lab` ahora emite `proof-graph.json` con 24 nodos y
un `proof_graph_root` reproducible: procedencia del código, decisiones de
alcance DIABLO, entradas numéricas, resultados del solver NQC, comprobación
independiente, bitácora y veredicto. `verify-lab` reconstruye el grafo,
comprueba todas las dependencias y rechaza modificaciones aun cuando alguien
regenere `COMPLETE.json`. Ver [PROOF_GRAPH.md](PROOF_GRAPH.md).

La suite histórica de esta rama quedó documentada con 157 pruebas previamente
ejecutadas. Esta ampliación superó **118 pruebas en el checkout local basado
en la entrega v3**, incluidos 16 tests nuevos del grafo. Esas 118 pruebas
NO incluyen los archivos adicionales de auditoría y QA incorporados a la
rama después de la entrega v3. **Falta ejecutar y certificar la suite completa
del HEAD combinado**. Ver [proof-validation.json](proof-validation.json).

El catálogo de 50 requisitos permanece en `capabilities.json`; ninguna
capacidad se acredita completa sin su propio benchmark y evidencia independiente.

## Fuzzing numérico verificable DIABLO + NQC

La fase añadida `fuzz-lab` produce hasta 256 casos sintéticos reproducibles por
semilla. DIABLO admite y audita cada caso; NQC ejecuta su solucionador económico;
una referencia independiente y dos propiedades metamórficas comprueban los
resultados. `verify-fuzz` recalcula cada caso y valida toda la bitácora.

```bash
python3 -m superhunter fuzz-lab --seed 20261103 --cases 256 --out /tmp/sh-fuzz-001
python3 -m superhunter verify-fuzz --bundle /tmp/sh-fuzz-001
```

Ver [FUZZ_LAB.md](FUZZ_LAB.md). Se trata de comprobación de modelos numéricos
**no** fuzzing EVM, PoCs, vulnerabilidades reales, pérdidas demostradas ni
certificación de las 50 capacidades. El catálogo #3 figura parcialmente
probado, y el gate central de QA exige sus pruebas.
