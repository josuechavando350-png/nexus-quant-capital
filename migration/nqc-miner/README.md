# NQC Miner — implementación aislada

Miner descubre **mercados candidatos**, registra evidencia y permite estudiar su economía. Esta entrega es una base de investigación ejecutable: **no es un Miner de producción, no demuestra rentabilidad y no activa minas**.

El alcance procede de `NQC_Miner.pdf`, versión 1.0 del 22 de octubre de 2026, páginas 1–9. La matriz completa está en [docs/requirements.md](docs/requirements.md). El documento original, marcado confidencial, no se copia al repositorio público.

## Separación del observador

Todo el código nuevo vive en `migration/nqc-miner/`, dentro de una rama propia. Este crate tiene su propio workspace y `Cargo.lock`. No modifica Census, el observador, las aplicaciones cliente ni los workflows existentes.

Los datos usan exclusivamente el espacio `nqc_miner_v1`. Cada ejecución tiene directorio nuevo, `owner.json`, configuración inmutable, clase de evidencia y bloqueo exclusivo. Un directorio ajeno no se adopta. Las únicas variables de RPC admitidas empiezan por `NQC_MINER_RPC_`. El puente es un contrato de exportación local y permanece desactivado; no existe escritor hacia el observador.

## Qué funciona

- Decodificación estricta de nacimientos y liquidaciones de Morpho Blue, y eventos de reservas/liquidaciones de Aave V3, con Alloy. La coincidencia ABI produce candidatos, nunca certificación de contratos.
- Ingesta finita en Rust desde dos o más proveedores RPC, verificando cadena, bloques finalizados, acuerdo de eventos y continuidad de checkpoints. No hay métodos de firma ni envío de transacciones.
- Recolector histórico por ventanas con reinicio, espera de finalización y cuarentena de colección; [operación y límites](docs/collector.md).
- Journal durable con hashes, deduplicación, reanudación y cuarentena por cambios de cadena. Los lotes provisionales y los escaneos incompletos no se presentan como cobertura completa.
- Saturación y cobertura limitadas al universo declarado. Elegibilidad, propinas y precios ausentes permanecen desconocidos. Descubrir una mina después no mejora retroactivamente su cobertura.
- Medición auxiliar de gas Ethereum con enteros exactos, vínculo al journal y coste único por transacción; [contrato y límites](docs/gas-measurement.md). La muestra retenida mide dos transacciones y conserva una tercera pendiente; no certifica rentabilidad.
- Lectura histórica de salud y precios Aave ligada a hashes de bloques y acuerdo de proveedores; [contrato y límites](docs/aave-historical-state.md). Hay 48 estados previos auditados de los tres eventos originales; no demuestran elegibilidad ejecutable.
- Cálculos offline de condiciones iniciales, importes de liquidación e [índices y saldos escalados Aave](docs/aave-reserve-projection.md), contrastados con Solidity. Reciben entradas suministradas y todavía no componen una certificación de liquidación completa.
- [Consumo de colateral escalado y comisión final Aave](docs/aave-collateral.md): contempla redondeos separados y el saldo posterior suministrado; no ejecuta transferencias del token.
- [Quema de deuda y déficit Aave](docs/aave-debt.md): comprueba contabilidad de deuda, indicador de préstamo, argumentos de tasas y liquidez virtual con respuestas externas suministradas.
- [Identidad histórica de tokens y estrategia](docs/aave-dependencies.md): recompilación exacta de las implementaciones y comparación con dos proveedores en tres bloques; estado y ejecución externa siguen pendientes.
- [Ejecución conjunta de deuda](docs/aave-debt-execution.md): función original del Pool, token de deuda y estrategia reales ejecutados juntos sobre estado sintético, con rollback y callbacks comprobados.
- Valuación condicional mediante bootstrap de economía diaria, con semillas reproducibles, escenarios, percentiles y costes de intentos fallidos. No sustituye una simulación completa de precios y ejecución.
- Simulación local con REVM sobre un estado cerrado suministrado: las cuentas, slots o hashes de ancestros ausentes causan error. No se completan consultando un RPC ni suponiendo ceros.
- Controles de ciclo de vida, caducidad, toxicidad, pruebas de adaptadores y presupuesto; asignación preparatoria por Thompson sampling.
- Primitivas de timelocks, intereses Morpho bajo supuestos explícitos, vencimientos, similitud de bytecode, grafos heurísticos e incentivos.
- Archivo local de colecciones con publicación atómica, snapshots verificados y propagación explícita de cuarentena; [operación y límites](docs/archive.md).
- Exportación local a Parquet con Polars, comprobación por el verificador Rust y conservación exacta de los registros originales.
- Pipeline de investigación LightGBM con contribuciones TreeSHAP, vinculación de fuentes y validación temporal. Sus pruebas entrenan fixtures artificiales, sin afirmar capacidad predictiva económica.

