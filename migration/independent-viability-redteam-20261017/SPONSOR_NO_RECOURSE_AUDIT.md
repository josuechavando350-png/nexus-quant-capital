# NQC — Patrocinio y capital cero sin recurso al fundador

Fecha de investigación: 17 de octubre de 2026. Capturas documentales: 15:43:04–16:00:59 UTC. Misión: Directiva 002, investigaciones A y B; investigación documental independiente, sin contactar proveedores ni ejecutar admisión o envíos.

## 1. Dictamen y alcance

**Hay mecanismos públicos de financiación de gas. Ninguna de las tres rutas tiene demostrado, en el expediente examinado, un compromiso utilizable que cubra arranque, ejecución y fallos sin aportación, deuda ni garantía del fundador.** Esto impide admitir comercialmente una operación bajo la condición actual. No demuestra imposibilidad universal.

Titan y Quasar presentan una hipótesis de financiación externa condicionada al valor que recibe su builder. La documentación de Robinhood ofrece infraestructura AA; Robinhood no queda identificado por ello como quien aporta los fondos. Alchemy y ZeroDev ofrecen modalidades cuyo pagador económico es el cliente o un tercero que financie al cliente. Que el usuario de una aplicación no tenga ETH no determina quién debe pagar después.

Esta investigación verificó publicaciones y código fuente, no fondos reservados, identidades on-chain ni aceptación de una ruta NQC. Los hechos de laboratorio leídos en GitHub conservan estado REPORTADO; no se volvieron a ejecutar. Los saldos de las matrices son hipótesis contables y no saldos observados.

Fuentes con identificación, URL, SHA cuando existe, hora real de captura, extracto breve, inferencias y límites: evidence/sponsor_sources.json. Los identificadores S-SP-* remiten a ese registro. Los documentos del repositorio se leyeron en los SHA fijados por la Directiva; la comprobación de los cinco HEAD pertenece al expediente BASELINE_AND_DRIFT.md.

### Cuatro estados, independientes

| Ruta concreta | MECANISMO_PUBLICADO | COMPATIBILIDAD_LOCAL | COMPROMISO_REAL | COBERTURA_INTEGRAL_SIN_RECURSO |
|---|---|---|---|---|
| Morpho Ethereum + Titan | VERIFICADO: S-SP-01/02 | REPORTADO_PARCIAL: modelos y pagos sintéticos; sin paridad histórica completa ni política real ejecutada, S-SP-19 | NO_DEMOSTRADO | NO_DEMOSTRADO |
| Morpho Ethereum + Quasar | VERIFICADO: S-SP-04 | REPORTADO_PARCIAL: mismo límite; no se hereda aceptación de Titan, S-SP-19 | NO_DEMOSTRADO | NO_DEMOSTRADO |
| Morpho Robinhood 4663 + EntryPoint v0.7 + financiador externo | VERIFICADO: soporte general S-SP-07/08/09 | REPORTADO_PARCIAL: replay con provisión de fondos ficticia; admisión completa pendiente, S-SP-20/21 | NO_DEMOSTRADO | NO_DEMOSTRADO |

COMPATIBILIDAD_LOCAL tampoco equivale a financiación: exige demostrar la ruta completa y controles de admisión con versiones fijadas. Una simulación contractual parcial puede coexistir con rechazo del bundler, política inadmisible o caja insuficiente.

## 2. Hechos documentales que cambian la evaluación

**D1 — Titan.** Ante LackOfFundForGasLimit publica anticipo para gas y value, condicionado a recuperar financiación mediante incremento del saldo del builder. Su explicación de 2023 intercala una transferencia previa y después considera el bundle como candidato. No acredita que NQC sea aceptado. S-SP-01/02.

**D2 — Quasar.** Publica patrocinio de gas ante ese error e incremento de saldo del builder. No extiende expresamente esa frase a value. El payload distingue transacciones que pueden revertir y transacciones descartables; Titan documenta una semántica distinta para su lista de reversiones. S-SP-04/01. La amplitud de una API no prueba que NQC haya configurado ni satisfecho sus condiciones.

