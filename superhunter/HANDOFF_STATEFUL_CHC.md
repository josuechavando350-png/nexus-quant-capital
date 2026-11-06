# Continuidad — control con estado CHC

Base recuperada: SUPERHUNTER_solidity_smt_1422.zip, carpeta codigo/.
No se sustituyó por una rama remota más pequeña. La base se reejecutó antes de
modificarla. Catálogos 27/50/25, fuentes nativas y tests previos se preservan.

Incremento: solidity_stateful.py, interfaz CLI y componente QA, 45 pruebas,
una captura real de compilación/solución vinculada por el snapshot de fuentes,
y documentación. No añade dependencias ni modifica fuentes nativas.

Pendiente EVM: no había motor instalado; pip no resolvió pypi.org y la descarga
alternativa de py-evm tampoco produjo un paquete. No se implementó una EVM falsa.
El desarrollo realizado usa solc y Z3 reales sobre controles propios con estado;
no se contabiliza como ejecución de bytecode. No se activan escáneres o explotación.

El estado intermedio observado por las referencias es el punto de la aserción,
antes de revert. No se presenta como saldo confirmado después de una transacción.

Publicación: esta entrega es local. No se modificó main, PRs, permisos, workflows,
servicios ni cuentas. No se ejecutó la suite histórica completa de NQC ni su
verificador global de aislamiento porque se trabaja con el paquete recuperado.

Ver VALIDATION.json del ZIP de entrega y los logs originales para resultados
finales; no heredar contadores de entregas antiguas. La aceptación nativa no usa
mocks. La evidencia deliberadamente manipulada está etiquetada como control negativo.

Dos intentos conjuntos con cuatro grupos agotaron el límite del grupo más pesado.
Se divide ahora la suite en ocho grupos deterministas completos, sin modificar
los tests anteriores ni los límites de cada worker (90 s CPU / 180 s real).
El presupuesto total máximo aumenta; no se presenta como el mismo presupuesto.
Se añaden dos comprobaciones del inventario y del modo de agregación.
