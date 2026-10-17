# NQC — Relevo de auditoría económica independiente / Directiva 002

**17 de octubre de 2026 · Investigación: PARCIAL, con resultados locales REPRODUCIBLES.**
**P&L propio realizado certificado: US$0. Expectativa mensual: NO ESTIMABLE.**
El expediente no acredita ninguna arquitectura comercialmente admisible. No demuestra imposibilidad universal.

## Primera página — decisión para el director

**SHA consultados y coincidentes al inicio:**

| Repositorio / rama | SHA |
| --- | --- |
| NQC / main | `16e352225ba8a6a931834c4edf3d86d9a2924b7d` |
| NQC / research/morpho-sponsored-gas-20261016 | `0f26557c1f83e12efcf364ece6cebd8505d2e2c2` |
| NQC / research/cross-repo-evidence-audit-20261017 | `ddade5d099e19449e0c4e55079a2b0c9d9ee1141` |
| NQC / nqc/viability-decision-20261016T1713 | `6693542e675f930a7ef0a4fd60cb72e7a6608845` |
| nexus-engine / main, sólo lectura | `380eff1fc14336bd24d93c8ef807525a7078950d` |

**Tres hallazgos nuevos y su impacto:**

1. Titan documenta adelanto de gas y `value`; Quasar menciona gas. No se acredita cobertura integral sin recurso aplicable a NQC. Alchemy y ZeroDev describen facturación o créditos, que no prueban esa cobertura. **G2 sigue PENDIENTE.** [SPONSOR_NO_RECOURSE_AUDIT.md; S-SP-01, S-SP-04, S-SP-12, S-SP-14]
2. El líder del censo concentra **35 eventos, todos con bad debt y todos el 26-sep**. Quitar eventos con bad debt deja **100 eventos/99 tx**; quitar sus transacciones completas deja **99/98**. Ningún filtro certifica rentabilidad. **G5 sigue PENDIENTE.** [CENSUS_BIAS_REPORT.md; resultados `concentration_findings` y `filter_sensitivity`]
3. El seguimiento de 95 segundos fue fijado **0.585742 segundos después de terminar la ventana**. Los datos completos llegaron 23.670478 segundos después del inicio y mezclan tres alturas. Hay selección anterior a la consulta, pero no prerregistro de una ventana futura. **G1/G4 no quedan certificados.** [TEMPORAL_COMPETITION_AUDIT.md; S-TM-038 a 050]

**Tres afirmaciones no demostradas:** patrocinador integral sin recurso; margen propio positivo con todos los pasivos; recepción competitiva y población de oportunidades capturables.

**Contradicciones:** los importes y las fronteras contables reconstruidos aquí coinciden con lo reportado por Astra en los SHA fijados; esto no recertifica sus demás resultados. La lectura como prerregistro futuro queda refutada por las horas guardadas. Los contadores 159 frente a 168 pertenecen a etapas distintas. Corregimos antes de publicar una transcripción propia de wei Robinhood con factor 1000; no fue un error de Astra.

**Pruebas ejecutadas:** `python3 -m unittest -v test_accounting_audit`: **25 PASS**; `python3 accounting_audit.py`: **10 guardrails PASS**; `python3 census_audit.py`: **12 grupos PASS / 46 blobs verificados**. Los diez controles están cubiertos por la suite; no se suman como pruebas independientes adicionales. Aislamiento original: **BLOCKED_INPUTS**, no PASS.

**Decisiones:** Morpho Ethereum **CONTINUAR sólo con evidencia nueva y revisión gratuita acotada**; Aave/SVR **PAUSAR** promoción del ejecutor histórico; Robinhood **CONGELAR** hasta su gate de reapertura. Ninguna decisión autoriza operaciones.

**Única solicitud al director:** remitir un expediente concreto, ya disponible o aportado por el propietario, que identifique la vía financiable de Morpho y permita contrastar su compatibilidad y cobertura sin recurso. Si no existe evidencia que pueda cambiar G2 sin contacto o gasto, mantener ese hilo en PAUSA.

**Tres tareas que no deben repetirse:** forks/contratos de Astra; baterías Robinhood sin evidencia nueva de reapertura; ampliar censos o benchmarks para proyectar ingresos.

---

## 1. Qué se verificó y qué conserva límites

