# Auditoría: DualAggregator real y selección de rondas

23 de octubre de 2026, America/Mexico_City. Avance **43/100**, sin crédito adicional
de fase. Confianza alta dentro del alcance ejecutado y observado que se describe.

La ruta WETH ejecuta AaveOracle, EACAggregatorProxy y DualAggregator observados.
El agregado `0x7c7fdfca295a787ded12bb5c1a49a8d2cc20e3f8` reemplaza el doble previo.
Sus **23186 bytes completos** coinciden con la recompilación de 23 fuentes
literales intactas, el bytecode publicado y dos proveedores en tres bloques.
Solidity 0.8.24, optimizer 1000000, Cancun; diez posiciones de cinco inmutables
se rellenan únicamente en rangos declarados por el compilador. Los valores
repetidos y getters deben coincidir. Sin parches de fuente o recortes de runtime.

La metadata se compara, pero el ajuste original es `bytecodeHash: none`:
**no autentica el texto original de las fuentes**. Equivalencia completa de
runtime tampoco es una prueba canónica de código o storage.

## Observaciones y ejecución

Una captura completa de **222 lecturas RPC** por hash EIP-1898 cubre código,
inmutables públicos, hot vars, cutoff, ronda actual para ambos llamantes y veinte
slots de transmisiones por bloque/proveedor. Verifica cadena/finalización,
cabeceras antes/después, IDs y acuerdo entre proveedores. Se reproduce offline.
No agrega eventos de liquidación ni autentica el preestado de una transacción.

El primer lote HTTP de cuatro solicitudes JSON-RPC devolvió HTTP 500. Se retiene
su script, contador y fallo. El segundo intento usa solicitudes individuales,
máximo cuatro conexiones y separación de inicio de al menos 125 ms; completa
las 222 lecturas. Total enviado: 226 solicitudes JSON-RPC en 223 HTTP; las cuatro
iniciales no tuvieron respuestas individuales ni se presume que se ejecutaron.

En 26248075 se selecciona la ronda 25161, precio 240275000000. En 26248113,
25162 y 240029113527. En 26248378, la consulta directa devuelve 25163 y
239563000000, mientras el proxy devuelve 25162 y 240029113527. El cutoff es 60:
la ronda 25163 se registró en el mismo timestamp del tercer bloque y la búsqueda
del proxy selecciona la anterior. Se conservan los slots completos y los cinco
campos de `latestRoundData()`.

**Nueve lecturas locales** reproducen en los tres bloques la consulta directa,
la consulta al proxy con fase y el precio WETH vía AaveOracle. Usan los slots y
timestamp observados, dentro de un entorno `synthetic_fixture`; state root,
balances/nonce, tarifas y fork no están autenticados. No es una reconstrucción
de una liquidación histórica completa. Cancun continúa siendo el fork del sandbox.

El cutoff es selección de ronda, **no una política de frescura**. Puede devolver
una respuesta antigua. No se certifica el origen del reporte, ni firmas OCR,
publicación, billing, administradores, upgrades o historial de rondas.

## Verificación exacta

**740 pruebas distintas aprobadas: 317 Rust y 423 Python**, incluidas 10 Rust y
12 Python nuevas. Dieciséis conjuntos con semilla se ejecutan en ambas rutas,
sin inflar el conteo. Las 47 palabras de salida, eventos y cambios de storage
coinciden con la composición previa y sus modelos independientes.

Se cubren cutoff -1/igualdad/+1, primera/vigésima ronda, exclusión de la vigésima
primera sin testigo, búsqueda sin coincidencia y ronda cero; filtro primario en
el mismo bloque; int192 mínimo/máximo, cero y negativos con fallback; overflow
uint32; estado ausente; denegación de acceso y rollback tardío USDC. La rama
primaria también funciona sin testigos de cutoff/secundaria que no necesita.

Las claves de storage calculadas con Keccak Ethereum se contrastan con Alloy
en 37 vectores y en todas las claves de la muestra. Python valida alcance y
límites de requests, normalización de respuestas, manipulación de captura aun
reescribiendo hashes, metadata/inmutables/layout, fixture completo y CLI real.

Ejemplos artificiales de liquidación: pago 40, colateral 41, comisión 1 y salud
751807228915662650. aToken: 19 eventos/45 slots, gas 1088585; WETH: 16/46,
gas 1096122. Este gas mide envolturas de prueba, no producción ni cobertura Titan.
La fuente USDC y los precios/reservas de esos ejemplos siguen suministrados.

La compilación repetida produce output/stderr idénticos. Pruebas enfocadas,
Clippy y la primera batería completa pasan. El runner verifica build offline,
Rust/Python, Clippy sin warnings, formato, identidad, alcance y aislamiento;
sin fallos ni omisiones. Se preservan 531 fuentes originales, 106 workflows
deshabilitados y cero activos. No comprueba objetos Git originales ni concede
recertificación canónica. Observador permanece intacto.

Fuente probada: `8aeee0ddde196989bf9e2d5b0f0202695ac34695`.
Árbol: `af2c6032f828eeb26c940a7b635fe42af0d0c502`.
Base previa: `65dac3ff0ec544fbe84e11aabfe3d6ca6b6d271e`.

El cierre solo añade documentación/evidencia y conserva los inputs auditados.
Evidencia: `evidence/aave-dual-aggregator-execution-20261023/verification.json`.
[Alcance y reproducción](aave-dual-aggregator-execution.md).

## Continuidad

Sustituir la fuente USDC; autenticar estado de rondas, preestado de transacción y
fork; definir y verificar frescura. Permanecen abiertos entrada Pool real, más
reservas, mismo activo/multirreserva, metadata de tokens WETH/USDC, Foundry e
integración operacional. No hay certificación económica ni salida de fase:
**43/100** permanece sin crédito adicional.

Gas exclusivo de Titan: cero gas propio, prefund/fallback, principal, colateral,
garantías o recurso al operador. No se acredita patrocinio específico. Sin
firma, broadcast, despliegue, activación ni gasto.
