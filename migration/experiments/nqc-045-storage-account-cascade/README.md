# NQC045 — cascada sintética storage → cuenta → stateRoot

19 de octubre de 2026. Base durable NQC044: `09eb7e446cc7bd8102ac6de073ef4038fb508984`. Solo archivos nuevos de este experimento; anteriores y plan NQC038 sin cambios. El cierre acumulado se encuentra en [CIERRE.md](CIERRE.md).

## Qué se comprobó

`cascade.apply_slot()` comprueba cuenta y slot mediante NQC043/NQC037; exige cuenta presente; aplica una sola mutación de almacenamiento mediante NQC044; sustituye únicamente el campo storageRoot del RLP de cuenta; actualiza esa hoja en el trie de cuentas. Usa las dos pruebas ligadas a sus raíces originales, no intercambia storageRoot por stateRoot. No necesita los bytes del código para cambiar esos tries, pero tampoco afirma haberlos verificado o ejecutado.

El cero se representa borrando la hoja de almacenamiento, no almacenando RLP(0). El borrado de la última hoja deja storage vacío sin borrar automáticamente la cuenta. La creación o eliminación de cuentas, la limpieza de cuentas vacías del protocolo y SELFDESTRUCT están fuera del alcance y no se implementan.

Con dos cuentas inventadas y dos slots en la cuenta objetivo, borrar un slot exige el hermano identificado por NQC044. Sin él se devuelve `BLOCKED_STORAGE_NODE`, con ambas raíces candidatas en `null`. Al añadir el nodo del generador sintético y verificar su hash, se obtiene una raíz global que coincide con una reconstrucción completa. La prueba posterior de referencia se verifica contra esa raíz candidata usando el walker MPT preservado. Nonce, balance y codeHash conservan exactamente sus bytes; la cuenta vecina mantiene sus campos y almacenamiento.

Los generadores completo y parcial usan la misma biblioteca de actualización `trie==4.0.0`; su coincidencia **no es una implementación independiente de las actualizaciones**. La lectura posterior usa el verificador separado NQC031. El cálculo independiente de raíz de hoja única de NQC044 también sigue cubierto por la regresión, pero no se presenta como verificación independiente de toda la cascada.

`evidence/SYNTHETIC_CASCADE.json` conserva inputs y outputs. Todos son inventados: direcciones 1 y 2, nonce 7, balance `2**200+31`, código `0x6000`, slots 9=77 y 13=88; una cuenta vecina sirve de control. **No son valores del PairOracle ni del estado Robinhood.** No se alimentó el diagnóstico histórico al mutador ni se completaron sus huecos con ceros.

## Alcance estricto

El llamante ordena una mutación de slot; no se ejecuta bytecode o transacción, no se decide si esa escritura sería legítima, no se aplican hooks/gas/refunds/forks ni se produce un witness de replay. El helper permite verificar una relación algebraica entre tries, no certificar una transición de la cadena. `raw_trie_cascade_completed=true` es distinto de `nitro_replayed`, `historical_position_authenticated` o `complete_parent_witness`, siempre falsos. `commercial_admission=false`.

Cada intento trabaja con bases de datos desechables, sin red, firmas, credenciales ni persistencia operativa. Cualquier error de lectura se rechaza. Un bloqueo de escritura no expone raíces candidatas; la política del segundo nivel se prueba por inyección de fallo, no se afirma que esa geometría suceda naturalmente al reemplazar una cuenta existente del mismo tamaño. No hay búsqueda ni descarga automática de nodos, reintento RPC o ampliación del presupuesto.

## Reproducción y verificación

```sh
python migration/experiments/nqc-045-storage-account-cascade/validate.py
```

Con las dependencias ya usadas en NQC037/044, el runner verifica primero los hashes fijados, genera evidencia en NQC045 y ejecuta cada suite en un proceso separado. `VALIDATION.json` y logs contienen el resultado efectivo. La regresión consolidada comprende 16 casos nuevos, 74 de NQC040–044, 32 del verificador NQC037, 7 del transporte NQC038, 2 del exportador NQC039 y 9 de aislamiento: **140 pruebas**, más el verificador de aislamiento. No se suman los totales repetidos de las rondas previas.

Casos nuevos: bloqueo sin raíces, coincidencia con reconstrucción completa y prueba posterior, preservación de campos y vecino, distinción entre raíces, borrado del último slot, cero canónico, no-op, inserción desde ausencia probada, rechazo de creación de cuenta, pruebas/campos incompletos, límites uint256, nodo adicional inválido, fallo inyectado en segundo nivel, no mutación de inputs y puertas cerradas.

No se ejecutó Go/Nitro, Rust, adquisición histórica ni replay económico. No se reejecutó la auditoría KZG de NQC036. La búsqueda acotada de capacidades disponibles no identificó un canal soportado nuevo para la credencial; no se repitieron búsquedas de proveedores, transferencias ni consultas Blockscout. No se solicitó ninguna acción desde el teléfono.
