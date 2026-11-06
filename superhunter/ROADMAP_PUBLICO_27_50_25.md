# SUPERHUNTER — Roadmap completo y ubicación de cada requisito

Fuente de verdad: los tres catálogos JSON incluidos en la instantánea. El texto siguiente **no cambia sus estados**. Una prueba unitaria no significa módulo terminado.

## Prioridades inmediatas con criterios de aceptación

1. **P0 — Consolidación del repositorio:** comparar esta rama con los PR históricos y `main`, ejecutar el verificador global de aislamiento y suites afectadas Python/Rust. No fusionar automáticamente ni reactivar workflows.
2. **P0 — Trazabilidad reproducible:** trasladar a esta rama evidencias públicas sanitizadas, firmas/identidades de productor independientes y reporte de reproducción para cada hito, sin publicar secretos ni expedientes privados.
3. **P1 — Benchmark realmente ciego:** corpus con custodio independiente, partición por protocolos/grupos, compromisos publicados antes de predicciones, métricas de recall/precision/abstención con intervalos de confianza y presupuesto por caso. Los cuatro fixtures actuales no acreditan esto.
4. **P1 — Inteligencia de detección:** incorporar reglas semánticas reales de Slither/SlithIR, taint, fuzzers EVM (Echidna/Medusa), generación verificable de hipótesis y minimización, con controles positivos/negativos sin introducir capacidades de evasión o explotación de terceros.
5. **P1 — EVM multi-contrato y economía:** oráculos, vaults, préstamos, proxies y casos de bloqueo, reconciliando trazas, balances y modelos independientes; medir efectos persistentes y condiciones de reversión.
6. **P1 — Program Intelligence real:** conectores de lectura oficiales y autorización programa por programa, verificando vigencia, scope y límites. Bloquear tráfico por defecto. Ninguna acción de producción automática sin autorización explícita.
7. **P2 — Tribunal de falsos positivos:** políticas de abstención, contradicción entre motores, revisión humana obligatoria para disclosure, aprendizaje de descartes y regresiones sin contaminación del conjunto ciego.
8. **P2 — Operación fiable:** control de concurrencia, colas y aislamiento entre hasta 20 programas autorizados, presupuestos, reinicios, métricas de salud, auditoría y alertas controladas. 24/7 solo tras pruebas de continuidad y autorización.
9. **P2 — Rendimiento frente a baselines:** comparar con herramientas externas sobre igual hardware, tiempo, cobertura, corpus no visto y métricas calibradas. No declarar superioridad sin resultados independientes.

## 27 hitos originales (texto y estado declarados)

