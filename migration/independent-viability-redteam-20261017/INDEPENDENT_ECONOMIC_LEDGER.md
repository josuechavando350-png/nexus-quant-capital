# NQC - Auditoría contable independiente, Directiva 002

Fecha: 17 de octubre de 2026. Corte de fuentes: Morpho `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`; Robinhood/viabilidad `6693542e675f930a7ef0a4fd60cb72e7a6608845`.

## Dictamen

**La aritmética del caso B coincide exactamente con lo reportado en el expediente. Su rentabilidad neta para NQC sigue sin demostrarse.** La reconstrucción independiente del recibo, la traza y el bloque guardados produce un residual condicionado de **0.001651296044494913 ETH equivalente** después del repago, el pago coinbase y el gas observados. Se conservan como desconocidos las obligaciones externas, el patrocinador y la propiedad económica conjunta del sender/ejecutor. [B1–B5]

El máximo precio entero de gas que deja un residual estrictamente positivo, manteniendo esos flujos y las 745509 unidades de gas, es **2481140052 wei/gas = 2.481140052 gwei**. En esa frontera quedan **743570 wei**; un wei/gas adicional deja **−1939 wei**. A 3 gwei el residual es **−386814760229962 wei**. Se refuta ese escenario de costes; no se refutan todas las liquidaciones Morpho. [B1, B2, B5]

Se ejecutaron **25 pruebas unitarias propias** y diez controles T-01…T-10. El PASS de un control significa que la regla de rechazo o la identidad contable funciona. No significa patrocinio aceptado, dinero ganado ni replay EVM. No se ejecutaron las suites de Astra ni se importó ninguno de sus módulos.

## 1. Procedencia y alcance independiente

El paquete conserva dentro de `evidence/accounting_inputs.json` los textos UTF-8 exactos de las fuentes consultadas. Se recalculó la identidad Git blob de cada archivo completo; un extracto de `historical_rpc_audit.py` se marca expresamente como extracto y no se autentica como archivo completo. Los SHA-256 de contenido y los resultados se guardan en `evidence/accounting_results.json`; las órdenes, UTC, salidas y hashes ejecutados están en `evidence/accounting_test_output.txt`.

La independencia de esta auditoría es **aritmética y metodológica**: se decodificaron de nuevo las cantidades del recibo y las llamadas nativas, se construyó un libro propio y se comprobó la fórmula mediante enteros. La adquisición original de los datos sigue siendo la del expediente anterior. Una respuesta RPC archivada y una traza de indexador no se convierten en una segunda observación nueva por descargarlas otra vez de GitHub. Tampoco prueban por sí solas consenso, runtime histórico, propiedad de direcciones o preestado completo.

La lectura GitHub de los primeros nueve archivos se registró a las 15:46:24 UTC. El recibo original declara captura `2026-10-17T04:11:08.409531+00:00`; el control getLogs declara `2026-10-17T04:46:47.358491+00:00`. Ambos describen la transacción del 14 de octubre, no una señal observada antes de ella. Robinhood se leyó del caché compartido exacto por SHA; los tiempos de registro no se presentan como tiempos de señal. [B1, B6, R1]

**Clasificaciones:** cantidades del expediente = REPORTADO; identidades algebraicas y cruces de archivos repetidos aquí = REPRODUCIDO_LOCALMENTE; escenarios de costes y deudas = SIMULADO; neto NQC, patrocinio y captura = PENDIENTE. El saldo inicial desconocido se conserva como desconocido incluso si su cambio reconstruido es cero.

## 2. Caso B: identificación y transferencias

Cadena Ethereum, chain ID 1; bloque **26190955**, transacción índice **1**, hora de bloque reportada `2026-10-14T13:11:35Z`. Hash de transacción `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`; hash de bloque `0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8`. Se exige consistencia de estas identidades antes de calcular. [B1–B4]

