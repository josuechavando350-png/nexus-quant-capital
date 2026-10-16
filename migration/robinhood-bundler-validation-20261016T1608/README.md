# NQC: validación local instrumentada; bundler completo pendiente

El entorno completo del bundler quedó bloqueado por dependencias no descargadas.
No se sustituye con un modo que omita reglas. Este incremento prepara una prueba
real de EVM local con Geth y el trazador oficial ya disponibles, y mantiene la
admisión del bundler y la financiación comercial como no demostradas.

Las reglas/controles/limitaciones están fijados en [PROTOCOL.md](PROTOCOL.md).
El informe posterior de la ejecución, cuando exista, será `CAPTURE.md`, separado
del protocolo. La evidencia local no será una captura nueva de Robinhood.

`prepare.py` verifica fuentes Git y produce compiler-input/runtime/tracer fijados;
`validation.py` genera fixtures preservando cuenta/calldata/firma y decodifica
estrictamente la respuesta; `run_local.py` sólo permite cuatro métodos de lectura
en127.0.0.1, conserva prefijos y rechaza sobrescritura de salida. No signer ni API
de envío. El JWT determinista de laboratorio autentica una Engine API local sin uso;
no es una wallet ni un secreto de producción y no se publica como evidencia.

El índice PR22 permanece intacto, sin nuevos candidatos/cobertura medidos. Ganancias,
stake y saldos de fixtures no son dinero obtenido. No se habilitan workflows.
