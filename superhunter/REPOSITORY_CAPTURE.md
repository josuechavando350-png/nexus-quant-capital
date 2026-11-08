# Lectura completa y acotada de la fuente propia

La captura de `repository_boundary` se usa también en los perfiles locales de
diagnóstico y cálculo restringido. Esta corrección conserva su formato y sus
presupuestos: 4,096 archivos, 20 MiB por archivo y 64 MiB de contenido total.

Los errores al enumerar una carpeta abortan ahora con `DIRECTORY_READ_FAILED`.
Antes, el comportamiento predeterminado de `os.walk` podía omitir esa carpeta.
Una segunda lectura que omitiera la misma carpeta tampoco demostraría que el
inventario estaba completo. La documentación oficial de Python describe este
[comportamiento de onerror](https://docs.python.org/3.12/library/os.html#os.walk).

Cada archivo regular debe conservar dispositivo, inodo, modo, tamaño y tiempos
de modificación/cambio entre su inspección inicial, el descriptor abierto, el
fin de la lectura y la nueva inspección de su ruta. La hora de acceso se excluye
porque leer puede modificarla. La lectura solicita únicamente el tamaño ya
admitido más un byte, para detectar crecimiento sin conceder a cada archivo
pequeño todo el máximo individual. Los descriptores se cierran también al fallar.

Se mantienen ambas capturas completas y la comparación de bytes/modos. El
inventario histórico y sus hashes no cambian por añadir estas observaciones.
Los metadatos son observaciones del mismo sistema; no constituyen una instantánea
atómica, autenticación del host, protección frente a toda carrera posible ni
aislamiento de código hostil. La adquisición continúa antes del filtro del
worker restringido. M1 permanece parcial.

## Regresiones

Trece pruebas usan archivos locales desechables. Los errores de enumeración
se inyectan explícitamente; las sustituciones y modificaciones de archivos
son operaciones reales en esos fixtures, situadas mediante hooks declarados.
No son fallos naturales observados en producción ni hallazgos de terceros.
Once regresiones fallaron con el lector anterior; las trece pasan con la
corrección. Se incluyen archivos estables y vacíos y cierre ante error de IO.
El módulo nuevo queda fijado al grupo 0 sin desplazar pruebas históricas.

La misma política de detener la lectura ante errores de enumeración se aplica
al inventario ejecutable de QA y a la captura para análisis de dependencias.
Sus exclusiones originales se conservan: ambos omiten cachés generados, y el
análisis de dependencias omite tests mientras QA los exige. Seis regresiones
adicionales comprueban ambos consumidores sobre fuentes propias; antes de la
corrección registraron siete fallos, contando sus subtests. Las fuentes leídas
no se importan ni ejecutan. El nuevo módulo también queda en el grupo 0.

El lector de expedientes `native_platform._tree` ya exige igualdad exacta de
archivos y carpetas con su inventario esperado; no se cambia en esta revisión.

La aceptación integral, su digest y sus límites se registran por separado al
completar las comprobaciones. No se deduce disponibilidad continua del número
de tests ni se ejecutan herramientas sobre destinos externos.
