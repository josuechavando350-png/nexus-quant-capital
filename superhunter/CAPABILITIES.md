# SUPERHUNTER — estado de las 50 capacidades

Las pruebas del paquete no demuestran detección de vulnerabilidades ni completan estas capacidades.
○ Pendiente · ◐ Parcial · ↻ Requiere reformulación defensiva. Ninguna está certificada completa.

○ **1. Consultas de grafos personalizadas (SlithIR)** — Pendiente: no hay SlithIR integrado ni trazado de fondos implementado.

○ **2. Análisis de contaminación de entradas (taint analysis)** — Pendiente: análisis estático de datos en código propio; las reglas de scope no son taint analysis.

○ **3. Fuzzing dinámico guiado por invariantes** — Pendiente: no se ha conectado un fuzzer; las pruebas unitarias existentes no son millones de transacciones.

○ **4. Fuzzing con bifurcación de red** — Pendiente: estados locales autorizados; no hay motor de forks integrado ni RPC activado.

↻ **5. Simulador de préstamos flash** — Reformular como pruebas de solvencia en modelos propios; no generador de ataques para drenar pools.

○ **6. Analizador de integración de oráculos** — Pendiente: comprobaciones contextuales de fuentes, frescura y unidades; spot/TWAP no decide por sí solo la seguridad.

○ **7. Inferencia simbólica estocástica** — Pendiente experimental: hipótesis sujetas a validación, no deducción garantizada de todas las reglas.

↻ **8. Estrategias de pruebas multibloque** — Reformular como pruebas de propiedades temporales en modelos propios, no planificador autónomo de ataques.

○ **9. Fuzzer de estado y memoria en laboratorio** — Pendiente: escenarios artificiales etiquetados como contrafactuales, nunca como explotabilidad demostrada.

○ **10. Orquestador LLM y simbólico** — Pendiente: propuestas revisables y comprobaciones deterministas; no se promete ausencia absoluta de alucinaciones.

○ **11. Diferenciales de bytecode** — Pendiente: comparación de versiones; el inventario SHA actual no es análisis semántico de bytecode.

○ **12. Simulación de corridas bancarias** — Pendiente: modelos de riesgo con supuestos explícitos y sensibilidad; no daño financiero garantizado.

○ **13. Taint analysis binario dinámico** — Pendiente: pruebas de software nativo propio; no hay instrumentación CPU/memoria integrada.

○ **14. Grafos de permisos** — Pendiente: grafo de autorizaciones; ScopeGuard no implementa análisis de escalada de privilegios.

↻ **15. Extractor automático de reproducciones** — Reformular como reducción de tests fallidos en código propio, no generación autónoma de exploits de terceros.

○ **16. Validación de firmas criptográficas** — Pendiente: regresiones locales de autorización, nonces y dominios; no extracción de claves.

○ **17. Inyección de fallos en sistemas distribuidos** — Pendiente: pruebas de fallos en infraestructura propia aislada; no perturbación de servicios ajenos.

○ **18. Análisis de reentrancia entre contratos** — Pendiente: revisión defensiva de llamadas y propiedades; no motor autónomo de explotación.

○ **19. Efectos del compilador** — Pendiente: verificar compilaciones equivalentes y diferencias; no hay análisis de optimizadores implementado.

○ **20. Fuzzer de API por gramáticas** — Pendiente: pruebas funcionales sobre APIs propias de laboratorio, sin encadenamiento ofensivo.

↻ **21. Fuzzing de protocolos de red** — Reformular como validación de parsers propios mediante tráfico de laboratorio; no fuzzing activo de terceros.

↻ **22. Análisis de canales laterales** — Reformular como medición de posibles fugas con secretos de prueba; no extracción de claves reales.

↻ **23. Consistencia HTTP y caché** — Reformular como revisión de configuración y conformidad proxy/backend; no secuestro de sesiones ni ataques automatizados.

○ **24. Consistencia de RBAC mutable** — Pendiente: modelos RBAC y revocación; el control de alcance actual no demuestra esta capacidad.

