# Primeros 10 originales y 10 propuestas propias

La numeración 1–100 conserva el documento entregado. Los nuevos componentes se numeran X101–X110 para no reemplazar ni inflar esa lista. Son propuestas propias de composición y producto; no afirmaciones de invención científica o patentabilidad.

## Los primeros 10 del documento

| ID | Programa | Función defensiva propuesta | Estado real de esta entrega |
|---|---|---|---|
| 1 | seL4 Core | Aislar servicios por capacidades en un dominio de ejecución con supuestos explícitos | Pendiente; no kernel instalado ni portado |
| 2 | eBPF Sentinel | Observar eventos del kernel Linux y aplicar políticas LSM revisadas | Pendiente; no sensor ni programa eBPF cargado |
| 3 | CHERI Guardian | Proteger acceso a memoria con capacidades en hardware/toolchain compatible | Pendiente; necesita plataforma CHERI |
| 4 | Secure Enclave Manager | Admitir cargas confidenciales según atestación verificada y mediciones autorizadas | Pendiente; no SGX/SEV-SNP validado |
| 5 | Quantum-Resistant Lattice | Integrar ML-KEM para establecimiento de claves y ML-DSA para firmas | Pendiente; no criptografía poscuántica implementada aquí |
| 6 | WASM Sandbox Engine | Ejecutar componentes con imports y recursos explícitamente limitados | Pendiente; no runtime WebAssembly en esta entrega |
| 7 | Nix Inmutable Base | Producir imágenes declarativas, versionadas y reversibles | Pendiente; no imagen NixOS arrancable |
| 8 | Formal Logic Verifier | Probar propiedades especificadas y registrar sus supuestos | Pendiente; los tests no se presentan como prueba formal |
| 9 | Anycast Decoy Network | Operar señuelos propios con correlación y límites de carga | Pendiente; no red anycast desplegada |
| 10 | Deterministic SOAR Orchestrator | Ejecutar transiciones defensivas verificables y reversibles | Subconjunto real: cuarentena de admisión, revocación de tokens y auditoría local |

No deben apilarse ciegamente sobre un único sistema: eBPF/LSM corresponde al dominio Linux; seL4 requiere otro dominio o integración explícita. CHERI, CET, PAC, SGX y SEV-SNP tienen requisitos propios. La arquitectura futura debe seleccionar perfiles de ejecución según disponibilidad, evidencia y costo medido.

## Diez propuestas adicionales

| ID | Nombre | Qué haría y beneficio comprobable | Estado |
|---|---|---|---|
| X101 | Evidence Ledger | Vincula decisiones a una cadena autenticada y checkpoint para verificar alteraciones y continuidad | Implementado localmente; anclaje externo pendiente |
| X102 | Input Guard | Rechaza entradas ambiguas, demasiado grandes o fuera del contrato antes de procesar activos | Implementado y conectado |
| X103 | Causal Decision Receipts | Cada decisión identifica política, observaciones y comprobaciones; un evaluador independiente reproduce el resultado | Implementado localmente en 0.2.0; no atestación externa |
| X104 | Defense Drift Meter | Mediría cambios de configuración, reglas y calidad de telemetría frente a una referencia aprobada | Diseño; faltan series temporales reales |
| X105 | Containment Budget | Limita cuarentenas persistentes y sigue rechazando solicitudes sospechosas cuando el límite se agota | Subconjunto ejecutable en 0.2.0; sin presupuesto de tráfico |
| X106 | Evidence Expiry Gate | Rechaza inspecciones locales caducadas o con retroceso de reloj y exige todos los archivos esperados | Subconjunto ejecutable en 0.2.0; sin reloj independiente ni sensores externos |
| X107 | Dependency Impact Graph | Calcularía qué servicios propios perderían funcionalidad al aislar una dependencia | Diseño; grafo de inventario y pruebas de impacto pendientes |
| X108 | Recovery Proof Runner | Ensayaría restauraciones sobre copias aisladas y produciría evidencia de integridad y tiempo de recuperación | Diseño; el ciclo local actual solo valida liberación de un artefacto |
| X109 | Sensor Disagreement Resolver | Separaría señales corroboradas de contradicciones entre sensores para reducir decisiones por datos falsos | Diseño; necesita fuentes independientes y métricas de error |
| X110 | Policy Regression Gate | Comprobaría una política candidata contra incidentes y tráfico benigno históricos antes de permitir su activación | Diseño; necesita corpus autorizado y métricas comparables |

El checkout íntegro ya fue recuperado y la incorporación local pasó aislamiento. Prioridad siguiente: integrar un consumidor concreto de NQC, añadir checkpoints externos y retención, evaluar políticas candidatas con corpus autorizado y después seleccionar sensores Linux y un runtime aislado. Ningún módulo pendiente aparece como implementación vacía en el código.
