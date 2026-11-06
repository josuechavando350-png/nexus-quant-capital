# 100 componentes para defensa operativa de extremo a extremo

Este catálogo C001–C100 responde a la nueva orientación: sensores → detección → incidente → respuesta → recuperación. Conserva el catálogo histórico M01–M100 sin renombrarlo ni alterar su porcentaje. No son 100 implementaciones terminadas. `planned` significa requisito pendiente; `bounded_partial` significa código ejecutable con alcance delimitado. Ninguna fila acredita cobertura completa, rendimiento superior ni integración productiva.

Los candidatos tecnológicos son opciones que deben evaluarse por precisión, consumo, mantenimiento, licencia, privilegios necesarios y compatibilidad. Una biblioteca nombrada no se cuenta como integración instalada. El desarrollo propio de C081–C090 no reclama originalidad mundial ni algoritmos demostrados antes de evaluarlos.

Contrato objetivo común: cada evento debe llevar identidad de cliente y activo, origen, versión de esquema, identidad estable, tiempo observado/recibido e incertidumbre, referencia a evidencia y alcance de autorización. Una detección debe referenciar evento y regla; un caso, detecciones; una acción, permiso y estado previo/posterior; una recuperación, copia fijada y prueba del consumidor. Este contrato distribuido aún está pendiente. El circuito local ejecutable usa los recibos existentes y no afirma conformidad OCSF.

Invariantes de integración: ningún sensor fuera de alcance; ningún evento perdido silenciosamente; ninguna respuesta sin autorización acotada; ningún éxito de recuperación sin prueba; ninguna cobertura declarada sin evidencia de ejecución. Las dependencias listadas son el diseño verificable de integración; las filas pendientes no son conexiones runtime existentes.

Primer circuito implementado: C014 → C032 → C041 → C052 → C064 → C067, con C082/C095/C096. Protege una copia JSON propia; observa bytes en cada solicitud/muestra, registra una alteración, impide consumo por la puerta de admisión, restaura desde hashes fijados y realiza una lectura posterior. No observa todos los procesos, no identifica al autor de un cambio y no aísla equipos. La evidencia se archiva por una operación explícita. El monitor es acotado y no se ha desplegado un servicio continuo.

## Activos y alcance

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C001 · Registro de activos autorizados | Inventarios del operador → Activos con propietario y alcance | API propia y SQL | Registro inicial autorizado | Rechazar activos sin autorización o propietario | Pendiente |
| C002 · Mapa de criticidad de servicios | Activos y dependencias → Prioridad de protección por servicio | Grafo propio | C001 | Un cambio de dependencia recalcula criticidad con explicación | Pendiente |
| C003 · Registro de identidades de cargas | Identidades y activos → Vínculos verificables entre carga e identidad | Certificados y registro propio | C001 | Rechazar una identidad asignada a otro activo | Pendiente |
| C004 · Registro de configuraciones aprobadas | Configuraciones revisadas → Versiones con hashes y aprobación | ConfigStore existente; adaptadores pendientes | C001 | Detectar cambios respecto a la versión fijada | Pendiente |
| C005 · Inventario de exposición autorizada | Configuración de servicios propios → Servicios expuestos y responsables | Adaptadores de configuración | C001, C004 | Detectar una exposición nueva en una exportación real | Pendiente |
| C006 · Inventario de certificados y vencimientos | Certificados de servicios propios → Alertas de vigencia y asociación | Bibliotecas TLS y X.509 | C001, C005 | Detectar vencimiento y certificado de otro servicio | Pendiente |
| C007 · Mapa de permisos efectivos | Roles y asignaciones → Permisos efectivos con procedencia | Analizador de políticas propio | C001, C003 | Distinguir permiso directo de permiso heredado | Pendiente |
| C008 · Grafo de dependencias operativas | Relaciones entre servicios → Impacto potencial de una contención | Grafo propio | C001, C002 | Una dependencia crítica impide una acción amplia sin revisión | Pendiente |
| C009 · Administrador de líneas base firmadas | Estado revisado de activos → Referencias verificables de integridad | Hashes fijados y firmas estándar | C001, C004 | Una línea base alterada no puede aprobar un archivo | Pendiente |
| C010 · Autorizador de alcance de sensores | Activos y permisos del operador → Alcance permitido por sensor | Motor de políticas | C001, C003, C007 | Un sensor no obtiene acceso a activos fuera de alcance | Pendiente |