**D3 — Dirección e inclusión.** Titan identifica 0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97 y Quasar 0x396343362be2A4dA1cE0C1C210945346fb82Aa49. Son declaraciones actuales; falta probar control y atribución para un bloque y una ruta. Titan declara haber eliminado colas de prioridad; Quasar publica preferencias por autenticación estable, historial y valor. Ninguna fuente proporciona una hora límite de admisión NQC ni reserva de espacio. S-SP-03/05/06.

**D4 — Robinhood.** La red documenta chain ID 4663, gas nativo ETH y EntryPoint v0.7 en 0x0000000071727De22E5E9d8BAf0edAc6f37da032, junto con otras versiones. Un ejemplo vigente de SDK no permite cambiar silenciosamente la versión del expediente. S-SP-07/08. La especificación actual ERC-4337 es contexto; para conducta v0.7 se leyó código fijado al commit 7af70c8993a6f42973f520ae0752386a5032abe7. S-SP-09/10/11.

**D5 — Pagadores AA.** En v0.7 el paymaster necesita depósito suficiente durante validación; el depósito y el stake son conceptos separados. El beneficiario de handleOps recibe los cargos y puede ser distinto del emisor de la transacción. Un fallo de la llamada de aplicación puede consumir fondos del paymaster; una reversión de toda la transacción tiene otro resultado. La matriz distingue ambos. No se ha medido el requisito de stake de la admisión exacta NQC. S-SP-09/10/11.

**D6 — Alchemy.** La FAQ pública muestra anticipo facturable o créditos comprados; en PAYG publica comisión del 8%, base mainnet de $0/mes y límites personalizados por acuerdo. Un fallo en el cobro ERC20 posterior no libera al cliente del gas. Advierte que el procesamiento concurrente puede exceder brevemente límites configurados. No es una oferta sin recurso a NQC. S-SP-12. La API de políticas contempla límites de importe, conteos, emisor y vigencia; una política recién creada comienza inactiva. S-SP-13.

**D7 — ZeroDev.** Publica cobro mensual a tarjeta o compra de créditos, y requiere política de patrocinio. Su ejemplo opcional de fallback usa fondos nativos del usuario cuando no hay patrocinio: esa configuración es incompatible con una garantía de capital personal cero. No se ha activado. S-SP-14.

**D8 — Estado del expediente.** Robinhood reporta 32.060665 USDG de simulación y provisiones de 0.1 ETH al depósito y 0.01 ETH al bundler. Son fixtures, no requisitos mínimos medidos ni fondos disponibles. La revisión de viabilidad declara incompleta la admisión y ausente financiación comprometida. S-SP-20/21. Morpho Ethereum mantiene no demostrados aceptación y financiación de Titan/Quasar. S-SP-19.

## 3. Titan: quince preguntas verificables