| Partida | Cantidad exacta | Tratamiento |
| --- | ---: | --- |
| ezETH obtenido y transferido a Liquidity | 24.343983926960874121 ezETH | Inventario recibido y vendido; no resultado monetario aislado |
| Venta nativa Fluid | 26.409680973611000000 ETH | Entrada de conversión, ya neta del resultado de la ruta |
| Repago Morpho | 26.039738525656992415 WETH | Obligación efectivamente transferida |
| Venta menos repago | 0.369942447954007585 ETH equivalente | Excedente anterior a coinbase y gas |
| Pago completo a coinbase | 0.368092735714237547 ETH | Salida; titular económico del builder no demostrado |
| Incremento WETH del ejecutor después de coinbase | 0.001849712239770038 WETH | Excluye inventario previo |
| Gas sender | 745509 × 266148625 wei | 198416195275125 wei |
| Residual condicionado tras costes conocidos | 1651296044494913 wei | Cota aritmética antes de obligaciones no conocidas |
| Inventario WETH previo | 0.006392502690919791 WETH | Nunca se suma a ingreso |
| WETH final inferido | 0.008242214930689829 WETH | Incluye inventario previo; no todo es beneficio |

La entrada ETH desde Liquidity coincide con el depósito WETH; el repago se obtiene del evento Transfer WETH del ejecutor a Morpho. El retiro WETH coincide con la transferencia nativa a la dirección coinbase del bloque guardado. El gas del recibo concuerda con el del indexador. No se vuelve a descontar una supuesta comisión DEX del importe vendido: esa salida ya refleja el resultado económico de la conversión. [B1–B5]

### Libro por participante y activo

| Participante / activo | Inicial | Final | Cambio reconstruido | Límites |
| --- | --- | --- | ---: | --- |
| Ejecutor histórico / WETH | 0.006392502690919791 | 0.008242214930689829 inferido | +0.001849712239770038 | Propiedad NQC no acreditada |
| Ejecutor histórico / ETH | UNKNOWN | UNKNOWN | 0 | Cambio cero no implica saldo inicial cero |
| Ejecutor histórico / ezETH | UNKNOWN | UNKNOWN | 0 | Se convierte todo lo recibido en esta operación |
| Sender / ETH | UNKNOWN | UNKNOWN | −0.000198416195275125 | No se prueba mismo titular que el ejecutor |
| Coinbase / ETH | UNKNOWN | UNKNOWN | +0.368092735714237547 | Dirección receptora conocida; ingreso del builder no acreditado |
| Morpho / WETH | UNKNOWN | UNKNOWN | +26.039738525656992415 | Transferencia de repago; no P&L propio |
| Liquidity / ETH | UNKNOWN | UNKNOWN | −26.409680973611000000 | Contrapartida de venta, no pérdida aislada del venue |
| Liquidity / ezETH | UNKNOWN | UNKNOWN | +24.343983926960874121 | No se valora ni atribuye margen del venue |
| Sponsor / activos y pasivos | UNKNOWN | UNKNOWN | UNKNOWN | Ningún compromiso NQC acreditado por estos archivos |
| Fundador NQC / obligaciones | UNKNOWN | UNKNOWN | UNKNOWN | Deben quedar probadamente en cero para admisión |

Las direcciones relevantes están en los insumos. El ejecutor histórico es `0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd`, el sender `0xd9fffdf0c4b18fb7e225da15b2af9f88e55676c3` y coinbase `0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97`. No se atribuye a NQC ninguno de esos flujos por semejanza técnica. [B1–B4]

## 3. Frontera exacta de gas y obligaciones adicionales

Sea S la venta, D el repago, B el pago coinbase, g las unidades de gas, p su precio efectivo total y E los costes adicionales efectivos que no están contabilizados en otra partida:

`H(p,E) = S − D − B − g*p − E`.

Para `E = 0` **como escenario antes de costes desconocidos**, el dinero disponible para gas es `S−D−B = 1849712239770038 wei`. La solución entera para positividad estricta es:

`p_max = floor((1849712239770038 − 1) / 745509) = 2481140052 wei/gas`.

