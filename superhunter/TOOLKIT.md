# SuperHunter · toolkit de contratos

El comando `python3 -m superhunter toolkit` forma parte de la CLI del producto. Usa los 19 repositorios que enumera el plan del PR #133. Seis ya pertenecían al catálogo anterior de 200.

## Primera ejecución

En Linux x86-64 con glibc 2.35 o posterior, usa Python 3.12 con `venv`, pip, setuptools, wheel y packaging disponibles, además de GCC, Git, curl, Node con npm y uv. Ejecuta desde la raíz de la rama del producto. La preparación descarga las dependencias en un directorio nuevo fuera del checkout. Los binarios publicados se fijan por versión y SHA-256. Sus versiones de publicación pueden diferir del commit de sus repositorios de referencia.

```sh
python3 -m superhunter toolkit setup ../nqc-toolkit-runtime
python3 -m superhunter toolkit check --runtime ../nqc-toolkit-runtime > t36.json
```

La prueba trabaja en una copia temporal del contrato T36 de NQC. El resultado JSON conserva los nombres de las pruebas, el informe de análisis estático, la propiedad evaluada, la mutación y las herramientas ejecutadas. Un fallo de las pruebas originales o de una etapa obligatoria devuelve un código distinto de cero. Una mutación que sobrevive queda registrada como `detected: false`.

| Repositorios | Operación |
|---|---|
| Solidity y 4naly3er | solc 0.8.24 compila T36. El motor de reglas de 4naly3er consume el AST y el texto de esa misma compilación. SMTChecker con Z3 demuestra que la guarda de longitud extraída de T36 admite entre una y cuatro patas de financiación. La prueba formal cubre esa guarda. |
| Foundry y crytic/properties | Forge ejecuta las ocho pruebas originales y una novena que usa las aserciones de crytic/properties para comprobar los roles del constructor. |
| Echidna y Medusa | Cada motor evalúa en una EVM local la propiedad sobre el operador y la estrategia del constructor. Echidna usa 64 llamadas con semilla 1. |
| Gambit | Genera una mutación en la validación del plan. Forge repite la misma suite y registra qué pruebas la detectan. |
| Slither, Slitherin, Aderyn y Semgrep | Si están instalados, la CLI los usa con el mismo contrato. Reconoce el plugin Slitherin entre los detectores registrados. Semgrep revisa las llamadas de bajo nivel al token con una regla local. Los ausentes figuran en `static_tools_unavailable`. |
| Halmos, Kontrol, Manticore, Mythril, ityfuzz y Nuclei | Lectura de informes locales en sus formatos nativos. |
| Solodit y building-secure-contracts | Consulta por términos en las etiquetas e índice de informes de Solodit y en el checklist de revisión. |

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
