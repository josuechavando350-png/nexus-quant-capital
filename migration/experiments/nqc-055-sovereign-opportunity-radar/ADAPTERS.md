# Contrato de adaptadores y familias futuras

`core.Adapter` expone `candidates(sources)` y `evaluate(sources, candidates)`.
`radar.scan(sources, adapters)` registra identidades, requisitos, decisiones y
prioridades. El adaptador se ocupa de interpretar las fuentes y producir límites
con unidades válidas. El kernel no llama a RPC ni ejecuta código de fuentes remotas.
`radar.run()` añade únicamente la evaluación de referencia específica de NQC055.

**Único adaptador implementado y validado con observaciones reales: MorphoArchive.**
Una prueba contractual entrega un dossier A real mediante un adaptador mínimo
para comprobar que `scan` no depende de la presencia de B. No es una integración
de otro protocolo ni una validación de arbitraje.

Un adaptador futuro debe producir:

- Identidad estable `eip155:<chain>/<protocol>/<tx>` y observaciones originales con
  puntero, commit, blob y SHA256. En este prototipo las identidades son transacciones
  históricas; candidatos prospectivos necesitarían otra versión de esquema.
- Mercado/activos/contratos, posición temporal y nivel de autenticación explícitos.
- Venta, gas y costes de inclusión observados o `null`; nunca valores imputados.
- Rutas, financiación, competencia y límites económicos por escenario, más grupos
  de reutilización y estado de investigación. `net_profit` y admisión permanecen
  sin promover a beneficio capturado por este motor offline.
- Las obligaciones con componentes disjuntos, activos exactos y referencias que
  justifiquen cualquier conversión. Los campos extra de cada familia quedan en
  el dossier del adaptador; no requieren convertirlos artificialmente en Morpho.

Los criterios/contratos actuales son deliberadamente pequeños; una familia que
necesite otra semántica debe versionar su adaptador/política y aportar casos reales.
No se promete un motor universal ya completo.

| Familia futura | Fuente posible del excedente | Evidencia mínima antes de simulación defendible | Financiación y riesgos |
|---|---|---|---|
| Liquidación de préstamo | Colateral realizable superior a deuda y obligaciones, dentro de reglas del protocolo | Estado coherente de deuda/colateral/oráculo, reglas y runtime, elegibilidad, ruta ejecutable para la cantidad y contexto de bloque | Callback o adelanto de principal; gas previo; cambios de oráculo/interés, límites, competencia y financiación |
| Arbitraje atómico | Salida realizable de un ciclo mayor que entradas y todos sus costes | Mismo preestado para todos los pools, código, reservas/límites, fees y tamaños, secuencia atómica y repago | Capital temporal y prima, gas, reversiones, orden, adversarios y latencia; precios indicativos no bastan |
| Diferencias de liquidez/precios ejecutables | Diferencia entre compras y ventas efectivamente llenables para un tamaño concreto | Cotizaciones ejecutables coherentes, profundidad, restricciones de tokens y liquidación, ruta completa de cierre | Inventario o financiación, slippage, caducidad, captura y riesgo de ejecución; una cotización aislada no es beneficio |
| Otra oportunidad DeFi verificable | Obligación contractual o flujo identificable superior a obligaciones completas | Fuente precisa del ingreso, contrapartida, reglas/código, condiciones de elegibilidad y cobro, estado temporal | Debe declarar garantías/principal, gas, insolvencia/settlement, competencia y condiciones de salida antes de proponer ejecución |

Todas las familias requieren evidencia de inclusión/latencia antes de atribuir
captura a NQC. Un replay histórico exitoso no prueba que la oportunidad siga
disponible. Riesgos no medidos y costes de adquisición permanecen desconocidos.
No se implementan adaptadores adicionales, feeds, carteras, estrategias reales,
schedulers ni modelos ML en NQC055.
