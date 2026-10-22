# H2C — auditoría ejecutable del checkout completo

Fecha: 2026-10-22. Repositorio: `josuechavando350-png/nexus-quant-capital`.
Base: `54318de74ad716b943c30c4deddb12ecf5fc54be`, descendiente del
`84fbaa2dd7a1b93c432f6611622b98d81fd3c679` entregado por el operador.
Se conserva H12. Todos los cambios de esta entrega están bajo `omega/`.

**H2: 93.75% (94% redondeado). Census abierto. Certificación: 0/36.**
La cifra mide integración auditada, no probabilidad de ganar ni certificación
de mercado. La base fundacional conserva 9/9: 7 `foundational_partial`,
2 `historical_partial`, 0 `not_evidenced`.

## Resultados comprobados

| Comprobación | Resultado y alcance |
|---|---|
| Aislamiento contra objetos Git originales | PASS: 637 payloads, 531 fuentes, 106 workflows desactivados, 0 activos; diez referencias originales comprobadas |
| Omega con D15B y D16 auténticos | 241/241 aprobadas; 0 errores/omisiones; incluye 12 pruebas nuevas del registro de regresión |
| Python Census, catálogo actual | 838 descubiertas; 664 ejecutadas y aprobadas, 7 errores `setUpClass`, 174 no ejecutadas; 0 omisiones con D06 autenticado |
| Comparación con snapshot original | Mismos 838 IDs, 664 éxitos y siete firmas de error; sin nuevos errores |
| Siete suites históricas con CLI y catálogo original | 174/174 aprobadas en copias separadas; no convierte discovery actual en verde |
| D06 con ZIP y metadatos originales | 58/58 aprobadas; incluidas en las 664, no sumarlas otra vez |
| Aislamiento heredado | 9/9 aprobadas sobre proyección completa sin Omega |
| Rust Census 1.98.1 | 528/528 aprobadas con `--workspace --all-targets --locked --offline`; 0 ignoradas |
| fmt / Clippy / build de Census | PASS; Clippy con `-D warnings` |
| Materialización PFT original | PASS con ancestros, árboles, blobs, 33 hashes recuperados y overlays fijados; en copia separada |
| Rust PFT 1.98.1 | 56/56 aprobadas con lock y modo offline; build aprobado; Clippy finaliza con advertencias heredadas |
| Solidity, Foundry 1.7.1 / solc 0.8.24 | 14/14 aprobadas; dos pruebas fuzz con 256 ejecuciones cada una, seed `0x39` |
| Python parity / WETH physical | 9/9 y 25/25 aprobadas |
| Corpus histórico PFT | Contrato de tres fixtures aprobado; mantiene `protocol_fork_truth: NOT_CLOSED` |
| Formato Rust / Solidity PFT | FALLA sobre la copia efectiva original; no se reescriben bytes protegidos |
| Fork histórico por dos proveedores | BLOQUEADO en preflight: ambos responden HTTP 403; no se ejecutó el fork |
| Namespace desconectado para replay D06 | BLOQUEADO: `unshare` no puede escribir `uid_map` (`Operation not permitted`) |

Una comprobación exploratoria con Rust 1.90.0 no cuenta para estos resultados:
se ejecutó después la suite completa con el toolchain fijado 1.98.1. Para PFT,
`cargo fetch --locked` preparó dependencias antes de tests offline. Su build
comprobado es debug/all-targets; no se ejecutó el build release histórico.

## Por qué discovery general sigue rojo

Los errores de `setUpClass` no se incluyen en `testsRun` de unittest. Restar
"7 errores" de "664 tests" daría un conteo incorrecto. El nuevo `regression.py`
registra éxitos directamente y compara contra el inventario previo. Devuelve
código 1 ante errores, omisiones, expected failures, inventario vacío o pruebas
no ejecutadas, incluso cuando unittest imprime `OK`.

Los siete errores se reprodujeron en un checkout NQC de la fuente original
`e259739c9f75fedcd1061d2f78d6b8852e7a3060`. Cinco suites requieren argumentos CLI
y dos exigen catálogos anteriores. No se eliminaron tests ni se modificaron
aserciones. `historical_regression.py` repite esos tests con los originales
autenticados y cambia sólo el catálogo de entrada en una copia desechable.
Usa `LOCAL_OFFLINE_TEST_NOT_CI` como etiqueta para el test que necesita
`GITHUB_WORKFLOW`; no representa una corrida CI.

