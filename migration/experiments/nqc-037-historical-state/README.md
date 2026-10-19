# NQC037 — Estado histórico, enlace por historial y recepción de pruebas

**Resultado al 19 de octubre de 2026 UTC:** se verificó una observación nueva del
evento L1 de confirmación, se identificó la altura de su bloque L2 y se construyó
un receptor reproducible para las pruebas que faltan. **No se obtuvo estado
histórico nuevo ni se ejecutó Nitro. Los 11 slots en el preestado exacto siguen
en 0/11.** Dos endpoints públicos adicionales devolvieron HTTP 403 desde este
entorno, antes de consultar métodos históricos.

La aportación principal es una ruta concreta de adquisición: el historial de
Arbitrum permite pedir una prueba de dos slots para vincular el bloque objetivo
y su padre al bloque observado en la confirmación. La ruta se deriva de código
fijado por commit y se prueba con tries sintéticos; todavía no se adquirieron
esas pruebas históricas ni se autenticó la finalidad de Ethereum.

`commercial_admission=false`. Preparación comercial: **2.5/10**, juicio de
preparación, no probabilidad. P&L realizado acreditado: **US$0**.

## Qué está comprobado y qué permanece abierto

| Elemento | Resultado | Límite |
| --- | --- | --- |
| Evento `AssertionConfirmed` | Firma Keccak, dirección Rollup, assertionHash, blockHash, sendRoot y altura L1 comprobados desde topics/data | Observación de explorador; no receipt proof |
| Bloque L2 de la confirmación | 66,753,418; hash y sendRoot coinciden con el evento | Falta su cabecera completa autenticada |
| Distancia al objetivo / padre | 9,256 / 9,257 bloques | No demuestra ascendencia por sí sola |
| Historial Arbitrum | Runtime de 133 bytes, ventana de 393,168 bloques | Fuente candidata; identidad del motor histórico pendiente |
| Código en captura diagnóstica | Coincide byte por byte con ese runtime y su Keccak | La captura no contiene accountProof |
| Receptor de pruebas | Verifica cuenta, slots, bytecode, cabeceras y enlace condicional | No ejecuta transiciones ni verifica consenso |
| Acceso público nuevo | PublicNode y BlockReq: un `eth_chainId` cada uno, HTTP 403 | No demuestra ausencia de archivo ni fallo del proveedor |
| Estado padre / preestado tx1 | Cero pruebas históricas nuevas | Sigue bloqueando el replay |

Los blobs y la raíz de transacciones ya resueltos por NQC036 permanecen intactos.
No se modificó R5, no se ejecutaron benchmarks y no se duplicó su investigación.

## 1. Anclaje observado, sin promoverlo a finalidad

La consulta nueva localizó el bloque
`0xcc02e358c6b11bfeb61182aef188bffffaa49073e666f740f2c2a887abc2c1c1`
en la altura **66,753,418**, timestamp **2026-09-19 03:15:33 UTC**, batch 258789.
El evento de confirmación observado pertenece a la transacción Ethereum
`0xccb8352f1ee3cd5a0ac2720670a90633baa8224a6fe5e4ebc11ce5387a30d0fb`,
bloque **26,054,880**, y fue emitido por el Rollup oficial
`0x23A19d23e89166adedbDcB432518AB01e4272D94`.

`audit.py` calcula `keccak256("AssertionConfirmed(bytes32,bytes32,bytes32)")`,
selecciona exactamente un evento de ese emisor y verifica su topic indexado y
sus dos palabras de datos. No depende de las etiquetas decodificadas del explorador.
El log índice 182 contiene:

- Assertion: `0x6a077d4444124a8f5192aca74c0c5824fc280697bfc8574cadb4e849176f5495`.
- BlockHash: `0xcc02e358c6b11bfeb61182aef188bffffaa49073e666f740f2c2a887abc2c1c1`.
- SendRoot: `0xb906463d939e473d25daa564dbbeaad712c2b1ffd6f2ad0ac617992f90665794`.

El calldata de la consulta de transacción llegó marcado `raw_input_truncated=true`.
Se conserva así y **no se decodifica como completo ni se reconstruye con él el
assertionHash**. El evento crudo sí tiene las dos palabras completas. Falta
verificar inclusión del receipt en una cabecera Ethereum y la finalidad de esa
cabecera con un checkpoint/modelo de confianza explícito. La etiqueta
`finalized` del explorador no satisface esos requisitos.

## 2. Ruta de historial específica de Arbitrum

