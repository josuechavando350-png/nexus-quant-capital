# Revisión defensiva integrada y conservación de contexto

Esta entrega cierra la validación pendiente del HEAD combinado anterior y añade
un recorrido único para comprobar el propio paquete. **No termina el Hunter ni
confirma vulnerabilidades.** No incorpora explotación autónoma de terceros.

## Uso

Desde la raíz del repositorio, con Python 3.11+, Linux/POSIX y PyYAML 6.0.3:

```bash
python3 -m superhunter review-platform --out /tmp/superhunter-review-001
python3 -m superhunter verify-platform --bundle /tmp/superhunter-review-001
```

El primer comando ejecuta la suite completa, el laboratorio nativo de cinco
casos y 256 casos de fuzzing numérico (semilla 20261104). No acepta direcciones,
RPC, PoCs, comandos de shell ni motores externos. Una etapa fallida impide
publicar la revisión final. Las salidas necesitan una carpeta nueva fuera del
checkout público. El segundo comando vuelve a comprobar todos los artefactos,
recalcula referencias y contrasta la identidad actual de las fuentes.

## Lo conectado

`quality.py` ejecuta las pruebas del paquete. `lab_cli.py` ejecuta el circuito
ScopeGuard/AuditLog de DIABLO y RMC-016 de NQC, su referencia y grafo causal.
`fuzz_cli.py` ejecuta los casos numéricos generados y sus invariantes. El nuevo
`platform.py` verifica esas tres etapas, registra sus hashes y enlaza el resultado
con los dos catálogos. No sustituye esas ejecuciones por booleanos proporcionados.

El catálogo `integration-checklist.json` conserva los 27 puntos originales y
sus cinco grupos. Cada punto parcial o implementado con límites exige tests
identificados y componentes comprobados. Sus límites se imprimen junto a la
palomita. `capabilities.json` conserva por separado los 50 puntos adicionales.
No se suman puntos heterogéneos para fabricar un porcentaje de capacidad.

Las salidas `review/INTEGRATION.md`, `review/CAPABILITIES.md`, `review/STATUS.md`
y `review/review.json` se reconstruyen desde la evidencia. Cambiar una palomita,
un conteo o la afirmación de plataforma completa, aun recalculando el manifiesto
de ese reporte, provoca rechazo si ya no corresponde a los artefactos.

Además de los tests obligatorios del gate anterior, se exige que el recibo incluya
**todo** el inventario actual de tests. Se extrae mediante AST de las clases
unittest.TestCase del propio paquete, sin ejecutar el código de los tests para
contarlos. Una forma dinámica o heredada no soportada requiere revisión y queda
bloqueada. Esta restricción corresponde a nuestras suites, no a un analizador
universal de código.

## Defecto corregido

Se reprodujo en el código anterior que el verificador de grafos aceptaba
`schema_version=true` como `1` e `independently_authenticated=0` como `false`,
por la igualdad de valores de Python. Se sustituyó la comparación por bytes JSON
canónicos y se añadieron pruebas negativas. Esto endurece la integridad de los
artefactos; no demuestra autenticidad del productor.

## Validación ejecutada

- Base combinada `d3fcd6ca16774efc921c964975c8f3cc5946ac1b`: 199 pruebas,
  sin fallos, errores ni omisiones, y `check`/`verify-check` aprobados.
- Primera validación de esta ampliación: 236 pruebas, sin fallos, errores ni
  omisiones (35 pruebas de revisión integrada y dos regresiones nuevas del grafo).
- Antes de publicar se detectó el commit concurrente
  `d3ab1a06b330e2d056114da91ff5f7b53d1304a7`. Se conservaron sus cambios y
  25 tests adicionales de evidencia numérica. El conjunto conciliado pasó
  **261 pruebas**, sin fallos, errores ni omisiones.
- Se ejecutaron `review-platform` y `verify-platform` realmente, fuera de los
  tests con sustitutos. El recibo final de esa ejecución incluye las 261 pruebas,
  cinco casos nativos y 256 casos numéricos generados.
- Los recibos sintéticos usados dentro de tests unitarios son datos de prueba,
  no evidencia de ejecución. El paquete de validación distingue ambos.

## Significado exacto del éxito

`LOCAL_DEFENSIVE_REVIEW_PASS` significa que pasó este recorrido local, no que
los 27 o 50 requisitos estén completos. Siempre conserva `platform_complete=false`
y `vulnerability_confirmed=false`. Los hashes y la repetición de cálculos no
son una firma de productor remoto, una garantía de ausencia de bugs ni una
certificación. Los límites de los workers existentes siguen aplicando y no son
un sandbox de sistema operativo apto para código hostil.

Continúan pendientes la ejecución EVM, la reconstrucción de vulnerabilidades,
el cálculo de impacto real, el triaje final, la revisión de alcance vigente y
la operación continua de programas. Tampoco se ejecutaron la suite histórica
completa NQC, su verificador total de aislamiento ni GitHub Actions. El checkout
completo no estaba disponible por red; la preservación histórica se controla
mediante el diff Git y los hashes de los árboles no modificados.

Los resultados anteriores se conservan como historia. El registro de esta
entrega está en `platform-validation.json`; la ejecución vuelve a generar su
propia evidencia sin sobrescribir otras revisiones.
