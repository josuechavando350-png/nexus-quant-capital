# Libro por participante y exposición

Fuente numérica: `titan_ledger` y cinco archivos de ejecución fijados en `SOURCE_MANIFEST.json`. Todos los actores/direcciones de `evidence/reconciliation.json` pertenecen al **laboratorio chain 31337**. El alias propietario/operador y la coincidencia financiador/builder de V06 son condiciones del fixture; no atribuyen propiedad ni derechos en producción.

| Participante | Entrega / recibe en la estructura C1 conservada | Obligación y beneficio |
|---|---|---|
| Propietario / EOA NQC | Recibe anticipo A; paga gas de sus tx; devuelve U; recibe residuo WETH | U no es beneficio. En laboratorio comienza vacío; responsabilidad externa real UNKNOWN |
| Ejecutor | Recibe garantía Morpho, la vende, reserva deuda, desenvuelve WETH para pagos | Repaga deuda, R al financiador, tip al destinatario definido y residuo al operador; inventario previo excluido |
| Financiador | A hacia operador; gas propio de fondeo; recibe R/U; puede pagar builder aparte | Caja R+U+V-A-F-P-O. R es cobro bruto, no necesariamente ganancia. Coste comercial/deuda/recuperación UNKNOWN |
| Builder | Según escenario recibe fee separado, o es además financiador | Necesita economía compatible propia; ingreso del proponente no se le atribuye por nombre |
| Proponente | Dirección distinta en laboratorio recibe tip y priority fees; en otra arquitectura cobra payout separado | No se añade su cobro al builder; omitirlo no crea beneficio económico aceptable |
| Protocolo / prestamistas | Morpho entrega garantía depositada y recibe activo de deuda | Repago no equivale a beneficio íntegro del protocolo; no atribuirle titularidad económica de todos los depósitos |
| DEX / LP | Pool recibe garantía y entrega WETH | Comisión/impacto incluidos en salida observada; sus cambios de inventario no son beneficio neto valorado |
| Prestatario liquidado | Garantía bajo custodia disminuye; deuda se reduce | Obligación del prestatario no se rebautiza como préstamo personal al propietario NQC |
| Wrapper WETH | Quema WETH y libera ETH en el unwrap | Movimiento entre activos contabilizado, no dinero nuevo |

En producción, `block.coinbase` es el destinatario de tasas definido en el bloque, no prueba por sí mismo de identidad económica del proponente. Las páginas generales de Titan/Quasar publican receptores propios; no autentican por sí solas todas las cuentas financiadoras, beneficiarios, payouts o términos para NQC. Se debe demostrar el mapa real. El modelo que separa esos roles y el que los reúne son escenarios diferentes.

## Ejemplo V06 exacto, no oferta comercial

- A: 30.000.000.000.000.000 wei desde financiador/builder de laboratorio.
- Gas del operador: 4.594.412.000.000.000 wei, ya consumido dentro de A-U.
- U recibido: 25.405.588.000.000.000 wei.
- R recibido: 50.000.000.000.000.000 wei desde la venta/unwrap.
- F gas de fondeo: 42.000.000.000.000 wei.
- Caja financiador: **45.363.588.000.000.000 wei**. No restar de nuevo gas del operador ni volver a sumar la misma dirección como builder.
- Venta: 8.249365645570551238 WETH; deuda 8 WETH; unwrap 0.09 WETH para R=0.05 ETH y tip=0.04 ETH; residuo operador 0.159365645570551238 WETH.

El gasto DEX ya está incorporado en la salida; no se descuenta otra comisión hipotética. ETH y WETH conservan libros distintos. R y tip proceden del excedente vendido, no son préstamos adicionales. La devolución U es saldo efectivamente devuelto, no devolución teórica. El cargo de oportunidad de 1 bp de expedientes previos es un supuesto de laboratorio, no una prima Titan/Quasar; las cifras anteriores son caja antes de costes comerciales desconocidos.

**Tres conceptos distintos:** R es ejecutor→financiador; U es operador→financiador por remanente del anticipo; el refund API es builder→destinatario de recompensa. No son el mismo flujo ni se compensan automáticamente. En V05 R termina en otro actor: ese cobro no puede usarse para demostrar beneficio del financiador que desembolsó A.

## Fallos: caja observada frente a responsabilidad desconocida

| Condición | Efecto probado o condicionado | Quién soporta caja / deuda |
|---|---|---|
| Ninguna tx incluida | En el control F01 no hay gas on-chain; costes fuera de cadena desconocidos | Sin cargo de cadena observado; no establece gratuidad comercial |
| Solo anticipo | V07: financiador -0.000052 ETH, EOA retiene 0.00001 ETH, cuatro tx pendientes | Financiador pierde caja; retorno/cobro futuro UNKNOWN; saldo retenido no es ingreso |
| CREATE o liquidación revierte | Gas de esa tx permanece; fondeo/despliegues anteriores no se revierten colectivamente | Sender paga con sus fondos/anticipo; derecho contra propietario UNKNOWN |
| Falta venta/repago/callback | La llamada revierte; no contar transferencias revertidas ni repago inexistente | Gas persiste; protocolo no completa el flash impago; financiación externa no queda resuelta |
| R, tip o U falla/se omite | No acreditar pago intentado; puede quedar anticipo o remuneración pendiente | Caja por receptor efectivo; obligación jurídica/pérdida final UNKNOWN |
| Gas/cap cambia | Cap limita reserva, precio efectivo determina gasto; U firmado puede no caber | Necesidad de nuevo monto/política verificada; no modificación automática de instrucciones firmadas |
| Beneficio builder antes de payout | NQC023 net_050 cambia a negativo después de pagar al proponente | Saldo intermedio no es viabilidad; fuente aquí es resumen auditado previo |
| Reorganización | Control heredado excluye recibos huérfanos de la rama canónica local | No acredita recuperación real, indemnización ni frecuencia; términos UNKNOWN |

Los controles de parcialidad muestran exposición EVM; **no prueban que Titan o Quasar admitan esos parciales**. La política pública de bundle y las listas revert/drop son distintas de atomicidad entre transacciones o un seguro financiero. Operaciones obligatorias no deberían hacerse opcionales para forzar aceptación; listas vacías tampoco demuestran cobertura de pérdidas.

La obligación intratransacción de Morpho puede estar saldada mientras el financiador externo pierde dinero o conserva una reclamación desconocida. Ningún documento revisado acredita límites aplicables a NQC sobre garantías, colateral propio, deuda diferida o recurso personal. Por eso todos esos campos se mantienen UNKNOWN, aunque una fixture los suponga nulos.

Para cerrar financiación hacen falta tanto un resultado económico favorable **para cada participante necesario** como un instrumento verificable que asigne las obligaciones y pérdidas. No necesariamente un contrato privado: un mecanismo público aplicable podría servir, si demuestra los extremos faltantes. No se aceptó ningún compromiso en NQC057.