La documentación vigente de Robinhood recomienda la imagen
`offchainlabs/nitro-node:v3.11.2-3599aca`. Se resolvió el candidato a Nitro
`3599acae1ad2fab4059fc46453c9cd3294126641` y se comprobó que su submódulo
go-ethereum es `f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88`.
Esto fija fuentes de referencia; **no acredita que ese binario ejecutara el
bloque histórico**, ni su WASM module root, configuración o calendario de forks.

`params/protocol_params.go` distingue dos contratos: el de Ethereum conserva
8,191 hashes; `HistoryStorageCodeArbitrum` conserva **393,168** y obtiene el
número de bloque L2 mediante `ArbSys.arbBlockNumber()`. Usar el módulo 8,191 o
el número de bloque L1 produciría una consulta incorrecta.

Contrato: `0x0000f90827f1c53a10cb7a02335b175320002935`.
Keccak del runtime Arbitrum:
`0xceef1f6ad6c0cb7eb8fb15678abf11da3ce0d3a7c7106aa900c5930e556a43ff`.

| Hash requerido | Altura L2 | Distancia al anclaje observado | Slot, `altura % 393168` |
| --- | ---: | ---: | --- |
| Objetivo | 66,744,162 | 9,256 | `0x48f12` |
| Padre | 66,744,161 | 9,257 | `0x48f11` |

Ambos caben en la ventana. Una vez recibidos, el receptor debe:

1. Reconstruir por RLP/Keccak la cabecera completa del bloque 66,753,418 y exigir
   exactamente el hash observado, su altura y sendRoot.
2. Verificar accountProof del historial contra su `stateRoot`; verificar los
   dos storageProof contra el storageRoot de esa cuenta.
3. Verificar el código por su codeHash y exigir el runtime Arbitrum exacto.
4. Exigir que los dos valores sean los hashes exactos del objetivo y del padre,
   y que ambas cabeceras se enlacen consecutivamente.

El resultado se denomina `HISTORY_LINK_VERIFIED_RELATIVE_TO_OBSERVED_ANCHOR`.
Es una comprobación condicional respecto del anclaje observado. No sustituye
el anclaje Ethereum, la semántica histórica del sistema ni un replay. Si esta
ruta no está disponible, la cadena completa de cabeceras sigue siendo otra
ruta posible; no se descargó ni se afirmó validada.

## 3. Estado de sistema y alcance de la captura anterior

La captura `augmented-prestate.json` contiene **23 cuentas y 137 slots**. Incluye
la cuenta ArbOS con **15 slots** y el contrato de historial con código, pero
**sin slots de historial ni pruebas Merkle**. El runtime del historial capturado
coincide exactamente con la fuente fijada. Esa consistencia sirve para preparar
la adquisición; no autentica la posición histórica de los datos.

La cuenta ArbOS es `0xa4b05fffffffffffffffffffffffffffffffffff`. Sus offsets
lógicos no son slots EVM directos. `Storage.mapAddress` calcula:

`slot_físico = keccak256(storageKey || key[0:31])[0:31] || key[31]`

Para el espacio raíz, `storageKey` está vacío. Los cinco campos de control
comparten el prefijo de 31 bytes
`15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b4`:

| Campo | Offset / último byte | Presente en captura diagnóstica |
| --- | --- | --- |
| Versión ArbOS | `00` | Sí, valor observado 61 |
| Versión de upgrade programado | `01` | No |
| Timestamp de upgrade | `02` | No |
| Chain ID | `04` | No |
| Genesis block number | `05` | No |

Los slots completos están en `evidence/RESULTS.json` y en las peticiones.
El receptor exige pruebas de los cinco contra la raíz padre capturada y comprueba
versión 61, chain ID 4663 y génesis 0. Un resultado distinto se conserva como
entrada rechazada y exige investigar el contexto; no se normaliza silenciosamente.

El código fijado de `startBlock` muestra efectos que deben ejecutarse:

| Operación de sistema | Datos necesarios / efecto posible |
| --- | --- |
| Historial de hashes | Código y estado de historial; escribe el hash padre |
| Registro de origen L1 | Estado previo del subespacio de blockhashes; actualización condicional |
| Dos intentos de procesar retryables expirados | Cola, tickets, expiraciones y ventanas; puede borrar storage y transferir saldo de escrow al beneficiario |
| Modelo de precios L2 | Parámetros y acumuladores previos; aplica `timePassed=1` |
| Upgrade ArbOS programado | Versión, timestamp y configuración; puede activar cambios de sistema |

