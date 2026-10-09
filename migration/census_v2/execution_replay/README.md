# Ejecución y destino del excedente

Prioridad del 9 de octubre de 2026: comprobar financiación, repayment y costes,
además de continuar la cobertura histórica. **Census sigue abierto.**

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

## Intento físico y límite de acceso

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
`inputs/execution-attempt.zip`. El runner actual agrega el pin explícito del
binario; no se presenta como ejecutado contra la cadena.

No reanudar automáticamente esa adquisición bloqueada. Requiere resolver el
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

**12 pruebas Python pasan**, incluyendo el archivo real de 127 transacciones,
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

Vincular los destinos de pagos a headers completos del bloque y acreditar
su función económica; después conciliar principal, todas las rutas y costes
por ejecutor/beneficiario. Una suma de pagos no prueba utilidad ni coste de
captura de Nexus. Continúan pendientes el fork nuevo con estado verificable,
la compatibilidad de los 43 activos y la revisión independiente. No se alcanza
15/20 ni 20/20 con este incremento. No hubo gas gastado ni transacciones enviadas.
