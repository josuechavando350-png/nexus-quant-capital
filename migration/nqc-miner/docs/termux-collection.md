# Prueba de colecciones en Termux

Estado: **runner preparado y verificado offline; ejecución y auditoría de resultados
pendientes**. Avance global **42/100**. La prueba anterior acredita journals
individuales; no se reutiliza para acreditar esta migración nueva.

Guardar `scripts/nqc-miner-collection-check.sh` en Descargas con ese nombre.
Requiere el Termux nativo y PostgreSQL 18.6 ya usados. No instala paquetes, descarga
dependencias ni necesita Rust, Python o Polars en el teléfono.

```bash
(
set -eu
MINER_COLLECTION_FILE="/sdcard/Download/nqc-miner-collection-check.sh"
printf '%s  %s\n' \
  'a4257cb34557600579f7d33c50cfa9b9bfca6d7f5f136fc3abc7b39d12f4c0d7' \
  "$MINER_COLLECTION_FILE" | sha256sum -c -
bash "$MINER_COLLECTION_FILE"
)
```

Mantener Termux abierto. Al terminar, devolver el archivo que señale
`ADJUNTA ESTE ARCHIVO AL CHAT`, tanto si muestra `MINER COLLECTION: pass` como
si muestra `failed`. Su nombre empieza por `nqc-miner-collection-evidence.` y
termina en `.tar.gz`. El runner intenta detener su servidor y conservar logs
también cuando una comprobación falla. No editar ni borrar evidencia de fallo.

Se crea una carpeta privada nueva `~/nqc-miner-collection.XXXXXX`. Usa un socket
propio, sin TCP, con puerto lógico 55434, roles locales y credenciales de entorno
descartadas. No descubre, adopta o modifica servicios existentes. No usa `pkill`
ni cambia configuración compartida. Todo el contenido de prueba es artificial.

La prueba incluye:

- 33 aserciones de importación de dos ventanas, extensión, repetición, rechazo
  de recibos viejos/ajenos/alterados, revocación de padre y bloqueo de todos los hijos.
- Conservación de bytes tras cuarentena, revocación sin hijos presentes,
  invalidación independiente de un hijo, conflicto de recibo y no reactivación.
- Fallo de outbox en la segunda ventana: ausencia del padre y de la primera
  ventana tras rollback, seguida de reintento correcto.
- Cuatro mutaciones prohibidas al escritor y una llamada prohibida al rol ajeno.
- Dos importadores realmente bloqueados en el mismo lock de colección: una
  inserción y una repetición, sin duplicados.
- Terminación deliberada de una sesión propia tras importar y antes de COMMIT.
  El FATAL administrativo de ese backend es esperado. No se mata el servidor.
- Reinicio ordenado con comparación byte a byte de doce tablas y dos vistas,
  apagado final, hashes y archivo de resultados.

La instancia se comparte con el UID de Termux; no es aislamiento ante un proceso
hostil con el mismo UID. La prueba de interrupción no simula pérdida eléctrica.
El archivo retornado deberá contrastarse con fuentes y fixtures antes de acreditar
runtime. No hay conexión productiva, RPC, firma, gasto o integración con Observador.
