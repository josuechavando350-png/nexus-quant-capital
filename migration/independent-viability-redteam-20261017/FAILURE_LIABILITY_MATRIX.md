# NQC — Matriz de fallos y responsabilidad económica

Fecha: 17 de octubre de 2026. Investigación B de la Directiva 002. **Todos los escenarios de este documento son construcciones hipotéticas de falsación. No describen fallos observados de un bundle o UserOperation NQC enviado.** No se ejecutó ninguna simulación remota, firma, transmisión ni admisión real.

Las reglas documentales D1–D8 y las fichas de proveedores están en SPONSOR_NO_RECOURSE_AUDIT.md. Las fuentes S-SP-* se identifican en evidence/sponsor_sources.json. Aquí se modelan límites de responsabilidad, no se duplica la ingeniería de Astra.

## 1. Convenciones y criterio que se intenta refutar

El criterio es **cero aportación y cero obligación personal del fundador desde el arranque y en todos los fallos cubiertos**. No basta que una wallet operativa tenga saldo inicial cero o que el resultado de una aplicación sea positivo.

Los balances de las tablas son exclusivamente los de las secuencias estipuladas. Los ceros significan que la secuencia hipotética no contiene ese movimiento; no sustituyen datos reales desconocidos. En todas las rutas, facturación externa O_i, obligaciones personales ℓ_i, reservas utilizables y condiciones de recuperación reales siguen UNKNOWN.

Para un saldo total de un participante debe añadirse a la tabla todo coste o ingreso externo verificado. Si queda un término UNKNOWN, su saldo económico final completo también queda UNKNOWN. Si ℓ_i > 0, falla capital cero sin recurso aunque el activo del ejecutor aumente.

### Actores y activos

| Actor | Símbolo | Función |
|---|---|---|
| Fundador | H | Titular económico cuyo dinero, garantías y deuda se excluyen. Se mantiene separado de la cuenta operativa. |
| Ejecutor o smart account | E | Ejecuta la aplicación y recibe el resultado. |
| Sponsor externo | S | Adelanta capital y debe asumir los fallos según condiciones verificables. |
| Builder o bundler | B | Builder Ethereum, o emisor AA exterior, según la sección; se explicita cuándo coincide con S. |
| Paymaster / depósito | D | Derecho del paymaster sobre ETH custodiado en EntryPoint. No es caja del bundler. |
| Stake | K | Capital con restricciones de retiro, distinto del depósito gastable. |
| Proponente | P | Recibe un pago separado cuando existe y se demuestra su fuente. |
| Red y receptores de gas | N | Cuenta de conciliación de gas quemado y recibido; no es una wallet ficticia de Ethereum. |
| Mercado / protocolo / financiadores | X, Z | Contrapartes de la conversión y otros ingresos; cada activo debe conservarse por separado. |

En modelos Ethereum se usa ETH. En Robinhood se separan ETH y USDG. Saldos de D y K pertenecen económicamente a su propietario: no sumarlos de nuevo como riqueza de una entidad independiente al consolidar.

## 2. Modelo Ethereum de caja y obligaciones

En esta sección S = B: el builder financia. Estado inicial hipotético: S tiene b ETH; E tiene 0 ETH; H no aporta fondos. Tener b suficiente es un supuesto que debe probarse para una ruta real.

Transferencias de la secuencia:

1. T_f: S entrega A ETH a E y paga F ETH de gas.
2. T_l: E paga G de gas; la aplicación produce X ETH nuevos después de devolver principal y cubrir los intercambios internos de tokens.
3. Si se ejecutan, E devuelve U del anticipo y paga R de reembolso. S cobra V de otra fuente externa probada y paga P al proponente y O a terceros.

La fuente externa de V es distinta de R/U; si comparte un flujo con ellos debe dividirse una vez. No se presupone que un pago a coinbase sea R, V ni un pago a este builder. En un caso concreto se necesita trazar el destinatario económico.

