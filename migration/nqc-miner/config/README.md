# Configuración y evidencia separadas por ejecución

El CLI admite JSON estricto, con `namespace=nqc_miner_v1`, `producer=nqc-miner`,
identidad de commit, hash de `Cargo.lock`, clase de evidencia y scopes explícitos.
Un scope declara cadena, contrato, firma del evento, intervalo inclusivo, tamaño
del lote y al menos dos proveedores. Consulta `src/config.rs` para el contrato
completo. Las variables RPC pertenecen exclusivamente al prefijo `NQC_MINER_RPC_`.

La configuración de una ejecución real debe obtener su identidad de
`nqc-miner about` después de construir el commit correspondiente. `scan` rechaza
binarios con cambios de código sin commit, identidades distintas y presupuesto
de gas positivo. `validate-config` no conecta a ninguna red.

Para un registro histórico nuevo:

1. Define el intervalo exacto de bloques finalizados y los contratos utilizando
   referencias oficiales fijadas a un commit cuando estén disponibles.
2. Construye y valida una configuración con `data_class=historical`, un `run_id`
   nuevo y ambos controles de firma/puente en `false`.
3. Proporciona los endpoints mediante variables propias de Miner, fuera del
   repositorio. Usa `scan` con un directorio nuevo. El programa verifica cadena,
   acuerdo entre proveedores y bloques finalizados antes de cerrar cada scope.
4. Conserva juntos `owner.json`, `config.json` y `events.jsonl`. `verify-journal`
   y `report` permiten reconstruir y revisar el resultado sin RPC.

Las muestras públicas documentadas en `evidence/` son ventanas acotadas de prueba
de integración. No constituyen un inventario completo de cadenas, un feed continuo
ni evidencia de rentabilidad. No se copian credenciales o datos del observador.

## Reanudación y cambios de cadena

Reanudar requiere la misma configuración y el mismo directorio. Los lotes y
registros ya comprometidos se concilian; el cierre completo de scope es un evento
separado. Un fallo en su comprobación final deja el scope incompleto.

Se revalidan los bloques conocidos de todos los scopes de una cadena antes y
después de cada escaneo. Una contradicción deja en cuarentena todos los intervalos
dependientes de esa cadena, incluidos scopes ya terminados. El registro original
se conserva y se requiere una ejecución nueva. Los hashes y el acuerdo RPC
establecen consistencia; no autentican por sí solos el estado de la cadena.