| # | Pregunta | Respuesta con evidencia y frontera |
|---|---|---|
| 1 | ¿Quién adelanta realmente los fondos? | La publicación identifica al builder Titan, no al relay. Dirección financiadora efectiva y reserva para NQC: UNKNOWN. D1. |
| 2 | ¿Qué activa el anticipo? | Error de fondos insuficientes y condición económica D1. Falta una evaluación reproducible de la implementación y versión que admitiría NQC. |
| 3 | ¿Qué conceptos cubre? | D1 incluye gas/value de la transacción. Creación de contrato, despliegue previo e infraestructura completa: NO_DEMOSTRADO. |
| 4 | ¿Quién debe tener ETH primero? | El financiador de la transferencia y su gas. La liquidez necesaria precede al rendimiento de la liquidación; cantidad y dueño reales: UNKNOWN. |
| 5 | ¿Depósito, saldo mínimo, tarjeta o crédito? | No aparecen compromisos comerciales suficientes en las páginas revisadas. Ausencia en una página no acredita inexistencia de requisitos. |
| 6 | ¿Existe aceptación de NQC? | Ninguna aportada o localizada en el expediente revisado. Una capacidad pública general no identifica ruta, presupuesto y obligaciones aceptadas. |
| 7 | ¿Recibe el builder el valor recuperable? | Pendiente de ledger de direcciones y trazas. Un pago histórico a coinbase de terceros no demuestra recuperación por este financiador. |
| 8 | ¿Cuál es el receptor? | Dirección declarada en D3. Falta casar financiador, receptor, bloque, beneficiario económico y devolución. No sustituir todo por block.coinbase. |
| 9 | ¿Cómo se calcula el margen y pago al proponente? | Publicación condiciona valor positivo; no revela umbral completo NQC. Usar la identidad contable de §7 con P y O en UNKNOWN. |
| 10 | ¿Qué pasa con top-up separado y ejecución omitida? | S2 es prueba hipotética necesaria. D1 no es una garantía contractual de recuperación ante todas las formas de separación o reorg. |
| 11 | ¿Quién paga si la operación incluida revierte? | Ver S3: pagador de la transacción pierde gas; una transferencia anterior puede persistir. La asunción económica final del sponsor sigue pendiente. |
| 12 | ¿Hay factura o deuda del fundador? | UNKNOWN. Exigir definición de recobro y pérdidas, incluso si no existe cuenta de facturación visible. No presumir deuda tampoco. |
| 13 | ¿Límites, reputación, permisos o geografía? | D3 descarta atribuir a Titan la cola actual de Quasar. Techos de patrocinio, elegibilidad regional y restricciones aplicables a NQC: UNKNOWN. |
| 14 | ¿Qué puede verificarse sin enviar? | Semántica publicada y escenarios contables; futuras pruebas locales aisladas de flags y dependencias. Aceptación real e inclusión: pendientes. |
| 15 | ¿Qué transforma documentación en compromiso utilizable? | Programa verificable o términos aceptados aplicables a la ruta, reserva/control demostrados, presupuesto, condiciones de parada y cobertura de S1–S5 sin recurso. |

Resultado de la ficha: capacidad documentada; autorización financiera específica y protección del fundador no demostradas. La primera prueba útil es delimitar qué flujo produce ingreso controlado por Titan después de todos los costes, junto con evidencia pública o contractual aplicable a su asunción de pérdidas. No es necesario que el instrumento tenga forma de contrato bilateral si un programa verificable cubre lo mismo.

## 4. Quasar: quince preguntas verificables

| # | Pregunta | Respuesta con evidencia y frontera |
|---|---|---|
| 1 | ¿Quién financia, y no sólo retransmite? | Quasar identifica a su builder como financiador del mecanismo D2. Tesorería, saldo comprometido y entidad acreedora NQC: UNKNOWN. |
| 2 | ¿Qué activa el anticipo? | Condiciones D2. No se ha probado cuál es el cálculo interno ni la versión efectivamente operativa para NQC. |
| 3 | ¿Gas, value, deploy y arranque? | Sólo gas expresamente cubierto en la cláusula revisada. Las otras categorías son UNKNOWN; no heredar la frase de Titan. |
| 4 | ¿Quién tiene el primer ETH? | Quien financia el anticipo y su transacción. Un flash loan de la ruta no entrega antes el ETH al pagador. |
| 5 | ¿Qué depósito, saldo o crédito exige? | No especificado suficientemente en las fuentes capturadas. No se comprobó inexistencia de mínimos o requisitos comerciales. |
| 6 | ¿Admitió la operación NQC? | NO_DEMOSTRADO, conforme a S-SP-19. No hay respuesta, presupuesto reservado ni compromiso verificable de esta operación. |
| 7 | ¿Controla el ingreso que permite patrocinar? | UNKNOWN para el caso histórico y para NQC. La condición de beneficio declarada necesita trazabilidad de pagos y derechos. |
| 8 | ¿Qué receptor corresponde? | Declaración de D3, no prueba de control histórico. Deben coincidir identidad económica y movimientos de fondos del ensayo exacto. |
| 9 | ¿Cómo compone ingreso, reembolso y puja? | Debe reconstruirse §7. Los campos de reembolso no convierten una puja en ganancia del fundador ni revelan P completo. |
| 10 | ¿Cómo quedan los anticipos separados? | S2 y S5 requieren dependencia del top-up verificada. La declaración de no desagregar bundles de S-SP-05 no liquida contratos externos ni reorgs. |
| 11 | ¿Quién absorbe una reversión incluida? | Aplicar S3 a la configuración exacta. Allow-revert y allow-drop tienen significados distintos; no suponer que activarlos conserva financiación íntegra. |
| 12 | ¿Puede quedar deuda personal? | UNKNOWN; sólo condiciones aplicables pueden excluir factura, reposición, clawback o responsabilidad contingente. |
| 13 | ¿Existen criterios de acceso competitivo? | D3 documenta prioridad por autenticación y trayectoria; no es garantía de inclusión. Cupo de financiación, geografía y whitelist concreta: UNKNOWN. |
| 14 | ¿Qué pruebas caben sin enviar? | Lectura de especificación, trazas públicas preexistentes si fueran suficientes y modelos locales. No probar reputación ni patrocinio por un ejemplo de payload. |
| 15 | ¿Qué prueba eleva el estado? | Compromiso aplicable y financiado de §9, más compatibilidad exacta incluyendo cobertura de value/despliegue cuando la ruta los necesite. |

