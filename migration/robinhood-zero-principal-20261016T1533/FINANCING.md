# Condiciones de una ruta sin aportación del fundador

Documento técnico para evaluación interna. No es un contrato firmado, una oferta,
un compromiso de terceros ni una autorización para gastos o contactos.

El modelo que merece probarse es un operador externo que aporta gas y capital de
operación, acepta pérdidas limitadas y recibe una parte explícita del excedente.
El callback permite explorar este modelo sin adelantar los 194.034131 USDG del
caso histórico; no garantiza que otras rutas puedan hacerlo ni financia ETH.

| Partida / decisión | Evidencia necesaria antes de declarar viable | Estado |
|---|---|---|
| Depósito EntryPoint y capital del bundler | Saldo externo verificable, límites por operación/concurrencia, propietario y reserva disponible | Sin compromiso ni fondos comprobados |
| Stake/admisión | Validación del account/paymaster exactos, versión EP, reglas y configuración del bundler; coste y bloqueo de stake si exige | No demostrado en bundler de producción |
| Fallos | Responsabilidad explícita por UserOp fallida, bundle revertido, rechazo previo y gastos fuera de cadena | Sin condiciones acordadas |
| Protección del fundador | Cero garantía personal, adelanto, recarga obligatoria, autodebito o deuda exigible; contraparte responsable de facturas | Sin acuerdo verificado |
| Reparto | Base del reparto: excedente después de principal, costes deducidos o no, porcentaje, destinatarios y plazo | Sin términos |
| Reinversión | Cobro real del excedente y conversión USDG→ETH con coste, liquidez y retraso; ausencia de doble reserva | No implementado/probado de extremo a extremo |
| Arranque | Despliegue, infraestructura, stake y gas inicial presupuestados y financiados por el tercero antes del primer intento | No financiado |
| Margen | Cotización fijada por hash, resultado y coste de todos los intentos; tasa prospectiva de éxito, coste fijo y conversión | No medidos para una campaña viable |

El depósito del paymaster y la caja nativa del bundler ocupan ubicaciones distintas
y deben existir antes de enviar. Los saldos inyectados de 0.1 ETH y 0.01 ETH del
replay son fixtures, no dinero obtenido. La reserva histórica por UserOp de la
variante de ventana es 0.00024954124 ETH; no es presupuesto de lanzamiento, saldo
actual ni tarifa futura. Stake, despliegue, caja del bundler y operación son aparte.

La política de reservas ya existe en `robinhood-opportunity-economics-20261016`;
este incremento no la sustituye. Un reparto de excedente tampoco repone por sí
solo el depósito: la ruta histórica paga USDG a la cuenta, no ETH al paymaster.

Siguiente prueba técnica: validar el account/paymaster de ventana contra una
versión/configuración fijada del bundler en entorno local, sin envíos ni cuentas
de proveedor. Registrar admisión/rechazo completo, stake requerido y límites.
Las comprobaciones de tiempo y la ejecución de EntryPoint existentes no equivalen
a ejecutar todas las reglas del bundler. Si no hay recursos para esa prueba,
documentar el bloqueo; no reemplazarla por otra simulación rentable del caso viejo.

La financiación externa real exige después una contraparte que acepte esos términos.
No puede fabricarse con código ni con más escaneos. Un candidato nuevo y un registro
prospectivo completo siguen siendo necesarios para demostrar captura y margen.
