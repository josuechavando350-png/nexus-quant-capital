# Auditoría offline de sincronización — 22 de octubre de 2026

Resultado: **PASS de software; prueba nativa del cliente pendiente**.
Avance **43/100**, infraestructura **5/6**, sin nuevo crédito operacional.

Se implementaron el ciclo acotado recolector pausado → archivo → preparación
Rust/Polars → cliente PostgreSQL, y un cliente estándar sin dependencias Python
adicionales. El SQL de importación y los preparadores previos no cambiaron.

## Validación completada

- **189 pruebas Python PASS**, 29 nuevas: 15 de protocolo/transporte, diez del
  ciclo completo con Rust/Polars y cuatro del empaquetado de la prueba nativa.
- Los tests de transporte ejecutan un proceso falso explícito para verificar
  argumentos, entorno, salida, timeout, límite de bytes y clasificación de
  resultados. No simulan un servidor para acreditar PostgreSQL.
- El ciclo captura y verifica bytes reales con Rust/Polars, conserva originales,
  aplica locks cooperativos, transmite revocaciones sin hijos, rechaza fuentes o
  recibos avanzados y vuelve a verificar en cada reintento.
- Ausencia de acuse, salida no cero incluso con respuesta, JSON ambiguo, UUID o
  recibo diferente y pérdida del resultado local nunca producen éxito falso.
- Una alteración no cooperativa de la fuente después de confirmar preserva el
  acuse, pero el ciclo pasa a desconocido sin afirmar vigencia de esa fuente.
- El parser pglast 8.7 acepta las 13 sentencias del envío y su unidad PL/pgSQL.
  Esta comprobación no certifica resolución de nombres, tipos ni permisos runtime.
- Los nueve hashes jsonb calculados por el cliente coinciden con los recibos
  conservados de PostgreSQL real en la auditoría anterior. Esa comparación usa
  resultados nativos independientes, no respuestas generadas por el cliente falso.
- Runner determinista, ocho entradas verificadas byte a byte, sintaxis Bash y
  rechazo real de un entorno ajeno antes de crear directorios.

## Hallazgos corregidos durante la revisión

El parámetro `require_auth=peer` no existe en libpq. Se reemplazó por
`require_auth=none` y `requirepeer` con el usuario explícito del servidor. Se
documenta que ausencia de reto no demuestra HBA peer. La prueba nativa conservará
el HBA configurado, mientras el cliente exige socket privado y proceso del UID propio.

`search_path` y timeouts se fijan para toda la sesión, no sólo la transacción,
para cubrir también la lectura posterior a COMMIT. El SQL del paquete nunca se
ejecuta: se genera una sentencia fija con payload hexadecimal.

La lectura del cliente usa pipes con límites, sin almacenar salida ilimitada en
memoria o disco. Los fallos de disco posteriores al envío dejan el intento inicial
en desconocido; el CLI no los describe como rechazo previo a la escritura.

Los tests iniciales intentaron crear un socket Unix y el entorno respondió
`EPERM`. No se eludió esa restricción: las pruebas de protocolo modelan sólo los
metadatos del socket. Una regresión sin ese modelo verifica que un archivo normal
sea rechazado. La prueba nativa pendiente usa sockets y PostgreSQL reales.

## Ensayo nativo preparado

`scripts/nqc-miner-sync-check.sh` contiene los fixtures artificiales previamente
auditados de `e4700af5`, junto al cliente y driver actuales. Prepara 17 comprobaciones
en una instancia Termux nueva, privada y descartable: confirmación, repetición,
extensión, recibo antiguo, revocación, identidad ajena, acuse perdido después de
COMMIT, timeout antes de COMMIT, rollback/reintento, clientes concurrentes,
permisos excesivos e invalidación individual. Conserva también snapshots de
reinicio, configuración, intentos y apagado final.

Los wrappers de fallo llaman al psql real; no reemplazan la base. El ensayo no
ejecuta Rust de Linux en Android ni pone el recolector a funcionar continuamente.
Las [instrucciones](termux-sync.md) piden Python estándar en el teléfono.

## Alcance y pendientes

La evidencia reproducible queda en `evidence/sync-preflight-20261022/`. Los hashes
de fuentes, runner, binario verificador y logs vinculan la revisión. Rust no se
recompiló ni se repitieron sus 155 pruebas históricas; SQL y evidencia auditada
previamente permanecen intactos. ShellCheck no está disponible.

Aislamiento y alcance pasaron: sólo `migration/nqc-miner`,
531 archivos originales conservados y 106 workflows heredados desactivados.
No se modifican datos, servicios o ramas del Observador ni se provisionan recursos.

Faltan ejecución/auditoría nativa de este cliente, servicios remotos, operación
prolongada, observabilidad continua y recuperación conjunta. Ninguna salida de
fase económica se acredita. Detalles de operación y confianza: [postgres-sync.md](postgres-sync.md).
