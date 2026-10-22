# Prueba del importador en Termux

Estado: **ejecución completada en Termux y evidencia auditada**.
Avance global: **42/100**. El archivo original y las 35 comprobaciones, permisos,
concurrencia, interrupción, bytes persistidos y reinicio están verificados en
[la auditoría runtime](AUDIT_IMPORT_TERMUX_20261022.md). El servidor de prueba
terminó apagado. Las instrucciones siguientes se conservan para reproducir el
experimento; no es necesario repetirlo para esta entrega.

## Archivo y ejecución

`scripts/nqc-miner-import-check.sh` es autocontenido. Requiere Termux nativo,
usuario ordinario y PostgreSQL **18.6**, ya presentes en el teléfono revisado.
No instala paquetes ni descarga dependencias. No requiere Python, Rust o Polars
en el teléfono: los 16 casos de entrada ya fueron verificados por Rust al
construir el paquete. Esos casos son artificiales y de clase `synthetic`.

Después de guardar el archivo con ese nombre en Descargas:

```bash
(
set -eu
MINER_IMPORT_FILE="/sdcard/Download/nqc-miner-import-check.sh"
printf '%s  %s\n' \
  '8a73eb9860a82193353df4b23f5d0abc08524e4430f42d7a541c9def4a8793c5' \
  "$MINER_IMPORT_FILE" | sha256sum -c -
bash "$MINER_IMPORT_FILE"
)
```

Dejar Termux abierto hasta `MINER IMPORT: pass` o `failed`. En ambos casos el
runner intenta apagar su servidor, empaqueta los logs y los copia a un archivo
nuevo de Descargas, cuyo nombre empieza por `nqc-miner-import-evidence.` y termina
en `.tar.gz`. La línea `ADJUNTA ESTE ARCHIVO AL CHAT` indica el archivo a devolver.
Si el almacenamiento compartido no permite la copia, `Results:` conserva la ruta
original. No borrar ni editar la evidencia aunque una prueba falle.

## Alcance y separación

Se crea `~/nqc-miner-import.XXXXXX` mediante `mktemp`, con permisos privados.
El cluster, socket, roles, base y logs pertenecen exclusivamente a esa instancia
nueva. No se busca ni se conecta ningún servicio existente. TCP está deshabilitado;
el puerto lógico 55433 se usa sólo en el socket privado. Las credenciales y opciones
libpq heredadas relevantes se descartan. Se usa un archivo de contraseñas inexistente
dentro de la carpeta propia y autenticación peer.

El UUID de base se fija deliberadamente a un valor sintético después de instalar
la migración en el cluster nuevo, para ejecutar solicitudes reproducibles. Ese
UUID no identifica infraestructura productiva. Los permisos concedidos existen
sólo en la instancia temporal; el rol escritor no tiene permisos de superusuario.

Los procesos concurrentes y la sesión interrumpida se identifican dentro de esta
misma instancia. La prueba termina una sesión propia antes del COMMIT mediante
`pg_terminate_backend`; no termina el servidor ni procesos de otros proyectos.
Ese caso debe producir un FATAL de terminación administrativa en los logs. Es una
inyección prevista, no una prueba de pérdida eléctrica ni de SIGKILL del servidor.

Al salir, incluso tras un error, el trap intenta apagar exclusivamente el cluster
creado. No usa `pkill`, no cambia paquetes/configuración compartida y no lee datos
del Observador. Termux comparte UID y paquetes entre sesiones; no se afirma
aislamiento frente a un proceso hostil con el mismo UID.

## Comprobaciones ejecutadas

- 35 aserciones SQL: identidad del escritor, permisos, UUID, hash del transporte,
  importación/repetición/extensión/prefijo anterior, bytes originales, journal
  vacío, aislamiento de transacción, conflictos, cuarentena permanente,
  invalidación tardía, huecos/outbox inconsistente, rollback y controles desactivados.
- Cuatro escrituras prohibidas al rol limitado y una ejecución prohibida al ajeno.
- Dos importadores realmente bloqueados a la vez por un tercer cliente; después,
  una importación y una repetición sin duplicados. El holder limpia el snapshot
  de estadísticas en cada consulta para observar las esperas actuales.
- Interrupción de una sesión tras insertar y antes del COMMIT: ausencia de filas
  comprometidas y posterior repetición exitosa.
- Reinicio ordenado y comparación byte a byte de las ocho tablas del contrato.
  Apagado final, manifiesto SHA-256 y archivo de evidencia conservado.

Las eliminaciones, cambios de payload y trigger de fallo que aparecen en los casos
son inyecciones sobre fixtures del cluster desechable. El trigger se elimina tras
su prueba. Algunos runs quedan intencionalmente en cuarentena o con filas faltantes;
el auditor debe compararlos con el caso correspondiente, no atribuirlos a datos reales.

## Auditoría de preparación

La suite completa pasa **116 pruebas Python**: las 112 anteriores y cuatro nuevas
sobre fuentes/fixtures incluidos, reproducción determinista, sintaxis y guardia de
entorno de Bash, e integridad de los archivos empaquetados. Se usa el verificador
Rust real para los 16 fixtures; no se simula un servidor PostgreSQL.

`bash -n` pasa. pglast 8.7 acepta las entradas SQL/PLpgSQL: 14/1 unidades en el DDL
base, 11/2 en el importador, 23/0 en fixtures, 59/4 en casos y 1/1 en el holder.
Esto no comprueba la resolución de nombres, permisos ni comportamiento runtime.
ShellCheck no está disponible y no se reclama esa verificación.

El DDL y el importador incluidos coinciden byte a byte con la fuente publicada
`a1d0f150633fda2e5142fe59c0beda924c7bd830`; Rust y su lock no cambiaron ni se
recompilaron. La evidencia offline se conserva en
`evidence/termux-import-preflight-20261022/`. El resultado runtime posterior se conserva en
`evidence/termux-import-20261022/`. Los estados pendientes dentro de la evidencia
de preparación son históricos y no se reescriben.