## Sensores reales

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C011 · Sensor de procesos Linux | Eventos del kernel autorizado → Eventos de procesos con identidad de origen | Falco modern eBPF; adaptador pendiente | C001, C010 | Ver creación real de un proceso y reportar pérdida de eventos | Pendiente |
| C012 · Sensor de eventos Windows | Eventos de sistema autorizados → Eventos de procesos y sesiones normalizables | ETW y eventos de Windows | C001, C010 | Conservar identificadores al reabrir una fuente real | Pendiente |
| C013 · Lector de registros de autenticación | Logs propios de acceso → Eventos de acceso con cursor persistente | Lector acotado propio | C001, C010 | Rotar un log sin duplicar ni omitir entradas confirmadas | Parcial: Lector JSONL y adaptadores de formato OpenSSH/journald, cursor y rotación explícita; sin captura productiva |
| C014 · Sensor de integridad de archivos administrados | Bytes actuales y línea base → Observaciones de hashes y errores de lectura | ManagedIntegrity y canary.observe_snapshot | C004, C009, C010 | Detectar cambio o desaparición de una copia administrada | Parcial: lectura local periódica; sin sensor de kernel |
| C015 · Sensor de consultas DNS | Telemetría DNS autorizada → Consultas y respuestas con contexto | Zeek y adaptador DNS | C001, C010 | Asociar respuesta real con consulta sin inventar identidad | Pendiente |
| C016 · Sensor de metadatos TLS | Telemetría de conexiones propias → Metadatos TLS sin prometer descifrado | Zeek y metadatos TLS | C001, C006, C010 | Reportar explícitamente campos no observables | Pendiente |
| C017 · Sensor de metadatos de red | Captura autorizada de comunicaciones → Flujos y eventos de protocolos | Zeek | C001, C010 | Reproducir una captura de laboratorio y cuantificar pérdidas | Pendiente |
| C018 · Adaptador de alertas de red | Alertas del sensor de red → Alertas con regla y evidencia de origen | Suricata | C001, C010 | Conservar regla y referencia a tráfico al normalizar | Pendiente |
| C019 · Conector de auditoría de nube | Logs de cuentas propias → Eventos de administración y acceso | APIs oficiales de lectura | C001, C003, C010 | Reanudar desde cursor sin duplicar eventos | Pendiente |
| C020 · Conector de auditoría Kubernetes | Registros del clúster autorizado → Eventos de API y cambios de cargas | API de auditoría Kubernetes | C001, C003, C010 | Distinguir identidad solicitante y recurso afectado | Pendiente |

