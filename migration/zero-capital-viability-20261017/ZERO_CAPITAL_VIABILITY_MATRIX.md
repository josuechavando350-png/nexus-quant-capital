# Auditoría de capital cero — 17 de octubre de 2026

Base inmutable: `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`. Rama nueva: `research/nqc-zero-capital-viability-20261017`. Las cinco referencias remotas coincidieron con la directiva al inicio; SHA, tree y hora están en [initial-heads.json](evidence/initial-heads.json). Fuentes y límites por afirmación: [CLAIM_AND_SOURCE_LEDGER.json](CLAIM_AND_SOURCE_LEDGER.json). Identificadores A, R, M, T, Q y C remiten a ese registro.

**Ninguna arquitectura supera hoy las seis puertas.** PENDIENTE significa evidencia insuficiente; no imposibilidad. SIMULADO no supera una puerta que exige estado auténtico, costes completos o contraparte real. ESTIMADO identifica aritmética condicionada. PROBADO siempre se limita al objeto de la afirmación. REFUTADO se limita a la hipótesis especificada.

| Puerta | A: Aave/SVR Ethereum | B: Morpho Robinhood, cadena 4663 | C: Morpho Ethereum |
|---|---|---|---|
| G0: cero recurso personal | PENDIENTE: no contrato de cobertura | PENDIENTE: depósitos de prueba | PENDIENTE: mecanismo público sin acuerdo NQC |
| G1: ejecución auténtica y obligaciones | SIMULADO: one-shot histórica; ruta actual REFUTADA sin modificarla | SIMULADO: estado de proveedor, fixtures financiadas, sin prueba de raíz | PENDIENTE: no replay completo del tercero ni NQC |
| G2: tercero paga arranque y fallos | PENDIENTE | PENDIENTE | PENDIENTE |
| G3: señal y admisión a tiempo | PENDIENTE | PENDIENTE | PENDIENTE |
| G4: neto completo positivo | PENDIENTE | PENDIENTE | PENDIENTE |
| G5: recurrencia medida | PENDIENTE | PENDIENTE | PENDIENTE |

## Requisitos comparables

En cada celda se clasifica la evidencia disponible para la ruta; los resultados locales no acreditan el requisito comercial. Responsable económico significa actor que **debería** asumir la partida: no se ha acreditado que lo acepte. Importes ausentes: DESCONOCIDO.

| # / requisito | Aave/SVR | Robinhood | Morpho Ethereum | Fuente / prueba mínima / responsable |
|---|---|---|---|---|
| 1. Principal temporal y devolución | SIMULADO: flash y swaps históricos | SIMULADO: colateral en callback y deuda USDG | SIMULADO: callback C1; flash C2 requiere cash | A1/R1/M2: replay de misma posición e índice, balances de protocolo/prestamista y repago íntegro |
| 2. EOA inicial y reserva de gas | ESTIMADO: reserva positiva a maxFee | SIMULADO: bundler tiene 0.01 ETH de fixture | PENDIENTE: top-up externo | A2/R2/T/Q: saldo previo y reserva antes de ejecutar; financiador externo |
| 3. Despliegue/inicialización | SIMULADO: CREATE histórica incluida en gas local, fuente no actual | PENDIENTE: cuatro fixtures preinstaladas, despliegue excluido | PENDIENTE: C1 requiere despliegue; C2 depende de ruta/adaptadores | A1/R1/M2: secuencia completa desde cero y coste de arranque; financiador |
| 4a. Paymaster: depósito | PENDIENTE: no ruta AA auditada | SIMULADO: 0.1 ETH en EntryPoint | PENDIENTE: no ruta AA auditada | R2: depósito externo reservado verificable; paymaster |
| 4b. Stake, política, reputación y admisión | PENDIENTE | PENDIENTE: RETURN EVM no es admisión integral | PENDIENTE | R3: ValidationManager, parser, reputación y reservas, sin unsafe/stubs; bundler/paymaster |
| 5. DEX ejecutable | SIMULADO: flash/swap ya incluidos en excedente | SIMULADO: wsNET→sNET→NET→USDG y tributo | PENDIENTE: Fluid antes de tx1; V2 solo sintético | A1/R1/M1: cotización y límites en el índice, transferencias; DEX y operador |
| 6. Deuda, redondeo y bad debt | SIMULADO: caso histórico fijo | SIMULADO: éxito en índice, fallo en padre | SIMULADO: matemáticas/core; caso B incompleto | A1/R1/M2/C1: estado deuda/oráculo/IRM y activos token reales; protocolo |
| 7. Builder, proponente, sponsor, bundler | PENDIENTE: puja no acreditada | SIMULADO: cobro paymaster distinto de tasa de red | PENDIENTE: coinbase observado, dueño económico no probado | A2/R2/M1/T/Q: flujos y derechos de cada beneficiario; cada receptor |
| 8. Revert, no inclusión, inclusión parcial | PENDIENTE: pérdidas completas | SIMULADO: UserOp fallida cobra gas y paymaster | ESTIMADO: ejemplo de top-up separado; contrato desconocido | R2/C2/T/Q: balance tras cada fallo y cobertura sin recurso; financiador |
| 9. Servicios y obligaciones mensuales | PENDIENTE | PENDIENTE | PENDIENTE | S1/S2: presupuesto operativo y responsable, sin créditos/deuda personal |
| 10. Estado, runtime y recibo | SIMULADO: fuente histórica acotada | SIMULADO: paridad 112 lecturas, sin MPT | PENDIENTE: trie de tx sí, storage/tx0/Fluid no | A1/R1/M1: tercero primero y NQC después, mismo testigo; proveedor de datos |
| 11. Recepción, estado coherente, latencia | PENDIENTE: hint autorizado no recibido | PENDIENTE: transporte no prueba captura | REFUTADO: muestra conservada mezcla tres alturas | A3/R4/M3: registro prospectivo coherente y reloj; investigador |
| 12. Preparación, cierre, competidor | PENDIENTE | PENDIENTE: bundler integral bloqueado | PENDIENTE | A3/R3/M3/C3: tiempos comparables anteriores a corte y ganador; fuente/builder |
| 13. P&L incremental propio | PENDIENTE: USDC simulado | PENDIENTE: USDG simulado, conversión nativa desconocida | PENDIENTE: residual del tercero, propiedad desconocida | A2/R2/M1: titularidad, pasivos, activos iniciales/finales y conversión; NQC y contrapartes |
| 14. Universo, elegibilidad y recurrencia | PENDIENTE | PENDIENTE | PROBADO: 143 registros API/141 tx; elegibilidad PENDIENTE | C1: censo con cobertura independiente y cada evento admisible; investigador |
| 15. Responsabilidad final del propietario | PENDIENTE | PENDIENTE | PENDIENTE | T/Q/S1/S2: compromiso verificable de cero gasto, garantía, reposición y deuda futura; contraparte |

La modalidad de pagar después con tarjeta o factura del propietario queda **REFUTADA para G0/G2 bajo este mandato**. No refuta la posibilidad de un patrocinador ajeno que asuma contractualmente esas obligaciones. Tampoco el principal flash financia por sí solo el gas.

Decisiones y condiciones de reapertura: [RESEARCH_DECISION.md](RESEARCH_DECISION.md).
