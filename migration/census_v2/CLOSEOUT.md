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

Préstamos observados en trazas, 10 de octubre: se recorren las 127 transacciones
y se concilian 49 llamadas de entrega/callback/devolución en 46 de ellas con
98 transferencias únicas de recibos, sobre diez activos. La ruta que el render
nombra `flashLoan` / `onMorphoFlashLoan` amplía la observación previa limitada a
eventos Aave/Balancer. Las devoluciones igualan los principales observados;
no se infieren comisiones completas cero, ABI/estado autenticado ni acceso de
Nexus. Pasan 58 controles afectados y nueve de aislamiento; las clasificaciones
siguen pendientes. Véase `execution_replay/TRACE_LOANS.md`.

Inventario WETH, 10 de octubre: 50 movimientos de los nueve casos fijan 21
mínimos iniciales positivos por cuenta; 15 se ocultan si sólo se mira el delta
final. El ejecutor del caso 4 exige al menos 3,379,677,466,555,340 wei WETH bajo
la semántica observada. No se atribuyen inventarios externos a Nexus ni se
considera financiado un mínimo cero. Se reproducen las 97 filas previas; pasan
50 controles afectados, nueve de aislamiento y los 637 objetos originales.
Esto delimita requisitos de financiación, no prueba balances, costes, captura
ni cierre. Véase `execution_replay/WETH_INVENTORY.md`.

Cuarto checkpoint cerrado, 10 de octubre 01:31:07Z: **25,000 bloques nuevos y
1,675,000 precios** concilian con dRPC. La unión verificada por dos operadores
alcanza **85,170 / 215,036 bloques**, con **129,866 pendientes**. Se reproduce
todo el prefijo de 80,000 bloques de la continuación sin duplicar los anteriores;
los 170 del archivo abierto se excluyen. Eventos y recibos completos vuelven
a conciliar. Fuentes, respuestas exactas y manifiesto del delta se conservan;
el trabajador sigue activo sin reinicio. Véase `oracle_recovery/CHECKPOINT_004.md`.
Este incremento todavía no alcanza 10/20 y no cierra Census.

Control integral de cobertura, 10 de octubre: se vuelven a comparar desde las
fuentes los 55 archivos cerrados del checkpoint 003, los oráculos previos y los
139 eventos / 127 recibos completos. La unión exacta sigue en **60,170 bloques**,
con **154,866 pendientes**; se excluyen 1,560 solapamientos previos y 20 capturas
abiertas. El control nuevo impide declarar cobertura por contadores o por una
etiqueta terminal sin archivos exactos. Esto reproduce la evidencia existente;
no suma cobertura nueva ni alcanza 10/20. Véase `oracle_recovery/COVERAGE_GATE.md`.

Conciliación por cuentas, 10 de octubre 01:02Z: los nueve casos WETH quedan
separados en 97 filas transacción/cuenta, 26 movimientos nativos y diez retiros.
En los rangos 2, 3, 4 y 5, el flujo WETH del ejecutor no equivale al excedente
de la liquidación seleccionada. Los pagos, otros activos y gas no se duplican
ni se agrupan por un propietario supuesto. Un préstamo Balancer del caso 5
concilia entrega y devolución por 342,642,361,343,309,991 wei WETH; no acredita
acceso o financiación de Nexus. Pasan 42 controles Python y nueve de aislamiento
tras conservar y resolver un fallo de espacio temporal. Véase
`execution_replay/WETH_ACCOUNTS.md`. Continúan sin probar balances completos,
costes, captura y beneficio; ninguna clasificación se promueve ni se alcanza
un hito por este incremento.

Realización nativa, 10 de octubre 00:33Z: las cuatro pruebas del harness con
Balancer pasan offline en ambos modos. Tras repayment y pago observado, retira
0.000240390311727552 WETH e incrementa el saldo del operador de prueba en igual
cantidad de ETH, sin consumir inventario previo. La prueba de reversión también
pasa. No autentica una wallet real ni gas inicial; el componente de gas deja
margen al precio histórico y lo agota a 1 gwei. Se conservan todos los costes
desconocidos y `complete_profit_wei=null`. Véase
`execution_replay/NATIVE_REALIZATION.md`; Census y sus umbrales siguen abiertos.