### Estado final del modelo general de éxito

| Actor / activo ETH | Inicial | Final |
|---|---:|---:|
| S = B | b | b − A − F + R + U + V − P − O |
| E | 0 | A + X − G − R − U |
| Mercado que entrega el excedente | x | x − X |
| Fuente externa de V | z | z − V |
| Proponente | p | p + P |
| Receptores de otros costes | o | o + O |
| N, conciliación de gas | 0 | F + G |
| H, obligación personal | 0 | ℓ_i, que no se deduce del saldo E |

Las variaciones de ETH se conservan. Si alguno de esos receptores coincide con S, consolidar su ingreso de forma explícita. Las obligaciones crediticias tienen además una contrapartida acreedora; no aparecen como nueva caja.

X no puede incluir inventario preexistente ni principal de flash loan. Un libro real necesita, además, las piernas por token de la liquidación, repago, impuestos y DEX. Este modelo neteado no certifica esas piernas ni presume que una ruta concreta produzca X.

## 3. S1–S5 en Titan y Quasar

### S1 — Rechazo antes de inclusión

Secuencia estipulada: evaluación del bundle, rechazo, ninguna transacción de la secuencia entra en cadena. S conserva b; E conserva 0; N tiene delta 0. No nace gasto de gas on-chain de este intento bajo esa condición. Despliegues anteriores, procesamiento externo y condiciones de factura no desaparecen: O_1 y ℓ_1 siguen UNKNOWN.

| Proveedor | Aplicación y partes desconocidas | Prueba local posible | Veredicto |
|---|---|---|---|
| Titan | El rechazo no prueba compromiso financiero. Debe constar si el mecanismo se activó y si existía algún fondeo previo separado. | Traza sintética sin transacciones incluidas; verificar que el ledger no inventa anticipo, gas ni ingreso. | Condicionalmente compatible sólo si gastos externos son cubiertos sin recurso. NQC: NO_DEMOSTRADO. |
| Quasar | Igual balance estipulado. Rechazo por prioridad, firma o política no demuestra gas financiado ni cupo reservado. | Separar rechazo documental, ausencia de respuesta e inclusión perdida; no convertir un timeout en rechazo definitivo. | NO_DEMOSTRADO por O_1/ℓ_1 y reserva desconocidos. |

### S2 — Top-up incluido y liquidación omitida

Secuencia estipulada: T_f canónica; T_l no incluida. Esto se examina como top-up separado, omisión admitida por configuración o trayectoria tras reorg; **no se afirma que ocurra en un bundle normal que respeta su política**.

| Actor / ETH | Inicial | Final del horizonte |
|---|---:|---:|
| S | b | b − A − F |
| E | 0 | A |
| N | 0 | F |
| Protocolo / DEX | saldo previo | mismo saldo |
| H, deuda o reposición | 0 | ℓ_2 = UNKNOWN |

A permanece como activo en E; no es beneficio de liquidación ni devolución U. Si S conserva derecho/control de recuperación, puede ser un activo recuperable de S, pero una cuenta por cobrar no equivale a caja recuperada. Retirar necesita permiso, gas W y secuencia propios; dueño del riesgo y plazo son UNKNOWN.

| Proveedor | Frontera de atomicidad | Prueba local posible | Veredicto |
|---|---|---|---|
| Titan | Deben fijarse tratamiento de T_f añadido y flags. La publicación del mecanismo no especifica por sí sola todo resultado ante separación/reorg. | Modelo con T_f sola; cambiar omisión permitida/no permitida y comprobar que los resultados no se etiquetan como política real. | Capital cero sólo si S asume F, recuperación y pérdida de A sin recurso. NO_DEMOSTRADO. |
| Quasar | Revisión separada de droppingTxHashes y protección del fondeo. No inferir que la promesa de agrupación cubre obligaciones externas. | Mismo modelo de caja, con semántica propia de sus flags y dependencia expresa del top-up. | NO_DEMOSTRADO; no declarar como deuda cierta el anticipo tampoco. |

