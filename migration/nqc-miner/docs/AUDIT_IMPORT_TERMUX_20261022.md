# Auditoría del importador PostgreSQL — 22 de octubre de 2026

Resultado: **PASS del experimento sintético de journal individual**. Avance
global **42/100**; infraestructura **4/6**. Se acredita un punto por ejecutar y
auditar el importador, distinto del contrato DDL base previamente probado.
Ninguna salida operacional o económica de fase queda cerrada.

## Identidades y evidencia

El usuario ejecutó el runner en Termux nativo, PostgreSQL 18.6 y aarch64. Inicio:
`2026-10-22T22:12:16Z`; los logs locales usan CST, seis horas detrás de UTC.
El agente revisó los archivos offline; no ejecutó otro servidor ni accedió al
teléfono. La captura mostraba el inicio; el archivo retornado contiene el cierre.

| Objeto | Identidad |
|---|---|
| Implementación del importador | `a1d0f150633fda2e5142fe59c0beda924c7bd830` |
| Runner publicado | `7ee9e9cba98c876c72082580ae2e514867917e6f` |
| SHA-256 del runner | `8a73eb9860a82193353df4b23f5d0abc08524e4430f42d7a541c9def4a8793c5` |
| SHA-256 del archivo recibido | `2ece1450711a6119ec47548f55c6f8f0e164671e6a36f1bf0db8c9366fb7819f` |
| SHA-256 del snapshot, antes y después | `29887b56402aa80a8f1edf8757e74ff8a815c91331d72bd7557ffb97dcf93cf2` |

Se conserva el archivo original de 86,647 bytes en
`evidence/termux-import-20261022/received.tar.gz`, junto a sus 43 archivos exactos
en `execution/`. Los 42 hashes del manifiesto son correctos. Las seis entradas
coinciden byte a byte con las incluidas en el runner publicado, incluido el reporte
de 16 fixtures sintéticos previamente verificados por Rust. No se ejecutó SQL
adjunto durante la auditoría. Los hashes prueban consistencia y vinculación con
la fuente; no constituyen una atestación criptográfica del teléfono.

La migración generó un UUID nuevo; después, el instalador de fixtures lo cambió
intencionalmente a `dfb1a49f-38d1-40ab-b19d-90a9577271be`. Es una identidad de
prueba reproducible, sin relación con una base productiva.

## Comprobaciones cerradas

- Las 35 etiquetas SQL aparecen exactamente una vez y en el orden previsto.
  También se verifican las 21 respuestas JSON del importador: run, estado,
  cantidad insertada, hash, cantidad persistida y motivo de cuarentena.
- Prefijo inicial, repetición, extensión y prefijo antiguo conservan bytes y no
  duplican filas. El journal vacío crea su run sin inventar registros.
- UUID ajeno, hash corrupto y aislamiento de transacción incompatible se rechazan.
  La instalación en una base ajena da `P0001`; una instalación repetida, `42P07`.
- Cuatro intentos de modificar datos con el escritor limitado y una ejecución
  con el rol ajeno fallan realmente con `42501`.
- Dos clientes quedan bloqueados simultáneamente en el lock del mismo run. Al
  liberarse, uno inserta tres registros y el otro devuelve repetición con cero
  inserciones; ambos tienen el mismo hash y tres filas persistidas.
- Un trigger de prueba provoca un fallo de outbox y revierte run, ledger y outbox.
  Tras quitarlo, el reintento inserta las tres filas.
- Una sesión propia se interrumpe después de insertar y antes del COMMIT. El
  runner comprueba ausencia de filas comprometidas; el reintento inserta tres.
  El único FATAL es el `57P01` previsto de ese backend, vinculado a su sentencia
  de prueba. No fue una caída del servidor ni una prueba de pérdida eléctrica.
- Los snapshots son idénticos byte a byte tras un reinicio ordenado. El auditor
  además reconstruye todas las filas esperadas desde los fixtures fijados,
  comprobando owner/config originales, metadatos y bytes de ledger/outbox.
- Ambos ciclos de inicio/apagado están registrados. El primer servidor escribe
  en `server.log`; el reiniciado escribe en `startup.log`. El apagado final
  termina a las 16:12:21 CST. No hay listener TCP; socket privado, peer, fsync
  y synchronous_commit activados.

| Tabla | Filas finales | Resultado esperado |
|---|---:|---|
| runs | 11 | Sólo runs sintéticos previstos; sin el caso UUID rechazado |
| journal_ledger | 30 | Bytes originales; falta deliberadamente la secuencia del caso de hueco |
| outbox | 29 | Una ausencia adicional y un payload alterado son inyecciones documentadas |
| import_quarantine | 6 | Conflicto de journal, owner, invalidación, hueco y dos fallos de outbox |
| import_identity | 1 | UUID sintético del experimento |
| mine_registry, gate_reports, lifecycle_journal | 0 | Sin actividad operacional |

Las alteraciones deliberadas pertenecen exclusivamente a los fixtures descartables.
La cuarentena se conserva, incluyendo la invalidación tardía; un prefijo antiguo
no reactiva esos runs. No se atribuyen estas anomalías a datos de mercado.

## Reproducción y validación del auditor

Desde `migration/nqc-miner`, con el historial Git que contiene el runner fijado:

```bash
python3 scripts/audit_termux_import_evidence.py \
  evidence/termux-import-20261022/received.tar.gz
```

El auditor usa sólo la biblioteca estándar. Lee el tar con límites de tamaño y
nombres, sin extraer rutas arbitrarias. Rechaza enlaces, duplicados, traversal,
archivos faltantes, manifiestos incompletos y JSON ambiguo.

La suite completa pasa **128 pruebas Python**. Las 12 nuevas regresiones cubren
manifiestos y archivos alterados, fuentes ajenas, resultados SQL falsos,
denegaciones incorrectas, concurrencia aparente, rollback/reintento incorrecto,
snapshots igualmente alterados, activación de controles, TCP/autenticación,
durabilidad y apagado incompleto. Los ocho tests del auditor base también pasan
tras permitir reutilizar su lector de archivos con otra lista de miembros.

El código Rust y su lock no cambiaron: sus 155 pruebas históricas no se volvieron
a ejecutar. Las pruebas Python que requieren Rust sí usan el binario verificador
real de la fuente `169b82f`. No se ejecutó ShellCheck; no está disponible.
La verificación de aislamiento conserva los originales y workflows desactivados;
el control de alcance no encuentra cambios fuera de `migration/nqc-miner`.

## Límites y trabajo pendiente

Este bloque valida un journal individual con fixtures sintéticos, cero nuevas
observaciones RPC y ningún resultado económico. Los roles y permisos probados
pertenecen a una instancia temporal que quedó apagada. El contrato supone
escritores cooperantes: SQL no sustituye el verificador Rust ni certifica una
fuente de mercado.

Faltan propagación de revocaciones del controlador padre a todas sus ventanas,
conexión del recolector completo, integración remota de almacenamiento/base/broker/
workflow, observabilidad, operación prolongada y recuperación conjunta. No hay
relay ni entrega externa activada. Observador, firma, Telegram, KMS y gasto
permanecen desactivados. No se tocó ninguna rama, archivo o servicio del Observador.
