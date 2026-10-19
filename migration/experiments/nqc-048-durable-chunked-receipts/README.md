# NQC048 — fragmentos durables y recuperación restrictiva

**Fecha:** 19 de octubre de 2026.  
**Base:** NQC047 `aa0d1f7b1d49feb7da0cc6f64f2b4bec8b097ac1`.  
**Rama:** `research/nqc-048-durable-chunked-receipts-20261019`.

Este experimento añade únicamente archivos nuevos. Conserva `main`, NQC037–NQC047 y sus cuentas de presupuesto. **Solo DRY_RUN, sin RPC, sin clave, sin transacciones ni pruebas de estado reales.**

## Resultado comprobado

NQC047 usaba un único journal con respuestas incluidas y un límite de 650,000 bytes; el transporte NQC038 permite hasta 16 MiB. NQC048 introduce `chunked_ledger.js` y `github_adapter.js`: reserva remota condicional con SHA del archivo, guarda la respuesta sintética en fragmentos base64 inmutables de hasta 256 KiB decodificados y exige un readback de **cada commit y contenido** antes de registrar un manifiesto `RECEIVED` dentro de `JOURNAL.json`. El manifiesto conserva SHA-256, longitud y hash de cada fragmento. Se reconstruye y valida desde GitHub antes de marcar `VERIFIED`.

Una reserva sin respuesta bloquea. Una falla o confirmación ambigua de cualquier operación de escritura bloquea. Una recuperación de `RECEIVED` **revalida offline, pero detiene la adquisición** con `BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED`; no autoriza siguiente consulta ni reenvía la anterior. La respuesta se guarda solo después de comprobar el envelope y rechazar el reflejo literal de un secreto sintético. Un verificador inyectado debe aprobar antes de marcar `VERIFIED`; durante estas pruebas acepta únicamente los marcadores `SIM_ACCEPTED_n`, que **no tienen valor probatorio de blockchain**.

La suite `test_chunked.js` **aprobó 15/15 casos** en el evaluador JavaScript con sus fuentes descargadas del commit GitHub, incluyendo ocho pasos sin noveno envío, respuestas >650 KB, Unicode/base64, pérdida de confirmación antes/después de la reserva, pérdida de confirmación de fragmento, recuperaciones, corrupción, autenticación simulada, rechazo del envelope y protección de clave. No son pruebas on-chain ni se suman a los 140 casos anteriores como si fueran evidencias históricas.

### Prueba con GitHub real

La respuesta sintética 1 tenía **700,063 bytes UTF-8**, SHA-256 `01ee296c7e334c5a6b1a6c31ef36f4b1f6a5e10cc1e7ea1746bbe6d6536fa58d`; una implementación independiente Python `hashlib` reprodujo el mismo digest. GitHub conservó **3 archivos** de 262,144 + 262,144 + 175,775 bytes decodificados y un manifiesto `RECEIVED`, en el commit `a79844bb12951e8fb96cbd3757d5d9689d24940c`.

La ejecución del conector fue interrumpida por su límite máximo de llamadas antes de terminar `VERIFIED`. Tras recuperar el código y volver a leer los commits desde GitHub, NQC048 reconstruyó y revalidó los **tres fragmentos**, devolvió **`BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED`** y efectuó **cero llamadas al transporte simulado**. Se conservó la reserva; no se forzó ni reinició el journal. El resultado y hashes de los archivos están en `evidence/REAL_GITHUB_RECOVERY.json`.

El límite de llamadas observado es una **restricción operacional de este conector**: un productor de 16 MiB requeriría muchos fragmentos y **no está probado** que este ejecutor pueda completar su persistencia antes de agotarse. Por tanto, el diseño fija hasta 16 MiB, pero la prueba real solo acredita **700,063 bytes**. No presentar este prototipo como apto para RPC real.

## Bloqueos que permanecen

1. No existe un canal confirmado en este entorno para usar la clave Triport sin exponerla: en el contenedor las variables `NQC_TRIPORT_API_KEY` y `NQC_ARCHIVE_RPC` están ausentes. La búsqueda de conectores no identificó uno específico de Triport. El panel Android del usuario muestra clave enmascarada y Robinhood LIVE, pero eso no entrega credenciales al ejecutor ni demuestra `eth_getProof`.
2. Falta conectar **realmente** `NQC037/src/intake.py` (`validate_step`) y el transporte fijo `NQC038/triport_intake.py` en un mismo ejecutor confiable, sin rutas alternativas y bajo una bitácora operativa única.
3. No se acreditó exclusión de **hosts independientes**, prevención de rollback externo, robustez de la persistencia de 16 MiB completos ni capacidad operativa para completar muchos commits en una sola sesión.
4. El checkout Git completo no está disponible en el contenedor actual por fallo de DNS y faltan dependencias Python como `rlp`; **no** se ejecutaron aquí `migration/verify_isolation.py` ni las pruebas históricas. El GitHub compare limita la revisión de alcance a los archivos modificados.
5. Siguen pendientes estado histórico autenticado, canonicidad/finalidad independiente, witness completo, configuración Nitro histórica, replay y prueba económica. Ninguna simulación abre estos gates.

El plan previo no cambia: `nqc-038-archive-access/TRIPORT_PLAN.json` fijado por digest, ocho lecturas **totales**, bloque padre 66744161 en chain 4663, nunca `latest`. **Cero** consultas Triport autenticadas enviadas, **cero** pruebas históricas adquiridas y **0/11** slots del preestado exacto autenticados. No reintentos, proveedores o rutas alternas. `commercial_admission=false`.

## Inspección y reproducción

Con checkout autorizado y Node, la suite offline se ejecuta con:

```sh
node migration/experiments/nqc-048-durable-chunked-receipts/test_chunked.js
```

El usuario solo dispone de Android y **no necesita ejecutarlo**. Esta instrucción es para un futuro entorno autorizado, no una petición al usuario. El reporte de esta entrega está en `VALIDATION.json` y `STATUS.json`. `JOURNAL.json` continúa en `RECEIVED` y bloquea cualquier nuevo intento DRY_RUN de esa sesión.

**Siguiente cuestión técnica:** reducir los commits necesarios para almacenar hasta 16 MiB sin perder confirmación y demostrar la integración del verificador NQC037 con un registro de consumo único y resistente a rollback; solo después reconsiderar un canal seguro de credencial. Hasta entonces, **ninguna consulta real**.