No se sabe qué ramas se ejecutaron sin estado autenticado. Las pruebas de cinco
campos de control tampoco completan esos accesos dinámicos. Se debe ampliar el
witness según las lecturas reales del motor, detenerse ante cualquier nodo o
bytecode faltante y no inventar ceros. El gas observado cero de `tx0` no elimina
estos efectos.

## 4. Adquisición mínima y recepción de exportaciones

El plan previo de 52 consultas queda preservado. Esta ronda añade un sondeo
escalonado de **ocho consultas**, suficiente para probar capacidades y verificar
un subconjunto útil, no para declarar completo el estado:

| ID | Método | Objeto |
| ---: | --- | --- |
| 1 | `eth_chainId` | Exigir 4663 |
| 2 | `eth_getBlockByHash` | Cabecera padre exacta |
| 3 | `eth_getProof` | PairOracle, 11 slots, raíz padre |
| 4 | `eth_getCode` | PairOracle, mismo bloque padre |
| 5 | `eth_getProof` | ArbOS, cinco campos de control, raíz padre |
| 6 | `eth_getBlockByHash` | Cabecera del anclaje observado |
| 7 | `eth_getProof` | Historial, dos slots, estado del anclaje |
| 8 | `eth_getCode` | Runtime del historial, mismo anclaje |

Todas las lecturas de estado usan el objeto EIP-1898
`{"blockHash": "…", "requireCanonical": true}`. Esa bandera solicita la visión
canónica del nodo; no es una prueba de consenso. Un servicio que no soporte el
selector falla expresamente. No se cambia automáticamente a `latest`, a un
número de bloque ni al postestado del objetivo.

El transporte acepta solamente las ocho peticiones exactas. No sigue redirects,
no reintenta, no contiene métodos de envío y se detiene en el primer fallo.
El endpoint se lee exclusivamente de `NQC_ARCHIVE_RPC` en modo `collect`; no
se imprime ni se guarda. **La variable no estaba configurada durante esta ronda.**
Se conservan respuestas RPC exitosas recibidas aunque falle su verificación;
`FAILURE.json` las marca como rechazadas. Los errores del proveedor no se copian
con URLs o texto potencialmente sensible.

Para cada valor, el receptor diferencia una ausencia probada de una prueba
faltante. Rechaza raíces, cuentas, slots, bytecode o cabeceras incorrectas,
duplicados, JSON ambiguo, cantidades no canónicas y pruebas incompletas. Compara
los valores probados del padre con los once valores derivados de eventos, pero
una discrepancia se informa: la estimación por eventos no reemplaza la prueba.

Desde la raíz del repositorio, con Python 3.12 y las dependencias fijadas:

```bash
python migration/experiments/nqc-037-historical-state/src/audit.py
python -m unittest discover -s migration/experiments/nqc-037-historical-state/tests -v
python migration/verify_isolation.py
python -m unittest migration/test_isolation.py -v
```

Para preparar peticiones sin red, usando una ruta de salida nueva:

```bash
python migration/experiments/nqc-037-historical-state/src/intake.py plan --out /tmp/nqc037-requests.json
```

Con un endpoint autorizado ya configurado en el entorno:

```bash
python migration/experiments/nqc-037-historical-state/src/intake.py collect --out /tmp/nqc037-acquisition
```

Una exportación puede verificarse sin acceso de red:

```bash
python migration/experiments/nqc-037-historical-state/src/intake.py verify --bundle /ruta/exportacion --out /tmp/nqc037-verified
```

La exportación contiene envelopes JSON-RPC completos con los IDs del plan y los
nombres `01-chain.json`, `02-parent.json`, `03-priority_proof.json`,
`04-priority_code.json`, `05-arbos_proof.json`, `06-anchor.json`,
`07-history_proof.json`, `08-history_code.json`. La salida debe ser una ruta nueva.
La CLI devuelve código 2 si falta o se rechaza una entrada. Los ejemplos en
`/tmp` son salidas operativas temporales, no los archivos publicados del expediente.

## 5. Validación, procedencia y límites del receptor

Se ejecutaron **32/32 pruebas nuevas y 9/9 pruebas de aislamiento**, todas aprobadas.
El verificador de aislamiento confirmó 531 archivos fuente preservados, 106
workflows deshabilitados y cero activos. No verificó los objetos originales Git
ni recertificó el productor canónico; esos indicadores permanecen en `false`.
No se ejecutaron pruebas Rust porque el motor no cambió. Tampoco hubo ejecución
Nitro, replay económico ni adquisición exitosa del paquete de ocho respuestas.

