# Revisión de dependencias de NQC y SuperHunter

Desde la CLI de SuperHunter se puede consultar el catálogo de 200 proyectos, el grafo de dependencias de Census y los conflictos entre los seis perfiles Python de SuperHunter. El catálogo procede del [PR 110](https://github.com/josuechavando350-png/nexus-quant-capital/pull/110), commit `474846b11ea41f9d9f41c4aa6d7eda0cbf18d2f6`. La copia conserva exactamente los bytes públicos de ese JSON. La consulta conserva los identificadores históricos de los siete proyectos que aparecen también en el portafolio de 50.

Dos proyectos producen evidencia en esta revisión. Syft extrae paquetes y relaciones de los manifiestos copiados a un directorio temporal. cvc5 comprueba si los perfiles con versiones incompatibles pueden compartir un número dado de entornos. Las demás entradas siguen siendo consultables por su nombre en GitHub. Pertenecer al catálogo no acredita una ejecución.

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
