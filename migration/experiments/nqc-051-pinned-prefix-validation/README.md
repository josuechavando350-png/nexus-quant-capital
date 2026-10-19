# NQC051 — comprobación de prefijo histórico con funciones NQC037 originales y fijadas

19 de octubre de 2026. Base exacta: NQC050 `5bfa900eedb94149f4ce175c0fac83ddbff30e65`. Rama de investigación única: `research/nqc-051-pinned-prefix-validation-20261019`. Solo archivos nuevos dentro de esta carpeta. No se modifica `main`, ninguno de NQC037–050, ningún workflow, credencial, integración, despliegue o presupuesto.

## Qué se comprobó, sin cambiar el alcance

NQC050 ejecutó adaptadores de RLP/Keccak y reprodujo hashes con una implementación de rehash por separado. En NQC051 se recuperaron directamente desde GitHub el `verify.py` y el `intake.py` conservados de NQC037, cuyos blobs Git son:

- `verify.py`: `a417a48eaf4dbabc36ded493730e6ce97cecb4e8`
- `intake.py`: `c36d60ce83e73d246496bd0b72bc6cbe00d5893e`

Se extrajeron **exactamente ocho definiciones** originales: `ValidationError`, `require`, `k256`, `data_hex`, `quantity`, `validate_header`, `envelope` y `validate_step`. Cada definición fue cotejada con su SHA-256 exacto antes de compilarse en un entorno de pruebas con el RLP y Keccak ya estudiados en NQC050. Los digestos exactos y los blob SHA de los tres archivos nuevos están en `VALIDATION.json`.

**Eso NO constituye importación ni ejecución del módulo NQC037 completo.** Se ejecutó exclusivamente el segmento original de sus dos primeras operaciones (`chain` y `parent`). El wrapper deshabilita explícitamente cualquier otra operación, en particular `priority_proof` / `eth_getProof`, para no confundir comprobación de la cabecera con autenticación de estado.

## Resultado y hallazgo de procedencia

Sobre las cabeceras ya conservadas en NQC037, el `validate_header` original calculó correctamente los hashes de los bloques padre 66744161 y objetivo 66744162, incluidos campos Nitro y metadatos del padre (`sendRoot`, `sendCount`, `l1BlockNumber`). Se comprobaron la vinculación padre–objetivo y los rechazos al modificar raíz, hash, gas, metadatos o esquema.

El `inputs/parent-header.json` heredado conserva **JSON-RPC `id=6`**, mientras que la **segunda** lectura del plan NQC038 fija `id=2`. El `envelope` original **rechazó** el sobre antiguo si se intentaba ofrecer como respuesta de esa segunda lectura. En un ensayo exclusivamente local, al empaquetar los **mismos campos capturados** en un sobre de prueba artificial con `id=2`, `validate_step(parent)` los aceptó con relación al hash/raíz observados. No equivale a haber recibido ese sobre desde Triport; no se debe modificar el expediente ni marcar la petición como adquirida. Asimismo, `chain=4663` se comprobó usando una respuesta local sintética de `eth_chainId`, no una nueva respuesta autenticada.

**18/18 pruebas finales aprobaron** en Python 3.13.5. Una primera ejecución de desarrollo tuvo ocho errores de enlace accidental de una función al objeto `unittest` (`self` adicional); se corrigió el harness antes de publicarlo y la suite final aprobó. Se documentan ambas ejecuciones en `VALIDATION.json`. Los tres archivos publicados fueron releídos por el conector GitHub y sus blobs **coinciden byte por byte** con los que aprobaron localmente. Los tests no son demostraciones Merkle ni rentabilidad.

El CLI `pinned_prefix.py --repo-root ...` exige los blobs originales completos NQC037 y el overlay NQC050, verifica también que la captura del padre sigue siendo `id=6`, ejecuta las funciones fijadas en modo read-only y devuelve `CAPTURED_HEADER_VERIFIED_PROVIDER_UNAUTHENTICATED` si el checkout está íntegro. El contenedor actual no dispone de ese checkout íntegro; allí el CLI devolvió deliberadamente `BLOCKED_PIN_OR_DEPENDENCY` (exit 2), sin red. Por tanto, **no se declara completada** la comprobación del CLI contra un checkout completo ni la ejecución completa de NQC037.

## Reproducción futura con un checkout confiable

Para un ejecutor con las fuentes íntegramente fijadas (no requiere al dueño de Android):

```sh
python -m unittest discover -s migration/experiments/nqc-051-pinned-prefix-validation -p 'test_pinned_prefix.py' -v
python migration/experiments/nqc-051-pinned-prefix-validation/pinned_prefix.py --repo-root .
```

Ninguno de esos comandos acepta clave, usa red, lee RPC, firma, modifica registros o inicia una sesión de adquisición. Los tests son aptos para detectar cambios en sus ocho fragmentos originales y errores de envelope/procedencia; **no reemplazan** `account_proof`, `storage_proof.verify_mpt` ni `intake.validate_step` completo.

## Estado real y siguiente dependencia

- Lecturas Triport autenticadas: **0 de 8**. Pruebas históricas de estado adquiridas: **0**. Slots prioritarios autenticados en el preestado exacto `txIndex1`: **0/11**.
- Sigue pendiente un canal seguro soportado de credencial para este ejecutor; no se revela ni solicita al usuario el token.
- Sigue pendiente el registro operacional remoto único integrado con la validación histórica completa, con garantías de no reintento, capacidad para respuestas grandes y prevención de rollback/copia de presupuesto.
- Sin `eth_getProof` auténtico al padre y witness para ejecutar prefijo/tx0, no se autentica el preestado de `txIndex1`. Canonicidad/finalidad independientes, binario y configuración Nitro históricos, replay, captura neta y financiación siguen abiertos.
- `commercial_admission=false`. Ningún ensayo sintético o autoconsistencia de cabecera acredita ganancias ni justifica gastar gas.

**Siguiente movimiento técnico útil:** cerrar el ejecutor real con verificador NQC037 completo, registro único y canal seguro de clave para consultar solo el plan de ocho lecturas original. Si no se habilitan conjuntamente, detener las consultas; no generar otra rama ni reiniciar el contador para eludir la restricción.
