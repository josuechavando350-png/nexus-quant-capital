# Revisión de dependencias de NQC y SuperHunter

La auditoría de los 200 IDs y tres participaciones funcionales adicionales se detallan en [la matriz verificable](INTEGRATION_STATUS_200.md) y [la receta de reproducción](SOURCE_AUDIT.md).

Desde la CLI de SuperHunter se puede consultar el catálogo de 200 proyectos, el grafo de dependencias de Census y los conflictos entre los seis perfiles Python de SuperHunter. El catálogo procede del [PR 110](https://github.com/josuechavando350-png/nexus-quant-capital/pull/110), commit `474846b11ea41f9d9f41c4aa6d7eda0cbf18d2f6`. La copia conserva exactamente los bytes públicos de ese JSON. La consulta conserva los identificadores históricos de los siete proyectos que aparecen también en el portafolio de 50.

La revisión básica utiliza dos productores. Syft extrae paquetes y relaciones de los manifiestos copiados a un directorio temporal. cvc5 comprueba si los perfiles con versiones incompatibles pueden compartir un número dado de entornos. Las opciones descritas más abajo añaden las observaciones de proveedores, SBOM, relaciones y licencias a la misma consulta. Pertenecer al catálogo no acredita una ejecución.

La [sesión conjunta de los 200 repositorios](CATALOG_SESSION.md) reúne los avisos de origen, los metadatos de Solidity y el archivo de prueba del encabezado de Census. La clave `integration-coverage` muestra el avance con su procedencia para cada ID.

NQC fija el código fuente de 153 de los 200 repositorios mediante submódulos Git. [Inventario de los 153, las 47 referencias de catálogo y comprobación del checkout](SOURCE_CHECKOUT.md).

## Reproducir

Usar Python 3.11 o posterior. Para producir evidencia se requieren Linux x86-64 y los dos ejecutables de las distribuciones indicadas. La CLI comprueba el SHA-256 de la copia privada que ejecuta. El verificador y el lector funcionan con la biblioteca estándar de Python. Los datos de entrada son los archivos del checkout local.

| Proyecto | Distribución probada | Commit de origen | SHA-256 del archivo de distribución |
|---|---|---|---|
| Syft 1.38.2 | [syft_1.38.2_linux_amd64.tar.gz](https://github.com/anchore/syft/releases/download/v1.38.2/syft_1.38.2_linux_amd64.tar.gz) | `bfe63f83dbaea88e22a5cfcd7d704c034c953730` | `6aa9a7b9e53c0f06e2d79fb24641cc1c856bb41702c282a577691f54bad94996` |
| cvc5 1.3.1 | [cvc5-Linux-x86_64-static.zip](https://github.com/cvc5/cvc5/releases/download/cvc5-1.3.1/cvc5-Linux-x86_64-static.zip) | `ea1b484fa54bfe56c0f8b3ac90a6e3e2f46441e7` | `1a1cda20d2df4938fa4944a69f33ddc9172e319ece0eed0aa09c4d7abede3ed1` |

Desde la raíz del checkout, sustituir las dos rutas por los binarios extraídos. El directorio de salida debe ser nuevo y externo al repositorio.

```bash
evidence_dir="$(mktemp -d)/evidence"
python3 -m superhunter review-product --syft /ruta/syft --cvc5 /ruta/cvc5 --out "$evidence_dir"
python3 -m superhunter verify-product --bundle "$evidence_dir"
python3 -m superhunter query-product --bundle "$evidence_dir" cvc5/cvc5 cryptography sha2
python3 -m superhunter.tests.benchmark_product_queries --bundle "$evidence_dir"
```

Para varias consultas, arrancar `query-product --bundle "$evidence_dir"` una vez y enviar un nombre exacto por línea por la entrada estándar. Devuelve un objeto JSON por línea o `null` si el nombre está ausente. Esa sesión consulta una instantánea verificada al arrancar. Para ver un cambio de los archivos fuente, generar y abrir un expediente nuevo.

## Qué demuestra

El inventario vincula cada observación con el archivo que fija su versión. El analizador de TOML y el lector de requisitos contrastan los resultados de Syft. Las relaciones Rust se contrastan con `Cargo.lock` y las dependencias directas de cada crate del workspace con su propio `Cargo.toml`. Una consulta de paquete devuelve las dependencias directas y los módulos de Census que dependen de él directa o transitivamente.

En Python se comprueban cotas crecientes de entornos hasta encontrar una solución. Si hay un conflicto, el motor elige primero el perfil cuya separación elimina más pares incompatibles y prueba si el resto admite un único entorno. Un segundo algoritmo construye particiones directamente a partir de las versiones declaradas, sin usar el grafo del solver. Devuelve un agrupamiento testigo y verifica tanto el mínimo como el resultado de la separación propuesta. Los dos métodos comparten las declaraciones originales. La verificación establece consistencia bajo el modelo de versiones declaradas. La compatibilidad binaria, la instalación conjunta y el comportamiento en ejecución requieren evidencia adicional.

Los expedientes locales incluyen los bytes originales de Syft, el resultado por consulta formal, los hashes de las consultas y entradas, y el informe reproducible. La verificación coteja el expediente con el checkout vigente. La autenticidad del host y la identidad del productor quedan fuera de esta comprobación.

## Evidencia de proveedores y referencias OWASP

La revisión de proveedores consume el expediente de producto ya verificado. Vincula sus bytes con el catálogo, los datos públicos de identidad y dos fuentes de OWASP. La instantánea del 21 de noviembre de 2026 incluye los 200 ID numéricos de GitHub, comprobados por nombre y con una segunda consulta por ID. Permite comparar el texto de licencia declarado en el catálogo con el identificador que devuelve GitHub. La igualdad de las etiquetas sólo expresa coincidencia textual. Las expresiones compuestas, la vigencia de las licencias y los derechos sobre cada componente requieren revisión de las fuentes.

| Fuente | Función en el resultado |
|---|---|
| in-toto 3.0.0 | Calcula los hashes de materiales y producto y genera metadatos Link sin firma. El verificador estándar de NQC reconstruye el enlace y comprueba sus bytes. |
| OWASP ASVS 5.0.0 | Extrae tres requisitos sobre inventario y plazos de actualización. Vincula V15.1.2 a la evidencia parcial del inventario. Los requisitos sobre plazos quedan sin evaluar. |
| OWASP Cheat Sheet Series | Consulta el índice por sección ASVS e incorpora las guías de inventario, cadena de suministro y gestión de dependencias. La asociación original tiene alcance de sección. |

Los documentos de OWASP y sus condiciones de atribución se conservan en sus fuentes. Descargar los dos archivos de la revisión fija antes de la ejecución local. [CSV de ASVS](https://raw.githubusercontent.com/OWASP/ASVS/5cf9b032440be53ce345ab3c130fda46ba1ce7a2/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv) · [Índice de guías](https://raw.githubusercontent.com/OWASP/CheatSheetSeries/c2a1e3e32cec12f27be0a3b1e771ce51288a363e/IndexASVS.md) · [in-toto v3.0.0](https://github.com/in-toto/in-toto/tree/659942bde1cd732b0b9449445f9769b2def6aeb1).

Desde el checkout y con el directorio de evidencia anterior en `$evidence_dir`, usar un entorno CPython 3.12 separado en Linux x86-64. El comando de creación valida la identidad de los dos documentos.

```bash
supply_work="$(mktemp -d)"
python3.12 -m venv "$supply_work/venv"
"$supply_work/venv/bin/python" -m pip install --only-binary=:all: --require-hashes -r superhunter/product_supply/wheels.txt
"$supply_work/venv/bin/python" -m superhunter review-product-supply --product "$evidence_dir" --out "$supply_work/supply" --asvs-csv /ruta/ASVS.csv --guide-index /ruta/IndexASVS.md
python3 -m superhunter verify-product-supply --product "$evidence_dir" --bundle "$supply_work/supply"
python3 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" in-toto/in-toto OWASP/ASVS anchore/syft
```

La consulta añade la identidad y la comparación de licencia de cada proyecto. El campo `supply_role` distingue los tres ejecutables, las dos fuentes de datos y los proyectos sin participación probada en este flujo. El expediente se liga al conjunto exacto de bytes de su ejecución de origen. Se puede consultar un expediente anterior sin aportar un expediente de proveedores.

## Inventarios CycloneDX con cdxgen

El adaptador de cdxgen 13.8.0 genera siete archivos CycloneDX 1.6 a partir del workspace Rust de Census y de los seis perfiles Python. Ejecuta el binario Linux x86-64 en un espacio de nombres de red vacío, sobre copias privadas de los manifiestos y con la instalación de dependencias desactivada. Requiere util-linux con `unshare --map-current-user --net` habilitado y el binario publicado. El adaptador verifica el SHA-256 de la copia que ejecuta. [Distribución v13.8.0](https://github.com/cdxgen/cdxgen/releases/tag/v13.8.0)

```bash
cdx_out="$(mktemp -d)/cyclonedx"
python3 -m superhunter review-product-cdxgen --product "$evidence_dir" --cdxgen /ruta/cdxgen-linux-amd64 --out "$cdx_out"
python3 -m superhunter verify-product-cdxgen --product "$evidence_dir" --bundle "$cdx_out"
python3 -m superhunter query-product --bundle "$evidence_dir" --cdxgen-bundle "$cdx_out" cdxgen/cdxgen
```

El expediente contiene `census.cdx.json`, un archivo `<perfil>.cdx.json` por perfil Python y un resumen ligado al informe de producto. La verificación coteja nombres y versiones por perfil, las relaciones Rust, la pertenencia al workspace y las sumas SHA-256 registradas en Cargo.lock. En Python, el alcance son las versiones declaradas por perfil. Los archivos originales pueden contener rutas temporales, UUID y marcas de tiempo. El resumen recoge los hechos reproducibles.

En el checkout derivado de `fc92ea6c`, dos ejecuciones locales produjeron el mismo resumen SHA-256 `4ec4567787f8609f707d07aef56de422f98babc14dc4c08692c7cfbd03c05e75`. Se cotejaron 18 paquetes Rust, 57 observaciones Python, 35 relaciones Rust y ocho miembros del workspace. El verificador rechazó tres copias con un paquete, una relación o un checksum omitidos, incluso tras recalcular el marcador de integridad.

## Contrastar las relaciones de CycloneDX con GUAC

GUAC 1.1.0 lee los siete SBOM verificados. En Linux x86-64, extraer `guacone` y `guacgql` de la [distribución oficial](https://github.com/guacsec/guac/releases/tag/v1.1.0). NQC comprueba los hashes de ambos binarios antes de ejecutarlos. El productor necesita espacios de nombres de usuario, red y PID habilitados. El servidor GraphQL y el colector se comunican por loopback dentro de esa red privada y usan un grafo en memoria que termina con la recopilación.

```bash
guac_out="$(mktemp -d)/guac"
python3 -m superhunter review-product-guac --product "$evidence_dir" --cdxgen-bundle "$cdx_out" --guacone /ruta/guacone --guacgql /ruta/guacgql --out "$guac_out"
python3 -m superhunter verify-product-guac --product "$evidence_dir" --cdxgen-bundle "$cdx_out" --bundle "$guac_out"
python3 -m superhunter query-product --bundle "$evidence_dir" --cdxgen-bundle "$cdx_out" --guac-bundle "$guac_out" guacsec/guac
```

El verificador reconstruye las relaciones esperadas desde los SBOM y coteja el documento de origen, los dos PURL en orden, el tipo de dependencia, su justificación y el número de apariciones. En la entrada comprobada encontró 43 relaciones explícitas (35 de Cargo y ocho de pertenencia al workspace). GUAC añadió 75 asociaciones heurísticas de raíz a componente, que se contabilizan por separado. El expediente conserva la respuesta GraphQL y un resumen ligado por SHA-256 a cada SBOM. La verificación posterior usa la biblioteca estándar de Python.

Los seis perfiles Python enumeran versiones. En estos SBOM del productor fijado, la verificación exige la raíz de aplicación propia del perfil, coteja cada referencia con su PURL y rechaza relaciones de dependencia explícitas que el manifiesto no acredita. Para Census se conserva el contraste del grafo con Cargo.lock y los manifiestos de los miembros.

### Recuperar los dos inventarios del perfil publicado

El [paquete de inventarios](product_supply/fixed-cdxgen-guac-inputs.json) conserva doce archivos, con sus tamaños y SHA-256. Los nueve de `cdx` contienen siete SBOM CycloneDX, el resumen y su marcador de integridad. Los tres de `guac` contienen la respuesta de dependencias, la comparación con esos siete SBOM y su marcador. En total son 106.246 bytes originales. La huella SHA-256 del paquete es `943ca6c8acc2612bc90951f02a88fc37ee1700c239891720812c401b0cd1fedc`.

La receta de [cdxgen](product_cdxgen.py) usa la distribución 13.8.0 fijada por SHA-256 y los manifiestos NQC cotejados con el expediente de producto. Nueve propiedades del SBOM de Census conservan la misma ruta efímera de su compilación de inventario, generada con `TemporaryDirectory(prefix='nqc-cdxgen-')`. La receta de [GUAC](product_guac.py) identifica las dos distribuciones 1.1.0 por sus hashes, procesa esos siete documentos y conserva por separado las relaciones declaradas y heurísticas. Las versiones y huellas registradas se cotejaron con las fijaciones del código. Los bytes originales se seleccionaron de las dos entradas del perfil `native-inputs.json` que alimentaron al producto.

Desde el repositorio, con Python 3.12 en Linux y un directorio padre ya existente:

```sh
python -B -m superhunter.tools.pack_remote_inputs --restore-inventory "$PWD/insumos-inventario"
python -B -m superhunter.tools.pack_remote_inputs --check-inventory "$PWD/insumos-inventario"
```

En el JSON completo que recibe `catalog_session --native-inputs`, asignar `cdxgen-bundle` a la ruta absoluta de `insumos-inventario/cdx` y `guac-bundle` a la de `insumos-inventario/guac`. El comando `query-product` acepta esas rutas con `--cdxgen-bundle` y `--guac-bundle`. El lector valida el paquete y cada miembro y publica ambos directorios juntos en un destino nuevo. Esta recuperación permite repetir la lectura de los mismos bytes. Una nueva ejecución de los productores se acredita por separado con las recetas anteriores.

## Avisos públicos de las distribuciones Python

Con las distribuciones de `superhunter/product_supply/wheels.txt` en un directorio local, se pueden consultar o exportar sus avisos desde la CLI. NQC comprueba el SHA-256 del wheel conforme al archivo de bloqueo vinculado al expediente de in-toto y comprueba nombre y versión en METADATA. Lee los archivos que nombra cada cabecera License-File. En los wheels antiguos sin esa cabecera busca los avisos LICENSE, COPYING y NOTICE del directorio dist-info.

```bash
notice_dir="$(mktemp -d)/avisos"
python3 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" --notice-wheels /ruta/wheels --export-notices "$notice_dir" cffi pycparser
```

La exportación escribe los textos originales y un índice que vincula cada texto con su ruta dentro del wheel, la versión y los hashes de ambos. Omitir `--export-notices` permite consultar sin escribir archivos. El campo `declared_license_expression` reproduce la declaración del proveedor cuando existe. Las versiones de los diez wheels corresponden al entorno de revisión de proveedores de NQC; cada perfil de la aplicación conserva sus propios pines. La opción `--scancode-release` añade las detecciones de ScanCode para esos mismos bytes.

## Reproducir el reconocimiento de licencias

Preparar fuera del checkout la distribución oficial de ScanCode Toolkit 32.5.0 para Linux/Python 3.12 (`scancode-toolkit-v32.5.0_py3.12-linux.tar.gz`), el binario cargo-deny 0.22.0 para x86_64 Linux musl y el toolchain Rust 1.98.1 de Census. Descargar a un CARGO_HOME dedicado las dependencias fijadas con `cargo fetch --manifest-path nqc-census/Cargo.toml --locked`. La revisión posterior funciona con la red deshabilitada. [ScanCode 32.5.0](https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0) · [cargo-deny 0.22.0](https://github.com/EmbarkStudios/cargo-deny/releases/tag/0.22.0)

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" \
  --notice-wheels /ruta/wheels --scancode-release /ruta/scancode-toolkit-v32.5.0_py3.12-linux.tar.gz \
  --cargo-deny /ruta/cargo-deny --rust-bin /ruta/toolchain/bin --cargo-home /ruta/cargo-home \
  aboutcode-org/scancode-toolkit EmbarkStudios/cargo-deny cffi
```

La CLI verifica el archivo de distribución de ScanCode antes de extraerlo y configurar su entorno privado. Sólo presenta al escáner los bytes públicos seleccionados de los wheels verificados. Coteja la cobertura, el hash por archivo, la ruta y las líneas de cada coincidencia. La respuesta conserva las referencias desconocidas que emite ScanCode. Un aviso de autoría puede mencionar licencias de otros componentes; las coincidencias describen ese texto.

Para Rust se ejecuta `cargo-deny --frozen list --layout crate --format json` y se comprueba cada identidad, versión y lista de licencias contra el manifiesto propio o el Cargo.toml de la distribución cuyo SHA-256 figura en Cargo.lock. El campo `declared_expression` conserva las alternativas originales y vale `null` cuando falta la declaración. La consulta de cada herramienta admite ejecución independiente. En una sesión con varias claves, cada productor se ejecuta una vez.

Para ampliar la revisión a los seis perfiles propios de NQC, descargar sus wheels en un directorio separado. En los tres archivos de bloqueo siguientes cada wheel tiene versión y SHA-256. La descarga prepara archivos; el análisis sólo lee metadatos y avisos públicos.

```bash
for profile in otel-qa owned-cross-evm owned-spec-evm; do
  python3.12 -m pip download --no-deps --only-binary=:all: --require-hashes \
    -r "superhunter/requirements-${profile}.txt" -d /ruta/wheels-perfiles
done
```

Añadir `--profile-wheels /ruta/wheels-perfiles` al comando de consulta. `profile_wheel_notices` conserva por separado cada versión, los perfiles que la declaran y los que aportan un digest. Dos perfiles pueden usar la misma versión aunque sólo uno fije el hash. La consulta indica `NO_DIGEST_IN_PRODUCT_PROFILES` cuando ninguno lo aporta. Un texto sin coincidencia de ScanCode conserva su hash y su resultado vacío. Los expedientes de proveedores y perfiles pueden revisarse juntos o por separado.

En la ejecución conjunta sobre estos manifiestos, 37 de las 39 combinaciones de paquete y versión tenían un wheel con digest verificable, lo que cubrió 55 de las 57 declaraciones por perfil. Las dos restantes fueron `crytic-compile` y `slither-analyzer`. ScanCode procesó 56 archivos distintos entre proveedores y perfiles, con coincidencias en 54. El índice exportado `notices.json` tuvo SHA-256 `ed06a5c822737c4b3e4d727f04ec70f6c3eed16bf2bffeb734052efacd4ef05d`. Para comprobarlo, añadir `--export-notices /ruta/nueva/avisos` a la consulta conjunta y ejecutar `sha256sum /ruta/nueva/avisos/notices.json`.

## Buscar términos en los avisos verificados con Qdrant

La opción `--qdrant` construye un índice local de los avisos cuya procedencia y SHA-256 se comprobaron en los wheels. Un proceso de Qdrant 1.20.2 sirve únicamente al proceso de consulta por loopback en un espacio de red y PID privado. El índice temporal termina al cerrar la sesión. El binario se extrae de [la distribución oficial x86-64 Linux musl](https://github.com/qdrant/qdrant/releases/tag/v1.20.2). SHA-256 del archivo comprimido `7c3e956b97830a9faa6391540330380c2fa4aa2f92df99bd8d1880a703b922af`, y del ejecutable `315342e8f783935932e8672c06fcc1a13903c819a82f1263765c3f00a831d893`.

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" \
  --notice-wheels /ruta/wheels --profile-wheels /ruta/wheels-perfiles --qdrant /ruta/qdrant \
  qdrant/qdrant 'notice:redistribution patent'
```

La búsqueda usa palabras y números ASCII sin distinguir mayúsculas. Cada resultado incluye el archivo, el SHA-256, los términos encontrados y cuántos términos distintos coincidieron. La CLI relee del índice los vectores y hashes de cada aviso. En cada consulta también coteja los resultados y puntuaciones con los términos de los textos originales. Los empates se ordenan por nombre de archivo. Las consultas de esta sesión comparten el índice en memoria. En la entrada conjunta de proveedores y perfiles se indexaron 56 avisos y 1,755 términos. La consulta del ejemplo obtuvo 22 avisos con al menos uno de sus dos términos.

## Localizar un componente o una relación en los bytes del SBOM

La opción `--tree-sitter` conecta Tree-sitter con los documentos CycloneDX verificados de cdxgen. Para cada paquete devuelve un puntero JSON, el SHA-256 del SBOM y el intervalo de bytes `[start_byte, end_byte)` que contiene el literal JSON del PURL o de la referencia de destino de una relación. Cada relación incluye los PURL de origen y destino. La CLI coteja el árbol nativo con un segundo lector JSON y vuelve a leer los valores en sus posiciones originales.

Se requiere la [CLI 0.27.2 de Tree-sitter](https://github.com/tree-sitter/tree-sitter/releases/tag/v0.27.2) para Linux x86-64 y la [gramática JSON](https://github.com/tree-sitter/tree-sitter-json/tree/ee35a6ebefcef0c5c416c0d1ccec7370cfca5a24/src) fijada en `ee35a6ebefcef0c5c416c0d1ccec7370cfca5a24`. Guardar `src/parser.c` y `src/tree_sitter/parser.h` bajo el mismo directorio conservando la subruta `tree_sitter/`. NQC verifica los hashes de las dos fuentes y el ejecutable. Compila la gramática con `/usr/bin/cc` en un directorio temporal y analiza los SBOM localmente sin red.

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" --cdxgen-bundle "$cdx_out" \
  --tree-sitter /ruta/tree-sitter --json-grammar /ruta/gramatica-json \
  tree-sitter/tree-sitter sha2 cryptography
```

En los siete SBOM propios se localizaron 75 componentes, sus siete raíces y 43 relaciones explícitas. La misma versión de un paquete puede aparecer en varios perfiles. Cada ubicación conserva la identidad del archivo en el que se observó.

## Enumerar las agrupaciones posibles de los seis perfiles

El verificador TLC de TLA+ construye todas las formas de repartir los seis perfiles Python en entornos compatibles con las versiones que declaran. El modelo se genera a partir de los pines de los seis manifiestos del checkout. Una segunda enumeración usa los conflictos que NQC ya verificó y contrasta todos los estados intermedios y finales. También coteja el mínimo demostrado con cvc5 y la agrupación testigo del informe de producto.

Se necesita Java en `/usr/bin/java` y el archivo oficial [tla2tools.jar, versión 1.7.4](https://github.com/tlaplus/tlaplus/releases/tag/v1.7.4), SHA-256 `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`. El proceso Java opera sin red. Se conserva un hash del conjunto ordenado de estados, independiente del orden de exploración.

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" \
  --tlc-jar /ruta/tla2tools.jar tlaplus/tlaplus cvc5/cvc5
```

En los manifiestos revisados se alcanzaron 190 estados, incluidas las asignaciones parciales. De las 114 particiones completas compatibles, ocho usan dos entornos, 46 usan tres, 46 usan cuatro, 13 usan cinco y una usa seis. La salida devuelve los ocho repartos mínimos. El modelo cubre las versiones declaradas directamente en esos archivos.

## Exportar observaciones de licencias en SARIF 2.1.0

El exportador identifica tres situaciones que requieren revisión. `NQC1001` localiza un miembro del workspace sin declaración de licencia. `NQC1002` apunta a la línea de un perfil cuyo paquete y versión carecen de digest en todos los perfiles. `NQC1003` señala un aviso verificado para el que ScanCode devolvió cero coincidencias. Cada observación incluye el archivo, sus bytes, SHA-256 y la región correspondiente. Las reglas describen la evidencia disponible.

Añadir las siguientes opciones a la consulta conjunta de ScanCode y cargo-deny, incluyendo `--profile-wheels`. Se necesita el paquete oficial [Sarif.Multitool 5.8.0](https://www.nuget.org/packages/Sarif.Multitool/5.8.0) y el archivo [dotnet-runtime-8.0.34-linux-x64.tar.gz](https://builds.dotnet.microsoft.com/dotnet/Runtime/8.0.34/dotnet-runtime-8.0.34-linux-x64.tar.gz). NQC verifica los hashes, ejecuta el validador oficial con el esquema incluido en ese paquete y comprueba el resultado sin red.

```text
--sarif-sdk /ruta/sarif.multitool.5.8.0.nupkg --dotnet-runtime /ruta/dotnet-runtime-8.0.34-linux-x64.tar.gz
--export-license-sarif /ruta/nueva/revision-sarif
```

La exportación opcional escribe `license-review.sarif`, el informe original de la validación y un resumen reproducible. Consultar `microsoft/sarif-sdk` devuelve los hashes del validador, del esquema y del informe, junto con los recuentos por regla. La ejecución conjunta en los seis perfiles produjo ocho observaciones de Cargo, dos pines sin digest y dos avisos sin coincidencia. El validador no emitió diagnósticos sobre el formato. El SHA-256 de `license-review.sarif` fue `29251a9ca219ef50647eb973f5d985bc26015aa07a38e0349002564b76cf2056`.

## Comprobar los requisitos de ejecución de los productores Linux

La opción `--lief-wheel` lee los encabezados ELF del conjunto de productores nativos de inventario y licencias. Sólo acepta binarios cuyo SHA-256 ya está fijado por NQC. LIEF obtiene la arquitectura, el intérprete y las bibliotecas de `DT_NEEDED`. La CLI coteja esos datos con el encabezado original y con la salida de GNU readelf. La inspección opera sin ejecutar los productores examinados.

Usar CPython 3.12 en Linux x86-64 y la distribución [LIEF 1.0.0](https://pypi.org/project/lief/1.0.0/) para ese sistema, SHA-256 `41ff868f5328fc8e5237a9e1f4718590e0ee9180c1422b3e4948b7116ba4517c`. En `--producer-bin-dir` colocar los ejecutables con los nombres `syft`, `cvc5`, `cdxgen`, `guacone`, `guacgql`, `cargo-deny`, `qdrant` y `tree-sitter`. Se informan por separado los nombres ausentes. También se aprovechan las rutas de cargo-deny, Qdrant y Tree-sitter que ya reciba la misma consulta.

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" \
  --lief-wheel /ruta/lief-1.0.0-cp312-abi3-manylinux_2_28_x86_64.whl \
  --producer-bin-dir /ruta/productores lief-project/LIEF tree-sitter/tree-sitter
```

En los ocho binarios verificados el encabezado indicó Linux x86-64 compatible con ELF64 little-endian. Tree-sitter declaró un intérprete y cuatro bibliotecas dinámicas. Los otros siete carecían de intérprete y de entradas `DT_NEEDED`. El inventario describe las dependencias de carga declaradas en esos archivos. Cada identidad conserva sus propias observaciones de ejecución en la consulta conjunta.

## Ordenar los avisos por relevancia con Haystack

Haystack 3.5.0 clasifica las coincidencias por BM25+. La frecuencia de los términos, su frecuencia en la colección y la longitud del aviso influyen en la puntuación. NQC recalcula cada puntuación desde los textos verificados y comprueba la cobertura. Al usar también Qdrant se cotejan archivo, hash y términos encontrados por los dos índices. La búsqueda sigue limitada a los avisos de la sesión.

Descargar los wheels de la distribución pública en Linux x86-64 con CPython 3.12. La preparación y la consulta son operaciones separadas. La búsqueda verifica los 41 hashes, instala las dependencias en un directorio temporal y mantiene el índice en memoria durante la sesión.

```bash
python3.12 -m pip download --only-binary=:all: --no-deps --require-hashes \
  -r superhunter/product_supply/haystack-linux-py312.txt -d /ruta/wheels-haystack
python3.12 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" \
  --notice-wheels /ruta/wheels --profile-wheels /ruta/wheels-perfiles \
  --haystack-wheels /ruta/wheels-haystack --qdrant /ruta/qdrant \
  deepset-ai/haystack 'notice:redistribution patent'
```

Sobre los 56 avisos, ambos índices recuperaron 22 coincidencias para la consulta del ejemplo. Haystack situó primero `coincurve-20.0.0-1.txt`, con una puntuación BM25+ de 5.6626298988. Las palabras desconocidas devuelven una lista vacía. [Documentación de Haystack](https://docs.haystack.deepset.ai/docs/inmemorybm25retriever).

## Encontrar avisos con texto parecido con pgvector

`similar:<archivo>` devuelve los cinco vecinos más próximos de un aviso verificado, con su similitud coseno y una indicación separada de igualdad exacta de SHA-256. pgvector compara vectores de frecuencias de términos ponderadas por TF-IDF. NQC comprueba cada par contra el producto escalar de los vectores calculados desde los avisos originales. La semejanza del texto sirve para localizar documentos que merece la pena comparar.

Preparar los dos paquetes binarios Debian 13 para x86-64 con sus nombres originales en una carpeta. [PostgreSQL 17.12](https://deb.debian.org/debian/pool/main/p/postgresql-17/postgresql-17_17.12-0+deb13u1_amd64.deb) y [pgvector 0.8.0](https://deb.debian.org/debian/pool/main/p/pgvector/postgresql-17-pgvector_0.8.0-1_amd64.deb). Se verificaron contra el índice firmado de Debian. La CLI comprueba sus SHA-256 y extrae los archivos sin instalarlos en el sistema. `initdb` y PostgreSQL funcionan con el usuario local sin privilegios, dentro de una red privada. El modo monousuario recibe el SQL por la entrada estándar y termina al completar el cálculo.

```bash
python3.12 -m superhunter query-product --bundle "$evidence_dir" --supply "$supply_work/supply" \
  --notice-wheels /ruta/wheels --profile-wheels /ruta/wheels-perfiles \
  --pgvector-packages /ruta/deb pgvector/pgvector similar:coincurve-20.0.0-1.txt
```

La revisión de 56 avisos comparó los 1,540 pares posibles. En 31 pares coincidían todos los bytes. El vecino más próximo de `coincurve-20.0.0-1.txt` fue `ckzg-2.1.8-1.txt`, con similitud 0.96771840 y hashes distintos.

## Consultar el avance por lotes

Las claves `batch:1` y `batch:2` dividen el catálogo fijado del PR 110 en dos grupos disjuntos de 100. El primer grupo conserva las 15 identidades acreditadas en `fa5e498d9c7d7ad3d8b685c6c2f127247899ac3c`. Las 185 restantes se ordenan por categoría (SUPPLY, CODIGO, FORMAL, OBSERVACION, METODO, BINARIOS, AGENTES, resto) y después por ID original. Las primeras 85 completan el primer grupo. La pertenencia a un grupo se mantiene aunque cambien sus resultados.

Cada fila indica el repositorio, su ID original, su función y la evidencia que se cargó en esa sesión. `with_evidence` incluye `executable` y `reference_data`. `pending` cuenta las identidades que carecen de evidencia funcional en esa ejecución. Al omitir un productor opcional, su resultado queda pendiente en esa consulta.

### Checksums Rust con ast-grep

Extraer `ast-grep` de la distribución oficial Linux x86-64 GNU 0.51.3. El SHA-256 del ZIP es `22803eb0c5bf83164fb7fd76d4721d355ecf0c8466ef47342c1ec7d80897ca47`. La CLI valida el binario y ejecuta una regla JSON fija sobre el CycloneDX de Census. Contrasta la identidad, el checksum y el intervalo de bytes de cada componente del registro con el SBOM y el Cargo.lock de NQC. [Distribución de ast-grep](https://github.com/ast-grep/ast-grep/releases/tag/0.51.3)

### Archivo de licencia del repositorio con Scorecard

Extraer `scorecard` del archivo oficial Linux amd64 de OpenSSF Scorecard v5.7.0 (SHA-256 del archivo comprimido `3b08ec0a8681806c3e744ec9210742a502c7d66f06f25523b70f7128738235d3`). NQC reconstruye los archivos del commit local en una carpeta privada, comprueba sus blobs y ejecuta exclusivamente el control `License`. Evalúa también un directorio de control con un aviso público real bajo el nombre `LICENSE`. La salida identifica por separado el commit, el resultado del repositorio y el control positivo. La puntuación expresa si Scorecard detectó el archivo y reconoció su licencia. [Distribución de Scorecard](https://github.com/ossf/scorecard/releases/tag/v5.7.0)

```sh
python3 -B -m superhunter query-product --bundle /ruta/product --supply /ruta/supply \
  --notice-wheels /ruta/wheels --cdxgen-bundle /ruta/cdx \
  --ast-grep /ruta/ast-grep --scorecard /ruta/scorecard \
  ast-grep/ast-grep ossf/scorecard batch:1 batch:2
```

### Grafo de Cargo con RustSec

`--rustsec-crates /ruta/crates --rust-bin /ruta/rust/bin` agrega el grafo que obtiene el ejecutable oficial `cargo-lock` del proyecto RustSec. Preparar en la primera carpeta `cargo-lock-11.1.0.crate` y los 66 archivos `<nombre>-<versión>.crate` del registro fijados por el Cargo.lock que trae ese paquete. Su SHA-256 es `50524592e6bfbb1bf6f94e8184a786f637faeaf1cf37bbe65502b9a2c5c48939`. El directorio de herramientas corresponde a Rust 1.98.1 para Linux x86-64. [Paquete publicado](https://static.crates.io/crates/cargo-lock/cargo-lock-11.1.0.crate) · [Fuente en RustSec](https://github.com/RustSec/rustsec/tree/86193f5e6d7f98a9f3d30b2c99390d9ba7c88589/cargo-lock)

NQC verifica el SHA-256 de cada archivo y compila la CLI con `cargo build --frozen` en una carpeta temporal sin red. Ejecuta `cargo-lock list --dependencies` sobre el lockfile verificado de Census y contrasta los paquetes y las aristas dirigidas con el grafo de producto. La fila `rustsec/rustsec` identifica el grafo, sus paquetes terminales, la versión del compilador y las entradas verificadas.

### Límite observado para strace

En la ejecución sin red del 21 de noviembre, el binario de Debian 13 `strace` 6.13 (SHA-256 `69f88291a4e47f258b8e32b089c919a247509f063ef3d6afe5389939051102b3`) recibió `PTRACE_TRACEME: Operation not permitted` al intentar observar un proceso hijo que leía el Cargo.lock de NQC. Su fila queda pendiente en el recuento.

### Expresiones SPDX con Dependency-Track

`--dependency-track /ruta/dependency-track-apiserver.jar` usa las clases del analizador SPDX y los grupos de licencias distribuidos en Dependency-Track 4.14.7. Requiere Java 21, ScanCode sobre los avisos verificados y cargo-deny sobre el workspace. NQC comprueba el SHA-256 del archivo y ejecuta exclusivamente el analizador en un proceso local sin red. Conserva la procedencia de cada expresión, incluidas las ausencias. Para los operadores AND y OR contrasta todas las combinaciones de valores de sus identificadores con un segundo evaluador. Los grupos provienen de la configuración del proveedor. [Distribución de Dependency-Track](https://github.com/DependencyTrack/dependency-track/releases/tag/4.14.7)

La verificación del navegador Chromium con Playwright 1.62.0 también quedó pendiente en este entorno. El navegador finalizó durante el arranque al recibir `socket() failed: Operation not permitted`. No produjo una comprobación funcional del inventario.

### Paridad de inventario entre x86-64 y ARM64

`--qemu-aarch64 /ruta/qemu-aarch64 --syft-arm64 /ruta/syft` repite en QEMU el inventario de los siete manifiestos de NQC usando el ejecutable oficial de Syft 1.38.2 para ARM64. NQC valida los dos binarios y coteja cada nombre, versión y archivo de origen con el expediente nativo x86-64. Los argumentos del catálogo son los mismos para ambas arquitecturas. La fila `qemu/qemu` contiene el SHA-256 de las observaciones normalizadas y los recuentos por archivo.

Extraer `usr/bin/qemu-aarch64` del paquete Debian 13 `qemu-user_10.0.13+ds-0+deb13u1_amd64.deb` (SHA-256 `ca6ede739327a20ae5a3498230c8a3a9a072c586e131bc6bcc1201eb1725e336`) y `syft` de `syft_1.38.2_linux_arm64.tar.gz` (SHA-256 `ccd95833d4124f0e30925033908934978086727af69585f015f28a4f355fda1b`). [Paquete QEMU](https://deb.debian.org/debian/pool/main/q/qemu/qemu-user_10.0.13+ds-0+deb13u1_amd64.deb) · [Distribución ARM64 de Syft](https://github.com/anchore/syft/releases/tag/v1.38.2)

## Decisiones sobre las licencias observadas

La consulta `license-choices` enlaza los avisos de las ruedas y las declaraciones de Cargo con sus expresiones SPDX. Para cada expresión AND/OR calcula las combinaciones mínimas de identificadores que la satisfacen. Compara la tabla de verdad completa con el resultado del analizador de Dependency-Track. El resultado conserva las fuentes sin expresión y los identificadores desconocidos. La equivalencia se limita a estos valores booleanos y operadores. Una clasificación jurídica de la obligación requiere evaluar el texto aplicable.

Con `--license-proof-kits /ruta/distribuciones`, NQC comprueba esa equivalencia con cada productor presente. La prueba de control elimina una opción válida observada y exige que cada productor detecte la diferencia. `verified_by` identifica los productores ejecutados. En esta revisión los doce comprobaron las mismas trece expresiones. Algunos comparten solvers.

El archivo [product_proof_releases.json](product_proof_releases.json) fija las versiones, las URL del proveedor y el SHA-256 de cada entrada. Preparar las distribuciones fuera del checkout. Usar el último segmento de la URL como nombre local salvo que haya un campo `file`. Para las entradas con `member`, verificar primero el SHA-256 del archivo del proveedor (`archive_sha256`), extraer solo ese miembro y guardarlo con el nombre `file`. NQC comprueba otra vez sus bytes antes de usarlos. KLEE usa los miembros de la imagen de Linux x86-64 indicados en el registro y la biblioteca SQLite indicada allí. Su biblioteca LLVM ocupa 1,98 GB. Alive2 se compila a partir del archivo de fuentes que coincide con el árbol Git fijado. Requiere GCC con soporte C++20. El directorio de temporales debe tener espacio para descomprimir las distribuciones. El replay completo se comprobó en Debian 13 x86-64 con Python 3.12, Java 21 y Rust 1.98.1.

## Consultas sobre los avisos

- `--pmd-release /ruta/pmd-dist-7.29.0-bin.zip` compara secuencias de al menos 45 tokens con el detector CPD de PMD. NQC coteja los tokens y las coordenadas con los bytes de cada aviso. `notice-overlaps:<archivo>` devuelve las coincidencias y sus ubicaciones.
- `--notice-review-wheels /ruta/ruedas` instala sin red las distribuciones verificadas por [license-review-linux-py312.txt](product_supply/license-review-linux-py312.txt). LlamaIndex construye una ventana de contexto por párrafo. `notice-context:<archivo>@<línea>` devuelve el párrafo que contiene esa línea y sus vecinos, con rangos que se pueden comprobar en el aviso.
- La misma opción compara mediante LangGraph la declaración de cada rueda con las expresiones que encontró ScanCode. Distingue discrepancias de texto, declaraciones ausentes y ruedas sin un hash verificable. La fila de LangGraph expone la decisión por paquete y sus totales. El grafo tiene transiciones fijas y se ejecuta localmente.
- `--proptest-crates /ruta/crates --rust-bin /ruta/rust/bin` verifica la partición de las 200 identidades con proptest 1.12.0. Preparar `proptest-1.12.0.crate` y los archivos de registro de su Cargo.lock, con el mismo formato de caché que para RustSec. Se compila el controlador con Cargo sin red. Sus 128 ensayos de semilla fija ejercitan el código de partición de NQC y comprueban el rechazo de faltantes, excedentes, IDs duplicados y nombres duplicados con mayúsculas distintas.

Al comando `query-product` que abre los expedientes y las demás distribuciones de esta guía, agregar las cuatro opciones anteriores. Las opciones de ScanCode, cargo-deny y Dependency-Track proporcionan las observaciones para `license-choices`. Enviar por entrada estándar una clave por línea permite reutilizar la preparación inicial. Por ejemplo, para consultar las 200 identidades y los dos lotes, generar la entrada en el propio checkout y pasarla mediante redirección a la misma sesión.

```sh
python3 - <<'PY' > consultas.txt
import json
from pathlib import Path

catalogo = json.loads(Path('superhunter/repositories_200.json').read_bytes())
for fila in sorted(catalogo['entries'], key=lambda x: x['id']):
    print(fila['repository'])
print('batch:1')
print('batch:2')
print('license-choices')
print('notice-context:annotated-types-0.8.0-1.txt@1')
print('notice-overlaps:annotated-types-0.8.0-1.txt')
PY
```

[Revisión del primer lote, identidad por identidad](FIRST_BATCH_REVIEW.md). [Distribución de PMD](https://github.com/pmd/pmd/releases/tag/pmd_releases%2F7.29.0). [Distribución de proptest](https://static.crates.io/crates/proptest/proptest-1.12.0.crate).

### Identificadores de licencia con OSV-Scanner

La consulta `google/osv-scanner` indica qué identificadores observados por NQC reconoce el registro distribuido con OSV-Scanner 2.7.1. Conserva las fuentes de cada término y distingue un identificador local `LicenseRef` del marcador literal `unknown`. En esta instantánea, tres avisos contienen alguno de los dos identificadores locales que faltan en el registro.

Agregar `--osv-license-cache /ruta/distribuciones` al comando anterior que abre el inventario de Dependency-Track. Colocar en esa carpeta el archivo oficial de fuentes de la etiqueta v2.7.1 como `osv-scanner-2.7.1.tar.gz` y el compilador oficial `go1.27.3.linux-amd64.tar.gz`. Los SHA-256 están en [product_spdx_ids.py](product_spdx_ids.py). La prueba compila los archivos originales de OSV-Scanner que implementan `spdx.Unrecognized` y su lista de identificadores. Ejecuta el test del proveedor y coteja la salida nativa con la lista publicada y con las fuentes del expediente. Puede reproducirse con la red deshabilitada. [Fuentes de OSV-Scanner](https://codeload.github.com/google/osv-scanner/tar.gz/refs/tags/v2.7.1) · [Distribución de Go](https://go.dev/dl/go1.27.3.linux-amd64.tar.gz).
