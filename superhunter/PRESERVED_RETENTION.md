# Conservación explícita de copias preservadas

`review-preserved-retention` comprueba un índice y todos sus ZIP antes de calcular qué entradas exige conservar una política externa. Solo marca como revisables aliases con bytes idénticos; cada ZIP distinto conserva al menos una entrada disponible. Dos ZIP de productores distintos no se descartan por representar el mismo inventario original.

La política canónica tiene exactamente `schema_version: 1`, `profile: explicit-preserved-retention-v1`, `minimum_copies_per_archive` (entero 1–64), `retain_ids` (lista ordenada, única y contenida en el índice), `maximum_retained_bytes` (entero 1–536870912) y `allow_review_of_incomplete_duplicates` (booleano). Las retenciones explícitas siempre prevalecen; cuando el último campo es false, todas las copias de capturas incompletas o inválidas se conservan. No hay política por defecto inferida de fechas ZIP.

Para cada ancla ZIP, primero retiene los IDs explícitos y las capturas incompletas protegidas; después completa el mínimo con IDs en orden lexical. El resto recibe `REVIEW_EXACT_DUPLICATE`. Copias faltantes o presupuesto insuficiente producen `RETENTION_REQUIREMENTS_UNMET`; nunca se simula una copia nueva ni se sacrifica una retención requerida para cumplir el presupuesto. Los bytes cuentan entradas lógicas, no bloques físicos, archivos independientes o ahorro real en disco.

## CLI

`review-preserved-retention --bundle INDEX --archive-root ARCHIVES --policy POLICY --policy-anchor SHA256 --out NEW_REPORT --source-digest CURRENT_CODE --manifest-anchor SHA256 --index-anchor SHA256 [--index-source-digest INDEX_PRODUCER]`

`verify-preserved-retention --bundle INDEX --archive-root ARCHIVES --report REPORT --report-anchor SHA256 --policy-anchor SHA256 --source-digest CURRENT_CODE --manifest-anchor SHA256 --index-anchor SHA256 [--index-source-digest INDEX_PRODUCER] [--retention-source-digest REPORT_PRODUCER]`

Las identidades anteriores son explícitas y externas; el lector actual siempre debe coincidir con `source_digest`. No se ejecuta ni autentica el productor histórico. El reporte conserva la política exacta y puede verificarse sin su archivo externo, pero requiere el índice y sus archivos actuales. Todos los estados y decisiones se recalculan; cambiar un resumen y su marcador no evita la comprobación.

Salida nueva 0700 con `policy.json`, `retention.json`, `REVIEW.md`, `COMPLETE.json` en 0600. No sobreescribe, borra, mueve ni modifica archivos de entrada. Un fallo posterior a escritura puede dejar el nuevo reporte sin devolver éxito. Dos pasadas de archivos, anclas, política, índice y código detectan cambios observados, sin afirmar inactividad o autenticidad del host.

Retorno 0 solo con requisitos satisfechos y capturas estructuralmente completas. Retorno 1 con requisitos incumplidos o alguna captura incompleta/ inválida. Retorno 2 ante rechazo de formato, anclas o evidencia. Ningún resultado autoriza purgas, acredita independencia de respaldos ni confirma hallazgos. La consola publica conteos/digests/estados, no IDs, nombres o rutas privadas.

## Evidencia

30 pruebas focales aprobadas; controles de retenciones, faltantes, presupuesto, estado incompleto, esquema, límites, bytes alterados y promociones con manifiesto recalculado. Un control puro de dos versiones ZIP usa anclas sintéticas declaradas, no ejecuciones de productores anteriores.

20 controles CLI sobre el índice y los ZIP exactos preservados en PR100. Política inicial: 10 entradas retenidas y un alias revisable, manteniendo 10 ZIP distintos y 5 inventarios originales. Retener explícitamente los dos aliases conserva las 11 entradas. Exigir dos copias por ZIP informa 9 faltantes. Presupuesto de un byte informa incumplimiento y conserva las 10 entradas requeridas. Ningún archivo de evidencia histórico se modifica ni elimina. El helper retira deliberadamente solo su archivo nuevo de política para probar la lectura de la copia incluida en el reporte.

Las nuevas pruebas se asignan al grupo 4, con margen medido; los 3,091 IDs anteriores mantienen su grupo. QA integral final: 3,121 PASS, cero fallos/errores/skips; SDK real y verificación separada sin SDK aprobados. No nuevas ejecuciones nativas, hallazgos, integraciones externas o promoción de hitos globales.
