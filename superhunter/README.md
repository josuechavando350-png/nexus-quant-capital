# SUPERHUNTER — integración en NQC

## Comprobación conjunta y checklist

```bash
python3 -m superhunter system-check --out /tmp/superhunter-system-001
python3 -m superhunter verify-system --bundle /tmp/superhunter-system-001
```

Este recorrido reúne el laboratorio nativo, un grafo de 30 nodos de evidencia,
1,728 casos de un dominio numérico finito y el checklist de los 50 requisitos.
Solo acredita pruebas defensivas locales. No acredita un Hunter terminado.
Detalles y brecha de consistencia corregida: [CONNECTED_CHECKS.md](CONNECTED_CHECKS.md).

Los dos recorridos anteriores siguen disponibles; no se deben confundir sus resultados.

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

Suite de esta entrega: 146 pruebas ejecutadas, sin fallos, errores ni omisiones.
El laboratorio necesita Linux/POSIX, Python 3.11+ y PyYAML 6.0.3; no instala
dependencias automáticamente. Los demás adaptadores usan la librería estándar.

Las salidas requieren una carpeta nueva y privada; no se sobrescriben.
COMPLETE.json se escribe al final con hashes. No guardar casos sensibles en
este repositorio público. Código de salida 0 significa ejecución/revisión
completada, nunca vulnerabilidad confirmada.

No hay integración autónoma de los motores de búsqueda de vulnerabilidades,
Forge, forks, RPC, firma, broadcasts ni envíos de reportes. No se heredan
certificaciones históricas de NQC. Los registros anteriores VALIDATION.md y
validation-results.json se conservan como historia; los resultados anteriores
están en local-validation.json y LOCAL_LAB.md. La entrega actual está registrada
en connected-validation.json y CONNECTED_CHECKS.md.
