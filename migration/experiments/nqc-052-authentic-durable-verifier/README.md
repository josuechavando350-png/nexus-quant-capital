# NQC052 — verificador completo y recuperación remota integrada

19 de octubre de 2026. Base: `a6e4600962dca78ddb4e02cc12c920a3df96d169`.
Rama: `research/nqc-052-authentic-durable-verifier-20261019`.

Esta entrega resuelve el checkout, la ejecución completa de NQC037 y su
integración **DRY_RUN** con NQC047–048 sobre GitHub real. La adquisición Triport
sigue bloqueada. **0/8 consultas Triport utilizadas; `commercial_admission=false`.**

## Evidencia nueva

- Se inspeccionaron las ramas remotas antes de editar: NQC051 seguía siendo el
  avance más reciente. Se clonó el repositorio completo; `git fsck --full
  --no-reflogs` terminó correctamente. Los **1,362 archivos** del commit base
  coinciden con sus blobs Git. Los **42 archivos** del manifiesto NQC037
  coinciden con tamaño y SHA-256; también se fijó el blob del propio manifiesto.
- Python 3.12.14 ejecutó **32/32 pruebas originales de NQC037** con las 15
  dependencias exactas de su `requirements.txt`, instaladas en un entorno
  separado. No se necesitó overlay NQC050 ni modificación de fuentes.
  Se cargaron completos `intake`, `verify`, `storage_proof` y `util` originales.
- NQC049 ejecutado sobre el checkout completo rechazó la respuesta ficticia
  de NQC048: `BLOCKED_NQC037_VALIDATION`, exit 2, resultado esperado. Se
  reconstruyeron sus 700,063 bytes y tres fragmentos; no se aceptó
  `SIM_ACCEPTED_1` como chain ID.
- **21 pruebas nuevas** (12 Python y 9 Node) pasan; **9/9 de aislamiento** pasan.
  Las suites históricas se cuentan una sola vez. No se repitieron NQC050–051
  ni pruebas Rust: no cambió ningún código Rust.

`worker.py` comprueba manifiesto, blobs, plan, dependencias y origen de los
módulos. Reconstruye el estado desde la primera respuesta en cada proceso;
rechaza estado proporcionado por el llamador y no acepta un validador suplente.
La salida enlaza el SHA-256 exacto de stdin. No contiene transporte ni gestión
de credenciales. Bloquea sockets durante toda la ejecución y procesos hijos
durante la validación. La carga nativa de PyCryptodome necesita ejecutar `file`
para detectar arquitectura antes de bloquear procesos hijos. Es una defensa
del proceso para este código fijado, no una sandbox contra código nativo hostil.

`authentic_bridge.js` utiliza **sin modificaciones** el hash NQC047 y el motor
NQC048. Sustituye su callback ficticio por el trabajador Python completo.
El único transporte que ofrece genera tres entradas de prueba fijas: chain ID,
campos de la cabecera conservada y una prueba inválida. **LIVE está prohibido**.
Los tests observan dos respuestas verificadas, rechazo de la tercera antes
de una cuarta, corrupción, pérdida de confirmaciones, repetición desde cero y
una respuesta de 700 KB que se revalida después de reconstruir tres fragmentos.

## Ensayo con almacenamiento remoto real

`github_store.js` usa las herramientas conectadas actuales, con repositorio,
rama y ruta fijados. Exige SHA anterior al escribir el journal y lee cada
resultado por commit exacto. `code_mode_probe.js` conecta ese almacén al
Python real del ejecutor; no accede a Triport.

| Fase | Resultado observado |
| --- | --- |
| Primera entrada sintética | `RESERVED → RECEIVED → VERIFIED`; NQC037 ejecutado sobre respuesta releída |
| Segunda entrada sintética | Se revalidó la primera; se persistió la segunda; el harness descartó intencionalmente su confirmación |
| Nueva ejecución | Releyó ambas, NQC037 verificó las dos, envió **cero** entradas y devolvió `BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED` |

