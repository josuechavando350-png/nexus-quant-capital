# Controles defensivos de SUPERHUNTER

Los controles consumen entradas fijas de NQC o datos públicos fijados por Git. El índice de producto conserva la identidad y la revisión de cada participante, la operación y la huella del resultado que se observó. Una revisión del mismo código puede seleccionar un solo dominio. La sesión ampliada solicita todos los dominios publicados y vuelve a obtener los resultados.

## Avisos de componentes incorporados

El dominio `vendored-attributions` contrasta los paquetes enumerados en el aviso de sqlmap con sus directorios en la revisión fijada. Señala directorios declarados ausentes, raíces de terceros sin declarar y avisos locales que requieren revisión. Los 15 directorios declarados existen. Dos incluyen un aviso local cuyo texto concuerda con la familia indicada. Los otros 13 se apoyan en la declaración general. La compatibilidad para redistribución sigue abierta. [Contraste independiente y seis controles](product_supply/acceptance-120/vendored-notices-crosscheck.json)

El verificador `python3.12 -m superhunter.tools.verify_go_lock_integrity --help` coteja los gitlinks y los archivos Go de la raíz y de `v2` en los 200 checkouts. Usa exclusivamente los archivos disponibles en las cachés locales indicadas. La ejecución publicada comprobó 598 entradas de archivo y 598 de manifiesto en 34 repositorios. Otras 24.996 entradas quedaron sin contenido disponible para el cotejo. [Evidencia por repositorio y versión](product_supply/acceptance-120/go-lock-cache-integrity.json)

## Atribuciones de dependencias y lectura de informes

El dominio `dependency-attributions` usa el inventario de terceros de Stratus y el manifiesto Go de su módulo v2. Cruza las rutas de módulo distinguiendo mayúsculas, conserva la versión declarada de cada dependencia ausente y señala las etiquetas de licencia vacías o mal formadas. El identificador de una fila por sí solo no demuestra los derechos sobre el paquete. [Comprobación independiente](product_supply/acceptance-120/supply-attributions-crosscheck.json)

El dominio `report-accessibility` consume las traducciones de Nettacker para abrir el informe histórico que compara los PR 119 y 120. Conserva el nombre del archivo y la dirección de lectura. Cuando falta el mensaje o su marcador de ruta, indica que el texto presentado está en inglés. La CLI `python3.12 -B -m superhunter.product_report_accessibility --source-root RUTA` genera el HTML local. La opción `--format markdown` reproduce el índice publicado. [Índice en 24 idiomas](product_supply/acceptance-120/pr119-140-vs-157-localized.md)

## Tres comprobaciones sobre archivos existentes

| Dominio de `query-product` | Entrada y resultado que puede comprobarse |
|---|---|
| `event-format` | Seis registros de Heimdall-rs se contrastan con los eventos declarados en IERC20 e IERC721 de OpenZeppelin. Tres admiten una única distribución de campos indexados y los otros tres admiten tres distribuciones. El recibo conserva esa ambigüedad. |
| `policy-catalog` | Los catálogos estáticos de iamlive se cruzan con cinco políticas de prueba de CloudFox y sus resultados de Policy Sentry. El consumidor distingue las operaciones del SDK, las acciones IAM reconocidas, los comodines y las denegaciones explícitas. |
| `development-manifest` | La convención documentada de cargo-fuzz y `cargo metadata` sin red permiten cotejar las dependencias de desarrollo de prettyplease y syn. Un tercer caso, de Suricata, queda sin clasificar porque falta el manifiesto generado del paquete padre. |

Heimdall-rs, iamlive y cargo-fuzz aportan referencias consumidas. Los recibos enlazan sus revisiones concretas con los resultados de cada control. [Implementación de eventos](product_event_format.py) · [Comprobación de políticas](product_policy_catalog.py) · [Comprobación de manifiestos](product_development_manifest.py)

## Consultar un dominio

Con el bundle de producto y los checkouts ya preparados, este ejemplo devuelve las políticas Android observadas. Lee manifiestos y contrasta sus identificadores y tipos de recurso. Puede ejecutarse sin preparar los analizadores de otros dominios.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter query-product \
  --bundle "$work/product" --control-source-root "$root" \
  --component-controls android-policy component-controls
