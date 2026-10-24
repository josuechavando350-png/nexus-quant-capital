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

## Correspondencia compilada de la muestra

La continuación `evidence/aave-compiled-identity-20261023/` recompila las
42 fuentes recuperadas con solc `0.8.27+commit.40a35a09`, cuyo hash se verifica
contra el índice oficial. Conserva la respuesta completa, los parámetros y
las entradas/salidas de compilación. La comparación incluye todos los bytes,
con sustituciones limitadas a enlaces, inmutables y la dirección propia de
bibliotecas generados por Solidity. No elimina metadatos para conseguir una
coincidencia.

Una primera compilación detectó que FlashLoanLogic no correspondía al perfil
del pool. Se conserva el fallo: 8.206 bytes compilados frente a 8.227 observados.
La biblioteca se recompila por separado con sus 28 fuentes de Etherscan y EVM
Shanghai, frente a Cancun para el pool. El resultado reproduce los 8.227 bytes.
No se cambia el EVM del pool ni se supone que todas las bibliotecas compartan
el mismo perfil. Ambos conjuntos de fuentes corresponden a consultas de Ethereum.

El pool y las cinco bibliotecas enlazadas se comprueban en los tres bloques
históricos seleccionados mediante dos proveedores. El enlace adicional de
FlashLoanLogic a BorrowLogic queda incluido. Las fuentes compiladas declaran
`POOL_REVISION = 11`; no se convierte ese valor en una etiqueta de lanzamiento
semántica sin evidencia adicional. Al usar `bytecodeHash=none`, la equivalencia
de código no autentica el texto original único ni sus comentarios.

### Reglas del código recompilado

`ValidationLogic.validateLiquidationCall` exige, en este orden: liquidador
distinto del deudor; ambas reservas activas; ambas sin pausa; gracia de ambas
reservas estrictamente anterior al timestamp; salud estrictamente inferior a
`1e18`; colateral habilitado por el deudor; deuda no nula del activo elegido.
Esta función no consulta el sentinel de precios. No se traslada aquí la regla
del repositorio archivado. Las tres funciones relevantes se conservan completas,
con hashes y referencias de línea, en `rule-excerpts.json`.

El recorrido completo hace más trabajo: actualiza índices, calcula salud con
eMode, consulta saldos escalados de colateral/deuda y precios, determina bonus,
importes máximos, redondeos, comisión y remanentes. El límite parcial se aplica
cuando el colateral y la deuda de las reservas elegidas alcanzan `2000e8` en
moneda base y la salud es **mayor** que `0.95e18`; usa el 50% de la deuda total
en moneda base, no necesariamente el 50% del activo de deuda seleccionado.
Si no se agota la deuda ni el colateral, ambos remanentes deben alcanzar
`1000e8`, con los redondeos definidos por el código. Finalmente ejecuta
operaciones de tokens y el cobro al liquidador, que también pueden revertir.

Estos umbrales son los enteros del contrato; su interpretación monetaria
depende de la moneda base del oráculo. Aprobar las condiciones iniciales de
validación no equivale a simular con éxito toda la operación.

## Criterios pendientes

1. Extender la identidad compilada de esta muestra a las dependencias externas
   que participan en el recorrido completo y autenticar el estado utilizado.
2. Comprobar la misma identidad para cada bloque usado en una conclusión, sin
   extrapolar tres puntos a todo un intervalo ni a otras cadenas.
3. Obtener reservas, deuda concreta, configuración de colateral, eMode, pausas,
   gracia y sentinel que correspondan a esa versión y estado.
4. Reconstruir el estado inmediatamente anterior a la transacción, incluyendo
   actualizaciones anteriores dentro del bloque, y ejecutar el recorrido
   completo con importes, liquidez, transferencias y costes.

Hasta entonces, la etiqueta de lanzamiento, elegibilidad ejecutable y latencia
siguen sin certificar. La revisión y equivalencia del runtime de esta muestra
tienen un alcance explícito. Este trabajo enriquece los eventos existentes y no acredita nuevos
eventos, rentabilidad, permisos de firma ni un cierre de fase. **43/100**.
