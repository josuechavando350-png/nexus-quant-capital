# NQC - Matriz comparativa de admisión económica

## Dictamen

Ninguna de las tres arquitecturas supera las cinco puertas comerciales simultáneas. El resultado no demuestra imposibilidad universal: identifica qué evidencia falta para promover una ruta concreta. La ingeniería de laboratorio y la ausencia de capital personal tienen requisitos distintos.

Decisiones: **Morpho Ethereum: CONTINUAR sólo una verificación de financiación y compatibilidad acotada, cuando haya insumos nuevos accesibles; Aave/SVR: PAUSAR la promoción del ejecutor histórico; Robinhood: CONGELAR conforme a su cierre existente.** Si la siguiente prueba requiere contacto, cuenta, dinero o un endpoint denegado, se pausa ese hilo. CONTINUAR nunca autoriza trading ni gasto.

## G1-G5 por arquitectura

PROBADO se reserva a la condición completa dentro del alcance declarado. SIMULADO califica un resultado de laboratorio, no satisface por sí solo la puerta comercial. PENDIENTE conserva lo desconocido. REFUTADO sólo se usa para una afirmación y condiciones concretas.

| Arquitectura | G1 Ejecución auténtica | G2 Financiación sin recurso | G3 Margen neto propio | G4 Tiempo y admisión | G5 Mercado capturable |
| --- | --- | --- | --- | --- | --- |
| Aave/SVR Ethereum | SIMULADO en un caso; REFUTADO promover sin cambios el ejecutor ligado a bloques antiguos | PENDIENTE: ETH inicial era sintético; no hay pagador aplicable acreditado | SIMULADO: 2,273.989378 USDC después de flash/swap, antes de nativo/puja/otros | PENDIENTE: documentación de señales sí; recepción NQC y cutoff no probados | PENDIENTE: sin cohorte financiada, intentos y victorias |
| Morpho Robinhood 4663 | SIMULADO con estado histórico y Nitro; admisión ERC-4337 integral pendiente | PENDIENTE: depósitos de prueba, facturación comercial y sin tercero comprometido | SIMULADO: 32.060665 USDG antes de costes completos y conversión | PENDIENTE: posición sana al bloque padre; falta observar transición con anticipación | PENDIENTE: un caso histórico, no campaña de captura |
| Morpho Ethereum / Titan / Quasar | PENDIENTE: rutas locales sí; preestado completo y paridad NQC auténtica no | PENDIENTE: mecanismos públicos, ninguna cobertura NQC integral sin recurso verificada | PENDIENTE: residual de tercero; REFUTADO residual positivo del caso B fijo a 3 gwei | PENDIENTE: ensayo con bloques distintos y sin aceptación/cierre competitivo | PENDIENTE: 143 eventos/141 tx no equivalen a oportunidades financiadas |

