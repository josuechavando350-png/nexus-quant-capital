# SUPERHUNTER — 50 repositorios candidatos y sus funciones

**Evidencia posterior al catálogo:** [OTEL_DEPENDENCY_INTEGRITY.md](OTEL_DEPENDENCY_INTEGRITY.md) registra QA completo con SDK real y pins; [SLITHER_NATIVE_EVIDENCE.md](SLITHER_NATIVE_EVIDENCE.md) registra el nuevo laboratorio nativo de tres controles propios. Los estados y denominadores del catálogo original no se promueven automáticamente por esas aceptaciones acotadas.

**Fecha:** 2026-11-07. **Resultado:** portafolio documentado, **50/50 referencias**. **Integraciones nuevas: 0/50**; no se clonó, instaló, ejecutó ni desplegó ningún proyecto externo. Este documento NO acredita un cazador 10/10, hallazgos originales o rentabilidad.

**Instrucción para otras IAs:** leer el [plan maestro](../SUPERHUNTER_MASTER_PLAN.md), [estado actual](../SUPERHUNTER_STATUS.md), [AGENTS](../AGENTS.md), este documento y el [JSON canónico](repo_portfolio_50.json). Los 50 repositorios externos **no son** las 50 capacidades de `superhunter/capabilities.json`, ni sustituyen los 27 requisitos o 25 iniciativas internas. Antes de operar, inspeccionar las PRs y su cadena actual.

## Contrato de integración obligatorio

1. Alcance por programa y operación con denegación por defecto. Un repositorio público o URL descubierta no equivale a autorización para pruebas activas.
2. Revisar licencia y dependencias del commit concreto, preservar SHA-256, fuente y SBOM. Sin instaladores remotos no auditados.
3. Adaptador aislado: entradas tipadas (`source_identity`, `authorization_scope`, `config_digest`, semilla, presupuesto), salida con hashes de originales y estados `CONFIRMADO`, `REFUTADO` o `INCONCLUSO`.
4. Pruebas offline con positivos, negativos, adversariales, holdout y comparación justa de latencia/p95, precisión, costo, cobertura útil y tasa de falsos positivos. Replay independiente antes de elevar un hallazgo.
5. Nunca activar escaneos de terceros, RPC, despliegues, firmas, envíos, capital, sensores ni workflows por añadir un candidato. Evidencia privada nunca se sube al GitHub público.
6. El estado solo avanza de `CATALOGUED_NOT_INTEGRATED` mediante PR posterior con licencia revisada, prototipo, QA, consumidor real y verificadores. Agregar un enlace no cuenta como implementación.

**Ensayo integrado offline posterior:** [SLITHER_OFFLINE_IMPORT_E2E.md](SLITHER_OFFLINE_IMPORT_E2E.md) define cuatro pruebas sobre el importador/bitácora/verificador reales, pero con reportes Slither sintéticos y sin ejecución nativa comprobada. El candidato #6 sigue sin certificación.

**Comparación reconciliada posterior a los PR #73/#74:** [SLITHER_TRIPLE_REPLAY.md](SLITHER_TRIPLE_REPLAY.md) compara seis reportes de dos ejecuciones de tres controles, sin importar código remoto ni afirmar independencia de host. El estado externo permanece en evaluación, sin QA integral ni ejecución Slither.

**Actualización posterior de Slither:** la referencia #6 ya tiene [gate de tres controles OWNED](SLITHER_THREE_CONTROL_GATE.md); su tercera condición reproduce una exclusión específica del detector. **No hay scanner real ejecutado ni certificación de integración**. La selección estructurada permanece candidata hasta cubrir sus criterios de aceptación.

**Actualización de implementación posterior al registro:** el candidato **#26** tiene un [adaptador de QA OpenTelemetry en laboratorio](OTEL_QA_LAB.md). Su código ejecutable está en otel_qa.py y sus pruebas en tests/test_otel_qa.py; solo se comprobó localmente con QA simulado y SDK real. **Collector no instalado; ningún nuevo motor externo certificado ni 10/10**. El estado del catálogo estructurado sigue `CATALOGUED_NOT_INTEGRATED` hasta la aceptación integral conforme a las reglas de promoción.

**Implementación posterior adicional:** el proyecto **#6 Slither** tiene un [runner en laboratorio](SLITHER_OWNED_LAB.md) y pruebas de contrato: solo fuente OWNED fija, sin ejecutable Slither instalado ni QA integral aún. Mantenerlo como candidato NO certificado; no confundir código del adaptador con hallazgo verificado.