| Suite histórica | Tests | Git blob del catálogo |
|---|---:|---|
| original_d08_debt_producer | 20 | `6754a74c5c1e348c0c731618332ba8feba96834e` |
| original_d08_native_flash_import | 20 | `c1b9f136a13f220af9dceaae50e5caa3105121eb` |
| four_native_original_source_join | 21 | `c1b9f136a13f220af9dceaae50e5caa3105121eb` |
| independent_seven_bounded_rejections | 22 | `c1b9f136a13f220af9dceaae50e5caa3105121eb` |
| independent_thirteen_source_pins | 22 | `9dee5fe5035fad450ede25462728eba26beffb49` |
| independent_discovery_admission | 49 | Catálogo actual sin reemplazo |
| independent_two_debt_pins | 20 | `c1b9f136a13f220af9dceaae50e5caa3105121eb` |

## Procedencia y límites de PFT

El materializador original se ejecutó en un checkout NQC de la fuente original,
separado del destino. Se respetó el gate de ancestros; no se atribuye al nuevo
repositorio la ascendencia ni certificación del anterior.

- Commit PFT: `5b4a0cb778cb4370cd54eb6fcba765dc8d7cecdf`.
- Árbol efectivo: `cc83e9664cdf6e095e2abfce7d08202e166c2c0556b7283d2d294bcd098ebc66`.
- Árbol reimplementado: `6be3a8ec1bbccfdd5cc650bc126d836a3eef1124cf3f99a11d5007a7e979addc`.
- Foundry SHA-256: `cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b`.
- solc SHA-256: `fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f`.

Los RPC previstos por el workflow preservado son
`https://eth-mainnet.public.blastapi.io` y `https://rpc.mevblocker.io`.
Ambos devolvieron 403 a `eth_chainId`. Es un bloqueo de acceso desde este
entorno; no prueba ausencia de oportunidades ni un defecto de liquidación.
No hubo firma, broadcast, gasto ni wallets conectadas. La falta de namespace
impide afirmar replay desconectado conforme al contrato; los tests unitarios
no sustituyen esa ejecución física.

## Reproducción

Usar checkout completo, cachés/targets y resultados fuera del repo. El almacén
Git fuente debe contener los objetos del manifest. ZIP y metadatos originales
se mantienen fuera del payload público.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 omega/isolation.py --source-git /ruta/source-objects
PYTHONDONTWRITEBYTECODE=1 python3 omega/regression.py \
  --start-directory omega --report /ruta/nueva/omega.json
PYTHONDONTWRITEBYTECODE=1 python3 omega/regression.py \
  --start-directory ci/nqc-census --report /ruta/nueva/census.json
PYTHONDONTWRITEBYTECODE=1 python3 omega/historical_regression.py \
  --source-git /ruta/source-objects --evidence /ruta/insumos --work /ruta/nueva/historical
```

Para Omega, exportar `NQC_D15_ARCHIVE` y `NQC_D16_ARCHIVE`. Para D06 real,
exportar `RMC006_SOURCE_ARCHIVE` y `RMC006_SOURCE_{RUN,ARTIFACT,COMMIT}_METADATA`.
COMMIT debe ser la respuesta de `/git/commits/{sha}`, no `/commits/{sha}`.
Sin insumos, las omisiones se conservan y el recorder no devuelve PASS.

El harness histórico espera `historical-{role}.zip`,
`historical-{role}-run.json`, `historical-{role}-artifacts.json` (un objeto
artifact, no colección), y `historical-{role}-commit.json` cuando se requiere.
Los metadatos D06–D10 van en `upstream/{stage}.{run,artifact,commit}.json`, con
los IDs de `ci/nqc-census/rmc011-real-source-inputs.json`.

| Role | Run original | Artifact original |
|---|---:|---:|
| d08 | 37836967374 | 11576077535 |
| dual | 37839036277 | 11577315781 |
| seven | 37826819250 | 11571178483 |
| new | 37839794172 | 11576204678 |
| discovery | 37841923756 | 11577503474 |
| debt | 37832286518 | 11573678487 |

Los hashes y límites semánticos permanecen en los validadores originales.
Los reportes, logs y hashes de esta ejecución están en `omega/evidence/h2-*`.

## Auditoría posterior y pendientes

La prueba positiva detectó un error en el nuevo parser de logs (ancla regex
sin modo multiline). Se corrigió y se repitieron las 12 pruebas nuevas, Omega
completo y las siete suites históricas. La primera selección del endpoint D06
también fue rechazada correctamente; se repitió con el objeto Git original.

El 94% conserva los cuatro controles H2: los primeros tres suman 75%; del
cuarto se auditaron aislamiento, regresión Python y Rust (3/4 de 25% = 18.75%).
PFT/forks/replay físico sigue parcial. No se cambian gates económicos ni estados
de certificación por este porcentaje.

Faltan acceso RPC a bloques históricos exactos, replay en namespace desconectado,
tratamiento revisado del formato heredado y enlace explícito de evidencia PFT
al productor destino. La certificación real requiere además triadas independientes
reales, cobertura completa de posiciones y ledger transaccional con costos
completos. Nada de ello se infiere de tests offline.