Commit final del ensayo:
`a9e3a5346a1bc7549fe86ed53a1e0aa238eaeee3`.
Las transiciones y hashes están en `evidence/remote-probe.json`; el journal y
sus fragmentos se conservan en `evidence/remote/`. La segunda fila sigue
`RECEIVED`: **no se promovió, borró ni reinició para continuar**.

El envelope original del padre sigue siendo `id=6`. La segunda entrada del
ensayo usa explícitamente un envelope **sintético** `id=2` sobre esos campos.
No es una respuesta Triport ni una nueva observación histórica. Tampoco las
dos reservas de prueba consumen o reinicializan el presupuesto real de ocho.

Esto demuestra la integración y la recuperación concreta, **no** exclusión
entre hosts independientes, un registro LIVE único ni resistencia a rollback
por otro actor. El CAS de un archivo GitHub no cierra por sí solo esas garantías.

## Reproducción offline

Desde la raíz del checkout, con un Python que tenga instaladas las versiones
originales de NQC037:

```sh
python -I migration/experiments/nqc-052-authentic-durable-verifier/worker.py --repo-root . --check
python -m unittest discover -s migration/experiments/nqc-037-historical-state/tests -v
python -m unittest discover -s migration/experiments/nqc-052-authentic-durable-verifier -p test_worker.py -v
NQC052_PYTHON=/ruta/al/python node migration/experiments/nqc-052-authentic-durable-verifier/test_bridge.js
NQC052_PYTHON=/ruta/al/python node migration/experiments/nqc-052-authentic-durable-verifier/replay.js a9e3a5346a1bc7549fe86ed53a1e0aa238eaeee3
python migration/verify_isolation.py
python -m unittest migration/test_isolation.py -v
```

`replay.js` lee el journal por commit Git local, sin red, sin escritura y con
`maxNewRequests=0`. Exit 0 significa que reprodujo el **bloqueo esperado** con
dos respuestas sintéticas revalidadas, no que autorice adquisición.

Se conserva el primer fallo del harness: 4 errores de comprobación en Python
y 4 fallos Node porque el bloqueo de procesos impedía la carga criptográfica.
Se corrigió exclusivamente el trabajador nuevo; las suites finales pasan.
La escritura Git directa no tenía autenticación; la publicación se hizo por
el conector GitHub existente y su árbol coincidió exactamente con el local.

## Credencial y siguiente movimiento

La documentación oficial de [Codex Cloud](https://learn.chatgpt.com/docs/environments/cloud-environments)
describe Network secrets: el proceso recibe un placeholder y un proxy sustituye
la credencial para destinos HTTPS configurados. **No se demostró ese canal en
esta sesión Work**. Las dos variables NQC previstas están ausentes (solo se
comprobó presencia), no apareció una herramienta genérica de secretos de red
y la búsqueda de plugin Triport no encontró resultados. La
[documentación de seguridad](https://learn.chatgpt.com/docs/agent-approvals-security)
distingue las capacidades de Work Cloud y Codex Cloud. La existencia de una
función documentada no confirma acceso en esta cuenta.

`WORK_ACCESS_REVIEW.json` conserva el alcance. No se solicitó, leyó, mostró ni
publicó una clave; no se consultó Triport ni se cambiaron integraciones.

Siguiente movimiento: verificar metadatos no secretos de un canal oficial
disponible y cerrar la identidad única del registro, antirrollback y exclusión
operativa. La ruta candidata es Network secrets de Codex Cloud; todavía falta
confirmar disponibilidad y enlace al destino. **No ejecutar una prueba RPC
para comprobar la clave**, ni crear otro presupuesto, ni rehabilitar este
journal sintético como LIVE. Las consultas siguen bloqueadas hasta demostrar
conjuntamente ambos requisitos y el tratamiento seguro de respuestas.

No hay nuevas pruebas históricas de estado, preestado exacto autenticado,
replay Nitro ni evidencia de beneficio. `0/11` slots del corte txIndex1.
Confianza alta en los resultados técnicos reproducidos; rentabilidad aún
sin demostrar. Solo se añaden archivos NQC052; main, NQC037–051, workflows,
nexus-engine, Cano, Vercel y las integraciones permanecen fuera de los cambios.
