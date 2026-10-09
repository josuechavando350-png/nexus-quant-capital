# Census: cierre de reconstrucción histórica, certificación pendiente

**No se declara terminado ni certificado Census.** Se completó la reconstrucción
y clasificación del corte histórico especificado abajo. La evidencia faltante
permanece como bloqueo explícito; no se sustituye por estimaciones de rentabilidad.

## Alcance comprobado

Ethereum, bloque **26,095,351**, hash
`0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781`,
timestamp **2026-10-01T05:23:35Z**. Este alcance no es cobertura en vivo.

| Resultado | Evidencia y límite |
| --- | --- |
| 1,045,459 fuentes D11 verificadas | Decodificación canónica de todas las filas, identidades, procedencia, ancla y hash de 3,757,728,513 bytes. No se volvió a ejecutar la importación completa del estado upstream. |
| 474 pares de 400 borrowers | Nueva ejecución del productor Rust original: archivos de pares y decisiones de capital idénticos byte por byte. |
| 42 pares no ejecutables en ese estado | 12 con colateral deshabilitado; 30 con tamaño de liquidación cero según PFT. |
| 432 pares con evidencia insuficiente | Rechazo original de financiación `EXECUTION_BLOCKED`; conservados los motivos de los tokens. No se afirma que nunca puedan ser rentables. |
| 0 valor ejecutable positivo admitido | No equivale a P&L realizado de cero ni a prueba de imposibilidad comercial. El P&L no está probado. |
| Portafolio conciliado | Mismos candidatos, recursos y conflictos. Diferencias explícitas: commit, tree y compromiso del productor. La capacidad concurrente financiada no se afirma. |
| Gas propio: máximo acumulado MXN 2,000 | Contabilidad offline vinculada al ledger. Sin saldo nativo, conversión o financiación autenticados; sin uso retroactivo. Capital propio para principal, colateral y garantías sigue en cero. |

El núcleo D11 recuperado declara por sí mismo `terminal_capital_census_complete=false`.
La certificación histórica D12 tiene alcance de actionability/principal; no
certifica gas, economía ni P&L. Ninguna de esas autoridades se transfiere al nuevo
productor por haber pasado estas pruebas.

## Trabajo material para terminar Census

| Autoridad o requisito | Estado | Evidencia necesaria para cerrar |
| --- | --- | --- |
| Market Truth | Corte histórico reconstruido; alcance temporal global abierto | Reconciliar el universo declarado y recuperar las observaciones detalladas, oportunidades censuradas y momentos reales de recepción. |
| Capital Truth | Núcleo D11 íntegro; admisibilidad operativa incompleta | Pruebas de proveedores, cobertura por candidato, repayment completo y obligaciones; autenticar gas nativo y coste de adquisición bajo el límite autorizado. |
| Economic Truth | Evidencia insuficiente en los 432 pares | Compatibilidad de los 43 activos requeridos, rutas monetizables, costes completos, competencia/inclusión y márgenes conservadores. Puede cerrarse con conclusiones negativas justificadas. |
| Evidencia temporal | Faltan ledgers crudos de D15B | Recuperar episode/censored/winner/economic ledgers por sus hashes. Los tres archivos agregados recuperados no los sustituyen. |
| Reproducción D11 completa | Intento terminado por OOM, exit 137, límite 8 GiB | Ejecutar productor completo en un entorno admisible o revisar un adaptador de memoria que conserve su semántica y demuestre paridad. El lector de fuentes no resuelve esta obligación. |
| Autoridad independiente | Pendiente | Revisar productor y consumidores exactos, commits/trees, fuentes, ledgers de fallos y discrepancias, falsación y límites del alcance. Esta modificación no se certifica a sí misma. |

El dispositivo de recuperación inspeccionado estaba desconectado. Existe el
snapshot de recuperación `248761092`, pero este entorno no tiene una clave SSH
para acceder al servidor. No se contrató infraestructura nueva ni se consumió gas.

## Reproducción

