# Auditoría del comprobador de condiciones iniciales Aave

Fecha de captura: 23 de octubre de 2026 UTC. Avance global: **43/100**,
sin alterar los pesos ni cerrar una fase operativa.

## Cambio entregado

Miner incorpora `check-aave-conditions`, un comando sin red que reproduce la
función inicial de validación de la revisión 11 identificada en Ethereum.
Devuelve las condiciones alcanzadas, el primer error y su selector Solidity.
Rechaza entradas ambiguas o fuera de rango y mantiene deshabilitadas las
afirmaciones de ejecución, autenticación y activación.

El modelo Rust se compara contra una compilación de las fuentes Solidity
retenidas. Un adaptador sintético importa esas fuentes sin cambiarlas y llama
a `ValidationLogic.validateLiquidationCall`; no reimplementa los predicados.
REVM ejecuta ese adaptador con estado cerrado, explícito y sin red. Se
comparan éxito/reversión y el contenido exacto del error en **539 casos
sintéticos**, incluidos 512 casos de semilla fija. Se cubren todos los ocho
errores posibles y la aceptación. Otros **tres casos** utilizan las entradas
históricas capturadas dentro del mismo adaptador sintético.

## Muestra histórica y resultado

La captura añade configuración de reservas y usuario, gracia y deuda del
activo a los mismos tres estados anteriores a los eventos ya existentes.
Los siete getters por bloque/proveedor producen 21 acuerdos y 42 respuestas;
tres acuerdos repiten los valores de cuenta para conciliarlos con la captura
anterior. No son eventos nuevos ni 21 estados distintos.

| Bloque | Resultado de condiciones iniciales | Motivo |
| --- | --- | --- |
| 26248075 | Rechazo | Salud no inferior a uno |
| 26248113 | Aceptación inicial | Ningún rechazo en la función inicial |
| 26248378 | Rechazo | Salud no inferior a uno |

El liquidador se obtiene retrospectivamente del evento. Los valores están al
cierre del bloque anterior, sin efectos posteriores dentro del bloque del
evento. La lectura de deuda procede de `balanceOf` del token variable declarado
por la reserva; no se presenta como autenticación de esa implementación externa.
La aceptación del segundo estado no demuestra que una liquidación completa
con importes y transferencias determinados vaya a ejecutarse.

## Controles ejecutados

- Captura de 96 registros de solo lectura, incluyendo cadena, finalización,
  hashes y comprobaciones posteriores a las consultas de ambos proveedores.
- ABI de retorno exacto, anchuras de enteros/direcciones, selectores de solo
  lectura y `blockHash` con `requireCanonical=true`. No se permiten overrides.
- Igualdad de todos los bytes de retorno, incluidos campos no usados de reservas.
- Reproducción sin red, vínculo con la publicación `3dfb0b5`, comparación de
  los seis valores de cuenta anteriores e identidad del binario antes/después.
- Pruebas de errores de bloque/cadena, ABI, ausencia de datos, desacuerdo,
  selectores distintos y modificaciones que intentan ocultarse regenerando hashes.
- Auditoría general de Rust y Python, Clippy con advertencias como errores,
  formato, correspondencia de fuentes/binario y aislamiento. Los recuentos
  definitivos están en `evidence/aave-conditions-20261023/offline/summary.json`.

El primer intento Rust se detuvo por una anotación de tipo ausente en una
prueba; `rust-preflight.txt` conserva la salida y la corrección pasó las
comprobaciones posteriores. Dos solicitudes de trazas internas no devolvieron
datos utilizables y quedan registradas como HTTPError, sin adjudicarles un
código de estado no retenido. No se sustituyeron por trazas inventadas ni se
afirma indisponibilidad permanente del servicio.

El nuevo binario corresponde al commit
`5e88d25e72c4b03ad5e6acfca76e9a02fd501a21`; su historial se conserva en un bundle
verificado que parte de `cc4abee`, recuperable del bundle anterior. Los hashes
del binario, captura, auditor y publicación están en los informes y manifiestos.
Esto no supone una compilación hermética ni autenticación criptográfica de
estado Ethereum.

## Aislamiento y pendientes

Todos los cambios están en `migration/nqc-miner/`. Observer, las fuentes
originales y las evidencias nativas Termux permanecen intactos. No se habilita
ningún servicio, workflow, firma, transacción o gasto.

Siguen pendientes el recorrido completo de liquidación, importes máximos,
polvo, bonus/comisiones, índices, liquidez y transferencias; las dependencias
externas autenticadas; el estado inmediatamente anterior a cada transacción;
la ejecución con el fork real de la cadena y las pruebas completas de Foundry
e integración operativa. Esta entrega aporta una parte comprobada del adaptador,
sin certificar el protocolo completo ni conceder puntos adicionales.
