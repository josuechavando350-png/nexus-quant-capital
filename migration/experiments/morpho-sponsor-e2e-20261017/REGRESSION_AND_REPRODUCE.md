# Regresión y reproducción

Estado final de las comprobaciones de este estudio (no suma de informes anteriores):

| Comprobación | Resultado | Log |
|---|---|---|
| Morpho Python anterior | RUN — PASS 168, FAIL 0, skipped 0 | `evidence/python-regression.log` |
| Morpho Solidity default | RUN — PASS 33, FAIL 0, skipped 0 | `evidence/solidity-default.log` |
| Morpho Solidity core original | RUN — PASS 17, FAIL 0, skipped 0 | `evidence/solidity-core.log` |
| Aislamiento | RUN — PASS 9; verificador PASS limitado | `evidence/isolation-tests.log`, `isolation-verifier.log` |
| Nuevas pruebas de evidencia | RUN — PASS 10 | `evidence/new-tests.log` |
| Anvil local | RUN — 21 escenarios, no 21 operaciones rentables | `evidence/e2e-run.log`, `run-index.json` |
| Reconciliación | RUN — cada snapshot/flujo por activo y actor coincide | `evidence/reconciliation.log` |
| Replay B | BLOCKED_PRESTATE | `MORPHO_B_REPLAY_BLOCKERS.md` |
| E2E C2 con recibos completos | NOT_RUN | Solo su suite core existente se reejecutó |
| Rust, Nitro, AA, CI remota | NOT_RUN | Sin cambios en esas líneas |
| Patrocinio, captura e ingreso reales | NO_EJECUTADO / PENDIENTE | No autorizado ni acreditado |

El verificador encuentra 106 workflows deshabilitados y cero activos. `original_objects_checked=false` y `canonical_recertification=false`: no se convierte su PASS de aislamiento en recertificación del material histórico.

## Herramientas

Python 3.12.14; PyCryptodome 3.23.0. Forge y Anvil 1.7.1. Solc 0.8.24 para NQC/helpers/Solmate; 0.8.19 para Morpho; 0.5.16 para Uniswap. Las regresiones Bundler3 usan el artefacto upstream previo de solc 0.8.28. Las versiones completas y hashes de los compiladores usados están en `evidence/build-manifest.json`; Anvil en `anvil-provenance.json` y `run-index.json`. Anvil exige además el SHA-256 fijado al arrancar. Los archivos de salida no dependen de librerías EVM nuevas de Python.

El checkout `morpho-blue` debe contener `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`; `nqc-uniswap-v2`, `6a9e7c97860676e0992f22a49665760444c1cdf5`; `bundler3/lib/permit2/lib/solmate`, `8d910d876f51c3b2585c9109409d601f600e68e1`. Los nombres de directorio son argumentos de entorno, no endpoints. `build_local.py` lee blobs Git fijados incluso si el checkout tiene otro HEAD, verifica identidad y no modifica esos repositorios.

La instalación de Anvil se limitó al paquete público gratuito `@foundry-rs/anvil-linux-amd64@1.7.1`, con `--ignore-scripts --no-audit --no-fund --save-exact`. No se creó cuenta ni infraestructura. npm verificó la integridad del paquete; se conserva la integridad SHA-512 y el SHA-256 del ejecutable.

## Comandos de regresión

Con las variables del README, desde la raíz:

```sh
"$NQC_PYTHON" -m unittest discover -v -s migration -p test_isolation.py
"$NQC_PYTHON" migration/verify_isolation.py
```

Desde `migration/experiments/morpho-sponsored-gas`:

```sh
"$NQC_PYTHON" -m unittest discover -v -s tests -p 'test_*.py'
"$NQC_TOOLCHAIN/node_modules/.bin/forge" test --offline --use "$NQC_TOOLCHAIN/solc-0.8.24" -vv
FOUNDRY_PROFILE=core "$NQC_TOOLCHAIN/node_modules/.bin/forge" test --offline --use "$NQC_TOOLCHAIN/solc-0.8.24" --match-path 'tests-core/*.t.sol' -vv
```

Las regresiones core necesitan los artefactos `out-upstream/` descritos en el REPRODUCE anterior. Si no están disponibles, seguir su compilación fijada en un checkout de reproducción, o clasificar ese grupo BLOCKED; no reemplazar contratos originales por mocks.

## Fallos durante implementación, corregidos

El primer envío unsigned retornó hash antes de que Anvil terminara de minar; el lector inmediato vio `null`. Se añadió una espera acotada de hasta 2 s, sin convertir ausencia de recibo en éxito. La creación original de Morpho excedió el límite provisional de 4 millones de gas: se amplió a 8 millones para el **setup externo**, conservando el coste real del recibo. Los límites de despliegues NQC permanecen en 4 millones cada uno. No se redujo lógica, alteró el original ni ocultó una obligación para pasar.

La revisión posterior a `9188d693255fc4ebc03c4499b046f651ba8b4e8d` detectó que el nuevo compilador usaba 999999 optimizer runs para Morpho, mientras la referencia previa usa 200. Ambas compilaciones provenían de las mismas fuentes originales, pero no daban el mismo bytecode/gas. Se corrigió a 200, se añadieron settings al manifiesto y aserciones de igualdad de bytecode, y se repitieron los 21 escenarios y 10 tests de evidencia. La liquidación pasa de 502088 a **502632 gas** y el total de 2338662 a **2339206**. `optimizer-alignment.json` preserva los dos resultados y su commit; `original-bytecode-parity.json` comprueba igualdad exacta de Morpho y V2 con los artefactos anteriores. Las cifras de todos los documentos actuales corresponden al build alineado, no al commit previo.

La primera proyección al gate usaba un contenedor de campos distinto. Se corrigió para emitir las claves exactas del esquema y nonces leídos del nodo; el rechazo final es por chain 31337, que no se finge mainnet. También se separó `local_control_assertions_pass` de `EVM_LOCAL_PASS`: un fallo esperado puede superar el control de regresión sin que la liquidación haya completado.

No se conservó un recibo íntegro del primer intento fallido de setup: no se presenta ese relato de depuración como evidencia histórica. Las reversiones F03 y F04–F10 sí tienen recibos y trazas publicados. Las repeticiones para corregir el lector, flags o fuente no aumentan los conteos de pruebas únicas.
