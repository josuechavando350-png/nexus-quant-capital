# NQC — Continuidad: caso PT-stcUSD/USDC

Fecha: 21 de octubre de 2026. Estado: HISTORICAL_FLOWS_RECONCILED_NQC_REPLAY_PENDING.

Este documento preserva un caso concreto para que la continuidad no dependa del chat o de NQC080. Es una liquidación histórica de un tercero. NO recupera NQC076/079/080, NO demuestra beneficio de NQC y NO autoriza trading.

## Procedencia y selección

Entrada del propietario: NQC_EVIDENCIA_ETHEREUM_90D.zip, SHA-256 `7d7b91194d424c63fb61c9233f1a4016ee42dd7cc96faba0fd97b86febba8994`. Se ejecutó el verificador original: 36 archivos del manifiesto coinciden, SQLite íntegro, 2,372 respuestas, 245 eventos, 212 transacciones. Los 119 eventos previos ya están incluidos. No se completaron los 90 días ni se generó un ranking económico.

Se decodificaron 118 eventos Morpho. El catálogo previo identifica 16 eventos PT en seis mercados. Regla para elegir un caso manejable: PT identificado, préstamo en la dirección exacta de USDC con seis decimales, índice de transacción cero; ordenar por deuda USDC descendente y desempatar por bloque/hash. Había tres candidatos. Esta regla selecciona facilidad de reproducción, no rentabilidad.

## Identidad inmutable del caso

- Ethereum, chain ID 1.
- Transacción: `0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2`.
- Bloque: `25666958`, índice de transacción `0`, 2026-08-02T11:39:59Z.
- Hash de bloque: `0x9359bb8b9facde49da1840c8dcce4b4b189db6ff3f1258f6a807f19e848f28b8`.
- Hash padre: `0x815fd2fe22f9faea8020c9aeec418cde5b2ee7d8a566ca2632c8600820d9952e`.
- Mercado Morpho: `0x03f715ef1ae508ab3e1faf4dffdbf2a077d1f0ad10c5aad42cf4438d5e3328af`.
- Prestatario: `0xa6e5541025a8e3124ea5ff1c7f2ee778e9492e49`.
- Ejecutor externo: `0x3f73fb5e1984d73d5e9065fbf7ab80d1ee73860e`.
- Emisor que paga gas: `0x3c1557217d1438fbde9539f5332a3e13b7edc287`.
- Destinatario de salida USDC: `0xd61c0e1c80ccae9915cbf9d8720e7e752ce0a612`.
- PT: `0xc3c7e5e277d31cd24a3ac4cc9af3b6770f30ea33`.
- USDC: `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`.
- WETH: `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2`.
- SY: `0x27010ce8d14b4e73ef48af1cf9a5a91e8356d10f`.
- Receptor del PT para canje: `0x8b4a52d28e49a9e8994d563420422e1a26a83df1`.
- Pool USDC/WETH: `0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`.
- Morpho: `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb`.

## Campos observados, en unidades mínimas

Las siguientes cifras son transcripciones estructuradas de campos seleccionados de las respuestas del conector Blockscout, NO recibos RPC brutos ni pruebas de estado.

| Índice del movimiento | Token | Desde -> hacia | Cantidad base |
|---|---|---|---:|
| 3 | PT | Morpho -> ejecutor | 3305257748749184918001 |
| 6 | PT | ejecutor -> receptor de canje | 3305257748749184918001 |
| 37 | USDC | SY -> ejecutor | 3305262344 |
| 42 | USDC | ejecutor -> Morpho | 3220954251 |
| 45 | WETH | pool -> ejecutor | 32436169090076373 |
| 46 | USDC | ejecutor -> pool | 60425142 |
| 49 | WETH | retiro del ejecutor a ETH | 32210448575152600 |
| 51 | USDC | ejecutor -> destinatario de salida | 23882951 |

El movimiento 49 es enriquecido por el indexador a partir del retiro WETH; no se presume un evento ERC-20 Transfer a cero. Los movimientos nativos devuelven: índice interno 293, WETH -> ejecutor, `32210448575152600` wei; índice interno 294, ejecutor -> `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97`, la misma cantidad. El bloque informa esa última dirección como miner/coinbase; coincide con la indicada por Titan en la captura del propietario. La igualdad de direcciones no prueba patrocinio.

