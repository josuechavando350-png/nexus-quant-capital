# Importación PostgreSQL de colecciones completas

Estado: **migración ejecutada en PostgreSQL 18.6/Termux y evidencia auditada**.
Avance **43/100**. [Auditoría completa](AUDIT_COLLECTION_TERMUX_20261022.md).
El importador individual permanece byte a byte sin cambios.

## Qué resuelve

Un journal hijo puede conservar integridad local después de que el controlador
revoque toda la colección. El paquete nuevo vincula padre, ventanas, UUID de archivo,
recibo publicado y UUID de base. La migración candidata importa el conjunto en una
transacción y conserva una cuarentena permanente del padre. Sus vistas de lectura
excluyen todas las ventanas cuando el padre o cualquiera de sus hijos queda inválido.

`research/prepare_postgres_collection.py` sólo acepta el último recibo publicado
del run, obtenido bajo el lock del archivo local. Revalida la cadena de recibos,
objetos y transiciones, copia los bytes a una carpeta nueva y ejecuta el verificador
Rust sobre el controlador y la colección. Cada journal pasa además por el preparador
individual y el roundtrip Parquet real. No selecciona objetos huérfanos ni acepta
exports hijos como prueba suficiente de una colección.

Si el controlador está revocado, conserva y verifica su evidencia aunque falten
ventanas hijas. El paquete de revocación no necesita volver a transportar todas
las ventanas. Sus vínculos ya registrados permiten bloquearlas en la base sin
borrarlas. La revocación debe capturarse y enviarse explícitamente: no hay watcher
ni conexión automática con un servicio remoto.

```bash
python research/prepare_postgres_collection.py \
  --archive /ruta/miner-archive \
  --archive-id UUID-DEL-ARCHIVO-REVISADO \
  --run-id RUN-DEL-CONTROLADOR \
  --database-id UUID-DE-LA-BASE-REVISADA \
  --verifier /ruta/absoluta/nqc-miner \
  --output /ruta/nueva/paquete-coleccion
```

El manifiesto de finalización se escribe al final. Un fallo deja una carpeta
incompleta para inspección; no sobrescribe fuentes, paquetes previos o archivos
ajenos. Se comprueban otra vez los recibos, objetos, copias y binario antes de
completar el paquete. Los subpaquetes se ligan a sus hashes de request.

## Contrato SQL candidato

`infra/postgres_collection.sql` es una migración adicional, instalada después de
`postgres.sql` y `postgres_import.sql`. No modifica ninguno de esos archivos ni
concede permisos, crea roles o configura conexiones por sí misma.

| Objeto | Función |
|---|---|
| `collections` | Identidad del padre, UUID de archivo y bytes originales del marcador |
| `collection_windows` | Índice, run hijo y hash/count del journal completo e inmutable |
| `collection_receipts` | Recibos aplicados con sus bytes, snapshots y resultado |
| `collection_quarantine` | Revocación permanente del padre con motivo y hashes |
| `eligible_collection_ledger` | Filas consultables sólo mientras toda la colección sea elegible |
| `eligible_collection_outbox` | Mensajes correspondientes a filas elegibles y con payload idéntico |

La función `import_verified_collection(jsonb)` requiere READ COMMITTED y usa
SECURITY INVOKER. Adquiere el lock de colección y los locks de runs por orden de
clave, compartiendo el namespace de locks con el importador individual. Comprueba
la vinculación del recibo/snapshot y de los bytes de cada fuente antes de escribir.
Rust sigue siendo la autoridad semántica de los journals y de la continuidad.

Una extensión conserva las ventanas anteriores. Un recibo anterior devuelve
`stale`; no reduce la colección. Repetir el recibo actual vuelve a comprobar sus
journals. Un recibo diferente para la misma secuencia, una regresión o un hijo
quarantined bloquean al padre. Un UUID de archivo diferente se rechaza sin adoptar
esa identidad. La recepción inicial no exige importar todas las versiones anteriores:
el preparador verifica la historia local y envía el último snapshot completo.