### S3 — Liquidación incluida que revierte

Secuencia estipulada: T_f ocurre; T_l incluida consume G_r ETH y revierte su aplicación. Requiere admisión explícita del fallo, una transacción separada o trayectoria posterior que lo permita. Con flags estrictos, un builder podría excluir el conjunto; eso sería S1.

| Actor / ETH | Inicial | Final modelado |
|---|---:|---:|
| S | b | b − A − F |
| E | 0 | A − G_r |
| N | 0 | F + G_r |
| Protocolo y DEX | saldo previo | mismo saldo por efectos internos revertidos |
| H, obligación | 0 | ℓ_3 = UNKNOWN |

Se exige A ≥ G_r en este modelo de pagador inicialmente vacío. El repago, swap, retorno de principal o puja **dentro de T_l** se revierte con la aplicación. Un pago anterior/separado conserva su propio destino. Si existe devolución posterior U, añadir +U a S y −U a E y cobrar su gas una sola vez.

| Proveedor | Parte que falta demostrar | Prueba local posible | Veredicto |
|---|---|---|---|
| Titan | Quién asume F + G_r y eventual saldo irrecuperable, y si T_f se mantiene en ese camino exacto. | Reversión interna con top-up previo; sumar fees y revertir exclusivamente efectos dentro de la transacción fallida. | Si H repone gas o A, REFUTADO para ese contrato. Sin términos: NO_DEMOSTRADO. |
| Quasar | Mismas responsabilidades, bajo sus condiciones independientes de reversión/omisión. | Ensayo de contabilidad equivalente, sin convertir allow-revert en garantía de margen del sponsor. | NO_DEMOSTRADO. Los flags son permisos técnicos, no indemnizaciones. |

### S4 — Ejecución exitosa, slippage y excedente insuficiente

Usar el modelo general con X_l menor al esperado. Si todas las obligaciones necesarias están protegidas dentro de T_l y no hay suficiente caja para pagarlas, la ruta debe revertir: contablemente vuelve a S3, no a pérdida on-chain cero.

Si la operación deja terminar con obligaciones posteriores, E puede tener A + X_l − G − R_pagado − U > 0 y todavía adeudar R_pendiente, gastos o reparto. Distinguir fondos prestados de rendimiento nuevo. Un reembolso hardcodeado que se paga antes de revisar el resultado puede dejar al propietario sin excedente, aun con sponsor positivo.

Una especialización analítica útil, no una ruta probada: si A sólo financia G, U = A − G se devuelve realmente y X_l es nuevo, entonces E final = X_l − R; margen sponsor = R + V − G − F − P − O. Un sponsor que requiere μ necesita R + V ≥ G + F + P + O + μ. El propietario exige X_l > R, y por separado ℓ_4 = 0. μ, V y obligaciones reales no se rellenan con cero.

| Proveedor | Déficit y responsable | Prueba local posible | Veredicto |
|---|---|---|---|
| Titan | Receptor/control y política determinan si falta ingreso, si se excluye la ruta o si alguien soporta déficit posterior. | Barrer X_l en los puntos de repago sponsor y mínimo del dueño; separar éxito EVM de cierre financiero. | REFUTADO si nace obligación personal; de otra forma, sin prueba de cobertura, NO_DEMOSTRADO. |
| Quasar | No presumir que un incremento nominal de builder satisface su margen con financiación/value/puja completos. | Mismos puntos frontera con costes propios y condiciones D2; no trasladar reembolsos Titan. | NO_DEMOSTRADO para NQC. |

### S5 — Inclusión parcial, reorg o fallo tardío

