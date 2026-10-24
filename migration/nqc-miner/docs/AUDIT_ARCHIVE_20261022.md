# Auditoría del archivo local de colecciones — 22 de octubre de 2026

Avance global **40/100**. El punto nuevo corresponde al backend local de archivo,
con publicación durable, recuperación y propagación de cuarentena verificadas.
Infraestructura queda en **2/6**: un punto por el recolector previo y uno por este
archivo. Los cuatro restantes requieren las integraciones de servicios, operación
prolongada, observabilidad y recuperación conjunta. Ninguna salida A–D está cerrada.

## Fuente auditada y hallazgo cerrado

Código final publicado: `169b82f6a02de161f6c42c94af5c4a18e6f13165`.
Árbol: `ec9b2bf8bd2b05dfefe0e3612026a33ff2ba57ec`.
El verificador se compiló limpio con Rust 1.90.0, perfil debug, x86_64 Linux.
Identidad del build:
`a778d942b39a682fa114e2eb8df0d837c5178d26607824a5bcbaaddce071db63`.

La implementación Rust y Cargo.lock conservan sus hashes previos; los cambios
funcionales están en Python. No se agregaron dependencias de producción. El
archivo utiliza la biblioteca estándar POSIX y el Polars ya fijado por el proyecto.
Los avisos de mantenimiento del lock Rust documentados anteriormente siguen abiertos.

La revisión posterior al primer pase detectó que los recibos v1 no incluían el
UUID del archivo. Se corrigió en **v2**, vinculando ese UUID dentro del hash del
recibo y verificándolo al leer. Una regresión copia objetos/recibos a otro archivo
con UUID diferente y confirma el rechazo. No se adopta ni migra v1 silenciosamente.

El primer código `005ab8c`, su auditoría de 155 Rust/90 Python y su captura v1
se conservan como baseline. **No acreditan el gate final v2** ni se suman a los
conteos siguientes. Tampoco se reescriben sus identidades.

## Resultado de la auditoría final

`evidence/offline-archive-v2-20261022/summary.json`: **PASS**, entradas auditadas
sin cambios y ocho gates aprobados:

- **155 pruebas Rust**, cero fallidas/ignoradas; el contador conserva el helper
  de subprocess descrito en la auditoría anterior.
- **91 pruebas Python**, cero fallidas. Incluyen **22 pruebas nuevas** del archivo
  que ejecutan el verificador Rust y Polars reales sobre fixtures artificiales.
- Build, Clippy sin advertencias, rustfmt, identidad de fuentes/build, aislamiento
  del repositorio y alcance exclusivo de Miner aprobados.

Las regresiones cubren publicación y repetición idempotente, extensión de ventanas,
rechazo de rollback y de cambios en bytes previos, límites de recursos, journals
incompletos/truncados, symlinks, corrupción de snapshots/recibos, propietarios
ajenos y exclusión de escritores. La revocación se propaga aun si falta una ventana
hija; un recibo posterior no puede reactivar esa colección.

Se inyectó un fallo justo antes de publicar el recibo y se mató un subprocess en
ese punto con SIGKILL. En ambos casos el objeto sellado quedó invisible para el
lector; el reintento lo verificó y publicó una sola vez. Otra comprobación confirma
que el lock compartido Python impide al verificador Rust tomar el lock exclusivo
de la misma fuente. No se reclama certificación frente a pérdida física de disco.

## Evidencia histórica archivada

`evidence/local-archive-v2-20261022/execution.json`: **PASS** en inicialización,
captura, repetición y resolución. La colección de origen procede de la captura
real anterior `public-collector-20261022`:

| Comprobación | Resultado |
|---|---|
| Ventanas completas | 3 |
| Registros originales / Parquet | 8, idénticos byte a byte |
| Eventos históricos ya existentes | 2 |
| Nuevas lecturas RPC | 0 |
| Archivos de origen preservados | 17 de 17 |
| Recibos tras capturar y repetir | 1 |
| Binario antes/después | Sin cambios |

UUID del archivo: `2cd0dda0-e28e-4b17-a3f7-aba7d90ca291`.
Snapshot:
`7386fcc59c70a384bf90be94433e8bb0eda5ba5534aa694dc52c2026bf3a9170`.
Recibo:
`2fa445d6ea1a4dcbffef9fc96f1a87017a238f2d8bd4f8ee143c6371e844bede`.

La observación original conserva el commit `a1f6006`; el verificador de esta
exportación conserva `169b82f`. Son funciones e identidades distintas, registradas
sin sustituir ninguna. La repetición del archivo y la captura baseline no crean
observaciones económicas adicionales.

`archive-artifact-verification-20261022.json` comprueba los 57 archivos de la
captura, los ocho registros Parquet y los hashes de la auditoría. Los marcadores
de directorio documentados en `archive-packaging-20261022.json` conservan la
estructura vacía al versionar; no son recibos ni modifican los bytes capturados.

La comprobación `archive-git-delivery-20261022.json` exportó el árbol Git a una
carpeta temporal independiente: los 57 archivos de cada captura conservaron sus
hashes y el lector v2 resolvió el mismo recibo desde la copia exportada. Los
17 archivos de la colección original permanecieron intactos.

## Aislamiento y límites pendientes

Todos los cambios permanecen en `migration/nqc-miner/`. Se preservaron los 531
archivos originales y los 106 workflows heredados desactivados. Cero cambios en
archivos del observador, cero workflows activos, presupuesto cero y puente/firma
desactivados. No hubo operaciones sobre el observador ni recursos de clientes.

PostgreSQL no se ejecutó: faltan herramientas de compilación y el entorno expone
únicamente UID 0, sin permitir el proceso sin privilegios que requiere initdb.
No se sustituyó su prueba de transacciones por mocks ni se acreditó ese gate.
No se provisionaron bases, servicios remotos o suscripciones. El registro técnico
de la limitación está en `storage-environment-20261022.json`.

El archivo exige una pausa durable del recolector y captura explícita de las
invalidaciones; no instala vigilancia de fondo. Quedan almacenamiento remoto,
Postgres/ClickHouse/Redpanda/Temporal, retención y cuotas, operación prolongada,
reproducción hermética y las validaciones económicas/prospectivas del PDF.
Los hashes locales no sustituyen una firma o ancla externa contra reescritura
administrativa o eliminación de un sufijo completo del historial.

Operación, formato, recuperación y límites: `docs/archive.md`.
