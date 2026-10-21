# Captura competitiva — NO DEMOSTRADA

Los metadatos consultados fijan:

| Observación | UTC | México (UTC−06) |
|---|---|---|
| Cierre del padre 25666957 | 2026-08-02 11:39:47 | 2026-08-02 05:39:47 |
| Bloque objetivo 25666958 | 2026-08-02 11:39:59 | 2026-08-02 05:39:59 |

La transacción histórica fue la primera de usuario según la evidencia previa. Eso evita un prefijo
de otras transacciones de usuario; no demuestra que la posición fuera liquidable al cierre del padre.
El timestamp, acumulación de intereses, oráculo y estado del bloque siguiente siguen importando.
La separación de 12 segundos tampoco prueba una ventana de captura de 12 segundos disponible a NQC.

No se recuperaron el precio del oráculo, la deuda acumulada ni la salud de la posición al padre.
Tampoco se recuperaron el instante en que los datos llegaron a NQC, una detección firmemente fechada,
latencia de simulación/envío, exposición pública/privada, bids competidores o respuestas del builder.
No puede identificarse el primer instante de liquidabilidad, ni asignarse una probabilidad de victoria.

El caso está seleccionado por su éxito observado posteriormente. Usar calldata ganador, coinbase,
prevRandao, ruta completa o pagos del bloque ganador como información que NQC ya conocía introduciría
información futura. Una futura reproducción satisfactoria seguiría siendo un contrafactual histórico.
La ruta y la política de oferta deben fijarse con datos disponibles antes del corte, conservar timestamps
de adquisición y evaluarse prospectivamente para sostener una captura posible.

Veredicto: `EX_ANTE_CAPTURE_UNPROVEN`. No se infiere ingreso mensual, porcentaje del mercado ni
capacidad competitiva de los 84.308093 USDC de excedente bruto del operador externo.
