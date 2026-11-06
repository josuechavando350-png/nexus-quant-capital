# SUPERHUNTER — PLAN MAESTRO Y CONTRATO DE CONTINUIDAD

**Fecha de decisión:** 2026-11-06. **Estado:** plan oficial de producto/ingeniería; NO es certificación ni declaración de implementación terminada. **Repositorio público:** `josuechavando350-png/nexus-quant-capital`. **Rama de referencia:** `main`. **Ámbito de código:** `superhunter/` sin modificar árboles históricos NQC.

**Estrategia de especialización crítica, múltiples dominios y cadenas:** [SUPERHUNTER_CRITICAL_RESEARCH.md](SUPERHUNTER_CRITICAL_RESEARCH.md). Las 100 capacidades nuevas permanecen propuestas hasta verificación real.

**Estado más reciente y commit de continuidad:** [SUPERHUNTER_STATUS.md](SUPERHUNTER_STATUS.md). Leerlo antes de asumir que `main` contiene todo el código.

## 0. Instrucción para cualquier nueva conversación o agente
Leer ESTE archivo antes de hacer cambios; leer además `AGENTS.md`, `README.md`, `migration/IMPORT-PLAN.md`, los tres inventarios originales de SuperHunter (cuando se publiquen en `superhunter/`) y los manifiestos de verificación. Consultar HEAD/PRs actuales, recuperar la última fuente íntegra y reejecutar pruebas **antes de programar**. No inferir un porcentaje a partir de la cantidad de tests; no sustituir una versión local acumulada por una rama remota parcial. Comparar diffs, preservar los 27+50+25 ítems originales y registrar avances como código, tests y verificadores reproducibles.

## 1. Misión
Construir **SUPERHUNTER — Sovereign Security Intelligence**, una plataforma autónoma de investigación de seguridad y defensa de categoría mundial: investigación de vulnerabilidades y Bug Bounty **estrictamente autorizados** (HUNTER) + observabilidad, forense digital, detección, respuesta y recuperación (GUARDIAN). Una sola inteligencia científica compartida con percepción (ojos), análisis causal (tercer ojo), experimentación aislada (manos), planificación/orquestación (pies), memoria verificable y supervisión. Objetivo de diferenciación: superar a herramientas líderes en métricas comparables; no afirmar superioridad antes de pruebas independientes ni prometer perfección absoluta o monopolio legal de mercado.

### Requisitos de producto que NO se pierden
- Investigación continua 24/7 con recuperación ante fallos **cuando** el sistema esté operacional y auditado; objetivo 20 programas simultáneos con políticas individuales y participación verificada, no 20 procesos ficticios.
- Ámbitos: EVM/DeFi/contratos inteligentes primero; después APIs, aplicaciones, infraestructura, cloud, contenedores, cadena de suministro y software distribuido.
- Hallazgos: hipótesis -> evidencia -> reproducción -> verificación independiente -> impacto y severidad sustentados -> revisión y reporte responsable; nunca convertir inferencia de LLM en prueba.
- White hat y mentalidad grey hat solo **dentro de autorización efectiva**; código público/análisis offline, objetivos propios o laboratorios aislados no equivalen a permiso para probar servicios ajenos.
- Tecnología original donde aporte una mejora medible; reutilizar componentes maduros donde sean mejores. Cero código falso, relleno, métodos vacíos o mocks presentados como producción. Un módulo sin consumidores reales y pruebas de integración NO cuenta como terminado.
- No secretos, fondos, firmas, broadcasts, transacciones, escaneos externos sin permiso, envío automático de bounties sin reglas y revisión humana, intrusión de terceros ni evasión de controles; no activar workflows, despliegues ni permisos sin revisión explícita.
- Nunca tocar `josuechavando350-png/nexus-engine`, Cano/Vercel ni sistemas de clientes; preservar `ci/`, `migration/`, `nqc-census/` y sus identidades/hashes históricos.

