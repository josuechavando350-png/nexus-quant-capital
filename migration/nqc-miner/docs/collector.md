# Recolector histórico por ventanas

`follow` repite escaneos finalizados, conserva un journal por ventana y reanuda
leyendo la evidencia durable. Solo admite una configuración v2 histórica con un
scope. `from_block` es el origen y el ancho inclusivo `to_block - from_block + 1`
se repite: no es un límite final para `follow`. Cada contrato/cadena tiene su propio
proceso, directorio, retraso y límite de fallo. No se admite Shadow: el catch-up
histórico no demuestra vigilancia prospectiva.

El comando usa el mismo control de build limpio, consenso RPC, decodificación y
cuarentena que `scan`. No amplía los tres métodos RPC de lectura permitidos.

```bash
nqc-miner follow --config /ruta/miner-plan.json --state /ruta/nueva/coleccion \
  --max-polls 2 --poll-seconds 15
nqc-miner verify-collector --config /ruta/miner-plan.json --state /ruta/coleccion
nqc-miner follow --config /ruta/miner-plan.json --state /ruta/coleccion --max-polls 1
```

Por defecto se ejecuta **un poll**. `--max-polls 0` permite repetición hasta que el
operador pare el proceso; esta entrega no instala ni deja ese servicio ejecutando.
Un poll cierra como máximo una ventana. Si aún no está finalizada, emite `waiting`
y no crea ni adelanta la ventana. Los fallos de disponibilidad RPC se reintentan
en el siguiente poll, tras las pausas acotadas del transporte. Un último poll
fallido sale con código distinto de cero. Desacuerdos, configuración inválida,
reloj atrasado y fallos de integridad detienen el proceso para inspección.
La salida es JSONL con estado y cursor, sin valores de endpoints.

## Persistencia y reinicios

La raíz tiene propietario, plan inmutable, marcador de colección, journal de
control y bloqueo exclusivo. Cada `window-00000000000000000000` contiene un run
con identidad derivada del hash del plan y el índice. Al abrir se comprueban todos
los journals, índices contiguos y compromisos de bloques entre ventanas. Solo la
última ventana puede estar incompleta. Los chunks durables se reanudan; no se
borra ni trunca evidencia para lograr que una comprobación pase.

Antes de avanzar se revalida por RPC la ventana anterior, incluidos sus anchors;
se comprueba además su enlace con la siguiente. Contradicciones persistidas o una
ruptura de esa continuidad escriben una invalidación durable en la raíz. La
colección queda en cuarentena, incluso si un journal hijo conserva evidencia
histórica válida. **Los consumidores deben comprobar `verify-collector` y el
journal de control**, no aceptar automáticamente exports hijos aislados.

El hash de colección vincula los tips de las ventanas completas. Es integridad
local, no autenticación de cadena ni protección contra un administrador que
reescriba todo el directorio o elimine su sufijo y los hashes externos. La lectura
RPC continúa dependiendo del acuerdo de proveedores. Tras reinicio la auditoría
local cubre todas las ventanas; la revalidación RPC ordinaria cubre la última.

Los bloqueos nuevos usan el kernel de Rust 1.90, conservan un inode estable y se
liberan al morir el proceso. `writer.lock` **permanece en disco**; no debe borrarse.
Un lock viejo con PID, un lock incompleto, un symlink, un filesystem sin soporte
de bloqueo o un registro truncado se rechaza para inspección manual. La prueba de
SIGKILL cubre un límite durable con locks de raíz e hijo abiertos. No demuestra
reparación automática de un write cortado ni supervivencia a pérdida física del
disco. Un directorio privado y almacenamiento local con fsync/locks fiables son
prerrequisitos; no se ha certificado NFS ni escritores hostiles en el mismo host.

Límite actual: 10,000 ventanas por colección, máximo 20,000 bloques por ventana.
Al alcanzarlo se requiere un plan nuevo revisado; no hay rotación ni retención
que borre evidencia automáticamente. La comprobación inicial y el índice de
compromisos crecen con la evidencia. No hay garantía operativa 24/7 ni integraciones
activas con Redpanda, ClickHouse, Postgres, Temporal u object storage.

## Captura reproducible de reinicio

`scripts/smoke_collector.py` liga una plantilla al build, ejecuta dos polls, verifica,
reinicia el proceso para un tercer poll y vuelve a verificar. Compara los bytes de
las ventanas anteriores y del binario. Conserva los fallos con su clasificación;
solo acredita la prueba si las tres ventanas exactas están completas.

```bash
python3 scripts/smoke_collector.py --binary /ruta/absoluta/nqc-miner \
  --template /ruta/plan.template.json --output /ruta/nueva/prueba \
  --timeout-seconds 600 --transport-context public_rpc
```

Una prueba finita no acredita operación continua prolongada, saturación calibrada,
cobertura prospectiva ni resultados económicos. Las ventanas repetidas respecto
a muestras anteriores nunca se suman como observaciones independientes.
