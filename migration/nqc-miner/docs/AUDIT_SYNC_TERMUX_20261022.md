# Auditoría del cliente PostgreSQL nativo — 22 octubre 2026

**PASS de consistencia y correspondencia con fuente. Avance global: 43/100.**
La prueba del cliente pendiente en `AUDIT_SYNC_PREFLIGHT_20261022.md` queda cerrada
para el commit `a1fb66a40f55728ecc5dd4913e2450bde8929473`. No cierra la
integración productiva ni las salidas económicas de fase.

Original retenido: `evidence/termux-sync-20261022/received.tar.gz`, 211,630 bytes,
SHA-256 `4dcc65211506c40853ea5a2b6f88500e640c5d40316e11db6aacb8f447df2a57`.
Runner: `bb59f9cff444990ff909fbc1af26b259ac92864fe8555a25b368ded3301aa4fb`.

El auditor abre el tar con límites, sin extraer rutas ni ejecutar SQL, Python,
wrappers o bytecode adjuntos. Los ocho inputs deben coincidir exactamente con el
runner publicado. Comprueba los **74 hashes**, las **17 comprobaciones**, los
**16 intents y resultados**, los requests, SQL generado, destinos, recibos y acuses.
El `.pyc` incluido por Python 3.14 se conserva y hashea como evidencia inerte.

Los datos originales se reconstruyen desde los fixtures fijados y se comparan
con cada fila de PostgreSQL: 16 runs, 24 filas de journal y outbox, 5 colecciones,
11 ventanas, 7 recibos, 2 cuarentenas de journal y 2 revocaciones de colección.
Las vistas elegibles contienen 12 filas cada una. Todos los payloads son
artificiales; no hay nuevas lecturas RPC, beneficios realizados ni datos Observer.

La pérdida de acuse conserva el resultado real del subcliente: COMMIT exitoso,
respuesta descartada, resultado del cliente `unknown`, reintento sin inserciones
adicionales. El timeout observa el backend propio en `PgSleep` antes de COMMIT;
se verifica PID, sentencia, terminación, ausencia antes del reintento y posterior
inserción. Dos clientes simultáneos producen 4 y 0 inserciones. No se atribuye a
esta prueba una medición de lock contention (consta en la auditoría anterior).

El cliente rechaza UUID de archivo ajeno y permisos de escritura excesivos.
Se confirman revocación del padre, propagación de un hijo y bloqueo de recibos
antiguos. PostgreSQL 18.6/aarch64 usa socket privado, peer, TCP desactivado,
fsync/synchronous_commit activos; el restart conserva exactamente los bytes de
12 tablas y 2 vistas. La instancia termina apagada.

El auditor no atestigua criptográficamente el teléfono ni prueba inmunidad ante
un administrador que reescriba todo. Los hashes prueban correspondencia e
integridad interna. Las 12 regresiones del auditor rechazan archivos/rutas
extraños, cambios rehasheados, resultados falsos, acuses, payloads o revocaciones
alterados, errores de permisos/terminación y divergencia del restart.

Reproducir la lectura, sin conexión a una base:

```bash
python scripts/audit_termux_sync_evidence.py \
  evidence/termux-sync-20261022/received.tar.gz
```

El punto restante de infraestructura sigue incluyendo integración remota,
operación prolongada, observabilidad y recuperación conjunta. La nueva evidencia
y el coordinador local no se contabilizan como esos sistemas ejecutados.