## 2. Estado y fuentes recuperadas (NO equivalen a avance porcentual)
- Baseline local recuperado del archivo de Biblioteca `SUPERHUNTER_holdout_etiquetas_2005.zip`, SHA-256 `c5a3ce77720213a3fa4e19da8faac84a41594b7823e90d2ac246d5119e57267f`, con 242 entradas; ZIP íntegro en la revisión del 2026-11-06. La carpeta `codigo/superhunter/` contiene fuentes y tests. NO subir artefactos privados de etiquetas/nonces.
- Reporte histórico `RESULTADOS.md`: 2,005 tests `LOCAL_QA_PASS`, 0 fallos/errores/skips, +36 sobre 1,969; identidad de fuentes registrada: `205b61fee612c263510c581216010c527d84e51f934d2c1ca9451fbd87ed6ed4`. Este resultado debe **reejecutarse** tras la restauración; no implica benchmark ciego auténtico, ni vulnerabilidades originales ni nivel mundial.
- Tres catálogos rectoramente separados: `superhunter/integration-checklist.json` 27 requisitos (12 `IMPLEMENTED_BOUNDED`, 3 `PARTIAL`, 12 `PENDING`); `superhunter/capabilities.json` 50 capacidades (9 `PARTIAL`, 24 `PLANNED`, 17 `REDESIGN_REQUIRED`); `superhunter/research_initiatives.json` 25 iniciativas (5 `PARTIAL`, 20 `PLANNED`). Estos conteos son registros históricos del baseline, no estado revalidado ni una ponderación de progreso.
- El 40–42% citado en conversaciones anteriores es **referencia informal NO auditada**. Progreso real solo se determina por hitos con criterios de salida.
- En `main` todavía NO estaba `superhunter/` antes de este plan. PRs históricos #35–#44 permanecían en borrador y con líneas de desarrollo paralelas; algunos expresamente omiten código acumulado. No fusionarlos directamente sin conciliación.
- El archivo de biblioteca `/SUPERHUNTER_Publicacion_20261106/` contiene transferencias `transfer-000.txt` a `transfer-053.txt` con catálogo `GH_EXPECTED_COMPACT.json` de **214** rutas previstas; es respaldo preparado, NO prueba de publicación. No confundir 214 rutas con 242 entradas del ZIP, que incluye informes y otros materiales.

## 3. Diseño del núcleo
```text
Fuentes y sensores ─> Identidades + cadena de custodia ─> modelo de estados/grafo causal
                          |                                 |
                          v                                 v
                  memoria científica <─> planificador <─> laboratorio aislado
                          |                                 |
                          +─> verificación independiente <─┘
                                     |
                         CONFIRMADO / REFUTADO / INCONCLUSO
                                     |
                        HUNTER (divulgación) / GUARDIAN (defensa)
                                     |
                           benchmarks y mejora controlada
```

Contratos compartidos propuestos: `Observation`, `Artifact`, `SourceIdentity`, `AuthorizationScope`, `Hypothesis`, `Experiment`, `ExecutionTrace`, `ProofObligation`, `VerificationResult`, `Finding`, `Remediation`, `Incident`, `BenchmarkRun`. Identidad de repositorio/commit, chain/block, versiones, evidencia, entorno y políticas son explícitas, nunca inferidas por conveniencia. Persistencia transaccional + blobs direccionados por contenido. No almacenar secretos o etiquetas privadas en un repositorio público.

## 4. Cinco líneas de invención propias (R&D, no funcionalidades ya realizadas)
1. **Causal State Reconstruction** — temporal knowledge graph con procedencia, semántica de estados y reconstrucción forense; comparar secuencias causalmente plausibles, incertidumbre y evidencias contradictorias.
2. **Counterfactual Research Planner** — planificador de experimentos por ganancia esperada de información, costo, cobertura, riesgo y permisos.
3. **Bidirectional Property Synthesis** — inferencia de invariantes desde código y observaciones, generación de contraejemplos y refinamiento de especificaciones.
4. **Differential World Verification** — validar que el gemelo computacional coincide con ejecuciones independientes; localizar divergencias y degradar confianza apropiadamente.
5. **Proof-Carrying Findings** — cada hallazgo conserva identidad, condiciones, evidencia, testigo, pasos de reproducción acotados, contra-controles, revisión y declaración explícita de límites.

## 5. Backlog adicional de 100 capacidades (todo estado inicial: PROPOSED)
Los ID `SH-XX-YY` son estables y distintos de los 27+50+25 originales. Ninguno se declara IMPLEMENTED por el solo hecho de figurar aquí. Cada ítem requiere fuente ejecutable, test positivo/negativo/adversarial, verificador y consumidor integrado.

### SH-01 — DFIR y forense digital
**Gate de aceptación de disciplina:** Reconstruir un incidente de laboratorio desde evidencias independientes, preservar originales y detectar manipulaciones.

