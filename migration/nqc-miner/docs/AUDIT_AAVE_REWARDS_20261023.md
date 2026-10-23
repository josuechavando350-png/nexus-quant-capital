# Auditoría: recompensas reales y ambas familias de proxies

23 de octubre de 2026. Avance ponderado: **43/100**.

La composición de deuda ahora ejecuta el proxy real de recompensas y los 18645
bytes de `RewardsController`, sustituyendo la sonda artificial de los experimentos
anteriores. La implementación se comprobó en los mismos tres bloques históricos
mediante una captura nueva de 72 solicitudes a dos proveedores. También se cerró
la identidad de la segunda familia de proxies: los ocho proxies de tokens de la
muestra, en doce observaciones, tienen cobertura de recompilación completa.

## Evidencia concreta

Las fuentes originales del proxy y controlador de recompensas se recompilan con
solc 0.8.10; las del proxy de 1853 bytes, con solc 0.8.22. Los compiladores están
fijados por checksum al índice oficial retenido. No se modificaron fuentes,
optimizador, objetivo EVM ni política de metadata. Sólo se ampliaron las salidas
del compilador y se rellenaron los lugares de inmutables declarados por éste.
Dos ejecuciones por perfil produjeron salidas idénticas.

Las comparaciones nuevas cubren doce respuestas de código de recompensas y cuatro
de la segunda familia, incluyendo metadata. Los slots de implementación y sus
bloques también se verifican. No se agregaron eventos históricos a los tres ya
retenidos ni se alteraron los 48 estados de posiciones/precios anteriores.

PublicNode no conservaba el estado más antiguo solicitado y la captura inicial
falló. Se retuvo ese fallo junto con el diagnóstico. La captura completa reinicia
desde la primera solicitud con Blast y dRPC; no mezcla respuestas de intentos.
Las fuentes de la segunda familia se recuperaron del explorador tras los errores
404 de Sourcify y 403 de Blockscout. Los scripts de la página nunca se ejecutan.

## Ejecución comprobada

El token pasa a recompensas el saldo y suministro previos a la quema. En el ejemplo,
son 100 y 1000; con seis decimales, emisión 100 y 100 segundos transcurridos, el
índice sube de 1000000 a 11000000 y se acumulan 1010 unidades nuevas para el usuario.
El acumulado almacenado pasa de 7 a 1017. Coinciden diez resultados de deuda,
cuatro eventos ordenados y todos los cambios de storage: cinco slots del Pool,
dos del token y dos de recompensas.

Ocho pruebas Rust añadidas incluyen 400 casos con semilla fija. Cada caso ejecuta
también la referencia anterior de deuda/token/tasas, ya contrastada con aritmética
independiente; las recompensas se calculan con un modelo entero independiente.
Se cubren distribuciones vacías y múltiples, vencimiento, emisión cero, redondeos,
suministro y saldo cero en llamadas aisladas, límites de índice/acumulado/tiempo,
slots ausentes y fallos después de acumular la primera recompensa. Los errores
posteriores deben revertir conjuntamente todos los cambios y logs.

Catorce pruebas Python verifican fuentes, perfiles, runtime completo, metadata,
layouts y reproducción CLI. Capturas alteradas y nuevamente hasheadas se rechazan
por identidad, secuencia, proveedor, bloque, finalización y desacuerdo de respuestas.

Verificación completa: **218 pruebas Rust y 314 Python, 532 en total**, sin fallos
ni pruebas omitidas. También pasan Clippy con warnings denegados, formato, identidad
de build, alcance e aislamiento. Las 22 pruebas nuevas están incluidas en ese total.

Fuente probada: `35dbcbe891f7199e29770b55dde0414057cf1a1e`.
Base del bundle: `c8134f4a448f22f55f7829ae89722e59e219185a`.
La batería final y sus hashes quedan en `evidence/aave-rewards-20261023/offline/summary.json`
y `evidence/aave-rewards-20261023/verification.json`.

## Confianza y pendientes

Confianza alta en la equivalencia de runtime dentro de los bloques observados y
en los comportamientos ejecutados. Los balances, parámetros de recompensas y
entrada del Pool siguen siendo sintéticos. La captura comprueba acuerdo de código
y slots, sin autenticar una raíz de estado ni reconstruir el estado de transacción.
El sandbox usa Cancun; no certifica el fork histórico.

Faltan transferencias reales de aToken y activo subyacente, salud/eMode, deuda
multirreserva, recompensas históricas autenticadas y estado intrabloque para cerrar
la liquidación. Reclamar recompensas, ejecutar estrategias de transferencia y el
contrato administrador desplegado siguen fuera del alcance de estas pruebas.
El gas 209080 del ejemplo corresponde únicamente al harness y no prueba ganancia.

Observer y la evidencia anterior permanecen intactos. No se activaron workflows,
despliegues, firmas, transacciones, gasto ni notificaciones. Este bloque no cierra
una fase operativa y no añade puntos al avance global.
