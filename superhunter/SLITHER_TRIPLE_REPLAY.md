# SUPERHUNTER — comparar dos ejecuciones de tres controles Slither

**Continuidad:** rama sucesora del [PR #73](https://github.com/josuechavando350-png/nexus-quant-capital/pull/73), que incorpora el comparador offline del [PR #74](https://github.com/josuechavando350-png/nexus-quant-capital/pull/74), actualizado para **tres** controles por ejecución. No sobrescribir ni fusionar directamente las ramas anteriores sin conciliar sus cambios.

**Estado:** código ejecutable del *verificador offline* publicado, análisis de Slither/solc real **PENDIENTE**; no hay autorización para escanear objetivos externos ni una nueva vulnerabilidad original. Las pruebas de integración y QA íntegra siguen pendientes.

## Por qué

#73 amplía el laboratorio a tres contratos Solidity OWNED:
1. **Positivo:** `require(tx.origin == owner, "owner")` → exactamente 1 alerta del detector `tx-origin`.
2. **Limpio:** `require(msg.sender == owner, "owner")` → 0 alertas.
3. **Exclusión explícita:** `require(tx.origin == msg.sender, "direct caller")` → 0 alertas según la implementación de `tx-origin` upstream; **NO** se afirma que esa condición certifique seguridad general.

#74 comparaba dos *pares* positivos/limpios. Su implementación no podía utilizarse sin cambios sobre #73: el verificador de #73 exige tres subexpedientes y tres argumentos de contexto. La unidad `slither_pair_replay.py` ahora verifica y coteja **seis** reportes originales entre dos ejecuciones (3 + 3). El CLI conserva `compare-owned-slither-pairs` y `verify-owned-slither-comparison` por compatibilidad, pero el contrato exige tres subdirectorios.

## Seguridad y equivalencia

- Ambas rutas de evidencias deben ser directorios distintos y no anidados, sin symlinks en raíces.
- Se exigen **dos hashes SHA-256 externos** de `COMPLETE.json`, obtenidos fuera de los paquetes **antes** de evaluar. Cambios posteriores deben invalidar la verificación.
- Cada expediente se valida con `slither_control_pair.verify_pair`; cada uno de los seis reportes se vuelve a normalizar con `static_review.verify_report`.
- El nuevo `_profile` llama **de verdad** a `slither_control_pair.accept` y `check_context`, sin sustituir sus comprobaciones por comparaciones superficiales. Rechaza mezcla de commits, versiones, scopes, fuentes, polaridades y resultados.
- Se comparan tanto alertas, ubicaciones, fingerprints, clasificación declarada y conteos como identidad del propio adaptador (`adapter_sha256`) y secciones ignoradas. Las variaciones en timestamps o hashes de reportes crudos no se toman como diferencias semánticas por sí mismas.
- El resultado `TWO_SLITHER_THREE_CONTROL_RUNS_AGREE_UNAUTHENTICATED` significa únicamente que **dos expedientes suministrados** son semánticamente compatibles. No demuestra que Slither se ejecutó realmente, que los hosts fueran independientes, que la identidad del productor esté autenticada ni que exista una vulnerabilidad nueva. Mantener `producer_authenticated=false`, `independent_execution_proven=false`, `vulnerability_confirmed=false`.
- El paquete final se crea nuevo con `comparison.json`, `REVIEW.md` y `COMPLETE.json`; reescrituras o falta de contenido bloquean el verificador.

## Comandos (solo después de generar dos expedientes completos en laboratorios autorizados)

```sh
sha256sum /privado/primera/COMPLETE.json
sha256sum /privado/segunda/COMPLETE.json

python3 -m superhunter compare-owned-slither-pairs \
  --first /privado/primera --second /privado/segunda \
  --expected-first-sha256 SHA256_EXTERNO_A \
  --expected-second-sha256 SHA256_EXTERNO_B \
  --out /privado/comparacion-nueva

python3 -m superhunter verify-owned-slither-comparison \
  --first /privado/primera --second /privado/segunda \
  --expected-first-sha256 SHA256_EXTERNO_A \
  --expected-second-sha256 SHA256_EXTERNO_B \
  --bundle /privado/comparacion-nueva
```

Este comparador no necesita Slither para verificar evidencia offline. El generador de los dos paquetes sí requiere, en una fase separada, Slither/solc auditados, sandbox sin egress y sus 3 experimentos OWNED reales.

## Salvaguarda adicional: duplicación literal de evidencia

Un segundo directorio con la misma huella SHA-256 externa del primero **no constituye una repetición**: podría ser solo una copia del paquete. El comparador exige ahora que los dos valores `--expected-...-sha256` sean distintos. Si son idénticos, rechaza con `DISTINCT_EXTERNAL_ANCHORS_REQUIRED` **antes de leer reportes**.

Esto es una defensa **necesaria pero no suficiente**: dos hashes diferentes tampoco prueban ejecución real de Slither, procedencia autenticada ni independencia de hosts. Un operador puede alterar un dato accesorio y conseguir otro hash. La evidencia firme sigue exigiendo bitácoras y firmas de productor confiable más ejecución independiente. Se agregaron dos pruebas a `test_slither_pair_replay.py` y ambas figuran en la lista obligatoria del QA; no se reclaman como PASS sin ejecución.

## Invariancia de anclas durante las lecturas

La revisión posterior al PR #76 agrega una comprobación **al terminar** de leer y validar los seis reportes: se vuelven a obtener y calcular los SHA-256 de `first/COMPLETE.json` y `second/COMPLETE.json`, y ambos deben coincidir con los valores externos ya comprobados al inicio. Cambios de cualquiera de los dos marcadores durante la lectura fallan con `EXTERNAL_ANCHOR_CHANGED_DURING_VERIFICATION`. No se crea un expediente de comparación exitoso si el cambio ocurre antes de su escritura.

Se agregaron tres pruebas de mutación intermedia, una por cada ancla y otra para asegurar ausencia de un nuevo paquete de éxito cuando falla `create`. También se registraron como `REQUIRED_TESTS` en el QA. Son **tests definidos, no PASS ejecutados**; esta revisión no ejecutó Slither/solc ni revalidó QA completo.

**Alcance y límite:** repetir el hash del manifiesto no congela su contenido ni impide que un actor con acceso de escritura cambie archivos entre lecturas. No autentica a los productores y no sustituye un snapshot inmutable con firma. El resultado sigue `TWO_SLITHER_THREE_CONTROL_RUNS_AGREE_UNAUTHENTICATED`.

## Qué falta para certificarlo

**Implementado en el código:** integración de las dos ramas, seis controles cotejados, fingerprints y adaptador en comparación, errores y faltantes como rechazo, nuevo registro de QA y comandos conectados.

**Pruebas unitarias:** archivo `test_slither_pair_replay.py` con **18 casos definidos**; las pruebas usan recibos Slither sintéticos y sustituyen únicamente `verify_pair` y `static_review.verify_report`. `pair.accept` y `check_context` ejecutan sus reglas reales. **No equivale a una corrida nativa Slither.**

**Pendiente:** ejecutar las 18 pruebas sobre checkout íntegro sin stubs del empaquetado, correr QA completa y verificador de fuentes, instalar/aislar Slither genuino de forma auditada, generar dos ejecuciones independientes con reportes originales, y medir la latencia/costo. Los 50 repositorios del catálogo siguen siendo candidatos; #6 no ha cumplido aún los gates para `INTEGRATED_BOUNDED`.

## Instrucción para otros agentes

No fusionar dos ramas independientes del PR #72 por separado sin resolver el conflicto en `quality.py` y `__main__.py`. Esta rama actúa como **propuesta reconciliada** de #73 y #74. Verificar SHA/HEAD de ambas antes de cualquier merge. El marcador de un paquete y las huellas declaradas no autentican el origen de las observaciones.

## Validación integrada posterior, sin scanner

El test [SLITHER_OFFLINE_IMPORT_E2E.md](SLITHER_OFFLINE_IMPORT_E2E.md) ahora conecta sin mocks el importador de resultados Slither, auditoría del paquete, verificación de tres controles y comparación offline de dos paquetes. Las entradas son *sintéticas* y las declaraciones de ejecución no autenticadas; mantener la distinción entre consistencia y veracidad del productor.