Segundo checkpoint de oráculos, 10 de octubre 00:22:43Z: **48,170 / 215,036
bloques verificados por dos operadores**, faltan **166,866**. Se compararon
2,881,000 precios de los 43,000 bloques cerrados de la continuación y no hubo
discrepancias. Incluye los 2,000 del checkpoint anterior; suma 41,000 bloques
nuevos, sin duplicar el prefijo. Los 220 capturados en el archivo abierto se
excluyen. Lecturas remota y local producen informes idénticos; archivo exacto
y fuentes se conservan en dos partes autenticadas. El recolector existente
sigue activo. Véase `oracle_recovery/README.md`. Todavía no se alcanza 10/20.

Tercer checkpoint cerrado, 10 de octubre 00:44:28Z: el delta conserva sólo los
12 archivos nuevos posteriores al segundo checkpoint. Sus **12,000 bloques y
804,000 precios** coinciden con los chunks dRPC originales, sin discrepancias.
El prefijo verificado de la continuación alcanza 55,000 bloques y la unión del
segundo operador **60,170 / 215,036**; faltan **154,866**. Los 20 registros del
archivo abierto se excluyen. El archivo delta fija el hash del ZIP y del
readback base, y el verificador rechaza sustitución o doble conteo del prefijo.
Pasan tres controles reales/adversariales. El trabajador existente seguía sano
bajo el mismo PID y lock; no fue reiniciado ni duplicado. Todavía no es 10/20.

Actualización del 10 de octubre, 00:20Z: la comparación controlada Aave/Balancer
pasó y se reprodujo sin red. En el estado histórico fijado, Balancer tiene
liquidez suficiente y comisión cero; la variante nueva paga atómicamente
0.095915734379292898 ETH al receptor autenticado del bloque, devuelve el
préstamo y conserva 0.000240390311727552 WETH **antes de gas y otros costes**.
La prueba negativa revierte también el pago; el saldo nativo previo permanece
intacto. El intento previo que suponía saldo inicial cero se conserva fallido.
Si se impone ese mismo pago a Aave, faltan 0.005101616615551362 WETH incluso
antes del gas. No se afirma que el pago observado sea el mínimo necesario.
El componente de gas medido deja margen al precio histórico, pero a 1 gwei
lo agota; no incluye todos los costes ni es una cotización de transacción.
Son nuevos escenarios de investigación de un caso elegido retrospectivamente,
no prueba de captura, rentabilidad global o admisión. Véase
`execution_replay/FUNDING.md`; los umbrales 10/20, 15/20 y 20/20 siguen pendientes.

Actualización posterior de acceso/ejecución: Nodies permitió una adquisición
nueva de 115 respuestas históricas. **Las dos pruebas del fork WETH pasan** y
se repiten en copia nueva, sin red, en modo normal y aislado. Las fuentes
originales permanecen intactas; una corrección de mayúscula del checksum sólo
se aplica en la copia. Se conserva el rechazo de dRPC y BlockPI sin reintentos.
No se necesita contratar Cloudflare. La reconstrucción RLP/Keccak de ambos
headers autentica que el pago de 0.095915734379292898 ETH va al receptor de
comisiones del bloque ganador. El gas del recibo es base fee quemada, con cero
priority fee, y se cuenta una sola vez. No prueba propiedad, acuerdos ni utilidad.
El excedente del fork antes de costes coincide, pero la medición de gas difiere
entre modos; no se presenta como cotización de producción. Pasan 19 controles
Python y 9 de aislamiento. Véase `execution_replay/README.md` y sus informes.
Se resuelve el acceso para esta prueba; siguen abiertos cobertura, compatibilidad,
economía completa, pruebas de estado y certificación independiente.

Actualización prioritaria de ejecución/economía: se conciliaron las 127 trazas
con los recibos completos: 332 transferencias nativas visibles, 18 valores de
`delegatecall` excluidos como pagos duplicados y 98 retiros WETH coincidentes.
En el caso WETH de rango 1, todo el excedente convertido a ETH se paga a dos
destinos cuya propiedad/función económica sigue sin acreditar. No se interpreta
como utilidad retenida ni se resta automáticamente como coste. Pasan 8 pruebas
originales del ejecutor con mocks y 12 controles Python. El fork nuevo se detuvo
en su primera consulta por HTTP 403 de dRPC; no se declara reproducido. Véase
`execution_replay/README.md`. Este incremento precisa el destino de fondos y
la semántica de pagos; no acredita rentabilidad ni cambia la admisión de capital.