## Ingestión y calidad

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C021 · Normalizador de eventos | Eventos de sensores 11–20 → Eventos versionados con procedencia | OCSF como esquema candidato | C011, C012, C013, C014, C015, C016, C017, C018, C019, C020 | Rechazar campos incompatibles y conservar el original referenciado | Parcial: Contrato local compartido de autenticación e integridad; sin conformidad OCSF |
| C022 · Bus duradero de eventos | Eventos normalizados → Entregas confirmadas y reanudables | Cola duradera; elección mediante benchmark | C021 | Reiniciar consumidor sin perder eventos confirmados | Pendiente |
| C023 · Deduplicador de eventos | Eventos y claves de origen → Eventos únicos y recuento de duplicados | Índices únicos y claves estables | C021, C022 | Repetir el mismo lote sin duplicar incidentes | Parcial: Cursor atómico e identidad journald deduplicada por fuente; sin deduplicación distribuida |
| C024 · Normalizador de tiempo e incertidumbre | Tiempos de origen y recepción → Intervalos temporales con incertidumbre | Timestamps y estimación explícita | C021 | Un reloj atrasado no produce falsa causalidad | Pendiente |
| C025 · Redactor de datos sensibles | Eventos y política de privacidad → Eventos minimizados y referencia protegida | Reglas de redacción y parser estricto | C021, C010 | Una credencial sembrada para prueba no sale en el evento | Pendiente |
| C026 · Validador de calidad de señales | Eventos y salud de fuentes → Indicadores de campos ausentes y calidad | Contratos de datos propios | C021, C023, C024 | Una fuente vacía reduce cobertura declarada | Parcial: Errores de esquema/host, mensajes parciales, conflictos y eventos atrasados visibles; origen no autenticado |
| C027 · Almacén consultable de eventos | Eventos normalizados → Consultas acotadas por cliente y tiempo | SQL o almacenamiento columnar tras pruebas | C021, C022, C025 | Limitar consulta extensa sin devolver resultados de otro cliente | Parcial: Consulta SQLite paginada por cliente y activo; sin autenticación multiusuario |
| C028 · Gestor de retención y conservación | Políticas y referencias de casos → Plan revisable de retención | Motor de retención; borrado pendiente | C027, C025 | Una evidencia bajo conservación no entra en plan de eliminación | Pendiente |
| C029 · Monitor de salud de colectores | Latidos y contadores reales → Alertas de fuentes silenciosas o pérdidas | OpenTelemetry y métricas propias | C011, C021, C026 | Detener un sensor de laboratorio y detectar su ausencia | Pendiente |
| C030 · Registro de versiones de contratos | Esquemas y adaptadores → Matriz de compatibilidad | Esquemas versionados y pruebas de contrato | C021, C026 | Un productor incompatible queda rechazado con causa precisa | Pendiente |

## Detección evaluable

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C031 · Evaluador de reglas de eventos | Eventos normalizados y reglas revisadas → Detecciones con versión de regla | Sigma como formato candidato | C021, C023, C024, C030 | Corpus etiquetado produce resultados reproducibles | Pendiente |
| C032 · Detector de integridad respecto a línea base | Observaciones del sensor de archivos → Decisión y evidencia de discrepancia | Engine y receipts existentes | C014, C009 | Cambiar bytes reales abre una detección; bytes intactos no | Parcial: comparación de archivo y canario con hashes fijados |
| C033 · Detector de uso anómalo de identidades | Accesos y permisos efectivos → Detecciones contextualizadas por cuenta | Reglas y modelos calibrados | C003, C007, C013, C021 | Separar cambios aprobados de uso fuera de política | Parcial: Regla de fallos repetidos por principal/IP; sin respuesta automática |
| C034 · Detector de escalamiento de permisos | Cambios de roles y auditoría → Cambios riesgosos con diferencias de permisos | Diferencias de políticas | C007, C019, C020, C021 | Detectar ampliación real de permisos en datos autorizados | Pendiente |
| C035 · Detector de conexiones fuera de política | Flujos y mapa de servicios → Conexiones inesperadas por activo | Reglas de conectividad | C005, C008, C017, C021 | Un flujo permitido no dispara la regla de aislamiento | Pendiente |
| C036 · Detector de transferencias fuera de política | Flujos y clasificación de datos → Señales de salida con alcance y confianza | Reglas y estadísticas calibradas | C016, C017, C025, C021 | Reconocer límites de visibilidad con tráfico cifrado | Pendiente |
| C037 · Detector de cambios masivos de archivos | Eventos de archivos propios → Alertas de actividad destructiva probable | Eventos de sistema y correlación | C011, C014, C021 | Distinguir una tarea de respaldo autorizada de cambios inesperados | Pendiente |
| C038 · Detector de cambios de arranque y servicios | Configuración y eventos de sistema → Cambios persistentes fuera de línea base | Reglas sobre estado autorizado | C004, C011, C012, C021 | Una instalación aprobada no se clasifica como incidente | Pendiente |
| C039 · Detector de consumo fuera de presupuesto | Métricas de CPU, memoria y colas → Desviaciones y acciones propuestas | OpenTelemetry y límites explícitos | C002, C026, C029 | Distinguir saturación operativa de evidencia de intrusión | Pendiente |
| C040 · Calibrador de alertas y confianza | Resultados etiquetados y detecciones → Umbrales con errores medidos | Estadística reproducible | C031, C032, C033, C034, C035, C036, C037, C038, C039 | Reportar precisión y omisiones por escenario y versión | Parcial: Evaluación por corpus/política fijados, matriz con exclusiones y evidencia por caso reverificada offline; sin etiquetas independientes ni calibración productiva |

