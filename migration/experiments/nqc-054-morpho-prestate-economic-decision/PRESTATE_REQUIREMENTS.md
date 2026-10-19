# Entradas que faltan para un replay auténtico de B

Este documento especifica un límite verificable; no es un plan de consultas RPC.
Las cuentas y las claves exactas se encuentran en
`evidence/audit.json → prestate.account_inventory / exact_known_slot_requirements`.
Cada entrada conserva `null` para prueba, valor autenticado, código y metadatos
ausentes. Se publica un inventario mínimo identificado, no un witness completo.

| Identidad | Evidencia conservada | Falta imprescindible |
|---|---|---|
| Padre 26190954, hash `0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc` | Cabecera y stateRoot | Ancla canónica/finalidad independiente y witness de cuentas/storage ligado a esa raíz |
| Bloque 26190955, hash `0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8` | Cuerpo, cabecera, resultado previo de verificación del transactionsRoot | Configuración de forks/reglas aplicables y estado necesario para transiciones de sistema previas a tx0 |
| tx0 `0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0` | Transacción serializable y posición; gas inferible 243495 | Códigos, cuentas, almacenamiento y accesos para ejecutarla; recibo/traza/diff para contrastar. Su conjunto de dependencias no puede inferirse del selector |
| Preestado inmediatamente anterior a B | Observaciones parciales de lecturas dentro de B | Estado derivado tras sistema+tx0, sin asumir que el padre equivale a txIndex1 |
| 50 cuentas inventariadas | Direcciones y rutas/roles de llamada | Por cuenta: nonce, balance, storageRoot, codeHash y prueba contra el padre; bytes del código o prueba de código vacío |
| 28 contextos de almacenamiento de B | Árbol de llamadas con contextos de DELEGATECALL | Conjunto completo de SLOAD/SSTORE; valores/pruebas de los slots accedidos. Una call trace no muestra accesos internos |
| Morpho `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb` | ABI, parámetros y layout de fuente fijada | Runtime histórico ligado a codeHash; las diez claves siguientes y otros slots realmente accedidos, con prueba/valor |
| Oracle `0x94f93f1eadb8a2f73c415ad4c19cb791e6d0192b`, IRM `0x870ac11d48b15db9a138cf899d20f13f79ba00bc` | Identidades concordantes entre calldata, traza y configuración conservada | Runtime, proxies/implementaciones, almacenamiento y estado de sus dependencias; una salida de llamada no sustituye su ejecución |
| WETH `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2`, ezETH `0xbf5495efe5db9ce00f80364c8b423567e58d2110` | Transferencias/lecturas intratransacción | Código histórico y layout efectivo, slots de balances/allowances y dependencias; no se inventan números de slot |
| Ejecutor `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd` | Input completo y traza | Runtime del padre, configuración/almacenamiento; el intento archivado de getCode falló |
| Fluid pool `0xdd72157a021804141817d46d9852a97addfb9f59` y Liquidity `0x52aa899454998be5b000ad077a46bbe360f4e497` | Fuente referenciada, constructor y cuatro lecturas por clave | Runtime/proxies ligados al estado, todos los slots de reservas, límites y configuración, no solo las cuatro lecturas externas |

Mercado `0xa0534c78620867b7c8706e3b6df9e69a2bc67c783281b7a77e034ed75cee012e`,
deudor `0x018d6cc992eb576e2f36dc485b92d168ada37156`, LLTV 945000000000000000.
El identificador se recalcula como keccak de los cinco parámetros de mercado.
Esto comprueba coherencia de identidad; no autentica el almacenamiento histórico.

Claves Morpho derivadas del layout conservado (vinculación al runtime pendiente):

| Campo | Clave base | Extensión |
|---|---|---|
| market: supplyAssets/shares, borrowAssets/shares, lastUpdate/fee | `0x2a77eb15b46c885e36c2be35a59b03ddfcb9d3e313a1e6bf2da2c8b4488de609` | base + 0, 1, 2 |
| borrower: supplyShares, borrowShares/collateral | `0xd23fc2386c6cfb569ad04c9a083d19ed21cabfeaf9d188c89af9ba0ba2cc698b` | base + 0, 1 |
| marketParams: loan, collateral, oracle, irm, lltv | `0x39acf4bd918e7fe6b00842751336026a71eca35b2353dbf71da80b410af2a1f8` | base + 0, 1, 2, 3, 4 |

Cuatro claves observadas en Fluid Liquidity, no en el pool:

| Campo | Clave |
|---|---|
| exchangePriceToken0 | `0x84481214d3f2018de0daf983b0d58307ac7a5294093d7fc9b6d961f4e9505ecb` |
| exchangePriceToken1 | `0xa1829a9003092132f585b6ccdd167c19fe9774dbdea4260287e8a8e8ca8185d7` |
| supplyToken0 | `0xd62514f881626332ada207f8acb7ec0f33c4279ec263b57b1869255363590335` |
| supplyToken1 | `0xe3b9bd247a03c6620600a8c5dd00e3f5620c90d52d504fc2e744d0e6e1d85ccf` |

No puede enumerarse honestamente cada slot restante a partir de esta evidencia:
faltan runtime y un witness de accesos, especialmente del prefijo. Esa imposibilidad
es una entrada ausente explícita, no una invitación a usar ceros. Las 14 claves no
equivalen a 14 slots suficientes para ejecutar B.

El intento archivado de `prestateTracer` recibió HTTP403, método no permitido.
El intento de código del ejecutor fijó el hash del padre, pero el proveedor devolvió
`state at block #26190955 is pruned`. Se conserva esa discrepancia textual: el error
no es código ni prueba de ausencia. NQC054 no reintentó ninguno de esos accesos.

Se excluyen expresamente los estados REST posteriores en 26210229–26210231 y el
witness parcial de otro mercado/deudor en 25422888. La raíz final de B tampoco
representa el estado anterior a txIndex1. Incluso con estado ejecutable recuperado,
el replay solo acreditaría el alcance histórico contrastado; no financiación,
inclusión competitiva futura ni beneficio capturado por NQC.
