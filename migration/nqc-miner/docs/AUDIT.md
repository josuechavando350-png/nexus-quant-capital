# Auditoría de NQC Miner — 22 de octubre de 2026

## Resultado y alcance

La implementación de investigación pasó la verificación conjunta sobre el código
identificado abajo. Se cerraron los hallazgos materiales reproducibles de esta
ronda. Esta auditoría verifica comportamiento del software y separación del trabajo;
no acredita operación productiva, cobertura global, autenticidad independiente de
fuentes ni rentabilidad.

**Avance global en este punto: 30/100.** El denominador y sus criterios están en
`progress.json`. La publicación remota y la prueba de integración pública están
pendientes de registrar en la siguiente actualización de evidencia. Ninguna fase
operacional A–D se marca completa.

El alcance procede de `NQC_Miner.pdf` aportado por el usuario. SHA-256 del original:
`b9c1cc9ec4d75ab46fa09fb2b45205caee1539bacdc40fa2eefddf584c996d9c`.
El documento original confidencial no se ha copiado al repositorio público.

## Verificación ejecutada

La ejecución íntegra se conserva en
[`evidence/offline-20261022/summary.json`](../evidence/offline-20261022/summary.json),
con comando, código de salida, log y hash de cada log. El runner confirma que los
archivos de código, pruebas, esquemas e infraestructura no cambiaron durante la
ejecución, y compara la identidad del binario con los bytes fuente.

| Control | Resultado |
|---|---:|
| Compilación Rust con dependencias bloqueadas y sin red | PASS |
| Analítica Rust | 44 PASS |
| Controles de ciclo de vida y presupuesto Rust | 35 PASS |
| Descubrimiento/ABI Rust | 16 PASS |
| Sandbox REVM | 12 PASS |
| Integración de ingesta, journal y reporting Rust | 29 PASS |
| **Total Rust** | **136 PASS; 0 fallos; 0 ignoradas** |
| Genoma con LightGBM/TreeSHAP reales sobre fixtures | 28 PASS |
| Exportación con Polars y verificador Rust reales | 10 PASS |
| **Total Python** | **38 PASS** |
| Clippy `--all-targets -- -D warnings` | PASS |
| Rustfmt | PASS |
| Aislamiento del repositorio y alcance de archivos | PASS |
| Identidad del binario contra los archivos auditados | PASS |

Las pruebas económicas y de cadena son fixtures explícitos. Que una prueba use una
clase `historical` para ejercitar una regla no convierte su transporte en memoria
en una lectura mainnet. LightGBM sí se ejecuta, pero sus datasets de prueba son
artificiales y no se atribuyen resultados predictivos económicos.

Identidad exacta de los fuentes Rust compilados:

```text
source_sha256=b6e41055a80713dbcdfdd0587f758275b179a1e79081ba8840464920e1e140fa
cargo_lock_sha256=6e8c71c5f4a7eaaf61580aa7ea02414276f01f7c5d9631f9ac8e159c30b36872
rust=1.90.0
```

La primera batería se ejecutó antes de publicar el commit; por eso su `about`
conserva honestamente `source_dirty=true` y el HEAD base. Ese binario no puede
ingestar datos públicos por el CLI. La muestra pública exige reconstruir desde el
commit publicado, comprobar `source_dirty=false` y comparar el mismo hash fuente.

## Hallazgos cerrados

