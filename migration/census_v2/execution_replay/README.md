# Ejecución y destino del excedente

Prioridad del 9 de octubre de 2026: comprobar financiación, repayment y costes,
además de continuar la cobertura histórica. **Census sigue abierto.**

Incremento posterior: [comparación Aave/Balancer y pago atómico](FUNDING.md).
Las variantes nuevas se reproducen sin red y muestran un residual positivo
antes de gas al usar Balancer; el coste completo y la captura siguen sin probar.
Ese documento conserva también el intento fallido y sus límites de medición.

## Resultado económico que cambia la interpretación

Se conciliaron las 127 trazas originales contra los recibos completos ya
verificados. Los 350 valores renderizados producen **332 transferencias
visibles**; 18 corresponden a `delegatecall`, que hereda el valor de la llamada
y no transfiere ese importe de nuevo. Los **98 retiros de WETH** coinciden en
beneficiario, importe y multiplicidad con los eventos `Withdrawal` de los
recibos. Las llamadas bajo un ancestro revertido quedan excluidas; este conjunto
concreto no contiene pagos con valor bajo esa condición.

En el caso WETH de rango retrospectivo 1, transacción
`0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba`,
la diferencia entre colateral recibido y deuda es **0.096156124691020450 WETH**.
La traza muestra su conversión a ETH y dos pagos desde el contrato ejecutor:

| Destino | ETH visible |
| --- | ---: |
| `0x6adb3bab5730852eb53987ea89d8e8f16393c200` | 0.095915734379292898 |
| `0x000004b6e6a0c96e7b8c0ad1ffe1f4ad34500000` | 0.000240390311727552 |

Los pagos suman exactamente aquel excedente. El neto nativo visible del contrato
es sólo **9,975 wei**, el valor aportado en la llamada raíz. No es el saldo final
del contrato ni la utilidad total del operador. No se conocen aquí la propiedad
económica de ambos destinos, sus acuerdos, reintegros ni costes externos.
Por eso **no se atribuyen automáticamente a builders ni se restan otra vez como
costes**. Tampoco se presenta el excedente bruto como utilidad retenida.

En los casos de rango 2 y 3 existen varias operaciones en la misma transacción;
los retiros/pagos no pueden asignarse íntegramente a una sola liquidación.
Los nueve casos WETH quedan vinculados al nuevo ledger, conservando `null` en
beneficio completo y cero valor NQC admitido. Gas sigue contabilizado una sola
vez por transacción, ligado al recibo original. Un pago al remitente tampoco
prueba por sí mismo utilidad: puede devolver capital previo.

Este análisis usa trazas renderizadas de un productor histórico. No sustituye
un state diff completo, pruebas de inclusión/estado, headers con fee recipient,
reproducción independiente ni recepción real de Nexus antes de la decisión.
Las etiquetas actuales de exploradores no se incorporan como autoridad histórica.

## Primer intento físico y límite de acceso conservado

Se preparó una copia nueva de las fuentes originales y un recorder RPC que:

- sólo admite lecturas del bloque histórico fijado y sus dos headers;
- traduce lecturas de estado a `blockHash` con `requireCanonical=true`;
- conserva request/response UTF-8 exactos, hashes, estado HTTP y recepción;
- limita llamadas, tiempo y ritmo; se detiene ante el primer error;
- ofrece replay sin acceso de red, rechazando cualquier dato ausente.

Foundry 1.7.1 se descargó de su release original y verificó contra SHA-256
`cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b`.
Solc 0.8.24 conserva el digest ya verificado en la recuperación de oráculos.
El binario `forge` se fija también por hash en el runner.

El primer arranque falló localmente por no existir aún el directorio de inputs,
sin consultas de red. Tras preparar los inputs, **dRPC devolvió HTTP 403,
Cloudflare 1010, en `eth_chainId` a las 23:28:06Z**. El intento terminó con una
sola consulta; no hubo reintento, cambio de identidad, fallback ni ejecución de
fork. Se conservan ambos fallos y la versión exacta del runner usado dentro de
`inputs/execution-attempt.zip`. El runner publicado en ese incremento agregó
el pin explícito del binario; aquel intento no ejecutó un fork.

No reanudar automáticamente esa adquisición dRPC bloqueada. Requiere resolver el
acceso normal al proveedor o disponer de un witness histórico completo ya
autorizado. La cobertura de oráculos que ya estaba en curso es otro proceso y
no fue alterada.