Las pruebas generan tries sintéticos mediante `HexaryTrie`, una implementación
separada del verificador MPT NQC031 preservado. Incluyen inclusión, no inclusión,
código incorrecto, nodos alterados, slots omitidos o duplicados, errores de
cabeceras y un historial sintético. También mutan la evidencia real del evento
para comprobar que las etiquetas decodificadas no oculten datos crudos alterados.
**Las pruebas sintéticas no cuentan como evidencia histórica recuperada.**

La verificación de cabeceras admite explícitamente el esquema Nitro de 16
campos de este caso. Rechaza campos de forks adicionales; no es un verificador
universal de cabeceras Ethereum. El receptor tampoco implementa consenso,
ejecución EVM/Nitro, generación de witness ni conciliación económica.

`PROVENANCE.json` identifica base, rama, consultas y copias inmutables de NQC031
y NQC035. `vendor/SOURCES.json` fija los archivos upstream por commit, SHA-256 y
Git blob; los árboles de GitHub comprueban adicionalmente las fuentes ArbOS y
los parámetros de geth. Se incluyen licencias originales sin modificarlas.
`MANIFEST.json` cubre el expediente; su función es integridad de archivos, no
prueba de blockchain. Los logs registran las pruebas y el aislamiento realizados.
La revisión de whitespace del código propio pasó. La revisión global detectó
dos espacios finales en la licencia Nitro original, conservada byte por byte;
no se editó una licencia upstream para eliminar ese diagnóstico.

Las lecturas públicas de PublicNode y BlockReq fueron autorizadas por sus páginas
de endpoint público. Ambas devolvieron 403 a `eth_chainId`; no se reintentó ni
se atribuye ese bloqueo a una causa concreta. Las consultas Blockscout disponibles
aportaron observaciones, no estado Merkle. No se crearon cuentas o suscripciones,
no hubo contacto con proveedores, gasto, firma, transmisión, despliegue o trading.

Fuentes primarias de descubrimiento y semántica:

- [Conexión oficial Robinhood](https://docs.robinhood.com/chain/connecting/).
- [Nodo y versión recomendada actualmente](https://docs.robinhood.com/chain/run-a-full-node/).
- [Endpoint público PublicNode](https://robinhood.publicnode.com/).
- [Endpoint público BlockReq](https://blockreq.com/chains/robinhood).
- [Límites explícitos de pruebas históricas de SolidRPC](https://solidrpc.io/docs/chains/robinhood-chain): ejemplo de por qué archivo de valores no implica archivo de trie; no se utilizó ese servicio.
- [EIP-1898](https://eips.ethereum.org/EIPS/eip-1898).
- [EIP-2935 Ethereum](https://eips.ethereum.org/EIPS/eip-2935): referencia comparativa; para esta cadena rige el runtime Arbitrum que se verifica.
- [Parámetros geth fijados](https://github.com/OffchainLabs/go-ethereum/blob/f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88/params/protocol_params.go).
- [Transacción interna Nitro fijada](https://github.com/OffchainLabs/nitro/blob/3599acae1ad2fab4059fc46453c9cd3294126641/arbos/internal_tx.go).

## Entrada pendiente y continuación exacta

La entrada inmediata es un **endpoint autorizado que sirva `eth_getProof` en los
bloques concretos**, o la exportación de las ocho respuestas anteriores. No basta
una promesa genérica de «archive». Se necesitan pruebas del padre de septiembre
y del bloque de confirmación L2, con bytecode y cabeceras completos.

Después deben completarse, en orden lógico:

1. Verificar el paquete recibido y conservar cada resultado relativo a su raíz.
2. Autenticar el anclaje Ethereum y la relación de historial bajo la semántica
   histórica correcta; conservar abiertas las condiciones que falten.
3. Obtener un witness completo para la ejecución nativa, identificar el motor,
   WASM/configuración/forks históricos y ejecutar las transiciones hasta justo
   antes de txIndex 1. `debug_executionWitnessByHash`, presente en la fuente
   candidata, produce un witness de bloque: no certifica por sí solo ese corte.
4. Autenticar las lecturas de los 11 slots y del resto del candidato en ese
   preestado; ejecutar original y candidato con recibos, diferencias y costes.
5. Cerrar financiación, propiedad de cuentas y asignación de pérdidas antes de
   cualquier admisión comercial.

Incluso un resultado satisfactorio del receptor de ocho consultas deja en
`false` los gates de consenso, witness completo, replay, financiación y admisión.
