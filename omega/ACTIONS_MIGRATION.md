# H2E — ejecución física en GitHub Actions

Destino exclusivo: `josuechavando350-png/nexus-quant-capital` (ID `1411047452`),
rama `feat/omega-h2-executable-audit-20261022`. El usuario autorizó esta alternativa
y confirmó expresamente la rama exclusiva de Omega el 2026-10-22.

Esta migración es adicional al import histórico. El único archivo activo admitido
es `.github/workflows/omega-h2-audit.yml`, copia exacta de
`omega/h2_actions_workflow.yml.disabled`, SHA-256
`a2d101c69a6ce5aa0dc46065429547dbafec79c0d253afffce6c57231d755f16`.
La preparación y auditoría se publican antes de su activación. Los 637 payloads,
106 workflows históricos desactivados, repositorio fuente e identidades originales
permanecen intactos. La excepción no incluye ningún archivo o rama de Miner.

## Productor y disparador

El evento es exclusivamente `push` a la rama indicada y a cinco rutas de auditoría
explícitas. No hay schedule, pull_request_target, evento de otra rama, despliegue
ni workflow_dispatch dependiente de main. Cada job comprueba repositorio público,
ID, ref, HEAD limpio, bytes/modos de cada archivo, árbol, workflow SHA/ref y
run/attempt. El checkout se fija a `github.sha`, con historial completo y sin
credenciales persistidas. `isolation.py` valida la única excepción antes de
proyectarla; archivos activos adicionales siguen llegando al verificador original
y fallan. Se informa por separado de workflows históricos activos (0) y Omega (1).

La comprobación de contexto del runner no se presenta como autenticación remota.
Al terminar se deben leer de GitHub el commit/tree, run, attempt, jobs, conclusión
y logs. Una corrida sobre un commit anterior no certifica un commit posterior.

## Dos trabajos y evidencia

Ambos usan `ubuntu-24.04` estándar, máximo 60 minutos, y prueban un namespace real
con `sudo unshare --net --mount`: sólo loopback abajo, sin rutas útiles IPv4/IPv6,
conexiones físicamente inalcanzables y bind mount de sólo lectura. Se reutiliza
la función original fijada por Git blob. Después clonan la fuente original en
otro directorio con checkout sparse sólo NQC, verifican objetos y aislamiento.

- `replay`: GET del run/commit/artifact original con el token temporal de sólo
  lectura. La disponibilidad entre repositorios se comprueba realmente, sin
  asumirla ni ampliar permisos si falla. ZIP, metadata e índice se validan con
  el autenticador original. Rust 1.98.1 corre tests y build release en un clon
  desechable del commit exacto. El runner histórico intacto ejecuta replay,
  crash/resume y closeout determinista dentro del namespace desconectado.
- `forks`: reproduce el materializador original y enlaza la copia con HEAD.
  Ejecuta Rust PFT y Solidity offline antes de los forks. Foundry 1.7.1 y solc
  0.8.24 se descargan con hashes fijados. Usa el test histórico inalterado y el
  executor de la copia efectiva. Los dos RPC originales ejecutan casos positivo
  y negativo; ambos resultados deben coincidir. El proxy original, fijado por
  blob, recibe un filtro adicional de métodos de lectura antes de enviar datos.

El token sólo se entrega a curl por stdin para GETs a la API del repositorio
fuente; se elimina del entorno de procesos hijos. No se imprimen credenciales.
Los redirects HTTPS no usan `--location-trusted`. No se rehostea el seed original.

No se usan runners grandes, cachés ni uploads de artifacts. Sólo logs de Actions:
comandos, códigos, SHA-256 del stdout y registros JSON con compromiso SHA-256.
Esto permite auditar los gates físicos sin introducir almacenamiento facturable
de artifacts. `artifact_id` queda null. Por tanto no satisface la recertificación
canónica que exige artifact autenticado y validación posterior del consumidor.

H2 continúa en 93.75% hasta tener resultados físicos auditados. Certificación
0/36, Census abierto, protocolo `NOT_CLOSED` y permisos económicos todos false.
Errores, ausencia de seed, red bloqueada, jobs omitidos o resultados parciales
no se convierten en PASS. La regresión Python Census mantiene los siete errores
de preparación documentados y la validación histórica separada de 174 casos.
