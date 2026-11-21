# SUPERHUNTER — catálogo público de 200 repositorios para integrar

**Decisión de producto (usuario, 2026-11-21):** se planea integrar **200 proyectos diferentes** en NQC/SUPERHUNTER. Este commit **publica únicamente el inventario**: no clona código, no instala herramientas, no ejecuta scanners, no cambia NQC financiero ni habilita workflows.

**Integraciones nuevas efectuadas por esta publicación: 0.** Todos los proyectos están en estado `CATALOGUED_FOR_INTEGRATION`; las integraciones de laboratorio preexistentes deben verificarse por separado, sin degradar su evidencia.

- **200/200 nombres `owner/repo` únicos** (insensible a mayúsculas); 21 de la primera lista, 29 de la segunda y 150 de la tercera.
- **7 nombres** ya estaban en el catálogo histórico de 50 candidatos de SuperHunter. **No se deberán crear dos integraciones del mismo componente**; conservar un solo adaptador y referenciar ambos catálogos. Coincidencias: zaproxy/zaproxy, projectdiscovery/katana, foundry-rs/foundry, crytic/slither, crytic/echidna, crytic/medusa, SunWeb3Sec/DeFiHackLabs.
- El resto son candidatos documentales, **no hallazgos**, no porcentaje de detección, no promesa de 10/10, ni autorización para pruebas en terceros.
- Los proyectos tienen licencias concretas; **uso gratuito** no equivale a ausencia de licencia. Validar condiciones del commit y componentes antes de instalar, modificar o redistribuir. Modelos, APIs, infraestructura y servicios pueden generar gastos.
- Algunas herramientas comparten motores o funciones; proyectos distintos no son capacidades independientes. Evaluar consolidación mediante pruebas comparables.
- Antes de cualquier integración: alcance autorizado por objetivo/operación, commit fijado y SBOM, adaptador de entrada/salida tipada, aislamiento, tests positivos/negativos/adversariales, evidencia privada y replay independiente, costo y mejora medidos.
- Preservar `ci/`, `migration/`, `nqc-census/` y todos los bytes históricos. No activar trading, firma, envío de transacciones, despliegues, CI, notificaciones o envíos automáticos de reportes.

**JSON procesable:** [SUPERHUNTER_REPOSITORIES_200.json](SUPERHUNTER_REPOSITORIES_200.json)

## Inventario completo

