# Entrega al director — Directiva 004

**Resultado: éxito técnico local y región favorable de modelo; bloqueo comercial e histórico intacto.** Se coordinaron financiación, CREATE, liquidación, devolución y fee separado en un bloque Anvil. El estado y los flujos concilian; no hay atomicidad EVM entre esas transacciones. La exclusión total solo está probada como política de selección del laboratorio.

Novedad económica: sobre el mismo preestado con 8 WETH cash, C1 cobra 2,325,526 gas y C2 5,196,129 para el primer ciclo. Ambos producen 0.159365645570551238 WETH nuevo NQC. El financiador gana respectivamente 0.043348948 y 0.037607742 ETH de caja antes de costos comerciales desconocidos. C2 ahorra gas de llamada, pero sus despliegues superan ese ahorro en este primer uso. La variante predesplegada omite únicamente costos pagados antes por otro actor, cuyos recibos se conservan; no prueba arranque gratuito ni compatibilidad mainnet.

Resultados negativos: C2 revierte con cash insuficiente; la pérdida medida del financiador es 0.011762244 ETH, aunque recupere U. C1 a 21 gwei completa pero, con financiador y builder separados, deja al financiador −0.001123326 ETH. Un anticipo excesivo sin devolución empeora la pérdida a −0.252084 ETH. Un status=1 sin contrato desplegado no acredita liquidación. Un cap correcto puede impedir incluir U si se reserva solo gas efectivo. El criterio local rechaza esas exposiciones.

| Puerta | Estado al cierre |
|---|---|
| Ejecución auténtica histórica | BLOCKED_EXTERNAL_EVIDENCE: falta preestado exacto y DEX Fluid del caso B |
| Mecánica EVM con fuentes originales | EVM_LOCAL_PASS dentro de la fixture y rutas documentadas |
| Financiación sin recurso | BLOCKED_EXTERNAL_EVIDENCE: contraparte y responsabilidades UNKNOWN |
| Margen completo real | BLOCKED_EXTERNAL_EVIDENCE; MODEL_ONLY bajo partidas medidas/supuestas |
| Recepción/captura temporal | NOT_RUN / sin evidencia competitiva |
| Recurrencia económica | NO ESTIMABLE |

Se preservan los doce candidatos congelados y su estado UNRATED_MISSING_WITNESS. No hay nuevos datos históricos, consultas de endpoints denegados, selección de ganadores retrospectiva ni monitoreo. B sigue siendo una operación de terceros: no se mezcla su deuda de 26.039738525656992415 WETH con la fixture de 8 WETH. Su residual anterior de 0.001651296044494913 ETH no acredita ingreso NQC. El expediente conserva tip íntegro de 0.368092735714237547 ETH al proponente y WETH preexistente de 0.006392502690919791, sin reclasificarlos.

**Decisión: PAUSAR la escalada comercial; conservar el arnés verificado.** Motivación técnica 7/10; confianza comercial 1/10, evaluaciones cualitativas, no probabilidades. No hay motivo para multiplicar fixtures sintéticas con la misma falta de testigo. Única prueba siguiente: replay local de C1 sobre un testigo gratuito, permitido y autenticable del estado inmediatamente anterior a B, incluidos efectos de tx0 y conversión Fluid. Se ejecutará únicamente si aparece ese testigo; no se sustituyen datos faltantes ni se contrata acceso.

Gasto externo incurrido: $0 MXN. P&L NQC certificado: US$0. Expectativa mensual: NO ESTIMABLE. Sin firmas, transacciones públicas, despliegues externos, servicios o workflows. Estado de GitHub y commits: `PUBLICATION.md`; logs y comandos: `VALIDATION_LOG.md`.