Resultado de la ficha: patrocinio de gas publicado; cobertura exacta, responsabilidad y competitividad NQC no demostradas. La ausencia de mención de value no prueba que Quasar nunca pudiera financiarlo; impide contabilizarlo como disponible.

## 5. Robinhood 4663 / EntryPoint / paymaster: quince preguntas

| # | Pregunta | Respuesta con evidencia y frontera |
|---|---|---|
| 1 | ¿Quién pone fondos? | El dueño económico del depósito del paymaster y la caja del bundler. Robinhood es la red; proveedor y sponsor deben identificarse por separado. |
| 2 | ¿Qué permite la financiación? | Validación de la operación, política y prefund. D4–D7 documentan componentes, no admisión integrada de la liquidación NQC. |
| 3 | ¿Incluye gas, value y despliegues? | Pago AA cubre cargos bajo su política; no aporta automáticamente valor transferido ni cualquier contrato previo. Creación y preparación deben presupuestarse. |
| 4 | ¿Quién tiene ETH antes de handleOps? | El emisor de la transacción exterior y quien financió el depósito necesario. No se pueden repagar retroactivamente ambas necesidades con USDG futuro. |
| 5 | ¿Depósito, stake, saldo, tarjeta o crédito? | Depósito y caja son necesarios; stake depende de la admisión. Modalidades comerciales D6/D7 requieren cliente pagador o fondos precomprados. |
| 6 | ¿Existe compromiso a favor de NQC? | S-SP-21 no lo acredita; esta auditoría tampoco. Integración de red o ejemplo SDK no autoriza gas ilimitado ni cubre pérdidas. |
| 7 | ¿El financiador accede a los ingresos? | UNKNOWN: un paymaster no recibe automáticamente el USDG residual. Deben fijarse derecho, cobro, conversión y tratamiento de fallos. |
| 8 | ¿A qué dirección se paga? | D4 fija EntryPoint. Falta identificar paymaster, propietario del depósito, emisor y beneficiary reales, además del receptor de ERC20 si existe. |
| 9 | ¿Cuál es el margen de cada actor? | Separar cargo C al depósito de gas G exterior; B gana C−G antes de sus costes. Consolidar según control común, nunca sumar C+G indiscriminadamente. |
| 10 | ¿Y si se fondea depósito/caja pero se omite la UserOp? | S2: permanecen activos prefinanciados y costes de fondeo. Retiro/control/plazos cuestan y no son ingresos de NQC. |
| 11 | ¿Quién paga una reversión? | S3 diferencia fallo interno y reversión total. Un minProfit que revierte la aplicación no revierte necesariamente el cargo de gas AA. |
| 12 | ¿Hay facturación posterior? | D6/D7 documentan modalidades facturables. Un tercero podría asumirlas; no hay evidencia de que lo haga sin obligación del fundador. |
| 13 | ¿Qué techos y permisos aplican? | Políticas y límites D6/D7. Los valores exactos de NQC, alcance geográfico y cupo simultáneo son UNKNOWN; no usar fixtures como límites. |
| 14 | ¿Cómo probar sin operación real? | Futuro ensayo offline con versión, parser, firma, depósito agregado, stake, reputación, caducidad y mempool; sin emisores de red habilitados. |
| 15 | ¿Qué evidencia permitiría pasar? | Financiador verificable con reserva previa, política que incluya esta liquidación y acuerdo/programa que cubra gastos y todos los fallos sin recurso. S-SP-22. |

