# Auditoría: salud original, eMode y llamadas al oráculo dentro de la liquidación

23 de octubre de 2026, America/Mexico_City. Avance global **43/100**, sin crédito
adicional de fase.

GenericLogic.calculateUserAccountData original se ejecuta después de actualizar
las dos reservas y antes de validar la liquidación. Deriva colateral agregado,
deuda agregada y salud desde saldos escalados leídos mediante código observado,
índices actualizados, configuración y precios. La selección original eMode y las
llamadas de precio alimentan después los importes, quema, ambas entregas, comisión
y cobro USDC. La ABI ya no recibe salud, totales agregados ni precios como argumentos.

**El oráculo es explícitamente sintético.** Los precios se suministran en su
storage; no se ha autenticado AaveOracle, Chainlink, frescura ni estado histórico
de precios. Categoría/eMode, todos los balances y la entrada Pool siguen siendo
artificiales. Se ejercitan deuda USDC y colateral WETH con huecos explícitos en la
lista; no se certifican reservas adicionales arbitrarias ni papeles invertidos.

## Resultado

La muestra deriva deuda/colateral seleccionados de 166/156, totales de
16600000000000/15600000000000 y salud 751807228915662650 con umbral 8000 bps.
La petición de 40 produce deuda pagada 40, colateral entregado 41 y comisión 1;
wallet/vault/allowance quedan en 460/240/460. Son unidades y precios artificiales
con decimales cero, no cantidades económicas reales de Ethereum.

Las 47 palabras, eventos ordenados y todos los cambios de storage coinciden con
expectativas enteras independientes y la composición previa. Los 16 slots nuevos
por defecto son copias instrumentales de reservas actualizadas y lista: no el
layout real del Pool. aToken produce 19 eventos/45 slots; WETH 16 eventos/46 slots.
Gas 1062339/1069876 es diagnóstico de estas envolturas y no un coste operacional.

La selección eMode puede cambiar umbral, bonificación, elegibilidad e importes.
Se ejercitan exclusión de bitmap, isolated y zero-LTV; los promedios LTV/umbral
son descartados por la llamada de liquidación original y no se certifican como
salidas independientes en este incremento.

## Pruebas e identidad

Fuente probada: `2c076e3b5ed68675d0a145e62959df48e7c78426`.
Árbol: `7aa4c0f33335bbf1485f453f91d526be064d74d5`.
Base anterior: `7d6e88ace43d1616d9a58798540d9365d7cf5827`.

**679 pruebas distintas aprobadas: 291 Rust y 388 Python**, incluidas 9 Rust y
8 Python nuevas. Los 32 conjuntos con semilla corren en ambas rutas; sus 64
invocaciones principales y referencias no inflan el conteo de pruebas.

Se comprueban salud calculada exactamente uno y un paso de precio por debajo;
eMode y bonus; flags vacíos, sin deuda y huecos hasta el bit más alto; precios
cero; overflow; respuesta de oráculo malformada; fallo de oráculo antes del
validador; fallo de reserva antes del oráculo; testigos ausentes; y completa
reversión del estado inicial, copias, transferencias y eventos si falla USDC.
Los antiguos campos de salud/totales de la referencia no afectan la ABI nueva.
Python reproduce ambas salidas completas y deriva salud con aritmética entera
independiente a partir de los reportes CLI de reservas.

Build offline, suite completa, Clippy con warnings denegados, formato, identidad,
alcance y aislamiento pasan sobre la fuente limpia fijada. El primer runner
completo pasa, sin fallos ni omisiones. Se mantienen 531 fuentes originales,
106 workflows deshabilitados y cero activos. No se comprobaron objetos Git
originales ni se concedió recertificación canónica. Observador permanece intacto.

Solc 0.8.27 fijado produce 16886 bytes de envoltura y 246 bytes de oráculo de prueba,
sin diagnósticos. Otra compilación fresca reproduce output y stderr completos.
No se modificaron fuentes originales ni ajustes de compilador. El primer caso
Python de eMode falló porque no incluía el storage inicial de categoría 7; se
agregaron los tres slots sintéticos explícitos y se contrastó su clave de mapping
en Rust. El fallo se conserva en development/python-1.txt. No se relajó el
rechazo de datos ausentes. Rust, compilador y Clippy pasan desde su primer intento;
la repetición Python corregida pasa antes de fijar la fuente.

El cierre añade solo documentación y evidencia; inputs auditados idénticos.
Evidencia: `evidence/aave-account-execution-20261023/verification.json`.
Reproducción: [aave-account-execution.md](aave-account-execution.md).

## Continuidad

Confianza alta dentro del alcance artificial probado. Pendientes: código y
estado observados de oráculos/feeds, autenticación/frescura de precios, más
configuraciones de reservas, mismo activo, deuda incobrable multirreserva,
entrada Pool real, metadata WETH/USDC y preestado de transacción autenticado bajo
su fork correcto. El sandbox usa Cancun. No se certifican liquidación histórica
completa, rentabilidad, Foundry fuzzing ni salida operacional. Avance 43/100.

No hubo nuevas consultas RPC públicas, eventos históricos, firma, broadcast,
despliegue, activación ni gasto. Titan sigue siendo la única fuente admisible de
gas: cero gas propio/fallback, principal, colateral, garantías o recurso al
operador. Los balances simulados no acreditan financiación ni patrocinio.
