# SuperHunter · toolkit de contratos

El comando `python3 -m superhunter toolkit` forma parte de la CLI del producto. Usa los 19 repositorios que enumera el plan del PR #133. El catálogo conjunto tiene 212 proyectos. Coinciden seis nombres y un séptimo proyecto, Solidity, aparece como `ethereum/solidity` y `argotorg/solidity` en el mismo commit y árbol Git.

## Primera ejecución

En Linux x86-64 con glibc 2.35 o posterior, usa Python 3.12 con `venv`, pip, setuptools, wheel y packaging disponibles, además de GCC, Git, curl, Node con npm y uv con el backend de construcción uv_build disponible sin conexión. Rich usa Pygments del entorno Python. Ejecuta desde la raíz de la rama del producto. La preparación descarga las dependencias en un directorio nuevo fuera del checkout. Los binarios publicados se fijan por versión y SHA-256. Sus versiones de publicación pueden diferir del commit de sus repositorios de referencia.

```sh
python3 -m superhunter toolkit setup ../nqc-toolkit-runtime
python3 -m superhunter toolkit check --runtime ../nqc-toolkit-runtime > t36.json
```

La preparación inicializa los 19 submódulos directos fijados. La sesión verifica los archivos seguidos por Git en esos checkouts. Las dependencias anidadas conservan los gitlinks de cada proyecto.

La consulta habitual de SuperHunter acepta el mismo entorno. Con un bundle de `review-product`, una invocación comprueba el bundle, ejecuta T36 una vez y contesta las consultas por identidad. `toolkit-matrix` devuelve el resultado de los 19, el commit y el árbol de cada participante y las 210 operaciones de la corrida archivada de los 200. Los dos nombres de Solidity devuelven la misma fila. El comando `check` también publica esa matriz en `product_session`.

```sh
python3 -m superhunter query-product --bundle ../nqc-product-review \
  --toolkit-runtime ../nqc-toolkit-runtime --embedded-root-manifests --source-inventory \
  toolkit-matrix crytic/slither ethereum/solidity
```

La prueba trabaja en una copia temporal del contrato T36 de NQC. El resultado JSON conserva los nombres de las pruebas, el informe de análisis estático, la propiedad evaluada, la mutación y las herramientas ejecutadas. Un fallo de las pruebas originales o de una etapa obligatoria devuelve un código distinto de cero. Una mutación que sobrevive queda registrada como `detected: false`.

| Repositorios | Operación |
|---|---|
| Solidity y 4naly3er | solc 0.8.24 compila T36. El motor de reglas de 4naly3er consume el AST y el texto de esa misma compilación. SMTChecker con Z3 demuestra que la guarda de longitud extraída de T36 admite entre una y cuatro patas de financiación. La prueba formal cubre esa guarda. |
| Foundry y crytic/properties | Forge ejecuta las ocho pruebas originales y una novena que usa las aserciones de crytic/properties para comprobar los roles del constructor. |
| Echidna y Medusa | Cada motor evalúa en una EVM local la propiedad sobre el operador y la estrategia del constructor. Echidna usa 64 llamadas con semilla 1. |
| Gambit | Genera una mutación en la validación del plan. Forge repite la misma suite y registra qué pruebas la detectan. |
| Slither, Manticore y Halmos | El analizador de tipos ABI de Manticore procesa las firmas. Slither calcula los selectores y Halmos los vincula a declaraciones de T36. Las tres lecturas se contrastan con solc. |
| Semgrep y Aderyn | Se compila la gramática Solidity que distribuye Semgrep y se compara su número de funciones con el del AST de solc. El tokenizador y contador de Aderyn miden las líneas de código de la misma fuente. |
| ityfuzz, Kontrol y Mythril | El iterador de bytecode de ityfuzz y el lector de Kontrol cotejan los límites de cada instrucción. Kontrol asocia las instrucciones al código fuente y la tabla de Mythril clasifica los opcodes. |
| Slitherin, Solodit y building-secure-contracts | Las listas de tokens de Slitherin se cotejan con las direcciones literales. Las funciones reconocidas orientan la búsqueda de etiquetas en Solodit y la selección de controles ERC20 del checklist de Crytic. |
| Nuclei | El protocolo de archivos de Nuclei comprueba el JSON local que reúne el contrato, el resumen del catálogo y los resultados de las etapas anteriores. |

La sesión requiere seis ejecutables de proyecto, diez bibliotecas o partes de proyectos y tres fuentes de datos. Si además están instalados los analizadores completos Slither, Slitherin, Semgrep o Aderyn, sus resultados aparecen en `installed_static_checks`. El informe conserva qué analizadores opcionales faltan. El alcance medido es el contrato T36 y las operaciones anteriores.

La corrida registrada pasó nueve pruebas de Forge. Seis detectaron la variante de Gambit. Los componentes coincidieron en seis selectores y 6,517 límites de instrucciones, con 3,551 instrucciones asociadas a la fuente de T36. Los datos por proyecto y las revisiones están en [el registro de la corrida](product_supply/toolkit-t36-session.json).

## Consulta e importación

La consulta de referencias busca términos en un documento fijado por repositorio y devuelve enlaces al documento y números de línea de las coincidencias. En Solodit también busca por nombre de informe.

```sh
python3 -m superhunter toolkit references ERC20
python3 -m superhunter toolkit reports --report aderyn upstream/aderyn/reports/highs-json-report.json
```

La segunda orden usa un informe de ejemplo del propio Aderyn. Puedes repetir `--report HERRAMIENTA ARCHIVO` con diferentes herramientas, tanto en `reports` como en `check`. Los recuentos externos van en `imported_reports` y conservan la identidad declarada por quien los proporciona. Un archivo importado por sí solo no acredita productor, revisión ni ejecución sobre T36.

| Nombre de importación | Archivo esperado |
|---|---|
| `slither`, `slitherin` | JSON de detectores de Slither. Para Slitherin se cuentan los detectores con prefijo `pess-`. |
| `aderyn`, `semgrep`, `mythril` | Informe JSON nativo. En Mythril se usa el formato `json`. |
| `echidna`, `halmos` | Resumen JSON de campaña o pruebas. |
| `kontrol` | JUnit XML de la prueba. |
| `manticore` | Sección de cobertura de `global.summary`. |
| `ityfuzz` | Contadores de instrucciones y ramas en `coverage.json`. |
| `nuclei` | Eventos JSONL. Se cuentan las coincidencias por severidad. |