Actualización de cobertura: el nuevo barrido BlockPI completó los 215,036
bloques originales y coincidió con las 139 liquidaciones de Blockscout. Los
127 recibos nuevos de dRPC coinciden completamente, incluidos sus logs, con
Tenderly. Se conservan los cuerpos RPC exactos y las horas de recepción actuales.
Quedan resueltos esos faltantes de eventos/recibos; **la cobertura secundaria
de oráculos seguía incompleta en 210,386 bloques en ese incremento**. Las adquisiciones parciales
anteriores se conservan como historia. Véase `full_window_recovery/README.md`.

Actualización posterior de oráculos: se verificaron 139,360 precios de 67 activos
en 2,080 bloques contra dRPC, sin discrepancias. Sólo 520 bloques amplían la
cobertura previa: el segundo operador alcanza **5,170 de 215,036 bloques** y
faltan **209,866**. El piloto terminó; el barrido restante se detuvo ante un
HTTP 429 de Nodies. Se conservan las respuestas exactas, el límite y los datos
parciales, sin reintentos automáticos. Pasan 15 pruebas. Las cuatro descargas
de archivos físicos siguen dando HTTP 403. Véase `oracle_recovery/README.md`.

Continuación posterior autorizada: tras respetar `Retry-After`, comenzó un
recolector secuencial más lento para los bloques faltantes. Su primer checkpoint
cerrado agrega **2,000 bloques y 134,000 precios coincidentes**: cobertura
secundaria verificada **7,170 / 215,036**, pendiente **207,866** en ese corte.
El proceso sigue separado del intento fallido; el contador de capturas abiertas
no cuenta como cobertura verificada. Los avisos solicitados de 10/20, 15/20 y
20/20 tienen criterios en `MILESTONES.md`; ninguno se ha alcanzado todavía.

Actualización económica: se autenticaron los 13 archivos económicos antes
faltantes y los 127 recibos decodificados completos. Coinciden las 210
observaciones previas de operadores; los cuatro recibos adicionales aportan
48 transferencias y dos eventos flash. Los 139 eventos de liquidación y el
cálculo histórico de nueve casos WETH se reproducen byte por byte. Pasan 40
pruebas afectadas. Esto resuelve esos faltantes de archivos y logs; los costes
completos y la admisibilidad de ejecución siguen abiertos. Véase
`economic_archives/README.md`.

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
| Evidencia temporal | D15B/D16 reproducidos; universo, transiciones y riesgo inicial también reproducidos | 29,998 candidatos y 134,275 cambios de estado conciliados. Riesgo inicial: 27,850 borrowers con cero discrepancias. Oráculos retenidos: 215,036 bloques; segundo operador verificado en 85,170 y pendiente en 129,866 al cuarto checkpoint de continuación. El 429 previo se conserva y el nuevo proceso sigue con menor ritmo. Siguen faltando independencia de infraestructura, headers completos y recepción histórica real. Eventos ejecutados y 127 recibos completos ya están conciliados; sus límites no se confunden con los oráculos. |
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

## Comparación y ampliación de mercados, 10 de octubre UTC

`STRATEGY_EXPANSION.md` registra la petición de buscar muchas oportunidades
pequeñas en más mercados, sin vender servicios a terceros. El consumidor nuevo
compara las 127 operaciones/139 eventos retenidos: 53 pares, nueve operaciones
con una liquidación del mismo activo, 107 con activos diferentes y once con
varias liquidaciones. Es población histórica de ganadores, no todo el mercado.
Dos omisiones de índices flash en el ledger económico previo se concilian contra
recibos completos y quedan explícitas; no se modifican las fuentes antiguas.

`execution_replay/STRATEGY_TRIALS.md` conserva una comparación controlada:
la financiación Aave del caso examinado no permite devolver principal y comisión
después del mismo pago competitivo, mientras que ejecutar con Balancer antes de
la elegibilidad revierte por la condición exacta del protocolo. Se conservan el
primer intento fallido y su corrección sobre copias nuevas. Pasan los mismos
seis casos de prueba en modo normal y aislado, 67 pruebas Python afectadas y
nueve de aislamiento; permanecen los 637 objetos originales y cero workflows
activos. No cambia el ejecutor original ni hay nuevas peticiones RPC externas.

La prioridad prospectiva de investigación incluye Aave V3 en Base/Arbitrum,
Morpho, rutas con intercambios y compras de colateral de Compound III, cada una
con alcance y evidencias propios. No se ha medido rentabilidad, volumen capturable
ni probabilidad del 80% para esas alternativas. El Census Ethereum declarado,
sus requisitos de cobertura y sus autoridades de cierre permanecen vigentes.
