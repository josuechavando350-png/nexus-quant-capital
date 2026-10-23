# Elegibilidad Aave: fijar la implementación antes de aplicar reglas

El pool es un proxy. Reconocer su dirección y el ABI de `getUserAccountData`
no identifica todas las reglas ejecutables del código al que delegaba en un
bloque histórico. La siguiente etapa debe vincular dirección, bytes de runtime,
fuente y configuración antes de dar por válida una liquidación.

## Diferencias encontradas en las fuentes

La revisión de `ValidationLogic.sol` del repositorio archivado `aave-v3-core`
incluye una comprobación del sentinel de precios, cuando está configurado, con
una excepción por factor de salud. El código consultado de `aave-v3-origin`
incluye además controles de autoliquidación y periodo de gracia de ambas
reservas, y conserva comprobaciones de reservas activas, pausa, salud, uso de
colateral y deuda del activo elegido. Su rama actual ya no aplica el sentinel
de precios. No se asigna esa rama al runtime histórico por coincidencia de ABI.

La [nota de cambio de v3.7](https://github.com/aave-dao/aave-v3-origin/blob/main/docs/3.7/sentinel-removal.md)
documenta la retirada del sentinel. Sus resúmenes no sustituyen los controles
del código de validación y ejecución: salud y periodo de gracia no bastan por
sí solos para afirmar que una operación completa vaya a ejecutarse.

Fuentes primarias revisadas, identificadas por blob Git:

| Fuente | Blob |
| --- | --- |
| [ValidationLogic, Origin](https://github.com/aave-dao/aave-v3-origin/blob/main/src/contracts/protocol/libraries/logic/ValidationLogic.sol) | `985978099465a3f3058d62263767b8de33d4fbfb` |
| [Retirada del sentinel](https://github.com/aave-dao/aave-v3-origin/blob/main/docs/3.7/sentinel-removal.md) | `63a94c133b93d23e0ec0536ec2c4c3097020e3e3` |
| [Proxy base archivado](https://github.com/aave/aave-v3-core/blob/master/contracts/dependencies/openzeppelin/upgradeability/BaseUpgradeabilityProxy.sol) | `a0d9b80f0f09b5db629996f6588f9f15a631ded3` |
| [Registro oficial Ethereum](https://github.com/aave-dao/aave-address-book/blob/main/src/AaveV3Ethereum.sol) | `75c7b74ed79abb8c55feeaaa99d59248aae09053` |

Los enlaces de rama son mutables; estos hashes identifican las revisiones
consultadas. Ninguna de ellas certifica por sí sola el código desplegado.

## Comprobación histórica del proxy

`evidence/aave-proxy-identity-20261023/` contiene una sonda de investigación
separada del CLI productivo. Consulta el slot de implementación
[ERC-1967](https://eips.ethereum.org/EIPS/eip-1967) y los bytes del proxy y de su
implementación al cierre del bloque inmediatamente anterior a cada evento.
Todos los accesos a estado usan `blockHash` y `requireCanonical: true`.

Se exige acuerdo entre dos proveedores, identidad de cadena, finalización y
revalidación del bloque y del evento después de las lecturas. Se rechazan slots
vacíos, direcciones mal codificadas, runtime vacío, desacuerdos y cambios de
hash. No se infiere un beacon cuando el slot está vacío. El límite por runtime
es 64 KiB; solo se investigan los tres bloques seleccionados, sin afirmar que
se hayan comprobado todos los bloques intermedios.

Se conservan completos el slot y los bytes de runtime. Para los encabezados se
conservan las proyecciones necesarias para comparar número, hash, padre y fecha;
esto no constituye autenticación criptográfica del encabezado o del estado.
Los hashes de runtime registrados son **SHA-256 de integridad**, no el
`codeHash` Keccak de Ethereum.

## Criterios pendientes

1. Vincular el runtime observado con fuentes verificadas, bibliotecas enlazadas,
   inmutables, compilador y parámetros de compilación; conservar esa identidad.
2. Comprobar la misma identidad para cada bloque usado en una conclusión, sin
   extrapolar tres puntos a todo un intervalo ni a otras cadenas.
3. Obtener reservas, deuda concreta, configuración de colateral, eMode, pausas,
   gracia y sentinel que correspondan a esa versión y estado.
4. Reconstruir el estado inmediatamente anterior a la transacción, incluyendo
   actualizaciones anteriores dentro del bloque, y ejecutar el recorrido
   completo con importes, liquidez, transferencias y costes.

Hasta entonces, versión, elegibilidad ejecutable y latencia siguen sin
certificar. Este trabajo enriquece los eventos existentes y no acredita nuevos
eventos, rentabilidad, permisos de firma ni un cierre de fase. **43/100**.