## Incidentes y forense

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C041 · Gestor de casos con evidencia | Detecciones y decisiones autenticadas → Casos abiertos, estados y cierre trazable | ManagedIntegrity: caso local derivado del ledger | C031, C032, C040 | Reabrir proceso conserva un incidente y su identidad | Parcial: Vista común y revisión local ligada a evidencia, con estados e historial; sin flujo SOC completo |
| C042 · Clasificador de urgencia y alcance | Casos, activos y criticidad → Cola priorizada con explicación | Políticas y puntuación explícita | C002, C008, C041 | Cambiar criticidad altera prioridad sin ocultar evidencia | Parcial: Cola de expedientes de autenticación registrados por activo, criticidad fijada y explicación reproducible; sin calibración empírica |
| C043 · Recolector forense de archivos | Rutas autorizadas y caso → Copias verificadas con metadatos | Lectura por descriptor y hashes | C010, C041 | Cambio durante lectura invalida adquisición completa | Parcial: Captura de líneas que activaron casos de autenticación y paquete verificado offline; sin imagen completa ni origen autenticado |
| C044 · Recolector y analizador de memoria | Adquisiciones autorizadas de laboratorio → Hallazgos enlazados a offsets y herramienta | Herramientas forenses especializadas; selección pendiente | C010, C041 | Analizar una captura conocida y registrar limitaciones | Pendiente |
| C045 · Analizador de artefactos del sistema | Artefactos adquiridos → Eventos de sistema con procedencia | Parsers aislados y corpus conocidos | C043, C044 | No confundir ausencia de artefacto con ausencia de actividad | Pendiente |
| C046 · Reconstrucción forense de comunicaciones | Capturas y metadatos autorizados → Cronología de comunicaciones | Zeek y parsers de captura | C017, C043 | Reproducir una sesión de laboratorio con evidencias referenciadas | Pendiente |
| C047 · Reconstrucción de acciones de nube | Auditoría y snapshots autorizados → Cronología de cambios y acceso | APIs oficiales y normalizador | C019, C024, C041 | Detectar huecos de auditoría y reportarlos | Pendiente |
| C048 · Registro de custodia y acceso a evidencia | Adquisiciones y operaciones autorizadas → Historial verificable de manejo | Ledger, firmas y anclajes separados | C043, C044, C045, C046, C047 | Una alteración o acceso no autorizado se detecta o rechaza | Parcial: Historial de revisiones y registro firmado de declaraciones por clave; sin todo acceso ni custodia independiente |
| C049 · Analizador aislado de muestras | Muestras autorizadas y caso → Indicadores y comportamiento observado | Análisis estático y sandbox dedicado | C010, C041, C043 | Sin acceso a producción; salida y recursos restringidos | Pendiente |
| C050 · Generador de informe de incidente | Caso y evidencias verificadas → Informe con hechos, hipótesis y límites | Plantillas y validación de referencias | C041, C042, C048, C049 | Cada afirmación factual enlaza a evidencia disponible | Parcial: Informe de autenticación con evidencia e historial, más declaración verificable con clave pública; sin otros tipos de caso ni custodia independiente |