- `SH-01-01` Ingesta forense de imágenes de disco — `PROPOSED`.
- `SH-01-02` Análisis de memoria RAM — `PROPOSED`.
- `SH-01-03` Reconstrucción de sistemas de archivos — `PROPOSED`.
- `SH-01-04` Análisis de eventos Windows — `PROPOSED`.
- `SH-01-05` Análisis de registros Linux — `PROPOSED`.
- `SH-01-06` Inspección de capturas de red — `PROPOSED`.
- `SH-01-07` Evidencia de contenedores — `PROPOSED`.
- `SH-01-08` Evidencia cloud — `PROPOSED`.
- `SH-01-09` Cronologías con incertidumbre temporal — `PROPOSED`.
- `SH-01-10` Reconstrucción causal de incidentes — `PROPOSED`.

### SH-02 — Telemetría y percepción profunda
**Gate de aceptación de disciplina:** Observar en un entorno propio un evento y enlazarlo con proceso, origen, pérdida y duplicación medibles.

- `SH-02-01` Sensor Linux eBPF — `PROPOSED`.
- `SH-02-02` Sensor Windows ETW — `PROPOSED`.
- `SH-02-03` Procesos y árboles de ejecución — `PROPOSED`.
- `SH-02-04` Cambios de permisos — `PROPOSED`.
- `SH-02-05` Actividad DNS — `PROPOSED`.
- `SH-02-06` Metadatos TLS — `PROPOSED`.
- `SH-02-07` Eventos Kubernetes — `PROPOSED`.
- `SH-02-08` Telemetría CI/CD — `PROPOSED`.
- `SH-02-09` Trazas distribuidas — `PROPOSED`.
- `SH-02-10` Correlación con controles de privacidad — `PROPOSED`.

### SH-03 — Gemelo computacional de sistemas
**Gate de aceptación de disciplina:** Reproducir comportamientos seleccionados de un sistema instrumentado y declarar explícitamente los que el modelo no representa.

- `SH-03-01` Representación intermedia multidominio — `PROPOSED`.
- `SH-03-02` Identidad de almacenamiento — `PROPOSED`.
- `SH-03-03` Grafo tipado de componentes — `PROPOSED`.
- `SH-03-04` Estados simbólicos acotados — `PROPOSED`.
- `SH-03-05` Reproducción determinista — `PROPOSED`.
- `SH-03-06` Simulación de orden de eventos — `PROPOSED`.
- `SH-03-07` Diferencias entre upgrades — `PROPOSED`.
- `SH-03-08` Contratos de entorno — `PROPOSED`.
- `SH-03-09` Fronteras de confianza — `PROPOSED`.
- `SH-03-10` Comprobación de equivalencia modelo-ejecución — `PROPOSED`.

### SH-04 — Inteligencia causal y Third Eye
**Gate de aceptación de disciplina:** Distinguir causalidad de correlación con intervenciones controladas, ablation y verificadores independientes.

- `SH-04-01` Generación de hipótesis — `PROPOSED`.
- `SH-04-02` Experimentos contrafactuales — `PROPOSED`.
- `SH-04-03` Priorización probabilística calibrada — `PROPOSED`.
- `SH-04-04` Detección de contradicciones — `PROPOSED`.
- `SH-04-05` Estudios de ablación — `PROPOSED`.
- `SH-04-06` Subgrafos causales — `PROPOSED`.
- `SH-04-07` Análisis de dependencias indirectas — `PROPOSED`.
- `SH-04-08` Precedencia temporal — `PROPOSED`.
- `SH-04-09` Localización de causas — `PROPOSED`.
- `SH-04-10` Explicaciones causales reproducibles — `PROPOSED`.

### SH-05 — Laboratorio experimental avanzado
**Gate de aceptación de disciplina:** Detectar defectos sembrados en software propio, minimizar el fallo y reproducirlo en otro proceso.

- `SH-05-01` Generación de harnesses — `PROPOSED`.
- `SH-05-02` Cobertura diferencial — `PROPOSED`.
- `SH-05-03` Fuzzing con estado — `PROPOSED`.
- `SH-05-04` Pruebas metamórficas — `PROPOSED`.
- `SH-05-05` Entradas mediante restricciones — `PROPOSED`.
- `SH-05-06` Minimización automática de fallos — `PROPOSED`.
- `SH-05-07` Snapshots reproducibles — `PROPOSED`.
- `SH-05-08` Detección de pruebas inestables — `PROPOSED`.
- `SH-05-09` Pruebas de mutación — `PROPOSED`.
- `SH-05-10` Planificación limitada por recursos — `PROPOSED`.

### SH-06 — Verificación formal y matemáticas computacionales
**Gate de aceptación de disciplina:** Demostrar/refutar propiedades con supuestos y testigos; preservar SAT, UNSAT, UNKNOWN y timeouts.

