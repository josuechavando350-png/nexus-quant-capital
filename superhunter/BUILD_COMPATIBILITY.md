# Compatibilidad de compilaciones propias de NQC

El flujo recompila las tres fuentes históricas de StatefulConservation y reproduce exactamente sus ABI, almacenamiento, bytecode de creación y bytecode de ejecución. También compila tres variantes fijas que agregan un campo, permutan dos campos o cambian el ancho de un campo. El proceso consume declaraciones y artefactos locales. No ejecuta contratos.

| Proyecto | Uso probado |
|---|---|
| NomicFoundation/hardhat | La función de producción getContractArtifact y sus auxiliares hexadecimales generan seis artefactos Hardhat. NQC comprueba el identificador de compilación, las interfaces, ambas clases de bytecode y las referencias de enlaces. |
| OpenZeppelin/openzeppelin-upgrades | Las funciones originales de límites de campo y getLayoutChange producen intervalos y detectan cambios de slot, desplazamiento y ancho. NQC corrobora estos resultados empaquetando la secuencia de enteros del AST de solc. |
| crytic/crytic-compile | La distribución completa de Crytic Compile procesa siete trabajos standard-json con solc fijado. Sus 41 módulos Python coinciden con el árbol Git. Los selectores que calcula coinciden con evm.methodIdentifiers de otra invocación directa a solc. |
| crytic/properties | Se compila su IERC20 y se compara la firma, el tipo de retorno y la mutabilidad con la interfaz WETH archivada en Census. |

Los tres controles históricos conservan los campos debit, credit y steps en los bytes 0–2, 2–4 y 4–5 respectivamente. Agregar un campo al final preserva los tres. La permuta cambia debit y credit; ampliar el entero de steps cambia su ancho. Estos resultados corresponden a la disposición de campos enteros de los contratos comprobados. El procedimiento no califica una actualización general de proxy ni equivalencia de comportamiento.

Las interfaces comparten siete firmas con sus tipos de retorno. El compilador clasifica decimals() de Crytic como nonpayable y el de NQC como view. Esta diferencia no altera el selector. Cuatro funciones sólo aparecen en el contrato de interfaz de NQC. El flujo conserva la diferencia para el consumidor. [Recibos](product_supply/compile-abi-acceptance.json)

## Reproducción

Usar los cuatro checkouts del catálogo, Python 3.12, el Node del perfil EVM y un directorio `NQC_BUILD_KIT`. Ese directorio contiene el ejecutable `solc` oficial 0.8.30 con SHA-256 `f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7` y el conjunto fijado de diez wheels Linux. Las ruedas se descargan una vez. Opcionalmente, antes de la primera ejecución offline, se puede preparar un archivo determinista para reutilizar la instalación.

```sh
python3.12 -m pip download --only-binary=:all: --require-hashes -r superhunter/product_supply/compile-abi-linux-py312.txt --dest "$NQC_BUILD_KIT"
python3.12 -B -m superhunter.tools.prepare_build_compatibility_cache "$NQC_BUILD_KIT" "$NQC_BUILD_KIT/compile-lib.zip"
export NQC_EVM_LAYOUT_SOURCES="$PWD/upstream"
python3.12 -B -m unittest superhunter.tests.test_product_build_compatibility
```

Dos preparaciones separadas produjeron el mismo archivo, SHA-256 `b0e65cc9be5c323b7991021a66b8b066dee45e55763dbd80d4b6b163911cc205`. En el recorrido con caché se comprueba su contenido y se vuelve a compilar y comparar cada entrada dentro del proceso sin red. La aceptación con instalación efímera y la aceptación con caché coinciden.

El wheel de Crytic Compile declara AGPL-3.0-only. No incorpora un archivo separado con el texto de licencia. Se cotejó con LICENSE del checkout, SHA-256 `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`. Crytic Properties también conserva un aviso AGPL v3. Las dos bibliotecas empleadas de Hardhat y OpenZeppelin Upgrades tienen avisos MIT. Las obligaciones de la distribución del producto siguen pendientes de revisión. [Expresiones declaradas y avisos por wheel](product_supply/compile-abi-wheel-notices.json)
