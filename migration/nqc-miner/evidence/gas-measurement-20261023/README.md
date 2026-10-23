# Medición de gas — 23 de octubre de 2026

`blockscout-input.json` retiene los seis `structuredContent` recibidos por el
conector: tres consultas de transacciones y tres de sus bloques, con sus
parámetros públicos. Son lecturas auxiliares nuevas sobre **los mismos tres
eventos** de `public-capture-v2-20261022`; no se añaden liquidaciones al conteo.

| Transacción (prefijo) | Bloque | Gas | Comisión de ejecución (wei) | Estado |
|---|---:|---:|---:|---|
| `0x0f41c414` | 26248076 | 615980 | 95545794283100 | Auxiliar medida |
| `0xb6eeb0b8` | 26248114 | desconocido | desconocido | Falta pertenencia en respuesta parcial |
| `0xeb7833ab` | 26248379 | 587161 | 181924692449274 | Auxiliar medida |

Agregado de las **dos transacciones medidas**: 277470486732374 wei. No es coste
total de la muestra, coste por liquidación ni rendimiento del Miner. Las dos
prioridades observadas son cero; los pagos directos al constructor son desconocidos.

Cada respuesta de bloque incluyó solo 50 hashes, frente a totales declarados de
291, 440 y 221. Las transacciones en posiciones 3 y 2 están presentes. La de
posición 328 no aparece. La ausencia en esa página no implica que no esté en el
bloque, y el módulo conserva su coste como `null`.

Intento complementario de página de transacciones desde índice 327: el conector
rechazó la respuesta de 148219 caracteres por su límite de 100000. La alternativa
REST documentada devolvió HTTP 403. La consulta de logs devolvió solo índices
909–918, con paginación pendiente: no alcanzó la liquidación 922. Se agotaron
las ocho llamadas de la sesión gratuita. Esos intentos no acreditan pertenencia,
ni se reconstruye una respuesta faltante. No se solicitaron suscripciones ni
credenciales nuevas. Las limitaciones no bloquean el trabajo offline.

`result/` es la salida reproducible del módulo y contiene las copias verificadas
del journal, configuración y owner originales. `verification.json` y
`python-tests.log` documentan las pruebas del código y la auditoría de hashes.
No hay precios históricos, elegibilidad, trazas de pagos directos, nuevo quorum
RPC, certificación económica ni salida de fase. Avance global: **43/100**.