- `SH-06-01` Lenguaje tipado de especificaciones — `PROPOSED`.
- `SH-06-02` Correspondencia especificación-código — `PROPOSED`.
- `SH-06-03` Resolución SMT — `PROPOSED`.
- `SH-06-04` Cláusulas de Horn restringidas — `PROPOSED`.
- `SH-06-05` Model checking temporal — `PROPOSED`.
- `SH-06-06` Aritmética exacta — `PROPOSED`.
- `SH-06-07` Diferencias semánticas de compiladores — `PROPOSED`.
- `SH-06-08` Verificación de artefactos de prueba — `PROPOSED`.
- `SH-06-09` Comprobación de concurrencia — `PROPOSED`.
- `SH-06-10` Certificados acotados de propiedades — `PROPOSED`.

### SH-07 — Software, identidad y cadena de suministro
**Gate de aceptación de disciplina:** Mostrar una consecuencia identificable de un cambio de dependencia, permiso o configuración y generar regresión.

- `SH-07-01` Inventario SBOM verificable — `PROPOSED`.
- `SH-07-02` Alcanzabilidad de dependencias — `PROPOSED`.
- `SH-07-03` Procedencia de compilaciones — `PROPOSED`.
- `SH-07-04` Diferencias binarias — `PROPOSED`.
- `SH-07-05` Deriva de configuraciones — `PROPOSED`.
- `SH-07-06` Grafo de identidades — `PROPOSED`.
- `SH-07-07` Detección de exposición de credenciales — `PROPOSED`.
- `SH-07-08` Pruebas de contratos API — `PROPOSED`.
- `SH-07-09` Revisión de infraestructura como código — `PROPOSED`.
- `SH-07-10` Integridad de pipelines — `PROPOSED`.

### SH-08 — Inteligencia científica autónoma
**Gate de aceptación de disciplina:** Cerrar una investigación de laboratorio con plan, experimentos, costos, incertidumbre y conclusión verificable.

- `SH-08-01` Planificador de investigaciones — `PROPOSED`.
- `SH-08-02` Descomposición de tareas — `PROPOSED`.
- `SH-08-03` Evaluación de experimentos — `PROPOSED`.
- `SH-08-04` Registro de contexto — `PROPOSED`.
- `SH-08-05` Crítico independiente — `PROPOSED`.
- `SH-08-06` Memoria con revisión de evidencias — `PROPOSED`.
- `SH-08-07` Calibración de incertidumbre — `PROPOSED`.
- `SH-08-08` Asignación de presupuesto — `PROPOSED`.
- `SH-08-09` Análisis retrospectivo — `PROPOSED`.
- `SH-08-10` Promoción controlada de mejoras — `PROPOSED`.

### SH-09 — Defensa autónoma y respuesta a incidentes
**Gate de aceptación de disciplina:** Detectar, contener en laboratorio autorizado, recuperar el servicio y comprobar corrección y regresiones.

- `SH-09-01` Detección multisensor — `PROPOSED`.
- `SH-09-02` Priorización basada en evidencia — `PROPOSED`.
- `SH-09-03` Propuestas de contención — `PROPOSED`.
- `SH-09-04` Simulación de impacto de contención — `PROPOSED`.
- `SH-09-05` Políticas de privilegio mínimo — `PROPOSED`.
- `SH-09-06` Planificación de recuperación — `PROPOSED`.
- `SH-09-07` Integridad de respaldos — `PROPOSED`.
- `SH-09-08` Autorizaciones humanas — `PROPOSED`.
- `SH-09-09` Regresiones posteriores al incidente — `PROPOSED`.
- `SH-09-10` Correlación entre detecciones y técnicas conocidas — `PROPOSED`.

### SH-10 — Evidencia, operación y evaluación
**Gate de aceptación de disciplina:** Operar expedientes paralelos sin mezclarlos y recuperar trabajos interrumpidos, con verificadores de evidencia.

- `SH-10-01` Almacén inmutable de evidencias — `PROPOSED`.
- `SH-10-02` Firmas verificables — `PROPOSED`.
- `SH-10-03` Aislamiento de expedientes — `PROPOSED`.
- `SH-10-04` Compilación de políticas de alcance — `PROPOSED`.
- `SH-10-05` Bitácora de aprobaciones — `PROPOSED`.
- `SH-10-06` Procedencia autenticada — `PROPOSED`.
- `SH-10-07` Generación de reportes — `PROPOSED`.
- `SH-10-08` Benchmarks con conjuntos ocultos — `PROPOSED`.
- `SH-10-09` Medición de costo y rendimiento — `PROPOSED`.
- `SH-10-10` Coordinación resiliente de investigaciones continuas — `PROPOSED`.

