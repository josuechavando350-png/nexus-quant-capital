# Cobertura temporal de las entradas propias

Continuación del trabajo pendiente documentado después de PR #83, commit
`93b5a34fca1159dcfb6b3e41631003612c0604f9`. El informe describe las once
secuencias sintéticas existentes; no ejecuta contratos ni altera el detector,
las fuentes, etiquetas, secuencias o métricas históricas.

## Qué calcula

Cada condición conserva los índices de los eventos que la ejercitan. Los índices
son de base cero y cada secuencia está limitada a 64 eventos por el esquema
histórico. La clave de estado es `(principal, tenant, action)`; generaciones de
otras claves no se mezclan. Cada grant o revoke aumenta la generación de su clave.

| Condición | Definición acotada |
| --- | --- |
| `use_without_control` | Uso ligado a su principal/ámbito, sin grant o revoke anterior para esa clave. |
| `current_grant_use` | Uso ligado, último control grant y generación de la credencial igual a la actual. |
| `revoked_grant_use` | Uso ligado de una generación emitida por grant y revocada posteriormente; último control revoke. |
| `stale_grant_after_regrant_use` | Uso ligado de una generación emitida y revocada; último control grant posterior. |
| `principal_mismatch_use` | La credencial declarada y el evento difieren en principal. |
| `scope_mismatch_use` | Difieren en tenant o action. |
| `repeated_current_grant_use` | Segundo o posterior uso actual de la misma clave/generación, válido según la especificación de entradas. |
| `current_grant_after_revocation_use` | Uso de generación actual después de un revoke de esa clave, incluso si ese revoke precedió al primer grant. |

Las condiciones pueden solaparse y **no son un catálogo exhaustivo de defectos**.
Los usos con principal o ámbito distintos no cuentan como condiciones temporales
ligadas. Una generación nunca emitida no cuenta como credencial revocada. Un uso
anticipado de una generación futura no cuenta como repetición de un uso válido.

`owned_authority_coverage.py` mantiene estado incremental. La referencia separada
reconstruye los controles anteriores desde el historial para cada uso. Ambos
comparten el esquema y la definición de condiciones; su coincidencia no demuestra
independencia del productor, completitud ni corrección universal.

## Uso integrado

Desde la raíz del repositorio; salidas nuevas fuera del checkout:

```sh
python3 -B -m superhunter review-owned-authority-coverage --out /ruta/privada/cobertura
python3 -B -m superhunter verify-owned-authority-coverage --bundle /ruta/privada/cobertura --expected-source DIGEST_DEL_INFORME
```

La CLI solo usa el corpus propio fijado. No admite objetivos, archivos de eventos
arbitrarios, RPC, credenciales reales ni comandos de generación de secuencias.
El paquete incluye `inputs.json`, `coverage.json`, `REVIEW.md` y `COMPLETE.json`.
El verificador regenera el informe, revisa su identidad de código, inventario,
hashes y bytes antes/después. Una edición con hashes recalculados no pasa si el
contenido discrepa del corpus o de los resultados recalculados.

## Interpretación del corpus histórico

`clean_repeat` y `latent_revocation` tienen la misma secuencia de eventos. En
ambos, solo aparecen uso actual y repetición; no aparecen revocación ni uso
posterior a ella. La omisión histórica continúa registrada: este informe **no
transforma FN en TP**, ni añade una detección o una ejecución EVM.

El corpus no contiene ningún `use_without_control` ligado. El informe conserva
ese hueco. No deduce de él una vulnerabilidad, severidad, recompensa o porcentaje
global. Los grupos de secuencias duplicadas se muestran sin contarlos como
muestras independientes. Incluso ocho condiciones observadas no demostrarían
cobertura completa de una aplicación.

## Regresiones

22 pruebas nuevas, incluidas 780 secuencias enumeradas de longitud 1–4 y 400
secuencias sintéticas con semilla fija y múltiples ámbitos, contra la referencia
de historial. Son controles de implementación conocidos, no benchmark ciego.
Se prueban el CLI y verificador en procesos separados, resultados alterados con
manifiesto recalculado, entradas sustituidas, discrepancia entre algoritmos,
archivos extra, symlinks, mutación durante la verificación y salida preexistente.

El componente y sus pruebas quedan registrados en QA, con un grupo fijo y sin
mover identidades anteriores. Consultar `CONTINUATION.md` para resultados de la
ejecución completa y estado de reanudación.