**Hecho verificado por esta auditoría:** se leyeron las cinco referencias, AGENTS.md y fuentes fijadas; se comprobaron identidades de bytes de los insumos; se reconstruyeron cantidades con enteros/Fraction; se rederivaron selección, denominadores y tiempos. Verificar un documento acredita lo que dice, no prueba su ejecución histórica.

**Hecho reportado en los expedientes:** replays Aave/SVR y Robinhood, pruebas Solidity de Astra, avance callback/Bundler3 y sus mediciones. No se reejecutaron sus forks ni se suman sus suites a las nuestras.

**Hipótesis:** modelos de balances S1–S5, precios alternativos de gas y márgenes por victoria. Sus ceros son condiciones explícitas de cada escenario. No rellenan los datos económicos reales ausentes.

**Pendiente:** titularidad de cuentas históricas, obligaciones externas, fondos disponibles, términos de cobertura, estado previo auténtico completo, acceso competitivo e inclusión elegible.

Se leyó la Directiva 002 adjunta. **NQC_RELEVO_MAESTRO_2026-10-17.pdf no estuvo adjunto y no fue leído.** Tampoco se recibió un informe posterior de Astra por medio del usuario. Los análisis paralelos internos pertenecen a esta auditoría; no son comunicación con el director ni con el chat externo de Astra. [BASELINE_AND_DRIFT.md]

## 2. Primera barrera: quién financia todo el arranque y cada fallo

La pregunta sigue sin respuesta acreditada para NQC. Un flash loan puede aportar principal a una ejecución, pero no demuestra que haya un pagador disponible para la validación inicial de gas, la operación de fondeo, un despliegue necesario, depósito/stake cuando corresponda y las pérdidas de los caminos de fallo.

Titan y Quasar publican mecanismos útiles que justifican revisar compatibilidad técnica. Sus páginas no bastan para afirmar que NQC tiene financiación adjudicada y pérdidas cubiertas. Tampoco debe imponerse necesariamente un contrato bilateral: un programa público verificable y aplicable puede acreditar cobertura si demuestra condiciones, fondos y ausencia de recurso. [S-SP-01 a 06]

Alchemy describe costes de gas facturados o cubiertos por créditos; la página consultada de ZeroDev describe tarjeta mensual o créditos prepagados. Que el usuario final no tenga ETH no implica que el fundador no deba pagar a otro actor. Cualquier factura, garantía o reposición personal impide G2, aunque el flujo muestre beneficio bruto positivo. [S-SP-12, S-SP-14; T-02, T-09]

La matriz S1–S5 distingue rechazo sin inclusión; top-up incluido y operación omitida; ejecución revertida; éxito con slippage o excedente insuficiente; e inclusión parcial/reorg/fallo tardío. Son escenarios hipotéticos, no incidentes NQC observados. Un revert interno de UserOperation dentro de handleOps exitoso y un revert de toda la transacción handleOps pueden dejar pérdidas en pagadores distintos. [FAILURE_LIABILITY_MATRIX.md]

Para el modelo Ethereum donde el builder adelanta A y paga F, el ejecutor consume G, devuelve realmente U y reembolsa R, el margen del financiador es:

`R + U + V − A − F − P − O`.

V debe ser ingreso externo distinto de los otros flujos; P es pago a proponente y O otros costes. Un saldo no gastado no cuenta también como devolución efectuada. El beneficio del dueño requiere excluir principal, inventario inicial y donaciones, y descontar pasivos completos. La obligación personal debe ser cero por separado: beneficio neto positivo no elimina una deuda. [INDEPENDENT_ECONOMIC_LEDGER.md; FAILURE_LIABILITY_MATRIX.md]

## 3. Caso B: frontera exacta, atribución aún desconocida

La reconstrucción utiliza recibo, traza, bloque y eventos guardados, cotejados con sus fuentes Git; no es nueva consulta RPC ni replay EVM. Los **0.006392502690919791 WETH** anteriores quedan fuera del incremento reconstruido. La transferencia a coinbase identifica su receptor en los archivos guardados, no al beneficiario económico final.

