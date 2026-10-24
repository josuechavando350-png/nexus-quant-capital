# Auditoría: quema de colateral y transferencia de WETH

23 de octubre de 2026. Avance global: **43/100**, sin puntos adicionales.

La función original de quema de colateral ahora se ejecuta junto con la quema de
deuda, las tasas, recompensas y comisión final. El aToken quema unidades escaladas
y llama a WETH para enviar el activo al liquidador. La comisión usa el saldo real
resultante dentro de la simulación. La entrada del Pool y todos los balances,
índices, parámetros y cantidades suministradas siguen siendo sintéticos.

La captura nueva contiene 66 solicitudes de sólo lectura con dos proveedores en
los tres bloques retenidos. Ambos coinciden en el código completo de WETH y el slot
61 de aWETH que identifica ese subyacente. Los hashes de bloque fijan las lecturas;
se comprueban cadena, finalización, secuencia y cabeceras repetidas. No se agregan
eventos de liquidación ni balances históricos y no se autentica una raíz de estado.

## Diferencia de metadata conservada

El solc 0.4.19 fijado por checksum recompila las fuentes originales de WETH sin
modificarlas. Coinciden los 3081 bytes del prefijo ejecutable, pero difieren 32 bytes
del hash bzzr0 de metadata, offsets 3090–3121. Por ello la coincidencia completa de
fuente/runtime sigue siendo **falsa**. El experimento ejecuta los 3124 bytes completos
observados, incluido su footer original; no se parchea la salida del compilador.
Esta diferencia está fijada en tests, fixture y auditoría y permanece como pendiente.

El harness de 6663 bytes usa la estructura original y ambas funciones internas
originales de LiquidationLogic. Mantiene los fragmentos exactos de consumo/flag y
comisión. Tres ejecuciones de cada perfil de compilación producen salidas idénticas.
El compilador antiguo no ofrece storageLayout: el orden/tipos del AST y las llamadas
reales a getters/transferencias sustentan el mapping de WETH, explícitamente etiquetado
como inferencia y no como layout emitido por solc.

## Comportamiento comprobado

En el ejemplo, los saldos escalados de aToken 100/20/7 pasan a 66/20/14 y el suministro
baja de 1000 a 973. El WETH del depósito/liquidador pasa de 1000/13 a 960/53; la liquidez
virtual de colateral baja a 960. Coinciden 24 resultados, 14 eventos ordenados y
los 21 slots modificados. El gas 439195 sólo corresponde al harness artificial.

Ocho pruebas Rust incluyen 240 casos con semilla, cada uno acompañado por las dos
referencias previas de deuda/token/tasas y recompensas con aritmética independiente.
Se prueban intereses que producen Mint durante una quema, agotamiento, fee cero y
capado, tesorería como receptor, varias distribuciones y extremos de liquidez.
Doce pruebas Python verifican procedencia, código/metadata, captura, AST y CLI.

Saldo WETH insuficiente, fallos de reserva, quema cero y desbordes tardíos deben
revertir deuda, tasas, flags, aTokens, WETH, recompensas y logs anteriores. Testigos
faltantes detienen la ejecución. Un estado artificial con receptor uint256 máximo
confirma el wrapping aritmético antiguo de WETH; no se presenta como estado respaldado
naturalmente ni como oportunidad económica. Las pruebas dirigidas no tuvieron fallos.

La batería completa terminó con **234 pruebas Rust y 334 Python: 568 aprobadas**,
sin fallos finales ni pruebas omitidas. También pasan Clippy, formato, identidad
de build, alcance e aislamiento. Las 20 pruebas nuevas están incluidas en ese total.

Fuente probada: `4bfae245e78ce99d37131198275867d5a3f04302`.
Base del bundle: `2955dbbce58d7d74df4a6c4eaa79188e3285cb04`.

Confianza alta en los comportamientos ejecutados dentro del alcance descrito. Faltan
cobro de deuda, actualizaciones/validaciones iniciales, salud/eMode, mismo activo,
deuda multirreserva y entrada real del Pool con estado histórico autenticado y fork
correcto. Se conserva Cancun en el sandbox. La metadata de WETH también queda abierta.
No hay certificación de liquidación histórica, rentabilidad ni cierre de fase operativa.
Observer y evidencia anterior intactos; sin firmas, transacciones, despliegues ni gasto.
