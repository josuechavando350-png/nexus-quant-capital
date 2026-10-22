# Auditoría del recolector histórico — 22 de octubre de 2026

Avance global **39/100**, frente a 38/100 al iniciar este bloque. Se acredita
**1 de los 6 puntos** de infraestructura por el recolector ejecutable, recuperación
comprobada y captura finita con reinicio. Permanecen pendientes los otros 5 puntos
por servicios de almacenamiento, broker, workflows, observabilidad y recuperación
integrados. No se cierra ninguna salida operativa A–D.

## Identidad y alcance

El código auditado y ejecutado es el commit publicado
`a1f600697e0f9de776956472033bcb9146d646e7`, árbol
`235c0eb1e4bef761edbdeb4fa1db09c4cea23b1e`.

| Identidad | SHA-256 |
|---|---|
| Fuentes Rust y entradas de build | `3b7ad83406f8dcea6537be014e607e07d5413d5b40e87efa5d20cf0b93e62a39` |
| Cargo.lock | `634f6b4361a2b29a6eeb55338422f5dbb0902fefa231433bfd385b6240a0daab` |
| Build | `bd07ac7ea9f6443cf03ea4c941d10e2c23b6775e80fe594654eb8bfb93de8fc3` |
| Binario de la captura | `f72c75c46eb24ada3680ef68f60f75883fbf68299274011f187ccac102612c65` |

Rust 1.90.0, debug, x86_64-unknown-linux-gnu, fuentes limpias. La evidencia
posterior conserva este commit, sin relabelarla al commit documental de entrega.
Para reproducir este build se debe checkout este commit publicado exacto.
No se agregaron dependencias; Cargo.lock conserva el hash ya auditado. Los dos
avisos de mantenimiento de derivative/paste siguen abiertos; no se afirma una
nueva consulta de advisories por repetir el mismo lock.

Todos los cambios están en `migration/nqc-miner/`. El observador, sus ramas,
credenciales, datos, procesos y configuración quedaron fuera de estas acciones.
La verificación confirma 531 archivos originales preservados, 106 workflows
heredados desactivados y 0 activos. No se habilitaron firma, puente ni presupuesto.

## Cambios y revisión

- `follow` genera ventanas históricas contiguas con identidad propia, espera a la
  finalización y solo avanza tras cerrar/verificar la ventana completa.
- Reanuda chunks persistidos. Un error de proveedor conserva el cursor. Los demás
  errores detienen la operación; la continuidad rota pone en cuarentena toda la
  colección mediante una invalidación durable en su journal de control.
- `verify-collector` verifica offline todas las ventanas, propietarios, índices,
  hashes y enlaces, y rechaza una colección en cuarentena.
- Locks de kernel con inode persistente liberan la exclusión al morir el proceso.
  Los locks antiguos o incompletos se rechazan; no se borran automáticamente.
- `smoke_collector.py` conserva una ejecución de dos ventanas, el reinicio, la
  tercera ventana y las verificaciones; compara los bytes previos y del binario.

La revisión cubrió separación de run/chain/class/build, overflow y límite de
ventanas, espera sin avance, rollback por fallo RPC, reorg y frontera entre
ventanas, doble escritor, symlinks, evidencia incompleta/truncada y formato de
locks heredados. No se introdujeron nuevos métodos RPC ni una transición hacia
operación económica. Véanse las restricciones en `docs/collector.md`.

## Pruebas retenidas

`evidence/offline-collector-20261022/summary.json`: **PASS** de los ocho gates,
entradas auditadas sin cambios:

- 155 pruebas Rust, 0 fallidas, 0 ignoradas. El contador incluye el helper de
  subprocess; hay 13 escenarios nuevos de recolector y su helper de SIGKILL.
- 69 pruebas Python, 0 fallidas. Cinco escenarios nuevos verifican que el
  capturador no confunda esperas, datos incompletos o identidad modificada con éxito.
- Build, Clippy con `-D warnings`, rustfmt, identidad de fuentes/build y las dos
  verificaciones de aislamiento aprobadas.

La prueba de SIGKILL mata un subprocess con locks de raíz e hijo abiertos,
reabre los datos y completa la ventana siguiente. La prueba de registro truncado
confirma rechazo y preservación, no reparación automática. Los transports de
estas pruebas son fixtures sintéticos y no cuentan como evidencia de mercado.

## Captura pública finita y exportación

`evidence/public-collector-20261022/capture.json`: **complete_bounded_restart_smoke**.
Mismo binario antes/después; las primeras dos ventanas permanecieron byte a byte
intactas tras el reinicio. No quedó un proceso continuo ejecutando.

| Ventana | Bloques Ethereum inclusivos | Eventos | Registros |
|---|---|---:|---:|
| 0 | 26248000–26248099 | 1 | 3 |
| 1 | 26248100–26248199 | 1 | 3 |
| 2 | 26248200–26248299 | 0 | 2 |

Aave V3, un contrato y un topic explícitos; acuerdo de publicnode y Flashbots.
Tres scopes de ventana cerrados, dos eventos canónicos, ocho registros.
Siguiente cursor: 26248300. Hash de colección:
`3c3bdca124b51416049a505b632aa8bc311b220755814e95a5ee22179de38ad7`.
Los proveedores distintos no prueban independencia de origen ni autenticación
criptográfica de la cadena.

Los ocho registros se exportaron con Polars y el verificador Rust a tres exports
en `evidence/public-collector-parquet-20261022/`. Se comprobó otra vez el estado
completo de colección después de exportar, hashes y recuperación exacta de las
líneas originales. El resultado es un snapshot histórico; una invalidación futura
debe propagarse a los consumidores. No existe aún un relay/consumidor operativo.

Estas ventanas se solapan con las capturas v1/v2 anteriores, elegidas para pruebas
de integración. **No sumar sus eventos ni tratarlas como muestras independientes**.
No hay medición nueva de rentabilidad, saturación calibrada o vigilancia Shadow.

## Pendiente

Operación prolongada supervisada y almacenamiento con retención; integraciones
reales de Postgres/ClickHouse/Redpanda/Temporal/object store; autorización de
recursos operativos; Nix y reproducción hermética; calibración económica,
Shadow prospectivo, adaptadores certificados y las posteriores etapas del PDF.
La prueba local no certifica NFS, pérdida de disco ni un administrador hostil.
