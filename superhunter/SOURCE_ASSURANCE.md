# Verificación defensiva de fuentes en NQC

El punto de partida es el commit de producto `ae02690627443df08b8eedb9d63a7a30cbda6c0e`. Los primeros 153 submódulos y sus revisiones se conservan. En el lote de los 47 restantes se verificaron todos los objetos de árbol raíz y se consumieron 34 manifiestos desde sus blobs. Dos proyectos aportan además extractos de fuente con licencia y un consumidor ejecutado. Las consultas `root-declarations` y `owned-source-checks` comparten las identidades del producto. [Árboles y declaraciones](REMOTE_ROOTS.md) · [Origen de los extractos](product_supply/source-excerpts/ORIGINS.md)

| Proyecto | Entrada y consumidor | Control comprobado |
|---|---|---|
| PyCQA/Bandit | El analizador B506 de Bandit 1.9.4 procesa el lector de políticas YAML de NQC. Los 69 archivos Python de la distribución coinciden con los blobs del submódulo. | `safe_load` y `SafeLoader` explícito se aceptan. La copia que usa `load` sin seleccionar cargador produce un diagnóstico en la línea 127. Sólo se analiza la sintaxis. |
| SmartBugs | La función original `result_region` recibe las coordenadas de Bandit y las incorpora a un resultado SARIF 2.1.0 que devuelve la consulta. | La región empieza en la columna 20 y termina en la 33. Un lector independiente coteja la línea con el AST de Python y los caracteres exactos en la fuente. |
| OpenSSF malicious-packages | Un árbol fijado de 12,065 nombres de PyPI se contrasta con los 38 nombres y 39 pares nombre/versión declarados por NQC. | Cero coincidencias de nombre en ese conjunto y revisión. Un registro OSV publicado distingue una versión que figura y otra que no figura. El proceso lee metadatos y no adquiere paquetes descritos en los avisos. |
| Crytic building-secure-contracts | Dos cláusulas originales sobre tipos de retorno se combinan con las declaraciones de NQC, el AST de solc y la interfaz IERC20 de OpenZeppelin. | Las tres declaraciones se ajustan a las cláusulas. Se detectan exactamente dos diferencias al alterar `decimals` y `transfer` en memoria. |
| Stanford DSPy e Inspect AI | Cada framework puntúa las predicciones de un proceso sin acceso a las etiquetas. El clasificador recibe 96 variantes fijadas del encabezado de Census. Los verificadores comparan caso por caso las etiquetas de campos contra una referencia independiente. | Ambos registraron 96/96 aciertos. Al omitir la validación de `extraData`, ambos registraron 86/96 y los mismos diez errores. La prueba mide representación de datos y sensibilidad al control eliminado. |

Los 47 proyectos siguen sin checkout completo. Entre ellos, SmartBugs aporta código de biblioteca y Crytic aporta una referencia documental. Los otros 45 mantienen alcance de metadatos en este lote. Las herramientas de intrusión y los laboratorios de explotación permanecen fuera del flujo autónomo. El registro de una dependencia o un aviso por sí solo no acredita una herramienta. La revisión comercial integral y la evaluación externa ciega de descubrimiento siguen pendientes.

## Reproducir

Usar Linux x86-64 y CPython 3.12. Partir de un checkout con los 153 submódulos, una [sesión estándar preparada y el comparador de Geth reproducible](SOURCE_AUDIT.md). Los comandos de preparación requieren rutas nuevas. Los procedimientos comprueban los objetos Git y los hashes de los wheels antes de usarlos.

```sh
python3.12 -B -m superhunter.tools.fetch_root_manifests "$work/manifests"
python3.12 -B -m superhunter.tools.prepare_owned_source_checks --scorers "$work/owned"
python3.12 -B -m superhunter.tools.catalog_session --source-inventory --source-references "$root" \
  --root-manifests "$work/manifests" --owned-source-kit "$work/owned" --score-kit "$work/owned" --fork-headers \
  --geth-header "$work/geth-header" "$work/product" fork-headers root-declarations owned-source-checks score-comparison integration-matrix
```

