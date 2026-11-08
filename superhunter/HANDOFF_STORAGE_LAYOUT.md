# Continuidad — revisión de layout de almacenamiento

Base recuperada: `SUPERHUNTER_expediente_orden_1059.zip`, carpeta `codigo/`.
No basar la siguiente entrega solo en un conteo de tests: los logs de 1116 y 1120
mencionan verificadores de pruebas de estado, pero no aportan esas fuentes en
el paquete recuperado. Se conservan como antecedentes, no como código integrado.

Nuevos archivos: `storage_layout.py`, `tests/test_storage_layout.py`,
`STORAGE_LAYOUT.md` y este registro. Se actualizan CLI, mapa de QA y README.
Las fuentes nativas, archivos de tests anteriores y registros 27/50/25 se
conservan. No se marca una capacidad amplia como completa por este comparador.

La unidad verifica compatibilidad declarada y referencias entre artefactos,
con manejo conservador de casos no soportados. No ejecuta solc/Slither/EVM,
no autentica código desplegado ni sustituye el trabajo pendiente del Hunter.
El módulo se conecta a las pruebas y al reporte conjunto por `quality.py`.

No modificar fuentes históricas PFT/Census, main, workflows, cuentas o permisos.
El parche de esta entrega es contra la base LOCAL 1059, no contra una rama remota
focalizada. Comprobar la identidad antes de aplicarlo. Los resultados actuales
están fuera del árbol de código en el manifiesto y registro de validación del ZIP.

Pendientes materiales conservados: compilación real de código propio, análisis
Solidity/EVM verificable, conectores autorizados, benchmark independiente,
publicación/conciliación íntegra del acumulado y revisión de herramientas/licencias.