```

La respuesta identifica los dominios solicitados, los fallos y las observaciones nuevas. Una herramienta ausente o un resultado distinto del contrato deja su dominio bloqueado y permite terminar los dominios independientes. El programa emite las observaciones disponibles y devuelve código de salida 2 si algún dominio quedó bloqueado. Para acreditar la ejecución completa, el verificador exige que todos terminen y que coincidan la evidencia individual, la consulta compartida y la matriz.

## Reproducir la sesión de aceptación

Partir del [perfil completo del PR 117](OFFLINE_SOURCE_AND_GO.md) y de su [preparación nativa](SOURCE_ASSURANCE.md). Añadir `--component-controls all` a la invocación de `superhunter.tools.catalog_session --review-queries`. Las 221 respuestas incluyen la consulta compartida al final. Los analizadores de terceros consumen fuentes fijadas. Los binarios opcionales de caché pasan por la comprobación de su digest antes de usarse. Seleccionar la versión documentada de Node y el compilador Rust para el dominio de bytecode, y los kits específicos de los dominios seleccionados.

| Dominio | Operación y reproducción |
|---|---|
| `scoring` | [Detectar desacuerdos que se pierden al normalizar respuestas y medir el efecto de retirar una comprobación](EVALUATION_BATCH.md) |
| `changes` | Gosec localiza el uso de MD5 introducido como control en el comparador de Census. OpenHands reconstruye el código original en memoria y rechaza la reaplicación. Aider produce las diferencias de las líneas 4 y 25 y mini-SWE-agent reconcilia diagnóstico, fuentes y cambio. El producto comprueba ambos hashes y contrasta la clasificación CWE con FindSecBugs. Los cinco wheels para el lector de parches se obtienen del entorno DSPy ya fijado. |
| `evm` | [Contrastar límites de instrucciones y efectos en la pila de tres compilaciones propias](FIXED_EVM_LAYOUT.md) |
| `state-amounts` | [Detectar pérdida de precisión al representar cantidades históricas](CENSUS_AMOUNT_FORMATS.md) |
| `slot-format` | [Conservar las marcas de tiempo y los campos desconocidos al cambiar de representación](SLOT_TIME_FORMATS.md) |
| `diagnostics` | [Comprobar rangos de enteros, diagnósticos duplicados y definiciones de reglas](LANGUAGES_BATCH.md) |
| `static-contracts` | [Comprobar tipos, nulabilidad y orden de argumentos en la lectura de evidencia](STATIC_CONTRACTS.md) |
| `build-compatibility` | [Detectar cambios incompatibles de almacenamiento y de la interfaz de artefactos compilados](BUILD_COMPATIBILITY.md) |
| `object-format` | [Verificar las etiquetas que sobreviven en objetos compilados de NQC](FORMATS_BATCH.md) |
| `timeline` | [Conservar la identidad de la fuente, el orden y la precisión temporal de los eventos](infra_batch_journal.md) |
| `infrastructure` | [Contrastar reglas de aislamiento y decodificar capturas registradas](infra_batch.md) |
| `configuration` | [Interpretar permisos declarados y ofertas TLS en memoria](infra_batch_config.md) |
| `supply` | [Comprobar las dependencias de NQC y atribuir identificadores](TRUST_BATCH.md) |
| `android-policy` | [Contrastar políticas y tipos de recursos de manifiestos Android](ATTESTATIONS_BATCH.md) |
| `source-extracts` | [Localizar diagnósticos y comprobar la cobertura de una muestra](PASSIVE_SOURCE_BATCH.md) |
| `remediation` | [Verificar comparaciones de URL, contención de rutas y nombres admitidos](REMEDIATION_BATCH.md) |

En la consulta compartida, `digest_corroboration` vincula el diagnóstico real de gosec, la taxonomía de FindSecBugs y la fuente reconstruida por OpenHands. Un desacuerdo de línea, categoría, digest o controles limpios invalida el resultado. Los controles de permisos y configuración describen los archivos revisados. La prueba de representación de datos y los controles de mutaciones conocidas tienen ese alcance.

## Procedencia y licencias

La [verificación de materialización](SOURCE_MATERIALIZATION.md) conserva el estado de los 200 checkouts observados en un espacio de fuentes separado. La [matriz de producto](INTEGRATION_STATUS_200.md) usa las fuentes incorporadas a esta rama y las participaciones demostradas en la ejecución. En las fichas de extractos se encuentran los avisos, las atribuciones, los fragmentos consumidos y las revisiones. La autorización de una distribución comercial completa sigue pendiente.

## Verificación de los recibos

La [transcripción histórica de 99 identidades](product_supply/component-session-99.json) contiene 221 respuestas. Este comando comprueba las filas y ejecuta los controles de alteración sobre los bytes archivados. La [matriz única](INTEGRATION_STATUS_200.md) y el [expediente de consolidación](CONSOLIDATION.md) recogen los resultados posteriores.

```sh
python3.12 -B -m superhunter.tools.verify_review_115 \
    --archive --check-controls --require-complete-controls \
    --expect-sha256 81ab0b56f1970caeecc58ffc2fbf09197f340ede1b193b5d984c3db00593c9f5 \
    superhunter/product_supply/component-session-99.json
```
