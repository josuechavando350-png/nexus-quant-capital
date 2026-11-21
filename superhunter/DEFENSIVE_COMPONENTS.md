# Controles defensivos de SUPERHUNTER

Los controles consumen entradas fijas de NQC o datos públicos fijados por Git. El índice de producto conserva la identidad y la revisión de cada participante, la operación y la huella del resultado que se observó. Una revisión del mismo código puede seleccionar un solo dominio. La sesión ampliada solicita todos los dominios publicados y vuelve a obtener los resultados.

## Consultar un dominio

Con el bundle de producto y los checkouts ya preparados, este ejemplo devuelve las políticas Android observadas. Lee manifiestos y contrasta sus identificadores y tipos de recurso. Puede ejecutarse sin preparar los analizadores de otros dominios.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter query-product \
  --bundle "$work/product" --control-source-root "$root" \
  --component-controls android-policy component-controls
```

La respuesta identifica los dominios solicitados, los fallos y las observaciones nuevas. Una herramienta ausente o un resultado distinto del contrato deja su dominio bloqueado y permite terminar los dominios independientes. Para acreditar la ejecución completa, el verificador exige que todos terminen y que coincidan la evidencia individual, la consulta compartida y la matriz.

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
