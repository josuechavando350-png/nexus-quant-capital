# Índice privado de archivos preservados

El índice verifica una lista explícita de archivos del perfil `private-preserved-copy-zip-stored-v1` y agrupa tanto los ZIP idénticos como los inventarios originales idénticos. Reutiliza el verificador real del archivo: no toma el nombre, extensión o resumen como prueba suficiente.

## Entradas y resultados

`index-preserved-archives --manifest MANIFEST --manifest-anchor SHA256 --archive-root DIRECTORY --out NEW_DIRECTORY --source-digest CURRENT_CODE_SHA256`

El manifiesto usa JSON canónico de `safe_io.canonical`, perfil `explicit-preserved-archives-v1`, `schema_version: 1` y una lista `archives` de 1 a 64 registros ordenada por `id`. Cada registro tiene exactamente `id`, `file`, `preserved_source_digest`, `input_anchor`, `recovery_anchor`, `archive_anchor`. IDs ASCII de 1 a 64 caracteres; nombres planos ASCII terminados en `.zip`; IDs y nombres no pueden repetirse. Los cuatro digests son SHA-256 hexadecimales minúsculos y deben obtenerse de las anclas preservadas fuera del paquete.

La misma ancla de archivo puede aparecer bajo nombres e IDs distintos. Se conserva cada entrada y se agrupan sus aliases. `unique_archives` cuenta anclas ZIP distintas; `unique_input_inventories` cuenta inventarios originales distintos. Ninguno mide ejecuciones independientes. Los bytes listados incluyen aliases; los bytes únicos no los duplican. Las capturas completas e incompletas se cuentan por archivo único.

`verify-preserved-index --bundle INDEX_DIRECTORY --index-anchor SHA256 --manifest-anchor SHA256 --archive-root DIRECTORY --source-digest CURRENT_CODE_SHA256 [--index-source-digest INDEX_PRODUCER_SHA256]`

El verificador vuelve a comprobar todos los archivos, reconstruye los conteos y exige coincidencia exacta con `index.json` y `REVIEW.md`. La copia de `inputs.json` permite retirar el archivo del manifiesto externo; sus anclas externas siguen siendo necesarias. El índice no incluye los ZIP: deben conservarse y estar disponibles para verificarlo. Las rutas raíz pueden reubicarse manteniendo los nombres declarados.

`source_digest` identifica el código lector actual. `index_source_digest`, cuando el índice se creó con otra versión, debe proporcionarse explícitamente; no se infiere del propio reporte. Cada archivo conserva además su propio `preserved_source_digest`. Verificar datos históricos con la semántica conocida actual no ejecuta ni autentica el productor anterior.

## Límites y efectos

Manifiesto máximo 65,536 bytes; 64 entradas; 512 MiB de bytes ZIP listados, incluyendo aliases. Cada archivo conserva los límites del perfil portable. La colección se procesa secuencialmente, sin acumular todos los ZIP en memoria. Se repiten hashes e identidades de archivos al terminar la colección y tras escribir. Esto detecta las mutaciones observadas; no demuestra inactividad, ausencia de cambios transitorios restaurados ni autenticidad del host.

Salida nueva: directorio 0700, archivos 0600 `inputs.json`, `index.json`, `REVIEW.md`, `COMPLETE.json`. No sobreescribe expedientes ni modifica entradas. Si falla una comprobación posterior a la escritura, puede quedar un expediente nuevo; el retorno no afirma éxito ni lo elimina. La salida es privada y no cifra los metadatos. Consola con estados, digests y conteos; no nombres, rutas o contenido original.

Código 0: índice válido y todas las capturas estructuralmente completas. Código 1: índice válido con alguna captura incompleta, inválida o con limpieza de commit pendiente. Código 2: rechazo del índice, manifiesto, archivo o anclas. Un marcador COMPLETE del índice no convierte sus capturas en completas.

Sin descubrimiento de directorios, extracción ZIP, red, ejecución del contenido, purgas o autenticación de productores. M1 permanece parcial; el índice no añade integraciones externas ni confirma hallazgos.

## Evidencia de esta entrega

34 pruebas nuevas de contrato pasaron inicialmente. Aceptación CLI sobre los 10 archivos exactos del expediente de PR99 más un alias: 11 entradas, 10 ZIP distintos, 5 inventarios originales, 2 archivos con captura completa y 8 incompleta. Se conservaron todos los bytes anteriores. Los 17 controles CLI incluyen retirar el manifiesto externo, reubicar la colección, alterar conteos/independencia/estado con un manifiesto recalculado, anclas incorrectas, archivo cambiado/ausente/symlink y 64 aliases frente al rechazo de 65 registros. Las capturas históricas se leyeron; no se reejecutaron sus productores. QA integral final: 3,091 PASS, cero fallos/errores/skips, con SDK real y revisión separada sin SDK; 3,057 IDs anteriores retenidos en los mismos ocho grupos y 34 nuevos. Consulte CONTINUATION.md para identidad y límites.
