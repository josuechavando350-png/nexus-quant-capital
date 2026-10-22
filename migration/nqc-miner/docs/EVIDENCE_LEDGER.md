# NQC Miner — Ledger de evidencia

Corte: 22 de octubre de 2026.

Bloque actual: colecciones completas ejecutadas en PostgreSQL 18.6/Termux y
auditadas contra la fuente `e4700af5`. 44 hashes, siete entradas, 33 comprobaciones
SQL, 14 respuestas, cinco denegaciones, concurrencia, rollback, interrupción/reintento,
revocaciones, elegibilidad y reinicio. **160 Python PASS; avance 43/100**.
Véase `docs/AUDIT_COLLECTION_TERMUX_20261022.md` y `evidence/termux-collection-20261022/`.
La preparación anterior (146 Python, tres ventanas históricas/ocho registros y 46
archivos intactos) queda preservada; su gate SQL pendiente se cierra para esta
prueba artificial, sin acreditar producción ni observaciones económicas nuevas.

Bloque anterior: importador de journal individual ejecutado por el usuario en
PostgreSQL 18.6/Termux y auditado desde el archivo original. Runner `7ee9e9cb`,
implementación `a1d0f150`: 42 hashes, seis entradas fijadas, 35 comprobaciones SQL,
21 respuestas, cinco denegaciones de permisos, concurrencia real, interrupción y
reintento, cuarentena y reinicio. Suite completa: **128 Python PASS**. Avance
**42/100**. Véase `docs/AUDIT_IMPORT_TERMUX_20261022.md`.

Etapas previas conservadas: preparación del importador (112 Python), runner
(116 Python) y contrato DDL base `6a89668` (30 comprobaciones SQL y tres
rechazos de permisos). Sus estados pendientes y avance 41/100 son históricos;
la auditoría individual sustituyó únicamente su gate runtime. La auditoría de
colecciones indicada arriba es posterior. Ninguna acredita servicios remotos ni
operación productiva.

Último bloque de archivo: `169b82f`, 155 Rust + 91 Python PASS.
`offline-archive-v2-20261022/` y `local-archive-v2-20261022/` acreditan
publicación/repetición verificadas con UUID ligado a cada recibo. Se conservan
17 archivos de origen y ocho registros de la muestra anterior; no son nuevos
eventos. Avance 40/100. El baseline v1 de `005ab8c` queda histórico y no satisface
el gate final v2. Véase `docs/AUDIT_ARCHIVE_20261022.md`.

Bloque anterior del recolector: `a1f6006`, 155 Rust + 69 Python PASS en
`offline-collector-20261022/`. `public-collector-20261022/` acredita tres ventanas
Ethereum y reinicio entre procesos: 2 eventos, 8 registros; sus Parquet conservan
los bytes originales. Se solapa con las capturas anteriores y no se suma.
Avance 39/100; alcance y límites en `docs/AUDIT_COLLECTOR_20261022.md`.

Actualización de la continuación: `offline-v2-isolation-20261022/` acredita
141 Rust + 64 Python y los gates de software sobre `a841261`.
`dependencies-full-20261022/` contiene el scan completo del lock (0 vulnerabilidades
conocidas, 2 avisos de mantenimiento abiertos).
`public-capture-v2-20261022/` conserva una lectura pública nueva, íntegra y completa
en cuatro ámbitos de tres cadenas: 3 logs canónicos y 17 registros totales.
`public-parquet-v2-20261022/` conserva su exportación local verificada. La captura
v1 previa también se preserva; ambas repiten la misma selección y no se suman.
Estas nuevas evidencias no recuperan ni certifican la observación transitoria de
cinco eventos descrita abajo, ni cierran saturación, rentabilidad o una fase.

Este ledger separa evidencia durable, evidencia auxiliar, planes no ejecutados y
observaciones transitorias. Ningún elemento cambia de clase por aparecer en una
conversación, log parcial o reporte humano.

| Evidencia | Clase | Estado | Qué demuestra | Qué NO demuestra |
|---|---|---|---|---|
| `evidence/offline-20261022/` | durable / software | PASS histórico | Primera batería offline del Miner | Estado del delta actual |
| `evidence/offline-native-ca-20261022/` | durable / software | PASS histórico | 136 Rust + 38 Python, Clippy, formato e aislamiento después del ajuste TLS | Que los cambios HTTP, rand y binder posteriores compilen o pasen la suite |
| `evidence/public-20261022/` | durable / integración fallida | FAIL preservado | El intento original se detuvo; journal con 0 registros y 0 scopes completos | Actividad mainnet o cobertura |
| `evidence/public-crosscheck-20261022/aave-ethereum.json` | auxiliar / fuente independiente | CORROBORADO | 3 transacciones únicas exitosas con `liquidationCall` en la ventana Ethereum y hashes extremos de la ventana | Conteo exacto de logs del Miner, rentabilidad, cobertura o saturación |
| `evidence/public-retry-20261022/config.template.json` | plan | NO EJECUTADO | Alcance y ventanas de la repetición propuesta, con identidad ligada en runtime | Lectura RPC, eventos o resultados |
| `evidence/binder-python-20261022.json` | durable / módulo aislado | PASS 6/6 | El binder rechaza identidades sucias/operativas y sobrescrituras | Suite Python completa, Rust o RPC |
| `evidence/supply-chain-review-20261022.json` | revisión dirigida | PASS PARCIAL | Ranges 2026 revisados; rand 0.8.5 remediado a 0.8.6 | `cargo audit`/grafo completo o compilación del lock nuevo |
| `evidence/build-identity-python-20261022.json` | durable / módulo aislado | PASS 2/2 | El toolchain pin cambia el hash fuente y build.rs lo rastrea | Que el build.rs modificado compile o que el build sea reproducible entre plataformas |
| `evidence/public-crosscheck-20261022/aave-ethereum-partial-saturation.json` | auxiliar / medición parcial | INSUFICIENTE | 3 tx exitosas, 2 direcciones liquidadoras observadas y span de bloques | Saturación, latencia, tips, cobertura o rentabilidad |
| `evidence/reproducibility-python-v2-20261022.json` | durable / contrato aislado | PASS 11/11 + schema 4/4 | Binder y verificador recalculan la identidad completa; owners v1/v2 quedan separados | Que el Rust v2 compile, que sus regresiones pasen o que exista reproducibilidad bit-a-bit |

## Observaciones no admisibles como evidencia durable

Durante una ejecución temporal se observó un conteo de cinco eventos en Ethereum.
No existe en esta rama un journal durable/versionado de esa ejecución. Por tanto,
**ese conteo se excluye de métricas, cobertura, calibración, progreso y cualquier
afirmación de resultado**. Solo podrá recuperarse si se repite con el pipeline
actual y queda verificado por `verify-journal`.

## Regla de admisión

Una afirmación operacional necesita, como mínimo:

1. archivo versionado o artefacto durable con propietario/run_id;
2. identidad completa del build: commit, fuentes, Cargo.lock, toolchain,
   compilador/target/perfil y RUSTFLAGS, ligada por `build_identity_sha256`;
3. integridad verificada;
4. alcance explícito de cadena/contrato/bloques;
5. estado completo, no provisional;
6. clase de datos explícita;
7. ninguna contradicción por reorg o proveedor;
8. para economía, precios/costes/eligibilidad y resultado observables.

La evidencia auxiliar puede corroborar hechos puntuales, pero nunca cerrar por sí
sola una salida de fase.