| ID | Estado | Hito | Alcance/limitación actual |
|---|---|---|---|
| `B01` | BOUNDED_IMPLEMENTED | Código de integración ubicado en el repositorio de NQC | Código del paquete superhunter; la procedencia del checkout se comprueba aparte con Git. |
| `B02` | BOUNDED_IMPLEMENTED | Repositorios originales de NQC y DIABLO preservados | Las cuatro copias nativas se verifican byte a byte. La ausencia de otros cambios se revisa en el diff Git de cada publicación, no la certifica este test. |
| `B03` | BOUNDED_IMPLEMENTED | Componentes originales seleccionados de ambos ejecutándose juntos | ScopeGuard y AuditLog de DIABLO con el solucionador numérico RMC-016 de NQC; no los motores completos. |
| `B04` | PENDING | Integrar el motor completo de descubrimiento de DIABLO | No implementado; se limita el desarrollo a evaluación defensiva, sin explotación autónoma de terceros. |
| `B05` | BOUNDED_IMPLEMENTED | Contrato de datos Candidate implementado | Validación de estructura de un candidato; no confirma una vulnerabilidad. |
| `B06` | BOUNDED_IMPLEMENTED | Conversión de un Finding nativo de DIABLO a Candidate | Adaptador de datos; la severidad del Finding original no se acepta como prueba. |
| `B07` | BOUNDED_IMPLEMENTED | Identificadores, hashes, repo, commit y bloque vinculados | Asociación de solicitud, cadena y estado; los hashes no autentican al productor. |
| `B08` | PENDING | Generación automática de candidatos a partir de nuevos descubrimientos | No hay motor de nuevos descubrimientos conectado. |
| `B09` | PENDING | Verificación real de la PoC contra el contrato exacto | No se ejecutó Forge ni se implementó un verificador genérico de PoCs. |
| `B10` | BOUNDED_IMPLEMENTED | Contrato de datos Reconstruction y adaptador de recepción implementados | Recibe evidencia existente; no reconstruye por sí mismo un contrato. |
| `B11` | BOUNDED_IMPLEMENTED | Comprobaciones de identidad, solicitud, cadena y estado | Rechazo de respuestas incompatibles con la solicitud; no validación independiente de la cadena real. |
| `B12` | BOUNDED_IMPLEMENTED | Solucionador numérico RMC-016 ejecutado en cinco casos sintéticos | Los cinco casos nativos se verifican con referencia numérica independiente. |
| `B13` | PENDING | Reconstrucción automática del estado de un contrato investigado | El solucionador RMC-016 no es un reconstructor de contratos. |
| `B14` | PENDING | Cálculo verificado de fondos en riesgo, costos y beneficio potencial | Los importes externos son declaraciones; no hay impacto de vulnerabilidades calculado. |
| `B15` | PENDING | Segunda ejecución independiente de una vulnerabilidad | Comparar números sintéticos no equivale a reproducir una vulnerabilidad. |
| `B16` | BOUNDED_IMPLEMENTED | Puertas de consistencia, integridad y revisión implementadas | Puertas de consistencia de artefactos; el resultado sigue siendo REVIEW_REQUIRED. |
| `B17` | BOUNDED_IMPLEMENTED | Detección de varias condiciones de rechazo y evidencia alterada | Rechazo de cambios de bytes y relaciones contradictorias entre evidencia, casos y bitácoras. |
| `B18` | BOUNDED_IMPLEMENTED | Borradores REVIEW_REQUIRED y retorno de feedback a DIABLO | Borrador de revisión sin confirmación de ejecución, severidad final ni recompensa. |
| `B19` | PENDING | Verificación autónoma del alcance vigente y duplicados | La revisión del programa y duplicados requiere fuentes y revisión humana vigentes. |
| `B20` | PENDING | Clasificación final de severidad con impacto demostrado | La severidad propuesta no se promueve a severidad oficial o final. |
| `B21` | PENDING | Emisión de Finding confirmado por evidencia independiente | No se emiten hallazgos confirmados. |
| `B22` | PARTIAL | Fuzzing combinado y ejecución simbólica | Existe fuzzing numérico local; faltan EVM y ejecución simbólica. |
| `B23` | PENDING | Exploración de vulnerabilidades entre múltiples contratos | No implementada; no se añade planificación autónoma de explotación. |
| `B24` | PENDING | Pruebas de invariantes económicas sobre contratos reales autorizados | Solo modelos numéricos sintéticos, no contratos reales. |
| `B25` | PARTIAL | Monitoreo de upgrades y regresiones | Regresiones del propio paquete; no monitorización de contratos o parches externos. |
| `B26` | PENDING | Operación continua y supervisión de 20 programas | No hay servicio 24/7 ni 20 programas conectados. |
| `B27` | PARTIAL | Preparación de reportes completos para revisión en Immunefi | Hay borradores Markdown y reportes locales, no un reporte completo de un hallazgo real. |

## 50 capacidades (texto y estado declarados)