Secuencia hipotética: bloque C contiene T_f/T_l; luego queda huérfano o una nueva cadena canónica contiene un subconjunto. La documentación de Flashbots justifica que la exposición de transacciones tras reorg debe analizarse; no prueba un incidente NQC ni las reglas de otro builder. S-SP-18.

Balances canónicos posibles, siempre desde el mismo estado inicial:

| Nueva trayectoria canónica | S final | E final | Gas canónico |
|---|---:|---:|---:|
| Ninguna transacción reinsertada | b | 0 | 0 de esta secuencia |
| Sólo T_f | b − A − F | A | F |
| T_f y T_l revertida | b − A − F | A − G_r | F + G_r |
| Secuencia completa con nuevo estado | Fórmula general recalculada | Fórmula general recalculada | F + G nuevo |

No sumar el gas del bloque huérfano como si sus débitos siguieran en la cadena canónica. Sí pueden persistir gasto externo, cobros comerciales, liquidaciones ya efectuadas fuera de cadena o top-ups de bloques anteriores que continúen canónicos. O_5, clawbacks y ℓ_5 son UNKNOWN.

| Proveedor | Pendiente contractual y técnico | Prueba local posible | Veredicto |
|---|---|---|---|
| Titan | Momento de liquidación final, control del top-up y responsabilidad por transacciones reaparecidas. | Dos historiales locales hipotéticos, conciliación por hash canónico y exclusión de recibos huérfanos. | NO_DEMOSTRADO; atomicidad declarada no liquida derechos fuera de cadena. |
| Quasar | Mismo análisis con sus flags y condiciones; no afirmar separación intencional. | Recalcular por orden canónico y conservar recibo huérfano como evidencia separada. | NO_DEMOSTRADO. |

## 4. Robinhood: reservas AA y cinco escenarios

### Estado inicial antes del primer intento

Separar arranque y operación. Antes de probar una UserOp, alguien debe haber financiado contratos necesarios, depósito, stake exigible y caja del bundler. El estado del replay que supone despliegues y saldos existentes no paga esas acciones.

Se modela un tercero S que controla D = d ETH en EntryPoint, K = k ETH y wallet s ETH; bundler B tiene b ETH. La cuenta E tiene 0 ETH y 0 USDG; H aporta cero. d y b deben satisfacer los requisitos exactos de validación y transacción. **No se afirma que 0.1/0.01 ETH sean esos mínimos.** S-SP-20.

C_i es el cargo al depósito atribuido al UserOp; G_i es el gasto nativo de la transacción exterior. No son idénticos por definición. Si hay múltiples UserOps, fijar una regla de asignación del gasto conjunto; no adjudicar todo el handleOps a cada una.

### Tabla de balances por escenario

En S1/S3/S4 se parte del estado d, k, s, b ya descrito. S2 parte antes de un depósito nuevo de a ETH. Los costes previos de preparar ese estado se mantienen fuera del cuadro y deben agregarse.

| Escenario y secuencia | S wallet / depósito / stake ETH finales | B ETH final | E final | N / obligaciones |
|---|---|---:|---|---|
| S1. Rechazo off-chain, sin handleOps incluido | s / d / k | b | 0 ETH, 0 USDG | Gas nuevo 0; O_1 y ℓ_1 UNKNOWN. |
| S2. S deposita a, paga F_d; no hay UserOp | s − a − F_d / d + a / k | b | 0 ETH, 0 USDG | N +F_d; control y coste de retiro W UNKNOWN. |
| S3a. handleOps queda canónico, llamada de liquidación revierte; patrocinio sin cargo ERC20 previo | s / d − C_r / k | b + C_r − G_r | 0 ETH, 0 USDG de la ruta | N +G_r; quién repone D o paga factura, UNKNOWN. |
| S3b. handleOps entero revierte | s / d / k | b − G_outer | 0 ETH, 0 USDG de la ruta | N +G_outer; pagos internos de la transacción se revierten. |
| S4. UserOp exitosa con q_l USDG y reparto r pagado en USDG | s / d − C_l / k; S además +r USDG | b + C_l − G_l | 0 ETH, q_l − r USDG | N +G_l; conversión y obligaciones posteriores UNKNOWN. |
| S5. Estado observado deja de ser canónico | Recalcular según nueva secuencia | Recalcular según nueva secuencia | Recalcular, no duplicar ganancias | Facturas/clawbacks/finalidad: UNKNOWN. |

