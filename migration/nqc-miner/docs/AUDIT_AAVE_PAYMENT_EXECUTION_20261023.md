# Auditoría: cobro USDC y reversión después de entregar WETH

23 de octubre de 2026, America/Mexico_City. Avance global: **43/100**, sin crédito
adicional de fase. La verificación terminó el 24 de octubre a las 00:55 UTC.

El experimento ahora ejecuta el cobro de deuda mediante el `safeTransferFrom`
original de Aave y emite su `LiquidationCall`, después de quemar deuda, actualizar
tasas y recompensas, entregar WETH y transferir la comisión. Se ejecutan completos
el proxy y la implementación observados de USDC. Entrada del Pool, saldos,
autorizaciones, índices y parámetros siguen siendo artificiales.

La muestra conserva 27 palabras de resultado, 16 eventos ordenados y 24 cambios
de almacenamiento, comprobados contra expectativas independientes. Al pagar 40,
el saldo USDC del liquidador pasa de 100 a 60, el destino aUSDC de 200 a 240 y la
autorización de 100 a 60. Incluso la autorización máxima se reduce. El gas 482588
es una medición exclusiva de esta envoltura artificial, sin certificación de costo
de una liquidación real ni compromiso de pago de Titan.

## Identidad y evidencia

Fuente probada: `addc0eef8a890e6a99d151a96fce0357bdab4558`.
Árbol: `9d04099b3432571ac5a95dc0a59f86e37332c0b4`.
Base previa: `e1c2e45a3f2b03ac26ebeda241f5ab5526704759`.
Build limpio, Rust 1.90.0, perfil debug; identidad de build
`d107b489ee9f6922821cdcaa27605b844cff53d3a85e3865c8f5c4552a0e7505`.

La captura nueva contiene **84 solicitudes RPC de solo lectura** a Blast y dRPC
en tres bloques históricos. Ambos coinciden en código completo del proxy y de su
implementación, sus slots de implementación/administrador y el activo de aUSDC.
Los pins son hashes canónicos; se comprueban cadena, finalidad y encabezados
repetidos. No se agregaron eventos de liquidación ni saldos históricos. El acuerdo
de proveedores no autentica raíces de estado ni preestado de transacción.

Solc 0.4.24 y 0.6.12, con checksum fijado, compilan las fuentes originales de
Sourcify sin repararlas. Coinciden los prefijos ejecutables de 2143 y 23411 bytes,
pero difieren 32 bytes de hash de metadata en cada runtime. Se preservan ambos
resultados y se ejecutan todos los bytes observados. La igualdad completa
fuente/runtime continúa en false para USDC; también sigue abierta la diferencia
WETH. No se parcheó salida del compilador. Una recompilación fresca de los tres
perfiles, incluida la envoltura Aave con solc 0.8.27, reproduce salidas idénticas.

## Pruebas y fallos conservados

**614 pruebas distintas aprobadas: 259 Rust y 355 Python**, incluidas 10 Rust y
15 Python nuevas. No se cuentan como pruebas adicionales los 120 casos internos
de composición con semilla ni sus ejecuciones de referencia. El runner completo
aprueba a la primera sobre la fuente fijada: build offline, Clippy con warnings
denegados, formato, identidad, alcance y aislamiento. No hubo fallos u omisiones.
Se conservan 531 fuentes originales y 106 workflows deshabilitados; cero activos.
El verificador no realizó comprobación de objetos Git originales y no se le
atribuye recertificación canónica. Observador permanece intacto.

Saldo/autorización insuficientes, pausa, bloqueo del Pool/liquidador/destino,
desbordamiento del saldo receptor y denegación del fallback al administrador
revierten todos los cambios de contratos y eventos previos, incluida la entrega
de WETH. Faltantes de código, routing o slots fallan cerrados. Tokens artificiales
de inyección de fallos prueban respuestas false, malformadas y ausencia de código;
no se presentan como USDC observado. La CLI reproduce exactamente la muestra.

Los intentos de desarrollo permanecen en `development/`: el primer generador no
resolvió las comillas/rutas de importación originales, y el primer build Rust
detectó un préstamo de valor parcialmente movido en el test. Ambos se corrigieron.
Una ejecución dirigida encontró que pagar una unidad produce quema escalada cero
y revierte en el contrato original. El generador de casos exitosos ahora empieza
en dos; una prueba adicional exige explícitamente ese rechazo y rollback. La
ejecución dirigida siguiente aprueba las diez pruebas. No se alteró código
original para hacer pasar ningún caso.

`evidence/aave-payment-execution-20261023/verification.json` vincula el runner
completo, sus hashes, compiladores, captura y muestra. El commit de cierre agrega
solo documentación y evidencia; los inputs auditados permanecen idénticos.

## Límites y continuidad

Confianza alta en el comportamiento probado dentro del estado artificial. Sigue
pendiente extender el pago a receive-aToken, componer validaciones y actualizaciones
iniciales, salud/eMode, mismo activo y deuda incobrable de múltiples reservas,
ejecutar la entrada real del Pool y autenticar el preestado histórico bajo su fork.
El sandbox usa Cancun. No se declara liquidación histórica completa, elegibilidad,
Foundry fuzzing, rentabilidad ni salida operacional de fase.

Se mantiene la política de gas exclusiva de Titan, sin gas propio/fallback,
principal, colateral ni garantías del operador. El patrocinio y la financiación
de principal no están acreditados por balances simulados. No hubo firma,
transmisión de transacciones, despliegue, activación ni gasto. Reproducción y
alcance detallados en [aave-payment-execution.md](aave-payment-execution.md).
