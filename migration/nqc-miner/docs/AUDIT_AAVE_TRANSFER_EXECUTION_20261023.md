# Auditoría: transferencia real de aTokens y comisión

23 de octubre de 2026. Avance global: **43/100**, sin puntos adicionales.

La secuencia probada ahora ejecuta en una transacción local la detección de colateral
agotado, el cambio de bandera, la quema de deuda, el cálculo de tasas, la entrega
de aTokens al liquidador y la comisión a tesorería. Los tokens, proxies, estrategia
y controlador de recompensas usan los runtimes reales previamente comprobados.
El Pool es un harness; los balances y parámetros siguen siendo sintéticos.

Los cuatro segmentos extraídos de LiquidationLogic son byte-exactos. La función
interna de deuda se importa sin modificar. El compilador fijado por SHA-256 reproduce
los mismos 5928 bytes del harness en dos ejecuciones. El código original y los
perfiles de compilación anteriores permanecen intactos; no hay nuevas capturas RPC.

El saldo posterior al primer envío se obtiene del aToken real. Con índice 1.5 RAY,
saldo escalado 100, envío 148 y comisión solicitada 2, el primer envío consume 99
unidades escaladas. La comisión queda limitada a la unidad restante y su importe
se recalcula a 1. No se suministra artificialmente ese saldo posterior. En el ejemplo
normal, los saldos 100/20/7 pasan a 66/47/14 sin cambiar el suministro escalado 1000.
Coinciden 19 salidas, 17 eventos ordenados y los 17 slots de storage modificados.

Las ocho pruebas Rust nuevas incluyen 320 casos con semilla fija y comparación
independiente de redondeos, intereses, recompensas y comisión. Cada caso también
ejecuta las dos referencias anteriores de deuda/token/tasas y recompensas. Se
incluyen los cuatro proxies de aToken retenidos de ambas familias, comisión cero,
transferencia cero, comisión limitada a cero, tesorería como destinatario, máximos
uint120/uint128, flags ya apagados, IDs 127/128 y colateral sin valor por redondeo.
La transferencia a sí mismo se prueba como comportamiento aislado del token; no
se presenta como una liquidación válida.

Fallos tardíos por saldo desbordado o acumulación de recompensas en tesorería deben
revertir también deuda, tasas, flags, balances y logs anteriores. Los testigos
faltantes se rechazan. Ocho pruebas Python verifican procedencia/layouts y ejecutan
el ejemplo, el recorte de comisión y la reversión a través del CLI real.

Se conservan los intentos fallidos: prefijo de extracción ambiguo, nombre de API
incompatible con rand fijado, máscara faltante del timestamp de 32 bits en el modelo
y expectativa incorrecta sobre un evento que el contrato emite incondicionalmente.
El cuarto intento dirigido se interrumpió por desconexión del ejecutor y no cuenta
como ejecución completa. Las fuentes originales no se cambiaron para aprobar.

La batería completa terminó con **226 pruebas Rust y 322 Python: 548 aprobadas**,
sin fallos finales ni pruebas omitidas. También pasan Clippy, formato, identidad
de build, alcance e aislamiento. Las 16 pruebas nuevas están incluidas en ese total.

Fuente probada: `424775f2b17fdc2581fcd8cd70f50abe6c126e06`.
Base del bundle: `4cceb0975d80e4c9c72b297b7c02b07f4bbd0699`.
La verificación final se conserva en `evidence/aave-transfer-execution-20261023/`.

Confianza alta en los comportamientos comprobados dentro de este alcance. Quedan
pendientes el envío del activo subyacente, cobro de deuda, actualización inicial
de reservas, salud/eMode, deuda multirreserva, entrada real del Pool y reconstrucción
del estado histórico bajo el fork correcto. El sandbox sigue usando Cancun.
No se certifica liquidabilidad histórica, beneficio económico ni una fase operativa.
Observer y evidencia anterior intactos; sin despliegues, firmas, transacciones ni gasto.
