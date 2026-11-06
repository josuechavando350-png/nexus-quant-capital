# SUPERHUNTER — prueba de vínculo por bytes entre journal y traza EVM

**Alcance:** importación offline de una exportación existente de `journalctl -o json`, previamente procesada con `ingest-journal`, junto con una traza **Geth JSONL** de un contrato propio, un contexto de bytecode/observación y el hash SHA-256 exacto de esa traza dentro del registro de journal.

No ejecuta Geth, `evm`, `solc`, Forge ni contratos; tampoco adquiere logs, consulta RPC o accede a programas de terceros. El módulo **sí reutiliza el analizador real** `evm_opcode_trace.decode_trace`, que interpreta PCs e instrucciones, valida saltos y comprobación de la salida observada contra el terminal declarado. Los tests crean trazas de laboratorio con formato Geth: NO son pruebas de ejecución blockchain independiente.

## Entrada y relación estructural

1. Crear un archivo de texto de traza JSONL compatible con Geth y fijar su SHA-256. Una línea del `journalctl` local debe incluir el campo `SH_EVM_TRACE_SHA256` exactamente igual al SHA-256 de **todos** los bytes originales de la traza, no al digest de un JSON normalizado.
2. Generar el paquete de evidencia con el comando existente `ingest-journal`.
3. Proveer un `context.json` con:

```json
{
  "schema_version": 1,
  "profile": "owned-offline-evm-journal-byte-binding-v1",
  "bytecode_hex": "60055760005b00",
  "gas_budget": 2000000,
  "observed": {"return_data": "0x", "error": null},
  "journal_event_id": "j000000-REEMPLAZAR_CON_ID_DEL_NORMALIZADOR"
}
```

`gas_budget` es el presupuesto real permitido por `evm_execution.GAS` (2,000,000 en este commit) o `1`. No sustituirlo por una cantidad arbitraria. El `journal_event_id` debe coincidir exactamente con el evento seleccionado en el paquete del ingestador, no con una cadena arbitraria. No se admiten campos extra, timestamps inferidos, perfiles ajenos ni bytecode no canónico.

```bash
python3 -m superhunter review-evm-forensic \
  --journal-bundle /privado/journal-verificado \
  --trace /privado/evm-trace.jsonl --context /privado/context.json \
  --out /privado/evm-journal-nuevo

python3 -m superhunter verify-evm-forensic \
  --bundle /privado/evm-journal-nuevo \
  --expected-complete-sha256 SHA256_GUARDADO_FUERA_DEL_PAQUETE
```

El verificador vuelve a calcular, a partir de los cuatro originales preservados, cada offset y hash de registro, la concordancia de ancla SHA-256 con la traza, los PCs e instrucciones y el contenido del reporte. Rechaza modificaciones incluso si se recalculó el manifiesto. `COMPLETE.json` se firma **solo por hash**, no por identidad o firma digital; el argumento opcional permite cotejarlo con una ancla custodiada externamente.

## Estados y límites que no pueden convertirse en PASS falsos

`TRACE_AND_JOURNAL_BYTES_BOUND_UNAUTHENTICATED` significa **coincidencia de bytes** de dos aportaciones del operador, no prueba de que el EVM se ejecutó. El campo temporal es del log, nunca del opcode. Los productores pueden falsificar simultáneamente la traza, el log y su hash; una fuente independiente necesitaría firmar o autenticar los originales. `evm_execution_replayed_here=false`, `execution_timestamp_authenticated=false`, `cross_source_causation_proved=false`, `vulnerability_confirmed=false` e `incident_confirmed=false` se preservan.

Los casos originales conservan datos sensibles (`MESSAGE`, contexto y traza) y solo se escriben en directorios privados fuera del repositorio. No subir el expediente a GitHub. El siguiente paso de M1 es comprobar esta asociación contra **ejecución EVM independiente y autorizada**, y posteriormente enlazarla con el grafo multifuente sin inventar causalidad.