En S3a la reversión se refiere a la llamada de aplicación. No se presume que deshaga cambios de validación o creación de cuenta que puedan persistir si handleOps termina. Un paymaster con cobro ERC20 previo requiere otra tabla: no hereda el supuesto de cero transferencias de tokens de este escenario.

En S4, si q_l < r y el pago se exige de forma atómica sin otro saldo, la rama exitosa es inválida y se analiza S3. Si r se factura posteriormente, hay deuda o riesgo de cobro que debe registrarse, no un activo libre del dueño. S-SP-12 documenta un ejemplo de responsabilidad del cliente tras fallo de cobro ERC20; no acredita que el fundador sea ese cliente en un contrato inexistente.

### Asignación de responsabilidad, prueba y puerta por escenario

| Escenario | Quién adelanta o pierde en el modelo | Prueba offline posible y evidencia pendiente | Capital cero |
|---|---|---|---|
| S1 | Ningún nuevo pagador on-chain; costes previos/proveedor quedan fuera. | Validación negativa sin habilitar envío; registro de errores y facturación aplicable. | NO_DEMOSTRADO sin términos sobre O_1/ℓ_1. |
| S2 | S paga F_d; a queda como derecho sobre depósito, no beneficio NQC. Si el fondeo fue a B, rehacer balances S −a−F, B +a. | Separar depósito, stake y float; comprobar dueño y condiciones de retiro sin tratarlos como gastos consumidos íntegros. | Compatible sólo si tercero aporta y asume riesgo y retiro sin recurso; pendiente. |
| S3a | D paga C_r; B paga G_r y recibe C_r. Un mínimo de beneficio no elimina estos movimientos. | Comprobar evento de fracaso de UserOp, recibo exterior exitoso y deltas de D/beneficiary/emisor. | NO_DEMOSTRADO; factura o reposición personal lo refutaría. |
| S3b | B pierde G_outer; depósito y cobro internos se revierten. | Forzar fallo hipotético exterior (p. ej., liquidación final del beneficiary) con código fijado; verificar que el ledger no inventa C. | Requiere reserva y regla de pérdidas del bundler, no sólo paymaster. |
| S4 | D cubre C_l y B afronta G_l; reparto USDG no es ETH disponible. | Frontera q_l=r, suficiencia de postOp, mínimos y conversiones. Medir todos los costes con una política aplicable. | NO_DEMOSTRADO; q_l positivo no prueba ℓ_4=0. |
| S5 | Depende del estado canónico y de pagos fuera de cadena ya liquidados. | Diferenciar confirmación de secuenciador, publicación L1 y finalidad; registrar reorg y reconstruir cargos. | NO_DEMOSTRADO sin regla de recobro y finalización. |

Robinhood describe niveles distintos de confirmación y publicación L1; no se sustituyen por “irreversible al recibir un recibo”. Su documentación de gas integra ejecución L2 y datos L1 en el cargo nativo: no sumar de nuevo un componente ya incluido. S-SP-15/16. Ninguna latencia típica de documentación se presenta como medición NQC.

### Consolidación AA que evita el doble conteo

Si S controla el depósito y B es un tercero, el flujo de S es −C_i más sus costes propios. El flujo de B es C_i−G_i menos sus costes. Si S y B pertenecen al mismo propietario económico, el cargo C_i es interno y se cancela: el grupo paga G_i más costes externos. No descontar simultáneamente C_i y G_i del grupo. Tampoco sumar el valor completo de K como gasto y como pérdida otra vez: es capital inmovilizado cuya disponibilidad y recuperación tienen costes y riesgos distintos.

