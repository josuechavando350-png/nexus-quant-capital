# Auditoría: ambas rutas de colateral con cobro USDC

23 de octubre de 2026, America/Mexico_City. Avance global: **43/100**, sin crédito
adicional de fase.

La misma envoltura artificial ahora selecciona el if/else original de Aave para
recibir aTokens o WETH y ejecuta después la comisión, el cobro USDC y el evento
LiquidationCall. El fragmento condicional y el fragmento de pago/evento conservan
sus bytes originales. La llamada interna de quema se reenvía a la función
original de la biblioteca, sin modificar sus fuentes.

## Resultado comprobado

En ambas muestras se pagan 40 USDC: saldo del liquidador 100 a 60, destino aUSDC
200 a 240 y autorización 100 a 60. Con aTokens, el liquidador termina con 47
unidades escaladas y la oferta permanece en 1000; con WETH, conserva sus 20
aTokens escalados y la oferta baja a 973. El saldo escalado del prestatario y la
tesorería terminan en 66 y 14 en ambos casos.

La ruta aToken funciona sin cuenta WETH, sin slot de activo subyacente del aToken
y sin mapping de tasas del colateral. Su ejecución tiene 19 eventos y 21 cambios
de almacenamiento. La ruta WETH conserva los 16 eventos y 24 cambios ya
comprobados. Se verifican las 25 palabras de salida de cada muestra. El indicador
final del evento corresponde al modo seleccionado. Los valores de gas 433684 y
480994 corresponden exclusivamente a estas envolturas y estados artificiales.

Insuficiencia de USDC/autorización, pausa, bloqueos, desbordamiento del receptor y
rechazo del administrador revierten todos los efectos previos en ambas rutas.
Los faltantes de código/routing/slots fallan cerrados. Tokens artificiales prueban
respuestas false, malformadas y ausencia de código; no se etiquetan como USDC.
Un fallo de tesorería precede a una pausa simultánea de USDC. Valores de modo ABI
inválidos o truncados revierten antes de cualquier efecto del contrato.

## Fuente y verificación

Fuente probada: `30365d4be28f96851bf6bf33c4d0b6dfbef40f55`.
Árbol: `8a0ff935e59bb87b908be22fd21877f8041a61e6`.
Base anterior: `0455198d478ec999290accb412e521fe4109d93d`.

**632 pruebas distintas aprobadas: 268 Rust y 364 Python**, incluidas 9 Rust y
9 Python nuevas. Los 80 casos con semilla se ejecutan en las dos rutas; esas
160 ejecuciones principales y sus referencias no se suman al conteo de tests.
Build offline, Clippy con warnings denegados, formato, identidad de build,
alcance y aislamiento pasan. La fuente compilada está limpia y los inputs
permanecen idénticos durante la verificación completa. Todos los controles
dirigidos y el primer runner completo de este incremento pasan sin omisiones.

Se conservan 531 fuentes originales, 106 workflows deshabilitados y cero activos.
El verificador conserva su límite: no comprueba objetos Git originales ni concede
recertificación canónica. Observador permanece intacto. El cierre incorpora solo
documentación/evidencia; no cambia los inputs probados.

Solc 0.8.27 con checksum fijado produce una envoltura de 7638 bytes. La
recompilación fresca reproduce salida y stderr idénticos. Se mantienen sin cambios
los runtimes completos observados y todas las diferencias de metadata de USDC y
WETH. La igualdad completa fuente/runtime continúa en false.

Evidencia: `evidence/aave-delivery-execution-20261023/verification.json`.
Reproducción: [aave-delivery-execution.md](aave-delivery-execution.md).
No hubo nuevas consultas RPC públicas: se reutilizó y revalidó offline la captura
anterior de USDC en los tres bloques históricos.

## Límites y siguiente trabajo

Confianza alta dentro del alcance artificial comprobado. El if/else conservado
incluye la condición para deuda y colateral iguales, pero los activos fijados son
USDC y WETH; esa condición no se ejecuta ni se declara cubierta. Siguen pendientes
validaciones/actualizaciones iniciales, salud/eMode, cálculo integrado de importes,
mismo activo, deuda incobrable de múltiples reservas, entrada real del Pool y
preestado histórico autenticado bajo el fork correcto. El sandbox usa Cancun.

No hay certificación histórica completa, elegibilidad, rentabilidad, Foundry
fuzzing ni salida de fase operacional. La política de gas exclusiva de Titan
continúa sin cambios, con cero gas propio/fallback, principal, colateral o
garantías del operador. Patrocinio y financiación no quedan acreditados por
balances de simulación. No hubo firma, broadcast, despliegue, activación ni gasto.