## Respuesta acotada

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C051 · Autorizador de acciones defensivas | Caso, alcance y política → Permiso limitado y explicable | OPA como candidato y controles propios | C007, C010, C041, C042 | Rechazar acción que exceda activos o duración permitidos | Pendiente |
| C052 · Puerta de consumo de artefactos | Archivo y decisión de admisión → Bytes aprobados o rechazo persistente | ArtifactReader y Engine | C032, C041, C051 | Archivo alterado no llega al consumidor administrado | Parcial: solo consumidor de JSON administrado; no aislamiento de host |
| C053 · Revocador de sesiones autorizadas | Caso y sesiones propias → Revocación comprobada por proveedor | APIs de identidad; adaptadores pendientes | C003, C033, C051 | Revocar solo sesiones del alcance aprobado | Pendiente |
| C054 · Aplicador de aislamiento de red | Permiso de respuesta y política de red → Regla acotada con comprobación posterior | Firewall del entorno; conector pendiente | C035, C051, C008 | Conservar acceso de recuperación y expirar excepción | Pendiente |
| C055 · Aislador de cargas administradas | Caso y cargas autorizadas → Cambio acotado de acceso de la carga | API de orquestador | C020, C051 | Una carga ajena al caso permanece intacta | Pendiente |
| C056 · Rotador de secretos autorizados | Caso y referencias a secretos → Rotación y prueba de uso de nueva versión | Gestor de secretos estándar | C003, C007, C051 | Revocar versión anterior solo tras verificar transición | Pendiente |
| C057 · Aplicador de corrección controlada | Cambio revisado y permiso → Resultado y plan de reversión | Orquestación con etapas y comprobaciones | C004, C051 | Un fallo de validación detiene el despliegue | Pendiente |
| C058 · Limitador de radio de contención | Acciones propuestas y dependencias → Acciones dentro de presupuesto de impacto | Motor propio de presupuestos | C008, C042, C051 | Una cascada excedida se detiene antes de afectar otro servicio | Pendiente |
| C059 · Ejecutor de reversión acotada | Estado anterior y acción registrada → Restauración del cambio específico | Comparación de versiones y estados | C057, C058 | No revertir cambios posteriores ajenos al incidente | Pendiente |
| C060 · Orquestador de procedimientos defensivos | Caso y acciones permitidas → Ejecución por etapas con estados persistentes | Máquina de estados propia | C051, C052, C053, C054, C055, C056, C057, C058, C059 | Reanudar tras fallo sin repetir acciones no idempotentes | Pendiente |

## Recuperación comprobada

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C061 · Inventario de respaldos recuperables | Respaldos y servicios → Cobertura de recuperación por servicio | Catálogo de respaldos | C001, C002, C008 | Distinguir respaldo existente de respaldo probado | Pendiente |
| C062 · Verificador de copias de recuperación | Copias y hashes externos → Copias aceptadas o rechazadas | Hashes y firmas estándar | C009, C061 | Una copia alterada jamás se utiliza para recuperar | Pendiente |
| C063 · Restaurador de ensayo aislado | Copia verificada y entorno vacío → Instancia restaurada de ensayo | Infraestructura de prueba aislada | C010, C062 | No escribir en producción durante ensayo | Pendiente |
| C064 · Restaurador de archivos administrados | Caso abierto y copias fijadas → Archivos propios restaurados y verificados | ManagedIntegrity.recover | C041, C052, C062 | Fallo parcial mantiene cerrada la admisión | Parcial: restaura dos archivos propios desde copias fijadas |
| C065 · Reactivador de servicios controlados | Configuración validada y permiso → Servicio recuperado con comprobación de salud | Conectores específicos de servicio | C057, C063, C064 | No declarar recuperación solo por iniciar un proceso | Pendiente |
| C066 · Reconciliador de datos restaurados | Datos restaurados y referencias → Diferencias verificadas y pendientes | Consultas y reconciliación propia | C061, C062, C063 | Reportar registros faltantes sin inventar datos | Pendiente |
| C067 · Comprobador del consumidor recuperado | Servicio o artefacto restaurado → Resultado de una operación real de lectura | ArtifactReader y pruebas funcionales | C052, C064, C065, C066 | Consumir exactamente los bytes inspeccionados tras restaurar | Parcial: lectura JSON real posterior a restauración |
| C068 · Ejecutor de ejercicios de continuidad | Escenario y servicios autorizados → Tiempos y fallos reales de restauración | Orquestación de laboratorio | C008, C063, C065, C066, C067 | Medir recuperación efectiva en un ensayo completo | Pendiente |
| C069 · Rotador de segmentos de archivo | Archivo lleno y checkpoint fijado → Nuevo segmento enlazado al anterior | Desarrollo propio; pendiente | C048, C061 | Verificar continuidad sin borrar evidencia previa | Pendiente |
| C070 · Cerrador de incidentes con lecciones verificadas | Caso y comprobaciones de recuperación → Cierre motivado y acciones pendientes | Máquina de estados y validadores | C041, C050, C060, C067, C068 | Impedir cierre definitivo con pruebas obligatorias ausentes | Pendiente |

