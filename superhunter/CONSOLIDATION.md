# SUPERHUNTER · Consolidación de las ramas de producto

Los PR [118](https://github.com/josuechavando350-png/nexus-quant-capital/pull/118) y [119](https://github.com/josuechavando350-png/nexus-quant-capital/pull/119) partieron de `672c31392929b8efbd6b3d5983c44e8560232add`. Las dos transcripciones históricas de 99 y 70 participantes compartían 63 identidades. Había 36 exclusivas de la primera y siete exclusivas de la segunda. El total histórico de esas dos ejecuciones era 106. [Archivo de 99](product_supply/component-session-99.json) · [Archivo de 70](product_supply/native-session-70.json)

## Resultado publicado de 8 grupos

El [acta de las dos ejecuciones](product_supply/consolidated-acceptance/acceptance.json) vincula el [productor fae41570](https://github.com/josuechavando350-png/nexus-quant-capital/commit/fae415708eccc117dd809036fcd4df09056777c5) con los árboles Git, las entradas y las transcripciones. Cada checkout emitió 222 respuestas con la misma huella `2c7e58d369f36c9461497824eb81b0043fd4324dba6927bc7670706ee09cb63b`. La comprobación estricta acreditó 128 identidades distintas, 89 con ejecución, 39 con referencias consumidas y 137 operaciones en total. Se conservaron las 106 identidades y 110 operaciones históricas.

## Resultado publicado de 9 grupos

El [acta de las dos ejecuciones](product_supply/consolidated-acceptance-accounting/acceptance.json) vincula el [productor 27fdac61](https://github.com/josuechavando350-png/nexus-quant-capital/commit/27fdac61b21f607325053fc3681e6e079328e9f1) con los árboles Git, las entradas y las transcripciones. Cada checkout emitió 222 respuestas con la misma huella `ea091d5b93821de6557f4c84a5f7d8c8846245e0d5586f8059d0b60fc8261400`. La comprobación estricta acreditó 129 identidades distintas, 91 con ejecución, 38 con referencias consumidas y 139 operaciones en total. Se conservaron las 106 identidades y 110 operaciones históricas.

## Evidencia recuperada en el PR 120

La rama de desarrollo `feat/superhunter-consolidated-product` recuperó el árbol `58e2535c45c195bbf8980c5af01ad0f3fc6de66e` del checkout `1edb169`. Los dos expedientes históricos se pueden recontar sin instalar herramientas externas. [PR 120](https://github.com/josuechavando350-png/nexus-quant-capital/pull/120) · [Matriz de los 200](INTEGRATION_STATUS_200.md)

Una ejecución con los kits oficiales sobre ese árbol produjo 222 respuestas y terminó con código 2. Participaron 127 identidades en 133 operaciones. Se conservaron 105 de las 106 identidades históricas. Faltó `cdump/evmole`; los grupos EVM y Java rechazaron sus entradas. El verificador independiente rechazó 20 alteraciones de ese expediente. [Acta parcial](product_supply/acceptance-120/recovered-partial-replay.json) · [Transcripción parcial](product_supply/acceptance-120/recovered-partial-session.json)

En el PR 119 se reprodujeron los dos grupos afectados en dos checkouts limpios del mismo commit en un host. Las cuatro identidades produjeron los mismos 13.025 bytes. El commit `fae4157` incorporó al perfil unificado el Node de la distribución oficial y la receta del JRE reconstruido desde Debian. [Acta EVM y Java](product_supply/acceptance-120/evm-java-replay.json) · [Transcripción](product_supply/acceptance-120/evm-java-transcript.json)

En una ejecución aislada del commit `fae4157` con observación de excepciones, el verificador acreditó las 106 identidades históricas y sus 110 combinaciones de recibos. La sesión emitió 222 respuestas, con 128 identidades, 89 de ejecución, 39 de referencia y 137 operaciones. Se rechazaron 20 alteraciones. Esta acta corresponde a esa ejecución individual. [Acta y verificador](product_supply/acceptance-120/observed-session-verification.json) · [Transcripción](product_supply/acceptance-120/observed-session.json)

Con dos conjuntos de insumos preparados por separado, dos checkouts del productor de ocho grupos acreditaron exactamente las mismas 128 identidades, roles y 137 operaciones. Coincidieron 217 de 222 respuestas. Siete inventarios CycloneDX regeneraron identificadores y fechas; uno también registró una ruta temporal diferente en nueve propiedades. Esto cambió los recibos de Tree-sitter, ast-grep y GUAC y las dos tablas que los resumen. Cada transcripción superó 20 controles negativos. Los dos hashes íntegros se conservan como control de variación de las entradas. [Desglose por archivo y por fila](product_supply/acceptance-120/regenerated-inputs.json)

## Pruebas del producto y de los árboles protegidos

| Alcance | Resultado | Evidencia |
|---|---|---|
| 37 módulos de producto, inventario y recibos, árbol `614361e3` | 398 aprobadas, cero fallidas u omitidas. El oráculo independiente utilizó la distribución local de npm para resolver semver. | [Casos de prueba y huella del registro](product_supply/acceptance-120/qa-results.json) |
| 38 módulos de producto y contabilidad, árbol [`549fb799`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/e6272223e31151b9adfe285276ce8c10987ecfed) | 411 aprobadas, cero fallidas u omitidas. Se conservaron los 398 casos anteriores. El inventario global de este árbol contiene 428 archivos Python y 158 datos. Se detuvo en su límite de 500. | [Acta de QA, módulos y casos adicionales](product_supply/acceptance-120/qa-411.json) |
| 38 módulos tras la corrección de recibos y el lector de inventarios, árbol [`7c2354c9`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/e4248efc14d61e21654ac1494ed03046ee92ecda) | 420 aprobadas, cero fallidas u omitidas. Se conservaron los 411 casos anteriores y se incorporaron nueve controles. QA global conserva el límite de 500 archivos. | [Acta de 420 pruebas](product_supply/acceptance-120/qa-420.json) |
| 39 módulos en la rama publicada con el lector de encabezados, árbol [`c213150c`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/27ce81b746f69a32c5fc74121f2a6ee2bea9f537) | 431 aprobadas, cero fallidas u omitidas. Se conservaron los 420 casos anteriores. En esa revisión se verificó también la matriz de ocho grupos. QA global se detuvo ante 430 archivos Python y 163 de datos frente a su máximo de 500. | [Acta de 431 pruebas](product_supply/acceptance-120/qa-431.json) |
| Rust histórico de Census, Cargo y rustc 1.98.1 | 528 aprobadas sin red. Los binarios compilados correspondían al árbol preservado y se reutilizaron con Cargo.lock fijado. | [Casos por ejecutable de prueba](product_supply/acceptance-120/qa-results.json) |
| Aislamiento de NQC y migración | 642 archivos protegidos verificados. En el árbol histórico pasaron las nueve pruebas de migración. Sobre el producto ampliado pasaron ocho y una dio `unreviewed root file`. | [Resultado por alcance](product_supply/acceptance-120/qa-results.json) |
| QA global del producto, árbol `614361e3` | Bloqueada antes de emitir el certificado. El inventario exige 426 archivos Python y 152 archivos de datos, frente al límite total de 500. | [Inventario de QA](product_supply/acceptance-120/qa-results.json) |

## Ejecutar el perfil conjunto

Se utiliza la misma entrada de producto y un solo índice de 200 identidades. Una fila puede tener varias operaciones. `integration-matrix` y `integration-coverage` exponen cada operación mediante `session_operations`, con su rol, el campo que contiene el recibo y su SHA-256. El resultado original se obtiene consultando la identidad en la misma sesión. El selector acepta controles fijos locales. La única cuenta por identidad prioriza la ejecución cuando también hay un uso documental.

Para preparar entradas temporales del inventario ARM64, escoger un directorio de trabajo fuera de los montajes que la versión fijada de Syft omite. En este host, el directorio de datos del workspace y un directorio ordinario de tmpfs produjeron las 75 observaciones de siete archivos; bajo `/dev/shm` el mismo binario informó cero. El producto rechazó ese resultado. [Control sobre los dos sistemas de archivos](product_supply/acceptance-120/arm-inventory-storage.json) · [Selección de rutas de Syft](https://github.com/anchore/syft/blob/139612f0cc25952bad472ab8ce6a86e4b442da95/syft/internal/fileresolver/path_skipper.go)

Preparar los [insumos históricos](OFFLINE_SOURCE_AND_GO.md), los [dominios de controles](DEFENSIVE_COMPONENTS.md), el [perfil de ocho grupos nativos](product_supply/native-kits-example.json) y el [códec de expedientes](EVIDENCE_CODEC.md). Los grupos java y upgrades requieren los kits descritos en sus [recibos Java](product_supply/java-native-receipt.json) y [de contratos](product_supply/upgrades-native-receipt.json). La entrada de producto para los tres perfiles es la misma. Antes de ejecutarla hay que preparar los kits enlazados y asignar las rutas absolutas a las variables. `NATIVE_INPUTS` es el manifiesto de los 25 insumos del runtime. `NATIVE_KITS` es el manifiesto de directorios de los grupos seleccionados. `SOURCE_CHECKOUTS` contiene los checkouts directos, `OWNED_SOURCE_KIT` y `SCORE_KIT` los artefactos revisados, `GETH_HEADER` y `GOSEC_KIT` los controles históricos, y `PREPARED` los directorios `product/` y `supply/`. El [acta de las rutas y huellas del perfil contable](product_supply/consolidated-acceptance-accounting/first/run-inputs.json) registra los argumentos en su orden real.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.catalog_session \
    --review-queries --native-inputs "$NATIVE_INPUTS" --native-kits "$NATIVE_KITS" \
    --source-inventory --source-references "$SOURCE_CHECKOUTS" --embedded-root-manifests \
    --owned-source-kit "$OWNED_SOURCE_KIT" --score-kit "$SCORE_KIT" --fork-headers \
    --geth-header "$GETH_HEADER" --gosec-kit "$GOSEC_KIT" \
    --component-controls all "$PREPARED" > session.jsonl
```

Para el perfil de diez, el manifiesto incluye los ocho directorios del ejemplo más las claves `properties` y `canonical_header`. Las recetas están en [los controles contables](product_supply/contract-properties-native-build.json) y [el lector de encabezados](NATIVE_CAPABILITIES.md).


El perfil opcional de nueve grupos añade diez comprobaciones contables sobre tokens de prueba fijos. Seis comprueban saldo y oferta con reglas de Crytic y cuatro comprueban comisiones y transferencias con las simulaciones de Immunefi. En la misma invocación, añadir `--properties-native-kit "$NATIVE_KIT_ROOT/properties"`, o añadir `"properties": "../native-kits/properties"` al manifiesto de los ocho kits. Las rutas del manifiesto se resuelven desde su propio directorio. La [receta del kit contable](product_supply/contract-properties-native-build.json) enumera compiladores, fuentes, revisiones, hashes y rutas.

Dos ejecuciones aisladas del grupo contable produjeron los mismos resultados para sus diez pruebas y el mismo [registro de dos operaciones](product_supply/contract-properties-native-acceptance.json). La [aceptación conjunta de los nueve grupos](product_supply/consolidated-acceptance-accounting/acceptance.json) contiene las dos sesiones completas del producto.

Cada perfil exige exactamente sus grupos y contrasta los recibos de cada identidad. Las dos transcripciones del perfil de nueve grupos se comprueban con este comando.

```sh
python3.12 -B -m superhunter.tools.verify_review_115 --require-consolidated-accounting --check-controls --replay segunda.jsonl primera.jsonl
```

El perfil de diez grupos incluye una operación adicional de Ethernaut. Comprueba que el lector y el escritor RLP reproducen los 21 campos y los 649 bytes de un encabezado público archivado y de un segundo vector válido. En el segundo cambia una unidad de `gasUsed`. La interfaz reprodujo los dos recibos en checkouts separados. [Expediente del grupo](product_supply/acceptance-120/canonical-header-replay.json) · [Transcripción](product_supply/acceptance-120/canonical-header-transcript.json)

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

Los [200 checkouts directos](SOURCE_CHECKOUT.md) coinciden con sus revisiones de catálogo. La revisión de avisos alcanza los 200 proyectos. Los 200 almacenes directos conservan sus 141 rutas anidadas sin inicializar. En un espacio separado se verificó el contenido completo del único objeto LFS de Qdrant y una revisión de forge-std compartida por dos rutas. Quedan 139 de las 140 revisiones anidadas distintas por materializar en ese espacio. La revisión de redistribución y dependencias sigue abierta. [Acta de adquisición separada](product_supply/acceptance-120/staged-source-acquisition.json)

## Restaurar los insumos de inventario

El paquete del [perfil de producto](PRODUCT_REVIEW.md) conserva los doce archivos de CycloneDX y GUAC utilizados para las pruebas con insumos fijos. Se restauraron desde el commit público `e4248efc` en un directorio vacío. Las nueve entradas de CycloneDX y las tres de GUAC coincidieron byte por byte con las del productor. La regeneración independiente con metadatos distintos se conserva en el control de variación descrito arriba.

## Seguimiento de componentes pendientes

El [PR 119, commit 37a0d52](https://github.com/josuechavando350-png/nexus-quant-capital/commit/37a0d5261ae52ece080d18b294042931112f2861) reúne 15 grupos nativos y 17 dominios en su registro. Su aceptación de los 15 grupos en una misma sesión sigue pendiente en ese commit. El historial del PR conserva las operaciones y recibos de esa rama para su revisión independiente.

Las filas 106 y 107 corresponden a PHPStan y Psalm. La fuente fijada de PHPStan incluye su PHAR de 31.112.589 bytes. En el entorno revisado falta un intérprete PHP acreditado. Psalm también necesita extensiones y dependencias. Ambas filas siguen pendientes. [Inventario de disponibilidad local](product_supply/acceptance-120/typecheck-availability.json)
