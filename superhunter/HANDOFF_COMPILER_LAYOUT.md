# Continuidad — correspondencia de fuente, AST y layout

Base recuperada: SUPERHUNTER_layout_solidity_1114.zip, carpeta codigo/.
SHA-256 del ZIP: abd74de488e1bb969e2717a2d859d12ebdc8b2d70267fb257c25fd0e2a4e7099.

Se preservan los 1,114 IDs de pruebas, todos los archivos anteriores de tests,
los catálogos 27/50/25 y las cinco fuentes nativas. No se integra otra rama de logs
sin código recuperable. Este incremento añade 63 tests y un componente de
correspondencia de artefactos conectado a storage_layout, native, IO, privacidad,
QA y CLI. El catálogo no declara nuevos motores completos.

La base fue reejecutada: 1,114 pruebas, sin fallos, errores ni omisiones. El detalle
final de la suite ampliada y la copia limpia se registra en VALIDATION.json del
paquete de entrega; este archivo no sustituye esos recibos ni hereda sus resultados.

Control discriminante ejecutado: misma estructura, pero una fila de layout nombra
otro contrato. La revisión solo de layout devuelve LAYOUT_PRESERVED_IN_PROFILE;
la nueva ruta rechaza LAYOUT_CONTRACT_MISMATCH antes de promover la evidencia.
Otros controles: variable omitida, AST desactualizado, error de compilador con
layout presente, reordenamiento real del layout y settings cambiados.

No se ejecutó solc. No estaba instalado y el intento de obtenerlo falló; también
fallaron DNS del registro npm y del host raw de GitHub. No se reemplazó su salida
con una simulación presentada como compilación. La fuente+AST siguen siendo
artefactos aportados. Este incremento no implementa el motor de descubrimiento,
Slither, Forge, EVM ni un benchmark de vulnerabilidades reales.

No hay publicación remota de este acumulado, modificación de main ni activación
de workflows. El parche es incremental contra ZIP1114, no contra un PR remoto
reducido. Tampoco se ejecutó la suite histórica completa NQC ni su verificador
global de aislamiento: el contenido disponible es el paquete superhunter.