| Precio efectivo total, wei/gas | Residual, wei | ETH equivalente |
| ---: | ---: | ---: |
| 0 | 1849712239770038 | 0.001849712239770038 |
| 266148625 | 1651296044494913 | 0.001651296044494913 |
| 1000000000 | 1104203239770038 | 0.001104203239770038 |
| 2481140051 | 1489079 | 0.000000000001489079 |
| 2481140052 | 743570 | 0.000000000000743570 |
| 2481140053 | -1939 | -0.000000000000001939 |
| 3000000000 | -386814760229962 | -0.000386814760229962 |
| 5000000000 | -1877832760229962 | -0.001877832760229962 |
| 10000000000 | -5605377760229962 | -0.005605377760229962 |

El punto 0 wei/gas es una cota algebraica; no afirma gas gratis. El precio es **efectivo total**, no sólo priority fee. Todos los puntos conservan la venta, el repago, las unidades de gas y la oferta coinbase del tercero. Suprimir esa oferta o sustituir el gas por una cifra NQC cambiaría el escenario de inclusión y ejecución.

Al precio observado, `E = 1651296044494912` permite exactamente 1 wei; `E = 1651296044494913` deja cero. Para cualquier coste positivo x, `H(p,E+x)=H(p,E)−x`. **La cota no puede mejorar al agregar un coste real positivo.** Las pruebas cubren un wei, el agotamiento exacto y el cruce a pérdida. Con obligaciones externas desconocidas se devuelve `null/UNKNOWN`, no `E=0`.

### Evitar duplicar financiación sobre esta cota

Si un sponsor adelanta A a un perímetro propietario, recibe U sin usar y R de repago, el efectivo final condicionado de ese perímetro incorpora `+A−U−R`. No corresponde restar A, gas y R como tres gastos nuevos. Para una misma ruta cuyo H ya descontó el gas, el efecto adicional de esta financiación es `A−U−R`, y sólo después se restan obligaciones terminales y costes no incluidos. Cualquier traslado real de pagador exige reconstruir las transferencias de nuevo; H no es una cotización de patrocinio.

## 4. Ledger del builder

Se conservan los símbolos de la Directiva: A = anticipo; U = anticipo no usado y devuelto; R = reembolso de ejecución; V = ingresos externos verificados; F = gas de financiación; P = pago separado al proponente; O = otros costes.

`M_builder = R + U + V − A − F − P − O`.

Para exigir un margen mínimo b:

`R >= A + F + P + O + b − U − V`.

El gas pagado con A está contenido en A; no vuelve a descontarse como F. F sólo cubre el coste adicional de financiar, si existe. R y U deben representar transferencias distintas. El pago a coinbase del caso B no se incorpora como V mientras no exista evidencia del derecho económico del builder sobre él. Si P ya fue absorbido por otro término, ese término debe reclasificarse y documentarse antes de sumar.

Ejemplo **SIMULADO** en una sola unidad: A=100, U=20, R=90, V=5, F=2, P=3, O=1 deja M_builder=9. El script rechaza U>A. Con V desconocido devuelve UNKNOWN. Que una fórmula permita elegir V favorable no verifica su existencia.

Top-up aislado: si A=100 se devuelve completo como U=100 pero la financiación consumió F=2, el builder queda en −2. Si el fundador debe reponer esos 2, falla capital cero. Si la obligación de reposición no se conoce, el resultado es UNKNOWN; no se presume que la atomicidad elimina esa factura.

## 5. Activos netos del propietario y regla de pasivos

Para un perímetro explícito de direcciones con propiedad probada:

`N_t = valor_realizable_activos_t − pasivos_directos_t − pasivos_contingentes_t`.

`M_owner = N_final − N_inicial + distribuciones_fuera_del_perímetro − aportaciones_del_fundador − donaciones/subvenciones`.

Los préstamos no son ingreso: su entrada aumenta activos y su saldo pendiente aumenta pasivos. Los reembolsos pagados reducen activos y extinguen el pasivo correspondiente; no se descuentan otra vez como obligación terminal. Por ejemplo, activos 15 y deuda 10 producen el mismo neto 5 que activos 5 y deuda 0 después del pago. Una reserva inicial de 10 más aportación 4 y donación 6 que termina en 20 produce margen 0.

