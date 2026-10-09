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
| 1,045,459 fuentes D11 reproducidas | Reimportación completa de D08/D09 y dos verificaciones en procesos separados. Los nueve archivos originales coinciden byte por byte; el archivo de fuentes tiene 3,757,728,513 bytes. Adaptador histórico y árbol de código exactos fijados; no transfiere certificación. |
| 474 pares de 400 borrowers | Nueva ejecución del productor Rust original: archivos de pares y decisiones de capital idénticos byte por byte. |
| Colateral habilitado de las 400 cuentas: 12.36050759 USD al oráculo | Cinco archivos del análisis histórico reproducidos; agregación SQLite y valoración por posiciones coinciden. Sólo una cuenta alcanza un dólar de colateral habilitado. No equivale a beneficio ni pronóstico mensual. |
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

Actualización del 9 de octubre: [evidencia adicional](additional_evidence/README.md)
incorpora 127 recibos observados en Tenderly, conciliados con el checkpoint dRPC
y el ledger existente: cero discrepancias de gas; cuatro remitentes antes
desconocidos quedan como observaciones separadas. También se concilian 7,200
bloques posteriores al ancla entre Nodies y Tenderly: dos ejecuciones, ninguna
de la cohorte original de 857 cuentas. Esta ventana posterior no completa los
faltantes del estudio histórico de 30 días. Los registros son resultados RPC
decodificados; no conservan bytes HTTP originales ni recepción por petición.
Los 33 controles del suplemento pasan; la política MXN 2,000 y las clasificaciones
económicas originales no cambian. Census sigue sin cierre certificado.

| Autoridad o requisito | Estado | Evidencia necesaria para cerrar |
| --- | --- | --- |
| Market Truth | Corte histórico reconstruido; alcance temporal global abierto | Reconciliar el universo declarado y recuperar las observaciones detalladas, oportunidades censuradas y momentos reales de recepción. |
| Capital Truth | Núcleo D11 íntegro; admisibilidad operativa incompleta | Pruebas de proveedores, cobertura por candidato, repayment completo y obligaciones; autenticar gas nativo y coste de adquisición bajo el límite autorizado. |
| Economic Truth | Evidencia insuficiente en los 432 pares | Compatibilidad de los 43 activos requeridos, rutas monetizables, costes completos, competencia/inclusión y márgenes conservadores. Puede cerrarse con conclusiones negativas justificadas. |
| Evidencia temporal | D15B/D16 reproducidos; universo, transiciones y riesgo inicial también reproducidos | 29,998 candidatos y 134,275 cambios de estado conciliados. Riesgo inicial: 27,850 borrowers con cero discrepancias. Oráculos retenidos: 215,036 bloques; segundo proveedor presente en 4,650 y ausente en 210,386. Sigue faltando adquisición independiente completa, canonicalidad y recepción real de información. Los recibos y el barrido nuevo parcial conservan sus propios faltantes bajo el bloqueo RPC. |
| Reproducción D11 completa | Resuelta dentro del límite de memoria: nueve archivos idénticos | 371.5 segundos, RSS máximo 7,309,316 KiB, 256 pruebas de capital. Se preservan los intentos OOM y la divergencia del importador por roles. Falta la revisión independiente del nuevo productor. |
| Autoridad independiente | Pendiente | Revisar productor y consumidores exactos, commits/trees, fuentes, ledgers de fallos y discrepancias, falsación y límites del alcance. Esta modificación no se certifica a sí misma. |

El usuario reconectó el servidor original. El paquete central completo tiene
71 archivos verificados. La partición temporal de 29,998 cuentas concilia y
los tres archivos D15B y cuatro D16 se reproducen byte por byte. Los 29,998
candidatos temporales conservan clasificación explícita de evidencia insuficiente,
separada del corte D09. Se completó la transferencia de los insumos D15B,
se reprodujeron tres salidas de candidatos/estado y cinco de riesgo inicial,
y se recalcularon los 4,394 fragmentos de oráculos retenidos. Las tres
interrupciones anteriores siguen preservadas; véase `SERVER_RECOVERY.md`.
También se autenticaron las 127 trazas originales: 15,001 llamadas, 20
reversiones y 719 consultas de oráculo. Una consulta de WBTC difiere del precio
al cierre del bloque; cuatro consultas tienen ancestros revertidos. Sus
tratamientos y hashes constan en `WINNER_TRACES.md`; no aumentan la cobertura
de recibos originales completos ni prueban precios de ejecución o P&L.
No se contrató infraestructura ni se consumió gas. La reproducción no acredita
capital operativo, rutas, costes completos, captura ni autoridad independiente.

