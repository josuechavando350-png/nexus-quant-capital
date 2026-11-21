# SUPERHUNTER · Estado de las 200 identidades al 21 de noviembre de 2026

La rama de producto partió de 100 checkouts y 46 identidades con evidencia funcional. El PR 114 incorpora 53 fuentes adicionales, una ejecución nueva y dos referencias técnicas con controles de refutación. El núcleo existente de consulta reúne la evidencia mediante el ID original. La matriz clasifica cada proyecto por su función principal prevista. Los recibos de uso se conceden por separado.

| Indicador | Resultado | Alcance |
|---|---:|---|
| Identidades de catálogo | 200/200 | Nombres e ID de GitHub distintos, unidos al catálogo del PR 110 |
| Revisión identificada | 200/200 | 153 commits y árboles en checkouts locales y 47 commits y árboles contrastados con la API Git de GitHub |
| Fuente incorporada | 153/200 | Submódulos directos en las revisiones catalogadas. Los primeros 100 conservaron commit y árbol |
| Aviso revisado por identidad | 200/200 | 199 expresiones en los avisos directos y un texto MIT tras resolver un enlace. Las referencias parciales y ambiguas se conservan |
| Revisión comercial integral documentada | 0/200 | El inventario documenta evidencias de licencia por archivo y modalidad de uso pendiente |
| Uso funcional acreditado acumulado | 49/200 | 43 ejecutados y seis referencias contrastadas |
| Participación end-to-end en la sesión reproducida | 19/200 | 13 ejecutados y seis referencias. Los restantes recibos históricos conservan su procedencia |
| Sin recibo funcional acumulado | 151/200 | 104 con código incorporado y 47 con metadatos de procedencia |
| Hallazgos originales confirmados | 0 | Los controles de este lote evalúan integridad y compatibilidad de representaciones |

GitHub confirmó los 200 nombres actuales y sus ID numéricos. El recibo de la consulta conserva el digest de las 200 filas. [Resultados de la verificación](product_supply/review-114.json)

Los 200 expedientes de inventario contienen una naturaleza asignada, el propósito propuesto, una revisión, licencia observada y evidencia de procedencia. En el producto, los nombres se consultan con la sesión documentada y la opción `--source-inventory`. Una respuesta documental por ID no aumenta la cobertura funcional. [Receta de reproducción y límites de licencias](SOURCE_AUDIT.md) · [Inventario verificable](product_supply/source-inventory.json) · [Código de la unión](product_source_audit.py) · [Detalle de los submódulos](SOURCE_CHECKOUT.md)

## Evidencia nueva

- **Geth.** La biblioteca de la revisión exacta de go-ethereum reconstruyó el bloque de prueba 25,437,474 de Census. Concordó con EthereumJS, ethers.js y viem en la longitud, el SHA-256 de la codificación RLP y el hash Keccak del encabezado original y del control con gas modificado. Tres compilaciones con dos ubicaciones del código fuente y dos cachés de módulos produjeron el mismo SHA-256 en el perfil `purego`.
- **OpenZeppelin Contracts.** El compilador de Solidity analizó la interfaz IERC20 real y la interfaz histórica IMainnetWeth. Coincidieron los seis métodos de IERC20 en los tipos de entrada y salida, visibilidad y mutabilidad. Un control con retorno alterado discrepó sólo en `balanceOf`.
- **Ethereum consensus-specs.** El producto leyó los tipos y límites del esquema Deneb y comprobó 15 campos presentes en el archivo de Census. Detectó un `gasUsed` fuera de rango y un `logsBloom` truncado. Los dos campos de listas cuyo contenido falta en el archivo se conservaron fuera de alcance.
- **Evaluación de representaciones.** 96 casos generados después de fijar el clasificador, con etiquetas retenidas durante la predicción. TP 48, TN 48, FP 0, FN 0. Los 96 nombres de campo coincidieron y la segunda ejecución reprodujo los hashes. Tiempo de predicción en el primer pase 0.184394 s. Sin consumo de API de pago durante la evaluación. El coste del host no se midió. La medición de precisión de descubrimientos en sistemas desconocidos con un evaluador externo sigue pendiente.

## Verificaciones