Los activos y las obligaciones se llevan **por token y participante** antes de consolidar. ETH, WETH, ezETH, USDG, USDC y USD no son una única columna sin valoración documentada. La equivalencia ETH/WETH aquí explica flujos de wrap/unwrap guardados; no prueba conversión gratis futura. Los costes de creación, infraestructura adquirida, financiación y fallos se imputan una sola vez: como salida pagada o pasivo pendiente, identificando el acreedor y la operación.

Un pasivo contingente no se elimina por ser improbable. Hay que acreditar quién soporta cada fallo y el alcance de reposición, garantías y facturación. Un valor desconocido impide certificar pasivo cero. El founder gate exige cero aportación personal necesaria, cero deuda personal y cero obligación de cubrir fallos.

**Contraejemplo decisivo T-09:** activos finales 5, deuda personal 1, sin otros movimientos, producen M_owner=4. El resultado patrimonial es positivo y la deuda sigue existiendo. Por ello `M_owner>0` no sustituye `founder_obligation=0`.

## 6. Robinhood: Nitro y paymaster sin duplicación

El README de viabilidad reporta, para chain ID 4663, bloque 66744162, índice 1: **32.060665 USDG** en la cuenta, **57601054408000 wei** de comisión nativa simulada y **79616762214000 wei** de transferencia paymaster→beneficiario bundler. También reporta fixtures financiados de 0.1 ETH de depósito y 0.01 ETH de saldo bundler. Esos importes son resultados y condiciones de una simulación previa, no nuevas capturas ni mínimos comerciales. [R1]

| Perímetro | Flujo que corresponde contar | Importe exacto, wei |
| --- | --- | ---: |
| Paymaster con bundler externo | Salida al bundler | 79616762214000 |
| Bundler | Entrada menos comisión nativa antes de otros costes | 22015707806000 |
| Paymaster + bundler consolidados | Salida neta a red; transferencia interna cancela | 57601054408000 |
| Suma incorrecta como dos gastos del mismo perímetro | Cargo paymaster + comisión nativa | 137217816622000 |

El cobro Nitro ya se reconstruyó en el expediente como `feePayment−gasRefund`, concordante con `feeCollection`. Esta auditoría verifica la consolidación contable de los valores reportados; **no ejecutó Nitro ni contrastó nuevamente sus trazas**. El margen de 22015707806000 wei es un resto de dos flujos antes de otros costes, no beneficio libre del bundler. La ausencia de un componente DA extra en aquella consulta no acredita DA gratis en general. [R1]

**USDG no se convierte automáticamente en USD.** La valoración requiere cantidad, bid ejecutable, hora, profundidad, posibles desvíos de peg y coste de conversión. Un ejemplo explícitamente hipotético de 32.060665 USDG, bid 0.95 USD y coste 0.1 USD resulta en 30.35763175 USD. Con cotización o coste desconocido, el script devuelve UNKNOWN. No usa ese ejemplo como ingreso esperado.

## 7. Superficie de elegibilidad con lógica trivaluada

`eligible = (net_owner>0) AND (margin_sponsor>=umbral) AND (founder_obligation=0) AND time_eligible AND execution_valid`.

| Conjunción | Resultado |
| --- | --- |
| Todas TRUE | TRUE |
| Al menos una FALSE, incluso con otras UNKNOWN | FALSE |
| Ninguna FALSE y al menos una UNKNOWN | UNKNOWN |

La clase Truth impide convertir accidentalmente cualquiera de sus valores a un booleano Python. Un hash de bloque mal formado, un log alterado o una coordenada RPC no canónica no pueden validar un estado. Coincidir altura y hash sólo prueba coherencia de esos identificadores; no basta para probar disponibilidad temporal anterior al ganador.

Para NQC, `actual_net_after_unknown_obligations=null`, sponsor desconocido, obligaciones del fundador desconocidas, tiempo desconocido y ejecución admisible desconocida dan **UNKNOWN**. En la matriz comercial ese resultado impide admisión. Una ruta local técnicamente exitosa puede coexistir con todas esas incógnitas.

## 8. T-01…T-10: controles ejecutados y límites

PASS del guardrail = el control rechaza correctamente el supuesto inválido o verifica la igualdad acotada. La columna de evidencia no es una aprobación comercial.

