# Contra-controles de cobertura temporal — corpus v1

Esta continuación parte del PR #85, commit
`a296e91a3cd33581ef1fbccb10dca037ce28ea20`. Añade un corpus separado para
comprobar las ocho condiciones del informe de entradas de #84. No modifica
los once casos de detección históricos ni utiliza sus etiquetas para calcular
cobertura. Las aceptaciones nativas de #84 conservan su digest anterior.

## Contrato del nuevo corpus

El perfil es `owned-temporal-input-counter-controls-v1`: 16 casos fijos,
ocho pares y 13 secuencias de eventos distintas. Cada par tiene un caso
`present` y un contra-control `absent`, referidos únicamente a la condición
del par. Estas palabras no son etiquetas de vulnerabilidad.

| Condición del par | Caso que la ejerce | Contra-control |
| --- | --- | --- |
| `use_without_control` | Uso sin controles previos | Grant seguido de uso actual |
| `current_grant_use` | Generación actual | Generación aún no emitida |
| `revoked_grant_use` | Generación emitida y luego revocada | Generación del evento revoke, nunca emitida |
| `stale_grant_after_regrant_use` | Generación antigua tras reotorgar | Generación actual tras reotorgar |
| `principal_mismatch_use` | Principal declarado distinto | Principal coincidente |
| `scope_mismatch_use` | Tenant y acción distintos | Ámbito coincidente |
| `repeated_current_grant_use` | Dos usos de la misma generación actual | Rotación de generación entre usos |
| `current_grant_after_revocation_use` | Revoke anterior al grant actual | Dos grants sin revoke |

Cada caso declara manualmente los índices esperados de **las ocho condiciones**,
incluidas las listas vacías. Los algoritmos incremental y de historial reciben
solo los eventos. Después se comparan sus resultados entre sí y contra las
expectativas. Dos algoritmos que coincidan en un resultado incorrecto no
satisfacen por ello el contrato. Las expectativas comparten autor y
especificación con el código; no se atribuye independencia de productores.

Los eventos y sus credenciales se copian por ocurrencia y por caso. Un cambio
local de un caso no puede propagarse a otro por referencias compartidas.

Identidades separadas:

- Corpus adicional, incluidos los índices esperados:
  `eb2898a1714961bd4bf918ef096cb8cd8ee66622269284b4918a18ff6724261e`.
- Corpus histórico completo, incluidas etiquetas y variantes:
  `a0c577c4cad38f8518dfafa1860e77415e1e94a69136ee5e1b2b7b8777e78c0c`.

La creación exige ambos hashes. Cambiar un corpus requiere una revisión
explícita de su versión e identidad; no se acepta recalcular el manifiesto de
un expediente existente. El inventario exige exactamente un caso de cada rol
para cada condición, identidades únicas e índices enteros, ordenados, sin
duplicados, dentro del rango y apuntando a eventos de uso.

## Informes y comandos

Desde el checkout, con un destino nuevo fuera del repositorio:

```sh
python3 -B -m superhunter review-owned-coverage-suite --out /ruta/privada/contra-controles
python3 -B -m superhunter verify-owned-coverage-suite --bundle /ruta/privada/contra-controles --expected-source DIGEST_ESPERADO
```

Solo se admite el corpus incorporado. El bundle contiene `inputs.json`,
`evaluation.json`, `REVIEW.md` y el marcador final `COMPLETE.json`. El verificador
recalcula el informe y exige coincidencia exacta de sus archivos, identidad de
código, inventario y hashes; vuelve a comprobar los bytes tras el cálculo.

`evaluation.json` enumera duplicados dentro del corpus nuevo y secuencias
compartidas con el histórico. Cuatro casos nuevos reutilizan la secuencia
grant–uso actual para funciones distintas; no son cuatro muestras
independientes. No se suman los 16 casos a los 11 históricos para obtener una
puntuación de detección.

## Qué permite concluir

El informe permite comprobar las ocho condiciones explícitas, con sus
contra-controles, en este conjunto adicional. El corpus histórico sigue
declarando que carece de `use_without_control`. Su caso `latent_revocation`
sigue igual a `clean_repeat`; esta entrega no ejecuta un detector sobre los
casos nuevos ni afirma corregir el falso negativo.

El módulo no llama al modelo de autorización, al compilador, a una EVM o a un
servicio. No admite objetivos externos o archivos arbitrarios de secuencias.
La cobertura de entradas no demuestra cobertura universal, generalización,
hallazgos originales, operación continua o integración de los 50 candidatos.

## Validación

Se añaden 30 pruebas de regresión y se preservan las 22 pruebas previas de
cobertura. El primer pase focal encontró una referencia compartida entre
casos: 51 PASS y un fallo. La copia por ocurrencia corrigió el problema sin
alterar los valores ni hashes del corpus. Segundo pase: 52/52 PASS.

Las regresiones incluyen expectativas falsas, dos algoritmos coincidentes
pero incorrectos, preservación del corpus histórico, identidades duplicadas,
índices inválidos, entradas e informes alterados con hashes recalculados,
symlinks, mutación durante la verificación y CLI en procesos separados.

Los resultados de QA completo y aceptación nativa de esta versión se registran
en `CONTINUATION.md` y en el paquete de evidencia identificado allí. Los conteos
focales no sustituyen esos controles completos.
