# NQC036 — Blobs recuperados y vínculo con la raíz de transacciones

Fecha: 19 de octubre de 2026 UTC / noche del 18 de octubre en Ciudad de México.

**Resultado:** se recuperaron los tres blobs del batch Robinhood 258761 y se
verificaron sus compromisos KZG contra los tres versioned hashes observados en la
transacción L1. Se decodificaron 232 mensajes y se localizó el mensaje objetivo.
Sus 56 transacciones firmadas, junto con la transacción de sistema reconstruida,
reproducen exactamente la raíz de las 57 transacciones de la cabecera capturada.

Esto cierra la adquisición y autenticación del contenido respecto de esos hashes,
y el vínculo de su secuencia de transacciones con la cabecera capturada. **No
cierra la ejecución histórica, el estado intermedio ni la canonicidad/finalidad.**

`commercial_admission=false`. Confianza comercial: **2.5/10**, juicio de preparación
y no probabilidad. P&L acreditado de NQC: **US$0**. No se ejecutó trading, firma,
transmisión, despliegue, gasto ni contacto con proveedores.

## Evidencia nueva

| Comprobación | Resultado |
| --- | --- |
| Blobs completos | 3 × 131,072 bytes = 393,216 bytes |
| Compromiso KZG calculado desde cada blob | 3/3 coinciden con sus metadatos y hashes L1 |
| Integridad por CID IPFS | 3/3 coinciden |
| Pruebas de blob entregadas en el campo `proof` de Blobscan | 0/3 válidas como `verify_blob_kzg_proof` |
| Pruebas de blob calculadas localmente | 3/3 válidas; se identifican como locales |
| Payload Nitro después de decodificar campos BLS/RLP | 384,841 bytes |
| Payload Brotli descomprimido | 2,362,148 bytes |
| Segmentos | 259: 24 avances de tiempo, 3 de bloque L1, 232 mensajes L2 |
| Transacciones firmadas de los mensajes | 2,396; no se ejecutaron |
| Mensaje objetivo | ordinal 206, segmento 231, ambos desde cero |
| Transacciones firmadas del mensaje objetivo | 56/56 coinciden con la captura, en orden |
| Transacción objetivo | primera del mensaje; índice 1 del bloque después de `tx0` |
| Timestamp derivado, sujeto a timeBounds L1 | 1789786800 = 2026-09-19 03:00:00 UTC |
| Origen L1 derivado | 26,008,731 |
| `tx0` reconstruida | hash exacto; llamada `startBlock(0,26008731,66744162,1)` |
| Raíz de 57 transacciones | coincide exactamente con `transactionsRoot` capturada |
| Acumulador del batch | coincide exactamente con el evento L1 observado |

El campo `proof` recibido para cada blob representa el punto al infinito. La
comprobación como prueba de blob lo rechaza. No se lo cuenta como prueba válida
del proveedor ni se lo sustituye silenciosamente. La comprobación central calcula
el compromiso desde los 131,072 bytes y compara su versioned hash con la lista L1.
Las pruebas generadas localmente son una comprobación adicional de consistencia;
no aportan una fuente independiente de consenso.

Los 232 mensajes coinciden con `newMessageCount - prevMessageCount`. El ordinal
206 da 66,744,162 al sumarlo a 66,743,956. Esta cuenta se acompaña ahora de la
coincidencia real de los 56 hashes y de la raíz completa de transacciones. La
coincidencia numérica aislada no se utiliza como prueba suficiente.

## Identidades exactas

- L1 batch tx: `0x371af57bf11056f0228abbee533154ca844a284787490ed9d603be13d17b40d2`.
- Batch data hash calculado: `0x1d6bff2519d93074a1e66188db151cd9a8a3f16901f45f1fa32cd9b3f4a3e25d`.
- After accumulator: `0x229a908e4bc645ba97e7ad71961c70369557eae14c03e49cd477f3542608273f`.
- L2 objetivo: chain 4663, bloque 66,744,162, txIndex 1.
- Cabecera capturada: `0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7`.
- Raíz de transacciones: `0x0d48255688f8c8464b47af113fc105ba82bdbaa697fb39ce12e19cc5833550ac`.
- `tx0`: `0x3824f876e4f5f677850701f41b990f6971c631ff8ebbce08a904072c17488fe8`.
- Tx objetivo: `0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842`.

## Método y frontera de confianza

1. Se revalidaron `AGENTS.md`, main `16e352225ba8a6a931834c4edf3d86d9a2924b7d`
   y el extremo `69321e328428be58eddba15544d4764f65083d4c` de la rama NQC666.
   El trabajo se aisló en una rama nueva, derivada de ese extremo.
2. Se recuperaron los paquetes originales NQC031, NQC034 y NQC035. Pasaron las
   verificaciones SHA-256 de sus manifiestos: 27, 12 y 14 archivos respectivamente.
   Los encabezados usados se copiaron sin modificar de NQC031.
3. Las lecturas L1 y del batch se revalidaron con Blockscout. Los blobs completos
   se recuperaron mediante las referencias IPFS publicadas por la API de Blobscan.
   Se conservan bytes, metadatos, consultas y procedencia.
