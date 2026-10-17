# Barrera de admisión y ausencia de recurso

**BLOCKED_EXTERNAL_EVIDENCE.** El local PASS no cubre los campos siguientes.

| Prioridad | Evidencia que falta | Consecuencia |
|---|---|---|
| 1 | Vinculación autenticada entre cuenta(s) de fondeo, receptor R/U y entidad builder | No atribuir R a Titan/Quasar ni consolidar sponsor y builder reales |
| 1 | Regla aplicable que precise A, gas/value, CREATE, reserva maxFee por prefijo y devolución de sobrantes | No construir U a partir de un anticipo o precio que aún no se conoce |
| 1 | Condiciones verificables de pérdida y ausencia de deuda, garantía, stake, cobro diferido o recurso contra fundador, S1–S12 | `founder_max_recourse_wei = null`, UNKNOWN |
| 2 | Criterio de ingreso neto exigido, costo adicional del bloque/patrocinio y política ante reverts/omisiones/reorg | Caja positiva local es necesaria para nuestro modelo, no suficiente para admisión real |
| 2 | Aceptación verificable de esta intención específica por mecanismo autorizado | NOT_TESTED; esta directiva prohíbe enviar o firmar |
| Independiente | Testigo histórico padre + tx0 + Morpho/oráculo/IRM + Fluid | B permanece BLOCKED_PRESTATE |
| Independiente | Señal anterior al cutoff, competencia y muestra de capturas netas | Potencial mensual NO ESTIMABLE |

## Única próxima prueba medible

Contrastar **un expediente público autenticado de la ruta concreta** con el manifiesto V06: ¿identifica al financiador y receptor, determina A/U/caps/CREATE, el ingreso incremental exigido y la asignación de pérdidas S1–S12 sin recurso personal? Resultado observable: cobertura de todos esos campos sin UNKNOWN, o listado de campos faltantes. Puede cambiar el dictamen documental hacia CONTINUAR validación acotada; por sí solo no demuestra aceptación ni rentabilidad histórica.

Se agotó lo que estas fuentes públicas y el experimento controlado pueden comprobar. Si el expediente sólo se obtiene mediante contacto privado, cuenta, pago, firmas o relay, **PAUSAR** hasta nueva autoridad/evidencia. No repetir pruebas sintéticas como sustituto. No se hizo contacto ni intento de endpoint.

## Obligaciones por actor

El builder de laboratorio aporta 100 ETH generados por Anvil; A no procede de NQC. Es una condición de prueba, no oferta de financiación. La cuenta NQC devuelve U efectivamente incluida; ETH retenido es anticipo pendiente, no beneficio. El gas ya consumido y los CREATE previos subsisten aunque la liquidación revierta. No se modela un derecho real de cobro inexistente ni se presume su ausencia: la responsabilidad externa es desconocida. El supuesto local `founder_model_recourse_wei=0` sólo sirve para evaluar la hipótesis y nunca rellena `founder_max_recourse_wei`.
