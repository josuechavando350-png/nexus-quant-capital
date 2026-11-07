# QA propio con SDK y dependencias fijadas por bytes

El perfil `owned-local-qa-opentelemetry-sdk-pinned-v2` comprueba ocho distribuciones de Linux CPython 3.12 x86_64 antes de importar el SDK y después de terminar QA. Las versiones por sí solas no bastan. `otel_dependency_pins.py` contiene los hashes derivados de los wheels revisados: 403 archivos de código/datos y los ocho METADATA. El archivo de instalación incluye las ocho versiones y sus hashes, sin extras opcionales.

Distribuciones: OpenTelemetry SDK/API 1.42.1; semantic-conventions 0.63b1; typing-extensions 4.16.0; cryptography 46.0.4; PyYAML 6.0.3; cffi 2.1.1; pycparser 3.12. Instalar únicamente en un entorno dedicado con `--require-hashes`. EELS conserva su entorno distinto, incluida cryptography 45.0.7.

## Comprobación implementada

- Se leen los archivos esperados desde pins del código, sin tomar el RECORD instalado como autoridad.
- Se revisan también los directorios de los paquetes y los módulos vecinos que podrían sustituir una importación; archivos añadidos, faltantes, versiones diferentes y cambios de METADATA bloquean la admisión.
- Enlaces simbólicos, rutas fuera del entorno, mezclas de directorios de distribución, archivos no regulares, exceso de tamaño y cambios entre capturas se rechazan.
- Un cambio de dependencias al terminar QA impide el manifiesto final de telemetría. Un recibo vuelto a sellar con otras identidades también se rechaza.
- Los recibos históricos v1 siguen legibles como **v1 sin pins**. No reciben las afirmaciones nuevas; la CLI informa el perfil y si el recibo declara la comprobación de archivos.

La comprobación se limita a archivos instalados: **no** autentica productores ni demuestra integridad de memoria de procesos. El perfil de aceptación se inicia con `-I -B -X pycache_prefix=<directorio_privado_nuevo>`; los ocho workers ya usan prefijos privados nuevos. Las cachés `.pyc` existentes se excluyen de la identidad del código fuente y no se usan en esa aceptación. La API embebida no certifica módulos que el proceso anfitrión ya hubiera cargado o modificado.

## Validación real de esta iteración

- 25 pruebas focalizadas PASS con SDK real: 14 controles nuevos de integridad y tres nuevos de recibos/compatibilidad, además de las ocho anteriores. La comprobación sin SDK también ejecutó 25 tests y verificó el bloqueo; sus ramas opcionales no equivalen a ejecutar el SDK.
- **2,574/2,574 QA PASS** con SDK real, cero fallos/errores/skips, dentro del perfil completo instrumentado. Las 2,557 identidades anteriores se conservan. Ocho workers, 180 s de pared, 90 s CPU, 2 GiB y 20 MiB por archivo sin ampliación. Máximo observado: 72.876555 s.
- El perfil llamó al checker real y a su verificador; no usó un recibo simulado. Se conservaron los ocho recibos por worker y los spans reales en memoria. El helper de aceptación solo añadió medición y delegó la ejecución efectiva al checker.
- Digest de código: `bd4d458a46875ba777b074ca648df6a4dbeca7721a0178855f68877ba039169d`.
- Un proceso separado verificó QA y telemetría usando un entorno **sin SDK instalado**: prueba de consistencia del expediente, no segunda ejecución de QA o autenticación del productor.
- Límite de repositorio PASS y 642 archivos históricos preservados. Motores Geth/EELS y capturas sin cambios; su aceptación nativa anterior corresponde al digest de #79 y no se atribuye al nuevo digest sin repetirla.

Una sola medición no permite estimar p50/p95 ni atribuir diferencias de tiempo al SDK: también cambió el inventario de tests. Collector, OTLP, exportación de red y despliegues no están habilitados. No se promueve el candidato externo #26 a integración completa ni se altera el denominador de ningún catálogo. Avance global no determinado; ninguna vulnerabilidad original confirmada.