Se recuperó una vía adicional mediante RPC públicos. Las consultas se detuvieron
por denegación de acceso de red a las `17:13:21Z` del 9 de octubre. La herramienta
indicó cancelación de aprobación de red. No se intentó eludir esa restricción.
Los datos parciales y sus fallos se concilian offline en `HISTORICAL_RPC.md`;
no prueban cobertura completa, observación previa de Nexus ni captura comercial.

La recuperación adicional de nueve respaldos encontró dos incrementos útiles:
el análisis económico del corte D09 y 18 respuestas RPC que documentan tres
transacciones ya presentes en el universo de 127. Sus recibos coinciden con
BlockPI/dRPC y permiten desglosar gas base y prioridad sin contarlo dos veces.
Los otros respaldos contienen candidatos de investigación o evidencia previa
acotada; no recuperan los ledgers originales D15B. Véase `LIBRARY_RECOVERY.md`.

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

Actualización del 9 de octubre: se recuperaron los cinco archivos que faltaban
para cuatro suites históricas. Sus hashes e identidades originales coinciden;
**114 pruebas originales pasan, cero omitidas**, en copias con los catálogos
históricos exactos. Se conservan las aserciones, los archivos importados y los
dos intentos fallidos de preparación/lectura del log. Véase
`recovered_regressions/README.md`. Los párrafos siguientes preservan el estado
anterior; el resultado amplio de 664 pruebas no se reetiqueta como verde.

528 pruebas del workspace Rust original, 9 del puente PFT y 6 del consumidor
nuevo pasaron con Rust 1.98.1. La reparación de LLVM conserva la versión exacta
y verifica el paquete oficial por SHA-256. Las pruebas adversariales adicionales
cubren contabilidad, joins, metadata y paridad sobre archivos reales.

La búsqueda amplia de pruebas Python históricas conserva su resultado previo:
664 ejecutadas, 7 errores de preparación y 3 omitidas. No se presenta como suite
verde. En invocaciones separadas se resolvieron tres errores de preparación y
se ejecutaron las tres integraciones D06 antes omitidas: 63 pruebas originales
pasaron, además de seis controles nuevos de contexto. Se conservaron las
aserciones originales y se restauraron los catálogos por hash únicamente en
copias nuevas. Cuatro suites todavía requieren cinco archivos originales;
véase `HISTORICAL_REGRESSIONS.md`. El límite de memoria de D11 quedó
resuelto mediante un adaptador fijado en una copia nueva: nueve archivos
idénticos al original. Su historial de fallos se conserva. El límite de descarga
del archivo principal continúa; se recuperó el núcleo original por separado.

La versión importada agrupaba admisión de tokens por dirección; el productor
histórico distinguía dirección y rol. Los datos reales contienen 44 direcciones
repetidas y cero claves token/rol duplicadas. El adaptador de reproducción
incluye el importador histórico exacto en un módulo separado. No se cambió ni
se sustituyó silenciosamente la semántica de los archivos importados.

Los consumidores nuevos pasan 23 pruebas unitarias Python y 7 pruebas sobre
archivos históricos y respuestas RPC reales; los 9 controles de aislamiento
también pasan. La verificación de objetos originales conserva las 637 entradas
importadas y cero workflows activos. Véanse los logs y alcance de cada suite;
no se suman ejecuciones repetidas como casos distintos.

No se cambió código importado, no se activaron workflows y no se enviaron
transacciones. La clasificación disponible sirve para descartar promociones
sin evidencia y orientar el trabajo faltante; todavía no autoriza Shadow
certificado, Canary ni afirmaciones de ingresos.
