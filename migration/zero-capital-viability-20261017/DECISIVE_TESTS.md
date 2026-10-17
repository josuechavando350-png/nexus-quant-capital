# Pruebas decisivas ejecutadas y bloqueadas

Prioridad escogida: **reserva previa y absorción del fallo**. Es común a las tres rutas, puede refutar el uso de beneficio futuro como saldo inicial y se comprueba gratuitamente con fuentes y trazas ya disponibles. No requiere tres pipelines, nuevo ejecutor, proveedor ni firma. El objeto ejecutado es una auditoría offline, no un replay EVM nuevo.

| Orden | Hipótesis | Datos / coste | Resultado y alcance |
|---|---|---|---|
| 1 | El excedente futuro evita financiar gas previo; una fixture prueba financiación externa | Fuente one-shot y trazas Nitro guardadas / $0 | **REFUTADO**: reservas positivas; fallo Nitro consume fondos; fixtures no son compromiso |
| 2 | Sumar paymaster y gas da siempre coste externo consolidado | Transferencias guardadas / $0 | **REFUTADO**: depende de propiedad; partición exacta conserva activos |
| 3 | El ejecutor Aave original es candidato de bloque actual | Fuente exacta / $0 | **REFUTADO sin modificarlo**: guardas históricas, sin vía productiva acreditada |
| 4 | Robinhood puede admitirse integralmente con financiación ajena | Dependencias completas y acuerdo ausentes | **BLOCKED**, no stubs ni retorno EVM presentado como admisión |
| 5 | Morpho B permite replay auténtico completo y neto propio | Falta testigo padre/tx0/Fluid | **BLOCKED**; orden y aritmética no reconstruyen storage |
| 6 | Existe captura previa al corte independiente | Faltan tiempos y señal candidata comparable | **BLOCKED**; tests de rechazo temporal sí ejecutados |

## Cambios y comprobaciones

- `comparison_audit.py`: reserva EOA en wei, transferencias únicas por cadena/activo/actor, fallo financiado separado, control temporal y clasificación de las 141 transacciones. Reutiliza los tres módulos económicos existentes, sin modificar sus fuentes.
- `test_comparison_audit.py`: cinco tests, incluyendo input no entero, doble conteo, activos/cadenas separados, flujo duplicado, corte vencido, relojes desconocidos, agrupación por tx y ningún ascenso automático a rentabilidad.
- `reproduce_reference_audits.py`: verifica SHA-256 de los 121 archivos exportados de `6693542e675f930a7ef0a4fd60cb72e7a6608845`, reejecuta auditores originales y exige igualdad semántica de ambos JSON. Se detiene ante datos cambiados y no sobrescribe una salida existente.

| Verificación | Estado en esta auditoría | Evidencia |
|---|---|---|
| Morpho Python existente | **PASS 168**, recién ejecutadas | `evidence/morpho-python.log`, `initial-validation.json` |
| Aave gate y 17 tests originales | **PASS 17**; gate produce clasificación comercial BLOCKED | `aave-reference-tests.log`, `aave-source-gate.json` |
| Reconciliador Robinhood original | **PASS** sobre respuestas guardadas | `robinhood-reconciliation.json` |
| Nuevos tests comparación | **PASS 5** | `comparison-tests.log`, `comparison-validation.json` y validación final |
| CLI comparación | Salida **2 esperada**: no admisión | `comparison.json` |
| Aislamiento | **PASS 9** y verificador | `final-isolation.log`, `final-verifier.log`, `final-validation.json` |
| Reproductor con 121 hashes | **PASS**, JSON iguales | `reference-reproduction.log`, `reference-reproduction/commands.json` |
| Morpho Solidity, 50 pruebas previas | **NOT_RUN en esta auditoría**; fuente sin cambios | Logs anteriores en rama base; no se cuentan como nuevas |
| Geth/Nitro/Anvil, controles AA anteriores | **NOT_RUN** | Revisión/reconciliación de expediente, no nuevo runtime |
| Bundler integral | **BLOCKED** por entorno y financiación | Decisión/REOPENING originales |
| Rust, CI remota, producción, firma/envío | **NOT_RUN** | No cambios Rust ni autorización operativa |

Cero tests ejecutados terminaron fallidos o omitidos; los resultados económicos bloqueados no se convierten en PASS comercial. Las repeticiones del mismo test no incrementan el conteo. T36/T37/T38, pruebas nativas y benchmarks son evidencia histórica citada, no suites ejecutadas ahora. El verificador reporta 106 workflows deshabilitados, 0 activos; los objetos originales remotos para verificación completa no están disponibles en este checkout. Ese límite se conserva, no se sustituye por certificación.

## Reproducción

Desde la raíz del repositorio, usar Python 3.12.14 y PyCryptodome 3.23.0. `evidence/environment.json` fija versiones y hashes disponibles: Forge 1.7.1 y solc 0.8.24/0.8.19/0.8.28/0.5.16, consultados con `--version`, no usados para una nueva ejecución Solidity. Los registros de comandos contienen ejecutable, cwd, inicio/fin UTC, exit code y SHA de salida.

```sh
python -m unittest discover -v -s migration/zero-capital-viability-20261017 -p 'test_*.py'
python migration/zero-capital-viability-20261017/comparison_audit.py
# exit 2 esperado: evidencia económica insuficiente; no ocultarlo con un PASS.
python -m unittest discover -v -s migration -p test_isolation.py
python migration/verify_isolation.py
```

La suite Morpho se ejecutó con cwd en `migration/experiments/morpho-sponsored-gas`, como registra `initial-validation.json`. Desde ese directorio:

```sh
python -m unittest discover -v -s tests -p 'test_*.py'
```

Para auditores originales: el commit de decisión debe estar previamente disponible mediante lectura pública autorizada. Exportar **solo** los seis paths de `evidence/reference-extraction.json` con `git archive 6693542e675f930a7ef0a4fd60cb72e7a6608845 <paths>`, extraer en un directorio temporal nuevo y ejecutar:

```sh
python migration/zero-capital-viability-20261017/reproduce_reference_audits.py --source-dir /tmp/nqc-reference --out-dir /tmp/nqc-reference-new-result
```

No ejecutar scripts de captura, instalación o despliegue del archivo exportado. El reproductor solo llama a los dos auditores offline y al test de aritmética/fuente Aave. El manifiesto de exportación fija sus inputs. Los hashes de esta entrega están en `MANIFEST.sha256` (se excluye a sí mismo). `comparison-initial.json` conserva los bytes del primer informe: se recuperaron retirando únicamente los dos campos añadidos posteriormente y comprobando igualdad con el SHA registrado al ejecutarlo; el detalle está en `comparison-validation.json`. El informe final es `comparison.json`.

## Errores y límites conservados

No hubo nuevos intentos RPC de estado denegado. Los bloqueos históricos 403/405, null/poda, cuota agotada, instalación incompleta y aprobación automática denegada permanecen en sus fuentes. Durante navegación de archivos hubo rutas inexistentes y una lectura Git con cwd incorrecto, corregidas usando el árbol Git; no son pruebas EVM ni evidencia de mercado. Una apertura web de EntryPoint v0.7 devolvió DisabledError: no se contó como fuente leída. Los contenidos originales del bundler sí se leyeron por su commit y se compararon con cuatro SHA-256 del expediente. No se eludió ninguna restricción de acceso.
