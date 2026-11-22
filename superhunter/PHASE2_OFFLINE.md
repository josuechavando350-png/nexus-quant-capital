# Fase 2 · Estado de las mediciones sin red

La revisión parte del commit `045f13b89b9a0000198c0eefc23604cf1c1f3451`. Se ejecutaron la comprobación de la captura y las pruebas de regresión en un espacio de red aislado. Este documento registra dos concursos elegidos y el resultado de disponibilidad de cada medición. Ninguna de las tres campañas dinámicas se inició.

## Canto · LendingLedger.sol

| Hallazgo del juez | ¿ityfuzz alcanzó la ruta? | ¿ityfuzz localizó la causa? |
|---|---|---|
| H-01 · Peso de mercado incorrecto | Sin medición | Sin medición |
| H-02 · Cálculo incorrecto del siguiente período | Sin medición | Sin medición |

**El fuzzer consumió 0 segundos y ejecutó 0 iteraciones.** No se creó una traza dinámica ni hubo salida del fuzzer. La comprobación de disponibilidad fuera de línea `ityfuzz --version` terminó con código 127, stdout vacío y una sola línea en stderr.

```text
sh: 1: ityfuzz: not found
```

El entorno preparado contenía `ityfuzz-opcodes`. La captura de Canto contenía el contrato, el bytecode y seis salidas del trabajo anterior. En el material disponible no se identificó un snapshot de estado con bloque, raíz y datos de almacenamiento verificables para este contrato. Se confirmó la integridad de la captura existente. Las mediciones de esta fase excluyen esos datos estáticos.

| Comprobación real | Resultado |
|---|---|
| Archivos verificados por `toolkit benchmark-canto --capture` | 8 |
| Campo histórico `tools.ityfuzz.fuzzing_executed` | `false` |
| SHA-256 del ZIP verificado | `209663693febe6624148a0f57ad0d89d0addadc27293bc0189820d52195e0c5a` |

[Informe del juez](https://code4rena.com/reports/2024-01-canto) · [Expediente previo de SuperHunter](product_supply/c4-canto-2024-01.json)

## ENS · Octubre de 2023

El alcance publicado fue de un contrato Solidity. El material local no contenía una copia identificada de la revisión del concurso con sus dependencias ni el informe final completo con el desglose de hallazgos. No se generaron informes nuevos de la Capa 1 ni de ityfuzz.

| Categoría del juez | Hallazgos de referencia | Localizados por SuperHunter |
|---|---|---|
| High | Recuento e identificadores sin verificar offline | No evaluado |
| Medium | Recuento e identificadores sin verificar offline | No evaluado |

[Informe público de ENS](https://code4rena.com/reports/2023-10-ens)

## Munchables · Julio de 2024

El resumen público ya consultado registraba un contrato Solidity, cinco hallazgos altos y uno medio. Esas cifras proceden del juez. El material local no contenía la revisión del concurso con sus dependencias ni los informes de ejecución correspondientes.

| Categoría del juez | Hallazgos de referencia | Localizados por SuperHunter |
|---|---:|---|
| High | 5 | No evaluado |
| Medium | 1 | No evaluado |

[Informe público de Munchables](https://code4rena.com/reports/2024-07-munchables)

## Interpretación

Para acreditar localización técnica se exige una observación de la herramienta que señale la operación en el contrato y explique el mecanismo descrito por el juez. Una traza que solo visita una línea acreditaría alcance de esa línea. Las entradas sin ejecución se excluyen del cálculo de aciertos y falsos negativos. No se calculó una tasa de detección para esta fase.

Pasaron las 490 pruebas del producto, las 13 del toolkit y las nueve de aislamiento histórico, sin omisiones en esas suites. Estas pruebas verifican SuperHunter y la integridad de los archivos.