Los módulos de investigación e infraestructura documentan sus propios límites en `docs/`. Un archivo de configuración no acredita un servicio desplegado.

## Compilar y verificar

Requiere Rust **1.90.0**. Las dependencias están fijadas en `Cargo.lock`. Mantén los productos de compilación fuera del repositorio:

```bash
cd migration/nqc-miner
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo fetch --locked
cargo test --all-targets --locked --offline
cargo clippy --all-targets --locked --offline -- -D warnings
cargo fmt -- --check
python3 ../../migration/verify_isolation.py
cargo run --locked --offline -- about
```

La primera descarga requiere red; los tests y el compilador no requieren RPC. Los tests usan fixtures sintéticos identificados como tales, sin demostrar comportamiento rentable en mercados reales.

La investigación Python utiliza un entorno separado y las versiones de
`research/requirements.txt`. Con ese entorno instalado, el siguiente comando
ejecuta la batería completa y conserva sus resultados en un directorio nuevo:

```bash
python3 scripts/verify_offline.py \
  --research-python /tmp/nqc-miner-research-venv/bin/python \
  --binary "$CARGO_TARGET_DIR/debug/nqc-miner" \
  --output /tmp/nqc-miner-audit-001
```

La verificación incluye compilación, pruebas Rust/Python, Clippy sin advertencias,
formato, aislamiento del repositorio e identidad completa del build: commit,
fuentes, Cargo.lock, toolchain, rustc, target, perfil y hash de RUSTFLAGS. Las
corridas nuevas usan manifest schema v2 y quedan ligadas a
`build_identity_sha256`; evidencia histórica v1 sigue siendo verificable offline
pero no es elegible para una lectura RPC nueva. No inicia servicios. Los contratos de infraestructura y sus comprobaciones pendientes están
en [docs/infrastructure.md](docs/infrastructure.md).

## Comandos

```bash
nqc-miner about
nqc-miner assess-gas-funding --input fixtures/gas_funding.synthetic.json
nqc-miner topics
nqc-miner validate-config --config /ruta/miner-config.json
nqc-miner validate-aave-plan --config /ruta/miner-config.json --plan /ruta/plan.json
nqc-miner read-aave-state --config /ruta/miner-config.json --plan /ruta/plan.json
nqc-miner project-aave-reserve --input /ruta/reserva.json
nqc-miner calculate-aave-amounts --input /ruta/importes.json
nqc-miner calculate-aave-collateral --input /ruta/colateral.json
nqc-miner calculate-aave-debt --input /ruta/deuda.json
nqc-miner scan --config /ruta/miner-config.json --state /ruta/nueva/nqc-miner-run
nqc-miner verify-journal --state /ruta/nqc-miner-run
nqc-miner follow --config /ruta/miner-plan.json --state /ruta/nueva/coleccion --max-polls 2
nqc-miner verify-collector --config /ruta/miner-plan.json --state /ruta/coleccion
nqc-miner report --config /ruta/miner-config.json --state /ruta/nqc-miner-run
nqc-miner report --config /ruta/miner-config.json --state /ruta/nqc-miner-run --prometheus
nqc-miner value --input fixtures/valuation.synthetic.json
nqc-miner decode --input /ruta/log-con-scope.json
nqc-miner simulate --input /ruta/estado-y-llamada.json
```