| ID | Regla examinada | Guardrail | Verificación histórica/comercial | Límite |
| --- | --- | --- | --- | --- |
| T-01 | Principal cero con primer gas sin pagador | PASS | BLOCKED | Pagador y compromiso real no acreditados |
| T-02 | Anticipo con factura posterior al fundador | PASS | BLOCKED | Contraejemplo simulado; contrato real pendiente |
| T-03 | Top-up retornado pero gas de financiación perdido | PASS | BLOCKED | Sin condiciones reales de reposición/inclusión |
| T-04 | Coinbase no atribuye ingresos al builder/NQC | PASS | PASS | Sólo identidad del receptor en archivos guardados; propiedad pendiente |
| T-05 | Gas 2.481140052 gwei y 3 gwei | PASS | PASS | Sólo aritmética de flujos fijos; no replay ni cotización |
| T-06 | Paymaster/Nitro sin doble conteo | PASS | NOT_RUN | Consolidación con valores del README; Nitro no reejecutado |
| T-07 | Bloques 26210230/26210231/26210229 incompatibles | PASS | NOT_RUN | Fixture documental de alturas; ninguna captura nueva |
| T-08 | getLogs[] ante recibo positivo conocido | PASS | PASS | Dos envelopes guardados; no prueba nueva de consenso o cobertura global |
| T-09 | M_owner positivo con fundador endeudado | PASS | BLOCKED | Rechazo lógico; ausencia real de pasivos aún no acreditada |
| T-10 | Ganancias históricas de tercero no son NQC | PASS | BLOCKED | Sin atribución y liquidación económica NQC verificadas |

El control T-08 coteja filtros del mismo blockHash, contrato y topic. Para un log devuelto exige contenido igual en los campos disponibles, incluidos address/topics/data/blockHash/coordenadas/removed, y rechaza identidades duplicadas. Si un único control positivo coincidiera, eso acreditaría **ese control individual**, no cobertura universal.

## 9. Objetivos de ingreso: sensibilidad, no pronóstico

Se evalúa `victorias = ceil((T+F)/m)` con m estrictamente positivo. Todas las cantidades USD de esta sección son **supuestos**, separados de ETH/WETH/USDG y de los importes históricos. F=0 representa un supuesto algebraico; no prueba infraestructura gratuita. m debe ser margen disponible después de costes atribuibles y financiación de fallos, o esos fallos deben agregarse por separado.

| F mensual supuesto, USD | m neto por victoria supuesto, USD | T=1000 | T=5000 | T=10000 | T=50000 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1 | 1000 | 5000 | 10000 | 50000 |
| 0 | 5 | 200 | 1000 | 2000 | 10000 |
| 0 | 10 | 100 | 500 | 1000 | 5000 |
| 0 | 50 | 20 | 100 | 200 | 1000 |
| 0 | 100 | 10 | 50 | 100 | 500 |
| 0 | 500 | 2 | 10 | 20 | 100 |
| 100 | 1 | 1100 | 5100 | 10100 | 50100 |
| 100 | 5 | 220 | 1020 | 2020 | 10020 |
| 100 | 10 | 110 | 510 | 1010 | 5010 |
| 100 | 50 | 22 | 102 | 202 | 1002 |
| 100 | 100 | 11 | 51 | 101 | 501 |
| 100 | 500 | 3 | 11 | 21 | 101 |

Ejemplo de redondeo: objetivo 1000, F 100 y m 500 requieren ceil(1100/500)=3 victorias. Con m≤0 la función rechaza la fórmula; con F desconocido conserva UNKNOWN. La tabla no asigna a NQC ninguno de los márgenes hipotéticos.

Los 143 eventos/141 transacciones del expediente son una muestra histórica observada, no el número de operaciones elegibles o ganables por NQC. No se obtiene una tasa de victoria ni un promedio de ingresos multiplicándolos por m. Faltan intentos elegibles, ofertas perdidas, costes de fallos y una medición competitiva de inclusión. **La capacidad mensual continúa NO ESTIMABLE; este expediente no certifica nuevo P&L de NQC.** [M1]

## 10. Discrepancias, decisiones y siguiente prueba

