# Auditoría: ejecución con proxy Aave verificado

23 de octubre de 2026. Avance ponderado: **43/100**.

La prueba conjunta de deuda, token y tasas ya puede ejecutar el proxy desplegado
real de la familia usada por USDC y WETH. Se recompilaron las fuentes originales
con solc 0.8.10 fijado por checksum. Los 2400 bytes resultantes, incluidos metadata
y los seis lugares del administrador inmutable, coinciden con diez observaciones
históricas de seis proxies. Se contrastan veinte respuestas de código y veinte de
slot provenientes de los dos proveedores ya retenidos.

La segunda familia de dos proxies queda excluida: la consulta de fuentes respondió
404. El primer host del compilador respondió 403; la copia oficial de solc-bin en
GitHub pasó el mismo checksum publicado. Tres compilaciones dieron salidas idénticas.
No se añadieron estados, eventos ni consultas RPC históricas.

## Qué quedó comprobado

El proxy lee su slot ERC-1967 y delega en la implementación real. La composición
compara diez resultados, todos los eventos ordenados y todos los cambios de storage
contra aritmética independiente en 600 casos con semilla fija. Los fallos de token,
recompensas y etapas posteriores revierten todos los cambios de contratos.

En estados sintéticos separados, las diez observaciones de código/slot ejecutan
los getters de administrador, implementación y suministro. Este último usa el
código real de aToken o deuda. Las rutas de administrador, rechazo de fallback,
cambio local de implementación, destino sin código, inicialización repetida y
rollback de `upgradeToAndCall` también están cubiertas. El administrador y los
cambios de implementación son exclusivamente modelos locales; no se ejecutó el
contrato administrador desplegado ni una transacción en la red.

Ocho pruebas Rust añadidas contienen 654 intentos: 634 éxitos, 18 reversiones
esperadas y dos rechazos por testigos ausentes. Los 600 casos sembrados están dentro
de esas pruebas. Siete pruebas Python vinculan fuentes, compilador, metadata,
slots y proveedores; rechazan alteraciones y repiten el ejemplo completo por CLI.

La primera ejecución detectó el supuesto incorrecto de usar slot 58 para suministro
del aToken. Su layout real usa 54. Se corrigió la construcción del estado de prueba
para usar cada layout compilado, conservando el fallo y sin fabricar valores cero.

La batería final aprueba **210 pruebas Rust y 300 Python: 510 en total**, sin
fallos ni omisiones. Clippy, formato, identidad de fuente/binario, aislamiento y
alcance también pasan.

Fuente probada: `19f0e23e30845f9790c3ed2a7dc7fdc9063e75a1`.
Base del bundle: `009d8c923633f98fd590394702af10ddf1f8560c`.
La batería final y sus hashes se conservan en
`evidence/aave-token-proxy-execution-20261023/offline/summary.json` y `verification.json`.

## Confianza y pendientes

Confianza alta en la identidad de esta familia y en los comportamientos ejecutados.
El estado, entrada del Pool, recompensas y cuentas de prueba siguen siendo sintéticos.
Compilar para Berlin y ejecutar en Cancun no certifica el fork histórico real.
Faltan la otra familia de proxies, administrador y recompensas reales, balances y
parámetros autenticados, transferencias de aToken y activo subyacente, salud/eMode,
deuda multirreserva y estado intrabloque para completar la liquidación.

El gas del ejemplo mide únicamente el harness. No prueba rentabilidad ni elegibilidad
histórica. Observer y la evidencia anterior permanecen intactos. No se habilitaron
workflows, despliegues, firmas, envíos de transacciones ni gasto. Este bloque no
cierra una fase operativa ni añade puntos al avance global.
