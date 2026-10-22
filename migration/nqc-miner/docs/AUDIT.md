# Auditoría de NQC Miner — 22 de octubre de 2026

## Resultado y alcance

La implementación de investigación pasó la verificación conjunta sobre el código
identificado abajo. Se cerraron los hallazgos materiales reproducibles de esta
ronda. Esta auditoría verifica comportamiento del software y separación del trabajo;
no acredita operación productiva, cobertura global, autenticidad independiente de
fuentes ni rentabilidad.

**Avance global en este punto: 35/100.** El denominador y sus criterios están en
`progress.json`. La rama de código ya está publicada. La integración pública detectó un fallo TLS
que se corrigió y cuya repetición se registrará con identidad nueva. Ninguna fase
operacional A–D se marca completa.

El alcance procede de `NQC_Miner.pdf` aportado por el usuario. SHA-256 del original:
`b9c1cc9ec4d75ab46fa09fb2b45205caee1539bacdc40fa2eefddf584c996d9c`.
El documento original confidencial no se ha copiado al repositorio público.

## Verificación ejecutada

La ejecución íntegra se conserva en
[`evidence/offline-native-ca-20261022/summary.json`](../evidence/offline-native-ca-20261022/summary.json),
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
source_sha256=6ac0ba660374a50c66af8a3e6fc08b304967c19bc927642e6e827c775aeeee4f
cargo_lock_sha256=c840affc2bcf9f55429d92e20a5d46dc309d9fc606b738669ab2a709b087c80a
rust=1.90.0
```

Las baterías se ejecutaron antes de publicar sus respectivos commits, por lo que
sus `about` conservan honestamente `source_dirty=true` y el HEAD de partida. La
primera ejecución se preserva en `evidence/offline-20261022/`; la segunda, con
raíces TLS nativas, vuelve a pasar los mismos 136 + 38 tests. No se suman las
repeticiones como pruebas distintas. El CLI no admite escanear con esos binarios
sin commit: exige reconstruir el commit publicado, `source_dirty=false` y el hash
fuente esperado.

### Hallazgo de integración TLS

El primer intento con commit `15976fece06d1727fbe327b74d7808634f4719a5` se detuvo
con `UnknownIssuer`: las raíces WebPKI compiladas no incluían la autoridad de
certificados seleccionada por este entorno. Se conserva el intento completo en
`evidence/public-20261022/`, con salida de error y journal verificado de **cero
registros y cero scopes completos**. No se borró ni reinterpretó ese intento.

La corrección cambia únicamente el feature de reqwest a
`rustls-tls-native-roots`, conserva Rustls/ring y las verificaciones de certificado
y hostname, y fija las dependencias adicionales en Cargo.lock. No añade un
verificador permisivo, no acepta certificados inválidos ni modifica el almacén CA.
La revisión independiente leyó el constructor de Miner y el código fijado de las
dependencias. Las versiones fijadas de `rustls` y `rustls-webpki` permanecen en
0.23.46 y 0.103.16; la corrección es de integración del almacén de confianza.

La nueva muestra necesita configuración y directorio propios, ligados al commit y
lock corregidos. Hasta que termine no se registra una lectura pública completa.

### Delta de endurecimiento HTTP pendiente de reejecución completa

Después de la última suite completa se publicó un delta adicional. El cambio de
red introducido en `20a22c58b7bc64c6cda6d9610133b876452de0fe` serializa el
ritmo por proveedor, limita los reintentos, trata 408/425/429/500/502/503/504 como
transitorios y no incorpora endpoint, query string ni cuerpo remoto en el error.
Se añadieron regresiones locales para 429 seguido de éxito y para 401 sin reintento
ni fuga del token incluido deliberadamente en el URL de fixture.

Una revisión posterior de RustSec encontró que el pin `rand 0.8.5` caía en el
rango afectado de RUSTSEC-2026-0097; se elevó a `0.8.6` y se actualizó el lock.
El SHA-256 del Cargo.lock preparado es
`634f6b4361a2b29a6eeb55338422f5dbb0902fefa231433bfd385b6240a0daab`.
La configuración de repetición ya no guarda un SHA de commit autorefencial:
`config.template.json` es intencionalmente no ejecutable. El schema v2 contiene
placeholders para commit, Cargo.lock y `build_identity_sha256`;
`scripts/bind_run_config.py` los liga al `about` de un binario limpio justo
antes de correr. El binder recalcula además la identidad canónica a partir de
commit, fuentes, lock, rustc, target, host, perfil, optimización, debug y RUSTFLAGS,
por lo que un `about` internamente inconsistente se rechaza.

La repetición multichain está preparada en
`evidence/public-retry-20261022/` con `run_id` nuevo y lotes de 100 bloques.
**No se presenta como ejecutada.** Los 136 + 38 tests del commit anterior no se
heredan a estos cambios; tampoco se suman las nuevas pruebas del binder mientras no
se ejecuten. El avance permanece en 35/100 hasta reconstruir la revisión actual y
repetir compilación, tests, Clippy, formato, aislamiento, auditoría de dependencias,
identidad del binario y la muestra pública.

### Cross-check independiente del tramo Ethereum

Como control separado del transporte RPC de Miner, un indexador Blockscout confirmó
los hashes de los bloques extremos de la ventana Ethereum y **tres transacciones
únicas exitosas** dentro de esa ventana que contienen la llamada
`liquidationCall` al Pool de Aave V3. Las transacciones muestran además quemas de
deuda Aave y movimientos de colateral compatibles con liquidación; en los tres
casos aparecen transferencias desde Morpho Blue dentro de la ruta.

Este control se conserva en
`evidence/public-crosscheck-20261022/aave-ethereum.json`. No se usa para inflar el
conteo del Miner: evidencia transaccional no equivale a contar logs
`LiquidationCall`. Durante una ejecución temporal se observó un conteo de cinco
eventos, pero **no existe en la rama un journal durable/versionado de esa corrida**;
ese número queda excluido de métricas y afirmaciones hasta repetirlo y verificarlo.
Tampoco se atribuye identidad real a las direcciones observadas ni se certifica
rentabilidad, cobertura o saturación. El criterio de admisión está centralizado en
`docs/EVIDENCE_LEDGER.md`.

### Contrato de identidad completa del build

La auditoría detectó dos huecos sucesivos. Primero, el hash fuente embebido por
`build.rs` no incluía `rust-toolchain.toml`. Segundo, `scan` y `owner.json`
solo quedaban ligados a commit + Cargo.lock: un binario construido con otro target,
perfil o RUSTFLAGS podía compartir esa identidad.

El contrato actual corrige ambos puntos. `source_sha256` incluye el toolchain y
`about` declara rustc, target, host, perfil, optimización, debug y hash de
RUSTFLAGS. `build.rs` deriva un `build_identity_sha256` canónico de esos campos;
el binder lo recalcula y las nuevas configuraciones schema v2 lo almacenan.
`scan` exige que ese build-id coincida exactamente y los nuevos journals usan
`nqc-miner-owner-v2`. El parser conserva v1 solo para verificación histórica y
`validate_runtime` impide usarlo en una lectura RPC nueva.

Las pruebas Python aisladas del contrato actual pasaron **11/11** y el JSON Schema
de owners pasó 4/4 casos de compatibilidad/rechazo. La evidencia exacta se conserva
en `evidence/reproducibility-python-v2-20261022.json`. Las tres regresiones Rust
v1/v2 están escritas pero **aún no se han compilado ni ejecutado**, por lo que este
hallazgo no se acredita como cierre del gate integral.

### Revisión dirigida de dependencias

Se cruzó el lock con el inventario público de RustSec y se revisaron todos los
avisos de **2026** identificados para paquetes presentes en el lock. El único pin
detectado dentro de un rango afectado fue `rand 0.8.5`, que se corrigió a
`0.8.6`. Tras esa remediación, las versiones revisadas de bytes, keccak, rand,
ruint, time, tokio, rustls, rustls-webpki y quinn-proto quedan en rangos parchados
para sus advisories 2026 identificados.

El detalle está en `evidence/supply-chain-review-20261022.json`. Sigue siendo una
revisión dirigida: **no sustituye** un `cargo audit`/`cargo deny` completo sobre
todo el historial de la base RustSec y el grafo resuelto. El escaneo automático,
la compilación con el lock nuevo y toda la suite permanecen como requisitos antes
de acreditar el delta o fusionar la PR.

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
