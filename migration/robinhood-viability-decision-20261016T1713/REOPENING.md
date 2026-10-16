# Expediente mínimo para reabrir un piloto sin capital del fundador

Preparación interna, no solicitud enviada, contrato ni autorización de gasto.
Complementa PR23 `FINANCING.md`; no sustituye sus condiciones ni compromete a nadie.

La propuesta examinable sería un operador que financie un piloto limitado y reciba
un reparto acordado del excedente, asumiendo sus pérdidas dentro de una reserva
previa. Morpho puede resolver el principal de determinada operación; no aporta el
ETH para gas inicial, intentos fallidos o infraestructura.

| Pregunta que debe contestar la contraparte | Evidencia exigible |
|---|---|
| ¿Qué operación admite? | Red 4663, EntryPoint exacto y versión; bytecode/cuenta/paymaster/ruta y configuración del bundler fijados; política que incluya esta liquidación, no sólo transferencias |
| ¿Qué financia antes del primer intento? | Arranque, despliegue si procede, stake, depósito y caja del bundler, costes fuera de cadena; propietario y reserva disponible sin doble contar fondos |
| ¿Cuánto y durante cuánto tiempo? | Presupuesto total, por intento, concurrencia, vigencia y reglas de parada; nada de recarga automática a cargo del fundador |
| ¿Quién absorbe cada fallo? | Rechazo previo, UserOp revertida, bundle revertido/expirado y gastos del proveedor; ninguna factura, deuda, garantía o obligación de reponer para Chavando |
| ¿Cómo se reparte y repone caja? | Base neta y porcentaje, destinos/plazos, USDG→ETH, costes de cambio, desfase temporal y prioridad de reservas |
| ¿Cómo se comprueba que funciona? | Entorno completo, fuentes fijadas, controles de admisión positivos/negativos, límites de tiempo/stake/depósito agregado y logs completos |

Para retomar investigación basta evidencia nueva revisable de una vía financiable
y del entorno; para afirmar financiación disponible hacen falta condiciones
aceptadas y fondos comprobados para ese piloto. Una oferta todavía no aceptada no
se rotulará como saldo disponible. El primer paso sigue siendo offline; cualquier
contacto, firma, gasto o envío real requiere autorización específica posterior.

La admisión local deberá distinguir el reloj histórico del caso de septiembre del
reloj actual: no omitir caducidad, no alterar servicios reales, no usar unsafe.
Debe conservar las comprobaciones de firma, parser, reputación, depósito agregado y
mempool; aislar todo camino de envío. La fuente fijada de ExecutionManager intenta
formar un bundle después de admitir; llamar directamente a ese método sin aislar
envíos sería improcedente. Revisar esto al diseñar un protocolo nuevo.

No exigir previamente una captura rentable para poder investigar: el piloto
serviría precisamente para medirla. Pero no declarar rentabilidad hasta observar
captura repetible y margen neto tras todos los fallos/costes con financiación viable.