| Partida o condición fija | Resultado |
| --- | ---: |
| Venta | 26.409680973611000000 ETH nativo recibido desde Fluid |
| Repago | 26.039738525656992415 WETH |
| Pago a coinbase | 0.368092735714237547 ETH |
| Gas observado en el recibo guardado | 745509 unidades |
| Precio efectivo observado | 266148625 wei/gas = 0.266148625 gwei |
| Residual después de costes conocidos | **1651296044494913 wei = 0.001651296044494913 ETH equivalente**, cota condicionada |
| Último precio entero con residual positivo | **2481140052 wei/gas = 2.481140052 gwei** |
| Residual en ese precio | **743570 wei** |
| Residual con un wei/gas adicional | **−1939 wei** |
| Residual a 3 gwei | **−386814760229962 wei = −0.000386814760229962 ETH equivalente** |
| Coste adicional máximo que deja un wei positivo al precio observado | **1651296044494912 wei** |

Fuente: `evidence/accounting_results.json`, `case_b_reconciliation` y sensibilidad; código independiente `accounting_audit.py`; entradas originales en `evidence/accounting_inputs.json`. La entrada nativa desde Liquidity coincide con el depósito en WETH registrado antes del repago. El residual combina el incremento WETH del ejecutor y el gas ETH del sender sin acreditar propiedad conjunta.

La frontera conserva venta, deuda, pago a coinbase y gas usado. No es una oferta de gas disponible ni una garantía de inclusión. Quitar la propina aumenta el residual algebraico, pero modifica los incentivos de quien ordena el bloque. El residual conocido es una cota condicional de un flujo de terceros; obligaciones externas y titularidad no acreditadas mantienen el neto real y la elegibilidad NQC en **UNKNOWN**.

### Robinhood: una conciliación, dos perímetros

| Perímetro | Coste o diferencia de la simulación reportada |
| --- | ---: |
| Cargo del paymaster a favor del bundler | 79616762214000 wei = 0.000079616762214 ETH |
| Comisión nativa pagada a la red | 57601054408000 wei = 0.000057601054408 ETH |
| Diferencia del bundler antes de otros costes | 22015707806000 wei = 0.000022015707806 ETH |

Para el paymaster externo, el débito es la primera cifra. Para paymaster y bundler consolidados, su transferencia interna se elimina y queda la comisión nativa, más otros costes que correspondan. Restar ambas cifras como dos costes externos del mismo perímetro duplicaría una parte del flujo. No se considera USDG igual a USD ni se convierte ETH sin cotización justificada. [T-06; S-R-06; `migration/robinhood-real-state-replay-20261016/README.md` en SHA `6693542e675f930a7ef0a4fd60cb72e7a6608845`]

**Corrección propia:** la primera transcripción de esas dos cifras a wei quedó 1000 veces por debajo del decimal original. La revisión manual la detectó; se corrigieron entradas y documentación, se preservó la salida anterior como SUPERSEDED y se añadió una prueba que extrae el decimal del README y calcula `Fraction(decimal) × 10**18`. La validación final contiene 25 pruebas. El caso B no estuvo afectado. [INDEPENDENT_ECONOMIC_LEDGER.md, sección 10; evidence/accounting_test_output.txt]

## 4. Censo y tiempo: qué cambió con el análisis propio

El censo guardado contiene 143 eventos y 141 transacciones en una ventana de 30 días. La coincidencia de páginas directas, inversas y subconjunto de siete días demuestra consistencia interna de esa API, no cobertura universal ni fuentes independientes. Un control eth_getLogs guardado devuelve vacío para un filtro que cubre la liquidación B del recibo positivo guardado. Es una omisión o conflicto entre observaciones, sin causa demostrada. No certifica cobertura global. [S-TM-006, 008 a 010, 034 a 037, 051]

| Conjunto o filtro | Eventos | Transacciones |
| --- | ---: | ---: |
| Censo original | 143 | 141 |
| Quitar sólo eventos con bad debt | 100 | 99 |
| Quitar transacciones con cualquier bad debt | 99 | 98 |
| Sólo deuda WETH | 7 | 7 |
| WETH sin bad debt reportado | 6 | 6 |
| Selección diagnóstica de recibos | 25 | 23 |

Una transacción mixta explica 99 frente a 98. El bad debt no determina por sí solo la pérdida del liquidador; su ausencia tampoco prueba beneficio. De las 23 transacciones seleccionadas, una tiene el recibo B reutilizado y 22 respuestas guardadas son nulas; 118 quedan fuera del diagnóstico. Los nulos no son reverts, pérdidas ni gas cero.

