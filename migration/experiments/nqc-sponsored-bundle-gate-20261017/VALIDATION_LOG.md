# Validación realmente ejecutada — 2026-10-17

| Comprobación | Resultado | Evidencia |
|---|---|---|
| Compilación local original | PASS, 14 artefactos | build.log, build-manifest.json, bytecode-parity.json |
| C1 control seis bloques y coordinación | PASS, mismo gas 2,339,206 | A1_six_blocks.json, A2_C1_zero_cash.json |
| Conjunto de escenarios | 27 ejecutados; 149 recibos observados | run-index.json, coordinated-run.log |
| Admisión al pool / falta de fondos | 4 controles ejecutados | pool-admission-probe.json |
| Exclusión previa a inclusión | 2 controles, bloques vacíos | policy-exclusion.json, policy-exclusion.log |
| Conciliación y criterios | 27 conciliados; 0 admisiones comerciales | economics.log, FINANCIER_AND_BUILDER_LEDGER.json |
| Pruebas nuevas de evidencia | 14 PASS, 0 fallos al cierre | evidence-tests.log |
| Python anterior | 168 PASS, 0 fallos, 0 skipped | python-regression.log |
| Solidity anterior default | 33 PASS, 0 fallos, 0 skipped | solidity-default.log |
| Solidity anterior core | 17 PASS, 0 fallos, 0 skipped | solidity-core.log |
| Aislamiento | 9 PASS + verificador PASS limitado | isolation-tests.log, isolation-verifier.log |
| Archivos Directiva 003 preservados | 67 idénticos a 937a833 | SOURCE_LOCK.json |
| Replay B y nuevos históricos | BLOCKED_EXTERNAL_EVIDENCE; no nuevos intentos | candidatos congelados y documentos 003 |
| Titán/Quasar producción, firmas, redes públicas | NOT_RUN | sin interfaces de envío externas |
| Rust/CI/servicios | NOT_RUN | no cambios en esas líneas |

Las simulaciones temporales usadas para calcular U, las iteraciones de corrección y los recibos de setup externo no se suman a 149 ni a 27. Las variantes de reversión esperada no se presentan como ciclos favorables. Los dos archivos POLICY_trial_* son candidatos descartados, no transacciones incluidas por la política final. El verificador de aislamiento declara `original_objects_checked=false` y `canonical_recertification=false`; no se amplía su alcance a recertificación histórica.

## Herramientas y requisitos

Python 3.12.14 / PyCryptodome 3.23.0; Forge y Anvil 1.7.1. Solc 0.8.19 (Morpho, optimizer 200, Paris), 0.5.16 (V2/ERC20, 999999, Istanbul), 0.8.24 (NQC/Solmate/helpers, 200, Cancun), 0.8.28 (Bundler3/adapter, 999999, viaIR, Cancun). SHA-256 del ejecutable, fuentes fijadas y bytecodes en SOURCE_LOCK.json. Todas las herramientas utilizadas ya estaban disponibles gratuitamente; no se activó infraestructura.

Repos locales con blobs fijados: morpho-blue `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`, nqc-uniswap-v2 `6a9e7c97860676e0992f22a49665760444c1cdf5`, bundler3 `b4014349e3527f44ceaab697b26e29f2b11457f3` y sus submódulos, incluido Solmate `8d910d876f51c3b2585c9109409d601f600e68e1`. No se parchean fuentes originales. El compilador 003 se importa y se redirige su output a esta carpeta; LabSupport.sol se copia byte por byte con el mismo nombre de unidad. La paridad se exige para todos los artefactos C1, no solo para el texto fuente.

## Reproducción

Variables del entorno usado; pueden apuntarse a otro directorio con los mismos blobs/binarios fijados:

```sh
export NQC_WORKSPACE=/workspace/scratch/f380716a269b
export NQC_REPO="$NQC_WORKSPACE/nexus-quant-capital"
export NQC_PYTHON="$NQC_WORKSPACE/nqc-python/bin/python"
export NQC_TOOLCHAIN="$NQC_WORKSPACE/nqc-toolchain"
export NQC_EXP="$NQC_REPO/migration/experiments/nqc-sponsored-bundle-gate-20261017"
export NQC_ANVIL="$NQC_TOOLCHAIN/node_modules/@foundry-rs/anvil-linux-amd64/bin/anvil"
cd "$NQC_EXP"
"$NQC_PYTHON" build_reference.py --workspace "$NQC_WORKSPACE" --toolchain "$NQC_TOOLCHAIN"
"$NQC_PYTHON" local_node.py "$NQC_ANVIL"
"$NQC_PYTHON" run_coordinated.py --anvil "$NQC_ANVIL"
"$NQC_PYTHON" economics.py
"$NQC_PYTHON" policy_exclusion.py --anvil "$NQC_ANVIL"
"$NQC_PYTHON" -m unittest -v test_evidence
```

El run completo es la reproducción recomendada. `--only` es diagnóstico: genera un índice parcial y no sustituye el conjunto final. La evidencia se regenera solo aquí. Los puertos efímeros y duración de tests cambian; gas, balances, estado y afirmaciones no dependen del puerto. No prometer identidad textual de logs con tiempos/puertos distintos.

Regresión ejecutada desde el experimento anterior, con out/cache nuevos para no modificarlo:

```sh
cd "$NQC_REPO/migration/experiments/morpho-sponsored-gas"
"$NQC_PYTHON" -m unittest discover -v -s tests -p 'test_*.py'
"$NQC_TOOLCHAIN/node_modules/.bin/forge" test --offline --use "$NQC_TOOLCHAIN/solc-0.8.24" --out "$NQC_EXP/build/forge-default" --cache-path "$NQC_EXP/build/cache-default" -vv
FOUNDRY_PROFILE=core "$NQC_TOOLCHAIN/node_modules/.bin/forge" test --offline --use "$NQC_TOOLCHAIN/solc-0.8.24" --out "$NQC_EXP/build/forge-core" --cache-path "$NQC_EXP/build/cache-core" --match-path 'tests-core/*.t.sol' -vv
cd "$NQC_REPO"
"$NQC_PYTHON" -m unittest discover -v -s migration -p test_isolation.py
"$NQC_PYTHON" migration/verify_isolation.py
```

La suite core lee los artefactos originales previos out-upstream, disponibles en este entorno; su reconstrucción está descrita en el REPRODUCE anterior. No sustituirlos por mocks si faltan. Los comandos anteriores se ejecutaron con redirección a los logs evidence/ correspondientes.

## Errores y limitaciones conservados

`attempt-2-failed.log`: StopIteration al no encontrarse un retorno por contaminación del pool entre candidatos. Corregido con vaciado explícito y aserción de pool vacío. También se reserva el límite máximo de gas para que el retorno a un receptor que revierte sea realmente incluido y cobrado. `attempt-3-test-failure.log`: expectativa incorrecta sobre prioridad; se documenta y comprueba el orden observado. Después se repitieron los escenarios completos y la suite de evidencia; cero fallos pendientes de esas suites.

La prueba no genera claves ni firma; emplea únicamente solicitudes unsigned al hijo local. Las configuraciones no deshabilitan el límite de tamaño de código, gas de bloque ni validación EVM de saldo. Las asignaciones anvil_setBalance son solo actores externos de fixture, jamás NQC. Cada proceso termina en finally. No se probaron políticas de un builder real ni se reintentaron endpoints denegados.
