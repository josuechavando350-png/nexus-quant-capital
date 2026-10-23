# Condiciones iniciales de liquidación: revisión 11

`nqc-miner check-aave-conditions --input datos.json` reproduce, sin red, las
condiciones de `ValidationLogic.validateLiquidationCall` vinculadas al runtime
histórico de LiquidationLogic con SHA-256
`b11e141dc76358768078be0818b39d60b5b68385aed43552a617ad572e821914`.
Su resultado distingue aprobación de condiciones iniciales y ejecución completa.
Todos los indicadores de autenticación, elegibilidad ejecutable y activación
permanecen deshabilitados.

El comando acepta direcciones canónicas y enteros decimales exactos. Rechaza
campos desconocidos, desbordamientos, notación científica y ceros iniciales.
El perfil admite timestamps y periodos de gracia de hasta `2^40 - 1`; valores
posteriores se rechazan explícitamente, sin emular el truncamiento de Solidity
para fechas ajenas a este dominio. La entrada completa queda fijada por hash.

## Orden de validación

| Condición | Rechazo |
| --- | --- |
| Liquidador distinto del deudor | `SelfLiquidation` |
| Reservas de deuda y colateral activas | `ReserveInactive` |
| Ninguna reserva pausada | `ReservePaused` |
| Ambos periodos de gracia estrictamente anteriores al timestamp | `LiquidationGraceSentinelCheckFailed` |
| Salud estrictamente inferior a `1e18` | `HealthFactorNotBelowThreshold` |
| ID del colateral dentro de los 128 índices | `InvalidReserveIndex` |
| Colateral habilitado por el deudor | `CollateralCannotBeLiquidated` |
| Deuda no nula en el activo seleccionado | `SpecifiedCurrencyNotBorrowedByUser` |

El informe conserva solo las condiciones alcanzadas hasta el primer rechazo
y el selector exacto del error Solidity. La comprobación del índice ocurre
dentro de la consulta del bitmap del código original; no se adelanta sobre la
salud ni se confunde el bit de préstamo con el de colateral. Los bits de pausa
y actividad son respectivamente 60 y 56. El bit de colateral es `2 * id + 1`.

## Referencia ejecutable

`fixtures/AaveValidationHarness.sol` importa las fuentes originales sin cambiar
sus bytes e invoca directamente la función interna, en lugar de copiar sus
predicados. El generador conserva entrada y salida de solc y exige el compilador
de hash previamente verificado. El adaptador de prueba resultante se ejecuta
en REVM dentro de un estado **sintético** explícito y sin red.

La comparación cubre 539 casos, incluidos límites de salud, igualdad de gracia,
índices extremos, enteros de 256 bits, orden de errores y 512 combinaciones
aleatorias con semilla fija. Compara éxito/reversión y los bytes de error. No
compara el gas del adaptador sintético con una liquidación real. No constituye
la certificación del protocolo completo ni sustituye Foundry fuzzing.
Otros tres casos ejecutan las entradas históricas retenidas en ese mismo
adaptador sintético; tampoco se presentan como replay de una transacción.

## Lecturas históricas acotadas

`research/capture_aave_conditions.py` consulta únicamente siete getters por
proveedor y bloque: dos `getReserveData`, dos `getLiquidationGracePeriod`,
`getUserConfiguration`, `getUserAccountData` y `balanceOf` del token de deuda
variable indicado por la reserva. Todas las llamadas usan el hash del bloque
y `requireCanonical=true`; se rechazan selectores distintos, valor distinto
de cero, overrides y bloques sin fijar. La comparación exige igualdad de todos
los bytes, incluidos campos no utilizados del resultado de reservas.

Los bloques seleccionados son 26248075, 26248113 y 26248378. La identidad
compilada de esos bloques ya se auditó en la entrega anterior. Se comprueban
cadena, finalización y encabezados antes y después de leer, y nuevamente tras
consultar ambos proveedores. El auditor reproduce los registros sin red,
reconcilia los seis valores de cuenta con la publicación anterior y ejecuta
el comando nuevo con un binario de identidad conocida.

| Bloque observado | Condiciones iniciales | Primer rechazo |
| --- | --- | --- |
| 26248075 | No pasan | `HealthFactorNotBelowThreshold` |
| 26248113 | Pasan | Ninguno |
| 26248378 | No pasan | `HealthFactorNotBelowThreshold` |

El segundo resultado sigue sin demostrar ejecución completa. Los otros dos
son compatibles con cambios de estado posteriores dentro del bloque del evento;
esta muestra no identifica todavía cuáles fueron esos cambios.

Estas observaciones están al **cierre del bloque anterior**, no justo antes
de cada transacción. El liquidador procede retrospectivamente del evento.
La deuda seleccionada procede de un `balanceOf` fijado al bloque, sin afirmar
autenticación de su implementación ni equivalencia demostrada con todos los
redondeos internos del token. La ejecución local de esos valores en el adaptador
de prueba sigue siendo una ejecución sintética de condiciones, no un replay
de la transacción histórica.

Las trazas internas solicitadas a los dos endpoints públicos no devolvieron
datos utilizables; se conservan los errores de transporte observados. Esto no
prueba indisponibilidad permanente del servicio. No se cambió a una simulación
de estado final para presentarla como estado previo a la transacción.

Faltan importes máximos, polvo, bonus, comisiones, índices, liquidez,
transferencias, costes, dependencias externas y estado dentro del bloque para
certificar ejecución. Se enriquecen los mismos tres eventos. El avance global
sigue siendo **43/100** bajo los criterios originales.