Fuentes GitHub por SHA: [Aave/SVR](https://github.com/josuechavando350-png/nexus-quant-capital/blob/6693542e675f930a7ef0a4fd60cb72e7a6608845/migration/engine-v2-20261015/source/ci/nqc-census/rmc-v2-shadow/SVR_EXECUTOR_AUCTION_CAPITAL_CONTRACT.md), [Robinhood](https://github.com/josuechavando350-png/nexus-quant-capital/blob/6693542e675f930a7ef0a4fd60cb72e7a6608845/migration/robinhood-real-state-replay-20261016/README.md), [Morpho](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/RESEARCH_STATUS.md). Las operaciones aritméticas nuevas y fuentes primarias están en los documentos asociados de este expediente.

## Primera barrera común y qué la cambiaría

La primera barrera común bajo capital personal cero es **G2: identificar fondos externos utilizables y quién absorbe los fallos**. Un script no crea un compromiso comercial. Un programa público puede ser evidencia suficiente si sus condiciones verificables incluyen esta ruta, sus costes, sus límites y la ausencia de recurso; no se exige que siempre adopte la forma de un contrato negociado. En las fuentes disponibles aquí esa evidencia integral no consta.

Cada puerta permanece independiente: un sponsor acreditado no demuestra G1, G3, G4 ni G5. Tampoco se exige ganar dinero antes de permitir investigar: un piloto podría producir esa evidencia, pero su investigación debe respetar la autorización actual de no enviar ni gastar.

## Siguiente evidencia más barata por puerta

| Puerta | Aave/SVR | Robinhood | Morpho Ethereum |
| --- | --- | --- | --- |
| G1 | Solicitar al director el identificador de una versión dinámica ya existente y su prueba; no volver a ejecutar el constructor antiguo | Paquete de dependencias y admisión integral offline con versiones exactas, sólo si existe el gate de reapertura | Witness/preestado y prefijo ya autorizados, más paridad de Astra; no inventar reservas ni reemplazar código DEX |
| G2 | Evidencia de pagador externo compatible con la forma de subasta SVR, no traslado automático de eth_sendBundle | Programa o contraparte aplicable a 4663/EntryPoint/ruta con reserva y fallos sin recurso | Condición de sponsoring, identidad de saldo builder, top-up y obligaciones documentadas para la ruta exacta |
| G3 | Ledger de nativo, puja y caja inicial aparte del excedente USDC | Perímetro sponsor/bundler y USDG a ETH/caja con cotización fechada y costes | Reconciliar todos los participantes y costes externos, conservando U/R/F/P/V/O desconocidos |
| G4 | Registro prospectivo de señal, adquisición, simulación y deadline con incertidumbre de relojes | Transición auténtica observada con bloque/hash/index, no reutilizar estado sano | Inputs al mismo hash/versión y prueba de recepción anterior al cierre; 95s vacíos no sirven como tasa |
| G5 | Universo elegible y resultados completos de intentos | Campaña limitada preinscrita y denominador de fallos | Cobertura validada, todos los recibos del universo fijado, conflicto entre rutas y resultados de inclusión |

Estas son evidencias requeridas, no capturas nuevas ejecutadas en esta misión. Donde no existen fuentes gratuitas accesibles, el estado es PENDIENTE/BLOQUEADO.

## Aave/SVR: margen aparente y límites de la forma de subasta

La guía oficial [Ethereum SVR](https://docs.chain.link/data-feeds/svr-feeds/searcher-onboarding-ethereum) documenta un evento de oracle seguido de una transacción de liquidación, puja competitiva y recepción por MEV-Share. Eso delimita un camino posible; no demuestra recepción previa de NQC ni inclusión. La guía no cuantifica una puja mínima que permita declarar rentable nuestro caso. El endpoint [MEV-Share](https://docs.flashbots.net/flashbots-auction/advanced/rpc-endpoint) limita el bundle a una transacción de backrun. No se asume que una top-up separada aceptada por otro API pueda añadirse sin validar esta restricción. Un prefunding externo anterior seguiría necesitando pagador y cobertura propios.

Para el caso de laboratorio, sea p el precio fechado de 1 ETH expresado en USDC (USDC por ETH), y g el precio efectivo en wei/gas. Con la medición reportada de 3,914,680 gas, el coste nativo convertido es 3,914,680*g*p/10^18 USDC, más redondeo conservador cuando se trabaje en micro-USDC. El techo necesario de todos los otros costes es estrictamente menor que 2,273.989378 menos ese importe. No se inserta una cotización actual o histórica de otro caso.

El gas limit reportado, 5,089,056, determina una necesidad de saldo previa distinta del gasto final: gasLimit*maxFeePerGas + value para la ruta EOA correspondiente. A modo de aritmética hipotética, a un fee cap de 3 gwei y value cero serían 0.015267168 ETH de disponibilidad, mientras 3,914,680 gas a precio efectivo de 3 gwei costarían 0.01174404 ETH. Son cantidades necesarias bajo esos supuestos, no precios de subasta ni costes de producción. Falta conversión, otros costes y financiación. La salida a USDC posterior no financia por sí misma la validación de saldo anterior.

## Robinhood: un gate único de reapertura

Se conserva [REOPENING.md](https://github.com/josuechavando350-png/nexus-quant-capital/blob/6693542e675f930a7ef0a4fd60cb72e7a6608845/migration/robinhood-viability-decision-20261016T1713/REOPENING.md). Reabrir la investigación acotada al recibir **evidencia nueva revisable de una vía financiable aplicable a la ruta y del entorno necesario para la admisión offline**. Para afirmar financiación disponible se requieren términos aceptados o un programa verificable aplicable, fondos comprobados y cobertura sin recurso al fundador. Son umbrales distintos: no se exige financiación ya disponible para investigar una vía financiable, ni se convierte esa investigación en financiación comprometida. Presentar sólo una librería instalada o publicidad de gasless no satisface el conjunto. La investigación continúa sin contactos, firmas, envíos ni gastos.

La validación debe distinguir un revert de la UserOperation dentro de handleOps exitoso del revert de toda la transacción handleOps: los pagadores y cobros recuperables pueden ser distintos. La conciliación separa débito del depósito, transferencia al beneficiario y comisión nativa. Un coste DA desconocido permanece desconocido; una medición específica igual a cero no se generaliza. 32.060665 USDG sigue siendo cantidad de token antes de gastos, no USD ni ingreso realizado.

## Morpho: el callback resuelve sólo una parte

El callback local reduce una exigencia de liquidez interna en la fixture. No acredita fondos para la primera transacción, un precio DEX real, el margen del builder ni derecho de inclusión. La comparación local de 516,339 frente a 400,205 gas bruto omite costes relevantes y corresponde a laboratorio; no selecciona ganador comercial. La deprecación de Bundler3 y las diferencias de ruta se conservan como límites del expediente de Astra.

Reducir el pago observado a coinbase puede elevar el residual algebraico, pero cambia el incentivo de inclusión. No se usa ese cambio como demostración comercial. Antes de repartir excedente hay que identificar beneficiarios, dinero ajeno preexistente, obligaciones y reversión posible de cada flujo.

## Ranking de decisiones gratuitas útiles

1. **Compatibilidad financiera concreta de Morpho:** contrastar la ruta existente de Astra con las condiciones documentadas Titan/Quasar y exigir ledger de todas las cuentas. Una incompatibilidad de receptor, anticipo o recuperación puede refutar esa variante sin enviar nada. Un PASS local sólo despeja compatibilidad, no compromiso.
2. **Auditoría temporal del conjunto de prueba existente:** fijar hashes y hora de observación, impedir reconstrucción con conocimiento futuro. El expediente ya produce contraejemplos y un protocolo; no se repite un recolector sin nueva pregunta.
3. **Aplicar filtros al censo guardado:** cuantificar cambios de denominador y faltantes sin nuevas llamadas. Ejecutado en esta misión; cualquier proyección que ignorara los filtros debe retirarse.

Los puntos 2 y 3 están agotados para los insumos presentes. La próxima asignación a Astra debe atacar el punto 1 o aportar una evidencia que cambie G1/G4. Si necesita acceso bloqueado o una relación comercial nueva, corresponde PAUSAR y esperar evidencia, no multiplicar simulaciones equivalentes.

## Evaluación

- Investigación: buena, por delimitar patrocinio, pasivos y denominadores.
- Resultado comercial actual: malo; ninguna ruta supera admisión completa.
- Motivación para la siguiente prueba acotada: 7/10.
- Confianza comercial en ingresos repetibles con $0: 2/10, juicio cualitativo; no probabilidad de éxito.
- P&L propio realizado certificado: US$0. Capacidad mensual: NO ESTIMABLE.