Los 35 eventos de la dirección líder tienen bad debt, colateral sNUSD y fecha 26-sep. Ese día reúne 36 de los 43 eventos con bad debt del mes. La concentración invalida interpretar el ranking bruto como velocidad, rentabilidad o competencia cotidiana sin análisis adicional. [CENSUS_BIAS_REPORT.md]

En la muestra temporal, mercado/posición/oráculo corresponden a **26210230 / 26210231 / 26210229**. El máximo de recepción de las dependencias completas, incluidos headers, es **05:38:26.670478 UTC**. Dentro de la ventana 05:38:03–05:39:38 quedan **71.329522 segundos**, antes de resolver coherencia, preparación y admisión. La selección del seguimiento se guarda a **05:39:38.585742**. No existió prerregistro anterior a esa ventana futura. [S-TM-038 a 050]

Llegar antes del bloque no demuestra haber llegado antes que el ganador ni antes del cierre del builder. Para esa comparación hacen falta contenido idéntico de señal/candidato, registros de recepción y admisión, fuentes de reloj con incertidumbre y cobertura de los canales relevantes. Las diferencias decimales entre timestamps se conservan como aritmética; no son precisión física de reloj ni latencia de red demostrada. El protocolo futuro acotado está documentado y **NO EJECUTADO**.

## 5. Decisiones y reconciliación con el expediente de Astra

| Arquitectura | G1 | G2 | G3 | G4 | G5 | Decisión |
| --- | --- | --- | --- | --- | --- | --- |
| Morpho Ethereum / Titan / Quasar | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | CONTINUAR sólo una revisión gratuita con evidencia nueva; PAUSAR si sólo resta proveedor o dinero |
| Aave/SVR Ethereum | SIMULADO; promoción directa del ejecutor antiguo REFUTADA | PENDIENTE | SIMULADO, costes completos pendientes | PENDIENTE | PENDIENTE | PAUSAR promoción |
| Morpho Robinhood 4663 | SIMULADO; admisión integral pendiente | PENDIENTE | SIMULADO, costes completos pendientes | PENDIENTE | PENDIENTE | CONGELAR hasta gate de reapertura |

Los cinco requisitos deben satisfacerse a la vez. SIMULADO no equivale a PROBADO comercialmente. El bloqueo común más temprano es G2; acreditarlo tampoco resolvería automáticamente estado, margen o captura. [CROSS_STRATEGY_KILL_MATRIX.md]

Robinhood puede reabrir investigación acotada cuando llegue evidencia nueva revisable de una vía financiable aplicable y del entorno necesario. Afirmar financiación disponible exige además condiciones aceptadas, fondos comprobados y cobertura sin recurso. Se conserva esa distinción del archivo original REOPENING.md.

### Discrepancias delimitadas por archivo y SHA

| Afirmación comparada | Evidencia exacta | Resolución |
| --- | --- | --- |
| 159 frente a 168 pruebas Python de Morpho | AUDIT_STATUS.md, SHA `ddade5d099e19449e0c4e55079a2b0c9d9ee1141`, línea 29; RESEARCH_STATUS.md, SHA `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`, líneas 11–17 y 85–86 | Etapas distintas explícitas. No se atribuye a Astra un conteo falso ni se recertifican sus pruebas. |
| “Seguimiento prospectivo” entendido como selección antes del comienzo de una ventana futura | `evidence/2026-10-17-prospective-recovered/followup-selection.json`, SHA Morpho anterior, `saved_at_utc` en línea 2; intervalo y respuestas contiguos en el mismo expediente | La selección antecede la consulta, pero ocurre después de terminar la ventana. Refutada sólo esa interpretación más fuerte. |
| Residual y frontera de B | `PROFITABILITY_RESULTS.md` y resultados JSON, mismo SHA Morpho; rederivación independiente de recibo/traza | Coincidencia exacta bajo el perímetro declarado. Sin prueba de P&L propio. |
| Conversión Robinhood a wei de esta auditoría | README Robinhood en SHA `6693542e675f930a7ef0a4fd60cb72e7a6608845`; log SUPERSEDED y prueba final propia | Error de transcripción nuestro, corregido. La fuente original era correcta. |

