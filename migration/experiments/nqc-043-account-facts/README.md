# NQC043 — existencia y metadatos de cuenta preservados

19 de octubre de 2026. Base recuperada de GitHub: NQC042,
`7a6b141bd8a50349afbc13dcd79ab5234cdaaa80`. Solo se añaden archivos de este
experimento. Cero RPC autenticados y cero pruebas históricas nuevas.

## Problema demostrado, sin exagerar su gravedad

El verificador NQC031 preservado y la capa NQC037 **sí comprueban** la prueba de
cuenta, su nonce, balance, storageRoot y codeHash. Sin embargo, el resultado
descarta la existencia de la cuenta, nonce, balance y storageRoot; conserva el
codeHash, valores de slots y puertas cerradas. Las respuestas originales no se
perdieron: el intake guarda sus envelopes. La limitación está en la proyección
del resultado que consumiría un siguiente módulo.

La prueba `test_legacy_discards_validated_fields_new_layer_preserves_them`
demuestra la omisión con un trie sintético. No demuestra aceptación de una
prueba falsa, vulnerabilidad del proveedor ni error en una ejecución histórica.
No se modifica el algoritmo MPT ni se atribuye al verificador un fallo que no
se observó.

Esto importa para la cuenta auxiliar de NQC042: un futuro replay necesita saber
si está presente y qué nonce tiene antes de asignar 1. Cero balance o código
vacío no bastan para decidir que una cuenta no existe.

## Capa nueva, sin sustituir silenciosamente la anterior

`account_facts.verify_account_facts()` invoca primero la validación completa
original y luego recupera el indicador de inclusión del mismo camino MPT.
Devuelve además:

| Campo | Significado |
|---|---|
| `account_existence=PRESENT` | La hoja de cuenta está incluida contra la raíz suministrada |
| `account_existence=PROVEN_ABSENT` | No inclusión demostrada contra esa raíz; no una prueba faltante |
| `nonce`, `balance_wei` | Campos ya comprobados, como strings decimales sin pérdida |
| `storage_root` | Raíz del storage vinculada a la cuenta; vacía en ausencia probada |
| `code_bytes_checked` | Distingue codeHash probado de bytes de código realmente recibidos y comprobados |

La API rechaza entradas incompletas; no produce una tercera respuesta aceptada
con datos inventados. Un proof vacío solo es suficiente cuando la raíz de trie
vacío ya establece la ausencia. Bajo una raíz no vacía, faltar el nodo necesario
produce rechazo. Se conserva el conjunto exacto de slots solicitados: omitir
uno tampoco lo convierte en cero.

La función específica `verify_auxiliary_parent_account(proof)` fija la cuenta
`0xa4b0500000000000000000000000000000000001` y la raíz padre observada
`0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a`.
No permite reemplazar la raíz o dirección mediante argumentos. **No contiene
una consulta RPC ni autoriza una novena lectura**. Es un punto de recepción
offline para una eventual exportación autorizada; hoy no hay tal prueba.

Los receptores/transportes NQC037–040 siguen intactos y no llaman automáticamente
a esta nueva API. No se generó otra versión del exportador ni se modificó el
plan actual. Un consumidor futuro debe elegir explícitamente esta salida.

## Comprobaciones ejecutadas

**58 pruebas offline aprobadas**: 17 nuevas, 32 del verificador original y 9
de aislamiento; también pasó el verificador de aislamiento. Se probaron:

- Inclusión de cuenta en un trie con varios niveles y rechazo de nodo faltante.
- No inclusión en trie no vacío por divergencia de hoja, hijo vacío de rama y
  divergencia de extensión; los tres caminos se comprobaron también mediante
  `HexaryTrie.get_from_proof`, implementación independiente del walker local.
- Raíz vacía, nonce cero con cuenta presente, balance cero y código vacío.
- Declaraciones falsas de ausencia, campos alterados, código incorrecto,
  cuentas/raíces diferentes, campos y slots omitidos, enteros no canónicos.
- Conservación de enteros grandes, no mutación de inputs y puertas cerradas.
- Rechazo de una prueba sintética válida por la API fijada a la raíz histórica.

`evidence/SYNTHETIC_CASES.json` guarda cinco casos con inputs y resultados,
etiquetados explícitamente como generados localmente. **Ninguno corresponde al
estado histórico de Robinhood.** Las pruebas no ejecutan Nitro ni actualizan
un trie para producir el stateRoot siguiente. No se ejecutó Rust, Go, replay
económico ni las suites de transporte/exportador sin cambios.

Reproducción por el ejecutor, con las dependencias NQC037 ya disponibles:

```sh
python migration/experiments/nqc-043-account-facts/validate.py
```

El script verifica primero hashes fijos de las dependencias y del plan, luego
genera evidencia solo en este directorio. No usa red. `SOURCE_BINDING.json`,
`VALIDATION.json` y `MANIFEST.json` conservan las identidades y logs; no son
firmas de consenso ni un registro operativo de consumo de RPC.

## Qué sigue faltando

La revisión de capacidades documentadas/expuestas no aportó un canal seguro
para la clave. No se repitió la transferencia fallida, no se accedió a la clave
y no se usó Blockscout. Siguen pendientes ese canal y el registro operativo
durable único; la capacidad histórica de Triport continúa sin ensayarse.

Esta capa tampoco demuestra que una prueba de lectura baste para **modificar**
el trie y obtener la nueva raíz. Esa es la siguiente cuestión offline concreta:
delimitar los nodos adicionales necesarios al crear/modificar cuentas desde un
witness parcial, sin fabricar hermanos del trie ni llamar replay a una lectura.
No ampliar el plan de ocho lecturas para resolverla sin nueva autorización.

`complete_account_storage=false`, `state_transition_executed=false` y
`commercial_admission=false`. El preestado exacto txIndex1, la identidad del
motor histórico y la canonicidad independiente permanecen abiertos. Ninguna
acción se requiere del teléfono del usuario.