## Prevención y desarrollo seguro

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C071 · Analizador estático de código propio | Código autorizado y reglas → Hallazgos con ubicación y evidencia | Analizadores estáticos existentes | C001, C010 | Reproducir hallazgos en corpus de evaluación propio | Pendiente |
| C072 · Inventario y evaluador de componentes | SBOM y avisos de vulnerabilidad → Dependencias afectadas y prioridad contextual | SBOM y avisos oficiales | C001, C002, C071 | Distinguir coincidencia de versión de impacto demostrado | Pendiente |
| C073 · Verificador de procedencia de builds | Artefactos y atestaciones → Procedencia validada | Firmas y formatos de atestación | C009, C071, C072 | Rechazar una atestación de otro artefacto | Pendiente |
| C074 · Verificador de actualizaciones | Paquetes y políticas de firma → Actualizaciones aceptadas con versión fijada | Firmas estándar y metadatos versionados | C073 | Rechazar downgrade no autorizado y paquete alterado | Pendiente |
| C075 · Evaluador de permisos de APIs propias | Contratos y pruebas autorizadas → Diferencias entre acceso esperado y observado | Pruebas de contrato y autorización | C007, C010, C071 | Un usuario de prueba no accede a datos de otro ámbito | Pendiente |
| C076 · Evaluador de infraestructura declarativa | Configuración de despliegue → Desviaciones de política antes de aplicar | OPA y analizadores de configuración | C004, C005, C007, C071 | Detectar exposición introducida en un cambio de laboratorio | Pendiente |
| C077 · Verificador de imágenes de cargas | Imágenes y procedencia → Política de admisión de imágenes | SBOM, firmas y análisis de imagen | C072, C073, C076 | Rechazar imagen fuera de procedencia permitida | Pendiente |
| C078 · Controlador de herramientas de agentes | Solicitud de herramienta y contexto → Permiso acotado o rechazo | Políticas, aislamiento y validadores | C010, C025, C051 | Texto no confiable no amplía permisos del agente | Pendiente |
| C079 · Evaluador de minimización de datos | Flujos y clasificación → Reglas de acceso y conservación mínimas | Clasificación y políticas | C025, C027, C028 | Evitar datos personales innecesarios en una exportación | Pendiente |
| C080 · Registro de amenazas y supuestos | Diseño y límites de confianza → Amenazas, controles y supuestos trazables | Modelo estructurado propio | C001, C008, C010, C071, C075, C078 | Todo riesgo prioritario tiene control probado o deuda explícita | Pendiente |

## Desarrollo propio por validar

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C081 · Grafo de evidencias con confianza | Eventos, casos y referencias → Relaciones con procedencia y confianza | Desarrollo propio sobre grafo | C024, C027, C041, C048 | Una coincidencia temporal no se afirma causal automáticamente | Pendiente |
| C082 · Explicador reproducible de decisiones | Política, observaciones y resultado → Explicación reproducible y discrepancias | Receipts existentes; ampliación pendiente | C031, C032, C051, C081 | Recalcular una decisión y detectar hechos cambiados | Parcial: replay de decisiones locales registradas |
| C083 · Priorizador de exposición e impacto | Activos, permisos y detecciones → Prioridad con factores visibles | Desarrollo propio con calibración | C002, C007, C026, C040, C081 | Mostrar incertidumbre cuando falta telemetría | Pendiente |
| C084 · Evaluador de políticas candidatas | Eventos históricos y política candidata → Diferencia medida frente a política vigente | Replay defensivo propio | C027, C031, C040, C051, C082 | No ejecutar respuestas mientras compara políticas | Parcial: Comparación de dos políticas de umbral/ventana de autenticación sobre el mismo corpus fijado, con errores y conjuntos de evidencia; sin aplicar respuestas ni recomendar parámetros |
| C085 · Asignador de presupuesto de sensores | Salud, riesgo y presupuesto → Asignación y pérdida de cobertura declarada | Desarrollo propio sobre telemetría | C026, C029, C039, C083 | Reducir costo sin ocultar las señales descartadas | Pendiente |
| C086 · Comparador de respuestas alternativas | Caso, dependencias y acciones → Opciones con impacto esperado y evidencia | Desarrollo propio; modelo por validar | C008, C051, C058, C083 | Marcar estimación como tal y comprobarla en ensayo | Pendiente |
| C087 · Gestor de señuelos aislados | Activos señuelo propios y eventos → Alertas por interacción con señuelos | Honeynet aislada y canarios | C010, C021, C041 | Sin credenciales reales ni conexión necesaria a producción | Pendiente |
| C088 · Curador de inteligencia defensiva | Indicadores y fuentes autorizadas → Indicadores con vigencia y procedencia | Modelo de confianza propio | C024, C025, C031 | Una fuente vencida no genera bloqueo automático | Pendiente |
| C089 · Planificador de captura por incidente | Caso, alcance y presupuesto → Plan de adquisición mínimo suficiente | Desarrollo propio | C010, C025, C042, C043, C048 | No capturar fuera de alcance ni exceder presupuesto | Pendiente |
| C090 · Registro de incertidumbre y puntos ciegos | Calidad, pérdidas y cobertura → Limitaciones visibles en alertas e informes | Desarrollo propio | C026, C029, C040, C050, C080 | Un sensor caído impide declarar cobertura completa | Pendiente |

