# SUPERHUNTER — checklist basado en evidencia

Pruebas locales acotadas, no certificación de seguridad ni garantía de ausencia de fallos.

## Fundamentos

✅ F01. Puente de datos DIABLO/NQC
✅ F02. Ejecución conjunta de componentes locales
✅ F03. Integridad y almacenamiento privado
✅ F04. Bitácora vinculada a cada entrada y resultado
✅ F05. Catálogo de las 50 capacidades sin falsas palomitas

## Las 50 capacidades solicitadas

Ninguna está completada a su alcance original. El registro no implementa sus motores.

☐ 01. Consultas de grafos SlithIR — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 02. Taint analysis de contratos — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 03. Fuzzing guiado por invariantes — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 04. Fork fuzzing — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 05. Simulación de préstamos flash — **Rediseño defensivo pendiente**. Pruebas de liquidez en modelos propios; sin generar secuencias para drenar protocolos.
☐ 06. Integración de oráculos — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 07. Inferencia simbólica estocástica — **Pendiente**. Las reglas inferidas son hipótesis hasta contar con una especificación y verificación.
☐ 08. Secuencias multibloque — **Rediseño defensivo pendiente**. Pruebas temporales de propiedades; no planificación autónoma de ataques multibloque.
☐ 09. Mutaciones del estado local — **Pendiente**. Declarar toda mutación artificial; un estado fabricado no demuestra un fallo alcanzable.
☐ 10. Orquestación neuro-simbólica — **Pendiente**. El modelo propone; las pruebas deciden. No existe garantía general de cero alucinaciones.
☐ 11. Diferenciales de bytecode — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 12. Estrés de retiros y liquidez — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 13. Taint binario dinámico — **Pendiente**. Motor distinto al análisis EVM; limitarlo a binarios propios e instrumentación defensiva.
☐ 14. Grafos de permisos — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 15. Extractor automático de PoC — **Rediseño defensivo pendiente**. Minimizar y documentar contraejemplos de pruebas propias; no generar exploits de terceros.
☐ 16. Verificación de firmas y nonces — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 17. Fallos de sistemas distribuidos — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 18. Reentrancia entre contratos — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 19. Diferenciales del compilador — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 20. Pruebas de API por gramática — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 21. Pruebas de protocolos de red — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 22. Análisis de canales laterales — **Rediseño defensivo pendiente**. Evaluar tiempo constante con secretos de prueba; no extraer claves ni credenciales.
☐ 23. HTTP smuggling y cache poisoning — **Rediseño defensivo pendiente**. Verificar coherencia de parsers propios; sin secuestro de sesiones ni pruebas activas a terceros.
☐ 24. Consistencia dinámica RBAC — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 25. Deserialización y cadenas de gadgets — **Rediseño defensivo pendiente**. Inventario y endurecimiento de deserialización; no construir cadenas automáticas RCE.
☐ 26. Restricciones de circuitos ZK — **Pendiente**. Precisar circuito, entradas públicas, constraints y límites del verificador.
☐ 27. Concurrencia y memoria compartida — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 28. Consenso ante fallos bizantinos — **Rediseño defensivo pendiente**. Simulación local de tolerancia a fallos; sin interrumpir validadores o redes reales.
☐ 29. Detección de secretos en logs — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 30. Dependencias y funciones alcanzables — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 31. Integridad de carga de bibliotecas — **Rediseño defensivo pendiente**. Validar procedencia y permisos de bibliotecas; no desviar la ejecución legítima.
☐ 32. Evasión genética de sandboxes — **Rediseño defensivo pendiente**. Verificación de límites de aislamiento; sin optimizar payloads de escape o evasión.
☐ 33. Coherencia documentación/código — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 34. Verificación formal acotada — **Pendiente**. Una prueba es relativa al modelo, propiedades y límites; timeout o unknown no equivalen a seguro.
☐ 35. Planificación de exploits MCTS — **Rediseño defensivo pendiente**. Planificar cobertura de pruebas defensivas; no encadenar errores para optimizar exploits.
☐ 36. Grafo de conocimiento entre dominios — **Rediseño defensivo pendiente**. Relacionar activos, dependencias y controles; no diseñar ataques integrales.
☐ 37. Triaje e impacto financiero — **Pendiente**. Importes con unidades, fuentes y fecha; dinero en riesgo no equivale a beneficio ni a recompensa.
☐ 38. Aprendizaje con retroalimentación humana — **Rediseño defensivo pendiente**. Aprendizaje explícito, consentido, versionado y reversible; sin observación oculta ni autoedición libre.
☐ 39. Análisis visual del frontend — **Pendiente**. Una captura visual no demuestra por sí sola una vulnerabilidad del navegador.
☐ 40. Análisis de topología de grafos — **Pendiente**. Un patrón de grafo es una señal, no una demostración de vulnerabilidad.
☐ 41. Lectura de diagramas y especificaciones — **Pendiente**. Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados.
☐ 42. Secretos expuestos en grabaciones — **Rediseño defensivo pendiente**. Material propio autorizado, detección y redacción de secretos; no recopilar credenciales de terceros.
☐ 43. Navegación stealth y evasión de captchas — **Rediseño defensivo pendiente**. Automatización de navegador transparente en pruebas autorizadas; sin evasión WAF, bots o captchas.
☐ 44. Payloads adaptativos para evadir filtros — **Rediseño defensivo pendiente**. Verificar validación y sanitización en componentes propios; sin evasión adaptativa de filtros.
☐ 45. Entornos clonados de pruebas — **Pendiente**. Inventariar diferencias de la réplica; no afirmar identidad exacta sin comprobarla.
☐ 46. Despliegue de contratos de ataque — **Rediseño defensivo pendiente**. Aserciones de regresión locales revisadas; sin generar ni desplegar contratos de explotación.
☐ 47. Reportes ejecutivos y técnicos — **Pendiente**. Borradores basados en evidencias, revisados antes de divulgarse.
☐ 48. Verificación de parches y regresiones — **Pendiente**. Mismo contrato de pruebas antes/después; no modificar aserciones para ocultar regresiones.
☐ 49. Inteligencia de amenazas y avisos — **Pendiente**. Avisos públicos con fuentes y revisión; nunca instalar o ejecutar reglas remotas automáticamente.
☐ 50. Mapeo de controles de cumplimiento — **Pendiente**. Mapeo orientativo versionado; no certifica ISO/SOC ni determina por sí solo una infracción legal.