## Comprobaciones realizadas

**8 pruebas originales de Solidity pasan** en una copia nueva, sin RPC:
préstamos anidados Aave/Balancer con devolución inversa, preservación de saldos,
comisiones exactas, payload, identidad de ejecución, declaración de retorno y
rechazo de lenders duplicados. Usan contratos mock; no prueban liquidez real,
capital autorizado, compatibilidad general de tokens ni una nueva liquidación.
Fuentes, configuración, versión del compilador y log están en el ZIP del intento.

En ese primer incremento, **12 pruebas Python pasaron**, incluyendo el archivo real de 127 transacciones,
semántica de llamadas delegadas y rollback, concordancia de retiros, fallo ante
datos ausentes/corruptos, prohibición de escritura y conservación del 403.
Los controles de aislamiento se registran en `validation/`.
El primer control rechazó un `__pycache__` generado por los imports de Python
en el directorio histórico. Se trasladó esa caché fuera del repositorio y se
desactivó su escritura en los consumidores nuevos; el fallo inicial se conserva.
No cambió Rust ni se volvió a ejecutar su suite en este incremento.

```sh
python3 -m unittest discover -s migration/census_v2/execution_replay -p 'test_*.py' -v
python3 migration/census_v2/execution_replay/reconcile_settlements.py \
  --archive migration/census_v2/execution_replay/inputs/original-winner-traces.zip \
  --output /tmp/nqc-settlement-readback-fresh
```

El ZIP original de trazas se conserva íntegro: 828,195 bytes, SHA-256
`9323bf262e1f9695fcfc68a96a10b1a2e987544d3395c046aa31b13271a60c92`.
Su manifest interior conserva los 254 miembros originales. Los demás insumos
se fijan contra el commit NQC `09bf5069d81d45928bfcda0926373c933aaaa557`.
Las salidas no dependen del lugar de extracción y se reproducen byte por byte.

## Siguiente bloqueo económico concreto

La actualización siguiente resuelve el acceso para este fork y la vinculación
de un destino al header. Continúan pendientes la función económica de los
acuerdos/pagos, todas las rutas y costes por beneficiario, la compatibilidad
de los 43 activos y la revisión independiente. No se alcanza 15/20 ni 20/20.

## Recuperación explícita de RPC y fork reproducido

**Cloudflare no es una dependencia nueva ni un servicio que haya que contratar.**
Fue el filtro que respondió 403/1010 en dRPC y, en un intento separado, BlockPI.
No se volvió a consultar ninguno tras su rechazo. Nodies, proveedor público
que ya utilizaba el recolector de oráculos, respondió normalmente. El runner
selecciona un solo proveedor de forma explícita; no cambia de proveedor ante
un error. Se conservan estas adquisiciones nuevas por separado de la evidencia
histórica y de la adquisición dRPC fallida.

El archivo `inputs/rpc-recovery.zip` conserva 68 miembros, 331,815 bytes,
SHA-256 `a2752e56ad4a60b22c00a7e9db2d8f116f0b0e6d2ef67b1755c92f8f210287b5`:

| Intento | Resultado conservado |
| --- | --- |
| BlockPI 001 | Una consulta `eth_chainId`, HTTP 403/1010; ninguna prueba ejecutada. |
| Nodies 001 | Tres lecturas correctas; compilación rechazada por checksum de una dirección en el test original. |
| Nodies 002 | Compilación corregida en copia; proxy local rechazó `eth_chainId` sin `params`. |
| Nodies 003 | Proxy compatible con parámetros vacíos; rechazó `eth_gasPrice`, fuera del alcance histórico permitido. |
| Nodies 004 | **115 consultas correctas; las dos pruebas originales pasan**, finalizó 2026-10-09 23:57:15Z. |
| Nodies offline 001 | Copia nueva; las mismas dos pruebas pasan en modo normal y `--isolate`, **cero consultas externas**, finalizó 23:58:13Z. |

La corrección de checksum cambia una sola mayúscula en una copia nueva del test;
los 20 bytes de la dirección son idénticos. Preimagen y postimagen están fijadas
por SHA-256. No cambia el contrato ejecutor ni las aserciones. El runner compila
antes de consultar RPC y fija `--gas-price 0` como parámetro del test para evitar
pedir un precio actual. **Ese cero no es una estimación del coste de producción.**
Foundry solicitó también `eth_getAccountInfo`: el proxy lo rechazó localmente,
y Foundry utilizó los métodos de lectura admitidos. Los rechazos locales se
conservan; no se enviaron métodos fuera del alcance al proveedor.