Pasaron 183 pruebas focalizadas de Python en 12 módulos, nueve pruebas del verificador de migración en la copia histórica y 528 pruebas del workspace Rust de Census con su toolchain 1.98.1 y red deshabilitada. El verificador de NQC cotejó 642 archivos históricos y encontró cero workflows activos. En los 153 repositorios locales, `git fsck --full --no-reflogs --no-dangling` terminó con código cero y sin diagnósticos. Los objetos prometidos por gitlinks anidados y LFS quedan descritos en el inventario.

Un primer pase de 180 pruebas registró seis fallos y un error porque el registro de QA aún desconocía el módulo de pruebas y tres fuentes. Se corrigió el registro de propietarios y se añadieron controles de enlaces y de identidad ambigua. Durante dos sesiones simultáneas, una repetición rechazó un registro de PMD inesperado. Se limitó la JVM a dos procesadores y 512 MiB de heap y se enviaron sus diagnósticos a stderr. Dos repeticiones simultáneas en checkouts distintos devolvieron las 211 respuestas, idénticas byte a byte. El lector conserva su rechazo de registros inesperados. Los tres recibos nuevos exigen los hashes aceptados de revisión e informe. La suite Python histórica completa y la investigación de vulnerabilidades en laboratorios ciegos externos no se reevaluaron.

| Transcripción | SHA-256 |
|---|---|
| 208 respuestas históricas reproducidas | `4a4757ec107cd88dc698ae30cc62be7b93d651732279afffe2938d4074219f59` |
| 211 respuestas con auditoría, Geth y dos referencias | `729e2e74299c098cef60be43c8342504c4440e6c98fee172b336f6a6af0027c6` |
| Expediente de fuentes y ScanCode | `9fe08694ea198e7872cc954a122fc4bdc4675996a5403cb7344822a89a3bfe3f` |

## Estado por repositorio

En la columna funcional, «previo» conserva un recibo identificado de la sesión histórica y «actual» indica participación en las 211 respuestas. En la columna fuente, «metadatos» indica un commit y un árbol verificados a distancia sin checkout del proyecto. Para los proyectos de intrusión o reproducción ofensiva sólo se admite aquí su evidencia documental. Entre los demás pendientes también hay guías, evaluadores y analizadores que requieren un consumidor defensivo concreto y una prueba antes de acreditar su uso.

