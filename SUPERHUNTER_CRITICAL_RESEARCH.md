# SUPERHUNTER — ESTRATEGIA DE DESCUBRIMIENTO MULTIDOMINIO Y CRÍTICOS
**Decisión de producto:** 2026-11-06. **Estado:** especificación prioritaria aprobada; NO equivale a una capacidad implementada ni a una garantía de descubrimiento.

**Fuentes de continuidad:** [Plan maestro](SUPERHUNTER_MASTER_PLAN.md) · [Estado técnico](SUPERHUNTER_STATUS.md) · [Código en investigación (PR #49)](https://github.com/josuechavando350-png/nexus-quant-capital/pull/49).

## Misión precisa
SUPERHUNTER será una plataforma científica autónoma de investigación de seguridad **multidominio**, especializada en descubrir, reconstruir, verificar y reportar **vulnerabilidades críticas y de alto impacto** en objetivos **propios o expresamente autorizados**. Se investigan tanto fallos individuales como **cadenas de debilidades** donde componentes de severidad media/baja puedan combinarse en un daño alto o crítico demostrado. Una sola plataforma conecta HUNTER (investigación y divulgación responsable) y GUARDIAN (detección, defensa, recuperación y pruebas de regresión), manteniendo sus permisos diferenciados.

## Alcance, prioridad y diferencias esenciales
- **Ámbitos objetivo, progresivos, no cobertura actual:** EVM, DeFi y contratos inteligentes; aplicaciones web; APIs; autenticación e identidad; nube e infraestructura; redes; contenedores; cadena de suministro; software de sistemas y distribuidos; datos y lógica de negocio. Forense digital, análisis causal y verificación formal son disciplinas transversales.
- **Primera especialización implementable:** EVM/DeFi y fallos multicomponente. Extender a otros ámbitos únicamente con parsers, observadores, modelos y verificadores reales, integrados y medidos.
- **Prioridad de trabajo (no severidad automática):** (1) casos con impacto potencial crítico y evidencia; (2) casos de impacto alto; (3) cadenas potencialmente críticas que incluyan señales medias/bajas; (4) casos de menor severidad relevantes para entender dependencias o prevenir escaladas. No descartar un caso por su etiqueta inicial si pudiera formar parte de una cadena.
- **Ninguna etiqueta de severidad se hereda por agregar hallazgos.** La gravedad de una cadena requiere hipótesis de precondiciones, secuencia de laboratorio autorizada, impacto verificable, condiciones de acceso, alcance y evaluación independiente según criterios del programa. Un "critical" en un reporte del usuario es **afirmación**, no hecho.
- **Confianza y evidencia separadas:** `OBSERVED`, `HYPOTHESIZED`, `REPRODUCED_IN_LAB`, `INDEPENDENTLY_VERIFIED`, `REFUTED`, `INCONCLUSIVE`. La prioridad de investigación no implica confirmación, ejecución real ni autenticidad de la fuente.
- **Autorización antes que prioridad:** si el objetivo/superficie/tipo de prueba no está dentro de una política autenticada y vigente, no ejecutar acciones activas, aunque parezca una vulnerabilidad crítica.

## Pipeline obligatorio, interconectado
1. **Intake y scope:** identidad exacta de programa, activo, commit, contrato/cadena/red, versión, política y autorización. Si faltan, `NEEDS_SCOPE_REVIEW`.
2. **Fuentes y percepción:** análisis estático/dinámico autorizado, eventos, registros forenses, bytecode, dependencias, trazas, configuraciones; guardar evidencia original con hashes y procedencia, sin asumir autenticidad solo por el hash.
3. **Grafo de investigación:** nodos tipados de activos, observaciones, hipótesis, propiedades, dependencias, incidentes de laboratorio, condiciones e impactos; aristas con evidencia y temporalidad declarada. No confundir aristas con causalidad probada.
4. **Priorización acotada:** estimar valor esperado de información, severidad potencial, cobertura, costo de experimento, incertidumbre, factibilidad y límites éticos; conservar casos medios/bajos como entradas de cadenas si sus relaciones están justificadas.
5. **Experimentos:** copiar activos en un laboratorio aislado, generar casos positivos/negativos, intentar refutar hipótesis, minimizar contraejemplos y conservar hashes, versiones, precondiciones y trazas.
6. **Demostración:** comparación de modelo y ejecución, verificadores independientes, impacto reproducible y análisis de incertidumbre. **Abstención antes que falsos positivos.**
7. **Informe y defensa:** revisión humana, reporte de hallazgo válido según reglas del programa, corrección propuesta, validación de recuperación y regresión automatizada. Ningún envío externo automático sin regla explícita y autorización correspondiente.
8. **Memoria científica:** guardar resultados confirmados, refutados e inconclusos; medir precision, recall, cobertura, tiempo/costo por hallazgo, reproducibilidad y generalización en conjuntos ocultos.

## Primer motor implementable: Evidence-Constrained Chain Triage
Se incorporará **un evaluador offline**, no un motor de explotación:
- Admite observaciones tipadas de fuentes diferentes, hipótesis de cadenas (secuencia y dependencias), alcance declarado, severidad potencial y pruebas disponibles.
- Comprueba esquema, identidades y referencias, rechaza ciclos y cadenas incoherentes, no permite ascender de `POTENTIAL_CRITICAL` a `CRITICAL_CONFIRMED` sin una evidencia independiente y explícita; no publica datos de casos sensibles.
- Entrega ranking **de investigación** reproducible, con explicación de qué pruebas faltan, y **no** produce payloads de ataque, sesiones remotas ni autenticaciones ficticias.
- Pruebas: cadena sintética baja+media que merece investigación, high aislada, supuesta critical sin pruebas, duplicados, un edge inexistente, ciclo, evidencia alterada, alcance no autorizado, empate determinista, independencia inexistente, regresión completa previa.

## Cuándo considerar un motor completado
- Código fuente original real, integraciones CLI y QA, documentación de límites y verificadores independientes; ningún stub/módulo decorativo se cuenta como completado.
- Negativos adversariales, regresión de todas las pruebas anteriores, verificación de hashes de fuentes y recibos.
- Gate real: un caso controlado debe mostrar una hipótesis de cadena útil y otro debe demostrar que el sistema rechaza clasificar una cadena como crítica confirmada sin prueba de impacto.
- Ningún porcentaje global derivado de tests. El 40–42% es una referencia histórica no auditada.
- Todos los PRs antiguos #45–#49 continúan en ramas encadenadas; NO fusionar ni alterar NQC histórico por este plan.

## Metas de calidad, NO promesas comerciales
Priorizar descubrimientos críticos originales, baja tasa de falsos positivos, reproducibilidad independiente, costo controlado, trazabilidad forense, evaluación ciega y cobertura multidominio real. No prometer encontrar todos los tipos de vulnerabilidad, operar en terceros sin permiso, superar a XBOW sin pruebas comparables o ingresos garantizados.

## Continuidad en otra conversación
Consultar primero **SUPERHUNTER_STATUS.md**, este archivo y **SUPERHUNTER_MASTER_PLAN.md**. Inspeccionar el HEAD actual del último PR, preservar el árbol histórico y continuar desde el último gate efectivamente probado. Nunca reemplazar código acumulado por versiones parciales ni publicar evidencia sensible.