La matriz Markdown publicada corresponde al perfil ampliado de 58 participaciones. El perfil estándar reproduce 28. Para regenerar la versión publicada, preparar también los insumos nativos descritos más abajo. El renderizador abre la sesión, exige los recibos y devuelve un error si un productor falla. La salida de la ejecución se puede cotejar antes de reemplazar la matriz publicada.

```sh
python3.12 -B -m superhunter.tools.render_product_matrix --native-inputs "$work/native-inputs.json" --source-inventory --source-references "$root" \
  --root-manifests "$work/manifests" --owned-source-kit "$work/owned" --score-kit "$work/owned" --fork-headers \
  --geth-header "$work/geth-header" "$work/product" > "$work/matrix.md"
cmp "$work/matrix.md" superhunter/INTEGRATION_STATUS_200.md
```

## Árboles completos y avisos de los entornos

Para los 47 proyectos con checkout completo pendiente, el recorrido de todos los árboles cuenta 5,534 árboles distintos sumados por repositorio, 29,043 rutas de blobs, 26 gitlinks anidados y 211 rutas con nombres de manifiestos o archivos de fijación reconocidos. Los 13 archivos `.gitattributes` examinados contienen cero reglas literales `filter=lfs`. Los gitlinks anidados quedan identificados por el árbol del padre. El inventario no materializa su contenido ni certifica que todo blob sea ajeno a LFS. [Detalle por identidad](product_supply/remote-tree-inventory.json)

```sh
python3.12 -B -m superhunter.tools.audit_tree_metadata --fetch "$work/git-metadata" "$work/attrs" > "$work/trees.json"
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.audit_tree_metadata \
  "$work/git-metadata" "$work/attrs" > "$work/replay.json"
cmp "$work/trees.json" "$work/replay.json"
cmp "$work/replay.json" superhunter/product_supply/remote-tree-inventory.json
```

Tras una interrupción, `--resume` conserva las filas adquiridas y reintenta las pendientes. La consulta `recursive-source-trees` devuelve el resumen y cada repositorio conserva su recibo individual. La consulta `assurance-wheel-notices` reconstruye 122 avisos de 90 distribuciones fijadas con SHA-256. Hay 7 wheels de Bandit, 26 de DSPy y 80 de Inspect AI, con dependencias compartidas. De las 90 distribuciones, 45 declaran una expresión SPDX en sus metadatos. La consulta conserva por separado los clasificadores, declaraciones y hashes del texto de cada aviso. El permiso de redistribución para el producto comercial continúa pendiente de revisión.

## Interpretación de encabezados según la red

La consulta `fork-headers` conecta el calendario de Besu para Ethereum mainnet con el encabezado histórico 25,437,474 de NQC. Reth y Besu aportan sus calendarios de Hoodi y el producto contrasta el último segundo anterior a la activación de Prague con el primero en que está vigente. El alcance compara los campos incorporados desde Shanghai hasta Prague.

El caso externo es un bloque fijo del corpus de ethereum/hive para la era Cancun. El lector coteja el encabezado, el payload y el registro de selección de cabeza. Con la forma de encabezado seleccionada, EthereumJS, ethers y viem reproducen el hash de Hive y los 573 bytes de RLP. Se detectan la retirada de `requestsHash` de la muestra Prague, su adición prematura en Cancun y un cambio de `gasUsed`. Estas tres participaciones se acreditan como uso de referencias y datos. La validación usa archivos fijados y funciona sin nodos ni conexiones RPC.

## Recibos, controles y perfiles de ejecución

El perfil estándar usa las opciones de los ejemplos anteriores. El perfil ampliado añade `--native-inputs "$work/native-inputs.json"` a la misma invocación. Preparar las 25 entradas de [la plantilla](product_supply/native-inputs-example.json) siguiendo las versiones y los hashes de [las herramientas nativas](PRODUCT_REVIEW.md). El valor de cada entrada es una ruta local, absoluta o relativa al JSON. Los expedientes de CycloneDX y GUAC se pueden regenerar mediante `review-product-cdxgen` y `review-product-guac`. Cada productor valida su propia entrada antes de usarla. La plantilla sólo admite las 25 entradas especificadas.

