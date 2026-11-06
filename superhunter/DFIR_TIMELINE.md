# SH-01/SH-04 — timeline forense normalizada, validable offline

Esta primera entrega es una **pieza real y acotada** del circuito M1: conserva los bytes
originales de un manifiesto JSON de eventos normalizados y reconstruye restricciones
temporales declaradas, identificando inversiones imposibles, solapamientos inciertos
y ciclos del grafo de precedencia. Preserva el archivo original, identidades SHA-256
y un reporte que un verificador separado rehace desde la entrada y el código actual.

No lee imágenes de disco, memoria RAM ni PCAP; no verifica autenticidad de relojes,
artifacts, orígenes, firma de evidencias, causalidad ni la existencia de intrusiones.
**No detecta vulnerabilidades originales y jamás se anuncia como forense completo.**

## Contrato de entrada

JSON con raíz exacta:

```
{"schema_version":1,"profile":"normalized-evidence-timeline-v1",
 "sources":[{"source_id":"host-a","clock_uncertainty_ms":1000}],
 "events":[{"event_id":"e1","source_id":"host-a","sequence":1,
 "timestamp":"2026-11-06T17:00:00Z","kind":"process",
 "parent_event_id":null,"artifact_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}
```

Clases soportadas de evento: `process`, `file`, `identity`, `network`,
`application`, `cloud`, `other`. Los campos, tipos y límites son estrictos;
`source_id` debe estar registrado, un `(source_id, sequence)` no se duplica;
los timestamps requieren zona horaria, y cada parent debe existir.
La incertidumbre de cada reloj es una cota suministrada, no autenticada.

La salida **no confunde consistencia de datos con verdad externa**:
`DECLARED_ORDER_CONSISTENT`, `INCONCLUSIVE_ORDER` o
`DECLARED_CONSTRAINT_CONTRADICTION`, siempre con `incident_confirmed=false`,
`vulnerability_confirmed=false`, `evidence_authenticated=false`,
`causation_proved=false`.

## Reproducir

```bash
python3 -m superhunter review-forensic-timeline --input /privado/eventos.json --out /privado/revision-nueva
python3 -m superhunter verify-forensic-timeline --bundle /privado/revision-nueva
```

Las salidas son privadas, no se sobrescriben y usan `COMPLETE.json`. Si se altera
un archivo y se recalculan hashes, el verificador debe rechazar conclusiones
inventadas porque reconstruye el resultado desde `input.json` y las fuentes
actuales. Una edición coordinada de la entrada y la fuente sigue sin demostrar
autenticidad; para ello hace falta custodia de confianza externa.

## Continuación requerida

Los siguientes pasos de M1 **no están implementados**: adquisición forense real
con parsers propietarios verificados, identidad autenticada de evidencias,
correlación con trazas EVM y sensores, hipótesis causal contrastada,
experimento aislado y expediente final verificado. No marcar SH-01 ni SH-04
como terminadas basándose en este subcomponente.
