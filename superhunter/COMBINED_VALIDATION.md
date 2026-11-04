# SUPERHUNTER — validación combinada y corrección del verificador

## Alcance

Se recuperaron los **29 archivos ejecutables, de pruebas y de política** de
`superhunter/` correspondientes al commit
`0a6b912caaf67db9ecaf2b8ac226f02b5279cae2`, verificando sus Git blob SHA.
El padre de publicación `d3fcd6ca16774efc921c964975c8f3cc5946ac1b` solo añade
`fuzz-validation.json`: no cambia ese conjunto ejecutable.
La descarga Git del repositorio completo no estaba disponible. Se usaron el
conector GitHub y copias locales con identidad de bytes comprobada; no se
supone que un ZIP anterior represente la rama actual.

Se ejecutó la suite combinada original: **199 pruebas aprobadas**. Esto reúne
el puente, laboratorio nativo, auditoría semántica, grafo causal, control de
calidad y fuzzing numérico que se habían validado por separado.

## Fallos reproducidos y corregidos

El verificador de campañas numéricas aceptaba evidencia internamente
contradictoria después de recalcular sus hashes. Se reprodujeron cuatro casos:
un conteo con tipo incorrecto, un intervalo de tiempo invertido, un evento de
alcance etiquetado como producción y un evento final que afirmaba una
vulnerabilidad mientras el resumen negaba tal afirmación.

`verify_fuzz_audit_links()` comparte el módulo de auditoría semántica del
laboratorio. Ahora comprueba el esquema completo del resumen, tipos exactos de
conteos, UUID, identidad del motor, intervalo temporal y orden de los eventos.
Cada autorización, hash de entrada, resultado NQC, referencia independiente,
exclusión y cierre debe coincidir con el caso ejecutado. Los datos se comparan
mediante JSON canónico para distinguir `true`, `1` y `1.0`.

`fuzz_lab.py` exige además un manifiesto con versión entera, filas con esquema
cerrado e índices enteros, y coincidencia exacta de tipos en entradas/resultados.
El índice de generación queda acotado a uint64 y falla con ValueError si excede
ese dominio. No se cambiaron los cuatro archivos originales fijados de DIABLO/NQC.

## Evidencia de regresión

Se añadieron **25 tests**. Antes de corregir el código, esta suite produjo 29
fallos de aserción (incluyendo subtests) y un error; no son 30 tests diferentes.
Después de la corrección, la suite combinada ejecutó **224 tests**, sin fallos,
errores ni omisiones. Se ejecutó nuevamente a través del worker de calidad,
con recibos individuales y comparación de fuentes antes/después.

También se ejecutaron y verificaron en procesos separados:

- `check` / `verify-check`: 224 tests, `LOCAL_QA_PASS`.
- `local-lab` / `verify-lab`: cinco casos fijos y grafo causal de 24 nodos.
- `fuzz-lab` / `verify-fuzz`: 256 casos, semilla 20261104, oráculo exhaustivo,
  invariancia por permutación y escalado, y siete controles negativos.

Identidad ejecutable y de políticas validada:
`22b0e2b791a70f53984a70beabd775508f3291c71674a71046002643eb379201`.
Los nuevos tests son obligatorios en `quality.py`; no quedan fuera del control
conjunto. El registro de 50 capacidades no cambia: ninguna está completa;
3, 45, 47 y 48 conservan soporte parcial expresamente delimitado.

## Reproducción

Python 3.11+ en POSIX y PyYAML 6.0.3. Desde la raíz de NQC; cada salida debe
estar en un directorio nuevo, fuera del checkout público:

```bash
python3 -m superhunter check --out /tmp/sh-combined-001
python3 -m superhunter verify-check --bundle /tmp/sh-combined-001
python3 -m superhunter local-lab --out /tmp/sh-native-001
python3 -m superhunter verify-lab --bundle /tmp/sh-native-001
python3 -m superhunter fuzz-lab --seed 20261104 --cases 256 --out /tmp/sh-fuzz-001
python3 -m superhunter verify-fuzz --bundle /tmp/sh-fuzz-001
```

## Límites de la conclusión

Estas son pruebas del **paquete SUPERHUNTER completo de esta rama**, no de todo
el repositorio histórico NQC ni de su verificador de aislamiento completo.
No se ejecutaron GitHub Actions, Forge, contratos Solidity, forks, RPC,
transacciones, investigación de objetivos externos ni envío de reportes.
Los casos numéricos son sintéticos y no acreditan un bug o recompensa.

Las comprobaciones detectan inconsistencias entre artefactos; no autentican
al productor. Un operador que controle código y todas las evidencias puede
fabricar un historial coherente. No se promete perfección ni ausencia universal
de falsos negativos. El resultado permanece `vulnerability_confirmed=false`.