| Hallazgo | Corrección y comprobación |
|---|---|
| Duplicación por transacciones distintas en el mismo índice de log | La API analítica valida también `(chain, block, log_index)` y ordena por posición canónica. Regresiones en saturación y cobertura. |
| Scopes de una cadena que completaban sobre historias incompatibles | Registro global de hashes de eventos, extremos, padres y anchors; revalidación antes/después del scope; cuarentena de todos los scopes de esa cadena. Reproducer independiente: segundo scan rechazado y cero scopes contradictorios completos. |
| Lotes provisionales o comprobación final fallida contados como completos | Conciliación de eventos por lote y marcador `ScopeCompleted` separado. Un fallo final mantiene incompleta la cobertura hasta una reanudación válida. |
| Replay de una mina retirada tras una reorganización | Cada transición conserva su contexto canónico histórico vinculado al hash; replay reevalúa gates históricos y comprueba frente a la cadena actual solo la evidencia vigente. Seis regresiones nuevas; reorg vigente continúa rechazándose. |
| Fingerprint rechazaba una cola PUSH incompleta | Conserva y hashea todos los bytes, termina la extracción de selectores y marca la truncación. No certifica semántica ni ejecutabilidad. |
| Publicación parcial de métricas preparadas para ClickHouse | Barrera de publicación por propietario/tip/conteo y conciliación de proyecciones; invalidaciones derivadas del raw verificado. Revisión SQL cruzada; ejecución en servidor pendiente. |
| Payload decodificado inconsistente, clases/scopes ajenos y reanudación ambigua | Re-decoding ABI y comparación con raw; configuración inmutable, proveedor/cadena/scope exactos, deduplicación y rechazo de directorios no propios. |
| ABI mal formado y bytecode que podía provocar panic | Roundtrip ABI estricto y constructor REVM comprobado, con regresiones en las suites de descubrimiento/EVM. |

La revisión fue repartida entre implementación y revisión cruzada. Los
reproductores independientes se ejecutaron antes y después de las correcciones.
Los hashes locales preservan integridad; un productor capaz de reescribir todos
los archivos no queda autenticado por esos hashes.

## Aislamiento comprobado

Todos los archivos de esta entrega están bajo `migration/nqc-miner/` y tienen un
workspace/Cargo.lock propios. La rama de trabajo parte de
`16e352225ba8a6a931834c4edf3d86d9a2924b7d`. `check_scope.py` rechaza cualquier
cambio fuera de ese árbol.

El verificador original del repo confirmó **531 archivos fuente preservados,
106 workflows deshabilitados y cero workflows activos**. La comprobación usa el
manifiesto de importación local; no se verificaron de nuevo objetos Git del repo
de origen y no se renovó su certificación histórica.

No se leyó ni escribió estado operacional del observador. No se habilitó su
puente, no se inició un worker/servicio, no se enviaron notificaciones y no hubo
firma, broadcast ni movimiento de fondos. El presupuesto activo de Miner es cero.

## Infraestructura: comprobado frente a pendiente

PostgreSQL y ClickHouse se revisaron y parsearon estáticamente (14 sentencias por
archivo, con pglast 7.21 y sqlglot 27.29.0). Los tres JSON Schema se validaron con
jsonschema 4.25.1; se contrastaron propietario, manifest y cuatro tipos de registro
de fixtures. Esas herramientas de auditoría son separadas del runtime.

No se ejecutaron las DDL contra servidores. No hay broker Redpanda, worker Temporal,
importador transaccional, servicios de consulta, almacenamiento remoto ni dashboards
desplegados. Nix no está disponible en este entorno y su construcción no se ejecutó.
El pin preparado no se presenta como prueba de una compilación hermética.

## Criterios aún abiertos para el 100%

- Integrar y probar recuperación, concurrencia y permisos de los servicios propios.
- Completar mediciones multichain con precios, gas/propinas, primera elegibilidad y
  calibración; una ventana técnica acotada no cumple ese criterio económico.
- Construir el túnel causal de precios, posiciones y ejecución, y certificar los
  adaptadores completos mediante pruebas diferenciales y fuzzing.
- Ejecutar la ventana prospectiva Shadow y confrontarla con resultados observados.
- Preparar una propuesta concreta y, solo con aprobación explícita, probar la
  ejecución presupuestada mediante un firmante externo.
- Obtener datasets realizados verificables, validar el genoma y cerrar el ciclo de
  aprendizaje, drift y rollback sobre decisiones prospectivas.

El alcance del observador continúa excluido. Esta auditoría no promete ausencia
total de defectos fuera de los comportamientos y límites probados.