## Plataforma y evaluación

| ID / componente | Entrada → salida | Tecnología candidata | Dependencias | Prueba de aceptación | Estado actual |
|---|---|---|---|---|---|
| C091 · Aislamiento de clientes | Identidades, datos y solicitudes → Separación comprobada de datos y recursos | Autorización y partición por cliente | C003, C007, C010, C027 | Consulta y acción de cliente A no afectan al B | Pendiente |
| C092 · Control de acceso administrativo | Operadores y políticas → Operaciones mínimas con autorización trazable | RBAC y permisos de corta duración | C003, C007, C051, C091 | Una cuenta de lectura no ejecuta respuesta | Parcial: Credenciales locales con revocación/rotación/renovación y caducidad configurable; sin IAM, tiempo independiente ni aislamiento del administrador |
| C093 · Custodio de claves y rotación | Claves y políticas de uso → Operaciones criptográficas auditadas | KMS/HSM según entorno; sin criptografía casera | C003, C048, C092 | Rotar claves sin perder verificabilidad histórica | Parcial: Registro firmado local de claves emisoras, rotación/revocación y verificación histórica mediante receptor; sin KMS/HSM ni rotación de autoridad/auditoría |
| C094 · Controlador de presión y cuotas de ingestión | Tasas, colas y prioridades → Carga aceptada y rechazos explícitos | Colas acotadas y backpressure | C022, C026, C029, C091 | Saturación no provoca pérdida silenciosa de eventos confirmados | Parcial: Cuotas locales rechazan el lote sin adelantar el cursor; sin presión distribuida ni cuota física |
| C095 · Ledger y archivo autenticados | Decisiones y eventos del sistema → Historial, checkpoints y exportaciones verificables | Ledger, Witness, ArchiveStore existentes | C041, C048, C082, C093 | Alteración o prefijo incompleto frente a anclaje se rechaza | Parcial: Archivo y testigo locales; receptor de registro firmado con avance de prefijo y recibos externos; sin réplica independiente |
| C096 · Presupuesto persistente del archivo | Archivos y política fijada → Escrituras dentro de presupuesto | archive_budget existente | C027, C095 | Procesos competidores no exceden último espacio disponible | Parcial: presupuesto para escritores cooperantes locales |
| C097 · Monitor de objetivos operativos | Métricas y objetivos por servicio → Incumplimientos y presupuestos de error | OpenTelemetry y métricas propias | C029, C039, C094, C096 | Medir colas, pérdidas y latencias de casos lentos | Pendiente |
| C098 · Desplegador progresivo de la plataforma | Versiones verificadas y métricas → Despliegue acotado o reversión | Etapas canary y control de versiones | C074, C091, C092, C097 | Una regresión detiene el avance al siguiente grupo | Pendiente |
| C099 · Laboratorio de pruebas defensivas | Escenarios autorizados y versiones → Resultados repetibles con costos y errores | Laboratorio aislado y harness propio | C040, C063, C068, C084, C086, C098 | Mismo corpus permite comparar versiones sin alterar producción | Pendiente |
| C100 · Matriz de capacidades demostradas | Requisitos, integraciones y pruebas → Cobertura medida y pendientes visibles | Catálogo verificable y evidencia de ejecución | C080, C090, C095, C097, C099 | Una capacidad sin sensor o prueba no aparece como completada | Pendiente |

