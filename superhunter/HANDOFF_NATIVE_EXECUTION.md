# Continuidad — compilador real disponible y aceptación nativa ejecutada

Base exacta de esta entrega: SUPERHUNTER_ejecutor_solc_1347.zip, carpeta codigo/.
El usuario adjuntó el binario oficial solicitado. Se volvió a consultar el índice
oficial y se calculó el SHA-256 sobre los 16,791,816 bytes recibidos; coincide con
f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7.

La ruta de memfd sellado/worker del ejecutor anterior funcionó con el binario
real sin sustituirlo ni modificarlo. Se comprobó su versión completa y se compiló
Solidity para producir AST y storageLayout reales. No se generó/ejecutó bytecode
EVM ni se lanzó Slither/Forge.

## Nuevo enlace

native_layout.py conecta native_compile con compiler_layout v4. Sus comandos
review-native-layout / verify-native-layout exigen dos entradas ligadas a un
manifiesto externo. Compilan, repiten con el mismo solc y después contrastan
fuente, declaraciones, tipos, posiciones y cambios entre versiones. Registran
las asociaciones mediante el AuditLog nativo de DIABLO. Siempre mantienen
vulnerability_confirmed=false y upgrade_authorized=false.

Los datos originales de compilación se conservan completos. El verificador
requiere el binario de nuevo: un JSON consistente por sí solo no permite afirmar
reproducción. Un historial firmado tampoco sustituye esta ejecución.

## Aceptación realmente ejecutada

El script validation/run_native_acceptance.py pasó 15 controles con 31
invocaciones CLI en procesos separados. No usa un compilador simulado.

- Versión/hash fijados; AST/layout reales para dos uint128 empaquetados.
- Recompilación idéntica byte a byte, incluidos diagnósticos.
- Errores de sintaxis y tipo reportados como compilación fallida.
- Import ausente rechazado con callback deshabilitado; dos fuentes inline sí
  compilan. No se consulta red para resolver imports.
- Perfil v4 aplicado sobre outputs reales: mismo layout y append preservados;
  cambio de orden y signedness detectados; arrays/mapping/bytes contrastados;
  structs fuera del perfil conservan revisión requerida.
- Output inventado (slot cambiado a 7), recibo/auditoría/manifiesto recalculados:
  consistencia interna aceptable, pero replay real rechazado.
- Resultado derivado alterado y binario ausente: verificación rechazada/bloqueada.

Un primer intento fue interrumpido por el timeout de la llamada de herramientas
antes de terminar. Se conserva separado como INCOMPLETO y no cuenta como éxito.
La segunda ejecución fue supervisada hasta su salida 0 y produjo el recibo completo.

## Alcance y estado

Las 1,347 pruebas previas se reejecutaron y pasaron antes de esta modificación.
Se añaden 25 tests unitarios de enlace. Estos usan una captura nativa como datos
y, en casos de orquestación, mocks explícitos de replay; no se confunden con los
15 controles nativos separados. El estado final de la revisión acumulativa y de
la copia parcheada se registra en VALIDATION.json de la entrega, no se presume.

Los catálogos 27/50/25 y fuentes nativas se conservan. No se cambia su estado a
completo por haber desbloqueado este subcomponente. Mantener los documentos de
entregas anteriores como historia; las frases 'binario ausente' en ellos describen
esas ejecuciones anteriores, no este entorno después del adjunto.

No se redistribuye el compilador en el ZIP. El usuario conserva su archivo y debe
proporcionarlo con --binary. Las referencias repo/commit de los controles son
etiquetas locales declaradas, no clones autenticados ni targets de bounty.

No se modificaron main, workflows, cuentas, permisos ni infraestructura. No se
corrieron el checkout histórico completo NQC o su verificador global. La publicación
remota del acumulado sigue pendiente: no aplicar este parche a una rama parcial.