`scan` es una lectura acotada. Exige un binario construido desde un commit limpio y que el commit y SHA-256 de `Cargo.lock` coincidan con la configuración. `about` muestra ambas identidades. Los endpoints se proporcionan mediante las variables propias indicadas en cada scope; sus valores no se serializan ni se imprimen en errores. Dos nombres o hosts distintos no prueban que los proveedores tengan operadores independientes.

El comando `report` sin un registro prospectivo de vigilancia no atribuye detección anticipada. El JSON distingue datos históricos, Shadow y sintéticos. No importa ganancias realizadas ni datos del observador.

## Dinero y autorización

El presupuesto activo de esta entrega es **cero**. `scan` no admite presupuesto de gas. No hay firmante, KMS, broadcast, alertas enviadas ni aprobaciones utilizables para operar.

La política vigente exige **gas de Titan y cero aportación propia**: no se permiten prefondo de gas, fallback, principal, colateral, garantías ni recurso contra el operador. Los límites anteriores de MXN 2,000/500/1,000 quedan únicamente en el módulo de contabilidad histórica `controls::historical_own_gas`; ya no son la política actual.

El comando [assess-gas-funding](docs/gas-funding.md) revisa términos suministrados por ejecución: bundle, cadena, código, bloque, vigencia y límites para éxito y fallo. Un anuncio general, una simulación o un dato ausente no demuestra cobertura. Incluso términos consistentes conservan `execution_gas_coverage_verified=false`: la identidad del patrocinador y su compromiso concreto todavía deben autenticarse. No activa fondos ni minas.

## Qué falta para cerrar el PDF

La salida de fase A exige mediciones completas y calibradas en dos o tres cadenas. La fase B exige comparación real durante Shadow. La fase C exige una propuesta concreta, aprobación explícita y ejecución presupuestada por un firmante externo. La fase D exige colectores, modelo validado y un ciclo de aprendizaje funcionando.

Persisten integraciones de infraestructura, fuentes históricas suficientes, certificación diferencial de protocolos y validación económica. Los estados `Active` y `Watched` están representados, pero son inalcanzables en este binario. Ningún porcentaje de implementación equivale a una garantía de ganancias o ausencia total de defectos.

Consulta [docs/progress.json](docs/progress.json) para el denominador de progreso y [docs/AUDIT.md](docs/AUDIT.md) para la evidencia de verificación.

La [auditoría del lector histórico Aave](docs/AUDIT_AAVE_STATE_20261023.md)
registra **167 pruebas Rust y 242 Python aprobadas**, además de la revisión de
las respuestas públicas y su vínculo con el journal original. Avance: **43/100**.

## Captura durable de una lectura acotada

La continuación auditada se documenta en [docs/AUDIT_CONTINUATION_20261022.md](docs/AUDIT_CONTINUATION_20261022.md).
`scripts/capture_run.py` vincula una plantilla v2 a un binario limpio, valida la
configuración, limita el tiempo de lectura y conserva también los intentos fallidos.
Después verifica el journal, genera el informe y compara los hashes del binario.
Solo declara la muestra completa si coinciden propietario, build y todos los
ámbitos previstos. La configuración se publica una sola vez, sin seguir enlaces
simbólicos ni sobrescribir a otro escritor.

```bash
python3 scripts/capture_run.py \
  --binary /ruta/absoluta/nqc-miner \
  --template evidence/capture-plan-v2-20261022/config.template.json \
  --output /ruta/nueva/miner-capture \
  --timeout-seconds 600 --transport-context public_rpc
```

