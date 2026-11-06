# Continuidad: secuencia vinculada al expediente

Retomar el código completo de ESTA entrega, no un número de pruebas aislado ni
una rama focalizada antigua. Base: código/ de SUPERHUNTER_secuencia_contable_1019.zip.

Cambios: case_review.py (contexto v2 con secuencia obligatoria), quality.py
(dependencia y tests obligatorios), tests/test_ordered_case.py, ORDERED_CASE.md y
este documento. El parche es incremental sobre el ZIP1019; no aplicarlo sobre
main o sobre un PR reducido sin conciliar.

Las 1019 pruebas originales se conservan por identificador y por bytes de sus
archivos. Se añaden 40 tests de integración del expediente. La suite final no
incluye automáticamente los tests de logs1055/1066 cuyo código no está recuperado.
La función `context_groups` evita que una evidencia adicional se ignore o que se
pueda degradar implícitamente v2 a v1. v1 se conserva y declara que no comprueba
orden. Las decisiones no autorizan operaciones ni confirman hallazgos.

Leídos: fuente recuperada y registros de continuidad; estado remoto por GitHub.
La consulta de PRs sigue mostrando las ramas focalizadas anteriores. No hay
publicación remota de esta consolidación. Ver VALIDATION_ORDERED_CASE.json fuera
del árbol de código para tiempos, fuentes, comandos, intentos y límites actuales.

Persisten los pendientes de publicación íntegra, herramientas Solidity/EVM,
prueba sobre código propio compilado, benchmarks independientes y conectores.
No sustituirlos por más contadores de pruebas ni atribuirles esta validación.
