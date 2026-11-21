# Procedencia offline y verificación del digest de Census

El producto incluye en [el archivo de evidencia](product_supply/offline-remote-inputs.json) los 47 objetos Git de tipo commit y los 34 manifiestos declarativos raíz que se verificaron en el PR 115. La consulta `portable-source-proof` recalcula los identificadores Git, enlaza cada commit con su árbol y cada manifiesto con el blob declarado. Después procesa los bytes mediante la misma función que usa el perfil con archivos externos. El verificador limita la descompresión y rechaza truncamientos o datos adicionales. La preparación del producto puede usar `--embedded-root-manifests` sin el directorio de descargas de los 34 manifiestos. El archivo conserva objetos y declaraciones de procedencia; su incorporación aporta cero checkouts completos y cero participaciones funcionales por sí sola.

`go-header-digest` conecta el resultado del comparador Geth con el análisis estático de su fuente original de NQC. Gosec, fijado en `244f1f6f4d1d0d14f89e79a73dab1219eabb5228`, analiza el archivo original y dos variantes locales que cambian únicamente la función de digest y su importación. G401 señala el uso de MD5, con el identificador CWE-328. El verificador coteja la línea 25, columna 12, los bytes de la expresión y el recuento de tres archivos procesados. La fuente original SHA-256 y la variante SHA-512/256 pasan. El control se hace sobre texto y el compilador resuelve sus tipos. El comparador nunca ejecuta la variante MD5.

## Preparación

Se requiere el checkout de las 153 fuentes y Linux x86-64. Los pasos de preparación descargan la distribución pública de Go 1.27.3 y los módulos declarados. Los analizadores y módulos de prueba se ejecutan después con la red deshabilitada. Desde la raíz de NQC y en un directorio externo nuevo:

```sh
set -eu
root=$(pwd)
work=$(mktemp -d)
kit="$work/kit"
mkdir -p "$kit" "$work/source" "$work/toolchain" "$work/run/own" "$work/run/geth"
curl -fLsS https://go.dev/dl/go1.27.3.linux-amd64.tar.gz -o "$kit/go.tgz"
echo "65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40  $kit/go.tgz" | sha256sum -c -
tar -xzf "$kit/go.tgz" -C "$work/toolchain"
export PATH="$work/toolchain/go/bin:$PATH"
export GOROOT="$work/toolchain/go" GOENV=off GOTOOLCHAIN=local GOWORK=off CGO_ENABLED=0 GOAMD64=v1
export GOMODCACHE="$work/build-modules" GOCACHE="$work/build-cache"
git -C "$root/upstream/105-gosec" archive 244f1f6f4d1d0d14f89e79a73dab1219eabb5228 | tar -x -C "$work/source"
cd "$work/source"
go list -mod=readonly -deps ./cmd/gosec > "$work/analyzer-packages"
unshare --user --map-current-user --net env GOPROXY=off GOSUMDB=off \
  go build -p 2 -mod=readonly -buildvcs=false -trimpath -ldflags=-buildid= -o "$kit/gosec" ./cmd/gosec
echo "c627296e4e69c8dcf57abd44419fb51d9eb0a4fe3d32e3b03c8201e9809fcc47  $kit/gosec" | sha256sum -c -
git -C "$root/upstream/037-go-ethereum" archive 2b7829ea6aed9a95a3fd793cca46731202c6c310 | tar -x -C "$work/run/geth"
cp "$root/superhunter/product_supply/header-digest/go-mod.txt" "$work/run/go.mod"
cp "$root/superhunter/product_supply/header-digest/go-sum.txt" "$work/run/go.sum"
cp "$root/superhunter/product_supply/geth-header-main.txt" "$work/run/own/main.go"
cd "$work/run"
GOMODCACHE="$work/runtime-modules" go list -tags=purego -mod=readonly -deps ./own > "$work/runtime-packages"
cp -R "$work/runtime-modules/cache/download" "$kit/proxy"
cd "$root"
```

En la [invocación de aceptación](SOURCE_ASSURANCE.md#reproducir-la-aceptación-del-pr-115), reemplazar `--root-manifests "$work/manifests"` por `--embedded-root-manifests` y añadir `--gosec-kit "$kit"`. `--review-queries` emite entonces 220 respuestas. El verificador de transcripciones coteja también los 47 recibos con el informe portable y la salida de Gosec con su recibo individual. Para reconstruir el archivo de los 47 objetos a partir de los insumos verificados:

```sh
python3.12 -B -m superhunter.tools.pack_remote_inputs "$work/git-metadata" "$work/manifests" > "$work/offline.json"
cmp "$work/offline.json" superhunter/product_supply/offline-remote-inputs.json
```

## Verificación del expediente

El [registro de aceptación](product_supply/review-117.json) conserva los hashes de la ejecución en el commit publicado y de la ejecución con los cuatro expedientes reconstruidos, así como los controles y los resultados que dependen de la procedencia de esos expedientes. El [archivo de las 220 respuestas](product_supply/review-117-session.json) se comprueba sin instalar gosec, los módulos Go ni el resto del entorno nativo.

```sh
digest=$(python3.12 -c 'import json; print(json.load(open("superhunter/product_supply/review-117.json"))["canonical_session"]["transcript_sha256"])')
python3.12 -B -m superhunter.tools.verify_review_115 --archive --check-controls --expect-sha256 "$digest" \
  superhunter/product_supply/review-117-session.json
```