Datos de gas: gasUsed `1870816`, effectiveGasPrice `1042435069`, baseFeePerGas `42435069`, gasLimit `2683545`, maxFeePerGas `1084920764`, maxPriorityFeePerGas `1000000000`, value `0`.

Gas total: `1950204206046304` wei = `1870816000000000` de prioridad + `79388206046304` quemados. La prioridad ya está dentro del gas total. No sumar las comisiones mostradas para llamadas internas.

Lecturas balanceOf del ejecutor:

| Token | Bloque 25666957 | Bloque 25666958 |
|---|---:|---:|
| USDC | 0 | 0 |
| WETH | 92941183342122 | 318661698265895 |

El WETH previo queda excluido de los ingresos. La diferencia, `225720514923773` wei de WETH, coincide con entradas menos retiro. Son saldos al cierre de bloque; no constituyen un testigo de estado por transacción.

## Conciliación y límite económico

`3305262344 - 3220954251 = 84308093` unidades USDC: **84.308093 USDC** después de la deuda.

`84308093 - 60425142 = 23882951` unidades USDC: **23.882951 USDC** enviados a la dirección de salida.

El vector conservado tras esos movimientos, antes de obligaciones externas desconocidas, es: `23.882951 USDC + 0.000225720514923773 WETH - 0.001950204206046304 ETH de gas del emisor`.

Valorar WETH y ETH al ratio del swap ejecutado de este caso da aproximadamente 20.670421 USDC equivalentes. Es una valoración CONDICIONAL: exige consolidar tres direcciones cuya propiedad común NO se verificó; el ratio no es una cotización de venta inversa ni un precio actual. NO es P&L auditado del tercero y NO es dinero ganado por NQC. No contar el pago directo y el USDC usado para obtener ese ETH como dos gastos independientes.

## Alcance de la comprobación

Ocho consultas de datos satisfactorias: get_transaction_info, get_token_transfers_by_address, get_transactions_by_address, get_block_info y cuatro read_contract balanceOf. Ventana de movimientos: 2026-08-02T11:39:58Z a 11:40:00Z. Las listas del ejecutor devolvieron pagination=null y registros de una sola transacción. La primera respuesta de transacción truncaba su lista de tokens; se sustituyó para el cálculo por la consulta de movimientos del ejecutor, no se trató como completa.

El presupuesto gratuito informado por el conector llegó a cero y no hubo más consultas ni intentos de eludirlo. No se consultó el endpoint de Titan. No hay traza completa, recibo RPC bruto, prueba de almacenamiento, verificación de trie ni replay EVM NQC. El saldo inicial de USDC era cero; había WETH previo y el emisor pagó gas. No declarar por ello cero capital total ni patrocinio demostrado.

El paquete de entrega `NQC_CONTINUIDAD_ECONOMICA_20261021.zip` contiene analizador offline, entradas, manifiesto y 17 pruebas Python ejecutadas: cero fallos, errores y saltos. Incluye la copia íntegra del ZIP de entrada. Ese código y sus logs se entregan como archivo adjunto; este commit preserva documentación y datos esenciales, NO una integración del ejecutor. Las suites completas de NQC/Rust y el verificador completo de aislamiento NO se ejecutaron por falta del checkout completo. No se modifica ninguna fuente previa, workflow o certificado.

## Próximo experimento

Reproducir el original desde el padre fijado, aplicando las transiciones de sistema y el entorno exacto del bloque. El índice cero evita reproducir transacciones de usuario anteriores, no elimina la necesidad del estado histórico. Obtener bloque completo, cabecera padre, recibo y un preestado por una fuente archivística autorizada. No sustituir datos faltantes por mocks.

Tras paridad del original, probar NQC desde el mismo estado, primero con el callback directo de Morpho. Su fuente revisada entrega colateral, llama onMorphoLiquidate y después cobra la deuda. Comparar un flash loan externo solo si aporta una necesidad concreta. Medir gas propio, despliegue, financiación y pagos antes de afirmar beneficio. La captura competitiva y el patrocinio de Titan son pruebas separadas.

No hubo firmas, bundles, despliegues públicos, movimientos de fondos, compras, cambios en main o procesos de vigilancia. Esta rama es exclusivamente de investigación.

## Referencias

- Explorador del caso: https://eth.blockscout.com/tx/0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2
- Titan, Sponsored Bundles: https://docs.titanbuilder.xyz/api/eth_sendbundle
- Morpho, fuente revisada: https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol (líneas 346–435). Esto no autentica el runtime desplegado del bloque histórico.