| ID | Estado | Capacidad | Evidencia/límite actual |
|---|---|---|---|
| 1 | PLANNED | Consultas de grafos personalizadas (SlithIR) | Pendiente: no hay SlithIR integrado ni trazado de fondos implementado. |
| 2 | PLANNED | Análisis de contaminación de entradas (taint analysis) | Pendiente: análisis estático de datos en código propio; las reglas de scope no son taint analysis. |
| 3 | PARTIAL | Fuzzing dinámico guiado por invariantes | Parcial y solo numérico: el laboratorio ejecuta el solucionador NQC con casos generados, oráculo independiente e invariantes metamórficas bajo ScopeGuard/AuditLog de DIABLO; NO fuzzing de transacciones EVM ni contratos reales. |
| 4 | PLANNED | Fuzzing con bifurcación de red | Pendiente: estados locales autorizados; no hay motor de forks integrado ni RPC activado. |
| 5 | REDESIGN_REQUIRED | Simulador de préstamos flash | Reformular como pruebas de solvencia en modelos propios; no generador de ataques para drenar pools. |
| 6 | PLANNED | Analizador de integración de oráculos | Pendiente: comprobaciones contextuales de fuentes, frescura y unidades; spot/TWAP no decide por sí solo la seguridad. |
| 7 | PLANNED | Inferencia simbólica estocástica | Pendiente experimental: hipótesis sujetas a validación, no deducción garantizada de todas las reglas. |
| 8 | REDESIGN_REQUIRED | Estrategias de pruebas multibloque | Reformular como pruebas de propiedades temporales en modelos propios, no planificador autónomo de ataques. |
| 9 | PLANNED | Fuzzer de estado y memoria en laboratorio | Pendiente: escenarios artificiales etiquetados como contrafactuales, nunca como explotabilidad demostrada. |
| 10 | PLANNED | Orquestador LLM y simbólico | Pendiente: propuestas revisables y comprobaciones deterministas; no se promete ausencia absoluta de alucinaciones. |
| 11 | PLANNED | Diferenciales de bytecode | Pendiente: comparación de versiones; el inventario SHA actual no es análisis semántico de bytecode. |
| 12 | PLANNED | Simulación de corridas bancarias | Pendiente: modelos de riesgo con supuestos explícitos y sensibilidad; no daño financiero garantizado. |
| 13 | PLANNED | Taint analysis binario dinámico | Pendiente: pruebas de software nativo propio; no hay instrumentación CPU/memoria integrada. |
| 14 | PARTIAL | Grafos de permisos | Parcial: grafo de herencia de roles y cálculo de permisos de una política JSON local, con dos algoritmos contrastados. No analiza permisos reales de contratos ni busca rutas de explotación. |
| 15 | REDESIGN_REQUIRED | Extractor automático de reproducciones | Reformular como reducción de tests fallidos en código propio, no generación autónoma de exploits de terceros. |
| 16 | PLANNED | Validación de firmas criptográficas | Pendiente: regresiones locales de autorización, nonces y dominios; no extracción de claves. |
| 17 | PLANNED | Inyección de fallos en sistemas distribuidos | Pendiente: pruebas de fallos en infraestructura propia aislada; no perturbación de servicios ajenos. |
| 18 | PLANNED | Análisis de reentrancia entre contratos | Pendiente: revisión defensiva de llamadas y propiedades; no motor autónomo de explotación. |
| 19 | PLANNED | Efectos del compilador | Pendiente: verificar compilaciones equivalentes y diferencias; no hay análisis de optimizadores implementado. |
| 20 | PLANNED | Fuzzer de API por gramáticas | Pendiente: pruebas funcionales sobre APIs propias de laboratorio, sin encadenamiento ofensivo. |
| 21 | REDESIGN_REQUIRED | Fuzzing de protocolos de red | Reformular como validación de parsers propios mediante tráfico de laboratorio; no fuzzing activo de terceros. |
| 22 | REDESIGN_REQUIRED | Análisis de canales laterales | Reformular como medición de posibles fugas con secretos de prueba; no extracción de claves reales. |
| 23 | REDESIGN_REQUIRED | Consistencia HTTP y caché | Reformular como revisión de configuración y conformidad proxy/backend; no secuestro de sesiones ni ataques automatizados. |
| 24 | PARTIAL | Consistencia de RBAC mutable | Parcial: políticas RBAC JSON, dominios de asignaciones y comprobación real con Z3; testigos contrastados con dos evaluadores y enumeración acotada. No extracción desde código ni aplicación efectiva en producción. |
| 25 | REDESIGN_REQUIRED | Análisis de deserialización | Reformular como identificación de deserialización insegura y dependencias; no construcción de cadenas RCE. |
| 26 | PLANNED | Verificación de circuitos ZK | Pendiente: revisión de restricciones en circuitos propios; no motor ZK implementado. |
| 27 | PLANNED | Concurrencia y memoria compartida | Pendiente: instrumentación de concurrencia para programas propios; no primitivas de explotación. |
| 28 | REDESIGN_REQUIRED | Consenso y fallos bizantinos | Reformular como simulación de tolerancia a fallos; no interrupción de consenso en redes externas. |
| 29 | PARTIAL | Fugas de información en logs | Parcial: redacción determinista de logs UTF-8 locales, borradores y diagnósticos; sin detección semántica universal, monitorización continua ni garantía de ausencia de secretos. |
| 30 | PLANNED | Dependencias vulnerables y alcanzabilidad | Pendiente: inventario y alcanzabilidad; los hashes de fuentes no equivalen a un análisis de dependencias vulnerables. |
| 31 | REDESIGN_REQUIRED | Integridad de carga de bibliotecas | Reformular como verificación de procedencia y configuración de bibliotecas; no inyección ni desvío de ejecución. |
| 32 | REDESIGN_REQUIRED | Validación de aislamiento de sandboxes | Reformular como comprobación de aislamiento; no evolución de payloads para evadir sandboxes. |
| 33 | PLANNED | Consistencia documentación/código | Pendiente: no hay comparador semántico de especificaciones y código. |
| 34 | PARTIAL | Verificación formal acotada | Parcial: traducción del modelo RBAC finito a QF_LIA y ejecución de Z3 nativo con SAT/UNSAT/UNKNOWN, presupuestos, no vacuidad y contraste por enumeración. No Solidity/SMT general, certificado UNSAT externo ni garantía universal. |
| 35 | REDESIGN_REQUIRED | Planificación de experimentos mediante MCTS | Reformular como asignación de presupuesto de pruebas por cobertura; no planificación ni encadenamiento de exploits. |
| 36 | REDESIGN_REQUIRED | Grafo de conocimiento entre dominios | Reformular como correlación defensiva de dependencias y riesgos, no diseño de ataques integrales. |
| 37 | PARTIAL | Triaje e impacto económico | Conciliación local exacta de balances y flujos declarados, por activo y cuenta, con dos cálculos y cobertura explícita. Sin extracción EVM, precios verificados, fondos en riesgo demostrados, beneficio de atacante ni severidad final. |
| 38 | REDESIGN_REQUIRED | Aprendizaje con retroalimentación humana | Reformular con consentimiento, feedback explícito y cambios revisados; no observación encubierta ni autoedición sin pruebas. |
| 39 | PLANNED | Auditor visual de interfaz | Pendiente: revisión de UI propia y comprobaciones del navegador; una imagen por sí sola no demuestra un fallo. |
| 40 | PLANNED | Análisis de grafos mediante modelos | Pendiente experimental: grafos como datos; no detección instantánea ni certeza a partir de imágenes. |
| 41 | PLANNED | Diagramas y especificaciones visuales | Pendiente: extracción de especificaciones con referencias verificables y revisión de ambigüedades. |
| 42 | REDESIGN_REQUIRED | Detección visual de exposición de secretos | Reformular para material propio autorizado y redacción; no vigilancia de terceros ni recolección de credenciales. |
| 43 | REDESIGN_REQUIRED | Automatización de navegador para QA | Reformular como automatización identificada de pruebas; sin evasión de WAF, bots ni captchas. |
| 44 | REDESIGN_REQUIRED | Generación adaptativa de entradas de prueba | Reformular como pruebas de contratos de entrada y sanitización propios; no evasión adaptativa de filtros. |
| 45 | PARTIAL | Orquestación de entornos de prueba | Parcial: proceso local acotado para componentes fijados; no clonación Docker/DB/RPC ni sandbox para código hostil. |
| 46 | REDESIGN_REQUIRED | Validación de propiedades con contratos de prueba | Reformular como tests de propiedades de contratos propios; no contratos autónomos de drenaje ni promesas de recompensa. |
| 47 | PARTIAL | Reportes técnicos y ejecutivos | Parcial: informes locales Markdown/HTML con privacidad, revisión conjunta y los 27+50 requisitos; no reporte de vulnerabilidad real, PDF ni dictamen de seguridad. |
| 48 | PARTIAL | Verificación de parches y regresiones | Parcial: comparación reproducible antes/después de pruebas locales con identidades de código y oráculos conservados; detecta regresiones, pruebas eliminadas y cambios de aserciones. No monitoriza parches externos ni confirma exploits o ausencia universal de fallos. |
| 49 | PLANNED | Inteligencia de amenazas públicas | Pendiente: fuentes públicas y revisión de reglas antes de activarlas; sin escaneo ofensivo automático. |
| 50 | PLANNED | Mapeo de controles de cumplimiento | Pendiente: sugerencias trazables de controles; no certificación automática ni dictamen de incumplimiento legal. |

