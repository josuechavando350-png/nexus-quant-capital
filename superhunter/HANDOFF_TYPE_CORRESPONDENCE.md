# Continuidad — perfil v2 de coherencia de tipos

Base recuperada: SUPERHUNTER_fuente_ast_layout_1177.zip, carpeta codigo/.
SHA-256: `9f53f40d57984d6088285ab3894f06c8462307aed83fa04512dd1758ccb3db9c`.

Se preservan todos los 1,177 identificadores de pruebas y sus archivos originales.
El incremento añade 46 pruebas. Los tres catálogos 27/50/25 y las cinco fuentes
nativas quedan sin cambios. No se incorporan logs anteriores sin su código.

El manifiesto schema_version=2 activa coherencia entre fragmentos de tipos de
fuente, formas AST y descriptores del layout. El v1 sigue siendo revisión de
identidades/posiciones sin asumir esta garantía nueva. No hay un downgrade
silencioso: la referencia externa del expediente fija la versión requerida.

La reproducción clave es una fuente/AST uint128 con descriptor uint256. El
perfil anterior no rechazaba esa incoherencia de tipos porque no la comprobaba;
el v2 sí. Los ASTs de los controles son sintéticos y explícitos, no compilaciones.
El resultado de una forma fuera del perfil no se eleva a preservado.

Intentos de obtener solc: DNS del contenedor bloqueó el host oficial, y fallaron
las descargas alternativas probadas. El listado y documentación se pudieron
consultar en web, pero eso no equivale a disponer del ejecutable ni compilar.
No se ejecutaron solc, Slither, Forge, EVM ni sistemas de terceros.

Estado de pruebas y artefactos en el VALIDATION.json de la entrega. Los intentos
incompletos/fallidos se conservan por separado, no cuentan como pases. Esta
entrega no certifica seguridad ni detección de vulnerabilidades reales.

No se ha creado commit/PR remoto ni modificado main, workflows o fuentes NQC
históricas. El parche es incremental contra este ZIP completo, no contra ramas
remotas que solo contienen subconjuntos. No se corrió la suite histórica de NQC
ni su verificador global: el checkout completo no está disponible aquí.
