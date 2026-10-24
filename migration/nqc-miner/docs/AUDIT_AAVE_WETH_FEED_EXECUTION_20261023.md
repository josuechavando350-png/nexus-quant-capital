# Auditoría: proxy real de la fuente WETH y conservación del llamante

23 de octubre de 2026, America/Mexico_City. Avance global **43/100** sin crédito
adicional de fase. Confianza alta dentro del alcance explícito probado.

El código observado de `EACAggregatorProxy` en
`0x5424384b256154046e9667ddfaaa5e550145215e` reemplaza el doble de esa dirección en
la composición Aave. Sus 9571 bytes, incluida metadata, coinciden íntegramente con
la recompilación de siete fuentes publicadas intactas y con dos proveedores en
tres bloques retenidos. Solidity 0.6.6, optimizer 1000000, objetivo Istanbul;
sin sustituciones arbitrarias, recorte de metadata ni cambios de fuente.

El agregado observado es `0x7c7fdfca295a787ded12bb5c1a49a8d2cc20e3f8`, fase 2 y
controlador de acceso cero en las seis observaciones proveedor/bloque. La captura
correcta emite 114 consultas limitadas de lectura, con pins EIP-1898 por hash,
cadena/finalización, cabeceras antes/después y acuerdo entre proveedores. No añade
eventos de liquidación. Sus respuestas y secuencia se reproducen offline.

## Hallazgo y corrección de la captura

El primer intento falló tras 85 consultas al exigir igualdad entre el precio
del proxy y el del agregado consultado directamente. Se conservan el script,
las dos observaciones completas, el contador y la razón del fallo; no hay
observación completa del tercer bloque en ese intento.

El código publicado de `DualAggregator` selecciona rondas por llamante y tiempo.
La captura corregida conserva la consulta directa separadamente y compara el
proxy con una consulta al agregado cuyo `from` es el proxy. En el bloque 26248378,
ambos proveedores devuelven 239563000000 directamente y 240029113527 por el proxy
y con ese llamante. En 26248075 y 26248113 los tres resultados coinciden, con
240275000000 y 240029113527, respectivamente. La captura total emitió **199
consultas**, contando el intento fallido.

Esto evita sustituir indebidamente la ronda del proxy por una lectura directa.
`eth_call` con ese `from` también cambia `tx.origin`: la igualdad observada no
certifica todos los contextos posibles. La fuente del DualAggregator se retiene
solo como investigación; aún no se recompila, ejecuta ni autentica su estado.
Sourcify devolvió 404 para la fuente USDC; se conserva el fallo y sigue pendiente.

## Ejecución local y pruebas

**718 pruebas distintas aprobadas: 307 Rust y 411 Python**, incluidas 9 Rust y
11 Python nuevas. Los 16 conjuntos con semilla se ejecutan en ambas rutas y no
inflan el número de pruebas. Las 47 palabras, todos los eventos y cambios de
storage coinciden con la composición previa y sus modelos independientes.

Se cubren rutas aToken/WETH, fases 0/1/65535, bits altos sin uso, agregado alterno,
respuesta cero/negativa/mínima int256/máxima positiva, acceso permitido y denegado,
identidad de AaveOracle, identidad del proxy, calldata, errores y respuestas
malformadas, testigos faltantes y rollback tardío por USDC. Un doble adicional
devuelve precios diferentes según el llamante: la composición conserva el precio
de la ruta del proxy mientras una consulta directa devuelve otro valor. Este
doble no pretende ejecutar DualAggregator.

El alcance de ejecución del proxy es la ruta `latestAnswer()` y su control de
acceso; no certifica `getRoundData()`, historial de fases, setters, upgrades ni
permisos administrativos. Las consultas de captura no amplían ese alcance.

Los ejemplos mantienen salud 751807228915662650, pago 40, colateral 41 y comisión
1 con precios y decimales artificiales. aToken: 19 eventos/45 slots, gas 1085083;
WETH: 16/46, gas 1092620. Ese gas describe envolturas de prueba y no estima gas
productivo ni cobertura de Titan. La fuente USDC y el agregado WETH continúan
simulados; los slots de ruta observados no autentican el resto del estado.

Ambos perfiles de compilación se repiten con output/stderr idénticos. Los avisos
del compilador histórico sobre las fuentes originales se conservan sin cambiar
esas fuentes. Pruebas enfocadas, Clippy y la primera batería completa pasan.
La batería incluye build offline, Rust/Python, Clippy sin warnings, formato,
identidad exacta, alcance y aislamiento, sin fallos ni omisiones de pruebas.

Fuente probada: `c5612f4552a508b66ccbbd5a46585ddca47e30d2`.
Árbol: `261de6f704d058fa89029b4873768bb935ad0e83`.
Base previa: `e1028bbacd3954162c37bcd85c3dbe2d2638ed41`.

Se preservan 531 fuentes originales, 106 workflows deshabilitados y cero activos.
El verificador no comprobó objetos Git originales ni concedió recertificación
canónica. El cierre solo agrega documentación/evidencia; los inputs auditados
permanecen idénticos. Observador no se modifica.

Evidencia: `evidence/aave-weth-feed-execution-20261023/verification.json`.
Reproducción y detalle: [aave-weth-feed-execution.md](aave-weth-feed-execution.md).

## Pendientes

Ejecutar y autenticar DualAggregator y fuente USDC con sus rondas, cutoff y
llamantes correctos; comprobar frescura y preestado de transacción. Permanecen
abiertos más reservas, mismo activo/multirreserva, entrada Pool real, metadata
WETH/USDC, fork histórico, Foundry e integración operacional. El sandbox usa
Cancun. No se acredita liquidación histórica completa, rentabilidad o salida de
fase. El progreso permanece en **43/100**.

Titan sigue siendo la única fuente admisible de gas: cero gas propio, prefunding,
fallback, principal, colateral, garantías o recurso al operador. No hay patrocinio
autenticado ni autorización de gasto. No hubo firma, broadcast, despliegue,
activación o gasto.