## 25 iniciativas adicionales de los dos PDF (texto y estado declarados)

| ID | Estado | Iniciativa | Evidencia/límite actual |
|---|---|---|---|
| `OCTANE.R1` | PLANNED | Análisis continuo de repositorios | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OCTANE.R2` | PARTIAL | Correcciones asistidas con revisión | Comparación local de regresiones y revisión humana; sin generación de parches ni fusión automática. |
| `OCTANE.R3` | PLANNED | Análisis integrado de superficies | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OCTANE.D1` | PLANNED | Reproducción económica verificable | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OCTANE.D2` | PLANNED | Grafo de dependencias entre protocolos | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OLYMPIX.R1` | PLANNED | Detectores especializados de Solidity | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OLYMPIX.R2` | PLANNED | Generación automática de pruebas | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OLYMPIX.R3` | PLANNED | PoC reproducible con fuzzing y análisis simbólico | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OLYMPIX.D1` | PLANNED | Fuzzing guiado por estados económicos | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `OLYMPIX.D2` | PLANNED | Triangulación de impacto económico | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `CERTORA.R1` | PARTIAL | Verificador de invariantes | Verificación de propiedades de políticas RBAC declaradas mediante Z3 nativo, testigos comprobados y enumeración independiente. No Certora Prover, traducción de contratos ni invariantes DeFi. |
| `CERTORA.R2` | PLANNED | Asistencia IA para especificaciones | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `CERTORA.R3` | PLANNED | Validación formal en CI/CD | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `CERTORA.D1` | PLANNED | Especificaciones sensibles a régimen económico | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `CERTORA.D2` | PLANNED | Prueba formal + replay diferencial | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `IMMUNEFI.R1` | PLANNED | Gestión del ciclo de hallazgos | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `IMMUNEFI.R2` | PARTIAL | Panel de herramientas y evidencia | Reportes de evidencia local y normalización de alertas importadas; no detección autónoma ni panel de protocolos activos. |
| `IMMUNEFI.R3` | PLANNED | Monitoreo y correlación de alertas | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `IMMUNEFI.D1` | PARTIAL | Cadena de custodia técnica | Firmas Ed25519 de custodia de paquetes locales, claves de confianza externas por expediente/productor y controles de revocación/caducidad. No atestación de ejecución, autorización, verdad de datos ni tiempo confiable. |
| `IMMUNEFI.D2` | PLANNED | Priorización por exposición demostrada | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `TRAIL_OF_BITS.R1` | PARTIAL | Slither como capa de análisis estático | Importación offline de JSON de detectores con fuentes, localizaciones y deduplicación; Slither/solc no ejecutados ni reglas nuevas. |
| `TRAIL_OF_BITS.R2` | PLANNED | Echidna y Medusa como fuzzers | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `TRAIL_OF_BITS.R3` | PLANNED | Pruebas de propiedades e invariantes | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `TRAIL_OF_BITS.D1` | PLANNED | Corpus distribuido orientado a economía | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |
| `TRAIL_OF_BITS.D2` | PLANNED | Verificación diferencial entre motores | Pendiente: la arquitectura propuesta no acredita una implementación de esta iniciativa. |

## Decisiones prohibidas sin evidencia

- No afirmar 100% de cobertura, cero falsos positivos universales ni detección de una crítica original.
- No emitir transmisiones on-chain, firmar, comerciar, desplegar, escanear servicios externos ni enviar reportes automáticamente.
- No sustituir comprobaciones EVM/solc/Z3 fallidas por fixtures o hashes.
- No inventar premios, pérdidas económicas o riesgo con datos incompletos.
- No presentar un control conocido como benchmark ciego.

## Criterio global de finalización

Cada familia debe demostrar ejecución auténtica, procedencia, verificación independiente, control negativo, evidencia de alcance, métricas sobre corpus nunca visto, reproducibilidad en copia limpia y revisión de publicación. Los 27+50+25 puntos se cierran por criterios propios, no por suma de pruebas.
