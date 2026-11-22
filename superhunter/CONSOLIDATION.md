# SUPERHUNTER · Consolidación de las ramas de producto

Los PR [118](https://github.com/josuechavando350-png/nexus-quant-capital/pull/118) y [119](https://github.com/josuechavando350-png/nexus-quant-capital/pull/119) partieron de `672c31392929b8efbd6b3d5983c44e8560232add`. Las dos transcripciones históricas de 99 y 70 participantes compartían 63 identidades. Había 36 exclusivas de la primera y siete exclusivas de la segunda. El total histórico de esas dos ejecuciones era 106. [Archivo de 99](product_supply/component-session-99.json) · [Archivo de 70](product_supply/native-session-70.json)

La consolidación incorpora el estado local inmutable de Astra `1edb1699e6f6af382d7d65fdfd536c61989d0beb` y el checkpoint publicado `b87788962072578f9fb7ec5b584a06868639d89a`. Este último ya acredita 84 participaciones en una sesión; esa cifra no se suma a las 99 históricas. El checkpoint publicado 37a0d526 tiene 17 dominios de componentes y 15 grupos nativos. Su sesión de 222 respuestas fue aceptada: 139 identidades, 149 operaciones y 20 alteraciones rechazadas. [Expediente y transcripción](product_supply/consolidated-acceptance-139.json). La repetición desde otro checkout del mismo commit fue aceptada: las 222 respuestas son idénticas, byte por byte. El registro posterior incorpora grpcurl como grupo 16 con evidencia propia; su recibo no modifica el checkpoint anterior.

## Checkpoint vigente: 140 identidades

La ejecución desde el commit publicado `a183f60ed7229441a703a8f6ea9e180ff249abf3` añade grpcurl al mismo perfil. El verificador aceptó **140 identidades únicas, 150 operaciones, 222 respuestas y cero bloqueos**; rechazó sus 20 alteraciones de evidencia. Quedan 60 identidades pendientes. El [expediente](product_supply/consolidated-acceptance-140.json) declara una ejecución completa de 140 y conserva la pareja de 139 como evidencia anterior, sin trasladarle una repetición que no realizó.

## Ejecutar el perfil conjunto

Se utiliza la misma entrada de producto y un solo índice de 200 identidades. Una fila puede tener varias operaciones. `integration-matrix` y `integration-coverage` exponen cada operación mediante `session_operations`, con su rol, el campo que contiene el recibo y su SHA-256. El resultado original se obtiene consultando la identidad en la misma sesión. El selector acepta controles fijos locales. La única cuenta por identidad prioriza la ejecución cuando también hay un uso documental.

Preparar los [insumos históricos](OFFLINE_SOURCE_AND_GO.md), los [dominios de controles](DEFENSIVE_COMPONENTS.md), el [perfil de dieciséis grupos nativos](product_supply/native-kits-example.json) y el [códec de expedientes](EVIDENCE_CODEC.md). Los grupos java y upgrades requieren los kits descritos en sus [recibos Java](product_supply/java-native-receipt.json) y [de contratos](product_supply/upgrades-native-receipt.json). A la invocación de aceptación de 220 respuestas del PR 117, agregar estas opciones, antes del directorio preparado:

```sh
--component-controls all --native-kits "$NATIVE_KITS"
```

Las 222 respuestas incluyen `component-controls` y `native-capabilities`. Para evaluar la transcripción JSONL completa en un proceso separado:

```sh
python3.12 -B -m superhunter.tools.verify_review_115 --require-consolidated --check-controls session.jsonl
```

Los artefactos emitidos por un productor bloqueado carecen de crédito. Un reintento fallido o el cambio de selección retiran los recibos de componentes anteriores, conservando los productores independientes. La reproducción requiere los compiladores, binarios y conjuntos de dependencias fijados en cada manifiesto. Dos checkouts en una máquina permiten reproducir el resultado en ese host. La evaluación ciega y el rendimiento de descubrimiento en otros entornos siguen pendientes.

## Resolución de los cambios compartidos

| Rutas del comentario de coordinación | Comportamiento conservado |
|---|---|
| `product_batches.py`, `product_review.py`, `tools/catalog_session.py` | Un índice y un punto de entrada. Se pueden seleccionar dominios defensivos y grupos nativos, y se conserva cada operación en la fila de su identidad. |
| `product_sources.py`, `product_source_audit.py` | El manifiesto incluye 200 gitlinks. Se conservan la comprobación de bytes del directorio de trabajo, el orden de resultados, el inventario anterior y su huella. |
| `product_licenses.py`, `tests/test_product_license_session.py`, `tests/test_product_inventory_parallel.py` | El contenido de estas tres rutas ya coincidía entre las ramas. |
| `tests/test_product_source_parallel.py` | Se amplió el fixture de 153 a 200 y se conservaron los controles de índices, modos de archivo, enlaces y normalización de Git. |
| `quality.py`, `quality_worker.py` | Se registraron productores, datos y pruebas de ambas ramas. El límite explícito del inventario pasa de 500 a 768 archivos para cubrir los más de 640 de la consolidación. Los 19 módulos nuevos conservan las asignaciones anteriores de pruebas. |
| `tools/verify_review_115.py` | Verificación desde las fuentes fijadas, los resultados individuales y el índice completo. Los perfiles históricos conservan sus contratos originales. |
| `SOURCE_ASSURANCE.md`, `SOURCE_CHECKOUT.md` | Quedaron versionados el expediente de 153 y el de los 200. Las optimizaciones ya portadas del PR 116 se conservan una sola vez. |

Los [200 checkouts directos](SOURCE_CHECKOUT.md) coinciden con sus revisiones de catálogo. La revisión de avisos alcanza los 200 proyectos. Quedan pendientes la materialización de 141 gitlinks anidados y un objeto Git LFS, y la revisión de obligaciones de distribución del producto y sus dependencias.