**Prioridades:** P0 laboratorio inicial; P1 evaluación siguiente; P2 solo ante beneficio medido; P3 al justificar clusters. **Solapamientos:** ItyFuzz/LibAFL, Echidna/Medusa/ItyFuzz, Slither/Opengrep/Joern, Plaso/Timesketch, Arkime/Zeek. Z3 ya existe y Foundry se usa parcialmente en nuestros trabajos; no duplicar.

## Vulnerabilidades y contratos (01-10)

### 1. [ItyFuzz](https://github.com/fuzzland/ityfuzz) — P1

**Función:** Fuzzer híbrido EVM con ejecución simbólica y mutacional.

**Razón de seleccionarlo:** Explora caminos contractuales y estados DeFi que un análisis por patrones puede pasar por alto.

**Interfaz y trabajo propuesto:** Solidity/bytecode fijado y estados locales -> secuencias candidatas -> replay propio Geth/EELS.

**Condición de aceptación:** Comparar con fuzzing propio en casos positivos/negativos, cobertura útil y tiempo con presupuesto idéntico.

**Riesgo/límite:** No tomar exploits generados como evidencia final; comparte base técnica con LibAFL (#32).

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 2. [Kontrol](https://github.com/runtimeverification/kontrol) — P1

**Función:** Verificación formal KEVM/Foundry de propiedades contractuales.

**Razón de seleccionarlo:** Permite contrastar matemáticamente invariantes y encontrar contraejemplos con supuestos explícitos.

**Interfaz y trabajo propuesto:** Propiedad Foundry+premisas -> prueba formal/contraejemplo -> reproducción EVM independiente.

**Condición de aceptación:** Probar una propiedad válida y otra refutable, conservar versiones, supuestos y restricciones de tiempo.

**Riesgo/límite:** Una prueba está limitada por el modelo; instalación KEVM compleja.

**Licencia preliminar:** BSD-3-Clause. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 3. [Gambit](https://github.com/Certora/gambit) — P0

**Función:** Mutación de Solidity para evaluar la calidad de tests y oráculos.

**Razón de seleccionarlo:** Demuestra qué defectos sembrados detecta SuperHunter y cuáles permanecen invisibles.

**Interfaz y trabajo propuesto:** Fuente local -> mutantes controlados -> detectores/fuzzers -> matriz de supervivencia.

**Condición de aceptación:** Mutation score con mutantes equivalentes excluidos y controles adversariales repetibles.

**Riesgo/límite:** Los mutantes no constituyen vulnerabilidades externas ni hallazgos originales.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 4. [DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) — P1

**Función:** Reproducción de incidentes DeFi históricos mediante Foundry.

**Razón de seleccionarlo:** Aporta familias de errores reales para contrastar cobertura económica y reproducibilidad.

**Interfaz y trabajo propuesto:** PoC pública y bloque histórico -> fork aislado -> caso etiquetado -> benchmarking ciego separado.

**Condición de aceptación:** Recrear un subconjunto con hashes y sin fuga de etiquetas hacia el investigador.

**Riesgo/límite:** No tratar un hack conocido como descubrimiento nuevo; licencias de materiales derivados.

**Licencia preliminar:** Apache-2.0 raíz; revisar artefactos terceros. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 5. [CyberChainBench](https://github.com/defai-labs/CyberChainBench) — P1

**Función:** Benchmark de detección, reproducción y corrección de fallos DeFi.

**Razón de seleccionarlo:** Evalúa resultados integrales frente a incidentes reales, en lugar de contar alertas locales.

**Interfaz y trabajo propuesto:** Caso histórico oculto -> tarea detect/reproduce/patch -> veredicto y costo auditables.

**Condición de aceptación:** Holdout aislado, métricas de precisión, reproducción y latencia sobre corpus no visto.

**Riesgo/límite:** Licencias del dataset y documentación tienen advertencias inconsistentes; no redistribuir sin revisar.

**Licencia preliminar:** MIT código; dataset/NOTICE requiere revisión. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 6. [Slither](https://github.com/crytic/slither) — P0

**Función:** Análisis estático Solidity/Vyper y extracción de SlithIR.

**Razón de seleccionarlo:** Identifica rutas críticas, relaciones de permisos y llamadas externas que orientan hipótesis.

**Interfaz y trabajo propuesto:** Fuente/solc fijados -> facts/detectors/grafos -> planificador de experimentos.

**Condición de aceptación:** Casos con positivos/negativos y FP medidos; trazabilidad a versiones y líneas de origen.

**Riesgo/límite:** Alertas estáticas no prueban impacto; obligaciones AGPL.

**Licencia preliminar:** AGPL-3.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 7. [Echidna](https://github.com/crytic/echidna) — P0

**Función:** Fuzzing de invariantes y secuencias de llamadas con reducción de casos.

**Razón de seleccionarlo:** Intenta refutar propiedades de contabilidad y estados con entradas adversariales.

**Interfaz y trabajo propuesto:** Propiedades Solidity -> campaña acotada -> secuencias fallidas -> verificador separado.

**Condición de aceptación:** Replay por semilla y comparación justa con Medusa/ItyFuzz sobre controles reservados.

**Riesgo/límite:** No sumar hallazgos duplicados; AGPL y consumo de cómputo.

**Licencia preliminar:** AGPL-3.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 8. [Medusa](https://github.com/crytic/medusa) — P1

**Función:** Fuzzing paralelo Solidity basado en go-ethereum y cobertura.

**Razón de seleccionarlo:** Aporta un segundo motor independiente para comparar estrategias de exploración.

**Interfaz y trabajo propuesto:** ABI/harness propio -> corpus y trazas -> reproducción y métricas separadas.

**Condición de aceptación:** Benchmarks igualando cores, RAM, semillas, tiempos y tasa de errores.

**Riesgo/límite:** API Go aún evoluciona; paralelismo por sí solo no implica velocidad total.

**Licencia preliminar:** AGPL-3.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 9. [Opengrep](https://github.com/opengrep/opengrep) — P1

**Función:** Análisis estático multilenguaje y taint analysis.

**Razón de seleccionarlo:** Cubre APIs y backends que no se modelan con herramientas exclusivas de Solidity.

**Interfaz y trabajo propuesto:** Repositorio autorizado -> reglas revisadas -> SARIF/JSON -> normalización de hallazgos.

**Condición de aceptación:** Corpus positivo/negativo, fuentes exactas y tasa de falsos positivos.

**Riesgo/límite:** La coincidencia de regla es hipótesis, no prueba de vulnerabilidad.

**Licencia preliminar:** LGPL-2.1. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 10. [Nuclei](https://github.com/projectdiscovery/nuclei) — P1

**Función:** Escaneo de seguridad por plantillas tipadas en protocolos permitidos.

**Razón de seleccionarlo:** Acelera pruebas repetibles de servicios y APIs dentro de programas autorizados.

**Interfaz y trabajo propuesto:** Inventario aprobado + plantillas revisadas -> ejecución acotada -> evidencia.

**Condición de aceptación:** Fail-closed para objetivos fuera de alcance, límites de tráfico y pruebas en laboratorio.

**Riesgo/límite:** No habilitar escaneo de terceros ni plantillas intrusivas por defecto.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

## Forense digital (11-20)

### 11. [Velociraptor](https://github.com/Velocidex/velociraptor) — P1

**Función:** Adquisición forense y consultas VQL de endpoints.

**Razón de seleccionarlo:** Proporciona artefactos reales de hosts propios que faltan en el flujo forense actual.

**Interfaz y trabajo propuesto:** Host propio con autorización -> colección con identidad y hashes -> custodia y correlación.

**Condición de aceptación:** Demostrar recolección local limitada, cadenas de custodia e inexistencia de secretos en logs.

**Riesgo/límite:** No desplegar agentes o hacer triage de terceros; AGPL.

**Licencia preliminar:** AGPL-3.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 12. [Volatility 3](https://github.com/volatilityfoundation/volatility3) — P1

**Función:** Extracción de artefactos de memoria RAM y estado volátil.

**Razón de seleccionarlo:** Ayuda a explicar procesos/actividad que no dejaron huellas persistentes.

**Interfaz y trabajo propuesto:** Imagen RAM sellada -> plugins y offsets -> hallazgos ligados al original.

**Condición de aceptación:** Reproducir artefactos sobre imágenes de laboratorio y contrastar otro extractor.

**Riesgo/límite:** VSL impone condiciones incluso a ciertos wrappers y añadidos; revisión legal obligatoria.

**Licencia preliminar:** Volatility Software License 1.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 13. [The Sleuth Kit](https://github.com/sleuthkit/sleuthkit) — P1

**Función:** Análisis de imágenes de disco, particiones, metadatos y sistema de archivos.

**Razón de seleccionarlo:** Permite recuperar evidencia persistente y ubicar bytes en su fuente.

**Interfaz y trabajo propuesto:** Imagen readonly -> parsing de FS -> offsets/hashes/metadata -> expediente.

**Condición de aceptación:** Pruebas de lectura no destructiva y resultados contrastados con herramienta independiente.

**Riesgo/límite:** Licencias heterogéneas; no escribir jamás sobre imagen original.

**Licencia preliminar:** Múltiples licencias según módulo. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 14. [Plaso](https://github.com/log2timeline/plaso) — P0

**Función:** Extracción y normalización de eventos para líneas de tiempo forenses.

**Razón de seleccionarlo:** Extiende nuestras pruebas de journal a eventos multiformato reproducibles.

**Interfaz y trabajo propuesto:** Artefactos verificados -> eventos con marca temporal y procedencia -> correlador.

**Condición de aceptación:** Reproducir cronología con relojes discrepantes, eventos duplicados y campos faltantes.

**Riesgo/límite:** La coincidencia temporal no demuestra relación causal.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 15. [Timesketch](https://github.com/google/timesketch) — P1

**Función:** Consulta colaborativa, anotación y análisis de timelines.

**Razón de seleccionarlo:** Ayuda a investigar relaciones complejas y compartir hipótesis sin perder contexto.

**Interfaz y trabajo propuesto:** Eventos Plaso/normalizados -> interfaz de exploración -> exportación versionada.

**Condición de aceptación:** Comprobar importación/exportación, control de acceso y conservación de IDs.

**Riesgo/límite:** La UI no es un verificador de autenticidad; datos privados requieren acceso restringido.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 16. [Arkime](https://github.com/arkime/arkime) — P2

**Función:** Captura/indexado y búsqueda de paquetes PCAP.

**Razón de seleccionarlo:** Aporta bitstream de comunicaciones para corroborar logs derivados.

**Interfaz y trabajo propuesto:** Red de laboratorio -> PCAP original con hash -> sesiones/índices -> análisis.

**Condición de aceptación:** Comparar PCAP con sesiones indexadas y reejecución de parser.

**Riesgo/límite:** Requiere almacenamiento y retención cuidadosa de datos potencialmente sensibles.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 17. [Zeek](https://github.com/zeek/zeek) — P1

**Función:** Análisis semántico de protocolos y generación de logs de red.

**Razón de seleccionarlo:** Crea eventos útiles para correlacionar con endpoints y PCAP de Arkime.

**Interfaz y trabajo propuesto:** PCAP de laboratorio -> registros estructurados/versionados -> hipótesis.

**Condición de aceptación:** Verificar eventos contra paquetes y controles de protocolo malformado.

**Riesgo/límite:** Logs interpretados no prueban intención del actor ni reemplazan capturas originales.

**Licencia preliminar:** Licencia permisiva propia tipo BSD. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 18. [Ghidra](https://github.com/NationalSecurityAgency/ghidra) — P2

**Función:** Análisis estático, descompilación y automatización de binarios.

**Razón de seleccionarlo:** Amplía investigación a componentes sin código fuente y malware de laboratorio.

**Interfaz y trabajo propuesto:** Binario aislado -> CFG/decompilación -> hipótesis -> validación dinámica.

**Condición de aceptación:** Descompilar muestras benignas y maliciosas inertes con controles y tiempos límite.

**Riesgo/límite:** No ejecutar muestras sin sandbox; revisar vulnerabilidades del analizador.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 19. [Hayabusa](https://github.com/Yamato-Security/hayabusa) — P1

**Función:** Forense rápido de eventos Windows EVTX y reglas Sigma.

**Razón de seleccionarlo:** Introduce señales de compromisos Windows a la correlación multifuente.

**Interfaz y trabajo propuesto:** EVTX sellado -> reglas versión fijada -> CSV/JSONL -> timeline.

**Condición de aceptación:** Repetir reglas con positivos/negativos y reportar falsos positivos.

**Riesgo/límite:** Licencias independientes de reglas; alerta no equivale a incidente confirmado.

**Licencia preliminar:** AGPL-3.0; reglas Sigma con licencia propia. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 20. [Cloud Forensics Utils](https://github.com/google/cloud-forensics-utils) — P2

**Función:** Adquisición forense de recursos AWS, Azure y GCP.

**Razón de seleccionarlo:** Permite investigar evidencia de infraestructura cloud propia o autorizada.

**Interfaz y trabajo propuesto:** Cuenta sandbox y permisos mínimos -> snapshots/copia -> evidencia sellada.

**Condición de aceptación:** Comprobar permisos mínimos, cifrado, trazas de auditoría y coste real.

**Riesgo/límite:** Acceso cloud y snapshots pueden generar gastos; no usar credenciales de producción.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

## Rendimiento y sistemas distribuidos (21-30)

### 21. [Ray](https://github.com/ray-project/ray) — P2

**Función:** Cómputo paralelo y actores distribuidos.

**Razón de seleccionarlo:** Permite escalar experimentos cuando la medición indique saturación de capacidad.

**Interfaz y trabajo propuesto:** Tareas autorizadas -> workers con cuotas -> resultados con hash y eventos.

**Condición de aceptación:** Benchmark contra proceso local con CPU/memoria iguales, fallos y p95.

**Riesgo/límite:** Distribución introduce overhead; no desplegar cluster sin necesidad.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 22. [Temporal](https://github.com/temporalio/temporal) — P2

**Función:** Workflows duraderos, checkpoints y recuperación de errores.

**Razón de seleccionarlo:** Evita perder investigaciones cuando los workers se interrumpen.

**Interfaz y trabajo propuesto:** Investigación con identidad -> workflow y tareas idempotentes -> estado retomable.

**Condición de aceptación:** Simular cortes/reintentos sin duplicar acciones de red ni efectos secundarios.

**Riesgo/límite:** Reintentos no sustituyen autorización ni hacen atómicos efectos externos.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 23. [NATS](https://github.com/nats-io/nats-server) — P2

**Función:** Bus de eventos para coordinar motores y workers.

**Razón de seleccionarlo:** Reduce acoplamiento y permite distribuir trabajos con consumidores rastreables.

**Interfaz y trabajo propuesto:** Evento tipado -> JetStream/consumidor -> acuse e idempotencia.

**Condición de aceptación:** Reprobar entrega duplicada, replay, particiones y separación entre programas.

**Riesgo/límite:** No presuponer exactly-once; configurar autenticación y red privada.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 24. [Valkey](https://github.com/valkey-io/valkey) — P1

**Función:** Caché de bajo tiempo de respuesta y deduplicación.

**Razón de seleccionarlo:** Evita recalcular compilaciones y consultas cuando contexto no cambia.

**Interfaz y trabajo propuesto:** Clave por digest de fuente+versión+política -> hit válido o recálculo.

**Condición de aceptación:** Invalidar con un byte cambiado, nuevas restricciones, permisos y expiración.

**Riesgo/límite:** Nunca usar caché como evidencia primaria ni almacenar secretos.

**Licencia preliminar:** BSD-3-Clause. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 25. [Pants](https://github.com/pantsbuild/pants) — P1

**Función:** Build y QA incrementales según grafo de dependencias.

**Razón de seleccionarlo:** Puede reducir la repetición del QA de nuestro repositorio grande.

**Interfaz y trabajo propuesto:** Fuentes/dependencias -> ejecución selectiva -> resultados con anclas.

**Condición de aceptación:** Demostrar misma detección que QA completo en cambios controlados y adversariales.

**Riesgo/límite:** No sustituir gates completos de release por tests filtrados.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 26. [OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector) — P0

**Función:** Recepción y exportación de telemetría de servicios.

**Razón de seleccionarlo:** Permite localizar cuellos de botella con latencias p50/p95/p99 reales.

**Interfaz y trabajo propuesto:** Trazas/métricas redactadas de worker -> collector -> tablero de rendimiento.

**Condición de aceptación:** Medir overhead y evitar fuga de objetivos, credenciales o expedientes.

**Riesgo/límite:** Separar telemetría operativa de cadena de custodia forense.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 27. [Parca](https://github.com/parca-dev/parca) — P1

**Función:** Profiling continuo de consumo de CPU y RAM.

**Razón de seleccionarlo:** Señala funciones críticas antes de optimizar código intuitivamente.

**Interfaz y trabajo propuesto:** Perfil de proceso propio -> hotspots -> regresión controlada.

**Condición de aceptación:** Comparar costo y duración antes/después sin cambiar los resultados.

**Riesgo/límite:** eBPF y agentes pueden requerir permisos de host; no habilitar por defecto.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 28. [DuckDB](https://github.com/duckdb/duckdb) — P1

**Función:** Motor SQL analítico embebido para grandes conjuntos de resultados.

**Razón de seleccionarlo:** Facilita analizar cobertura, hallazgos y experimentos sin depender de un clúster.

**Interfaz y trabajo propuesto:** Resultados JSON/Parquet -> consultas versionadas -> estadísticas comparables.

**Condición de aceptación:** Controles de deduplicación, conteos independientes y segregación de datos.

**Riesgo/límite:** No inferir precisión de reportes solo con métricas operativas.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 29. [Firecracker](https://github.com/firecracker-microvm/firecracker) — P2

**Función:** MicroVMs de aislamiento para herramientas y experimentos no confiables.

**Razón de seleccionarlo:** Reduce exposición del host al evaluar código y binarios de terceros.

**Interfaz y trabajo propuesto:** Imagen firmada + límites -> microVM sin salida de red -> artefactos sellados.

**Condición de aceptación:** Probar recursos, filesystem, egress y destrucción de VM con fallos deliberados.

**Riesgo/límite:** Requiere Linux/KVM y hardening; aislamiento no es absoluto.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 30. [K3s](https://github.com/k3s-io/k3s) — P3

**Función:** Orquestación de servicios/workers en nodos de cómputo.

**Razón de seleccionarlo:** Sirve cuando haya varios hosts y necesidad demostrada de escalado.

**Interfaz y trabajo propuesto:** Cluster aprobado -> pods con recursos/políticas -> resultados auditables.

**Condición de aceptación:** Pruebas de recuperación, segregación, límites y costo vs único host.

**Riesgo/límite:** No desplegar por moda; Kubernetes añade superficie de ataque.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

## Algoritmos de investigación (31-40)

### 31. [BoTorch](https://github.com/meta-pytorch/botorch) — P1

**Función:** Planificación y optimización bayesiana de experimentos.

**Razón de seleccionarlo:** Propone pruebas según información esperada, incertidumbre y costo en vez de fuerza bruta.

**Interfaz y trabajo propuesto:** Resultados calibrados -> política de adquisición -> próxima hipótesis.

**Condición de aceptación:** Benchmark ciego contra selección aleatoria y heurística bajo CPU/tasa idénticos.

**Riesgo/límite:** Un modelo mal calibrado puede descartar hipótesis valiosas y elevar latencia.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 32. [LibAFL](https://github.com/AFLplusplus/LibAFL) — P1

**Función:** Biblioteca modular de feedback, mutadores y scheduling de fuzzers.

**Razón de seleccionarlo:** Permite investigar estrategias originales sobre observaciones EVM y software.

**Interfaz y trabajo propuesto:** Harness propio -> feedback instrumental -> mutación y corpus -> verificación.

**Condición de aceptación:** Medir cobertura y fallos nuevos con ablations y semillas fijadas.

**Riesgo/límite:** Parte del fundamento de ItyFuzz; evitar duplicar motor y licencias sin revisar.

**Licencia preliminar:** MIT/Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 33. [Fuzz Introspector](https://github.com/ossf/fuzz-introspector) — P1

**Función:** Análisis de cobertura y puntos inaccesibles de campañas de fuzzing.

**Razón de seleccionarlo:** Ayuda a identificar bloqueos y mejorar harnesses en vez de gastar cómputo inútil.

**Interfaz y trabajo propuesto:** Instrumentación -> métricas de reachability -> propuestas de nuevos ensayos.

**Condición de aceptación:** Validar mejora de cobertura significativa en corpus reservado y presupuesto fijo.

**Riesgo/límite:** No extrapolar métricas de código nativo a EVM sin adaptador probado.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 34. [Z3](https://github.com/Z3Prover/z3) — P0

**Función:** Solución SMT de restricciones y obligaciones lógicas.

**Razón de seleccionarlo:** Permite expresar invariantes contables y sintetizar contraejemplos matemáticos.

**Interfaz y trabajo propuesto:** Fórmula con supuestos/versiones -> SAT/UNSAT/UNKNOWN -> replay independiente.

**Condición de aceptación:** Casos SAT/UNSAT/UNKNOWN, timeout, doble chequeo con cálculo concreto.

**Riesgo/límite:** Z3 ya está presente en SuperHunter; ampliación planificada, no instalación nueva.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 35. [angr](https://github.com/angr/angr) — P2

**Función:** Ejecución simbólica y análisis de rutas de binarios nativos.

**Razón de seleccionarlo:** Investiga estados en componentes donde no tenemos fuente y fuzzing pierde cobertura.

**Interfaz y trabajo propuesto:** Binario aislado -> constraints/candidatos -> prueba nativa independiente.

**Condición de aceptación:** Validar un camino real en sandbox y controlar explosión combinatoria.

**Riesgo/límite:** No confundir ISA nativa con semántica EVM.

**Licencia preliminar:** BSD-2-Clause. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 36. [Triton](https://github.com/JonathanSalwan/Triton) — P2

**Función:** Ejecución simbólica dinámica y rastreo taint en binarios.

**Razón de seleccionarlo:** Complementa angr con observación de flujos concretos y expresiones simbólicas.

**Interfaz y trabajo propuesto:** Traza de laboratorio -> dependencias y AST -> comparación con ejecución.

**Condición de aceptación:** Casos multi-ISA limitados con replay y falsos positivos registrados.

**Riesgo/límite:** Fiabilidad del motor y cobertura ISA requieren validación; aislar binarios.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 37. [Joern](https://github.com/joernio/joern) — P1

**Función:** Code Property Graphs para análisis de sintaxis, control y flujos.

**Razón de seleccionarlo:** Descubre relaciones entre componentes de aplicaciones complejas y nuevas APIs.

**Interfaz y trabajo propuesto:** Fuentes propias/autorizadas -> CPG versionado -> consultas -> hipótesis.

**Condición de aceptación:** Comparar grafos conocidos, dependencias y detección con casos reservados.

**Riesgo/límite:** Complementa Slither, no sustituye su análisis especializado de Solidity.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 38. [Soufflé](https://github.com/souffle-lang/souffle) — P1

**Función:** Motor Datalog de reglas y relaciones derivadas.

**Razón de seleccionarlo:** Conecta relaciones estructurales, estados y evidencias en hipótesis auditables.

**Interfaz y trabajo propuesto:** Hechos con procedencia -> reglas Datalog versionadas -> explicaciones.

**Condición de aceptación:** Controles positivos y negativos, relaciones cíclicas y procedencia.

**Riesgo/límite:** Inferencias lógicas no demuestran causalidad por sí mismas.

**Licencia preliminar:** UPL-1.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 39. [Hypothesis](https://github.com/HypothesisWorks/hypothesis) — P0

**Función:** Property-based testing de módulos Python con shrinking.

**Razón de seleccionarlo:** Detecta errores de parsers, verificadores y oráculos del propio Hunter.

**Interfaz y trabajo propuesto:** Generadores adversariales -> test de propiedad -> contraejemplo mínimo.

**Condición de aceptación:** Fijar semilla/ejemplo y reproducir resultados con datos malformados.

**Riesgo/límite:** No prueba exhaustividad ni garantiza hallazgos en terceros.

**Licencia preliminar:** MPL-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 40. [OSS-Fuzz-Gen](https://github.com/google/oss-fuzz-gen) — P2

**Función:** Generación y evaluación de harnesses usando modelos de lenguaje.

**Razón de seleccionarlo:** Reduce preparación manual en nuevos proyectos C/C++/Java/Python.

**Interfaz y trabajo propuesto:** Fuente autorizada -> harness generado -> revisión, compilación y fuzz en sandbox.

**Condición de aceptación:** Medir porcentaje compilable, nueva cobertura y fallos confirmados vs manual.

**Riesgo/límite:** Código generado es no confiable; prohibido ejecutar fuera de aislamiento.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

## Operación bug bounty (41-50)

### 41. [OWASP Amass](https://github.com/owasp-amass/amass) — P1

**Función:** Inventario pasivo y relaciones de activos de alcance autorizado.

**Razón de seleccionarlo:** Permite mapear programas nuevos sin improvisar URLs y dependencias.

**Interfaz y trabajo propuesto:** Documento de alcance -> enumeración pasiva -> filtro de admisión por objetivo.

**Condición de aceptación:** Verificar que no se admiten dominios fuera de alcance y registrar procedencia.

**Riesgo/límite:** Enumeración activa solo con permiso explícito, no por estar en bug bounty.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 42. [Katana](https://github.com/projectdiscovery/katana) — P1

**Función:** Crawling web/headless y descubrimiento de rutas, formularios y APIs.

**Razón de seleccionarlo:** Acelera entender las funcionalidades y cambios de una aplicación.

**Interfaz y trabajo propuesto:** Host aprobado -> crawl con límites -> mapa versionado de endpoints.

**Condición de aceptación:** Probar con app local y exclusiones; validar que no hay peticiones destructivas.

**Riesgo/límite:** Navegar puede activar efectos de estado; limitar profundidad y tasa.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 43. [ZAP](https://github.com/zaproxy/zaproxy) — P1

**Función:** Análisis de tráfico y pruebas dinámicas de seguridad web/API.

**Razón de seleccionarlo:** Complementa el código estático con el comportamiento real de la aplicación.

**Interfaz y trabajo propuesto:** App local -> proxy y pasivo -> checks activos bajo permiso -> evidencia.

**Condición de aceptación:** Pruebas con sesión, cookies y fallos sembrados; registrar tasa de FP.

**Riesgo/límite:** Modo activo puede afectar estado; por defecto solo laboratorio/pasivo.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 44. [Interactsh](https://github.com/projectdiscovery/interactsh) — P2

**Función:** Correlación de interacciones de prueba fuera de banda.

**Razón de seleccionarlo:** Detecta comportamientos que no aparecen en la respuesta HTTP directa.

**Interfaz y trabajo propuesto:** Receptor propio controlado -> eventos DNS/HTTP -> correlación al caso.

**Condición de aceptación:** Verificar eventos en laboratorio sin enviar datos confidenciales.

**Riesgo/límite:** Evitar servicios OOB públicos para pruebas privadas o exfiltración.

**Licencia preliminar:** MIT. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 45. [Foundry](https://github.com/foundry-rs/foundry) — P0

**Función:** Forge/Anvil/Cast para pruebas y reproducción EVM aislada.

**Razón de seleccionarlo:** Convierte hipótesis DeFi en pruebas reproducibles, con estados históricos si están disponibles.

**Interfaz y trabajo propuesto:** Contrato propio/fork local -> test/invariant -> traza y replay.

**Condición de aceptación:** Comprobar estado inicial, bytecode, bloque, resultado y fallos negativos.

**Riesgo/límite:** Ya hay uso parcial relacionado; prohibido broadcast o firmas operativas.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 46. [Alloy](https://github.com/alloy-rs/alloy) — P2

**Función:** Cliente Rust Ethereum de alto rendimiento para RPC, ABI y datos.

**Razón de seleccionarlo:** Puede acelerar ingestión y normalización de bloques y eventos EVM.

**Interfaz y trabajo propuesto:** RPC de lectura aprobado -> ABI/recibos -> datos con identidad y hashes.

**Condición de aceptación:** Comparar bytes con otra implementación y medir latencia y confiabilidad.

**Riesgo/límite:** No habilitar wallets, firmas ni envío de transacciones.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 47. [Trivy](https://github.com/aquasecurity/trivy) — P1

**Función:** Escaneo de supply chain, contenedores, CVEs, secretos e IaC.

**Razón de seleccionarlo:** Cubre seguridad de infraestructura y dependencias en programas que la incluyan.

**Interfaz y trabajo propuesto:** Repo/imagen autorizada -> SBOM y hallazgos tipados -> revisión.

**Condición de aceptación:** Controles CVE conocidos, falsos positivos y versión de base de datos.

**Riesgo/límite:** CVE conocido no implica bounty; no publicar secretos detectados.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 48. [Open Policy Agent](https://github.com/open-policy-agent/opa) — P0

**Función:** Motor declarativo de políticas de autorización por programa.

**Razón de seleccionarlo:** Impide que la orquestación considere permitido un objetivo por simple descubrimiento.

**Interfaz y trabajo propuesto:** Scope firmado/validado -> decisión allow/deny por operación -> audit log.

**Condición de aceptación:** Fail closed con scope faltante, expirado, ambiguo o excluido; aislar programas.

**Riesgo/límite:** OPA aplica políticas, no sustituye permiso legal o humano real.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 49. [Cosign](https://github.com/sigstore/cosign) — P1

**Función:** Firmas y verificación de procedencia de artefactos.

**Razón de seleccionarlo:** Distingue integridad por hash de identidad de quien generó evidencia.

**Interfaz y trabajo propuesto:** Artefacto privado -> firma/attestation -> verificación de identidad.

**Condición de aceptación:** Manipulación de bytes, identidad y certificado debe producir rechazo.

**Riesgo/límite:** Firmas no certifican veracidad; no publicar evidencia privada en logs transparentes.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

### 50. [Threat Dragon](https://github.com/OWASP/threat-dragon) — P1

**Función:** Modelado de amenazas, límites de confianza y arquitectura.

**Razón de seleccionarlo:** Ayuda a convertir diseños nuevos en hipótesis que deben probarse.

**Interfaz y trabajo propuesto:** Diagrama versionado -> amenazas/properties -> experimentos revisables.

**Condición de aceptación:** Validar en diseños de laboratorio que cada amenaza mapee a prueba observable.

**Riesgo/límite:** El modelado por sí solo no descubre fallos ni demuestra impacto.

**Licencia preliminar:** Apache-2.0. **Estado:** `CATALOGUED_NOT_INTEGRATED`.

## Plan inicial, sin ejecución en esta entrega

En un contrato propio, usar Slither y Gambit para hipótesis y mutantes, Echidna/ItyFuzz para secuencias, Z3/Kontrol para propiedades y Foundry/Geth/EELS para confirmar o refutar, con evidencias verificadas. En forense, Plaso/Zeek sobre logs y PCAP propios, sin inferir causalidad por coincidencia temporal. Medir rendimiento con OpenTelemetry/Parca antes de incorporar Ray/K3s. La aprobación de cada integración requiere pruebas de beneficio real y compatibilidad/licencia, sin tocar árboles históricos NQC, nexus-engine, Cano o Vercel.

**Estado real:** consultar [SUPERHUNTER_STATUS.md](../SUPERHUNTER_STATUS.md), no atribuir un porcentaje por esta lista. Desglose y campos estructurados en [repo_portfolio/](repo_portfolio/).
