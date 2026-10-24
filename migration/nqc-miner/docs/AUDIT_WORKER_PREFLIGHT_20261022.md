# Auditoría del coordinador acotado — 22 octubre 2026

**Software offline PASS. Avance global conservado: 43/100.**

Cambios: `research/collector_worker.py` coordina la recuperación desde fuente
verificada, un poll Rust acotado y la sincronización local. Se integra con el
archivo y el cliente existentes sin modificar su formato, las migraciones SQL,
la ingesta Rust ni la evidencia histórica. Un workspace nuevo vincula plan,
binario, destino y ambos UUIDs. El mismo workspace exige la misma identidad.

La auditoría nativa del cliente se cerró por separado con el adjunto original;
ver `AUDIT_SYNC_TERMUX_20261022.md`. El nuevo auditor comparte exclusivamente la
reconstrucción de snapshots con el auditor anterior, cuyo comportamiento por
defecto permanece igual y conserva sus regresiones.

## Verificación

- **217 pruebas Python PASS**, 158.014 segundos, sin fallos ni skips. Incluye
  12 regresiones nuevas del auditor y 16 del coordinador. Log retenido en
  `evidence/worker-preflight-20261022/python-tests.log`.
- Tras reforzar la correlación PID/sentencia/acuse de terminación del auditor,
  se repitieron sus **12 pruebas: PASS** (9.801 segundos). El resto del código
  probado no cambió; log `auditor-final-tests.log`.
- Rust/Polars reales verifican, archivan y preparan los fixtures del coordinador.
  Se modelan explícitamente el poll RPC y PostgreSQL; el falso cliente sí es un
  proceso real. No se atribuye a ese doble una ejecución de SQL.
- SIGKILL real de un proceso con lock adquirido conserva la intención incompleta,
  libera el lock y obliga al siguiente worker a revalidar/sincronizar antes de
  leer otra ventana. Hay pruebas de escritores simultáneos, acuse desconocido,
  revocación después de un poll fallido, configuración ajena y capacidad de 64.
- Timeout/salida excesiva se prueban con procesos reales. No se conserva stderr
  sin filtrar. La revisión detectó y corrigió el rechazo de binarios Cargo con
  hard links: el hash del ejecutable se calcula por streaming con comprobación
  de inode/tamaño/tiempos antes/después. Los datos mutables siguen rechazando links.
- Aislamiento: 531 archivos originales, 106 workflows desactivados, 0 activos.
  El scope comprueba exclusivamente `migration/nqc-miner/`; no cambia Observer.
- Rust, Cargo.lock, migraciones, preparadores, transport y runner nativo no cambian.
  Sus pruebas Rust históricas no se repitieron ni se presentan como nuevas.

## Hallazgos y límites abiertos

La ejecución conjunta de este worker con RPC y PostgreSQL reales está pendiente.
No hay servicio persistente desplegado, infraestructura remota, carga prolongada,
reconstrucción económica, firmante o gasto. No se probó un corte físico de disco,
una ruptura durante un fsync ni actores hostiles con el mismo UID. Un SIGKILL del
supervisor puede dejar temporalmente un hijo con su lock; no se mata a terceros.

Un ciclo confirmado no implica nuevos eventos ni lucro. Un resultado incierto
puede coexistir con un COMMIT confirmado del último sync si el poll falló: el
resultado los separa. No se afirma exactly-once operacional de punta a punta.

`docs/closure-plan.json` conserva exactamente los 57 puntos restantes y sus
criterios originales. Completar este bloque no autoriza ni demuestra las salidas
operativas/económicas; todas permanecen abiertas. Falta desarrollo de varias
integraciones, además de infraestructura, datos y tiempo prospectivo reales.
