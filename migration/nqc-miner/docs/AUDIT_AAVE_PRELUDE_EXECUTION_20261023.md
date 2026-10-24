# Auditoría: reservas y validación inicial antes de entregar colateral

23 de octubre de 2026, America/Mexico_City. Avance global: **43/100**, sin crédito
adicional de fase.

La composición ejecuta ahora los fragmentos originales de caché/actualización de
la reserva de deuda y luego de la reserva de colateral, las lecturas de saldos
escalados y ValidationLogic.validateLiquidationCall antes de quemar deuda,
entregar aTokens o WETH, cobrar comisión y recibir USDC. Las fuentes originales
permanecen sin cambios.

Los totales se leen mediante los proxies y la implementación observados de los
tokens de deuda variable. El token de deuda WETH añadido ya tenía identidad y
routing auditados en dos bloques retenidos; este incremento no hizo consultas
RPC públicas nuevas. Reserva, token storage, salud e importes siguen formando
un estado artificial. El Pool de entrada continúa siendo una envoltura sintética.

## Resultado y límites de cálculo

Los índices actualizados, tesorería acumulada, timestamps y factores alimentan
la ejecución posterior. La deuda seleccionada y el balance de colateral se
derivan del saldo escalado leído y los índices nuevos; ya no se reciben como
cachés o balances subyacentes calculados por el llamador. Se conserva el redondeo
ceil de deuda y floor de colateral.

En la muestra artificial de un año, tesorerías de deuda/colateral avanzan de
7/11 a 20/24; deuda y colateral seleccionados resultan 166/156. Ambas rutas pagan
40 USDC y dejan wallet/vault/allowance en 60/240/60. Se comprueban las 37 palabras
de salida, todos los eventos ordenados y todos los cambios de almacenamiento:
19 eventos/29 slots en aToken y 16 eventos/30 slots en WETH.

**La salud agregada sigue suministrada.** GenericLogic, eMode, oráculos e importes
calculados de liquidación todavía no están integrados. Que el validador original
acepte una salud aportada no demuestra elegibilidad real. Los valores de gas
636438 y 643971 son exclusivos de estas envolturas artificiales.

## Pruebas e identidad

Fuente probada: `1273c9badb88d509cd7280f171182dbde66fb0ae`.
Árbol: `f4a86bdc53e111a9eda7d879afcb9cde20186509`.
Base previa: `2973fa86cdea4334f9fe91b13c42b5bd1413e7a0`.

**647 pruebas distintas aprobadas: 275 Rust y 372 Python**, incluidas 7 Rust
y 8 Python nuevas. Los 32 conjuntos con semilla se prueban en ambas rutas; esas
64 ejecuciones principales y sus referencias no se suman al conteo de pruebas.
Se comparan modelos independientes de reservas y condiciones con la composición
previa de entrega/pago. La CLI reproduce además los informes de esos modelos.

Se cubren los ocho rechazos originales de validación, actualizaciones en el mismo
timestamp, tasas/deuda cero, overflow de tesorería, downcast de índices, timestamps
futuros, callbacks y ambas rutas. Los rechazos revierten también la inicialización
artificial y la acumulación de índices/tesorería. Un fallo de la primera reserva
precede a la caché de la segunda incluso cuando falta su testigo. Un fallo tardío
de USDC revierte el conjunto. Los datos ausentes fallan cerrados.

Build offline, Clippy con warnings denegados, formato, identidad de compilación,
alcance y aislamiento pasan sobre la fuente limpia fijada. El runner completo
pasa a la primera, sin fallos ni omisiones. Se conservan 531 fuentes originales,
106 workflows deshabilitados y cero activos. El verificador no comprobó objetos
Git originales ni concedió recertificación canónica. Observador permanece intacto.

En desarrollo, el primer compilador rechazó el checksum tipográfico de una
dirección en la envoltura nueva; se corrigió con el checksum emitido por solc.
Clippy detectó dos detalles del código de pruebas y se corrigieron sin suprimir
advertencias. Los fallos permanecen en development/. No se modificó una fuente
original ni una salida de compilador para superar controles. Solc 0.8.27 con
checksum fijado produce 9919 bytes; otra compilación fresca reproduce output y
stderr idénticos.

El commit de cierre agrega solo documentación y evidencia; los inputs auditados
permanecen idénticos. Evidencia:
`evidence/aave-prelude-execution-20261023/verification.json`.
Reproducción y límites: [aave-prelude-execution.md](aave-prelude-execution.md).

## Continuidad

Confianza alta dentro del alcance artificial probado. Pendientes: cálculo
agregado de salud/eMode, precios/importes, mismo activo, deuda incobrable de
múltiples reservas, entrada real del Pool, diferencias de metadata WETH/USDC y
preestado histórico autenticado bajo su fork. El sandbox usa Cancun. No se
certifican liquidación histórica completa, rentabilidad, Foundry fuzzing ni
salida operacional de fase.

La política exclusiva de gas Titan permanece intacta, sin gas propio/fallback,
principal, colateral ni garantías del operador. La simulación no acredita
financiación ni compromiso del patrocinador. No hubo firma, broadcast, despliegue,
activación o gasto.
