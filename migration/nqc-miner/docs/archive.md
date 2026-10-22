# Archivo local de colecciones Miner

`research/archive_collection.py` conserva colecciones históricas verificadas,
sus configuraciones originales y exports Parquet de cada ventana. Publica un
snapshot solo mediante un recibo durable, después de verificar y sincronizar
sus archivos. Es un backend **local**; PostgreSQL, almacenamiento remoto y broker
siguen pendientes de integración.

## Uso

Usa el entorno de `research/requirements.txt` y el binario Miner auditado. El
archivo v2 tiene identidad UUID propia y exige un directorio nuevo bajo un padre
existente. Cada colección conserva su `run_id`, clase y configuración.

```bash
python research/archive_collection.py init \
  --archive /ruta/nueva/miner-archive --archive-id UUID-CANONICO-NUEVO
python research/archive_collection.py capture \
  --archive /ruta/miner-archive --state /ruta/coleccion-miner \
  --verifier /ruta/absoluta/nqc-miner
python research/archive_collection.py resolve \
  --archive /ruta/miner-archive --run-id RUN-DE-LA-COLECCION
```

`capture` exige que el recolector esté detenido en un límite durable. Adquiere
locks compartidos de lectura sobre los archivos `writer.lock` existentes de la
raíz y sus ventanas. Son los mismos locks de kernel que usa Rust; no escribe en
la fuente. Si un escritor está activo, falta el formato persistente del lock o
el sistema de archivos no soporta la exclusión, rechaza la operación. No detiene
ni modifica procesos para conseguir el lock.

## Publicación y lectura

- `owner.json` identifica el archivo como `nqc_miner_v1`; los directorios ajenos
  o incompletos no se adoptan. Un lock exclusivo serializa sus operaciones.
- `staging/` contiene únicamente trabajo pendiente. Se copia la evidencia con
  límites de tamaño y se verifica su journal de control en Rust. Para una
  colección activa se verifican todas las ventanas y se exportan a Parquet.
- El manifest registra hashes de cada archivo, fuentes originales, build del
  verificador y hash de los dos módulos Python que implementan la copia/export.
  Su SHA-256 da nombre a `objects/`. Se sincronizan archivos y directorios.
- `commits/` es una secuencia de recibos v2 enlazados por hashes y ligados al UUID
  del archivo; recibos de otro archivo se rechazan. Un hardlink atómico
  publica el recibo sin sobrescribir otro; la sincronización de su directorio
  precede al éxito. Solo objetos referenciados por recibos son visibles.
- `resolve` valida los recibos, objetos y transiciones antes de devolver el último
  snapshot de ese run. Un snapshot antiguo no representa el estado de la cadena
  en este instante: `live_chain_revalidated` permanece false.

Repetir exactamente la misma captura produce el mismo snapshot y devuelve el
recibo anterior. Una extensión conserva todos los bytes de las ventanas previas.
Eliminar una ventana ya archivada, reemplazar su historial o reutilizar el run
con otra configuración causa rechazo. Un directorio `staging` o un objeto sellado
sin recibo no acredita publicación. El reintento puede reutilizar un objeto
huérfano íntegro después de una interrupción. Los restos incompletos se conservan
para revisión; no existe borrado automático de evidencia ni cuota global de disco.

## Cuarentena

Si el journal de control contiene una invalidación válida para toda la colección,
`capture` publica un snapshot de revocación con la evidencia de control. Puede
hacerlo aunque falte una ventana hija: el control íntegro para ese propietario
se verifica independientemente mediante Rust. Los objetos anteriores se conservan
para análisis, pero `resolve` rechaza entregar esa colección como utilizable.

La revocación es permanente para su run. Reponer una copia anterior sin la
invalidación no la reactiva. El lector también verifica esa regla al recorrer
los recibos, incluso si alguien construye recibos con hashes coherentes. Continuar
requiere una colección nueva y una revisión de la causa del cambio de historial.
La revocación debe capturarse explícitamente: no se instala un watcher de fondo.

El prototipo v1 previo no vinculaba el UUID en cada recibo y no se adopta
automáticamente. Sus capturas se conservan como evidencia histórica verificable
con el código original; el gate de entrega actual exige v2. No se reescribe la
procedencia de un archivo para aparentar que fue producido por otra versión.

## Límites y condiciones

Admite colecciones v2 históricas de un scope; no mezcla clases ni importa ganancias
realizadas. Una colección activa vacía o con una ventana incompleta no se publica.
Los defaults son 64 MiB de fuentes y 100,000 registros por captura; máximos de
512 MiB y 1,000,000 registros. El manifest está limitado a 16 MiB y el archivo a
10,000 recibos. Copias, Parquet e históricos consumen espacio adicional a ese
límite de entrada. La verificación de lectura crece con todo el historial.

Requiere un directorio privado, almacenamiento local, rename/hardlink dentro del
mismo filesystem y soporte fiable de fsync y flock. Las pruebas cubren fallos
de publicación y SIGKILL antes del recibo; no certifican pérdida física de disco,
NFS ni manipulación por un administrador hostil. Los hashes no son firma ni ancla
externa: no detectan por sí solos la eliminación de todos los recibos finales y
sus copias externas. Un consumidor debe usar `resolve`, no escoger objetos antiguos
por su cuenta. No hay todavía migración, retención automatizada ni consumidor remoto.

## Verificación

```bash
PYTHONDONTWRITEBYTECODE=1 POLARS_MAX_THREADS=1 \
NQC_MINER_TEST_BINARY=/ruta/absoluta/nqc-miner \
python -m unittest discover -s research -p test_archive_collection.py -v
```

Las pruebas usan el verificador Rust y Polars reales, con bloques inventados y sin
RPC. La etiqueta histórica ejercita el contrato de admisión del recolector; no
convierte esos fixtures en observaciones del mercado.

La prueba base y el importador de journal individual se ejecutaron después en
Termux y sus evidencias se auditaron; véase `docs/AUDIT_IMPORT_TERMUX_20261022.md`.
La [preparación de colecciones para PostgreSQL](postgres-collection.md) ya usa
el último recibo publicado de este archivo, incluidos los recibos de revocación.
Su migración adicional está pendiente de ejecución y auditoría. Este archivo
local conserva su formato v2 y sus fuentes originales sin cambios.
