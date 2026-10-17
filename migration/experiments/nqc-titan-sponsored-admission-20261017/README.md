# Directiva 005 — C1 y admisión de patrocinio

Resultado: **MODEL_ONLY / BLOCKED_EXTERNAL_EVIDENCE**. Tres variantes EVM nuevas, 11 recibos de candidato, 12 grupos de comprobación; no firmas, relay, fork ni fondos públicos. Consultar RESEARCH_DECISION.md y RESEARCH_STATUS.md. Todos los cambios están en la nueva carpeta/rama; fuentes y evidencia 004 permanecen idénticas.

## Reproducción offline de evidencia incluida

Desde la raíz del repositorio, Python 3.12.14 y PyCryptodome 3.23.0:

```sh
NQC_PY=/workspace/scratch/f380716a269b/nqc-python/bin/python
NQC005=migration/experiments/nqc-titan-sponsored-admission-20261017
"$NQC_PY" "$NQC005/build_evidence.py"
"$NQC_PY" -m unittest discover -s "$NQC005" -p 'test_*.py' -v
"$NQC_PY" -m unittest discover -s migration/experiments/nqc-sponsored-bundle-gate-20261017 -p 'test_*.py' -v
"$NQC_PY" -m unittest migration.test_isolation -v
"$NQC_PY" migration/verify_isolation.py
```

Sólo rederiva ledgers/comprobaciones; **no vuelve a ejecutar la EVM**. Requiere el checkout completo, no únicamente esta carpeta. El ZIP es expediente, no distribución de herramientas ni checkout de todas las dependencias.

## Repetir las tres ejecuciones nuevas

```sh
NQC_ANVIL=/workspace/scratch/f380716a269b/nqc-toolchain/node_modules/@foundry-rs/anvil-linux-amd64/bin/anvil
NQC004_ARTIFACTS=migration/experiments/nqc-sponsored-bundle-gate-20261017/build/artifacts.json
"$NQC_PY" "$NQC005/run_identity.py" --anvil "$NQC_ANVIL" --artifacts "$NQC004_ARTIFACTS"
"$NQC_PY" "$NQC005/build_evidence.py"
"$NQC_PY" -m unittest discover -s "$NQC005" -p 'test_*.py' -v
```

Anvil 1.7.1, commit 4072e48705af9d93e3c0f6e29e93b5e9a40caed8, binario SHA-256 fijado por local_node. El arnés termina su hijo en finally, sólo loopback 31337, `--accounts 0`, solicitudes unsigned, sin fork. Se conservó el override del pool y la validación EVM de saldo. Repeticiones pueden variar puertos/horarios de logs, no se exige igualdad textual de esos campos.

`artifacts.json` es caché compilada no versionada. En un entorno limpio: obtener gratuitamente los blobs/toolchains fijados por SOURCE_LOCK de 004; extraer **una copia desechable** del commit 9988e425 en otro directorio (`git archive`), ejecutar allí `build_reference.py --workspace <fuentes-locales-fijadas> --toolchain <compiladores-fijados>` y pasar su `build/artifacts.json` mediante `--artifacts`. No reconstruir sobre la evidencia protegida. Los comandos y versiones de compilación de 004 están en su VALIDATION_LOG.md; 005 verifica los 14 hashes de bytecode antes de ejecutar, sin reemplazarlos por mocks. Compiladores: 0.8.19 Morpho, 0.5.16 V2, 0.8.24 NQC/auxiliares, 0.8.28 adaptadores heredados. Esta sesión reutilizó los artefactos y **no recompiló** Solidity.

## Alcance de comprobaciones

- 12 pruebas nuevas: identidad, balances, nonces, caps, fronteras y desconocidos. 0 fallos al cierre.
- 14 pruebas de evidencia 004 reejecutadas; 9 de aislamiento reejecutadas, verificador PASS limitado.
- 26 escenarios anteriores conciliados en el reporte 005 (A1 de seis bloques no se incluye); controles de exclusión leídos. Los 27 escenarios EVM de 004, 168 Python antiguos y 50 Solidity son antecedentes **no reejecutados** aquí.
- No replay B, no censo nuevo, no Rust/CI, no aceptación real. Se detiene en la evidencia externa faltante.

SHA-256 de archivos publicados: `MANIFEST.sha256`. SHA base y dependencias: SOURCE_LOCK.json. Logs: evidence/*.log. El verificador no recertifica objetos históricos (`original_objects_checked=false`).
