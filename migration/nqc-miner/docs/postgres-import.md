# Preparación e importador PostgreSQL candidato

Estado: **preparación offline verificada; migración SQL pendiente de ejecución**.
El avance global permanece en **41/100**. La prueba anterior de Termux acredita
el DDL base, no esta función ni sus nuevas tablas. Ningún servidor está conectado
por este código y no se han creado roles, permisos, servicios o credenciales.

## Preparador offline

`research/prepare_postgres_import.py` copia un journal v2 a una exportación nueva,
lo verifica con el binario Rust real, conserva el Parquet y genera `request.json`
y `import.sql`. El archivo `manifest.json` se escribe al final. No ejecuta SQL.
El límite es 4 MiB de journal y 10,000 registros; el segmento empieza en cero y
es un prefijo completo. No implementa paginación ni importación incremental por
fragmentos que comiencen en otra secuencia.

```bash
python research/prepare_postgres_import.py \
  --state /absolute/path/to/miner-journal \
  --output /absolute/path/to/new-import-directory \
  --verifier /absolute/path/to/nqc-miner \
  --database-id UUID-DE-LA-INSTANCIA-DEDICADA
```

El UUID debe ser el de la instancia revisada, leído de `import_identity` después
de instalar la migración. No se deduce del nombre de la base. El UUID del ejemplo
de pruebas es artificial y no identifica una base desplegada.

La fuente original no se modifica. Se rechazan carpetas existentes, solapamientos,
symlinks, propietarios ajenos, v1, corrupción y cambios en la copia después de su
verificación. Los datos variables entran al SQL como hexadecimal. Se conservan
los bytes originales de owner/config y cada línea, incluido su salto final.
El hash canónico del propietario usado por Rust es distinto del hash de los
bytes originales cuando cambia el formato JSON; ambos quedan documentados.

La autenticidad de mercado permanece sin certificar. El binario verificador y
el preparador son dependencias locales de confianza; sus hashes identifican
los archivos, no los autentican mediante firma. Los ejemplos son sintéticos.

## Migración candidata y contrato de la transacción

`infra/postgres_import.sql` se instala una sola vez, por el dueño del esquema,
después del DDL base, en una instancia nueva dedicada a Miner. Conserva intacto
`infra/postgres.sql` y su evidencia anterior. Añade dos tablas y una función
`SECURITY INVOKER`, sin conceder permisos automáticamente:

- `import_identity`: identidad UUID generada por PostgreSQL y versión del contrato.
- `import_quarantine`: revocación permanente del run, con motivo y hashes entrantes.
- `import_verified_journal(jsonb)`: validación del transporte, comparación y escritura.

La función exige la base `nqc_miner_v1`, el UUID esperado y READ COMMITTED. El
diseño toma un advisory lock transaccional por run antes de leer el estado
existente. Todas las llamadas participantes deben usar esta función; un escritor
con INSERT directo que ignore el lock está fuera de esta garantía propuesta.
La validación de concurrencia sigue pendiente.

El plan compara owner/config originales y, para cada secuencia existente,
todos los hashes, metadatos y bytes de la línea. Un prefijo anterior idéntico se
acepta sin borrar la cola posterior. Las nuevas líneas y sus mensajes outbox se
insertan en la misma transacción. No hay `ON CONFLICT DO NOTHING` que oculte una
diferencia. Se comprueba también la correspondencia ledger/outbox existente.

Los conflictos dejan una fila de cuarentena sin sustituir datos previos. Un
registro `invalidated` se conserva y marca todo el run en cuarentena; el diseño
es deliberadamente conservador. Una cuarentena existente nunca se borra ni se
reactiva mediante el importador. Los lectores futuros deben excluir esos runs.
El outbox sigue con entrega deshabilitada y no existe un relay.

La función devuelve `quarantined` en lugar de lanzar una excepción por conflicto:
una excepción abortaría también la escritura de la cuarentena. El ejecutor debe
confirmar el COMMIT y revisar ese resultado; **un proceso psql con código cero
no significa que el run haya sido aceptado**. Los errores SQL inesperados abortan
la transacción. Cualquier futura ejecución requiere `psql -X -v ON_ERROR_STOP=1`,
verificar hashes del paquete y conservar salida y estado final. No se proporciona
un comando de conexión a una instancia existente ni se configura un servicio.

## Auditoría y pendientes

Trece pruebas del preparador pasan usando el verificador Rust y Polars reales:
bytes y transporte, determinismo, hash canónico frente a formato original,
invalidaciones, journal vacío, rechazo de v1, UUID incorrecto, namespace/build
ajenos, corrupción detectada por Rust, alteración posterior a la verificación,
aislamiento de rutas, límites y caracteres que intentarían escapar del SQL.

El parser pglast 8.7 acepta las 11 sentencias SQL y las dos unidades PL/pgSQL.
Es una revisión sintáctica: no prueba resolución de nombres/tipos ni comportamiento
de tablas, permisos, rollback, UUID, duplicados, cuarentena o concurrencia.
El motor PostgreSQL no se ejecutó para esta migración.

La siguiente prueba debe crear una instancia desechable con roles separados y
ejecutar: importación/repetición/prefijo antiguo/extensión, conflicto de owner y
línea, invalidez tardía, huecos/outbox inconsistente, error después de insertar
ledger, UUID ajeno, permisos, dos importaciones concurrentes, caída del cliente
y reinicio. Se deben auditar los bytes retornados antes de sumar avance.
La importación de colecciones requiere además propagar las revocaciones del
controlador padre a todas sus ventanas; este módulo recibe un journal individual.

Referencias de diseño: [locks transaccionales](https://www.postgresql.org/docs/18/explicit-locking.html)
y [snapshots de funciones VOLATILE](https://www.postgresql.org/docs/18/xfunc-volatility.html).
Estas reglas documentadas sustentan el diseño; no sustituyen su prueba real.