Las rutas completas e IDs se conservan en SOURCE_LEDGER.json. No se hace una acusación general contra Astra ni se presume conocimiento de commits futuros.

## 6. Tres solicitudes concretas de verificación a Astra

**A1 — Compatibilidad financiera Morpho, prioridad máxima.** Entregar el manifiesto de la ruta existente, sin firma: red, actores y destinatarios económicos, condición exacta de sponsorship publicada, capital previo requerido, anticipo, gas del fondeo, value si aplica, reembolso cobrado una sola vez y obligaciones S1–S5. Adjuntar cualquier evidencia aplicable ya disponible de financiación/cobertura sin recurso; de no existir, rotular PENDIENTE. Una respuesta documental o contable puede refutar una variante sin otro contrato ni bundle.

**A2 — Límite de la reproducción B.** Señalar la evidencia ya existente que autentica el estado antes de la transacción índice 1, efectos pertinentes de la transacción 0, intereses/oráculo y liquidez DEX, y la paridad de la ruta NQC. Separar los artefactos auténticos de fixtures. Si falta el testigo, conservar G1 PENDIENTE y no presentar la reconstrucción de flujos de terceros como replay NQC. Esta solicitud no ordena repetir un fork.

**A3 — Evidencia de captura y cobertura.** Proporcionar un candidato y registros ya disponibles que vinculen mismo bloque/hash, todas las dependencias, selección previa, señal recibida, incertidumbre de reloj y cierre de admisión. Indicar qué canal del ganador se observa y cuáles quedan desconocidos. Acompañar control positivo de cobertura y conservar nulos/rechazos. Si no existe, declarar G4/G5 PENDIENTE; no reabrir un recolector permanente.

## 7. Escala, objetivos y control de entrega

La búsqueda histórica acotada no localizó el artefacto primario de “11 microsegundos” ni el de “$14,000 billones”. Estado **NO LOCALIZADOS, NO REFUTADOS**. El resultado 11.3288× de Multicall3 expresa una razón de tiempos; no 11 µs. T37 declara 50000 mercados y 1000000 señales sintéticos. Filas de pools, tokens, fuentes de capital y coordenadas bloque/activo son unidades distintas y no se suman como mercados negociables. [SCALE_AND_MAGNITUDE_AUDIT.md]

La sensibilidad para metas de USD 1000, 5000, 10000 y 50000 está en el ledger: `ceil((T+F)/m)`, sólo si m > 0. m y F son supuestos explícitos; no hay tasa de victoria ni pronóstico. F = 0 es un escenario aritmético, no una constatación de gastos reales nulos.

La reejecución final del coordinador terminó a **2026-10-17T16:13:33Z** con salidas 0 para los tres comandos propios. `evidence/final_validation.json` conserva comandos y salidas. El verificador original de aislamiento terminó con salida 1 por payload faltante en la copia parcial, condición **BLOCKED_INPUTS**. No se ejecutaron sus nueve pruebas ni suites Rust/Solidity/Astra. La comparación de árboles Git de publicación es un control distinto; su recibo de lectura posterior y lista de paths/bytes se entregan como PUBLICATION_RECEIPT.json en el paquete final.

Destino único de los nuevos archivos de repositorio: `migration/independent-viability-redteam-20261017/`, en rama propia derivada de auditoría. La publicación sólo se considera realizada cuando el recibo confirma commit y read-back. Ningún mensaje se envía a otros chats; el propietario transfiere este relevo.

Gasto externo iniciado por las acciones de esta misión: **$0**. No se inspeccionó la facturación preexistente del usuario. No hubo firmas, transacciones, contactos, cuentas nuevas, admisión de bundles, despliegues ni procesos persistentes.

**Motivación: 7/10. Confianza comercial: 2/10, juicio cualitativo, no probabilidad.**
**Resultado: bueno para la investigación; desfavorable para promover ingresos hoy.**
**Siguiente movimiento concreto:** el director obtiene el expediente A1 ya existente o aportado por el propietario; esta auditoría contrasta compatibilidad y obligaciones. Sin evidencia nueva capaz de cambiar G2 dentro de $0, se pausa la línea y se preserva el cierre.
