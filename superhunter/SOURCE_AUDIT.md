# Reproducir la auditoría de fuentes y las comparaciones del producto

El PR 114 parte del commit de producto `929486be4132aac626bca92ac3fca0a6669c117d`. El documento de estado histórico se consultó en [main, en el commit observado](https://github.com/josuechavando350-png/nexus-quant-capital/blob/384e7deb5020e3e29715e05c049ac5e97dcd7706/SUPERHUNTER_STATUS.md). El catálogo del PR 110 y el código de producto del PR 111 están en ramas diferentes. Los PR 112 y 113 se habían integrado en la rama del PR 111. [Catálogo](https://github.com/josuechavando350-png/nexus-quant-capital/pull/110) · [Rama de producto](https://github.com/josuechavando350-png/nexus-quant-capital/pull/111) · [Evidencia anterior](https://github.com/josuechavando350-png/nexus-quant-capital/pull/112) · [Primeros 100](https://github.com/josuechavando350-png/nexus-quant-capital/pull/113)

## Reproducir el inventario

Se requieren Git, Linux, CPython 3.12, util-linux con espacios de nombres de usuario y red, y la distribución oficial de ScanCode Toolkit 32.5.0 para Linux/Python 3.12. Reservar fuera del checkout un directorio de trabajo y usar una carpeta nueva para los avisos. Las descargas de preparación consultan únicamente los orígenes públicos. La comparación posterior funciona sin acceso a Internet.

```sh
set -eu
work=$(mktemp -d)
export GIT_LFS_SKIP_SMUDGE=1
git -c core.hooksPath=/dev/null submodule update --init --depth 1 --jobs 8
python3.12 -B -m superhunter product-sources --require-checkout > "$work/checkouts.json"
python3.12 -B -m superhunter.tools.check_catalog_origins --remote-trees
python3.12 -B -m superhunter.tools.fetch_upstream_notices "$work/notices"
curl -fLsS -o "$work/scancode.tar.gz" https://github.com/aboutcode-org/scancode-toolkit/releases/download/v32.5.0/scancode-toolkit-v32.5.0_py3.12-linux.tar.gz
unshare --user --map-current-user --net python3.12 -B -m superhunter product-sources --inventory \
  --notice-bundle "$work/notices" --scancode-release "$work/scancode.tar.gz" > "$work/inventory.json"
cmp "$work/inventory.json" superhunter/product_supply/source-inventory.json
git submodule foreach --quiet 'git --no-replace-objects fsck --full --no-progress --no-dangling --no-reflogs'
```

La consulta de los 47 commits usa la API pública de GitHub y está sujeta a su cuota. La verificación offline lee la [captura de commit y árbol](product_supply/catalog-commit-trees.json). Para las 153 fuentes incorporadas, el programa compara el índice, el commit, el árbol, las rutas y los archivos rastreados. Enumera gitlinks anidados, archivos de manifiesto reconocidos por su nombre y punteros LFS v1 presentes en blobs pequeños. Los 115 gitlinks pertenecen a 32 repositorios. El único puntero LFS se encontró en Qdrant y declara un objeto de 1,752,948 bytes. En 140 repositorios se encontraron 6,504 archivos con nombres de manifiesto o bloqueo reconocidos. Estos conteos incluyen archivos de ejemplos y pruebas. La clausura de dependencias transitivas, el contenido de los repositorios anidados, los objetos externos de LFS y la firma de autor de los commits siguen fuera del alcance verificado.

## Licencias

La sesión descargó de nuevo los avisos por su SHA de commit y cotejó tamaño, SHA-256 y objeto Git. ScanCode leyó los 144 textos distintos de los 200 avisos seleccionados. Encontró alguna expresión en 199 avisos directos. El archivo `LICENSE` de viem contiene el enlace simbólico `src/LICENSE`. El auditor resolvió ese enlace dentro del árbol Git, verificó el segundo blob y obtuvo MIT. La evidencia por ID conserva las expresiones, reglas y números de línea, incluidos los resultados mixtos o desconocidos.

En dirsearch el aviso seleccionado es una línea de `pyproject.toml`. En RustSec y EthereumJS se seleccionó la licencia de un componente. En Geth aparecen tanto `COPYING` como `COPYING.LESSER`. Para el uso comercial hay que determinar qué archivos y dependencias se copian, enlazan, modifican, distribuyen o sirven, y qué alternativas o excepciones se aplican. Ningún expediente de este lote cierra esa evaluación global. [Observaciones por repositorio](product_supply/source-inventory.json)

| Texto observado | Cuestión a documentar al distribuir o servir el producto |
|---|---|
| GPLv2 / GPLv3 | Para el código objeto cubierto, documentar la vía elegida de entrega u ofrecimiento del código fuente correspondiente y conservar los avisos aplicables. [GPLv2, §3](https://opensource.org/license/gpl-2.0) · [GPLv3, §§4–6](https://opensource.org/license/gpl-3.0) |
| AGPLv3 | Además de la distribución, analizar la interacción remota con una versión modificada y el ofrecimiento de su código fuente a esos usuarios. [AGPLv3, §13](https://opensource.org/license/agpl-3.0) |
| Apache-2.0 | Al redistribuir, revisar la copia de la licencia, las atribuciones, las indicaciones de cambios y los avisos NOTICE aplicables. [Apache-2.0, §4](https://www.apache.org/licenses/LICENSE-2.0) |
| Expresión compuesta, licencia de componente o referencia desconocida | Revisar cada archivo relevante, su titular, excepciones, avisos y la modalidad concreta de uso. La expresión detectada en un documento conserva su alcance documental. |

## Compilar el comparador fijo de Geth

Se usó Linux x86-64 y Go 1.27.3. El archivo oficial `go1.27.3.linux-amd64.tar.gz` utilizado tuvo SHA-256 `65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40`. Dos compilaciones, una desde un archivo Git limpio, produjeron SHA-256 `af8353f39c60f5038cfa0c894ebc9566ad8ea958575d83a1108e00b23089bec7`. El ejecutable se construye localmente y el producto comprueba su digest antes de invocarlo. El ejemplo supone que `go` es el binario de esa distribución. [Código del comparador](product_supply/geth-header-main.txt)

```sh
root=$(pwd)
mkdir -p "$work/geth" "$work/helper"
git -C upstream/037-go-ethereum archive 2b7829ea6aed9a95a3fd793cca46731202c6c310 | tar -x -C "$work/geth"
cp superhunter/product_supply/geth-header-main.txt "$work/helper/main.go"
export GOENV=off GOWORK=off GOTOOLCHAIN=local CGO_ENABLED=0 GOAMD64=v1
export GOMODCACHE="$work/go-modcache"
cd "$work/geth"
go list -mod=readonly -deps "$work/helper/main.go" > "$work/geth-packages.txt"
unshare --user --map-current-user --net env GOPROXY=off GOSUMDB=off \
  go build -mod=readonly -buildvcs=false -trimpath -ldflags=-buildid= -o "$work/geth-header" "$work/helper/main.go"
cd "$root"
sha256sum "$work/geth-header"
```

## Reproducir las 211 respuestas

Preparar el entorno de [la sesión de inventario](CATALOG_SESSION.md) en una carpeta nueva. La preparación descarga las herramientas fijadas con digest y genera los expedientes locales. Las consultas se ejecutan sin red externa.

```sh
python3.12 -B -m superhunter.tools.catalog_session --prepare "$work/product" upstream-notices
python3.12 - <<'PY' > "$work/keys"
import json
from pathlib import Path
for row in json.loads(Path('superhunter/repositories_200.json').read_bytes())['entries']:
    print(row['repository'])
for key in ('batch:1', 'batch:2', 'upstream-notices', 'solidity-headers', 'notice:redistribution',
            'notice-overlaps:upstream-002-license.txt', 'census-header', 'integration-coverage',
            'geth-census', 'source-references', 'source-inventory'):
    print(key)
PY
python3.12 -B -m superhunter.tools.catalog_session --source-inventory --source-references "$root" \
  --geth-header "$work/geth-header" "$work/product" < "$work/keys" > "$work/answers.jsonl"
sha256sum "$work/answers.jsonl"
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.evaluate_payload_types "$root"
```

La sesión compara los 649 bytes RLP del encabezado de Census y un control que cambia `gasUsed`, valida 15 campos representables del payload frente al esquema Deneb y compara las seis firmas de IERC20 con las declaraciones de la interfaz histórica de NQC. El control Solidity cambia únicamente el tipo de retorno de `balanceOf`. La ejecución termina en el análisis sintáctico. El cuerpo del bloque, el comportamiento de un contrato desplegado y la validación de una cadena viva quedan pendientes de otros criterios. [Comparador de Geth](product_census_header.py) · [Comparadores de tipos e interfaces](product_source_references.py)

El clasificador de campos quedó fijado por SHA antes de registrar la semilla de 96 casos. El proceso de predicción recibió sólo los campos y los ID opacos. Un proceso distinto comparó la salida con las etiquetas. Los casos cubren formas válidas y alteraciones de longitud, representación o rango. La semilla y las etiquetas son reconstruibles, y ambos procesos comparten autor y host. Una evaluación externa con custodia independiente y una medición de descubrimiento de vulnerabilidades originales siguen pendientes. [Evaluador y semilla](tools/evaluate_payload_types.py) · [Pruebas de integridad y falsos positivos](tests/test_product_source_audit.py)

## Punto de reanudación

La consulta por nombre devuelve el propósito original, la naturaleza principal elegida para integración, el commit, el tipo de evidencia de fuente, la observación de licencia y, cuando existe, la evidencia funcional. Para reanudar, partir de la cabeza del PR 114 o de su merge en la rama del PR 111, reproducir la transcripción y consultar `integration-coverage`. Los 151 ID con estado pendiente carecen de recibo funcional acumulado. Un siguiente lote defensivo reproducible puede cerrar un manifiesto real de dependencias o verificar otro contrato de datos propio con controles positivos y negativos. Las capacidades de intrusión o reproducción ofensiva autónoma permanecen fuera de este flujo. [Matriz de las 200 identidades](INTEGRATION_STATUS_200.md)


### Suites ejecutadas

Los 12 módulos Python se ejecutaron con `python -B -m unittest` y el prefijo `superhunter.tests.`. Se usó Python del sistema con sellos de memfd y el libseccomp con el digest que exige el producto en un espacio de montaje y red privado. Los módulos fueron `test_product_source_audit`, `test_repository_boundary`, `test_product_catalog_session`, `test_product_review`, `test_product_supply`, `test_quality`, `test_quality_entrypoint`, `test_quality_cache`, `test_quality_process`, `test_quality_row_index`, `test_owned_sealed_input` y `test_owned_sealed_worker`. Para Rust se prepararon las dependencias de `nqc-census/Cargo.lock` con `cargo fetch --locked` y se ejecutó `cargo test --locked --offline --workspace` desde `nqc-census` con la red deshabilitada y el directorio de salida fuera del checkout.

[Recibo de aceptación, controles y mediciones](product_supply/review-114.json)
