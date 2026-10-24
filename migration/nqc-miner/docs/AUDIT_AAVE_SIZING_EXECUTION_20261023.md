# Auditoría: importes originales conectados con reservas y pagos

23 de octubre de 2026, America/Mexico_City. Avance global: **43/100**, sin crédito
adicional de fase.

La composición ejecuta ahora el cálculo original de unidades, factor de cierre,
límite solicitado, colateral disponible, bonificación, comisión y remanentes
mínimos después de actualizar ambas reservas y validar la llamada. Esos importes
alimentan la quema de deuda, las dos rutas de entrega, la comisión final y el
cobro de USDC en una misma transacción artificial. El llamador suministra un
máximo solicitado, no los tres importes efectivos. Fuentes recuperadas intactas.

La bonificación se deriva de la configuración de reserva. La envoltura cubre
exclusivamente categoría eMode cero; no ejecuta selección eMode. Salud, precios
y totales agregados siguen suministrados. No hubo consultas RPC públicas nuevas.

## Resultado y contraste

La muestra artificial parte de saldos escalados, actualiza índices/tesorería y
deriva deuda/colateral de 166/156. La petición de 40 calcula deuda pagada 40,
colateral para el liquidador 41 y comisión 1. Wallet/vault/allowance USDC quedan
en 460/240/460. Los ejemplos usan decimales cero y precios artificiales: son
unidades de prueba, no importes económicos reales de Ethereum. Otro caso ejercita
6/18 decimales con precios ajustados artificialmente.

Se comparan las 43 palabras, todos los eventos ordenados y todos los cambios de
storage contra modelos independientes y la composición previa. aToken mantiene
oferta escalada 1000 y termina con saldos 72/47/8; WETH reduce oferta a 973 y deja
72/20/8. Son 19 eventos/29 slots y 16 eventos/30 slots, respectivamente. Gas
640818/648352 pertenece solo a estas envolturas y no estima gasto operacional.

## Pruebas e identidad

Fuente probada: `e733d1c3792bf8a1494097e23d38c658078ba38b`.
Árbol: `209c7a5eda376f96869e273bbaf848ff05bafce8`.
Base anterior: `7c339e6c62e291a5c03ec79d347fc2ee07eb3008`.

**662 pruebas distintas aprobadas: 282 Rust y 380 Python**, incluidas 7 Rust y
8 Python nuevas. Los 48 conjuntos con semilla corren en ambas rutas; esas 96
invocaciones principales y sus referencias no inflan el conteo de pruebas.

Se verifican el umbral exacto de salud para factor de cierre, límites de deuda
agregada/petición, agotamiento de colateral, bonificación/comisión, distintas
unidades de reserva, aceptación y rechazo exactos de remanentes, divisor cero,
overflows y orden de validación. Un rechazo por remanentes revierte también
índices/tesorería ya actualizados. Un fallo tardío de USDC revierte todos los
efectos y eventos. Los testigos ausentes fallan cerrados. Agotar una reserva no
marca colateral agregado cero cuando el total suministrado indica otras reservas.

Build offline, suite completa, Clippy con warnings denegados, formato, identidad,
alcance y aislamiento pasan sobre la fuente limpia fijada, a la primera ejecución
completa y sin omisiones. Se preservan 531 fuentes originales, 106 workflows
deshabilitados y cero activos. El verificador no comprobó objetos Git originales
ni otorgó recertificación canónica. No hubo cambios en Observador.

Solc 0.8.27 con checksum fijado compila 11578 bytes sin diagnósticos; una segunda
compilación fresca reproduce output y stderr completos. En desarrollo se retienen:
una extracción rechazada por el formato multilínea original de la bonificación,
un error de ownership Rust en una aserción, una expectativa incorrecta sobre el
número de selectores (las constantes públicas también generan getters) y un caso
que confundía colateral seleccionado con agregado. Se corrigieron envoltura,
pruebas y datos sintéticos, sin modificar fuentes originales ni suprimir controles.
Python y Clippy pasan en su primer intento; todos los fallos anteriores permanecen
en development/ y la suite Rust enfocada corregida pasa.

El cierre agrega solo documentación y evidencia. Los inputs auditados permanecen
idénticos. Evidencia: `evidence/aave-sizing-execution-20261023/verification.json`.
Reproducción: [aave-sizing-execution.md](aave-sizing-execution.md).

## Límites y continuidad

Confianza alta dentro del alcance artificial probado. Pendientes: GenericLogic
para salud agregada/eMode, lecturas y autenticación de oráculos, mismo activo,
deuda incobrable multirreserva, entrada real del Pool, diferencias de metadata
WETH/USDC y preestado histórico autenticado bajo su fork. El sandbox usa Cancun.
No se certifican liquidación histórica completa, rentabilidad, Foundry fuzzing ni
salida operacional de fase. No se suman puntos a 43/100.

Titan sigue siendo la única fuente admisible de gas: cero gas propio/fallback,
principal, colateral, garantías o recurso al operador. Los balances simulados no
acreditan financiación ni compromiso de patrocinio. No hubo firma, broadcast,
despliegue, activación o gasto.