S-SP-10/11 sustenta los componentes técnicos v0.7; las reservas y condiciones comerciales del modelo siguen siendo hipotéticas.

## 5. S6 — Resultado positivo y fundador todavía endeudado

**Contraejemplo contable inventado, sólo en ETH. No son cantidades ni condiciones de NQC ni de un proveedor.**

Un tercero presta A = 0.005 ETH al ejecutor y paga F = 0.001 ETH de fondeo. La aplicación consume G = 0.005 ETH, produce X = 0.020 ETH nuevos netos de sus obligaciones internas y termina. No se devuelve dinero al prestamista dentro de la operación. Un acuerdo hipotético deja al fundador obligado por 0.010 ETH: 0.006 de financiación/coste y 0.004 de cargo comercial.

| Actor | Variación de caja ETH | Derecho u obligación fuera de caja |
|---|---:|---|
| Sponsor S | −0.006 | Crédito contra H de +0.010; no es dinero realizado. |
| Ejecutor E | +0.020 | El saldo no prueba que los costes externos estén liquidados. |
| Mercado X | −0.020 | Ninguna en este modelo cerrado. |
| N | +0.006 | Contrapartida de gas. |
| Fundador H, propietario de E | Acceso económico al saldo E | Deuda −0.010. |

El resultado de E es positivo; incluso el patrimonio neto modelado del propietario es +0.010 ETH después de reconocer la deuda. **La condición founder_obligation = 0 es falsa.** Por ello, ni P&L_E > 0 ni M_owner > 0 son suficientes para declarar capital cero sin recurso.

Si la deuda contractual fuera superior a 0.020 ETH, también sería negativo M_owner. Son dos preguntas separadas: rentabilidad y responsabilidad. Una estimación de beneficio no cancela la segunda.

## 6. Pruebas de falsación y estados a conservar

| Prueba propuesta | Fallo que detecta | Qué no demuestra |
|---|---|---|
| Ledger conserva A pendiente cuando sólo entra T_f | Contar un top-up como beneficio o devolución | Que el builder permite realmente esa secuencia. |
| Reversión interna conserva costes que corresponden | Afirmar que todo revert es gratis | Precio real, aceptación o política de pérdidas. |
| Reversión exterior elimina cobro interno C | Cobrar al depósito y al bundler ficticiamente a la vez | Reserva de B ni cobertura comercial. |
| Caso q_l = r y q_l < r | Éxito técnico mal clasificado como margen dueño positivo | Liquidez auténtica ni tasa de victoria. |
| Dos historiales canónicos alternativos | Duplicar gas o ingresos de un bloque huérfano | Probabilidad de reorg ni términos de clawback. |
| S6 con deuda registrada | Omitir una obligación por tener saldo positivo | Existencia de ese contrato para NQC. |

Son protocolos de prueba local propuestos. Esta misión no afirma haber ejecutado replays EVM de esos escenarios ni tener acceso a código privado de builders.

Sí se ejecutó una verificación aritmética de las identidades: diez controles de conservación por activo, la equivalencia del modelo de devolución U = A − G y el contraejemplo de deuda dieron PASS. Se usaron enteros elegidos para los modelos, no datos de mercado. Los flujos e instante de verificación están en model_evidence de evidence/sponsor_sources.json. Este control no incrementa los contadores históricos Python/Solidity de NQC ni demuestra aceptación.

**Conclusión de responsabilidad:** los mecanismos pueden mover el pagador inicial, pero la financiación sin recurso sólo queda demostrada al identificar reserva, derechos y dueño de pérdidas en todas las ramas aplicables. Para NQC, el pagador último y las obligaciones completas de S1–S5 permanecen NO_DEMOSTRADOS. No se certifica cobertura cero a partir de campos omitidos.
