# Verificación conjunta de archivos y custodia

El revisor combina el índice real y todos sus archivos con una firma Ed25519 separada. La firma debe coincidir con la política externa fijada por SHA-256, el caso, el productor de custodia y su vigencia actual. Después se recalcula el índice. Una firma válida sobre un índice que miente en sus conteos sigue siendo rechazada.

No genera claves, firma, ejecuta capturas o descubre objetivos. Consume el sello del módulo custody existente. La atribución es a una clave confiada para custodia de esos bytes y ese caso; no autentica la ejecución original, la identidad humana del custodio, su independencia ni la veracidad de los datos.

## CLI

`review-preserved-custody --bundle INDEX --archive-root ARCHIVES --seal SEAL --trust TRUST --trust-anchor SHA256 --source-digest CURRENT_CODE --manifest-anchor SHA256 --index-anchor SHA256 --seal-anchor SHA256 --case-id UUID --producer-id CUSTODY_PRODUCER [--index-source-digest INDEX_PRODUCER_CODE] --out NEW_REPORT`

`verify-preserved-custody` usa los mismos argumentos de entrada, más `--report REPORT --report-anchor SHA256` en lugar de `--out`; admite `--review-source-digest REVIEW_PRODUCER_CODE` para verificar un reporte anterior con identidad explícita. El lector actual siempre debe coincidir con `source_digest`; no se infiere una identidad confiada de los reportes.

La política de confianza es externa al índice, sello y reporte, tiene un máximo de 65,536 bytes y conserva el esquema de custody. Se exigen anclas externas para política, sello, índice, manifiesto y reporte. El índice mantiene sus límites de 64 entradas y 512 MiB listados, incluyendo duplicados. Los archivos se verifican nuevamente, con comprobaciones de identidad/hashes después de verificar la firma; cambios de índice, sello, política o código también causan rechazo.

Vigencia y revocación se comprueban con el reloj local actual, también después de revisar el índice. No existe opción CLI para omitir la vigencia o imponer una fecha pasada. No prueba que el reloj sea confiable. Una verificación futura puede rechazar un sello expirado o una clave revocada aunque el recibo histórico haya sido válido en su comprobación anterior.

Salida nueva 0700 con `custody.json`, `REVIEW.md` y `COMPLETE.json` en 0600. No guarda claves privadas ni copia el contenido de los ZIP. Consola con digests, conteos y estados, sin caso, nombre del custodio, rutas o claves. Un fallo posterior a escritura puede dejar el reporte nuevo sin devolver éxito; no se sobreescribe ni elimina evidencia.

Retorno 0 solo con firma/custodia/índice válidos y todas las capturas estructuralmente completas. Retorno 1 si esa verificación pasa pero hay capturas incompletas o inválidas. Retorno 2 ante cualquier rechazo. Firmar una copia incompleta no la convierte en completa.

## Evidencia de aceptación

19 pruebas focales con Ed25519 real y claves efímeras solo en memoria. Incluyen índice falso firmado correctamente, archivo ausente/alterado detrás de una firma válida, política revocada con ancla nueva, firma corrupta con marcador recalculado, expiración durante la verificación y cambios concurrentes.

21 controles CLI sobre los bytes exactos conservados en PR101. La colección mixta mantiene 11 entradas, 10 ZIP distintos, 5 inventarios y 8 capturas incompletas por ZIP único: código 1. Un índice nuevo de capturas completas mantiene 3 entradas y 2 ZIP distintos: código 0. Una firma válida sobre conteos falsos pasa el verificador criptográfico aislado y es rechazada por el revisor conjunto. Se preservan todos los originales anteriores.

La aceptación genera una clave efímera y una política de laboratorio en este mismo host. No conserva la clave privada ni demuestra confianza de un custodio independiente. El control de expiración firma un timestamp pasado explícitamente fabricado para la prueba; no representa una firma histórica real. Los sellos de aceptación vencen tras su intervalo declarado: reproducir requiere nuevos fixtures y una nueva clave de laboratorio, sin reescribir evidencia anterior.

La suite completa terminó con 3,148 pruebas aprobadas, cero fallos, errores o pruebas omitidas. Las 19 nuevas pruebas van al grupo 0; los 3,129 IDs anteriores conservan su grupo. La instrumentación usó el SDK real y un proceso separado sin SDK revalidó QA, telemetría y preparación. El worker más lento tardó 97.574358 segundos, con los presupuestos anteriores intactos.

Los 642 archivos históricos permanecen intactos. El verificador legado mantiene el mismo rechazo previo por `unreviewed root file`; no se presenta como recertificación de NQC. M1 sigue parcial; esta composición no confirma vulnerabilidades, operación 24/7 ni hitos nuevos.