### Tres modalidades que no deben confundirse

| Modalidad | Consecuencia |
|---|---|
| Chavando compra créditos o paga tarjeta/factura | Incompatible con su condición actual: aportación o deuda personal, aunque la wallet operativa comience en cero. |
| Tercero paga el servicio y asume costes sin recobro personal | Hipótesis potencialmente compatible; compromiso, reserva y alcance NO_DEMOSTRADOS. |
| Paymaster cobra ERC20 dentro o después de la operación | Cambia el activo y el momento del cobro; no demuestra quién absorbe gas cuando falla ni quién fondea el arranque. |

## 6. Alternativa concreta Flashbots: qué aporta y qué no

El ejemplo oficial searcher-sponsored-tx describe una cuenta sponsor con ETH que financia una cuenta ejecutora. Sirve como referencia de separación de pagadores. No identifica a Flashbots como donante ni concede capital a NQC. No se ejecutó, adaptó ni tomó como contrato utilizable. S-SP-17.

La documentación de EIP-1559 de Flashbots también advierte que transacciones de un bloque reorganizado pueden reaparecer en mempool. Esto justifica S5 como riesgo a modelar; no demuestra que Titan o Quasar hayan desagregado un bundle NQC. S-SP-18. No se incluyeron otras alternativas especulativas.

## 7. Ledger del builder y atribución correcta del valor

Se conserva la definición requerida por la Directiva:

    M_builder = R + U + V − A − F − P − O

| Símbolo | Definición exacta en el horizonte de evaluación |
|---|---|
| A | Anticipo bruto efectivamente entregado por el sponsor. |
| U | Parte no usada que volvió efectivamente al sponsor. Un saldo aún en el ejecutor no es U. |
| R | Reembolso efectivamente cobrado por el sponsor con cargo a la ejecución. |
| V | Otros ingresos externos verificados del builder, no registrados ya en R o U. |
| F | Coste de gas de financiar que sale de caja del builder fuera de A. |
| P | Pago separado que sale del builder al proponente y no está ya incluido en otro término. |
| O | Otros costes atribuibles, incluyendo operación, reintentos, conversión o capital según el horizonte definido. |

Esta identidad es caja por activo, no una promesa de que el builder acepte margen cero. Su umbral comercial μ y coste de oportunidad quedan UNKNOWN. Para que acepte se necesita M_builder ≥ μ y suficiente liquidez inicial, además de las condiciones técnicas y competitivas.

Cada flujo debe tener ID único, activo, pagador, receptor, instante y fuente. Si una transferencia a una dirección del builder repaga A, clasificarla R o dividirla en componentes justificables; no volver a sumar íntegramente esa transferencia como V. Si A financia gas G del ejecutor, restar A y después G del builder cuenta dos veces la misma salida salvo otra financiación documentada. Si F ya incluye propina recibida por el propio builder, su retorno sólo entra en V cuando esté verificado. El resultado consolidado debe eliminar transferencias internas.

El pago a block.coinbase sólo acredita un destino de ejecución si se reconstruye la traza. Identificarlo como ingreso del builder requiere probar destinatario económico y derechos de cobro, y separar cualquier pago posterior al proponente. Una dirección publicada hoy tampoco identifica por sí sola un bloque de septiembre.

Para el propietario:

    M_owner = variación de activos netos realizables atribuible a NQC
              − costes aún no reflejados
              − obligaciones directas y contingentes aún no descontadas

