# SuperHunter · toolkit de contratos

El comando `python3 -m superhunter toolkit` forma parte de la CLI del producto. Usa los 20 repositorios que enumera el plan del PR #133. El catálogo conjunto tiene 212 proyectos. Ocho tienen antecedentes en el catálogo de 200. Los nombres anteriores de Solidity y Wake se resuelven a los mismos commits y árboles que `argotorg/solidity` y `ack3-ai/wake`.

## Primera ejecución

En Linux x86-64 con glibc 2.35 o posterior, usa Python 3.12 con `venv`, pip, setuptools, wheel y packaging disponibles, además de GCC, Git, curl, Node con npm y uv con el backend de construcción uv_build disponible sin conexión. Rich usa Pygments del entorno Python. Ejecuta desde la raíz de la rama del producto. La preparación descarga las dependencias en un directorio nuevo fuera del checkout. Los binarios publicados se fijan por versión y SHA-256. Sus versiones de publicación pueden diferir del commit de sus repositorios de referencia.

```sh
python3 -m superhunter toolkit setup ../nqc-toolkit-runtime
python3 -m superhunter toolkit check --runtime ../nqc-toolkit-runtime > t36.json
```

La preparación inicializa los 20 submódulos directos fijados. La sesión verifica los archivos seguidos por Git en esos checkouts. Las dependencias anidadas conservan los gitlinks de cada proyecto.

La consulta habitual de SuperHunter acepta el mismo entorno. Con un bundle de `review-product`, una invocación comprueba el bundle, ejecuta T36 una vez y contesta las consultas por identidad. `toolkit-matrix` devuelve el resultado de los 20, el commit y el árbol de cada participante y las 210 operaciones de la corrida archivada de los 200. Los dos nombres de Solidity devuelven la misma fila. Lo mismo ocurre con `Ackee-Blockchain/wake` y `ack3-ai/wake`. El comando `check` también publica esa matriz en `product_session`.

```sh
python3 -m superhunter query-product --bundle ../nqc-product-review \
  --toolkit-runtime ../nqc-toolkit-runtime --embedded-root-manifests --source-inventory \
  toolkit-matrix crytic/slither ethereum/solidity Ackee-Blockchain/wake
```

La prueba trabaja en una copia temporal del contrato T36 de NQC. El resultado JSON conserva los nombres de las pruebas, el informe de análisis estático, la propiedad evaluada, la mutación y las herramientas ejecutadas. Un fallo de las pruebas originales o de una etapa obligatoria devuelve un código distinto de cero. Una mutación que sobrevive queda registrada como `detected: false`.

| Repositorios | Operación |
|---|---|
| Solidity y 4naly3er | solc 0.8.24 compila T36. El motor de reglas de 4naly3er consume el AST y el texto de esa misma compilación. SMTChecker con Z3 demuestra que la guarda de longitud extraída de T36 admite entre una y cuatro patas de financiación. La prueba formal cubre esa guarda. |
| Foundry y crytic/properties | Forge ejecuta las ocho pruebas originales y una novena que usa las aserciones de crytic/properties para comprobar los roles del constructor. |
| Wake y Foundry | El generador de enteros de Wake, con semilla 36020, prepara los saldos y beneficios de 18 casos. Forge comprueba cinco condiciones contables por caso con T36 y sus prestamistas simulados. Repite los mismos casos sobre la variante de Gambit. |
| Echidna y Medusa | Cada motor evalúa en una EVM local la propiedad sobre el operador y la estrategia del constructor. Echidna usa 64 llamadas con semilla 1. |
| Gambit | Genera una mutación en la validación del plan. Forge repite la misma suite y registra qué pruebas la detectan. |
| Slither, Manticore y Halmos | El analizador de tipos ABI de Manticore procesa las firmas. Slither calcula los selectores y Halmos los vincula a declaraciones de T36. Las tres lecturas se contrastan con solc. |
| Semgrep y Aderyn | Se compila la gramática Solidity que distribuye Semgrep y se compara su número de funciones con el del AST de solc. El tokenizador y contador de Aderyn miden las líneas de código de la misma fuente. |
| ityfuzz, Kontrol y Mythril | El iterador de bytecode de ityfuzz y el lector de Kontrol cotejan los límites de cada instrucción. Kontrol asocia las instrucciones al código fuente y la tabla de Mythril clasifica los opcodes. |
| Slitherin, Solodit y building-secure-contracts | Las listas de tokens de Slitherin se cotejan con las direcciones literales. Las funciones reconocidas orientan la búsqueda de etiquetas en Solodit y la selección de controles ERC20 del checklist de Crytic. |
| Nuclei | El protocolo de archivos de Nuclei comprueba el JSON local que reúne el contrato, el resumen del catálogo y los resultados de las etapas anteriores. |