Se recuperaron los bytes de la [sesión histórica de 205 respuestas](product_supply/session-d94b58f.txt). El producto coteja los 38 recibos contra la línea original, identidad, campo de salida, función y SHA-256. La cobertura nativa también comprueba el contrato y los identificadores del productor. Los recibos nuevos de este PR requieren salidas específicas verificadas sobre entradas fijas. La sesión estándar puede conservar crédito histórico aunque el productor no haya participado en esa ejecución.

La consulta de PMD valida los tokens extraídos de cada posición contra los avisos de origen. Si una coincidencia candidata agrupa secuencias distintas, devuelve las ubicaciones y sus huellas con estado `REFUTED`. Esas ubicaciones quedan excluidas de las coincidencias aceptadas. Un resultado sintácticamente inválido, un conteo incorrecto o una ubicación fuera de rango siguen bloqueando la operación. Scorecard coteja los gitlinks con las revisiones autorizadas antes de examinar los archivos propios de NQC.

En los procesos de DSPy e Inspect AI se aplican límites de CPU, espacio de direcciones, tamaño de archivo y descriptores. El clasificador recibe sólo casos; el evaluador conserva las etiquetas hasta comparar las predicciones. El siguiente comando reproduce ocho cohortes de 96 casos con semillas derivadas del commit de la cuarta entrega. Opcionalmente, `--timing ARCHIVO_NUEVO` guarda el tiempo observado. La exactitud en esta tarea mide el reconocimiento de valores representables por tipo de campo. No se ha ejecutado una evaluación externa de descubrimiento original.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.replay_review_115 "$root" > "$work/holdout.json"
cmp "$work/holdout.json" superhunter/product_supply/review-115-holdout.json
```

## Reproducir la aceptación del PR 115

Con todos los insumos preparados, esta invocación abre un solo índice y entrega primero las 200 identidades y después las 18 consultas transversales, en orden estable.

```sh
mkdir -p "$work/tmp"
TMPDIR="$work/tmp" python3.12 -B -m superhunter.tools.catalog_session \
  --review-queries --native-inputs "$work/native-inputs.json" \
  --source-inventory --source-references "$root" --root-manifests "$work/manifests" \
  --owned-source-kit "$work/owned" --score-kit "$work/owned" --fork-headers \
  --geth-header "$work/geth-header" "$work/product" > "$work/session.jsonl"
```

En el corpus combinado de 256 avisos, la verificación de PMD aceptó 817 grupos con 4,043 ubicaciones. Refutó un grupo adicional de 87 tokens. Los primeros 81 tokens coincidían y los siguientes divergían. El informe conserva el expediente del grupo rechazado. La clasificación de 768 encabezados generados dio 384 verdaderos positivos, 384 verdaderos negativos y cero errores en esta tarea. Se repitió sin acceso a red y conservó las mismas predicciones. [Datos completos de cada cohorte](product_supply/review-115-holdout.json)

El resolver de pip recibe un directorio temporal con los wheels autorizados y solicita únicamente la distribución raíz de cada entorno. Sin red, el conjunto transitivo predeterminado en CPython 3.12/Linux x86-64 coincide con los 7, 26 y 80 wheels fijados. Cada versión y hash se verifican contra la salida del resolver. Retirar `stevedore` del entorno de prueba hace que Bandit falle por esa dependencia. `assurance-wheel-notices` publica los campos `Requires-Dist` y el cierre observado para cada raíz. Las opciones adicionales de instalación quedan pendientes de evaluación.

El verificador independiente puede cotejar las 218 respuestas, incluidas las identidades, avisos, funciones, totales y hashes de los recibos individuales. Si se dispone del digest publicado de esa ejecución concreta, usar `--expect-sha256 DIGEST` para comprobar también todos sus bytes.

```sh
python3.12 -B -m superhunter.tools.verify_review_115 "$work/session.jsonl"
```
