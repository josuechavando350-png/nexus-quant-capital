# Continuidad — enlace EVM a conciliación de unidades internas

Base: `SUPERHUNTER_evm_estado_1550.zip`, directorio `codigo/`. No sustituirla
por una rama remota reducida. El nuevo módulo usa el ejecutor EVM y sus fuentes
fijas originales; no las modifica. Los 27 requisitos, 50 capacidades, 25
iniciativas y cinco fuentes nativas se conservan byte a byte.

Nuevo código: `evm_accounting.py`; API aritmética añadida en
`balance_reconciliation.py`; rutas nuevas en `__main__.py`; registro y pruebas
obligatorias en `quality.py`. Tests nuevos: `test_internal_units.py` y
`test_evm_accounting.py`. Fixture `evm_accounting_capture.json` obtenido de una
nueva ejecución de los binarios fijados, sin alterar la captura anterior.

La captura histórica `evm_state_capture.json` tenía un hash de desarrollo de
`evm_execution.py`, no el archivo final del paquete 1550. El nuevo enlace la
rechazó al exigir identidad exacta. No se retocó su hash para aparentar origen:
se ejecutó otra vez la ruta nativa y se conservó una captura nueva. El comprobador
anterior no ofrecía esa autenticación del archivo al releer solo el fixture.

El registro VALIDATION.json en la raíz de la entrega distingue pruebas unitarias,
aceptación nativa real, original/copia parcheada y checks no realizados.
Los intentos intermedios incompletos o rechazados no cuentan como aprobaciones.

No hubo cuentas de plataformas, escaneos, RPC, transacciones firmadas, envío de
reportes ni cambios de repositorio remoto. No se elevó el estado de capacidades
amplias. La suite histórica completa NQC y su aislamiento global no forman parte
del paquete recuperado: no se declaran ejecutados.
