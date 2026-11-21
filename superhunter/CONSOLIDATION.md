# SUPERHUNTER · Consolidación de las ramas de producto

Los PR [118](https://github.com/josuechavando350-png/nexus-quant-capital/pull/118) y [119](https://github.com/josuechavando350-png/nexus-quant-capital/pull/119) partieron de `672c31392929b8efbd6b3d5983c44e8560232add`. Las dos transcripciones históricas de 99 y 70 participantes compartían 63 identidades. Había 36 exclusivas de la primera y siete exclusivas de la segunda. El total histórico de esas dos ejecuciones era 106. [Archivo de 99](product_supply/component-session-99.json) · [Archivo de 70](product_supply/native-session-70.json)

## Evidencia recuperada en el PR 120

La rama de desarrollo `feat/superhunter-consolidated-product` recuperó el árbol `58e2535c45c195bbf8980c5af01ad0f3fc6de66e` del checkout `1edb169`. Los dos expedientes históricos se pueden recontar sin instalar herramientas externas. [PR 120](https://github.com/josuechavando350-png/nexus-quant-capital/pull/120) · [Matriz de los 200](INTEGRATION_STATUS_200.md)

Una ejecución con los kits oficiales sobre ese árbol produjo 222 respuestas y terminó con código 2. Participaron 127 identidades en 133 operaciones. Se conservaron 105 de las 106 identidades históricas. Faltó `cdump/evmole`; los grupos EVM y Java rechazaron sus entradas. El verificador independiente rechazó 20 alteraciones de ese expediente. [Acta parcial](product_supply/acceptance-120/recovered-partial-replay.json) · [Transcripción parcial](product_supply/acceptance-120/recovered-partial-session.json)

En el PR 119 se reprodujeron los dos grupos afectados en dos checkouts limpios del mismo commit en un host. Las cuatro identidades produjeron los mismos 13.025 bytes. El commit `fae4157` incorporó al perfil unificado el Node de la distribución oficial y la receta del JRE reconstruido desde Debian. [Acta EVM y Java](product_supply/acceptance-120/evm-java-replay.json) · [Transcripción](product_supply/acceptance-120/evm-java-transcript.json)

En una ejecución aislada del commit `fae4157` con observación de excepciones, el verificador acreditó las 106 identidades históricas y sus 110 combinaciones de recibos. La sesión emitió 222 respuestas, con 128 identidades, 89 de ejecución, 39 de referencia y 137 operaciones. Se rechazaron 20 alteraciones. Esta acta corresponde a esa ejecución individual. [Acta y verificador](product_supply/acceptance-120/observed-session-verification.json) · [Transcripción](product_supply/acceptance-120/observed-session.json)

## Pruebas del producto y de los árboles protegidos

| Alcance | Resultado | Evidencia |
|---|---|---|
| 37 módulos de producto, inventario y recibos, árbol `614361e3` | 398 aprobadas, cero fallidas u omitidas. El oráculo independiente utilizó la distribución local de npm para resolver semver. | [Casos de prueba y huella del registro](product_supply/acceptance-120/qa-results.json) |
| Rust histórico de Census, Cargo y rustc 1.98.1 | 528 aprobadas sin red. Los binarios compilados correspondían al árbol preservado y se reutilizaron con Cargo.lock fijado. | [Casos por ejecutable de prueba](product_supply/acceptance-120/qa-results.json) |
| Aislamiento de NQC y migración | 642 archivos protegidos verificados. En el árbol histórico pasaron las nueve pruebas de migración. Sobre el producto ampliado pasaron ocho y una dio `unreviewed root file`. | [Resultado por alcance](product_supply/acceptance-120/qa-results.json) |
| QA global del producto, árbol `614361e3` | Bloqueada antes de emitir el certificado. El inventario exige 426 archivos Python y 152 archivos de datos, frente al límite total de 500. | [Inventario de QA](product_supply/acceptance-120/qa-results.json) |

## Ejecutar el perfil conjunto

Se utiliza la misma entrada de producto y un solo índice de 200 identidades. Una fila puede tener varias operaciones. `integration-matrix` y `integration-coverage` exponen cada operación mediante `session_operations`, con su rol, el campo que contiene el recibo y su SHA-256. El resultado original se obtiene consultando la identidad en la misma sesión. El selector acepta controles fijos locales. La única cuenta por identidad prioriza la ejecución cuando también hay un uso documental.

Para preparar entradas temporales del inventario ARM64, escoger un directorio de trabajo fuera de los montajes que la versión fijada de Syft omite. En este host, el directorio de datos del workspace y un directorio ordinario de tmpfs produjeron las 75 observaciones de siete archivos; bajo `/dev/shm` el mismo binario informó cero. El producto rechazó ese resultado. [Control sobre los dos sistemas de archivos](product_supply/acceptance-120/arm-inventory-storage.json) · [Selección de rutas de Syft](https://github.com/anchore/syft/blob/139612f0cc25952bad472ab8ce6a86e4b442da95/syft/internal/fileresolver/path_skipper.go)

Preparar los [insumos históricos](OFFLINE_SOURCE_AND_GO.md), los [dominios de controles](DEFENSIVE_COMPONENTS.md), el [perfil de ocho grupos nativos](product_supply/native-kits-example.json) y el [códec de expedientes](EVIDENCE_CODEC.md). Los grupos java y upgrades requieren los kits descritos en sus [recibos Java](product_supply/java-native-receipt.json) y [de contratos](product_supply/upgrades-native-receipt.json). A la invocación de aceptación de 220 respuestas del PR 117, agregar estas opciones, antes del directorio preparado:

```sh
--component-controls all --native-kits "$NATIVE_KITS"
```

Las 222 respuestas incluyen `component-controls` y `native-capabilities`. Para evaluar la transcripción JSONL completa en un proceso separado:

```sh
python3.12 -B -m superhunter.tools.verify_review_115 --require-consolidated --check-controls session.jsonl
```

El verificador contrasta cada fila de la sesión con las dos transcripciones históricas. Exige las 106 identidades y las 110 combinaciones distintas de identidad, rol y campo de recibo. WhatsABI, Scapy, Cppcheck y Capstone conservan dos campos cada uno. Una referencia puede ascender a ejecución cuando el productor validado conserva el campo y prueba ese rol. Las huellas de los nuevos resultados se contrastan con sus productores antes de realizar el cotejo histórico.

Los artefactos emitidos por un productor bloqueado carecen de crédito. La reproducción requiere los compiladores, binarios y conjuntos de dependencias fijados en cada manifiesto. Dos checkouts en una máquina permiten reproducir el resultado en ese host. La evaluación ciega y el rendimiento de descubrimiento en otros entornos siguen pendientes.

## Resolución de los cambios compartidos

| Rutas del comentario de coordinación | Comportamiento conservado |
|---|---|
| `product_batches.py`, `product_review.py`, `tools/catalog_session.py` | Un índice y un punto de entrada. Se pueden seleccionar dominios defensivos y grupos nativos, y se conserva cada operación en la fila de su identidad. |
| `product_sources.py`, `product_source_audit.py` | El manifiesto incluye 200 gitlinks. Se conservan la comprobación de bytes del directorio de trabajo, el orden de resultados, el inventario anterior y su huella. |
| `product_licenses.py`, `tests/test_product_license_session.py`, `tests/test_product_inventory_parallel.py` | El contenido de estas tres rutas ya coincidía entre las ramas. |
| `tests/test_product_source_parallel.py` | Se amplió el fixture de 153 a 200 y se conservaron los controles de índices, modos de archivo, enlaces y normalización de Git. |
| `quality.py` | Se registraron productores, datos de control y pruebas de las dos ramas. |
| `tools/verify_review_115.py` | Verificación desde las fuentes fijadas, los resultados individuales y el índice completo. Los perfiles históricos conservan sus contratos originales. |
| `SOURCE_ASSURANCE.md`, `SOURCE_CHECKOUT.md` | Quedaron versionados el expediente de 153 y el de los 200. Las optimizaciones ya portadas del PR 116 se conservan una sola vez. |

Los [200 checkouts directos](SOURCE_CHECKOUT.md) coinciden con sus revisiones de catálogo. La revisión de avisos alcanza los 200 proyectos. Quedan pendientes la materialización de 141 gitlinks anidados y un objeto Git LFS, y la revisión de obligaciones de distribución del producto y sus dependencias.