Se excluyen capital inicial, anticipos y préstamos como ingresos. Se excluye inventario previo. No sumar ETH, USDG y USD: se necesita cantidad, activo, precio ejecutable fechado, profundidad, posibles desvíos de paridad, costes y plazo de conversión. D8 no contiene una conversión que certifique caja disponible para gas.

## 8. La atomicidad no es una póliza de pérdidas

Una transacción revertida deshace sus efectos de aplicación, pero puede consumir gas. Un conjunto de transacciones con política de bundle no equivale a una única transacción EVM ni a términos de indemnización. Las garantías documentales de agrupación se evalúan junto con flags, transacciones externas, reorgs y punto de finalización.

Para AA, la unidad que contiene varios UserOperations puede seguir viva tras fallar una llamada de aplicación. La función que impone un beneficio mínimo sólo tiene alcance sobre sus efectos alcanzables; no borra costes previos, préstamos comerciales ni facturas. S-SP-10 sustenta la distinción técnica; FAILURE_LIABILITY_MATRIX.md contiene los modelos hipotéticos.

## 9. Evidencia mínima, sin outreach

La puerta de financiación necesita un conjunto concreto y coherente de pruebas, mediante un programa público verificable o términos aceptados. No exige por definición un contrato bilateral, pero sí aplicabilidad y obligaciones claras:

1. Identidad del financiador, quién controla fondos y quién es acreedor; ninguna confusión entre red, relay, builder y paymaster.
2. Ruta exacta admitida: chain, versión, contratos, activos, first run, creación y despliegues; límites de calldata, value, gas y concurrencia.
3. Liquidez previa verificable, reserva atribuible y vigencia, sin contar el mismo ETH como depósito, stake y caja disponible.
4. Cobertura de S1–S5, costes de rechazo y fuera de cadena, reorgs, retiradas, fallos de conversión, discontinuación y devolución del anticipo.
5. Ausencia aplicable de factura, deuda, garantía, reposición obligatoria o recobro contra el fundador; reglas explícitas de parada al agotar reserva.
6. Reparto y liquidación de beneficio, prioridad del repago, destino y activo de cada flujo, momento en que el rendimiento se puede reinvertir.
7. Compatibilidad offline completa bajo términos fijados, seguida sólo en una fase posteriormente autorizada por evidencia efectiva de aceptación y fondos utilizables.

Esta lista es preparación interna; no se solicitó ni recibió ningún compromiso. Una página que no publique condiciones suficientes se clasifica NO_DEMOSTRADO, nunca IMPOSIBLE. La negación fuerte sólo procede contra una proposición limitada: por ejemplo, “el fundador paga con su tarjeta y aun así no tiene obligación económica” es incompatible por definición.

## 10. Puerta conjunta y próxima prueba decisiva

    elegible = net_owner > 0
               AND margin_sponsor >= μ
               AND founder_obligation = 0
               AND time_eligible
               AND execution_valid

Usar lógica de tres valores. Una condición falsa refuta el candidato bajo esos supuestos; todas verdaderas permiten evaluarlo; cualquier UNKNOWN restante impide admitirlo. “No vimos deuda” no implementa founder_obligation = 0.

Prioridad de investigación: cerrar identidad, reserva y responsabilidad del financiador en una ruta económicamente delimitada. En paralelo, la ingeniería debe resolver admisión y estado auténtico; no aumentar contadores de simulaciones para sustituir financiación. La financiación sola tampoco demuestra frecuencia, anterioridad temporal o inclusión ganable.

### Qué cambiaría el dictamen

Cambiaría el estado de compromiso ante una prueba verificable aplicable a NQC de financiación y obligaciones, con reserva utilizable. Cambiaría cobertura sólo cuando incluya fallos y arranque sin recurso. Un programa que cubra únicamente gas de la ejecución exitosa mejora una parte del expediente y deja las otras pendientes. Un rechazo de una ruta particular tampoco refuta todas las rutas de Morpho.

**Confianza:** alta en los hechos documentales delimitados; insuficiente para afirmar disponibilidad de patrocinio NQC. **Resultado económico:** NO_DEMOSTRADO. **Ganancias realizadas certificadas por esta investigación:** ninguna.