La simulación parte del estado del bloque 25,938,047 y cambia solamente número
y timestamp al siguiente bloque, conservando el perfil EVM `cancun` original.
No reproduce las transacciones previas del bloque ganador. El resultado mantiene
el principal de **10.684013854557827871 WETH**, comisión flash de
**0.005342006927278914 WETH** y excedente posterior al repayment de
**0.090814117763741536 WETH**, antes de gas y demás costes. La estrategia y el
ejecutor empiezan y terminan con cero WETH; el saldo previo del operador no se
declara cero ni se usa para pagar la comisión. El beneficio imposible revierte
sin conservar cambios en el borrower, saldos o identidad de ejecución.

La medición de la llamada es **562,357 unidades de gas** en el modo original y
**534,803** con `--isolate`; la diferencia se conserva expresamente. No se usa
ninguna como cotización completa de producción. Excluye intrínseco/calldata,
despliegue, detección, intentos revertidos, inclusión y otros costes; el perfil
de ejecución también requiere revisión antes de una estimación económica.

Las respuestas de estado quedan vinculadas al hash canónico solicitado mediante
EIP-1898 y permiten repetir el fork sin red. **No son pruebas Merkle de estado**,
ni fuentes observadas por Nexus antes de la decisión, ni admisión de capital.
La repetición offline tampoco es una certificación independiente. Los cuatro
ZIP históricos inaccesibles siguen sin recuperarse: esta es una ejecución nueva.

## Cabeceras autenticadas y pago al receptor de comisiones

`verify_headers.py` reconstruye los 21 campos RLP de ambas cabeceras y su
Keccak-256, que coincide con los hashes históricos ya fijados. Se conserva el
RLP completo. Orden de campos: [Ethereum execution-specs](https://ethereum.github.io/execution-specs/src/ethereum/forks/bpo2/blocks.py.html).
Esto autentica los campos respecto a esas anclas; no rehace la validación de
consenso, inclusión de trazas ni las pruebas de estado.

El receptor de comisiones del bloque ganador es
`0x6adb3bab5730852eb53987ea89d8e8f16393c200`: coincide exactamente con el destino
de **0.095915734379292898 ETH** de la traza original. La función del campo del
header queda acreditada; propiedad, acuerdos, reintegros y función del segundo
destino permanecen desconocidos. No se etiqueta automáticamente como beneficio
del operador ni como coste de captura de Nexus.

El recibo original registra 331,267 unidades a 59,451,728 wei por gas, exactamente
la base fee del header: **19,694,395,579,376 wei quemados y cero priority fee**.
Ese gas ya figura una vez en el ledger. El pago directo al receptor es separado
del gas del recibo; no se duplica ni se convierte en una hipótesis de rentabilidad.
El ledger anterior se conserva sin reescribir; el nuevo informe añade esta
vinculación comprobable.

Pasan **19 pruebas Python y 9 de aislamiento** en este incremento. Dos pruebas
Solidity distintas pasan con adquisición nueva y se repiten offline en ambos
modos; no se cuentan las repeticiones como seis casos distintos. Se verifican
los bytes de cada miembro, fuentes/overlays/logs, los 115 intercambios y cada
respuesta servida durante el replay. Rust no cambió ni se volvió a ejecutar.
Informes y logs: `recovery-validation/`. No se gastó gas ni se enviaron transacciones.

Al comprobarlo a las 00:01:00Z del 10 de octubre (18:01 del día 9 en México),
el recolector de oráculos PID 25786 seguía activo y sin fallo: 31,430 bloques
capturados, 31,000 en archivos cerrados. **No se promueven esos contadores a
cobertura verificada**; el checkpoint publicado sigue en 7,170/215,036 hasta
verificar uno nuevo. No duplicar ese proceso. Los intentos de fork documentados
aquí ya terminaron; no requieren reanudación. La siguiente ejecución programada
puede comprobar el recolector existente y verificar un checkpoint cerrado.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/verify_recovery.py \
  --archive migration/census_v2/execution_replay/inputs/rpc-recovery.zip \
  --output /tmp/nqc-rpc-readback.json
```