La corrida usó ocho motores, un plugin, nueve bibliotecas o componentes y dos fuentes de datos. Slither 0.11.6 y el plugin Slitherin 0.7.2 ejecutaron los 101 y 29 detectores registrados, respectivamente. Slitherin recibe un ajuste en la copia de construcción para leer el nombre de la función llamada con la API de Slither 0.11.6. Una prueba de control comprueba que el detector de visibilidad distinga una función pública llamada internamente de otra que solo se usa externamente.

Semgrep OSS 1.169.0 ejecutó una regla de Solidity. Los números de línea de sus tres coincidencias se cotejaron con el AST de solc. La preparación usa la distribución Linux de Zibby del binario OSS, fijada por SHA-256. Slither y su plugin se instalan en un entorno Python aislado. Se puede repetir `--wheelhouse DIRECTORIO` en `toolkit setup` para instalar las 51 distribuciones Python verificadas desde copias locales.

### Aderyn y la comprobación estricta

La revisión ejecutó el código de métricas de Aderyn y sus dos pruebas de origen. El analizador completo quedó pendiente. Cyfrin retiró los binarios y el registro de Cargo resultó inaccesible en el entorno de prueba. La preparación admite el archivo Linux original de la versión 0.6.8 y comprueba su SHA-256. También admite una compilación del código fijado con la herramienta de Rust declarada por el proyecto y sus dependencias de Cargo. Ambas opciones sirven para añadir Aderyn a un entorno ya preparado. [Estado del proyecto](https://github.com/Cyfrin/aderyn/blob/a902831fcb31a83e97c62e0b7c3a2794f2f2f9a2/README.md)

```sh
python3 -m superhunter toolkit setup ../nqc-toolkit-runtime --aderyn-archive ./aderyn-x86_64-unknown-linux-gnu.tar.xz
# Alternativa para construir desde el commit fijado
python3 -m superhunter toolkit setup ../nqc-toolkit-runtime --build-aderyn
python3 -m superhunter toolkit check --runtime ../nqc-toolkit-runtime --require-all-analyzers
```

El modo estricto exige Slither, Slitherin, Semgrep y Aderyn. La ausencia de cualquiera devuelve código 2 y aparece en el JSON. Un error durante la ejecución de un analizador instalado también hace fallar la corrida. Con Aderyn ausente, la revisión ordinaria y la consulta del producto terminaron con código 0 y la comprobación estricta con código 2.

### Resultado de la sesión

Pasaron las nueve pruebas de Forge y los 18 casos generados por Wake. Seis de las primeras y los 18 casos de Wake detectaron la variante de Gambit. Los componentes coincidieron en seis selectores y 6,517 límites de instrucciones, con 3,551 instrucciones asociadas a la fuente de T36. La consulta del catálogo, la revisión ordinaria y la verificación estricta produjeron la misma matriz de resultados con la red deshabilitada. [Resultados por proyecto y revisiones](product_supply/toolkit-t36-session.json)

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