| ID | Repositorio | Naturaleza principal | Fuente | Participación acreditada |
|---:|---|---|---|---|
| 1 | usestrix/strix | Framework de agentes | Metadatos | Pendiente · alcance documental |
| 2 | zaproxy/zaproxy | Analizador/verificador | Metadatos | Pendiente |
| 3 | sqlmapproject/sqlmap | Ejecutable | Metadatos | Pendiente · alcance documental |
| 4 | schemathesis/schemathesis | Analizador/verificador | Checkout | Pendiente |
| 5 | ffuf/ffuf | Ejecutable | Metadatos | Pendiente |
| 6 | projectdiscovery/httpx | Ejecutable | Metadatos | Pendiente |
| 7 | projectdiscovery/katana | Ejecutable | Metadatos | Pendiente |
| 8 | PortSwigger/turbo-intruder | Ejecutable | Metadatos | Pendiente · alcance documental |
| 9 | PortSwigger/param-miner | Ejecutable | Metadatos | Pendiente |
| 10 | hahwul/dalfox | Analizador/verificador | Metadatos | Pendiente · alcance documental |
| 11 | projectdiscovery/subfinder | Ejecutable | Metadatos | Pendiente |
| 12 | foundry-rs/foundry | Auxiliar | Checkout | Ejecución · actual |
| 13 | crytic/slither | Analizador/verificador | Checkout | Pendiente |
| 14 | crytic/echidna | Analizador/verificador | Checkout | Pendiente |
| 15 | ack3-ai/wake | Analizador/verificador | Checkout | Ejecución · actual |
| 16 | crytic/medusa | Analizador/verificador | Checkout | Pendiente |
| 17 | argotorg/hevm | Analizador/verificador | Checkout | Pendiente |
| 18 | crytic/properties | Biblioteca/motor | Checkout | Pendiente |
| 19 | SunWeb3Sec/DeFiHackLabs | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 20 | shazow/whatsabi | Biblioteca/motor | Checkout | Pendiente |
| 21 | immunefi-team/forge-poc-templates | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 22 | Fraunhofer-AISEC/cpg | Biblioteca/motor | Checkout | Pendiente |
| 23 | meta/Pysa | Analizador/verificador | Checkout | Pendiente |
| 24 | tree-sitter/tree-sitter | Biblioteca/motor | Checkout | Ejecución · previo |
| 25 | ast-grep/ast-grep | Analizador/verificador | Checkout | Ejecución · previo |
| 26 | mitmproxy/mitmproxy | Ejecutable | Checkout | Pendiente |
| 27 | microsoft/playwright | Biblioteca/motor | Checkout | Pendiente |
| 28 | proptest-rs/proptest | Biblioteca/motor | Checkout | Ejecución · previo |
| 29 | microsoft/restler-fuzzer | Analizador/verificador | Metadatos | Pendiente |
| 30 | OWASP/ASVS | Referencia | Checkout | Referencia · actual |
| 31 | runtimeverification/evm-semantics | Referencia | Checkout | Pendiente |
| 32 | trailofbits/mewt | Auxiliar | Checkout | Pendiente |
| 33 | Jon-Becker/heimdall-rs | Analizador/verificador | Checkout | Pendiente |
| 34 | cdump/evmole | Biblioteca/motor | Checkout | Pendiente |
| 35 | argotorg/solidity | Auxiliar | Checkout | Ejecución · actual |
| 36 | ethereum/execution-specs | Referencia | Checkout | Referencia · actual |
| 37 | ethereum/go-ethereum | Biblioteca/motor | Checkout | Ejecución · actual |
| 38 | bluealloy/revm | Biblioteca/motor | Checkout | Pendiente |
| 39 | OpenZeppelin/openzeppelin-contracts | Biblioteca/motor | Checkout | Referencia · actual |
| 40 | OpenZeppelin/openzeppelin-upgrades | Biblioteca/motor | Checkout | Pendiente |
| 41 | cvc5/cvc5 | Analizador/verificador | Checkout | Ejecución · actual |
| 42 | AFLplusplus/AFLplusplus | Analizador/verificador | Checkout | Pendiente |
| 43 | diffblue/cbmc | Analizador/verificador | Checkout | Ejecución · previo |
| 44 | model-checking/kani | Analizador/verificador | Checkout | Ejecución · previo |
| 45 | tlaplus/tlaplus | Analizador/verificador | Checkout | Ejecución · previo |
| 46 | klee/klee | Analizador/verificador | Checkout | Ejecución · previo |
| 47 | rr-debugger/rr | Auxiliar | Checkout | Pendiente |
| 48 | jaegertracing/jaeger | Auxiliar | Checkout | Pendiente |
| 49 | OWASP/wstg | Referencia | Checkout | Pendiente |
| 50 | strace/strace | Auxiliar | Checkout | Pendiente |
| 51 | s0md3v/Arjun | Ejecutable | Metadatos | Pendiente |
| 52 | maurosoria/dirsearch | Ejecutable | Metadatos | Pendiente |
| 53 | epi052/feroxbuster | Ejecutable | Metadatos | Pendiente |
| 54 | OJ/gobuster | Ejecutable | Metadatos | Pendiente |
| 55 | xnl-h4ck3r/xnLinkFinder | Ejecutable | Metadatos | Pendiente |
| 56 | xnl-h4ck3r/waymore | Ejecutable | Metadatos | Pendiente |
| 57 | projectdiscovery/dnsx | Ejecutable | Checkout | Pendiente |
| 58 | projectdiscovery/naabu | Ejecutable | Metadatos | Pendiente |
| 59 | projectdiscovery/tlsx | Ejecutable | Checkout | Pendiente |
| 60 | d3mondev/puredns | Ejecutable | Metadatos | Pendiente |
| 61 | blechschmidt/massdns | Ejecutable | Checkout | Pendiente |
| 62 | danielmiessler/SecLists | Corpus/laboratorio | Metadatos | Pendiente |
| 63 | EnableSecurity/wafw00f | Ejecutable | Metadatos | Pendiente |
| 64 | lc/gau | Ejecutable | Metadatos | Pendiente |
| 65 | rapid7/recog | Corpus/laboratorio | Checkout | Pendiente |
| 66 | nabla-c0d3/sslyze | Analizador/verificador | Checkout | Pendiente |
| 67 | wapiti-scanner/wapiti | Analizador/verificador | Metadatos | Pendiente |
| 68 | PortSwigger/http-request-smuggler | Ejecutable | Metadatos | Pendiente · alcance documental |
| 69 | fullstorydev/grpcurl | Auxiliar | Checkout | Pendiente |
| 70 | doyensec/inql | Ejecutable | Metadatos | Pendiente |
| 71 | ticarpi/jwt_tool | Ejecutable | Metadatos | Pendiente · alcance documental |
| 72 | testssl/testssl.sh | Analizador/verificador | Checkout | Pendiente |
| 73 | dolevf/graphql-cop | Analizador/verificador | Metadatos | Pendiente |
| 74 | dolevf/graphw00f | Ejecutable | Metadatos | Pendiente |
| 75 | prowler-cloud/prowler | Analizador/verificador | Checkout | Pendiente |
| 76 | kubescape/kubescape | Analizador/verificador | Checkout | Pendiente |
| 77 | aquasecurity/kube-bench | Analizador/verificador | Checkout | Pendiente |
| 78 | RhinoSecurityLabs/pacu | Ejecutable | Metadatos | Pendiente · alcance documental |
| 79 | BishopFox/cloudfox | Ejecutable | Metadatos | Pendiente |
| 80 | cartography-cncf/cartography | Auxiliar | Checkout | Pendiente |
| 81 | DataDog/stratus-red-team | Ejecutable | Metadatos | Pendiente · alcance documental |
| 82 | stackrox/kube-linter | Analizador/verificador | Checkout | Pendiente |
| 83 | cilium/cilium | Biblioteca/motor | Checkout | Pendiente |
| 84 | iann0036/iamlive | Auxiliar | Checkout | Pendiente |
| 85 | salesforce/policy_sentry | Auxiliar | Checkout | Pendiente |
| 86 | falcosecurity/falco | Analizador/verificador | Checkout | Pendiente |
| 87 | aquasecurity/tracee | Analizador/verificador | Checkout | Pendiente |
| 88 | cilium/tetragon | Analizador/verificador | Checkout | Pendiente |
| 89 | cilium/hubble | Auxiliar | Checkout | Pendiente |
| 90 | inspektor-gadget/inspektor-gadget | Auxiliar | Checkout | Pendiente |
| 91 | wireshark/wireshark | Auxiliar | Checkout | Pendiente |
| 92 | secdev/scapy | Biblioteca/motor | Checkout | Pendiente |
| 93 | OISF/suricata | Analizador/verificador | Checkout | Pendiente |
| 94 | OWASP/Nettacker | Ejecutable | Metadatos | Pendiente · alcance documental |
| 95 | the-tcpdump-group/tcpdump | Auxiliar | Checkout | Pendiente |
| 96 | MobSF/Mobile-Security-Framework-MobSF | Analizador/verificador | Metadatos | Pendiente |
| 97 | frida/frida | Biblioteca/motor | Checkout | Pendiente |
| 98 | skylot/jadx | Auxiliar | Checkout | Pendiente |
| 99 | iBotPeaches/Apktool | Auxiliar | Checkout | Pendiente |
| 100 | sensepost/objection | Ejecutable | Metadatos | Pendiente · alcance documental |
| 101 | meta/infer | Analizador/verificador | Checkout | Pendiente |
| 102 | Ericsson/codechecker | Analizador/verificador | Checkout | Pendiente |
| 103 | cppcheck-opensource/cppcheck | Analizador/verificador | Checkout | Pendiente |
| 104 | PyCQA/bandit | Analizador/verificador | Checkout | Pendiente |
| 105 | securego/gosec | Analizador/verificador | Checkout | Pendiente |
| 106 | phpstan/phpstan | Analizador/verificador | Checkout | Pendiente |
| 107 | vimeo/psalm | Analizador/verificador | Checkout | Pendiente |
| 108 | pmd/pmd | Analizador/verificador | Checkout | Ejecución · actual |
| 109 | spotbugs/spotbugs | Analizador/verificador | Checkout | Pendiente |
| 110 | find-sec-bugs/find-sec-bugs | Analizador/verificador | Checkout | Pendiente |
| 111 | microsoft/sarif-sdk | Biblioteca/motor | Checkout | Ejecución · previo |
| 112 | google/honggfuzz | Analizador/verificador | Checkout | Pendiente |
| 113 | CodeIntelligenceTesting/jazzer | Analizador/verificador | Checkout | Pendiente |
| 114 | google/atheris | Biblioteca/motor | Checkout | Pendiente |
| 115 | rust-fuzz/cargo-fuzz | Analizador/verificador | Checkout | Pendiente |
| 116 | google/fuzztest | Biblioteca/motor | Checkout | Pendiente |
| 117 | google/oss-fuzz | Auxiliar | Checkout | Pendiente |
| 118 | trailofbits/polytracker | Analizador/verificador | Checkout | Pendiente |
| 119 | google/clusterfuzzlite | Auxiliar | Checkout | Pendiente |
| 120 | esbmc/esbmc | Analizador/verificador | Checkout | Ejecución · previo |
| 121 | seahorn/seahorn | Analizador/verificador | Checkout | Ejecución · previo |
| 122 | dafny-lang/dafny | Analizador/verificador | Checkout | Ejecución · previo |
| 123 | verus-lang/verus | Analizador/verificador | Checkout | Ejecución · previo |
| 124 | GaloisInc/saw-script | Analizador/verificador | Checkout | Ejecución · previo |
| 125 | rocq-prover/rocq | Analizador/verificador | Checkout | Ejecución · previo |
| 126 | FStarLang/FStar | Analizador/verificador | Checkout | Ejecución · previo |
| 127 | verifast/verifast | Analizador/verificador | Checkout | Ejecución · previo |
| 128 | AliveToolkit/alive2 | Analizador/verificador | Checkout | Ejecución · previo |
| 129 | radareorg/radare2 | Analizador/verificador | Checkout | Pendiente |
| 130 | rizinorg/cutter | Auxiliar | Checkout | Pendiente |
| 131 | lief-project/LIEF | Biblioteca/motor | Checkout | Ejecución · previo |
| 132 | capstone-engine/capstone | Biblioteca/motor | Checkout | Pendiente |
| 133 | DynamoRIO/dynamorio | Biblioteca/motor | Checkout | Pendiente |
| 134 | qemu/qemu | Biblioteca/motor | Checkout | Ejecución · previo |
| 135 | google/osv-scanner | Analizador/verificador | Checkout | Ejecución · previo |
| 136 | anchore/syft | Auxiliar | Checkout | Ejecución · actual |
| 137 | anchore/grype | Analizador/verificador | Checkout | Pendiente |
| 138 | dependency-check/DependencyCheck | Analizador/verificador | Checkout | Pendiente |
| 139 | DependencyTrack/dependency-track | Auxiliar | Checkout | Ejecución · previo |
| 140 | cdxgen/cdxgen | Auxiliar | Checkout | Ejecución · previo |
| 141 | ossf/scorecard | Analizador/verificador | Checkout | Ejecución · previo |
| 142 | guacsec/guac | Auxiliar | Checkout | Ejecución · previo |
| 143 | in-toto/in-toto | Auxiliar | Checkout | Ejecución · actual |
| 144 | ossf/package-analysis | Analizador/verificador | Checkout | Pendiente |
| 145 | ossf/malicious-packages | Corpus/laboratorio | Checkout | Pendiente |
| 146 | rustsec/rustsec | Auxiliar | Checkout | Ejecución · previo |
| 147 | EmbarkStudios/cargo-deny | Analizador/verificador | Checkout | Ejecución · previo |
| 148 | trufflesecurity/trufflehog | Analizador/verificador | Checkout | Pendiente |
| 149 | betterleaks/betterleaks | Analizador/verificador | Checkout | Pendiente |
| 150 | aboutcode-org/scancode-toolkit | Analizador/verificador | Checkout | Ejecución · previo |
| 151 | OpenHands/software-agent-sdk | Framework de agentes | Checkout | Pendiente |
| 152 | SWE-agent/mini-swe-agent | Framework de agentes | Checkout | Pendiente |
| 153 | Aider-AI/aider | Framework de agentes | Checkout | Pendiente |
| 154 | langchain-ai/langgraph | Framework de agentes | Checkout | Ejecución · previo |
| 155 | stanfordnlp/dspy | Framework de agentes | Checkout | Pendiente |
| 156 | huggingface/smolagents | Framework de agentes | Checkout | Pendiente |
| 157 | deepset-ai/haystack | Framework de agentes | Checkout | Ejecución · actual |
| 158 | run-llama/llama_index | Framework de agentes | Checkout | Ejecución · previo |
| 159 | qdrant/qdrant | Biblioteca/motor | Checkout | Ejecución · actual |
| 160 | pgvector/pgvector | Biblioteca/motor | Checkout | Ejecución · previo |
| 161 | vllm-project/vllm | Biblioteca/motor | Checkout | Pendiente |
| 162 | ggml-org/llama.cpp | Biblioteca/motor | Checkout | Pendiente |
| 163 | sgl-project/sglang | Biblioteca/motor | Checkout | Pendiente |
| 164 | huggingface/transformers | Biblioteca/motor | Checkout | Pendiente |
| 165 | langfuse/langfuse | Auxiliar | Checkout | Pendiente |
| 166 | vibrantlabsai/ragas | Analizador/verificador | Checkout | Pendiente |
| 167 | promptfoo/promptfoo | Analizador/verificador | Checkout | Pendiente |
| 168 | UKGovernmentBEIS/inspect_ai | Analizador/verificador | Checkout | Pendiente |
| 169 | NVIDIA/garak | Analizador/verificador | Metadatos | Pendiente |
| 170 | bountybench/bountybench | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 171 | NomicFoundation/hardhat | Auxiliar | Checkout | Pendiente |
| 172 | ethers-io/ethers.js | Biblioteca/motor | Checkout | Ejecución · actual |
| 173 | wevm/viem | Biblioteca/motor | Checkout | Ejecución · actual |
| 174 | ethereumjs/ethereumjs-monorepo | Biblioteca/motor | Checkout | Ejecución · actual |
| 175 | paradigmxyz/reth | Biblioteca/motor | Checkout | Pendiente |
| 176 | besu-eth/besu | Biblioteca/motor | Checkout | Pendiente |
| 177 | ethereum/hive | Auxiliar | Checkout | Pendiente |
| 178 | crytic/crytic-compile | Auxiliar | Checkout | Pendiente |
| 179 | smartbugs/smartbugs | Analizador/verificador | Metadatos | Pendiente |
| 180 | LiteSVM/litesvm | Biblioteca/motor | Checkout | Pendiente |
| 181 | anza-xyz/mollusk | Biblioteca/motor | Checkout | Pendiente |
| 182 | otter-sec/anchor | Biblioteca/motor | Checkout | Pendiente |
| 183 | anza-xyz/agave | Biblioteca/motor | Checkout | Pendiente |
| 184 | lfdt-ibc/ibc-go | Biblioteca/motor | Checkout | Pendiente |
| 185 | CosmWasm/cosmwasm | Biblioteca/motor | Checkout | Pendiente |
| 186 | cosmos/cosmos-sdk | Biblioteca/motor | Checkout | Pendiente |
| 187 | MystenLabs/sui | Biblioteca/motor | Checkout | Pendiente |
| 188 | starkware-libs/cairo | Biblioteca/motor | Checkout | Pendiente |
| 189 | ethereum/consensus-specs | Referencia | Checkout | Referencia · actual |
| 190 | ethereum/EIPs | Referencia | Checkout | Referencia · actual |
| 191 | crytic/building-secure-contracts | Referencia | Metadatos | Pendiente |
| 192 | theredguild/damn-vulnerable-defi | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 193 | OpenZeppelin/ethernaut | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 194 | juice-shop/juice-shop | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 195 | WebGoat/WebGoat | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 196 | OWASP/crAPI | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 197 | digininja/DVWA | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 198 | vulhub/vulhub | Corpus/laboratorio | Metadatos | Pendiente · alcance documental |
| 199 | OWASP/CheatSheetSeries | Referencia | Checkout | Referencia · actual |
| 200 | OWASP/mastg | Referencia | Checkout | Pendiente |