No apareció una discrepancia numérica entre esta reconstrucción final y los resultados de Astra en las fuentes fijadas. Durante la revisión se detectó y corrigió un error de transcripción propio en un borrador: la conversión ETH→wei de los dos cargos Robinhood estaba 1000 veces por debajo de la escala correcta. Los valores finales se derivan automáticamente de los decimales del README y una prueba rechaza esa escala incorrecta. El caso B, decodificado desde recibo/traza, no estuvo afectado. La diferencia esencial es de **alcance de evidencia**: el cálculo reproducible conserva una cota antes de costes desconocidos y resultados de terceros. No demuestra ingreso NQC. La frontera exacta añade que un incremento de 1 wei/gas lleva de 743570 wei a −1939 wei; la refutación no depende de redondeo decimal.

Las prioridades económicas resultantes son:

1. Identificar términos verificables de financiación para primer gas, creación y fallos, con pagador, topes, dirección y ausencia de deuda del fundador. Una fórmula builder positiva no satisface ese requisito.
2. Obtener para una sola oportunidad el paquete que permita contrastar preestado completo, ruta y titularidad económica, y separar reembolso/gas/oferta sin partidas duplicadas. El replay pertenece a Astra.
3. Acreditar que señal y estado suficiente estuvieron disponibles antes de la admisión competitiva. La hora de descargar archivos históricos no satisface esa puerta.

La investigación continúa con gasto cero. El resultado de esta contabilidad por sí solo no habilita ninguna operación comercial.

## 11. Reproducción y archivos

Desde esta carpeta:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 accounting_audit.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_accounting_audit
```

`accounting_audit.py` genera resultados locales y usa sólo biblioteca estándar. El comando no contacta redes. Los scripts originales de Astra se conservaron como textos de lectura y nunca se importaron. El segundo comando ejecuta 25 pruebas propias, incluyendo casos frontera, una enumeración exhaustiva de pequeños enteros, datos alterados, desconocidos y obligaciones positivas. La ejecución registrada terminó con código 0. No se mezclan las 168 Python / 50 Solidity / 9 de aislamiento reportadas anteriormente con este contador. [M1]

## Fuentes versionadas

Todos los originales completos de la tabla están preservados como cadenas UTF-8 dentro de los insumos. Los identificadores entre corchetes remiten a esta tabla; el ledger JSON añade fechas, método, unidades, evidencia faltante y estado por aseveración.

| ID | Fuente exacta por SHA | Git blob SHA |
| --- | --- | --- |
| [M1] | [monthly](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/MONTHLY_POTENTIAL.md) | `81683d23066fc49f98fc3966279c58030d8781c1` |
| [M2] | [profitability](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/PROFITABILITY_RESULTS.md) | `5525a49a4cb4be95c357d3b0a6a3ac1318183c43` |
| [M3] | [astra_route_script_read_only](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/case_b_route_audit.py) | `bbe1d77b3d65c20300c28e51104211701a3892ce` |
| [B1] | [case_b_saved_receipt](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-profitability/b-receipt.json) | `259506f36686e9b141d803143d4c83658a40bddb` |
| [B2] | [case_b_saved_trace](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17/case_b_trace.json) | `ff05f926c2b6c2b0ee934a03e2552ce9fcec61df` |
| [B3] | [case_b_saved_block](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17/case_b_block.json) | `79b37296d0b113045afb6655db84d8de08b032a7` |
| [B4] | [case_b_indexer](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17/case_b.json) | `5db805fa994b636db870f41f8261cb0277d36181` |
| [B5] | [reported_case_b_results](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-prospective-recovered/final-case-b-costs.json) | `fc9baeaa1764248bdf4cf6b95be8fda8f0eaba70` |
| [B6] | [case_b_saved_getlogs](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-monthly/b-morpho-logs.json) | `676535a7bb772f3a696c598f2f36c5af939661bf` |
| [R1] | [robinhood_readme](https://github.com/josuechavando350-png/nexus-quant-capital/blob/6693542e675f930a7ef0a4fd60cb72e7a6608845/migration/robinhood-real-state-replay-20261016/README.md) | `ee3103124abb51352b9fd746ca8e3fad3c57ef5d` |
