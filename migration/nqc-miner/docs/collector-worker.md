# Coordinador acotado de recolección y sincronización

`research/collector_worker.py` une el recolector Rust, el archivo local, la
verificación Rust/Polars y el cliente PostgreSQL. Trabaja sobre una colección
histórica ya inicializada, un archivo propio y una base local dedicada. Cada
invocación hace entre 1 y 16 ciclos y termina; no instala ni deja un servicio.

## Orden y recuperación

1. Comprueba identidad limpia del binario, hash de plan, clase histórica,
   UUID de archivo/base, destino local y rutas separadas.
2. Adquiere un bloqueo exclusivo de su propio workspace. Conserva el inode;
   un segundo coordinador no puede avanzar sobre el mismo workspace.
3. Crea una sesión nueva con intención durable `unknown`. **Siempre** vuelve a
   verificar y sincronizar el estado actual antes de ejecutar otro poll, incluso
   cuando la sesión anterior decía `applied` o murió sin escribir resultado.
4. Solo un acuse confirmado permite lanzar un `follow --max-polls 1`.
5. Cuando termina el proceso, archiva y sincroniza de nuevo. Un poll fallido
   también pasa por reconciliación, porque pudo escribir una invalidación.
   Una cuarentena se transmite y detiene el lote. Un estado incierto o un error
   impide nuevos polls. El siguiente intento vuelve a verificar desde la fuente.

No utiliza un cursor local de éxito para omitir trabajo. El archivo, los recibos
inmutables y el importador idempotente resuelven los reintentos. No borra sesiones,
no repara registros cortados ni adopta directorios ajenos. Un cambio de plan,
binario, destino o identidad exige un workspace nuevo revisado.

## Ejecución

Usa el Python aislado con `research/requirements.txt`; el binario limpio debe ser
el mismo build que creó el plan de la colección. El formato del destino y los
requisitos de la base están en `postgres-sync.md`. No usa el clúster descartable
de los experimentos Termux ni instala roles/migraciones automáticamente.

```bash
python research/collector_worker.py \
  --binary /ruta/miner/bin/nqc-miner \
  --state /ruta/miner/coleccion \
  --archive /ruta/miner/archivo \
  --workspace /ruta/miner/trabajador \
  --target /ruta/miner/destino.json \
  --cycles 4 --timeout 120
```

Las variables RPC propias del plan deben estar disponibles. Solo usa los métodos
RPC de lectura ya admitidos por el binario; no habilita firma, relay ni gasto.
Los valores de endpoints y stderr no se guardan: los comandos conservan hashes,
retorno, tiempo y límite. La evidencia semántica queda en los journals y bundles.

| Salida | Código | Significado |
|---|---:|---|
| `applied` | 0 | Todos los ciclos pedidos terminaron y confirmaron su snapshot |
| `unknown` | 2 | No puede afirmarse que el ciclo completo terminó; conservar y reintentar |
| `quarantined` | 3 | Revocación confirmada; detener e inspeccionar |
| `superseded` | 4 | La recuperación encontró una versión posterior en base; inspeccionar |
| `capacity_reached` | 5 | Ya hay 64 ventanas o falta el conteo; no lanzar otra ventana |

`last_sync_commit_confirmed` corresponde al último intento de sincronización,
no al éxito del lote. Puede ser verdadero con resultado global `unknown` si el
poll falló pero sus datos persistidos fueron reconciliados. `cycles_applied`
cuenta ciclos confirmados, **no nuevas observaciones**: un poll puede esperar
finalización y no agregar eventos. Las métricas son archivos locales por sesión,
sin endpoint HTTP ni servidor Prometheus activo.

## Límites comprobados y pendientes

16 pruebas del coordinador ejercitan Rust/Polars reales, archivos y locks reales,
reinicio, SIGKILL de un proceso que tenía el lock, intents incompletos, pérdida de
acuse, revocación, límites y privacidad de stderr. RPC/follow y el servidor SQL
se modelan explícitamente en estas pruebas; el cliente PostgreSQL tiene evidencia
nativa separada (`AUDIT_SYNC_TERMUX_20261022.md`). **No hay todavía una ejecución
integral de este coordinador contra RPC y PostgreSQL reales simultáneamente.**

El wrapper controla tiempo y tamaño observado de salida de sus propios procesos.
SIGINT/SIGTERM liberan y matan su grupo de proceso en ejecución. SIGKILL no permite
cleanup Python; un hijo aún vivo puede conservar el lock del recolector y bloquear
la recuperación hasta que termine. No se matan procesos ajenos para desbloquearlo.
La prueba SIGKILL acredita liberación del lock del coordinador e intención
incompleta conservada, no terminación automática de todos los descendientes.

Máximo 64 ventanas importables, 10,000 registros y 8 MiB de fuente por snapshot;
1,000 sesiones por workspace. No hay rotación/borrado automático. El control
previene el poll 65; un límite de bytes/registros alcanzado durante un poll deja
el lote incierto para revisión. Un cron, systemd o Temporal futuro debe invocarlo
con identidades/recursos propios y auditar la integración antes de declarar 24/7.
