# Auditoría PostgreSQL en Termux — 22 de octubre de 2026

Avance global **41/100**, desde 40/100. Infraestructura queda en **3/6**: un punto
por el recolector, otro por el archivo local y uno por ejecutar y auditar el
contrato PostgreSQL sobre un motor real. Los tres puntos restantes requieren el
importador y las integraciones de almacenamiento/broker/workflows, operación
prolongada, observabilidad y recuperación conjunta. Ninguna salida A–D se cierra.

## Origen e integridad

El usuario ejecutó el runner en su teléfono, sobre PostgreSQL **18.6**, Termux
nativo **aarch64**, y devolvió el archivo de evidencia. La ejecución comenzó el
22 de octubre a las **15:16:17, hora de Ciudad de México**. Los logs muestran el
apagado final a las 15:16:22. Es una prueba funcional breve, no una medición de
capacidad o disponibilidad prolongada.

Runner y casos publicados: commit `6a89668b5c326a0e120288a0631204ec4a082827`, árbol
`dd93929dea6ca0093fa99976a9ad30d36a9026ac`. El auditor conserva esa identidad;
no atribuye la ejecución del teléfono a los commits documentales posteriores.

| Objeto | SHA-256 |
|---|---|
| Archivo recibido, 20,793 bytes | `0e842116cff766c1f51249aa94de022e07194aa80665537fbf0bf763a43e0755` |
| Runner ejecutado | `ed966c715e422fe18eda02afc78fed9a0316df2fd708e91152f6ae3c21e34102` |
| SQL original del repositorio | `5307880cd7f274f5f0ac4eb222e19ca34fb0e0a9abd59a2970be50611a259f21` |
| Casos SQL | `e0d321b30d43e1199bba3bd439087e1d404d876307edff70959de4a03ae86fff` |
| Datos antes y después del reinicio | `b52327d22ca43fcea4e6c4a8d59903946977de57e833f25fbc66850797a84b07` |

Se verificaron **24 archivos del manifiesto**, más el propio manifiesto: **25
archivos** en total. El tar original se conserva sin cambios. Se rechazaron rutas
inesperadas, enlaces, duplicados y tamaños excesivos antes de leer contenido.
No se ejecutó SQL ni comandos procedentes del adjunto durante esta auditoría.

El SQL y los casos coinciden byte a byte con las fuentes publicadas. Los hashes
aportan integridad y vinculación con esas fuentes; no son una atestación firmada
del teléfono. La ejecución fue realizada por el usuario; el agente revisó los
archivos recibidos offline y no reclama haber vuelto a ejecutar PostgreSQL.

## Resultados comprobados

- **30 comprobaciones SQL**, con todas las etiquetas esperadas presentes una vez
  y en el orden previsto. Cubren propietario de las seis tablas, acceso PUBLIC,
  identidad/clase, bytes binarios, duplicados, claves foráneas, límites,
  restricciones del outbox, rollback y estados de operación deshabilitados.
- **Tres escrituras rechazadas** bajo el rol limitado: UPDATE del journal,
  DELETE del outbox y TRUNCATE del journal. Cada una devolvió SQLSTATE **42501**.
- Aplicación en una base ajena rechazada con **P0001**; segunda aplicación del
  esquema rechazada con **42P06**. El esquema se creó bajo un propietario
  dedicado, sin privilegios de superusuario, en una instancia nueva.
- El fallo de inserción del outbox revierte la inserción del journal de esa
  transacción. El rollback explícito también deja ambas tablas sin esas filas.
- Los cuatro conjuntos de datos retenidos —runs, journal, outbox y registry—
  son idénticos byte a byte después del reinicio ordenado. Persisten únicamente
  las filas artificiales comprometidas; las filas revertidas no aparecen.
- `fsync` y `synchronous_commit` activos. TCP deshabilitado, socket privado,
  autenticación local peer y reglas host reject. Apagado final confirmado.

Los cinco errores SQL visibles en el log del servidor son los rechazos esperados:
base ajena, esquema existente y tres operaciones sin permiso. No hay FATAL/PANIC.
La terminación del worker de replicación durante el apagado rápido no constituye
un fallo de estos casos; ambos arranques llegaron a aceptar conexiones y ambos
apagados completaron su checkpoint.

Las filas están marcadas **synthetic** y usan hashes/bytes artificiales. No son
journals certificados por Rust, nuevas observaciones de mercado ni resultados
económicos. La prueba establece el comportamiento del DDL y sus transacciones;
no certifica que exista un importador o un relay operando.

## Verificación del auditor y aislamiento

`scripts/audit_termux_postgres_evidence.py` reproduce la revisión desde el tar y
el commit publicado. Ocho regresiones comprueban rechazo de archivos alterados,
faltantes, rutas y enlaces inseguros, etiquetas de éxito duplicadas/falsas,
SQLSTATE incorrecto, fuentes ajenas, cambios tras reinicio y fallos de aislamiento
o apagado, incluso después de recalcular el manifiesto.

La suite Python completa pasa **99 pruebas**, incluidas esas ocho. Los fuentes
Rust, Cargo.lock, DDL y runner ejecutado no cambiaron; se conserva el resultado
previo de 155 pruebas Rust, sin presentarlo como una nueva ejecución de Rust.
Los chequeos de aislamiento mantienen 531 archivos originales y 106 workflows
heredados desactivados, con cero workflows activos y cero cambios fuera de Miner.

La prueba utiliza su propio directorio y cluster, y deja ese servidor apagado.
No reutiliza la base del bootstrap ni datos, configuración o procesos del
Observador. Las sesiones de Termux comparten usuario del sistema y paquetes;
esa separación no equivale a aislamiento contra un proceso hostil con el mismo
UID. Firma, puente, notificaciones, KMS, relay y presupuesto siguen desactivados.

## Límites y siguiente trabajo

Faltan importación de journals verificados por Rust, reintentos idempotentes con
comparación de bytes y cuarentena por conflictos, pruebas concurrentes del
importador/outbox y su conexión con los demás servicios. El reinicio probado es
ordenado: no acredita SIGKILL de PostgreSQL, pérdida eléctrica, recuperación de
disco, un servicio remoto ni operación prolongada.

Evidencia: `evidence/termux-postgres-20261022/`. La nota antigua «prepared contract»
del SQL se conserva como parte de sus bytes históricos auditados; el estado
actual de esta prueba local figura aquí y en `docs/infrastructure.md`.
