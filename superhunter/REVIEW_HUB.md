# Revisión integrada y continuidad del proyecto

Esta entrega conecta las evidencias de QA, laboratorio nativo, grafo causal y
fuzzing numérico en un reporte autocontenido Markdown/HTML. No conecta motores
de explotación ni transforma las pruebas numéricas en hallazgos de protocolos.

## Ejecución desde la raíz de NQC

Los directorios deben ser nuevos y quedar fuera del checkout público.
Python 3.11+ y los requisitos locales ya documentados siguen siendo necesarios.

```bash
python3 -m superhunter check --out /tmp/sh-qa-001
python3 -m superhunter local-lab --out /tmp/sh-lab-001
python3 -m superhunter fuzz-lab --seed 20261104 --cases 256 --out /tmp/sh-fuzz-001
python3 -m superhunter review \
  --qa /tmp/sh-qa-001 --lab /tmp/sh-lab-001 --fuzz /tmp/sh-fuzz-001 \
  --out /tmp/sh-review-001
python3 -m superhunter verify-review --bundle /tmp/sh-review-001
```

`review` captura los bytes de los tres paquetes, conserva sus manifiestos y
aplica sus verificadores a esas mismas copias. Exige QA satisfactoria con el
snapshot actual; vuelve a calcular la referencia local y los casos del fuzzer;
comprueba el grafo, la bitácora y los vínculos entre entradas y resultados.

Genera `review.json`, `REVIEW.md`, `index.html`, los artefactos originales y un
manifiesto final. No acepta una etiqueta PASS como sustituto de los verificadores.
El HTML es estático, escapa todo el contenido y no carga recursos externos.
Los informes se recomputan durante la verificación: una modificación de texto
no puede presentarse como el informe derivado de esas evidencias.

## Contexto conservado

`integration_milestones.json` mantiene los 27 puntos originales de las capturas:
12 implementaciones acotadas y 15 pendientes. Cada implementación acotada exige
referencias de tests presentes en el recibo de QA; los límites aparecen junto
a la marca. No es un porcentaje de terminación de la plataforma.

`capabilities.json` mantiene los 50 IDs: 4 parciales, 29 pendientes y 17 que
requieren reformulación defensiva. No se marca ninguna capacidad completa.
El punto 47 incorpora el reporte Markdown/HTML local, sin convertirse en un
reporte de una vulnerabilidad real ni en certificación de cumplimiento.

## Resultados ejecutados de esta entrega

- Se materializaron y comprobaron contra Git los 29 archivos de código, pruebas
  y políticas ejecutables del commit `d3fcd6ca16774efc921c964975c8f3cc5946ac1b`.
- Baseline conjunto: 199 tests, sin fallos, errores ni omisiones.
- Primera suite con el reporte: 226 tests, sin fallos, errores ni omisiones.
- Se detectó un commit concurrente, `d3ab1a06b330e2d056114da91ff5f7b53d1304a7`,
  con controles adicionales de evidencia y 25 pruebas. Se preservó íntegro.
- Suite final reconciliada: **251 tests**, sin fallos, errores ni omisiones;
  los ocho comandos se reejecutaron sobre una sola identidad de fuentes.
- Ejecutados `check`, `verify-check`, `local-lab`, `verify-lab`, `fuzz-lab`,
  `verify-fuzz`, `review` y `verify-review`, todos con salida 0.
- Cinco casos numéricos fijos y 256 generados, semilla 20261104, recalculados.

La primera invocación de baseline excedió el límite de la herramienta sin un
resultado completo; se reejecutó y se registró el baseline completo. Durante el
desarrollo del reporte se corrigieron un nombre de función de test y un orden
no determinista de presentación antes de ejecutar la suite final. No se
omitieron pruebas para ocultar esas fallas.

## Qué NO prueba este reporte

El recibo no está firmado por un tercero ni autentica al productor remoto.
Un actor con control de todas las fuentes y artefactos puede fabricar una
historia consistente; los hashes no corrigen ese límite de confianza.
`LOCAL_REVIEW_PASS` solo significa revisión local consistente con los
verificadores actuales. No equivale a `Finding`, ni a seguridad de producción,
ni a beneficio económico, ni a ausencia de vulnerabilidades.

No se ejecutaron Forge, forks, RPC, contratos externos, la suite histórica
completa de NQC, su verificador completo de aislamiento ni GitHub Actions.
Los cambios de esta entrega están limitados a `superhunter/`. No se modifican
main, DIABLO ni los árboles históricos ci/migration/nqc-census.
