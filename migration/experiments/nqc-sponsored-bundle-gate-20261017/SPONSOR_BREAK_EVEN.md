# Financiador, builder y condiciones de equilibrio

La contabilidad ETH del financiador se verifica exactamente como `R + U + V - A - F - P - O`. El principal A y el saldo U no se cargan dos veces. En el escenario C1 de cash cero:

| Partida | Wei | Evidencia |
|---|---:|---|
| A desembolsado | 30,000,000,000,000,000 | Recibo topup |
| U efectivamente devuelto | 25,405,588,000,000,000 | Recibo retorno exitoso |
| R recibido desde ejecutor | 50,000,000,000,000,000 | CALL comprometido |
| V adicional | 0 | Ningún flujo adicional observado |
| F gas de topup | 42,000,000,000,000 | 21,000 × 2 gwei |
| P directo pagado por financiador | 0 | El tip directo lo paga el ejecutor desde la conversión |
| O | 2,042,000,000,000,000 | Fee builder 0.002 ETH + gas de ese pago |
| Margen de caja | **43,321,588,000,000,000** | Igual al delta ETH del financiador |
| Cargo de oportunidad supuesto | 3,000,000,000,000 | ceil(A/10000), hipótesis de 1 bp por intento |
| Margen después del cargo supuesto | **43,318,588,000,000,000** | MODEL_ONLY |

El builder simulado recibe 0.002 ETH. El proponente recibe separadamente 0.04 ETH más priority fees de las transacciones; base fees se queman. Esos pagos no prueban ingresos de Titan ni Quasar. El financiador empieza con 1 ETH sintético, no con cero; lo demostrado es ausencia de aporte inicial del **propietario NQC**, condicionada al capital externo.

Si financiador y builder tuviesen el mismo dueño económico, la transferencia de 0.002 sería interna y se cancelaría al consolidar: margen conjunto de caja 0.045321588 ETH en C1 base; el gas del pago sigue consumido. Es una hipótesis de titularidad explícita, no una identidad verificada. Proponente separado en ambos modelos.

Esa distinción también cambia la evaluación a 21 gwei: el financiador **separado** pierde 0.001123326 ETH, pero el grupo hipotético financiador+builder queda en +0.000876674 ETH, o +0.000846674 tras oportunidad. La política predeterminada rechaza la pérdida del participante separado; no se sustituye su identidad para hacerla pasar. El escenario consolidado es otro MODEL_ONLY, sensible a costos comerciales desconocidos y sin dueño común real acreditado.

## Región favorable y fronteras exactas

La conversión medida produce excedente de 0.249365645570551238 WETH sobre la deuda. R=0.05 y tip=0.04 dejan 0.159365645570551238 WETH a NQC. A 2 gwei los financiadores de C1 y C2 también tienen margen positivo después de gas, fee builder y el cargo explícito de oportunidad. Es una región local condicionada; infraestructura, fallos agregados, términos comerciales, stake, contratación y recurso personal permanecen **UNKNOWN**, no cero.

Manteniendo constante el gas medido y A=0.03 ETH, el mínimo R para dejar al financiador al menos un wei es `fee_builder + gas_total × precio + ceil(A/10000) + 1`:

| Ruta | R mínimo a 2 gwei (wei) | Máximo precio efectivo con margen positivo (wei/gas) |
|---|---:|---:|
| C1 cash cero | 6,681,412,000,000,001 | 20,518,500,722 |
| C1 cash ocho | 6,654,052,000,000,001 | 20,639,201,625 |
| C2 primer ciclo cash ocho | 12,395,258,000,000,001 | 9,237,068,594 |

El R máximo aritmético para mantener NQC estrictamente positivo, con ese output y tip fijo, es 209,365,645,570,551,237 wei; para respetar mínimo contractual de 0.01 WETH es 199,365,645,570,551,238. Cambiar R exige cambiar reserva/calldata y reejecutar, pues el gas también puede cambiar. Estos intervalos son `MODEL_ONLY`, no ofertas comerciales.

**Rentabilidad no basta para poder arrancar.** A 0.03 ETH fijo las fronteras de tarifa anteriores pueden ser inalcanzables por el máximo saldo exigido en un prefijo. `break-even.json` incluye además el modelo uniforme `cap=precio`: la reserva mínima es `max_i(gas_anterior_consumido + gasLimit_i) × precio`, excluyendo U, que depende del saldo disponible. Los coeficientes son 4,411,179 para C1 y 8,897,777 para C2 primer ciclo. Se calculan tanto la tarifa financiable con A fijo como la frontera conjunta elevando A al mínimo necesario y cobrando su mayor costo de oportunidad. La frontera y el siguiente wei se verifican con aritmética entera. No se confunde esta sensibilidad con replays adicionales.

A 21 gwei y A=0.3 ETH, C1 realmente ejecutado deja al financiador −0.001123326 ETH de caja, −0.001153326 con oportunidad, pese al WETH positivo NQC. **Se rechaza** por participación no rentable del financiador. Si U falta, el criterio no acepta apropiarse de la financiación retenida como ingreso. Si R revierte, tampoco se cuentan flujos de esa llamada revertida.

## Datos que una simulación local no puede certificar

El prefiltro puede verificar estado de la fixture, bytecode, orden, nonces, gasto, capacidades por prefijo, deudas, flujos y rechazo bajo umbrales declarados. No conoce saldos/ingreso neto reales del builder, su bloque competitivo, políticas de selección/reemplazo, contraparte ni condiciones sin recurso. Conserva el límite documental de `../morpho-sponsor-e2e-20261017/BUILDER_ACCEPTANCE_BOUNDARY.md`; no se efectuaron nuevas llamadas a Titan/Quasar ni se revalidó su política comercial en producción. Un programa público verificable podría aportar evidencia; no se exige necesariamente un acuerdo bilateral.

`sponsorRefundWei` paga al financiador en este ejecutor. No es el refund de recompensa hacia el usuario de las APIs de builders. Una simulación favorable tampoco acredita inclusión ni disponibilidad del financiamiento.
