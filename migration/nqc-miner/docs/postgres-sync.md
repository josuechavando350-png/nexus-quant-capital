# Sincronización local del recolector con PostgreSQL

Estado: implementación y pruebas offline completas; **conexión del cliente nuevo
a PostgreSQL real pendiente**. Avance global **43/100**, sin crédito adicional.
La migración SQL conserva su auditoría anterior; este bloque no modifica SQL,
Rust, archivo local, preparadores ni evidencia histórica.

## Ciclo implementado

`research/sync_postgres_collection.py` toma una colección propia pausada, verifica
su propietario y el UUID del archivo, publica un snapshot, prepara el último
recibo con Rust/Polars y lo entrega mediante `scripts/collection_transport.py`.
Cada intento usa un directorio nuevo con metadatos, captura, paquete, resultado
de entrega y métricas locales. No crea un servicio de fondo ni consulta RPC.

Después de preparar, vuelve a comprobar el último recibo y los bytes de la fuente.
Durante el envío mantiene los locks cooperativos del archivo, del controlador y
de las ventanas, en ese orden. Un recibo más reciente, un escritor activo o un
cambio de fuente impiden entregar el paquete antiguo. La revocación del padre
puede enviarse sin disponer de las ventanas hijas.

No hay cursor local que permita saltarse una comprobación. Repetir un ciclo
vuelve a verificar y enviar el estado actual; PostgreSQL decide si es repetición,
extensión, recibo antiguo o cuarentena. Un resultado anterior no bloquea una
revocación posterior. Los intentos incompletos se conservan y no se adoptan.

```bash
python research/sync_postgres_collection.py \
  --state /ruta/coleccion-miner-pausada \
  --archive /ruta/archivo-miner \
  --output /ruta/nueva/operacion-001 \
  --verifier /ruta/absoluta/nqc-miner \
  --target /ruta/destino-local-revisado.json \
  --run-id IDENTIDAD-EXACTA-DEL-CONTROLADOR
```

Se requiere el entorno de investigación existente, Polars y el verificador Rust.
La base debe estar instalada por separado. El comando no instala migraciones,
crea roles, modifica permisos ni descubre servicios existentes.

## Destino explícito y limitado

El JSON de destino requiere exactamente estos campos:

| Campo | Valor requerido |
|---|---|
| `schema` | `nqc-miner-local-postgres-target-v1` |
| `database_id` / `archive_id` | UUID canónicos, no cero, revisados explícitamente |
| `socket_directory` | Directorio absoluto privado, 0700, del UID actual |
| `port` | Entero entre 1024 y 65535; sólo identifica el socket |
| `login_user` | Nombre del usuario actual del sistema |
| `psql` / `psql_sha256` | Ejecutable absoluto sin symlinks y su hash revisado |

El cliente sólo admite un socket Unix real del mismo UID. La base es siempre
`nqc_miner_v1`; el rol de trabajo, `nqc_miner_import_writer`. No acepta URLs,
TCP, contraseñas, nombres de bases alternativos o configuración de servicios.
Se descartan variables `PG*`/`PSQL*` heredadas; psql no lee archivos de inicio
ni solicita contraseña. El socket y el ejecutable se verifican antes de enviar.

`requirepeer` comprueba el usuario del proceso servidor. `require_auth=none`
exige ausencia de reto de autenticación, compatible con peer; por sí solo no
demuestra que el servidor use peer. La prueba nativa conserva y revisa su HBA.
Un proceso hostil con el mismo UID está fuera de esta frontera de confianza.

La sesión fija `search_path=pg_catalog` y timeouts, también para la lectura
posterior a COMMIT. Antes de llamar al importador comprueba versión 18.6, UUID,
durabilidad, ausencia de TCP, rol limitado y hashes exactos de las dos funciones
SQL auditadas. Rechaza permisos UPDATE/DELETE/TRUNCATE del escritor. No vuelve
a certificar un administrador ni toda la configuración de una instalación ajena.

## Confirmación y recuperación

El cliente ignora `import.sql`: genera una sentencia fija con el payload codificado
como hex. El paquete debe estar completo y sus hashes, UUID, padre, recibo y
snapshot deben coincidir. Es una frontera de transporte para salida del preparador
de confianza; no reemplaza su verificación semántica Rust/Polars.

Se requiere salida exitosa del cliente, respuesta válida del importador y una
segunda respuesta **después de COMMIT**. Ésta vuelve a leer la identidad, el
recibo guardado, el hash jsonb del request, la última secuencia y la cuarentena.
La respuesta previa a COMMIT por sí sola jamás acredita persistencia.

| Resultado | Código CLI | Significado |
|---|---:|---|
| `applied` | 0 | Transacción confirmada, recibo exacto presente y vigente en la lectura posterior |
| `unknown` | 2 | No se puede confirmar; puede haber ocurrido COMMIT. Reintentar en un directorio nuevo |
| `quarantined` | 3 | Estado bloqueado confirmado; se conserva la cuarentena, no se trata como datos utilizables |
| `superseded` | 4 | Existe una secuencia posterior; no se acredita vigencia del paquete enviado |

No se revierten cuarentenas por devolver código no cero. Timeout, pérdida de
conexión, respuesta truncada, identidad incorrecta o fallo de disco nunca generan
un marcador local de éxito. El intento durable empieza en `unknown`; si el proceso
muere después de COMMIT y antes de guardar resultado, repetir reconcilia con la base.

Si un escritor ignora los locks y altera la fuente después del envío, se conserva
el acuse ya recibido pero el ciclo queda `unknown`, sin afirmar fuente actual.
La lectura confirmada tampoco prueba vigencia futura ni autenticidad de mercado.

Límites: request/jsonb de 32 MiB, 64 ventanas, 10,000 registros; hasta 120 segundos
por cliente y 64 KiB por cada flujo de salida. Se matan únicamente el proceso psql
creado por el intento y sus hijos. Los mensajes crudos del servidor no se publican:
se guardan códigos SQLSTATE, hashes y tiempos. `metrics.prom` describe un intento,
sin servidor de métricas ni observabilidad continua.

## Evidencia y límite de las pruebas

Las pruebas del ciclo usan archivo, Rust y Polars reales. La frontera de base de
datos usa un cliente falso explícito para inyectar respuestas, cortes y errores.
El entorno del agente no permite crear sockets: sus metadatos también se modelan
en esas pruebas, y una prueba separada confirma rechazo de un archivo ordinario.
No se presentan estos tests como una ejecución PostgreSQL.

La batería nativa preparada en [termux-sync.md](termux-sync.md) usa el mismo
cliente y PostgreSQL real, con 17 comprobaciones, sin simular el servidor.
El teléfono sólo necesita Python estándar para esa batería; los paquetes ya
verificados se incluyen. No ejecuta allí el verificador Rust de Linux ni acredita
el ciclo completo como servicio persistente.

Quedan transporte remoto, almacenamiento/broker/workflows, operación prolongada,
recuperación conjunta y validación económica. Observador, firma y gasto continúan
desactivados. Este bloque mantiene el avance en 43/100 hasta nuevas evidencias.

Referencias primarias revisadas: [psql](https://www.postgresql.org/docs/18/app-psql.html),
[SET ROLE](https://www.postgresql.org/docs/18/sql-set-role.html),
[parámetros libpq](https://www.postgresql.org/docs/18/libpq-connect.html) y
[variables libpq](https://www.postgresql.org/docs/18/libpq-envars.html).
