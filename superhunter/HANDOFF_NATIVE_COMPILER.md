# Continuidad: ejecutor nativo, todavía bloqueado por el binario

Base exacta: SUPERHUNTER_inventario_fuente_1316.zip, carpeta codigo/.

Se añade native_compile.py, solc_worker.py y 31 pruebas. La CLI y el registro QA
los enlazan con validación de entradas de compiler_layout, safe_io y AuditLog de
DIABLO. No se alteraron las fuentes nativas o las listas 27/50/25.

La compilación REAL sigue pendiente: no hay binario solc disponible. La descarga
por npm falló por DNS; el descargador no obtuvo la distribución. El dispositivo
Desktop Commander estaba offline. La documentación/índice oficial sí pudieron
consultarse: no confundir acceso al índice con acceso al ejecutable.

El ejecutor NO admite reemplazar solc por Python, scripts o binarios sin el hash
oficial fijado. No hay modo simulado ni fallback. Ausencia del binario => exit 3,
COMPILATION_BLOCKED y ninguna carpeta de resultados. SHA/versión incorrectos =>
rechazo antes de tratar el ejecutable como compilador.

Hay criterios de aceptación NO EJECUTADOS en SOLC_NATIVE_DRIVER.md. Ni los 31
tests de esta unidad ni un LOCAL_QA_PASS acreditan esos criterios. No marcar
Solidity, Slither, Forge/EVM o el Hunter como completados.

El insumo necesario para la siguiente prueba es el archivo nativo Linux x86_64
0.8.30+commit.73712a01 con SHA-256
f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7.
No sustituir por "latest", un enlace simbólico o una versión de Node sin adaptar
el perfil y volver a probarlo. No se redistribuye el compilador en este ZIP.

No se cambiaron main, ramas remotas, workflows, motores históricos, cuentas o
permisos. No se corrieron la suite histórica NQC o su verificador global: se
trabaja con el paquete recuperado, no un checkout completo del repositorio.
El reporte de validación de la entrega debe distinguir unit tests, el recorrido
numérico previo y los criterios reales de compilación que siguen bloqueados.