El padre revocado nunca se reactiva al reenviar un paquete antiguo. Las vistas
también bloquean la colección si un hijo se invalida mediante el importador
individual antes de reenviar el paquete del padre. Las tablas originales son
evidencia retenida; leerlas directamente no aplica el criterio de elegibilidad.
Las vistas usan los permisos del usuario que consulta, sin elevarlos al propietario.

La transacción incluye padre, ventanas, outbox y recibo. Un error de SQL debe
revertir el conjunto. `quarantined` es un resultado que se debe comprobar y
**confirmar con COMMIT** para conservar la cuarentena. Un código de salida cero
de psql no significa que el contenido sea utilizable. `stale` tampoco certifica
la vigencia del paquete enviado. No hay relay ni entrega externa habilitada.

Estos contratos suponen un escritor cooperante que usa el preparador y las
funciones. Los permisos INSERT directos y el acceso administrativo a tablas
siguen siendo una frontera de confianza. No se afirma autenticidad de mercado,
frescura RPC ni protección contra un administrador que reescriba todo el historial.

## Límites y verificación offline

Se admiten hasta 64 ventanas completas por snapshot, 8 MiB de fuentes, 4 MiB de
journals acumulados, 10,000 registros acumulados, 2 MiB de manifest del snapshot
y 32 MiB de request. No hay fragmentación automática para superar los límites.
Las colecciones v2 deben ser históricas y de un scope, conforme al recolector actual.

La suite completa pasa **160 pruebas Python**: 14 del preparador, cuatro
del runner y 14 del auditor de evidencia, además de las 128 anteriores.
Usa Rust y Polars reales para verificar
bytes, extensión, revocación con hijos faltantes, identidad, integridad de archivo,
no reactivación, bloqueo, límites, fallos parciales y reproducibilidad del paquete.
No hay mock de PostgreSQL que se haga pasar por ejecución SQL.

También se preparó la colección histórica ya archivada: tres ventanas, ocho
registros y los mismos dos eventos anteriores. Sus 46 archivos se compararon
antes/después sin cambios. Se conservaron request y reportes en
`evidence/collection-import-preflight-20261022/historical-*`. El UUID de base usado
es sólo de pruebas; no identifica una instancia productiva. Son cero observaciones
RPC nuevas y cero incrementos de muestra económica.

pglast 8.7 acepta 13 sentencias y dos unidades PL/pgSQL de la migración. El runner
tiene sintaxis Bash válida y rechaza un entorno ajeno/root antes de crear la
instancia. El parser no prueba resolución de nombres, permisos, concurrencia ni
rollback. ShellCheck no está disponible. Rust no cambió ni se recompiló; se usa
el verificador auditado de `169b82f`, sin reclamar una nueva ejecución de sus 155 tests.

## Prueba ejecutada y auditada

[Instrucciones del runner de Termux](termux-collection.md). Ejecutó 33 aserciones
SQL, cinco denegaciones de permisos, concurrencia, interrupción antes del COMMIT,
reintento, reinicio y comparación de las doce tablas y las dos vistas.
Los 12 paquetes son artificiales: 11 de colección y uno de invalidación de hijo.
La clase histórica ejercita la admisión del recolector; no los convierte en datos
de mercado. El reloj fijo de recibos sólo hace reproducibles estos fixtures.

La auditoría del archivo retornado pasó y conserva todas las filas originales.
Faltan conexión operacional del recolector, transporte remoto, servicios de almacenamiento/broker/
workflow, observabilidad, operación prolongada y recuperación conjunta. Observador,
firma y gasto permanecen desactivados.

Referencias del contrato: [vistas y permisos del invocador](https://www.postgresql.org/docs/18/sql-createview.html)
y [snapshots de funciones VOLATILE](https://www.postgresql.org/docs/18/xfunc-volatility.html).