## 6. Ruta de entrega, con dependencias estrictas
**M0 — Consolidación verificable (primero, sin excepción):** comparar el baseline local 2,005 con cabezas de PR, inventariar artefactos privados/no-publicables, validar checksums y test IDs; restaurar fuente sin pérdidas en rama de desarrollo, reejecutar QA y verificadores aislados; mantener código NQC heredado intacto. Publicar PR revisable; no cambiar porcentajes. La mera publicación del plan no completa M0.

**M1 — Un circuito científico de extremo a extremo:** en un laboratorio propio, capturar 1 evidencia forense auténtica y una traza observable, enlazar identidades temporales, formular hipótesis, probar/refutar en sandbox, generar un finding con evidencias verificables y un plan de corrección. Test negativo: manipulación/ambigüedad produce rechazo o INCONCLUSO, no PASS.

**M2 — Investigación EVM especializada:** herramientas reales de Solidity/solc, Geth, Z3, invariantes, fuzzing guiado, distintas variantes de compilación y modelo económico sujeto a límites; replicar suites de laboratorio y defectos históricos autorizados; declarar cobertura y fallos no encontrados.

**M3 — Inteligencia causal y mejora de detección:** motores R&D #1–#5, evaluaciones ciegas con custodio externo, datasets train/dev/test separados, tests de filtraciones, baselines comparables de tiempo/costo/recall/precision y pruebas de ablación.

**M4 — Operación y defensa:** sensores operativos, DFIR, detección, gestión de incidentes, respuesta reversible con aprobación, recuperación comprobada; 20 programas concurrentes autorizados, cuotas, aislamiento, reintentos y auditoría; reportes revisados por humano según reglas de cada programa.

**M5 — Escalado y negocio:** prestaciones reproducibles, despliegues privados verificados, soporte, continuidad, mejoras versionadas; Bug Bounty, auditorías, servicios defensivos y licenciamiento. Prohibido prometer ingresos o monopolio sin evidencia.

## 7. Definición formal de «terminado»
Todo cambio debe presentar (a) código real probado y bytes rastreables; (b) identidad de fuente y entorno; (c) tests de unidad/integración/controles adversariales y todos los tests previos preservados; (d) consumidor demostrado dentro del flujo; (e) prueba de no afectar el NQC histórico; (f) resultado reproducido por proceso/verificador separado; (g) riesgos, supuestos, incertidumbre y límites explícitos; (h) comparación de rendimiento si se alega superioridad. Estado `PLANNED` no cuenta; un `PASS` sintético no implica operación externa. Un presupuesto agotado es `INCONCLUSO` o fallo, jamás prueba de ausencia de vulnerabilidad.

### Métricas obligatorias
- Tasa de descubrimientos confirmados (originales vs históricos, con procedencia), TP/FP/TN/FN, precision/recall, tasa de abstención, calibración, tiempo hasta reproducción, costo por hallazgo, cobertura de estado/entradas, estabilidad de reproducción, errores operativos y disponibilidad. Los benchmarks externos deben incluir conjuntos ocultos y presupuestos comparables. Nunca medir «90% de razonamiento» sin definir el conjunto evaluado.
- No clasificar como hallazgo ni prometer recompensa hasta verificar alcance, originalidad, reproducción, impacto, duplicados y revisión responsable.

## 8. Procedimiento de reanudación («siguiente conversación»)
1. Leer este archivo, `AGENTS.md` y estado `main`, luego PRs/branches; citar SHA de HEAD real.
2. Buscar la fuente consolidada bajo `superhunter/` o el ZIP de biblioteca antes indicado; no inventar que 2,005 pruebas ya corrieron en el nuevo HEAD.
3. Comparar SHA de ZIP y manifiesto, inventario 27+50+25 y 100 nuevas `SH-*`; revisar exclusiones y ausencia de secretos.
4. Conciliar código sobre rama nueva sin force-push ni auto-merge; `main` solo recibe plan/documentación y cambios revisados.
5. Ejecutar baseline QA y tests del nuevo módulo; documentar comandos, resultados, timeouts y dependencias ausentes.
6. Desarrollar exactamente el siguiente hito no terminado, comenzando por M0 y luego M1. Registrar avance en commits, PR y manifiestos de evidencia; actualizar este documento si cambia la decisión arquitectónica.
7. No pedir al usuario que vuelva a compartir el chat anterior: el estado debe poder inferirse de GitHub y los archivos de biblioteca. Si falta algún dato, marcarlo `UNKNOWN` y no inventarlo.