4. Se usó C-KZG a través de `ckzg`, con trusted setup del repositorio oficial de
   Ethereum fijado por commit y SHA-256. La biblioteca estándar no implementa KZG.
5. `decode_batch.py` interpreta la codificación de campos de 254 bits, RLP,
   Brotli, los segmentos de avance y los mensajes L2 firmados/anidados. Rechaza
   clases no soportadas y truncamientos. Su alcance es este corpus; no es un
   reemplazo universal del parser Nitro ni de su semántica ante entradas inválidas.
6. `audit.py` reconstruye el header de secuenciador de 40 bytes, el data hash
   `keccak(header || 0x50 || blobHashes)` y el acumulador
   `keccak(beforeAcc || dataHash || delayedAcc)`.
7. Se construyó `tx0` tipo 106 con chainId 4663 y el calldata derivado del contexto.
   Su hash coincide con la captura y el calldata coincide con otra lectura del
   explorador. `HexaryTrie` reconstruyó el trie de las 57 transacciones, indexado
   por RLP(index). RLP/Keccak de las cabeceras padre y objetivo también coincide.

Los archivos de `vendor/` están fijados por identidades y procedencia. El código
Nitro actual consultado permite reproducir estas estructuras, pero **no prueba
qué binario ni calendario de forks ejecutó históricamente el secuenciador**.

Las lecturas de explorador siguen siendo observaciones de terceros. No se verificó
una prueba de inclusión del receipt L1 contra una cabecera Ethereum autenticada
por consenso. Tampoco se construyó el camino desde la cabecera L2 objetivo hasta
la aserción confirmada. Verificar el trie de transacciones no verifica stateRoot,
receiptsRoot, ejecución correcta, fork schedule ni disponibilidad de financiación.

`tx0` consume cero gas en la observación, pero tiene efectos de sistema. Reconstruir
sus bytes no equivale a aplicar sus cambios al estado padre. **El preestado de
txIndex=1 permanece pendiente y los 11 slots prioritarios siguen en 0/11.**

## Reproducir sin red

Se instalaron dependencias únicamente en un entorno virtual de investigación:
`ckzg`, `Brotli`, `pycryptodome`, `trie`, `rlp` y sus dependencias. Se fijaron las
versiones resueltas en `requirements.txt`. No se modificó el motor R5.

Desde la raíz del repositorio, después de preparar un entorno Python 3.12 con esas
dependencias:

```bash
python migration/experiments/nqc-036-blob-authentication/src/audit.py
python -m unittest discover -s migration/experiments/nqc-036-blob-authentication/tests -v
python migration/verify_isolation.py
python -m unittest migration/test_isolation.py -v
```

`audit.py` y los tests son locales y no hacen llamadas de red. `audit.py` actualiza
solo `evidence/RESULTS.json`. `decode_batch.py` permite reconstruir los resultados
intermedios y las transacciones crudas del mensaje objetivo.

Validación ejecutada: **17/17 pruebas nuevas**, **9/9 pruebas de aislamiento**, y
verificador de aislamiento aprobado: 531 archivos de fuente preservados, 106
workflows deshabilitados y cero workflows activos. No se ejecutaron pruebas Rust
ni benchmarks porque no se cambió el motor. No se ejecutó Nitro, Anvil ni replay
económico. Las pruebas nuevas incluyen mutaciones de blob, CID, orden, prefijo,
stateRoot, truncamiento y comparación del RLP con una biblioteca separada.

La revisión de whitespace del código propio pasó. La revisión global detectó dos
espacios finales en `vendor/LICENSE.md`, conservados exactamente como en la
licencia upstream; no se alteró esa fuente para silenciar el diagnóstico.

## Acceso fallido y siguiente trabajo exacto

- La consulta nativa de blobs excedió su límite de respuesta. La ruta REST
  documentada para respuestas grandes devolvió HTTP 403. No se insistió ni se
  eludió la restricción; los payloads llegaron por el archivo público de Blobscan.
- El RPC público oficial de Robinhood respondió HTTP 403 a `eth_chainId`.
  No se realizó ninguna lectura de archivo por esa vía. Un 403 no demuestra que
  los datos históricos no existan.
- Una consulta de `tx0` a Blockscout devolvió 500; un reintento obtuvo la respuesta.

La próxima entrada necesaria es **un estado padre completo o un witness histórico
verificable**, accesible por un endpoint autorizado o exportación, además del
camino de canonicidad/finalidad. El bloque padre es 66,744,161, hash
`0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917`.
Su raíz capturada es
`0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a`.

Orden de continuación:

1. Autenticar el anclaje Ethereum/rollup y el estado padre. Conservar explícito el
   modelo de confianza de cualquier RPC o exportación.
2. Identificar el motor/fork schedule histórico compatible con ArbOS 61.
3. Ejecutar las transiciones de sistema y el `tx0` reconstruido sobre ese estado.
4. Obtener el preestado exacto de txIndex=1 y autenticar allí los 11 slots.
5. Ejecutar original y candidato NQC; después conciliar costes y financiación.

No volver a gastar una ronda buscando estos mismos tres blobs o usando más
benchmarks como sustituto del estado. Los bytes y el vínculo de transacciones ya
quedan conservados en este paquete.
