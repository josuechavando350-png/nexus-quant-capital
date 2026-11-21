# Revisión de las 100 identidades del primer lote

La tabla conserva el estado histórico del PR 111. Los recibos posteriores de ambos lotes pueden consultarse en la [sesión conjunta del catálogo](CATALOG_SESSION.md).

El primer lote conserva la pertenencia publicada en `a55602cf6bbba4d79bdb20d5678b4f7ed135b6e6`. La consulta `batch:1` devuelve las filas con sus recibos para la sesión abierta. La tabla documenta el replay de las distribuciones fijadas el 21 de noviembre de 2026. El segundo lote se consulta con `batch:2`.

| Estado | Identidades |
|---|---:|
| Ejecutables con evidencia del producto | 36 |
| Referencias públicas con correspondencias probadas | 2 |
| Bloqueo observado | 2 |
| Fuera del alcance | 27 |
| Pendiente | 33 |

Los doce verificadores de `license_choice_evidence` comprueban la misma propiedad de licencias con el mismo control negativo. Cada fila identifica el ejecutable del proyecto que participó. La columna de pendientes describe la evidencia que falta para el uso solicitado. La columna de alcance aplica al uso propuesto en el catálogo del PR 110.

[Procedimiento de reproducción](PRODUCT_REVIEW.md) · [Catálogo fijado](repositories_200.json) · [Licencias en OSV-Scanner](https://google.github.io/osv-scanner/usage/license-scanning/) · [Modo offline de OSV-Scanner](https://google.github.io/osv-scanner/usage/offline-mode/).

| ID del PR 110 | Repositorio | Estado | Evidencia o motivo |
|---:|---|---|---|
| 136 | anchore/syft | Ejecutable | Inventario Syft por paquete, versión y archivo. Recibo `evidence`. |
| 140 | cdxgen/cdxgen | Ejecutable | SBOM CycloneDX generado desde los manifiestos. Recibo `cyclonedx_evidence`. |
| 142 | guacsec/guac | Ejecutable | Relaciones leídas del SBOM y contrastadas con los manifiestos. Recibo `guac_evidence`. |
| 143 | in-toto/in-toto | Ejecutable | Metadatos de procedencia generados para el expediente local. Recibo `supply.link`. |
| 147 | EmbarkStudios/cargo-deny | Ejecutable | Declaraciones de licencias del workspace de Cargo. Recibo `license_evidence`. |
| 150 | aboutcode-org/scancode-toolkit | Ejecutable | Expresiones reconocidas en los avisos de dependencias. Recibo `license_evidence`. |
| 24 | tree-sitter/tree-sitter | Ejecutable | Ubicaciones de componentes en el JSON del SBOM. Recibo `sbom_location_evidence`. |
| 111 | microsoft/sarif-sdk | Ejecutable | Resultados de revisión de licencias en SARIF. Recibo `sarif_evidence`. |
| 41 | cvc5/cvc5 | Ejecutable | Número mínimo de grupos compatibles de versiones Python. Recibo `evidence`. |
| 45 | tlaplus/tlaplus | Ejecutable | Comprobación del agrupamiento de perfiles. Recibo `profile_grouping_evidence`. |
| 30 | OWASP/ASVS | Referencia | Controles públicos ASVS enlazados al expediente. Recibo `asvs.csv`. |
| 199 | OWASP/CheatSheetSeries | Referencia | Guías públicas consultables desde el expediente. Recibo `asvs-guides.md`. |
| 131 | lief-project/LIEF | Ejecutable | Inventario ELF de los ejecutables de los productores. Recibo `runtime_inventory_evidence`. |
| 157 | deepset-ai/haystack | Ejecutable | Ordenación de avisos de licencias por coincidencia de términos. Recibo `notice_ranking_evidence`. |
| 159 | qdrant/qdrant | Ejecutable | Búsqueda local en los avisos con ubicaciones verificables. Recibo `notice_search_evidence`. |
| 135 | google/osv-scanner | Ejecutable | Registro de identificadores SPDX del proveedor comprobado sobre las expresiones locales y sus avisos de origen. Recibo `spdx_identifier_evidence`. |
| 137 | anchore/grype | Fuera del alcance | La función propuesta usa avisos de vulnerabilidad o paquetes maliciosos. |
| 138 | dependency-check/DependencyCheck | Fuera del alcance | La función propuesta usa avisos de vulnerabilidad o paquetes maliciosos. |
| 139 | DependencyTrack/dependency-track | Ejecutable | Interpretación de expresiones SPDX y grupos de licencias. Recibo `spdx_group_evidence`. |
| 141 | ossf/scorecard | Ejecutable | Detección del archivo de licencia en el commit local y control positivo. Recibo `license_file_evidence`. |
| 144 | ossf/package-analysis | Fuera del alcance | La función propuesta observa el comportamiento de paquetes al ejecutarlos. |
| 145 | ossf/malicious-packages | Fuera del alcance | La función propuesta usa avisos de vulnerabilidad o paquetes maliciosos. |
| 146 | rustsec/rustsec | Ejecutable | Grafo de dependencias reproducido a partir de Cargo.lock. Recibo `lock_graph_evidence`. |
| 22 | Fraunhofer-AISEC/cpg | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 23 | meta/Pysa | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad de código. |
| 25 | ast-grep/ast-grep | Ejecutable | Checksum y rango del componente en el SBOM. Recibo `registry_checksum_evidence`. |
| 101 | meta/infer | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 102 | Ericsson/codechecker | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 103 | cppcheck-opensource/cppcheck | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 104 | PyCQA/bandit | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad de código. |
| 105 | securego/gosec | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad de código. |
| 106 | phpstan/phpstan | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 107 | vimeo/psalm | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 108 | pmd/pmd | Ejecutable | Pasajes de avisos compartidos y rangos en los originales. Recibo `notice_passage_evidence`. |
| 109 | spotbugs/spotbugs | Pendiente | El expediente contiene manifiestos, lockfiles y avisos. Falta una prueba funcional sobre esos datos para este analizador. |
| 110 | find-sec-bugs/find-sec-bugs | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad de código. |
| 17 | argotorg/hevm | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 31 | runtimeverification/evm-semantics | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 43 | diffblue/cbmc | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 44 | model-checking/kani | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 46 | klee/klee | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 120 | esbmc/esbmc | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 121 | seahorn/seahorn | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 122 | dafny-lang/dafny | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 123 | verus-lang/verus | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 124 | GaloisInc/saw-script | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 125 | rocq-prover/rocq | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 126 | FStarLang/FStar | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 127 | verifast/verifast | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 128 | AliveToolkit/alive2 | Ejecutable | Equivalencia de las alternativas mínimas de licencias y rechazo de la alternativa eliminada. Recibo `license_choice_evidence`. |
| 47 | rr-debugger/rr | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 48 | jaegertracing/jaeger | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 50 | strace/strace | Bloqueo observado | El kernel denegó PTRACE_TRACEME al observar la lectura de Cargo.lock. |
| 86 | falcosecurity/falco | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 87 | aquasecurity/tracee | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 88 | cilium/tetragon | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 89 | cilium/hubble | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 90 | inspektor-gadget/inspektor-gadget | Pendiente | La revisión local carece de una comprobación con eventos o trazas de este productor vinculada al inventario. |
| 49 | OWASP/wstg | Pendiente | Falta un control de esta guía aplicable al inventario propio con correspondencia reproducible. |
| 189 | ethereum/consensus-specs | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 190 | ethereum/EIPs | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 191 | crytic/building-secure-contracts | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 200 | OWASP/mastg | Pendiente | Falta un control de esta guía aplicable al inventario propio con correspondencia reproducible. |
| 129 | radareorg/radare2 | Pendiente | Falta una observación de dependencias o licencias reproducida con este analizador binario. |
| 130 | rizinorg/cutter | Pendiente | Falta una observación de dependencias o licencias reproducida con este analizador binario. |
| 132 | capstone-engine/capstone | Pendiente | Falta una observación de dependencias o licencias reproducida con este analizador binario. |
| 133 | DynamoRIO/dynamorio | Pendiente | Falta una observación de dependencias o licencias reproducida con este analizador binario. |
| 134 | qemu/qemu | Ejecutable | Repetición de Syft para ARM64 y paridad con x86-64. Recibo `arm_inventory_evidence`. |
| 1 | usestrix/strix | Fuera del alcance | El propósito del catálogo requiere un agente de investigación web/API. |
| 151 | OpenHands/software-agent-sdk | Pendiente | Falta una función local probada sobre estos datos de inventario o licencias. |
| 152 | SWE-agent/mini-swe-agent | Pendiente | Falta una función local probada sobre estos datos de inventario o licencias. |
| 153 | Aider-AI/aider | Pendiente | Falta una función local probada sobre estos datos de inventario o licencias. |
| 154 | langchain-ai/langgraph | Ejecutable | Clasificación de declaraciones y expresiones observadas por rueda. Recibo `wheel_decision_evidence`. |
| 155 | stanfordnlp/dspy | Pendiente | Falta una función local probada sobre estos datos de inventario o licencias. |
| 156 | huggingface/smolagents | Pendiente | Falta una función local probada sobre estos datos de inventario o licencias. |
| 158 | run-llama/llama_index | Ejecutable | Ventanas de contexto con citas por párrafo y línea. Recibo `citation_evidence`. |
| 160 | pgvector/pgvector | Ejecutable | Similitud de los textos de avisos. Recibo `notice_similarity_evidence`. |
| 2 | zaproxy/zaproxy | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 3 | sqlmapproject/sqlmap | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 4 | schemathesis/schemathesis | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 5 | ffuf/ffuf | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 6 | projectdiscovery/httpx | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 7 | projectdiscovery/katana | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 8 | PortSwigger/turbo-intruder | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 9 | PortSwigger/param-miner | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 10 | hahwul/dalfox | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 11 | projectdiscovery/subfinder | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 12 | foundry-rs/foundry | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 13 | crytic/slither | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 14 | crytic/echidna | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 15 | ack3-ai/wake | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 16 | crytic/medusa | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 18 | crytic/properties | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 19 | SunWeb3Sec/DeFiHackLabs | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 20 | shazow/whatsabi | Pendiente | El expediente de dependencias carece de una aplicación probada del modelo o especificación de Ethereum. |
| 21 | immunefi-team/forge-poc-templates | Fuera del alcance | El propósito del catálogo requiere análisis de seguridad, fuzzing o reproducción de incidentes en contratos. |
| 26 | mitmproxy/mitmproxy | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
| 27 | microsoft/playwright | Bloqueo observado | Chromium terminó durante el arranque con socket() failed: Operation not permitted. |
| 28 | proptest-rs/proptest | Ejecutable | Invariantes de la partición de 200 identidades ante permutaciones y entradas inválidas. Recibo `batch_property_evidence`. |
| 29 | microsoft/restler-fuzzer | Fuera del alcance | La función propuesta requiere tráfico, reconocimiento o pruebas sobre una aplicación o API. |
