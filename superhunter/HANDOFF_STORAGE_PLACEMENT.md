# Continuidad — colocación independiente de almacenamiento

Base exacta: SUPERHUNTER_tipos_fuente_layout_1223.zip, carpeta codigo/.
SHA-256 del archivo base: 418afa6afc7f07c94edab3f7971e240032ca90b82f8119da3cd56ee661489c4c.

Se conserva el acumulado, las fuentes nativas y los registros 27/50/25.
No se eleva ninguna capacidad amplia a completa. No se combina esta entrega con
ramas o logs sin su código correspondiente.

Cambios: storage_placement.py, tests/test_storage_placement.py, compiler_layout.py,
quality.py y los dos documentos de esta entrega. Los tests previos se conservan.
Se añade el perfil 3 al manifiesto externo, sin cambiar las garantías de 1 y 2.
El análisis de tipos se registra como componente propio; sigue siendo el mismo
source_types.py, sin modificaciones de sus bytes.

Control discriminante: fuente uint128 en un contrato ordinario, pero primera
variable reportada en slot 7. El perfil 2 acepta esa consistencia entre versiones;
el perfil 3 rechaza la colocación incorrecta. Es una ampliación de garantía, no
un exploit o un hallazgo atribuible a un protocolo.

El primer intento del gate conjunto quedó bloqueado por una dependencia de QA
registrada bajo un nombre inexistente. Se corrigió separando la propiedad del
módulo source_types, sin quitar tests o relajar el gate. Los logs se preservan.

Descargas solc: los intentos HTTPS al servidor de binarios y a la release oficial
fallaron en este entorno. solc no está instalado y NO se ejecutó. No se añadió
un ejecutor ficticio ni se sustituyó compilación por un archivo de ejemplo.

Pendientes materiales: compilador real fijado y ejecución Solidity/EVM; conexión
con estados auténticos; detección y validación de vulnerabilidades; consolidación
remota integral; benchmark ciego. La suite histórica de NQC y su verificador de
islamiento total no se ejecutan desde este paquete parcial de repositorio.
No se modifica main, workflows, secretos, servicios ni objetivos externos.
