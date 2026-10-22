# Prueba nativa del cliente de sincronización

Estado: **preparada, no ejecutada todavía**. Avance global **43/100**. La prueba
anterior validó las funciones SQL; ésta valida el cliente que las llama y exige
confirmación posterior a COMMIT. No hace falta repetir las pruebas anteriores.

Guardar `scripts/nqc-miner-sync-check.sh` en Descargas con ese nombre. Requiere
Termux nativo, PostgreSQL 18.6 y Python 3.10 o posterior. Si Python no está instalado:

```bash
pkg install python
```

Ejecutar:

```bash
(
set -eu
MINER_SYNC_FILE="/sdcard/Download/nqc-miner-sync-check.sh"
printf '%s  %s\n' \
  'bb59f9cff444990ff909fbc1af26b259ac92864fe8555a25b368ded3301aa4fb' \
  "$MINER_SYNC_FILE" | sha256sum -c -
bash "$MINER_SYNC_FILE"
)
```

Mantener Termux abierto. Al terminar, adjuntar el `.tar.gz` indicado por
`ADJUNTA ESTE ARCHIVO AL CHAT`, incluso si informa `failed`. El runner conserva
los intentos y trata de apagar su servidor en éxito o fallo.

Se crea `~/nqc-miner-sync.XXXXXX`, con socket privado propio y puerto lógico
55435. No se adoptan bases anteriores ni se accede al Observador. No hay TCP,
RPC, firma o gasto. Los fixtures son artificiales; se conservan las identidades
de la fuente previamente auditada que los generó.

Las 17 comprobaciones cubren confirmación, repetición, extensión, recibo antiguo,
revocación, UUID ajeno, pérdida del acuse después de COMMIT, reintento idempotente,
timeout antes de COMMIT y rollback, dos clientes concurrentes, permisos excesivos
rechazados e invalidación independiente de un hijo. Los wrappers de fallo llaman
al psql real; sólo descartan una respuesta o insertan una espera de prueba.
Puede terminarse una sesión de prueba propia que siga esperando; nunca otro servidor.

La salida también conserva comparación byte a byte antes/después de reiniciar,
configuración, fuentes, hashes y apagado final. El `pass` requiere luego auditar
el archivo retornado. No equivale a producción ni a un servicio continuo.