Usa un `run_id` nuevo para cada captura. Los endpoints se suministran mediante las
variables propias de la plantilla; el capturador no registra sus valores.
Los exports Parquet admiten propietarios v1 históricos y v2, preservando su
identidad de compilación y los bytes originales. El puente continúa desactivado.

La auditoría más reciente del recolector está en [docs/AUDIT_COLLECTOR_20261022.md](docs/AUDIT_COLLECTOR_20261022.md): 39/100, 155 pruebas Rust y 69 Python, captura histórica con reinicio y exports verificados.

El bloque de archivo local está en [docs/AUDIT_ARCHIVE_20261022.md](docs/AUDIT_ARCHIVE_20261022.md): 40/100, 155 pruebas Rust y 91 Python, archivo local v2 con recuperación y revocación verificadas.

La auditoría base PostgreSQL está en [docs/AUDIT_POSTGRES_TERMUX_20261022.md](docs/AUDIT_POSTGRES_TERMUX_20261022.md), conservada como evidencia histórica de 41/100.

Estado actual: **43/100**. La [importación de colecciones completas](docs/postgres-collection.md) pasó la [auditoría runtime en Termux](docs/AUDIT_COLLECTION_TERMUX_20261022.md): 33 comprobaciones SQL, permisos, concurrencia, rollback/reintento, revocaciones, bytes originales y reinicio verificados. La suite de ese bloque pasó **160 pruebas Python**. La instancia de prueba terminó apagada; siguen pendientes conexión operacional del recolector e integración remota.

La [auditoría individual anterior](docs/AUDIT_IMPORT_TERMUX_20261022.md) conserva su corte de 42/100 y 35 comprobaciones SQL. El [runner de colecciones](docs/termux-collection.md) y el archivo original permiten reproducir el experimento artificial. Observador, firma y gasto permanecen desactivados.

La [prueba nativa del cliente PostgreSQL](docs/AUDIT_SYNC_TERMUX_20261022.md)
ya está auditada: **17 comprobaciones, 16 intentos, 74 hashes**, recuperación de
acuse perdido, timeout antes de COMMIT, permisos, revocaciones y restart.

El [coordinador de recolección y sincronización](docs/collector-worker.md) ya une
los componentes locales con recuperación previa, ejecución acotada, exclusión de
trabajadores y conservación de intentos inciertos. **16 pruebas del coordinador**
usan Rust/Polars y locks reales con RPC/SQL modelados; la ejecución integral del
coordinador con servicios reales sigue pendiente. Auditoría del bloque en
[docs/AUDIT_WORKER_PREFLIGHT_20261022.md](docs/AUDIT_WORKER_PREFLIGHT_20261022.md).

El [plan de cierre](docs/closure-plan.json) conserva los **57 puntos restantes**
y sus criterios originales. No se han reponderado para declarar 100% a partir de
código o fixtures: exige desarrollo e integración pendientes, mediciones reales,
Shadow prospectivo, certificación de adaptadores y operación expresamente aprobada.

The [audited token-proxy execution](docs/aave-token-proxy-execution.md) replaces the synthetic forwarder for one verified proxy family while retaining synthetic execution-state limits.

The [actual rewards execution](docs/aave-rewards-execution.md) covers the real rewards proxy/controller and the remaining token-proxy family, while balances and distributions remain synthetic.

Actual aToken transfer composition: [scope and reproduction](docs/aave-transfer-execution.md), [audit](docs/AUDIT_AAVE_TRANSFER_EXECUTION_20261023.md).

Underlying WETH execution: [scope and metadata gap](docs/aave-underlying-execution.md), [audit](docs/AUDIT_AAVE_UNDERLYING_EXECUTION_20261023.md).

Auditoría vigente de política de gas: [Titan por ejecución](docs/AUDIT_TITAN_GAS_POLICY_20261023.md), **589 pruebas aprobadas (249 Rust + 340 Python)** sobre la misma fuente tras restaurar objetos Git históricos. Se conservan el intento inicial fallido y una repetición interrumpida. Avance **43/100**, sin cobertura de patrocinio ni operación certificada.
