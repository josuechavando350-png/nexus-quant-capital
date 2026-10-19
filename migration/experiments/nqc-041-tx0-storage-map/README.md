# NQC041 — mapa de dependencias de estado de tx0

## Hallazgo nuevo y alcance

El preestado **diagnóstico** ya conservado contiene `ArbOSVersion=61`, longitud
del vector de restricciones simples **2** y longitud multigas **0**. Aplicando
`GasModelToUse` de las fuentes candidatas fijadas, selecciona **single**, no
multigas ni legacy. La versión 61 por sí sola no determina el modelo.

Los dos backlogs simples están presentes; sus targets y adjustment windows no.
También faltan los dos punteros de la cola de retryables, el contador L1 de
blockhashes y los controles de actualización de ArbOS. Ausencia en un tracer
parcial **no equivale a cero ni a prueba de inexistencia**.

Esto no prueba el modelo activo en el bloque padre: el artefacto diagnóstico es
del preestado de la transacción objetivo, no una fotografía autenticada anterior
a tx0. Tampoco demuestra que estas fuentes sean el binario histórico ejecutado.
No se calcula una tarifa, un beneficio ni un nuevo estado raíz.

## Qué se ejecutó

Se recuperó NQC040 de GitHub antes de comenzar; base
`bfed312ca1675aaa8869b8788bfc3b501243f1a0`. Se añadieron únicamente archivos de
este experimento. `storage_map.py` deriva selectores sin red; `validate.py` los
compara con el diagnóstico existente y genera `SLOT_MAP.json`, conservando los
ausentes como `null`. No modifica ni amplía `TRIPORT_PLAN.json`.

Se leyeron nueve archivos adicionales de fuentes públicas fijadas y se
conservaron byte por byte, con tamaño y Git blob SHA comprobados en las pruebas.
Nitro: `3599acae1ad2fab4059fc46453c9cd3294126641`; go-ethereum:
`f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88`. `SOURCES.json` contiene sus URLs;
las licencias completas permanecen en el vendor NQC037 referenciado allí.
`SOURCE_BINDING.json` vincula los inputs, fuentes y plan previos por SHA-256.

Se ejecutaron **55 pruebas offline**: 14 del mapper, 32 del verificador histórico
y 9 de aislamiento; además pasó el verificador de aislamiento. Las pruebas de
slots son sintéticas/comparativas, no pruebas Merkle históricas. No se ejecutó
Nitro, Rust, replay EVM, pruebas económicas ni adquisición RPC. Los logs y sus
hashes están en `VALIDATION.json` y `evidence/`.

## Derivación exacta de direcciones

Sea `H` Keccak-256 (no SHA3-256), raíz de namespace `K = bytes vacíos`.
Cada descenso aplica `K = H(K || id)` por separado. Para una clave lógica de
32 bytes `u`, el slot físico es `H(K || u[0:31])[0:31] || u[31]`.
Se retiene el último byte; **no** se hashea la clave completa de 32 bytes.

Los namespaces raíz de precios L2, retryables y blockhashes son respectivamente
`01`, `02` y `06`. Una entrada de vector usa como id su índice **uint64 big-endian
de ocho bytes**, no uint256. Todos estos slots pertenecen a
`0xa4b05fffffffffffffffffffffffffffffffffff`.

| Dependencia | Layout derivado | Estado necesario para continuar |
|---|---|---|
| Selección de precios | L2/00 y L2/01: offset 0 es longitud | Versión y ambas longitudes; falta una no significa cero |
| Restricción simple i | L2/00/BE64(i): offsets 0 target, 1 window, 2 backlog | Valores al inicio efectivo del cálculo |
| Restricción multigas i | L2/01/BE64(i): 0 target, 1 window uint32, 2 backlog, 3 maxWeight, 4..12 pesos | Longitud y campos; el código usa maxWeight, no el sumWeights del comentario |
| Tarifas multigas | L2/02: 0..8 next, 9..17 current | Incluye dimensión Unknown=0; rotación current ocurre fuera de este mapa de tx0 |
| Cola | Retryables/00: 0 nextPut, 1 nextGet; datos desde offset 2 | Punteros y ticket de la cabeza; no es un ring de módulo 256 |
| Ticket | Retryables/ticketId: campos 0..6; subespacio 01 para calldata | Timeout, windows, beneficiario, longitud y chunks según rama |
| Blockhashes | 06: 0 contador L1, 1+(n mod 256) hash | Contador anterior para determinar si escribe y qué huecos rellena |
| Upgrade | Raíz: 0 versión, 1 upgradeVersion, 2 upgradeTimestamp | Si se activa, se abre otra rama de efectos aún no enumerada |

