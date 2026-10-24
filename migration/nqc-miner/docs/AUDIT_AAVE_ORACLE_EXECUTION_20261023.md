# Auditoría: AaveOracle observado integrado con fuentes de precio simuladas

23 de octubre de 2026, America/Mexico_City. Avance global **43/100**, sin crédito
adicional de fase.

La composición ejecuta ahora el código histórico de AaveOracle en
`0x54586be62e3c3580375ae3723c145253060ca0c2`, sustituyendo el oráculo simulado
anterior. Sus 3405 bytes coinciden íntegramente, incluida metadata, con la
recompilación de las siete fuentes publicadas sin cambios. Se conserva Solidity
0.8.10, objetivo Berlin, optimizer 100000 y todos los ajustes originales; solo
se rellenan seis posiciones inmutables declaradas por el compilador.

**Las fuentes y el oráculo de respaldo siguen siendo dobles de prueba.** Se
suministran respuestas y estado artificiales, mientras AaveOracle ejecuta su
lógica real de enrutamiento. No se ha ejecutado aún el código observado de los
adaptadores/feeds/aggregators ni autenticado rondas, frescura o preestado histórico.
No se atribuye al conjunto una liquidación real ni financiación verificada.

## Observaciones públicas y resultado local

Una captura acotada de 144 consultas de lectura cubre los bloques 26248075,
26248113 y 26248378 mediante dos proveedores. Comprueba cadena, finalización y
cabeceras antes/después, y usa pins EIP-1898 de hash canónico para código, storage
y llamadas. Se conservan y reproducen exactamente las respuestas y su secuencia.
No se añaden eventos de liquidación; son nuevas lecturas de los bloques anteriores.

Ambos proveedores coinciden en código, inmutables, fuentes, precios positivos y
fallback cero. El código del oráculo recompilado coincide en las seis comparaciones
proveedor/bloque, incluida metadata, y con el bytecode publicado. El proveedor
Aave apunta al mismo oráculo. Base USD cero, unidad 100000000. Fuentes observadas:
USDC `0x3f73f03aa83b2a48ed27e964ed0fdb590332095b` y WETH
`0x5424384b256154046e9667ddfaaa5e550145215e`. Sus códigos completos se retienen,
pero en la composición se sustituyen explícitamente por dobles.

USDC devuelve 99983478 en los tres bloques; WETH 240275000000 en el primero y
240029113527 en los dos siguientes. Cada precio del oráculo coincide con la
respuesta positiva de su fuente. No se comprobó frescura, prueba Merkle/canónica
ni frontera intrabloque. Los precios públicos no se presentan como el estado
artificial usado para la liquidación.

La muestra local mantiene salud 751807228915662650, pago 40, colateral al liquidador
41 y comisión 1, usando decimales cero y respuestas artificiales de 100000000000.
Las 47 palabras, todos los eventos y cambios de storage coinciden con la composición
previa. aToken: 19 eventos/45 slots; WETH: 16/46. Gas 1076591/1084128 describe solo
estas envolturas y no estima ejecución productiva ni cobertura de Titan.

## Pruebas e identidad

Fuente probada: `dfc8ffea467c2c373f66a7d624126e6503351576`.
Árbol: `1bb47029c3bfb4a6f18f9783ce8311132aef98b8`.
Base anterior: `760ade7c6bff6d5fe779646feed418b5dd16527d`.

**698 pruebas distintas aprobadas: 298 Rust y 400 Python**, incluidas 7 Rust y
12 Python nuevas. Los 24 conjuntos con semilla se ejecutan en ambas rutas; esas
48 invocaciones principales y sus referencias no inflan el conteo de pruebas.

Se cubren moneda base, respuesta positiva máxima int256, cero, negativos y mínimo
int256, fuente ausente, fallback válido/revertido/cero, respuesta malformada,
testigos ausentes y fallo tardío USDC. Una respuesta positiva no necesita leer
fallback. Un revert o respuesta malformada de la fuente no se recupera mediante
fallback: el contrato propaga el fallo. Todas las rutas conservan reversión
completa de reservas, copias, transferencias y eventos. El fallback de precios
no modifica la prohibición de fallback de gas propio.

Python comprueba alcance de solicitudes, reproducción de captura, manipulación
semántica incluso recalculando hashes de archivo, fuentes/ajustes/selectores,
rangos inmutables, metadata y límites explícitos. Los ejemplos completos y las
rutas positivas/negativas se reproducen por la CLI real. Ambos compiladores se
reconstruyen desde cero con output/stderr idénticos; la envoltura mide 16886 bytes.

El primer intento exploratorio de solc 0.8.10 rechazó `--no-import-callback`, opción
no disponible en esa versión. Se retiene su stderr y se usa `--standard-json` en
un directorio temporal vacío con todas las dependencias literales. No se modifica
una fuente ni se elimina metadata. Captura completa, compilación corregida, Rust,
Python y Clippy pasan desde su primer intento registrado de este incremento.

La suite completa pasa a la primera sobre fuente limpia, sin fallos ni omisiones,
incluidos build offline, Clippy con warnings denegados, formato, identidad, alcance
y aislamiento. Se preservan 531 fuentes originales, 106 workflows deshabilitados
y cero activos. El verificador no comprobó objetos Git originales ni otorgó
recertificación canónica. Observador permanece intacto.

El cierre agrega solo documentación/evidencia; los inputs auditados no cambian.
Evidencia: `evidence/aave-oracle-execution-20261023/verification.json`.
Reproducción y tablas: [aave-oracle-execution.md](aave-oracle-execution.md).

## Continuidad

Confianza alta dentro del alcance observado y artificial probado. Siguiente trabajo:
verificar y ejecutar adaptadores/feeds/proxies/aggregators, autenticar estado fresco
de precios, ampliar reservas, cubrir mismo activo/multirreserva, entrada Pool real,
metadata WETH/USDC y preestado de transacción autenticado bajo su fork. El sandbox
usa Cancun. No se certifican liquidación histórica completa, rentabilidad,
Foundry fuzzing ni salida operacional. El avance permanece en 43/100.

Titan sigue siendo la única fuente admisible de gas: cero gas propio/fallback,
principal, colateral, garantías o recurso al operador. La simulación no acredita
financiación ni patrocinio. No hubo firma, broadcast, despliegue, activación o gasto.
