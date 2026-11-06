# Continuidad: estado persistente observado en EVM

Base recuperada: SUPERHUNTER_bytecode_nativo_1504.zip, subdirectorio codigo/.
Se preservan las fuentes, los 1,504 IDs de tests anteriores, las cinco fuentes
nativas DIABLO/NQC y los catálogos 27/50/25.

Los logs de 1,549 pruebas y aceptación EVM fueron leídos como antecedentes.
No se recuperó un paquete fuente de esa línea; sus 45 pruebas no se cuentan ni
se presentan como incorporadas. Esta implementación tiene su propio módulo,
46 pruebas nuevas y controles nativos efectivamente ejecutados. El recibo de
validación fuera del árbol codigo/ identifica la ejecución final y sus hashes.

Módulos nuevos: evm_execution.py, evm_worker.py, test_evm_execution.py y captura
real de salida en tests/fixtures/evm_state_capture.json. Se registran en quality.py,
el snapshot de fuentes y __main__.py. No se sustituyen métodos originales.

La captura de tests procede de una ejecución nativa de desarrollo anterior al
último refuerzo del validador. Es un fixture explícito, no una compilación nueva
ni un productor autenticado. Los tests que sustituyen execute prueban únicamente
la orquestación. El registro de aceptación nativa NO emplea esas sustituciones.

Pendientes: consolidación remota completa, integración de analizadores externos,
medición ciega de capacidad de descubrimiento y alcance operativo verificable.
No se habilitan exploración ofensiva autónoma, objetivos externos, RPC, cuentas,
reportes automáticos ni nuevos servicios. El éxito en los controles fijos no
completa el Hunter. No modificar main ni workflows con este parche.

Este paquete no es un checkout completo de NQC. La suite histórica Rust/Python
y el verificador global de aislamiento no se ejecutan con esta copia parcial.
El parche se aplica contra la base 1504; no contra una rama remota reducida.
