# SUPERHUNTER — reducción de corpus por cobertura *observable*

Esta unidad analiza **resultados de ejecuciones EVM locales anteriores, completamente
reproducidas**. No observa program counters, instrucciones/opcodes, ramas o mapas
internos de cobertura. Los rasgos son una clasificación de los resultados
observados: control propio, etapa persistida, clase del argumento y resultado
`COMMITTED`, `PRECONDITION_REVERT`, `ASSERTION_REVERT` o
`RESOURCE_EXHAUSTED`. Su cardinalidad **no es un porcentaje de cobertura**.

## Conexión ejecutable

`evm_sequence_fuzz.replay` vuelve a compilar y ejecutar los experimentos con
el `solc` oficial y la EVM Geth fijados por SHA-256. Una vez contrastados los
bytes de los artefactos originales, `evm_feedback.features` extrae los rasgos,
comprueba la correspondencia entre perfiles de compilación y aplica una selección
greedy determinista. El resultado se enlaza por SHA-256 a la evidencia nativa y
se registra mediante el `AuditLog` original de DIABLO. `verify-evm-feedback`
vuelve a ejecutar íntegramente el experimento fuente y recalcula el reporte.

El subconjunto es *irreducible por eliminar una sola secuencia del conjunto
seleccionado*: ninguna de esas secuencias es redundante respecto a los rasgos
observados. **No se prueba cardinalidad mínima global** ni que las secuencias no
seleccionadas sean dispensables en futuras versiones del software.

Se conserva el prefijo más corto **ya observado** que alcanza la reversión por
aserción dentro del corpus registrado. No es minimización global ni resultado de
búsqueda independiente; no se deduce una explotación ni pérdida persistente.

## Uso, sin objetivos externos

Obtener primero el hash SHA-256 del snapshot ejecutable actual de
`superhunter.quality.source_snapshot()` como ancla separada. Crear y verificar
un paquete nativo con los comandos de `FUZZ_EVM_SEQUENCES.md`.

```
python3 -m superhunter review-evm-feedback \
  --native-bundle /privado/fuzz-nativo \
  --solc /privado/solc --evm /privado/evm \
  --expected-source HASH_EXTERNAMENTE_COMPROBADO \
  --out /privado/reporte-nuevo

python3 -m superhunter verify-evm-feedback \
  --bundle /privado/reporte-nuevo \
  --native-bundle /privado/fuzz-nativo \
  --solc /privado/solc --evm /privado/evm \
  --expected-source HASH_EXTERNAMENTE_COMPROBADO
```

Solo acepta los dos contratos aritméticos propios y los presupuestos existentes
de 9 a 24 secuencias, cuatro llamadas por secuencia. No lee ni ejecuta
bytecode, transacciones o calldata suministrado dentro del reporte: el replay
los regenera desde el código fijado. La evidencia completa es privada.

## Límites de evidencia

- Los dos perfiles usan el mismo compilador y el mismo motor Geth EVM; son
  generación alternativa de bytecode, no ejecución por motores independientes.
- Las reglas para seleccionar los rasgos están definidas por código. No existe
  un universo conocido de todas las rutas o vulnerabilidades posibles.
- El motor **no genera todavía nuevas entradas adaptativas** ni busca
  automáticamente fallos desconocidos: solo orienta qué secuencias del corpus
  previamente ejecutado merecen retenerse.
- La comprobación externa de identidad de código es una huella local, no una
  certificación de producción ni autenticación de quién hizo la ejecución.
- `ASSERTION_REVERT` implica deshacer cambios de esa llamada, no transferencias
  fraudulentas ni derechos a una recompensa.
- No hay RPC, despliegue, interacción con programas de terceros, gestión de
  secretos, trading o divulgación automática.

## Pendientes posteriores

Un fuzzer con instrumentación real de cobertura de EVM y mutaciones que *se
ejecuten y midan* iterativamente, validación en un segundo motor EVM
independiente, minimización diferencial de trazas y evaluación ciega. No se
infiere ninguna de estas capacidades de este análisis observable.
