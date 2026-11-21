# Acta de materialización de fuentes

## Comprobación local de dependencias anidadas

El [recibo de almacenamiento](product_supply/acceptance-120/nested-source-storage.json) registra la inspección de los 200 repositorios directos. Los árboles fijan 141 rutas de submódulo en 40 proyectos y apuntan a 140 commits distintos. Los 141 directorios estaban vacíos. Ninguno de los 140 commits apareció en las 200 bases de objetos directas consultadas.

El archivo de prueba de Qdrant contenía los 132 bytes del puntero LFS. Se contrastó su blob Git y se buscaron los 1.752.948 bytes identificados por SHA-256 en el archivo de trabajo y en las 200 cachés LFS canónicas. Su materialización sigue pendiente. Cada resultado describe el almacenamiento local examinado. El conteo funcional se calcula en las sesiones del producto.

Para cotejar el recibo desde el directorio que contiene los 200 checkouts en `upstream/`, ejecutar los siguientes comandos.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.verify_source_materialization \
  --nested-workspace "$FUENTES_DIRECTAS" > "$TMPDIR/dependencias-anidadas.json"
cmp "$TMPDIR/dependencias-anidadas.json" superhunter/product_supply/acceptance-120/nested-source-storage.json
```

**La rama consolidada registra 200 gitlinks.** Su árbol `upstream` es `d8b5a3d79e81e686d4299e40bea64d37824d29fe`. La comprobación contrasta todas sus rutas y revisiones con el catálogo y reconstruye el árbol de las 153 revisiones originales. El [inventario directo vigente](SOURCE_CHECKOUT.md) cubre los 200 repositorios. Las pruebas de procedencia otorgan cero participaciones funcionales.

## Acta histórica del PR 118

Cuando se produjo el acta, la rama de producto contenía 153 gitlinks y un espacio de fuentes separado contenía los 200 checkouts. El [inventario de aquel corte](product_supply/source-inventory-153.json) y los tres recibos se conservan con sus bytes originales. El campo `historical_record` del verificador reconstruye las cifras de entonces.

| Evidencia | Alcance |
|---|---|
| `all200-checkouts.json` | Observación histórica de los 200 estados `checked_out`, con identidad, revisión, árbol y ruta de cada directorio. Se reconstruye la huella del manifiesto a partir de la lista revisada. |
| `preserved153.json` | Las 153 revisiones compartidas del punto de partida coinciden exactamente con sus gitlinks en el producto consolidado. Su árbol es `20df6bd14174b62825d33de0d48f9af4598079cd`. |
| `summary.json` | Los 47 registros adicionales identifican el resultado, commit y árbol de cada checkout. El programa histórico escribía `checked_out` después de obtener código de salida cero de `git fsck --full --no-dangling --no-reflogs --no-progress`. El acta conserva el hash del programa examinado. Los registros originales carecen de una transcripción independiente de stdout y stderr de cada llamada. |
| Cotejo actual | Con los tres recibos originales se reconstruyó la huella del árbol de los 200 y se contrastó con el superproyecto local `785860fc85166597d40ba08503a3d89a6be8e5be`. Los 200 pares revisión/árbol observados en sus checkouts dieron SHA-256 `0b763d22f728b559e18075bfe5b3db916f0968cbb745556cd20ffe22bab91b4b`. |

El [archivo de observaciones](product_supply/source-materialization-observations.json) preserva los bytes exactos de los tres recibos mediante compresión. El [acta](product_supply/source-materialization-review.json) conserva las huellas de cada original. La verificación ordinaria abre los recibos publicados, comprueba sus huellas, coteja cada fila con las autoridades de identidad y árbol de producto y reconstruye la huella Git del conjunto de 200 referencias. Esta verificación no requiere los 200 directorios ni descarga sus fuentes.

```sh
unshare --user --map-current-user --net python3.12 -B -m superhunter.tools.verify_source_materialization
python3.12 -B -m unittest -v superhunter.tests.test_source_materialization
```

Quien ya disponga del espacio de observación original puede añadir `--existing-workspace RUTA` para repetir el contraste de directorios, HEAD y árboles. Esta opción es de sólo lectura. Los bytes completos de cada proveedor, los objetos de submódulos anidados y los contenidos externos de Git LFS quedan fuera de este nuevo cotejo. Se reutilizó la evidencia de fsck ya registrada, con cero fsck o compilaciones adicionales durante esta comprobación. El superproyecto histórico se identifica como procedencia local. Las mismas 200 revisiones se publicaron como gitlinks en el PR 119. Las huellas y la concordancia de datos no autentican la firma de un operador histórico.

## Atribución y selección de los seis extractos nuevos

La revisión recorrió las rutas de los seis archivos bajo el árbol de cada revisión y examinó tanto el origen como el material seleccionado. La primera selección usa dos módulos matemáticos o de representación y una tabla de reporte. La segunda usa una función de comparación y dos referencias documentales. Ninguna selección incluye la aplicación completa, técnicas de explotación, muestras de ataque, credenciales o código para sondear objetivos.

| Proveedor | Material de procedencia conservado | Adaptación |
|---|---|---|
| Strix | `LICENSE`, Apache-2.0 | Se seleccionaron tres funciones de ubicaciones de informe. El nuevo encabezado indica la extracción y añade importaciones estándar. |
| Dalfox | `LICENSE.txt`, MIT, copyright de hahwul | La tabla de severidad del formato SARIF se conservó como texto. |
| NVIDIA garak | `LICENSE`, Apache-2.0, y encabezado SPDX de la fuente con atribución a NVIDIA | Se conservaron el encabezado y la función matemática, con una nota de extracción. |
| OWASP Juice Shop | `LICENSE`, MIT, copyright de Bjoern Kimminich y colaboradores | Sólo se separó la función corregida que compara destinos; los bytes de ese tramo se conservan. |
| OWASP WebGoat | `COPYRIGHT.txt`, `LICENSE.txt`, Bruce Mayhew y Nanne Baars, GPL-2.0-or-later, y copia del texto GPL-2 | Se conservan dos líneas de la condición de contención canónica como texto sin cambios. |
| DVWA | `COPYING.txt`, texto GPL versión 3 | El ejemplo de admisión de nombres se usa como dato de referencia. La presentación normaliza los finales de línea y espacios finales. Se comprobaron tanto las huellas originales como las normalizadas del fragmento y del aviso. |

Los listados de origen enlazan cada revisión con ruta, blob, tramos y aviso. La comprobación adicional con las fuentes originales autenticó los seis extractos. [Selecciones de informes](product_supply/passive-source-excerpts/origins.json) · [Selecciones de remediación](product_supply/remediation-excerpts/origins.json). La revisión de estos textos no otorga un dictamen de compatibilidad de distribución comercial del conjunto del producto.
