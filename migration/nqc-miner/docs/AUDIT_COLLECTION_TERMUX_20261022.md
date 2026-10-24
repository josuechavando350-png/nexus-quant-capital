# Auditoría PostgreSQL de colecciones — 22 de octubre de 2026

Resultado: **PASS del experimento artificial de colecciones completas**.
Avance global **43/100**, infraestructura **5/6**: se acredita un punto por la
importación atómica y propagación de revocaciones ejecutadas y auditadas.
No se cierra ninguna salida operacional o económica de fase.

## Fuente y evidencia original

El usuario ejecutó PostgreSQL 18.6 en Termux nativo/aarch64. Inicio:
`2026-10-22T22:48:36Z`. Los logs CST corresponden a UTC−6. El agente auditó
offline los archivos retornados sin ejecutar su SQL ni conectarse al teléfono.

| Objeto | Identidad |
|---|---|
| Fuente del runner y migración | `e4700af5bed905e6b071d93cbc17f7489521b342` |
| SHA-256 del runner | `a4257cb34557600579f7d33c50cfa9b9bfca6d7f5f136fc3abc7b39d12f4c0d7` |
| SHA-256 del archivo recibido | `b6c0ab0a4406c751bc1d914a559b26289bbabc35689f7e50c99cd8db91af38b1` |
| SHA-256 del snapshot antes/después | `16d6065a9778eed94b7b22d0d05b73ccfc640bc9ca931cbd8a2375132d3b2140` |

`evidence/termux-collection-20261022/received.tar.gz` conserva los 185,692 bytes
originales. `execution/` conserva sus 45 archivos sin normalizar espacios ni logs.
Los 44 hashes del manifiesto coinciden. Las siete entradas son idénticas a las
incluidas en el runner fijado en Git; también coinciden los hashes de las fuentes
del preparador y del generador de fixtures. Son 11 paquetes de colección y uno
de invalidación individual, previamente verificados con Rust y Polars reales.
Su clase `historical` ejercita la admisión: todos los datos de este experimento
son artificiales, con cero lecturas RPC y cero evidencia económica nueva.

Los hashes vinculan fuentes, bytes y resultados; no atestiguan criptográficamente
el teléfono. La migración genera un UUID nuevo y el instalador de fixtures lo
cambia explícitamente al UUID reproducible de pruebas. No es una base productiva.

## Resultados comprobados

- Las 33 etiquetas SQL coinciden en contenido, cantidad y orden. Las 14 respuestas
  JSON se comprueban completas: padre, estado, inserciones, secuencia y motivo.
- Importación inicial, extensión y repetición conservan los bytes de las ventanas.
  Un recibo antiguo no reduce ni reactiva una colección revocada.
- La revocación del padre excluye todas sus ventanas sin borrar los registros.
  Funciona también antes de importar hijos y cuando faltan archivos hijos.
- Invalidar un hijo mediante el importador individual bloquea toda la colección
  en las vistas; reenviar el padre conserva su cuarentena explícita.
- Un recibo diferente para la misma secuencia provoca cuarentena y conserva el
  recibo y las filas originales. UUID ajeno y transporte alterado se rechazan.
- Un fallo inyectado en el outbox de la segunda ventana revierte también padre
  y primera ventana. El reintento importa el conjunto completo.
- Cuatro mutaciones del escritor limitado y una llamada del rol ajeno fallan
  realmente con `42501`. Base ajena y migración repetida se rechazan.
- Dos importadores quedan bloqueados simultáneamente en el lock de colección;
  uno inserta cuatro registros y el otro devuelve repetición sin duplicarlos.
- Una sesión propia termina después de importar y antes de COMMIT. No quedan
  filas sin confirmar; el reintento inserta las cuatro. El único FATAL es el
  `57P01` esperado y está ligado al PID y sentencia de esa sesión.
- El reinicio ordenado conserva el snapshot byte a byte. El auditor reconstruye
  además cada fila desde los fixtures fijados, incluyendo owner/config, journals,
  outbox, vínculos de ventanas, recibos, snapshots y cuarentenas.
- Los nueve hashes de request se recalculan usando la representación textual
  jsonb de PostgreSQL para estos fixtures enteros, distinta del JSON empaquetado
  del preparador. Las dos vistas deben coincidir con las filas elegibles exactas,
  incluyendo sus timestamps originales.
- Dos ciclos de inicio/apagado completos; apagado final a las 16:48:41 CST.
  Socket privado, sin TCP, autenticación peer y durabilidad activada.

| Tabla o vista | Filas finales |
|---|---:|
| runs | 20 |
| journal_ledger / outbox | 29 / 29 |
| collections / collection_windows | 7 / 13 |
| collection_receipts | 9 |
| import_quarantine / collection_quarantine | 3 / 4 |
| eligible_collection_ledger / eligible_collection_outbox | 12 / 12 |
| import_identity | 1 |
| mine_registry / gate_reports / lifecycle_journal | 0 / 0 / 0 |

Sólo rollback, concurrent e interrupt permanecen elegibles: seis ventanas y doce
registros. Las colecciones normal, child, conflict y revoked-first quedan excluidas.
El estado histórico `verified` de un recibo no sustituye la elegibilidad actual.

## Auditor reproducible y validación

Desde `migration/nqc-miner`, con el historial Git del runner:

```bash
python3 scripts/audit_termux_collection_evidence.py \
  evidence/termux-collection-20261022/received.tar.gz
```

Sólo usa la biblioteca estándar. El lector limita tamaños, miembros y nombres,
rechaza enlaces, duplicados y rutas fuera de la carpeta prevista, y no ejecuta
contenido adjunto. Las **14 regresiones nuevas** alteran datos y recalculan el
manifiesto para probar que el auditor detecta fallos semánticos: fuentes, resultados,
permisos, concurrencia, rollback, recibos, revocaciones, elegibilidad, controles,
configuración y apagado. Alterar ambos snapshots de forma idéntica también falla.

La suite completa pasa **160 pruebas Python**, usando el verificador Rust y Polars
reales cuando corresponde. Rust, Cargo.lock, SQL y runner no cambiaron en este
bloque; no se repiten sus 155 pruebas Rust históricas ni se reclama otra ejecución
PostgreSQL. ShellCheck sigue sin estar disponible. Aislamiento y alcance pasan:
531 archivos originales intactos, 106 workflows heredados desactivados, cero
workflows activos y cero cambios fuera de `migration/nqc-miner`.

## Límites abiertos

El contrato requiere escritores cooperantes y consultas a las vistas de elegibilidad.
Los permisos administrativos y la escritura directa en tablas son una frontera de
confianza. Capturar/enviar revocaciones sigue siendo explícito; no hay vigilancia
de fondo. Interrumpir un backend y reiniciar ordenadamente no prueba pérdida eléctrica.

Faltan la conexión operacional del recolector, transporte y almacenamiento remotos,
broker, workers de workflow, observabilidad, operación prolongada y recuperación
conjunta. No hay relay, firma, gasto ni activación productiva. Los archivos, datos,
servicios y ramas del Observador permanecen fuera de este trabajo. La preparación
histórica anterior y las auditorías previas se conservan sin reescribir sus resultados.
