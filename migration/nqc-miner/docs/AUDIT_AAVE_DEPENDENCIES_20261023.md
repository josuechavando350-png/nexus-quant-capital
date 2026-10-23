# Auditoría: implementaciones históricas de tokens y tasas Aave

Fecha: 23 de octubre de 2026. Avance ponderado: **43/100**.

Se identificaron y recompilaron las implementaciones reales de aToken, deuda
variable y estrategia de tasas presentes en los tres bloques ya auditados.
Las **30 comparaciones de runtime** con dos proveedores coinciden byte por byte,
incluidos los metadatos. Esto permite trabajar sobre esas fuentes concretas;
todavía no sustituye las respuestas simuladas de los modelos anteriores.

## Alcance comprobado

- Tres bloques: 26248075, 26248113 y 26248378, fijados por sus hashes originales.
- Ocho proxies distintos de token; doce observaciones de proxy y tres de la
  estrategia, derivadas de las reservas de las mismas tres liquidaciones.
- 132 consultas públicas de solo lectura, con comprobaciones de red, finalización
  y cabeceras antes/después de las lecturas y al finalizar ambos proveedores.
- ATokenInstance: 10477 bytes, solc 0.8.27, implementación
  `0xadc45df3cf1584624c97338bef33363bf5b97ada`.
- VariableDebtTokenInstance: 7198 bytes, solc 0.8.27, implementación
  `0xb27c52c7f84819e3157993489741cb60786ae330`.
- DefaultReserveInterestRateStrategyV2: 4038 bytes, solc 0.8.20, dirección
  `0x9ec6f08190dea04a54f8afc53db96134e5e3fdfb`.

Las fuentes y ajustes originales de Sourcify quedan guardados. Los compiladores
se verifican contra el índice oficial retenido. Se comprueba que todos los
imports pertenecen al conjunto de fuentes suministrado y se compila en un
directorio vacío. Solo se añade la selección de salidas. Una segunda compilación
reprodujo exactamente todos los archivos de entrada, salida y stderr.

Las sustituciones de despliegue se restringen a los offsets de inmutables que
emite el compilador, identificados mediante su AST. Se fijan Pool, proveedor de
direcciones, chain ID, tesorería y controlador de recompensas. No se eliminan
metadatos ni se aceptan regiones arbitrarias de bytes diferentes.

## Validación y trazabilidad

**194 pruebas Rust y 289 Python: 483 en total**, aprobadas sin fallos ni omitidas.
Las doce pruebas nuevas incluyen alteraciones de cada respuesta de código,
metadatos, compilador, fuentes, inmutables, slots, cabeceras y finalización;
también rechazan llamadas mutables o sin bloque fijado y capturas modificadas
aunque se recalculen sus hashes. Clippy, formato, alcance, aislamiento e identidad
del binario pasan.

Fuente comprobada: `421f7f236d5523dd8f279e4759b71336e6c34557`,
`source_dirty=false`. El bundle requiere
`550963b88ca120adc19dcdeef2fbfe2fc9093340`. Los logs, hashes y documentación
quedan vinculados en `evidence/aave-dependencies-20261023/verification.json`.
Se preservan 531 archivos originales, 106 workflows deshabilitados y cero activos.

La primera captura falló por HTTP 408 y se conserva aparte; el segundo intento
completo no mezcla respuestas del primero. Las correcciones preliminares de la
opción no admitida por solc 0.8.20 y de perfiles incompletos de inmutables están
registradas. Un filtro de pruebas sin coincidencias no se contabiliza como pase.
La sesión Blockscout no admitió consultas; no se crearon credenciales ni
suscripciones y se usaron los proveedores públicos establecidos del proyecto.

## Límites y siguiente trabajo

El código revela llamadas al controlador de recompensas durante operaciones de
saldo. Su dirección queda identificada, pero su código, estado y comportamiento
siguen pendientes. También faltan la semántica del proxy, transferencias del activo
subyacente, parámetros históricos de tasas y balances autenticados. La igualdad
de runtime no prueba autenticidad criptográfica de estado ni unicidad del texto
fuente original.

La siguiente etapa es ejecutar las dependencias reales y sus callbacks, componer
los modelos parciales, cubrir deuda multirreserva y salud/eMode, y reconstruir el
estado anterior a cada transacción bajo el fork histórico correcto. No se declara
una liquidación completa, rentabilidad, Foundry fuzzing ni build hermético.

No se añaden eventos históricos ni puntos operativos. Observer sigue intacto;
no se habilitan firma, envío de transacciones, despliegue, workflows ni gasto.