Los archivos originales D06–D10 conservan sus nombres `d06-original.zip`…
`d10-original.zip`. Los recuperados adicionales son `d11-original-core.zip`
y `d12-historical-terminal.zip`. Los pins y snapshots API están versionados.
Use directorios de salida nuevos. El reloj de clasificación debe ser el de la
recepción/evaluación actual; para reproducir un ledger use su timestamp guardado.

```bash
python3 migration/census_v2/prepare_research_replay.py \
  --archive-root "$EVIDENCE" \
  --metadata-root migration/census_v2/evidence/historical-api \
  --out "$REPLAY"

cargo run --release --locked \
  --manifest-path nqc-census/crates/nqc-census-capital/Cargo.toml \
  --bin nqc-rmc011-authority-lock-build -- \
  --input "$REPLAY/legacy-replay-lock-candidate.json" \
  --output "$REPLAY/legacy-replay-lock.json"

cargo run --release --locked \
  --manifest-path migration/census_v2/capital_stream/Cargo.toml -- \
  "$D11_CORE/capital-sources.jsonl" "$STREAM"

cargo run --release --locked \
  --manifest-path ci/nqc-census/rmc012-pft-actionability-bridge/Cargo.toml \
  --bin rmc012-terminal-actionability -- \
  --d08 "$REPLAY/d08-raw/closeout" --d09 "$REPLAY/d09-raw/closeout" \
  --authority-lock "$REPLAY/legacy-replay-lock.json" \
  --d11-sources "$STREAM/capital-sources-aave-view.jsonl" \
  --code-commit dfc259fca3b3144b0623461cb46346e2e960dce1 \
  --code-tree b25947022554a9ba5b50faa3a77831f16010d201 \
  --out "$REPLAY/d12-research"

python3 migration/census_v2/verify_terminal_recovery.py \
  --d11 "$EVIDENCE/d11-original-core.zip" \
  --d12 "$EVIDENCE/d12-historical-terminal.zip" \
  --metadata migration/census_v2/evidence/terminal-api \
  --replay "$REPLAY/d12-research" --output "$REPORT"

python3 migration/census_v2/classify_historical_candidates.py \
  --d08 "$EVIDENCE/d08-original.zip" \
  --d12 "$EVIDENCE/d12-historical-terminal.zip" \
  --policy migration/census_v2/capital-policy.json \
  --gas-events migration/census_v2/evidence/gas-events.json \
  --observed-at "$CLASSIFIED_AT" --out "$CLASSIFICATION"
```

Defina `CARGO_TARGET_DIR` fuera del repositorio y
`PYTHONDONTWRITEBYTECODE=1`. `$D11_CORE` contiene la extracción exacta de su ZIP
autenticado. Los metadatos de productor del comando D12 corresponden al código
original inalterado en ese commit base: verifique esa igualdad antes de repetir
el comando en otra revisión. Los consumidores nuevos se fijan por sus hashes y
por el commit que incluye esta evidencia.

El lock y la salida Rust se utilizan exclusivamente dentro del sobre
`RESEARCH_ONLY.json`. Sus flags históricos no conceden permisos ni una nueva
certificación. El resumen de diferencias de portafolio se conserva expresamente;
no se afirma igualdad completa de todos los archivos.

## Validación y fallos conservados

528 pruebas del workspace Rust original, 9 del puente PFT y 6 del consumidor
nuevo pasaron con Rust 1.98.1. La reparación de LLVM conserva la versión exacta
y verifica el paquete oficial por SHA-256. Las pruebas adversariales adicionales
cubren contabilidad, joins, metadata y paridad sobre archivos reales.

La búsqueda amplia de pruebas Python históricas conserva su resultado previo:
664 ejecutadas, 7 errores de preparación y 3 omitidas. No se presenta como suite
verde. Cinco suites necesitan invocaciones CLI con archivos originales; otras
dos vinculan catálogos históricos diferentes. El fallo OOM de D11 y el límite
de descarga del archivo principal siguen abiertos en el ledger de validación.

No se cambió código importado, no se activaron workflows y no se enviaron
transacciones. La clasificación disponible sirve para descartar promociones
sin evidencia y orientar el trabajo faltante; todavía no autoriza Shadow
certificado, Canary ni afirmaciones de ingresos.