↻ **25. Análisis de deserialización** — Reformular como identificación de deserialización insegura y dependencias; no construcción de cadenas RCE.

○ **26. Verificación de circuitos ZK** — Pendiente: revisión de restricciones en circuitos propios; no motor ZK implementado.

○ **27. Concurrencia y memoria compartida** — Pendiente: instrumentación de concurrencia para programas propios; no primitivas de explotación.

↻ **28. Consenso y fallos bizantinos** — Reformular como simulación de tolerancia a fallos; no interrupción de consenso en redes externas.

○ **29. Fugas de información en logs** — Pendiente: revisión y redacción de logs autorizados, sin almacenar secretos innecesariamente.

○ **30. Dependencias vulnerables y alcanzabilidad** — Pendiente: inventario y alcanzabilidad; los hashes de fuentes no equivalen a un análisis de dependencias vulnerables.

↻ **31. Integridad de carga de bibliotecas** — Reformular como verificación de procedencia y configuración de bibliotecas; no inyección ni desvío de ejecución.

↻ **32. Validación de aislamiento de sandboxes** — Reformular como comprobación de aislamiento; no evolución de payloads para evadir sandboxes.

○ **33. Consistencia documentación/código** — Pendiente: no hay comparador semántico de especificaciones y código.

○ **34. Verificación formal acotada** — Pendiente: pruebas limitadas por modelo, propiedades y profundidad; sin garantía universal de cero falsos negativos.

↻ **35. Planificación de experimentos mediante MCTS** — Reformular como asignación de presupuesto de pruebas por cobertura; no planificación ni encadenamiento de exploits.

↻ **36. Grafo de conocimiento entre dominios** — Reformular como correlación defensiva de dependencias y riesgos, no diseño de ataques integrales.

○ **37. Triaje e impacto económico** — Pendiente: el puente recibe declaraciones económicas; RMC-016 calcula capacidad, no impacto de vulnerabilidades ni severidad oficial.

↻ **38. Aprendizaje con retroalimentación humana** — Reformular con consentimiento, feedback explícito y cambios revisados; no observación encubierta ni autoedición sin pruebas.

○ **39. Auditor visual de interfaz** — Pendiente: revisión de UI propia y comprobaciones del navegador; una imagen por sí sola no demuestra un fallo.

○ **40. Análisis de grafos mediante modelos** — Pendiente experimental: grafos como datos; no detección instantánea ni certeza a partir de imágenes.

○ **41. Diagramas y especificaciones visuales** — Pendiente: extracción de especificaciones con referencias verificables y revisión de ambigüedades.

↻ **42. Detección visual de exposición de secretos** — Reformular para material propio autorizado y redacción; no vigilancia de terceros ni recolección de credenciales.

↻ **43. Automatización de navegador para QA** — Reformular como automatización identificada de pruebas; sin evasión de WAF, bots ni captchas.

↻ **44. Generación adaptativa de entradas de prueba** — Reformular como pruebas de contratos de entrada y sanitización propios; no evasión adaptativa de filtros.

◐ **45. Orquestación de entornos de prueba** — Parcial: proceso local acotado para componentes fijados; no clonación Docker/DB/RPC ni sandbox para código hostil.

↻ **46. Validación de propiedades con contratos de prueba** — Reformular como tests de propiedades de contratos propios; no contratos autónomos de drenaje ni promesas de recompensa.

◐ **47. Reportes técnicos y ejecutivos** — Parcial: borradores Markdown y reporte de QA vinculados a evidencias; faltan informe corporativo completo y PDF.

◐ **48. Verificación de parches y regresiones** — Parcial: regresiones del propio paquete y control de fuentes; no monitorización de parches externos ni reproducción de exploits.

○ **49. Inteligencia de amenazas públicas** — Pendiente: fuentes públicas y revisión de reglas antes de activarlas; sin escaneo ofensivo automático.

○ **50. Mapeo de controles de cumplimiento** — Pendiente: sugerencias trazables de controles; no certificación automática ni dictamen de incumplimiento legal.

