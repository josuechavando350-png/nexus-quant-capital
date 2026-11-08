# Captura observable de un proceso propio

Sucesor de PR #94 (`8e39da34033065a203207b1df962a4762de4180e`).

`capture-owned-boundary` ejecuta un único worker fijo que revisa, en lectura,
los árboles históricos y las fronteras de este checkout. El padre recoge su
salida real y código de terminación, comprueba el mismo resultado antes y
después y escribe un expediente privado con marcador de finalización.
El formato `superhunter-owned-boundary-capture-v1` identifica observación
propia. No convierte JSON generado en una supuesta exportación de journald.

## Uso

Desde el checkout, con el intérprete local que satisface las dependencias:

```bash
python3 -B -m superhunter capture-owned-boundary \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE --out /ruta/externa/captura
python3 -B -m superhunter verify-owned-boundary-capture \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE \
  --capture-anchor SHA256_EXTERNO_DE_COMPLETE \
  --bundle /ruta/externa/captura
```

Los valores SHA son argumentos obligatorios, no valores de ejemplo ejecutables.
El digest de fuentes es SHA256 de `canonical(quality.source_snapshot())`.
La creación devuelve el ancla del marcador `COMPLETE.json`: conservarla por
separado. La verificación no vuelve a ejecutar el worker. CLI 0 indica captura
creada o consistencia verificada, según el campo `status`; CLI 2 rechaza.

## Observaciones y límites

- Un UUID nuevo distingue cada captura. No identifica a una persona o máquina.
- La salida canónica real conserva los 642 archivos históricos, sus árboles,
  el inventario completo de fuente/documentos y las limitaciones del revisor.
- Se recoge monotónico inicial, tiempo del host inicial, supervisión del hijo,
  tiempo del host final y monotónico final, en ese orden. La resta exacta en
  nanosegundos mide lanzamiento, espera y limpieza; no mide CPU ni hora UTC cierta.
  Un retroceso del reloj se conserva explícitamente; no se corrige ni oculta.
- Se registra SHA256 del ejecutable Python usado y su versión. Esto no fija
  bibliotecas compartidas ni autentica el host. El verificador puede usar otro
  intérprete compatible: no presenta la identidad declarada como atestación.
- Worker fijo, sin argumentos de target/comando/intérprete, stdin cerrado,
  entorno mínimo, directorio temporal privado, sesión propia y supervisión
  existente antes de liberar al líder. Presupuestos: 30 s de espera, 15 s CPU,
  256 MiB de dirección virtual y 64 KiB por archivo de salida. No son un sandbox
  del sistema operativo ni un límite agregado de procesos o escritura.
- Solo una salida exitosa, acotada y sin stderr produce expediente positivo.
  Timeout, fallo, salida distinta, cambios observados de fuentes o intérprete
  abortan. Los errores CLI omiten rutas, órdenes y contenido privado.
- El consumidor exige esquema cerrado, aritmética exacta, inventario exacto,
  hashes y ancla externa, límites sin promociones y reporte regenerado. Revisa
  nuevamente evidencia y fuentes al terminar. Cambios de documentos también
  pueden invalidar la comparación porque el inventario del revisor los incluye.

Un expediente coherente creado manualmente con una nueva ancla no demuestra
ejecución histórica. Las pruebas incluyen ese contra-control explícito: editar
coherentemente un reloj no lo autentica. Host comprometido, cambios transitorios
restaurados entre lecturas y productor independiente permanecen fuera de esta
garantía. No se afirma que los archivos capturados prueben un incidente.

## Validación

26 pruebas nuevas, incluidas adquisición real, CLI en procesos separados,
verificación sin ejecución, alteración de ancla/salida/origen/tiempos/garantías,
rechazo de symlinks, presupuestos, fallos y cambios durante lectura. Los controles
que inyectan fallos o editan tiempos están identificados como controles de prueba;
no representan eventos observados del host.

62 focales PASS (captura, supervisor y frontera). El resultado de QA completa y
la aceptación final con su identidad exacta se registran en CONTINUATION.md y en
el expediente `SUPERHUNTER_CAPTURA_PROCESO_PROPIO_20261108.zip`.

Este incremento cubre adquisición de una operación propia pequeña. No cierra
M1 completo, no añade objetivos remotos ni prueba vigilancia continua. La métrica
de hitos globales cerrados sigue en 1/6; no es porcentaje de código o esfuerzo.
