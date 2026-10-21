# Titan — mecanismo documentado, caso NQC condicionado

Se consultó la documentación oficial de Sponsored Bundles:
https://docs.titanbuilder.xyz/api/eth_sendbundle . Declara anticipo de ETH frente a insuficiencia de
fondos para gas/value, condicionado a recuperar ese coste y aumentar el balance del builder.
La respuesta directa de Titan sobre priority fees/coinbase se conserva como **declaración aportada por
el propietario en esta misión**; no se recuperó ni autenticó aquí el mensaje original.

| Etapa | Estado |
|---|---|
| Posibilidad descrita públicamente | Sí, documentada |
| Prefinanciación y ejecución local NQC medidas | No |
| Simulación aceptada por Titan para este paquete | No |
| Selección frente a otros bundles | No |
| Inclusión real NQC | No |

No se llamó al RPC de Titan, ni se preparó/envió un bundle firmado.
Un bundleHash de recepción tampoco demostraría inclusión o beneficio.

## Correcciones revisadas

Se revisaron las fuentes originales del experimento NQC068 por su commit y hashes, registrados en
`evidence/prior_source_review.json`. El caso anterior era UNI, no esta ruta PT-stcUSD.
`HistoricalFlashExecutor` separaba `inclusionReward`, `sponsorPayment` y `minBeneficiaryWeth`.
Sus tests ponían `sponsorPayment=0`, usaban `prank` y medían scopes con `gasleft()`.
Esos tests no prueban reembolso, saldo inicial EOA cero ni el coste facturado de creación/ejecución.
No se modificó ni se importó ese ejecutor como si sirviera para el caso actual.

Para el destinatario histórico `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97`, el nuevo dato indexado
confirma que es coinbase del bloque objetivo. No prueba que sea la cuenta que adelantó fondos,
que su propietario sea Titan en todo bloque, ni que el pago salde una obligación del patrocinador.
Los metadatos del padre muestran **otra coinbase**.

## Libro de financiación requerido

Sean A anticipo, U devolución no utilizada, R reembolso explícito, F margen adicional,
B transferencia al builder, P prioridad y Gs gas de transacciones del patrocinador.
Si (y solo si) las cuentas y derechos de cobro están demostrados, el cambio de caja del patrocinador es
`−A + U + R + F + B_atribuible + P_atribuible − Gs − otros_pagos`.
No se puede sumar B o P si corresponden a otro beneficiario, ni omitir obligaciones al proponente.
R/F deben definirse sin solaparse. La rentabilidad del sponsor necesita su saldo final neto positivo.

El límite máximo previo `gasLimit * maxFeePerGas` no es el gas finalmente gastado.
Debe calcularse por separado para anticipo, despliegue, aprobaciones y ejecución.
Hay que acreditar el tratamiento de ETH no gastado y de reversiones, reorgs y no inclusión.
El principal del anticipo no es ingreso NQC. Si R ya incluye gas, cargar además el mismo gas
sin reconciliar A/U duplica el coste. Lo mismo ocurre al sumar priority fees al gas total ya facturado.

En el historial externo, prioridad + transferencia directa a coinbase suman
0.034081264575152600 ETH según las fuentes conservadas. No es beneficio neto de Titan
ni prueba de patrocinio: faltan anticipo, otras obligaciones y titularidad económica.
No se supone gratuita la creación del ejecutor ni se amortiza sobre ingresos futuros no demostrados.
