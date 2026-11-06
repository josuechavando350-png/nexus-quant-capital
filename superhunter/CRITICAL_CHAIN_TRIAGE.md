# SuperHunter — Evidence-Constrained Critical Chain Triage (M1 / investigación offline)

**Funcionalidad real y limitada:** ordena hipótesis de defectos individuales y *cadenas* de impactos potencialmente críticos, incluso si parten de observaciones de impacto bajo y medio. **No es un descubridor de vulnerabilidades, un clasificador CVSS, ni una herramienta de explotación**. Su resultado es una prioridad de investigación reproducible, nunca una declaración de vulnerabilidad o gravedad confirmada.

## Dependencias funcionales (verificadores, no nombres de módulos)

- `forensic_timeline.verify(bundle)`: recalcula coherencia de eventos y relojes. Cada referencia apunta a un `event_id` verdadero de su timeline verificada.
- `journal_correlation.verify(bundle)`: reconstruye fuentes, bytes, offsets y las hipótesis temporales originales. Cada referencia apunta a un `event_id` exacto de `event_proofs`.
- `evm_bounded_replay.verify(bundle)`: vuelve a ejecutar el intérprete independiente de pila/PC; cada referencia apunta al SHA-256 de la traza de `semantic.json`, no a una palabra arbitraria.

El programa verifica los originales y guarda `source-pins.json` con hashes de `COMPLETE.json`, estados del verificador e identidades de objetos. Esos hashes prueban consistencia local, **no autenticidad remota ni relación causal**. Nunca confundir soporte observacional con prueba del impacto. Los registros y expedientes privados permanecen en las carpetas fuente y NO se publican en GitHub.

## Formato de entrada

`hypotheses.json` (privado):

```json
{
  "schema_version": 1,
  "profile": "offline-critical-chain-research-v1",
  "scope": {"program_id": "controlled-lab", "scope_id": "scope-1", "policy_sha256": "<64 hex>", "authorization": "OPERATOR_DECLARED"},
  "observations": [
    {"observation_id": "a", "asset_id": "contract", "domain": "evm", "impact_hint": "low", "evidence_refs": [{"source_id":"timeline", "object_id":"ev1"}]},
    {"observation_id": "b", "asset_id": "api", "domain": "api", "impact_hint": "medium", "evidence_refs": [{"source_id":"timeline", "object_id":"ev2"}]}
  ],
  "links": [{"from":"a", "to":"b", "relation":"enables", "evidence_refs":[]}],
  "candidates": [{"candidate_id":"combined", "observation_ids":["a","b"], "kind":"chain", "potential_impact":"critical", "lab_cost_units":5}]
}
```

`source-map.json` (privado, NO incluido en salida):

```json
{"schema_version":1, "sources":[{"source_id":"timeline", "kind":"forensic_timeline", "bundle_path":"/ruta/privada/al-bundle-verificado"}]}
```

Comandos desde la raíz del repositorio, siempre sobre carpetas nuevas:

```sh
python3 -m superhunter triage-critical-chains --input /privado/hypotheses.json --sources /privado/source-map.json --out /privado/triage-nuevo
python3 -m superhunter verify-critical-triage --bundle /privado/triage-nuevo --sources /privado/source-map.json
```

El verificador **requiere nuevamente los originales externos**. Sin ellos no puede declarar aprobado. Los pares `(source_id,object_id)` deben existir en artefactos que superaron los verificadores anteriores. El manifiesto no concede permisos de prueba activa; incluso `OPERATOR_DECLARED` no acredita autorización.

## Ranking explícito, nunca probabilidad calibrada

Score determinista de investigación: peso de `potential_impact` declarado (desconocido 50, bajo 150, medio 400, alto 700, crítico 1000), más 30 por observación con una referencia a un bundle local no contradicho, más 12 por enlace con referencia, más 40 por cadena, menos 100 por cada observación/enlace sin referencia verificable local, menos `lab_cost_units` (0–100). Truncado a cero. Desempates por ID. **Nunca transforma la suma de severidades baja + media en crítica**: solo el operador propone un impacto potencial para investigar. Un enlace con hash coincidente no demuestra causalidad.

`NEEDS_SCOPE_REVIEW`: la autorización ni siquiera está declarada; `NEEDS_EVIDENCE`: faltan referencias para algunos pasos; `READY_FOR_AUTHORIZED_LAB_REVIEW`: solo disponibilidad y consistencia local de referencias (no autorización autenticada). 

**Nunca** genera `CRITICAL_CONFIRMED`, explotación, activo remoto, hallazgo confirmado, pago estimado o permiso de escaneo. Una hipótesis importante queda como **hipótesis** hasta reproducir y revisar su impacto independientemente.

## Límites medidos y próximo gate

Hasta 8 fuentes, 128 observaciones, 128 relaciones (DAG), 32 hipótesis, 12 observaciones por candidato. Rechaza fuentes duplicadas, grafos cíclicos, referencias inventadas, chains desconectadas, sources alteradas y reclamaciones falsas, incluso si se recalculan hashes externos del manifiesto. Recalcula el resultado con las fuentes actuales en otro proceso.

Siguiente hito: acoplar pruebas de impacto económico reales y autorizadas, un validador de alcance auténtico y un expediente de hallazgo que contenga experimentos independientes antes de evaluar severidad confirmada. Comparar utilidad frente a priorización simple en casos ciegos; no afirmar superioridad a otros sistemas sin evidencia.