## Fuentes técnicas consultadas

- [Falco: eventos de kernel](https://falco.org/docs/concepts/event-sources/kernel/)
- [OCSF: esquemas de eventos](https://github.com/ocsf/ocsf-schema)
- [Zeek: monitor de red](https://zeek.org/)
- [Suricata: análisis y detección de red](https://suricata.io/)
- [Sigma: formato de detección](https://sigmahq.io/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Open Policy Agent](https://www.openpolicyagent.org/docs)
- [NIST CSF](https://www.nist.gov/cyberframework/faqs)
- [NIST forense e incidentes](https://csrc.nist.gov/pubs/sp/800/86/final)
- [MITRE D3FEND](https://d3fend.mitre.org/)

## Prioridad y definición de terminado

Primero: cerrar el circuito local y sus fallos. Después: un sensor de autenticación con cursor persistente, normalización y detecciones evaluadas que produzcan el mismo contrato de caso. Luego: respuesta y recuperación específicas del servicio elegido. Expandir plataforma distribuida solo tras medir esa cadena. Una fila se completa únicamente al cumplir contrato, integración real, casos positivos/negativos, fallo/reinicio, permisos, mediciones de costo y documentación de límites. Una prueba de catálogo no acredita esos resultados.

La entrega 0.11 añade una ruta JSONL de autenticación con cursor, regla evaluada, casos y vista compartida con integridad. Ahora hay 17 componentes con alcance parcial y 83 pendientes; 0 completos. Ver V0_11.md y AUTH_PIPELINE_CHECK.json para límites y errores medidos.

La entrega 0.12 amplía C013/C023/C026 con formatos OpenSSH/journald y evaluación explícita. Se mantienen 17 componentes parciales, 83 pendientes y 0 completos; no se cuentan adaptadores como componentes completos nuevos.

La entrega 0.13 incorpora C043 con adquisición acotada de registros por caso y verificación offline. Estado actual: 18 componentes parciales, 82 pendientes y 0 completos. La preservación local no se cuenta como custodia independiente.

La entrega 0.14 conecta revisión por credenciales e historial HMAC a evidencia preservada. Estado actual: 20 componentes parciales, 80 pendientes y 0 completos. La revisión local no equivale a identidad humana, respuesta ejecutada o recuperación comprobada.

La entrega 0.15 amplía C092 con revocación, rotación y renovación conectadas al historial de revisión. Conserva 20 componentes parciales, 80 pendientes y 0 completos; no se contabiliza una mejora parcial como un componente adicional.

La entrega 0.16 amplía C092 con caducidad configurada y control persistente del reloj local. El catálogo permanece en 20 parciales, 80 pendientes y 0 completos; el tiempo no tiene anclaje independiente.

La entrega 0.17 incorpora C050 con expedientes de autenticación y verificación offline. Estado actual: 21 parciales, 79 pendientes y 0 completos. El porcentaje de cierres de los 200 entregables se calcula mediante el registro de aceptación; consultar PROGRESO.md.

La entrega 0.18 amplía C048/C050 con declaraciones verificables mediante clave pública, tras replay completo del emisor. Se conserva el conteo de 21 parciales; custodia independiente y rotación siguen pendientes.

La entrega 0.19 añade el alcance local de C093: rotación, revocación y receptor de registros de firma. Estado actual: 22 parciales, 78 pendientes y 0 completos.

La entrega 0.21 añade C042 parcial: priorización enlazada a expedientes registrados, preservación de casos cerrados y recálculo por política. Estado actual: 23 parciales, 77 pendientes y 0 completos.