`SLOT_MAP.json` muestra direcciones exactas y coincidencias diagnósticas.
La unión de 16 controles/candidatos incluye límites L2 y campos legacy para
comparación; no afirma que todos se lean en tx0 ni que la unión sea completa.

## Dependencias dinámicas que no se pueden cerrar con una lista estática

`startBlock(0,26008731,66744162,1)` llama dos veces a `TryToReapOneRetryable`.
Las llamadas son secuenciales: si la primera cabeza sigue viva, la segunda
vuelve a ella; no se deben solicitar dos tickets distintos por suposición.
Si timeout=0, se descarta la entrada sin leer windows. Con timeout no nulo,
se lee windows antes de comprobar si timeout >= timestamp. Si venció, se
extrae la entrada y se borra el ticket o se extiende timeout según windows.
Puede haber ids repetidos en la cola; la segunda llamada ve los cambios de la
primera. El mapper calcula direcciones, no simula esos cambios ni sus errores.

La eliminación requiere además el estado de la cuenta escrow
`last20(H("retryable escrow" || ticketId))` y del beneficiario para transferir
saldo, y los slots de calldata: longitud en 0 y chunks en 1..ceil(length/32).
No se inventan ids, longitudes, balances ni valores de slots ausentes.

El target del registro L1 sería 26008730 solo si el contador previo activa la
rama. La fuente puede rellenar huecos adicionales antes de escribir el target
y el contador; el slot target por sí solo no cubre esa rama. La escritura del
hash padre al contrato de historial de bloques sigue siendo otro efecto,
descrito en NQC037, separado del namespace ArbOS blockhashes.

En precios simples, tx0 lee target/backlog y reduce backlog con timePassed;
solo si queda positivo usa adjustmentWindow. En multigas también dependen de
los pesos y maxWeight. No se aplica el viejo máximo de 20 restricciones como
límite de protocolo para ArbOS 61. El mapa no enumera un vector de longitud
arbitraria ni convierte un truncamiento local en witness completo.

## Frontera y siguiente tramo verificable

Continúan **cero consultas Triport autenticadas y cero pruebas históricas**.
La revisión de herramientas expuestas no añadió un canal de credencial seguro.
No se volvió a intentar la transferencia fallida; no hubo acceso a la clave,
consultas Blockscout, nuevas cuentas, servicios ni gastos. El proveedor sigue
sin probarse: no se le atribuye un fallo. El exportador anterior no se presenta
como solución Android verificada; no se exige instalar nada al usuario.

Antes de cualquier lectura autorizada siguen faltando el canal soportado para
la credencial y el registro operativo durable único de NQC040. El presupuesto
permanece ocho lecturas en total, no ocho por experimento. Este mapa **no es un
segundo plan RPC autorizado**; las ocho respuestas originales no cubren estas
dependencias adicionales ni bastan para demostrar el preestado de txIndex1.

Siguiente cuestión offline acotada: determinar qué hooks de ProduceBlockAdvanced
ocurren antes de tx0 y si alteran precios/estado respecto al stateRoot padre.
Eso evita asumir que basta ejecutar el cuerpo de startBlock sobre el padre.
Después habría que vincular el binario/configuración históricos y demostrar
el estado de cada rama necesaria antes de intentar replay; datos diagnósticos
del objetivo no pueden usarse como sustituto silencioso del padre.

`commercial_admission=false`: sin canonicidad independiente, preestado exacto,
replay Nitro ni rentabilidad probada. La investigación sigue abierta.

## Reproducción por el ejecutor

Con las dependencias NQC037 ya disponibles, desde la raíz del repositorio:

```sh
python migration/experiments/nqc-041-tx0-storage-map/validate.py
```

El script no usa red y escribe únicamente resultados dentro de este experimento.
Los tiempos de los logs pueden cambiar al repetir pruebas; los mapas de slots
y los bytes de las fuentes son deterministas. No es una tarea para el teléfono.