| Nº | Proyecto GitHub | Área | Función distintiva para evaluar | Licencia declarada en la selección |
|---:|---|---|---|---|
| 1 | [usestrix/strix](https://github.com/usestrix/strix) | AGENTES | Agente para investigación web/API con herramientas y coordinación | Apache-2.0 |
| 2 | [zaproxy/zaproxy](https://github.com/zaproxy/zaproxy) | WEB | Proxy y análisis dinámico de aplicaciones web | Apache-2.0 |
| 3 | [sqlmapproject/sqlmap](https://github.com/sqlmapproject/sqlmap) | WEB | Análisis especializado de inyección SQL | GPL-2.0+ |
| 4 | [schemathesis/schemathesis](https://github.com/schemathesis/schemathesis) | API | Pruebas generativas sobre especificaciones API | MIT |
| 5 | [ffuf/ffuf](https://github.com/ffuf/ffuf) | WEB | Fuzzing y descubrimiento de contenido HTTP | MIT |
| 6 | [projectdiscovery/httpx](https://github.com/projectdiscovery/httpx) | RECON | Identificación y caracterización de servicios HTTP | MIT |
| 7 | [projectdiscovery/katana](https://github.com/projectdiscovery/katana) | RECON | Recorrido de aplicaciones y extracción de rutas | MIT |
| 8 | [PortSwigger/turbo-intruder](https://github.com/PortSwigger/turbo-intruder) | WEB | Pruebas HTTP altamente configurables y concurrentes | AGPL-3.0 |
| 9 | [PortSwigger/param-miner](https://github.com/PortSwigger/param-miner) | WEB | Descubrimiento de parámetros y cabeceras implícitas | Apache-2.0 |
| 10 | [hahwul/dalfox](https://github.com/hahwul/dalfox) | WEB | Análisis especializado de XSS | MIT |
| 11 | [projectdiscovery/subfinder](https://github.com/projectdiscovery/subfinder) | RECON | Descubrimiento pasivo de subdominios | MIT |
| 12 | [foundry-rs/foundry](https://github.com/foundry-rs/foundry) | EVM | Laboratorio EVM y pruebas reproducibles de contratos | MIT OR Apache-2.0 |
| 13 | [crytic/slither](https://github.com/crytic/slither) | EVM | Análisis estático y representación de contratos Solidity | AGPL-3.0 |
| 14 | [crytic/echidna](https://github.com/crytic/echidna) | EVM | Fuzzing de invariantes sobre contratos | AGPL-3.0 |
| 15 | [ack3-ai/wake](https://github.com/ack3-ai/wake) | EVM | Framework Python para pruebas y fuzzing de contratos | ISC |
| 16 | [crytic/medusa](https://github.com/crytic/medusa) | EVM | Fuzzer EVM paralelo guiado por cobertura | AGPL-3.0 |
| 17 | [argotorg/hevm](https://github.com/argotorg/hevm) | FORMAL | Ejecución simbólica y concreta de EVM | AGPL-3.0 |
| 18 | [crytic/properties](https://github.com/crytic/properties) | EVM | Biblioteca de propiedades de estándares de tokens y vaults | AGPL-3.0 |
| 19 | [SunWeb3Sec/DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) | LAB | Reproducciones históricas de incidentes DeFi | Apache-2.0 |
| 20 | [shazow/whatsabi](https://github.com/shazow/whatsabi) | EVM | Inferencia de ABI y análisis de proxies por bytecode | MIT |
| 21 | [immunefi-team/forge-poc-templates](https://github.com/immunefi-team/forge-poc-templates) | LAB | Plantillas de evidencia y PoC para Immunefi | LGPL-3.0 |
| 22 | [Fraunhofer-AISEC/cpg](https://github.com/Fraunhofer-AISEC/cpg) | CODIGO | Code property graphs para relaciones y flujos del programa | Apache-2.0 |
| 23 | [meta/Pysa](https://github.com/meta/Pysa) | CODIGO | Análisis estático de seguridad y taint para Python | MIT |
| 24 | [tree-sitter/tree-sitter](https://github.com/tree-sitter/tree-sitter) | CODIGO | Parsing incremental estructurado de código | MIT |
| 25 | [ast-grep/ast-grep](https://github.com/ast-grep/ast-grep) | CODIGO | Búsqueda de patrones estructurales en AST | MIT |
| 26 | [mitmproxy/mitmproxy](https://github.com/mitmproxy/mitmproxy) | WEB | Interceptación y análisis programable de tráfico TLS/HTTP | MIT |
| 27 | [microsoft/playwright](https://github.com/microsoft/playwright) | WEB | Reproducción de recorridos y estados de navegador | Apache-2.0 |
| 28 | [proptest-rs/proptest](https://github.com/proptest-rs/proptest) | FUZZ | Property-based testing y reducción de casos en Rust | MIT OR Apache-2.0 |
| 29 | [microsoft/restler-fuzzer](https://github.com/microsoft/restler-fuzzer) | API | Fuzzing de secuencias con estado en APIs REST | MIT |
| 30 | [OWASP/ASVS](https://github.com/OWASP/ASVS) | METODO | Estándar de requisitos verificables de seguridad web | CC-BY-SA-4.0 |
| 31 | [runtimeverification/evm-semantics](https://github.com/runtimeverification/evm-semantics) | FORMAL | Semántica formal K de la EVM | BSD-3-Clause |
| 32 | [trailofbits/mewt](https://github.com/trailofbits/mewt) | PRUEBAS | Pruebas de mutación para medir fuerza de tests | AGPL-3.0 |
| 33 | [Jon-Becker/heimdall-rs](https://github.com/Jon-Becker/heimdall-rs) | EVM | Desensamblado y reconstrucción de bytecode EVM | MIT |
| 34 | [cdump/evmole](https://github.com/cdump/evmole) | EVM | Extracción de selectores y estructuras de bytecode | MIT |
| 35 | [argotorg/solidity](https://github.com/argotorg/solidity) | EVM | Compilador Solidity y comprobador SMT integrado | GPL-3.0 |
| 36 | [ethereum/execution-specs](https://github.com/ethereum/execution-specs) | EVM | Especificación ejecutable Python de Ethereum | CC0-1.0 |
| 37 | [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) | EVM | Cliente Geth para ejecución y trazas de Ethereum | LGPL-3.0 + GPL-3.0 |
| 38 | [bluealloy/revm](https://github.com/bluealloy/revm) | EVM | EVM embebible en Rust para ejecución controlada | MIT |
| 39 | [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) | EVM | Implementaciones de referencia de estándares y permisos | MIT |
| 40 | [OpenZeppelin/openzeppelin-upgrades](https://github.com/OpenZeppelin/openzeppelin-upgrades) | EVM | Validación de cambios y layouts de contratos upgradeables | MIT |
| 41 | [cvc5/cvc5](https://github.com/cvc5/cvc5) | FORMAL | Solver SMT alternativo con pruebas de restricciones | BSD-3-Clause mod. |
| 42 | [AFLplusplus/AFLplusplus](https://github.com/AFLplusplus/AFLplusplus) | FUZZ | Fuzzing nativo guiado por cobertura | AGPL-3.0+ |
| 43 | [diffblue/cbmc](https://github.com/diffblue/cbmc) | FORMAL | Model checking acotado de programas C/C++ | BSD-4-Clause |
| 44 | [model-checking/kani](https://github.com/model-checking/kani) | FORMAL | Verificación de propiedades de programas Rust | MIT OR Apache-2.0 |
| 45 | [tlaplus/tlaplus](https://github.com/tlaplus/tlaplus) | FORMAL | Comprobación de modelos de estados y concurrencia | MIT |
| 46 | [klee/klee](https://github.com/klee/klee) | FORMAL | Ejecución simbólica sobre LLVM | UIUC/NCSA |
| 47 | [rr-debugger/rr](https://github.com/rr-debugger/rr) | OBSERVACION | Grabación y replay de procesos Linux | MIT + terceros |
| 48 | [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | OBSERVACION | Visualización y consulta de trazas distribuidas | Apache-2.0 |
| 49 | [OWASP/wstg](https://github.com/OWASP/wstg) | METODO | Guía metodológica de comprobaciones de seguridad web | CC-BY-SA-4.0 |
| 50 | [strace/strace](https://github.com/strace/strace) | OBSERVACION | Trazas de llamadas al sistema de procesos Linux | LGPL-2.1+ |
| 51 | [s0md3v/Arjun](https://github.com/s0md3v/Arjun) | RECON | Descubrimiento de parámetros HTTP no evidentes | AGPL-3.0 |
| 52 | [maurosoria/dirsearch](https://github.com/maurosoria/dirsearch) | RECON | Enumeración de rutas y archivos web | GPL-2.0+ |
| 53 | [epi052/feroxbuster](https://github.com/epi052/feroxbuster) | RECON | Descubrimiento recursivo de contenido web | MIT |
| 54 | [OJ/gobuster](https://github.com/OJ/gobuster) | RECON | Enumeración de rutas DNS y hosts virtuales | Apache-2.0 |
| 55 | [xnl-h4ck3r/xnLinkFinder](https://github.com/xnl-h4ck3r/xnLinkFinder) | RECON | Extracción de endpoints y parámetros de recursos web | MIT |
| 56 | [xnl-h4ck3r/waymore](https://github.com/xnl-h4ck3r/waymore) | RECON | Recuperación de respuestas históricas web | MIT |
| 57 | [projectdiscovery/dnsx](https://github.com/projectdiscovery/dnsx) | RECON | Consultas y validaciones DNS | MIT |
| 58 | [projectdiscovery/naabu](https://github.com/projectdiscovery/naabu) | RECON | Identificación de puertos accesibles | MIT |
| 59 | [projectdiscovery/tlsx](https://github.com/projectdiscovery/tlsx) | RECON | Recopilación de metadatos TLS | MIT |
| 60 | [d3mondev/puredns](https://github.com/d3mondev/puredns) | RECON | Resolución DNS con filtros wildcard | GPL-3.0 |
| 61 | [blechschmidt/massdns](https://github.com/blechschmidt/massdns) | RECON | Resolución masiva de nombres DNS | GPL-3.0 |
| 62 | [danielmiessler/SecLists](https://github.com/danielmiessler/SecLists) | LAB | Diccionarios y datos de ensayo de seguridad | MIT |
| 63 | [EnableSecurity/wafw00f](https://github.com/EnableSecurity/wafw00f) | RECON | Identificación de productos WAF | BSD-3-Clause |
| 64 | [lc/gau](https://github.com/lc/gau) | RECON | Recuperación de URLs de fuentes públicas | MIT |
| 65 | [rapid7/recog](https://github.com/rapid7/recog) | RECON | Biblioteca de fingerprints de servicios | BSD-2-Clause |
| 66 | [nabla-c0d3/sslyze](https://github.com/nabla-c0d3/sslyze) | WEB | Auditoría de configuración TLS | AGPL-3.0 |
| 67 | [wapiti-scanner/wapiti](https://github.com/wapiti-scanner/wapiti) | WEB | Analizador web dinámico automatizable | GPL-2.0 |
| 68 | [PortSwigger/http-request-smuggler](https://github.com/PortSwigger/http-request-smuggler) | WEB | Investigación de desincronización HTTP | Apache-2.0 |
| 69 | [fullstorydev/grpcurl](https://github.com/fullstorydev/grpcurl) | API | Exploración y llamadas a servicios gRPC | MIT |
| 70 | [doyensec/inql](https://github.com/doyensec/inql) | API | Reconocimiento de esquemas y pruebas GraphQL | Apache-2.0 |
| 71 | [ticarpi/jwt_tool](https://github.com/ticarpi/jwt_tool) | WEB | Inspección de validación de tokens JWT | GPL-3.0 |
| 72 | [testssl/testssl.sh](https://github.com/testssl/testssl.sh) | WEB | Auditoría de protocolos y certificados TLS | GPL-2.0 |
| 73 | [dolevf/graphql-cop](https://github.com/dolevf/graphql-cop) | API | Comprobaciones de seguridad comunes de GraphQL | MIT |
| 74 | [dolevf/graphw00f](https://github.com/dolevf/graphw00f) | API | Fingerprints de motores GraphQL | BSD-3-Clause |
| 75 | [prowler-cloud/prowler](https://github.com/prowler-cloud/prowler) | CLOUD | Evaluación de controles y configuraciones cloud | Apache-2.0 |
| 76 | [kubescape/kubescape](https://github.com/kubescape/kubescape) | CLOUD | Análisis de seguridad de Kubernetes | Apache-2.0 |
| 77 | [aquasecurity/kube-bench](https://github.com/aquasecurity/kube-bench) | CLOUD | Controles CIS para Kubernetes | Apache-2.0 |
| 78 | [RhinoSecurityLabs/pacu](https://github.com/RhinoSecurityLabs/pacu) | CLOUD | Marco de investigación de permisos AWS | BSD-3-Clause |
| 79 | [BishopFox/cloudfox](https://github.com/BishopFox/cloudfox) | CLOUD | Relaciones entre recursos y permisos cloud | MIT |
| 80 | [cartography-cncf/cartography](https://github.com/cartography-cncf/cartography) | CLOUD | Grafo de activos e identidades de infraestructura | Apache-2.0 |
| 81 | [DataDog/stratus-red-team](https://github.com/DataDog/stratus-red-team) | CLOUD | Emulación controlada de técnicas cloud | Apache-2.0 |
| 82 | [stackrox/kube-linter](https://github.com/stackrox/kube-linter) | CLOUD | Análisis de manifiestos y políticas Kubernetes | Apache-2.0 |
| 83 | [cilium/cilium](https://github.com/cilium/cilium) | CLOUD | Implementación eBPF de redes y políticas | Apache-2.0 + componentes |
| 84 | [iann0036/iamlive](https://github.com/iann0036/iamlive) | CLOUD | Inferencia de acciones IAM desde llamadas observadas | MIT |
| 85 | [salesforce/policy_sentry](https://github.com/salesforce/policy_sentry) | CLOUD | Análisis de privilegios y políticas AWS | MIT |
| 86 | [falcosecurity/falco](https://github.com/falcosecurity/falco) | OBSERVACION | Reglas para eventos de seguridad del sistema | Apache-2.0 |
| 87 | [aquasecurity/tracee](https://github.com/aquasecurity/tracee) | OBSERVACION | Detección de eventos Linux mediante eBPF | Apache-2.0 |
| 88 | [cilium/tetragon](https://github.com/cilium/tetragon) | OBSERVACION | Telemetría de procesos e identidades | Apache-2.0 + componentes |
| 89 | [cilium/hubble](https://github.com/cilium/hubble) | OBSERVACION | Visibilidad de comunicaciones entre servicios | Apache-2.0 |
| 90 | [inspektor-gadget/inspektor-gadget](https://github.com/inspektor-gadget/inspektor-gadget) | OBSERVACION | Instrumentación de Linux/Kubernetes con eBPF | Apache-2.0 + componentes |
| 91 | [wireshark/wireshark](https://github.com/wireshark/wireshark) | RED | Análisis de paquetes y protocolos | GPL-2.0 |
| 92 | [secdev/scapy](https://github.com/secdev/scapy) | RED | Generación y análisis programable de paquetes | GPL-2.0 |
| 93 | [OISF/suricata](https://github.com/OISF/suricata) | RED | IDS y análisis de tráfico de red | GPL-2.0 |
| 94 | [OWASP/Nettacker](https://github.com/OWASP/Nettacker) | RED | Reconocimiento y comprobaciones multiprotocolo | Apache-2.0 |
| 95 | [the-tcpdump-group/tcpdump](https://github.com/the-tcpdump-group/tcpdump) | RED | Captura de paquetes para investigación reproducible | BSD-3-Clause |
| 96 | [MobSF/Mobile-Security-Framework-MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF) | MOVIL | Análisis estático y dinámico de apps móviles | GPL-3.0 |
| 97 | [frida/frida](https://github.com/frida/frida) | MOVIL | Instrumentación dinámica de procesos | wxWindows-3.1 + componentes |
| 98 | [skylot/jadx](https://github.com/skylot/jadx) | MOVIL | Decompilación de bytecode Android/Java | Apache-2.0 |
| 99 | [iBotPeaches/Apktool](https://github.com/iBotPeaches/Apktool) | MOVIL | Decodificación de recursos APK | Apache-2.0 |
| 100 | [sensepost/objection](https://github.com/sensepost/objection) | MOVIL | Inspección móvil dinámica sobre Frida | GPL-3.0 |
| 101 | [meta/infer](https://github.com/meta/infer) | CODIGO | Análisis estático de Java C C++ y Objective-C | MIT + opcionales |
| 102 | [Ericsson/codechecker](https://github.com/Ericsson/codechecker) | CODIGO | Coordinación y seguimiento de analizadores | Apache-2.0 con excepción |
| 103 | [cppcheck-opensource/cppcheck](https://github.com/cppcheck-opensource/cppcheck) | CODIGO | Detección de defectos C/C++ | GPL-3.0+ |
| 104 | [PyCQA/bandit](https://github.com/PyCQA/bandit) | CODIGO | Detección de patrones inseguros Python | Apache-2.0 |
| 105 | [securego/gosec](https://github.com/securego/gosec) | CODIGO | Reglas de seguridad para código Go | Apache-2.0 |
| 106 | [phpstan/phpstan](https://github.com/phpstan/phpstan) | CODIGO | Análisis de tipos y errores PHP | MIT |
| 107 | [vimeo/psalm](https://github.com/vimeo/psalm) | CODIGO | Análisis de programas PHP | MIT |
| 108 | [pmd/pmd](https://github.com/pmd/pmd) | CODIGO | Análisis estático multilenguaje configurable | BSD/Apache-2.0 |
| 109 | [spotbugs/spotbugs](https://github.com/spotbugs/spotbugs) | CODIGO | Análisis de defectos en bytecode Java | LGPL-2.1 |
| 110 | [find-sec-bugs/find-sec-bugs](https://github.com/find-sec-bugs/find-sec-bugs) | CODIGO | Reglas de seguridad complementarias de SpotBugs | LGPL-3.0 |
| 111 | [microsoft/sarif-sdk](https://github.com/microsoft/sarif-sdk) | CODIGO | Modelo de informes SARIF para correlación de alertas | MIT |
| 112 | [google/honggfuzz](https://github.com/google/honggfuzz) | FUZZ | Fuzzing nativo guiado por cobertura | Apache-2.0 |
| 113 | [CodeIntelligenceTesting/jazzer](https://github.com/CodeIntelligenceTesting/jazzer) | FUZZ | Fuzzing en proceso para JVM | Apache-2.0 |
| 114 | [google/atheris](https://github.com/google/atheris) | FUZZ | Fuzzing de Python y extensiones | Apache-2.0 |
| 115 | [rust-fuzz/cargo-fuzz](https://github.com/rust-fuzz/cargo-fuzz) | FUZZ | Integración de libFuzzer para Rust | MIT OR Apache-2.0 |
| 116 | [google/fuzztest](https://github.com/google/fuzztest) | FUZZ | Pruebas de propiedades y fuzzing C++ | Apache-2.0 + componentes |
| 117 | [google/oss-fuzz](https://github.com/google/oss-fuzz) | FUZZ | Infraestructura para fuzzing continuo | Apache-2.0 + componentes |
| 118 | [trailofbits/polytracker](https://github.com/trailofbits/polytracker) | FUZZ | Seguimiento de datos de entrada en ejecución | Apache-2.0 |
| 119 | [google/clusterfuzzlite](https://github.com/google/clusterfuzzlite) | FUZZ | Fuzzing en flujos de CI | Apache-2.0 |
| 120 | [esbmc/esbmc](https://github.com/esbmc/esbmc) | FORMAL | Verificación acotada de C/C++ vía SMT | Apache-2.0 + BSD-4 |
| 121 | [seahorn/seahorn](https://github.com/seahorn/seahorn) | FORMAL | Verificación de programas LLVM | BSD mod. |
| 122 | [dafny-lang/dafny](https://github.com/dafny-lang/dafny) | FORMAL | Especificaciones ejecutables y verificación de código | MIT |
| 123 | [verus-lang/verus](https://github.com/verus-lang/verus) | FORMAL | Verificación de propiedades de Rust | MIT |
| 124 | [GaloisInc/saw-script](https://github.com/GaloisInc/saw-script) | FORMAL | Comparación de programas y pruebas formales | BSD-3-Clause |
| 125 | [rocq-prover/rocq](https://github.com/rocq-prover/rocq) | FORMAL | Pruebas matemáticas verificadas por máquina | LGPL-2.1 |
| 126 | [FStarLang/FStar](https://github.com/FStarLang/FStar) | FORMAL | Lenguaje para especificar y verificar programas | Apache-2.0 |
| 127 | [verifast/verifast](https://github.com/verifast/verifast) | FORMAL | Verificación modular de C Rust y Java | MIT |
| 128 | [AliveToolkit/alive2](https://github.com/AliveToolkit/alive2) | FORMAL | Comprobación de transformaciones LLVM | MIT |
| 129 | [radareorg/radare2](https://github.com/radareorg/radare2) | BINARIOS | Ingeniería inversa y desensamblado programable | LGPL-3.0 + componentes |
| 130 | [rizinorg/cutter](https://github.com/rizinorg/cutter) | BINARIOS | Interfaz gráfica de análisis de binarios Rizin | GPL-3.0 |
| 131 | [lief-project/LIEF](https://github.com/lief-project/LIEF) | BINARIOS | Lectura y modificación de formatos ejecutables | Apache-2.0 |
| 132 | [capstone-engine/capstone](https://github.com/capstone-engine/capstone) | BINARIOS | Motor de desensamblado multiarquitectura | BSD-3-Clause |
| 133 | [DynamoRIO/dynamorio](https://github.com/DynamoRIO/dynamorio) | BINARIOS | Instrumentación dinámica de binarios | BSD-3-Clause |
| 134 | [qemu/qemu](https://github.com/qemu/qemu) | BINARIOS | Emulación de procesadores y máquinas | GPL-2.0 + componentes |
| 135 | [google/osv-scanner](https://github.com/google/osv-scanner) | SUPPLY | Detección de avisos OSV en dependencias | Apache-2.0 |
| 136 | [anchore/syft](https://github.com/anchore/syft) | SUPPLY | Generación de inventarios SBOM | Apache-2.0 |
| 137 | [anchore/grype](https://github.com/anchore/grype) | SUPPLY | Comprobación de CVE en SBOM e imágenes | Apache-2.0 |
| 138 | [dependency-check/DependencyCheck](https://github.com/dependency-check/DependencyCheck) | SUPPLY | Análisis de composición y vulnerabilidades | Apache-2.0 |
| 139 | [DependencyTrack/dependency-track](https://github.com/DependencyTrack/dependency-track) | SUPPLY | Seguimiento de riesgo de dependencias SBOM | Apache-2.0 |
| 140 | [cdxgen/cdxgen](https://github.com/cdxgen/cdxgen) | SUPPLY | Inventarios CycloneDX de software | Apache-2.0 |
| 141 | [ossf/scorecard](https://github.com/ossf/scorecard) | SUPPLY | Evaluación de prácticas de proyectos OSS | Apache-2.0 |
| 142 | [guacsec/guac](https://github.com/guacsec/guac) | SUPPLY | Grafo de procedencia y composición de software | Apache-2.0 |
| 143 | [in-toto/in-toto](https://github.com/in-toto/in-toto) | SUPPLY | Atestación de pasos de cadena de suministro | Apache-2.0 |
| 144 | [ossf/package-analysis](https://github.com/ossf/package-analysis) | SUPPLY | Observación del comportamiento de paquetes | Apache-2.0 |
| 145 | [ossf/malicious-packages](https://github.com/ossf/malicious-packages) | SUPPLY | Base de avisos de paquetes maliciosos | Apache-2.0 |
| 146 | [rustsec/rustsec](https://github.com/rustsec/rustsec) | SUPPLY | Avisos de vulnerabilidades de dependencias Rust | MIT OR Apache-2.0 |
| 147 | [EmbarkStudios/cargo-deny](https://github.com/EmbarkStudios/cargo-deny) | SUPPLY | Políticas de dependencias y licencias Rust | MIT OR Apache-2.0 |
| 148 | [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | SECRETOS | Detección de secretos filtrados | AGPL-3.0 |
| 149 | [betterleaks/betterleaks](https://github.com/betterleaks/betterleaks) | SECRETOS | Detección configurable de credenciales en código | MIT |
| 150 | [aboutcode-org/scancode-toolkit](https://github.com/aboutcode-org/scancode-toolkit) | SUPPLY | Extracción de licencias y procedencia de código | Apache-2.0 |
| 151 | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | AGENTES | SDK de agentes de programación con herramientas | MIT |
| 152 | [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | AGENTES | Agente mínimo para tareas de software | MIT |
| 153 | [Aider-AI/aider](https://github.com/Aider-AI/aider) | AGENTES | Edición de código asistida por modelos y Git | Apache-2.0 |
| 154 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | AGENTES | Orquestación de agentes con estado persistente | MIT |
| 155 | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | AGENTES | Composición y optimización de flujos con LLM | MIT |
| 156 | [huggingface/smolagents](https://github.com/huggingface/smolagents) | AGENTES | Agentes con herramientas ejecutables en código | Apache-2.0 |
| 157 | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | AGENTES | Pipelines de recuperación y análisis documental | Apache-2.0 |
| 158 | [run-llama/llama_index](https://github.com/run-llama/llama_index) | AGENTES | Ingesta e indexación de conocimiento para modelos | MIT |
| 159 | [qdrant/qdrant](https://github.com/qdrant/qdrant) | AGENTES | Motor de búsqueda vectorial con metadatos | Apache-2.0 |
| 160 | [pgvector/pgvector](https://github.com/pgvector/pgvector) | AGENTES | Índices vectoriales en PostgreSQL | PostgreSQL |
| 161 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | MODELOS | Servicio de inferencia eficiente de LLM | Apache-2.0 |
| 162 | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | MODELOS | Inferencia local eficiente C/C++ | MIT |
| 163 | [sgl-project/sglang](https://github.com/sgl-project/sglang) | MODELOS | Orquestación de inferencia de LLM | Apache-2.0 |
| 164 | [huggingface/transformers](https://github.com/huggingface/transformers) | MODELOS | Biblioteca de arquitecturas y ejecución de modelos | Apache-2.0 |
| 165 | [langfuse/langfuse](https://github.com/langfuse/langfuse) | MODELOS | Trazabilidad y evaluación de aplicaciones LLM | MIT + Enterprise separado |
| 166 | [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) | MODELOS | Evaluación de sistemas de recuperación y generación | Apache-2.0 |
| 167 | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | MODELOS | Pruebas y evaluación de seguridad de aplicaciones IA | MIT + funciones remotas |
| 168 | [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | MODELOS | Framework de evaluación independiente de agentes IA | MIT |
| 169 | [NVIDIA/garak](https://github.com/NVIDIA/garak) | MODELOS | Pruebas de seguridad de modelos de lenguaje | Apache-2.0 |
| 170 | [bountybench/bountybench](https://github.com/bountybench/bountybench) | BENCHMARK | Casos de evaluación de investigación y reparación | Apache-2.0 |
| 171 | [NomicFoundation/hardhat](https://github.com/NomicFoundation/hardhat) | EVM | Pruebas y depuración de contratos Ethereum | MIT + por paquete |
| 172 | [ethers-io/ethers.js](https://github.com/ethers-io/ethers.js) | EVM | SDK de interacción y ABI Ethereum para JavaScript | MIT |
| 173 | [wevm/viem](https://github.com/wevm/viem) | EVM | Cliente tipado JSON-RPC y ABI Ethereum | MIT |
| 174 | [ethereumjs/ethereumjs-monorepo](https://github.com/ethereumjs/ethereumjs-monorepo) | EVM | Implementaciones TypeScript de EVM y tipos de cadena | MPL-2.0 + por paquete |
| 175 | [paradigmxyz/reth](https://github.com/paradigmxyz/reth) | EVM | Cliente modular Ethereum en Rust | MIT OR Apache-2.0 |
| 176 | [besu-eth/besu](https://github.com/besu-eth/besu) | EVM | Cliente Ethereum en Java | Apache-2.0 |
| 177 | [ethereum/hive](https://github.com/ethereum/hive) | EVM | Pruebas de interoperabilidad de clientes Ethereum | GPL-3.0 |
| 178 | [crytic/crytic-compile](https://github.com/crytic/crytic-compile) | EVM | Compatibilidad de compilación para análisis de contratos | AGPL-3.0 |
| 179 | [smartbugs/smartbugs](https://github.com/smartbugs/smartbugs) | EVM | Orquestador de analizadores de Solidity/bytecode | Apache-2.0 + analizadores |
| 180 | [LiteSVM/litesvm](https://github.com/LiteSVM/litesvm) | SOLANA | Simulador SVM en proceso | Apache-2.0 |
| 181 | [anza-xyz/mollusk](https://github.com/anza-xyz/mollusk) | SOLANA | Pruebas locales de instrucciones SVM | Apache-2.0 |
| 182 | [otter-sec/anchor](https://github.com/otter-sec/anchor) | SOLANA | Framework de desarrollo y prueba de programas Solana | Apache-2.0 |
| 183 | [anza-xyz/agave](https://github.com/anza-xyz/agave) | SOLANA | Código del cliente y validador Solana | Apache-2.0 |
| 184 | [lfdt-ibc/ibc-go](https://github.com/lfdt-ibc/ibc-go) | COSMOS | Implementación IBC entre cadenas Cosmos | Apache-2.0 |
| 185 | [CosmWasm/cosmwasm](https://github.com/CosmWasm/cosmwasm) | COSMOS | Runtime Wasm para contratos Cosmos | Apache-2.0 |
| 186 | [cosmos/cosmos-sdk](https://github.com/cosmos/cosmos-sdk) | COSMOS | Framework modular de cadenas Cosmos | Apache-2.0 |
| 187 | [MystenLabs/sui](https://github.com/MystenLabs/sui) | OTRAS_CADENAS | Cliente y modelo de objetos Sui | Apache-2.0 |
| 188 | [starkware-libs/cairo](https://github.com/starkware-libs/cairo) | OTRAS_CADENAS | Lenguaje y compilador Cairo | Apache-2.0 |
| 189 | [ethereum/consensus-specs](https://github.com/ethereum/consensus-specs) | METODO | Especificación y tests del consenso Ethereum | CC0-1.0 |
| 190 | [ethereum/EIPs](https://github.com/ethereum/EIPs) | METODO | Estándares y propuestas Ethereum | CC0-1.0 |
| 191 | [crytic/building-secure-contracts](https://github.com/crytic/building-secure-contracts) | METODO | Guías de análisis de contratos inteligentes | AGPL-3.0 |
| 192 | [theredguild/damn-vulnerable-defi](https://github.com/theredguild/damn-vulnerable-defi) | LAB | Laboratorio de fallos DeFi intencionales | MIT |
| 193 | [OpenZeppelin/ethernaut](https://github.com/OpenZeppelin/ethernaut) | LAB | Desafíos de seguridad EVM | AGPL-3.0 |
| 194 | [juice-shop/juice-shop](https://github.com/juice-shop/juice-shop) | LAB | Laboratorio web vulnerable deliberado | MIT |
| 195 | [WebGoat/WebGoat](https://github.com/WebGoat/WebGoat) | LAB | Laboratorio educativo web con fallos conocidos | GPL-2.0+ |
| 196 | [OWASP/crAPI](https://github.com/OWASP/crAPI) | LAB | Laboratorio de APIs y microservicios vulnerables | Apache-2.0 |
| 197 | [digininja/DVWA](https://github.com/digininja/DVWA) | LAB | Entorno de vulnerabilidades PHP de ensayo | GPL-3.0 |
| 198 | [vulhub/vulhub](https://github.com/vulhub/vulhub) | LAB | Recetas Docker de software vulnerable conocido | MIT + componentes |
| 199 | [OWASP/CheatSheetSeries](https://github.com/OWASP/CheatSheetSeries) | METODO | Guías de diseño y mitigación de aplicaciones | CC-BY-SA-4.0 |
| 200 | [OWASP/mastg](https://github.com/OWASP/mastg) | METODO | Guía de pruebas de seguridad móvil | CC-BY-SA-4.0 |

## Política de incorporación

Estos 200 son el alcance **previsto**, no una implementación certificada. Cada repositorio deberá pasar revisión independiente de **existencia, identidad, licencia real en commit exacto, actividad/mantenimiento, valor incremental, compatibilidad, aislamiento y evaluación ciega**. Si un proyecto está descontinuado, tiene un cambio de licencia o no aporta valor frente a un componente existente, registrar el resultado sin inventar una integración exitosa. No modificar ni borrar las fuentes PFT/Census o las ramas históricas.

Registro de avance sugerido por proyecto: `CATALOGUED_FOR_INTEGRATION -> VERIFIED_UPSTREAM -> LICENSE_REVIEWED -> OFFLINE_ADAPTER -> NATIVE_QA -> INDEPENDENT_REPLAY -> MEASURED_INTEGRATION`. Estados `BLOCKED` y `REJECTED` deben conservar sus motivos. La ejecución activa sobre objetivos exige autorización independiente del mero catálogo.
