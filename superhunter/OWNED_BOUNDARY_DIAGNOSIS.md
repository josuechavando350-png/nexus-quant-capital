# Diagnóstico contrastado de dos fallos operativos propios

Sucesor de PR #95 (`b2933041fdc7ad7c0c67254c475a82c59bad78a8`).

La captura de #95 conserva una revisión exitosa. Este experimento nuevo
conserva también rechazos, stderr privado e intentos inconclusos. El padre
prepara una copia temporal con los bytes y modos Git del checkout revisado.
Solo cambia `migration/source-manifest.json` dentro de esa copia. Los archivos
copiados nunca se ejecutan; el worker importa el revisor desde el código original.

## Experimento fijo

| Ensayo | Intervención en la copia | Resultado esperado |
| --- | --- | --- |
| baseline | Estado original | exit 0, revisión correcta |
| missing-file | Retirar el archivo fijo | exit 2, HISTORICAL_TREE_CHANGED |
| restored-file | Restaurar sus bytes y modo | exit 0, revisión correcta |
| changed-mode | Conservar bytes, cambiar modo Git a ejecutable | exit 2, HISTORICAL_TREE_CHANGED |
| restored-mode | Restaurar bytes y modo original | exit 0, revisión correcta |

El inventario de archivos completo antes y después de cada proceso debe
coincidir con la intervención exacta. Los deltas de los controles restaurados
deben ser vacíos. El inventario recoge SHA256 y modo Git; no registra inode,
propietario, permisos completos de directorios ni estado de todo el host.

Los dos rechazos tienen el mismo código y causas distintas. Por eso se refuta
la hipótesis de que el código solo identifica un archivo faltante. El control
de modo también refuta que se necesite modificar contenido para que falle
la revisión. La restauración apoya las dos explicaciones en este experimento
fijo; no demuestra causalidad general ni un incidente de terceros.

## Conservación de resultados inesperados

El primer resultado inesperado o timeout detiene la secuencia. Se conservan
los streams acotados y la observación parcial como
`OWNED_FAULT_DIAGNOSIS_INCONCLUSIVE`; ninguna hipótesis se promueve. El revisor
rechaza una secuencia que intente esconder un fallo inesperado con restauraciones
posteriores. CLI devuelve **1** tanto al crear como al verificar un inconcluso.

El timeout no inventa un código de terminación: registra `returncode: null` y
`timed_out: true` después de que el supervisor existente limpie el grupo propio.
Un error antes de lanzar, pérdida de supervisión, presupuesto excedido,
fuente/copia cambiante o expediente inválido se rechaza con CLI **2**. No se
presenta ese rechazo como una captura exitosa ni se garantiza conservar fallos
del propio sistema de archivos.

Solo cinco observaciones esperadas y controles completos producen
`OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB`, con CLI **0**. No significa hallazgo,
vulnerabilidad, autenticación independiente o cierre del sistema Hunter.

## Interfaz

```bash
python3 -B -m superhunter diagnose-owned-boundary \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE --out /ruta/externa/experimento
python3 -B -m superhunter verify-owned-boundary-diagnosis \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE \
  --experiment-anchor SHA256_EXTERNO_DE_COMPLETE \
  --bundle /ruta/externa/experimento
```

Las mayúsculas representan los argumentos SHA reales, obligatorios. El digest
es SHA256 de `canonical(quality.source_snapshot())`; la creación devuelve
el ancla del marcador COMPLETE. Conservarla por separado.

El verificador no ejecuta ni repara nada: comprueba anclas, esquema cerrado,
streams, aritmética y orden monotónico, inventarios y diagnóstico regenerado.
Vuelve a leer evidencia y checkout al terminar. El inventario incluye documentos;
una edición posterior puede invalidar la comparación con la evidencia original.

No hay argumentos para targets, comandos o intérpretes arbitrarios. Cada worker
mantiene 30 s de espera, 15 s CPU, 256 MiB de espacio virtual y 64 KiB por archivo
de salida. Son límites locales, no un sandbox del SO ni presupuestos agregados.
Los relojes pertenecen al mismo host. Identidad del intérprete, SHA y anclas no
prueban ejecución histórica ni productor independiente. El stderr se conserva
en el expediente privado y no se imprime en el diagnóstico ni en la consola.

## Pruebas y continuidad

86 focales PASS, incluidas 24 nuevas. Se ejecutan procesos reales para los dos
fallos/restauraciones y CLI. Las pruebas de timeout/error de infraestructura usan
inyecciones explícitas: no se atribuye a ellas una caída real del host. Se cubren
alteraciones de evidencia, falsas hipótesis, promoción de garantías, mezcla de
ensayos, cambios durante lectura y resultados inconclusos sin elevarlos a éxito.

Los resultados completos y la aceptación del commit exacto se conservan en
CONTINUATION.md y `SUPERHUNTER_DIAGNOSTICO_FALLOS_PROPIOS_20261108.zip`.
Los originales históricos permanecen intactos. No cierra M1 ni cambia el
indicador de 1/6 hitos globales cerrados; no revalida perfiles EVM o Slither.

La suite completa terminó con 2,956 PASS, 2,932 anteriores retenidas en sus
mismos grupos y 24 nuevas. Verificación separada sin SDK PASS. El verificador
histórico `migration/verify_isolation.py` devuelve 1 por `unreviewed root file`
en PR #95 y en esta versión: su contrato original no admite la estructura
ampliada. Se conserva sin cambios; este bloqueo preexistente no se oculta ni
se convierte en PASS. El revisor complementario de frontera conserva los 642
archivos históricos. No hay recertificación original de NQC.
