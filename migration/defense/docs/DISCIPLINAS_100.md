# 100 disciplinas y especialidades defensivas vinculadas al software

Son disciplinas, especialidades y prácticas de ingeniería, no 100 ciencias independientes ni 100 programas adicionales. Cada D tiene un componente responsable C, un entregable y una comprobación de competencia. El código puede automatizar parte del trabajo; decisiones forenses, operación y validación pueden requerir especialistas. Los vínculos son requisitos de diseño; no certificaciones profesionales ni implementación ya terminada.

## Activos y alcance

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D001 · Gestión de superficie de ataque | C001 | Activos con propietario y alcance | Rechazar activos sin autorización o propietario |
| D002 · Clasificación de activos críticos | C002 | Prioridad de protección por servicio | Un cambio de dependencia recalcula criticidad con explicación |
| D003 · Gestión de identidades de máquinas | C003 | Vínculos verificables entre carga e identidad | Rechazar una identidad asignada a otro activo |
| D004 · Gestión de configuración segura | C004 | Versiones con hashes y aprobación | Detectar cambios respecto a la versión fijada |
| D005 · Gestión de exposición de servicios | C005 | Servicios expuestos y responsables | Detectar una exposición nueva en una exportación real |
| D006 · Gestión de certificados | C006 | Alertas de vigencia y asociación | Detectar vencimiento y certificado de otro servicio |
| D007 · Gobierno de privilegios | C007 | Permisos efectivos con procedencia | Distinguir permiso directo de permiso heredado |
| D008 · Gestión de dependencias de negocio | C008 | Impacto potencial de una contención | Una dependencia crítica impide una acción amplia sin revisión |
| D009 · Gestión de líneas base | C009 | Referencias verificables de integridad | Una línea base alterada no puede aprobar un archivo |
| D010 · Gobierno de alcance defensivo | C010 | Alcance permitido por sensor | Un sensor no obtiene acceso a activos fuera de alcance |

## Sensores reales

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D011 · Telemetría de procesos Linux | C011 | Eventos de procesos con identidad de origen | Ver creación real de un proceso y reportar pérdida de eventos |
| D012 · Telemetría de Windows | C012 | Eventos de procesos y sesiones normalizables | Conservar identificadores al reabrir una fuente real |
| D013 · Monitorización de autenticación | C013 | Eventos de acceso con cursor persistente | Rotar un log sin duplicar ni omitir entradas confirmadas |
| D014 · Monitorización de integridad de archivos | C014 | Observaciones de hashes y errores de lectura | Detectar cambio o desaparición de una copia administrada |
| D015 · Seguridad de DNS | C015 | Consultas y respuestas con contexto | Asociar respuesta real con consulta sin inventar identidad |
| D016 · Seguridad de transportes cifrados | C016 | Metadatos TLS sin prometer descifrado | Reportar explícitamente campos no observables |
| D017 · Análisis defensivo de tráfico | C017 | Flujos y eventos de protocolos | Reproducir una captura de laboratorio y cuantificar pérdidas |
| D018 · Detección de intrusiones en red | C018 | Alertas con regla y evidencia de origen | Conservar regla y referencia a tráfico al normalizar |
| D019 · Auditoría de nube | C019 | Eventos de administración y acceso | Reanudar desde cursor sin duplicar eventos |
| D020 · Auditoría de Kubernetes | C020 | Eventos de API y cambios de cargas | Distinguir identidad solicitante y recurso afectado |

## Ingestión y calidad

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D021 · Ingeniería de esquemas de seguridad | C021 | Eventos versionados con procedencia | Rechazar campos incompatibles y conservar el original referenciado |
| D022 · Ingeniería de transporte de telemetría | C022 | Entregas confirmadas y reanudables | Reiniciar consumidor sin perder eventos confirmados |
| D023 · Ingeniería de identidad de eventos | C023 | Eventos únicos y recuento de duplicados | Repetir el mismo lote sin duplicar incidentes |
| D024 · Sincronización temporal forense | C024 | Intervalos temporales con incertidumbre | Un reloj atrasado no produce falsa causalidad |
| D025 · Protección de datos en telemetría | C025 | Eventos minimizados y referencia protegida | Una credencial sembrada para prueba no sale en el evento |
| D026 · Ingeniería de calidad de datos | C026 | Indicadores de campos ausentes y calidad | Una fuente vacía reduce cobertura declarada |
| D027 · Ingeniería de almacenamiento de eventos | C027 | Consultas acotadas por cliente y tiempo | Limitar consulta extensa sin devolver resultados de otro cliente |
| D028 · Gestión de retención de evidencias | C028 | Plan revisable de retención | Una evidencia bajo conservación no entra en plan de eliminación |
| D029 · Observabilidad de sensores | C029 | Alertas de fuentes silenciosas o pérdidas | Detener un sensor de laboratorio y detectar su ausencia |
| D030 · Ingeniería de compatibilidad de eventos | C030 | Matriz de compatibilidad | Un productor incompatible queda rechazado con causa precisa |

## Detección evaluable

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D031 · Ingeniería de detecciones basadas en reglas | C031 | Detecciones con versión de regla | Corpus etiquetado produce resultados reproducibles |
| D032 · Detección de alteraciones de configuración | C032 | Decisión y evidencia de discrepancia | Cambiar bytes reales abre una detección; bytes intactos no |
| D033 · Detección de abuso de identidades | C033 | Detecciones contextualizadas por cuenta | Separar cambios aprobados de uso fuera de política |
| D034 · Detección de cambios de privilegios | C034 | Cambios riesgosos con diferencias de permisos | Detectar ampliación real de permisos en datos autorizados |
| D035 · Detección de comunicaciones anómalas | C035 | Conexiones inesperadas por activo | Un flujo permitido no dispara la regla de aislamiento |
| D036 · Detección de salida indebida de datos | C036 | Señales de salida con alcance y confianza | Reconocer límites de visibilidad con tráfico cifrado |
| D037 · Detección de comportamiento destructivo | C037 | Alertas de actividad destructiva probable | Distinguir una tarea de respaldo autorizada de cambios inesperados |
| D038 · Análisis de persistencia no autorizada | C038 | Cambios persistentes fuera de línea base | Una instalación aprobada no se clasifica como incidente |
| D039 · Detección de abuso de recursos | C039 | Desviaciones y acciones propuestas | Distinguir saturación operativa de evidencia de intrusión |
| D040 · Calibración de detecciones | C040 | Umbrales con errores medidos | Reportar precisión y omisiones por escenario y versión |

## Incidentes y forense

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D041 · Gestión de incidentes | C041 | Casos abiertos, estados y cierre trazable | Reabrir proceso conserva un incidente y su identidad |
| D042 · Triage de incidentes | C042 | Cola priorizada con explicación | Cambiar criticidad altera prioridad sin ocultar evidencia |
| D043 · Adquisición forense de archivos | C043 | Copias verificadas con metadatos | Cambio durante lectura invalida adquisición completa |
| D044 · Forense de memoria | C044 | Hallazgos enlazados a offsets y herramienta | Analizar una captura conocida y registrar limitaciones |
| D045 · Forense de sistemas operativos | C045 | Eventos de sistema con procedencia | No confundir ausencia de artefacto con ausencia de actividad |
| D046 · Forense de red | C046 | Cronología de comunicaciones | Reproducir una sesión de laboratorio con evidencias referenciadas |
| D047 · Forense de nube | C047 | Cronología de cambios y acceso | Detectar huecos de auditoría y reportarlos |
| D048 · Cadena de custodia digital | C048 | Historial verificable de manejo | Una alteración o acceso no autorizado se detecta o rechaza |
| D049 · Análisis de malware | C049 | Indicadores y comportamiento observado | Sin acceso a producción; salida y recursos restringidos |
| D050 · Elaboración de informes forenses | C050 | Informe con hechos, hipótesis y límites | Cada afirmación factual enlaza a evidencia disponible |

## Respuesta acotada

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D051 · Ingeniería de políticas de respuesta | C051 | Permiso limitado y explicable | Rechazar acción que exceda activos o duración permitidos |
| D052 · Contención de consumo de datos | C052 | Bytes aprobados o rechazo persistente | Archivo alterado no llega al consumidor administrado |
| D053 · Contención de sesiones | C053 | Revocación comprobada por proveedor | Revocar solo sesiones del alcance aprobado |
| D054 · Contención de conectividad | C054 | Regla acotada con comprobación posterior | Conservar acceso de recuperación y expirar excepción |
| D055 · Contención de cargas de trabajo | C055 | Cambio acotado de acceso de la carga | Una carga ajena al caso permanece intacta |
| D056 · Gestión de credenciales comprometidas | C056 | Rotación y prueba de uso de nueva versión | Revocar versión anterior solo tras verificar transición |
| D057 · Gestión de cambios de emergencia | C057 | Resultado y plan de reversión | Un fallo de validación detiene el despliegue |
| D058 · Control de impacto de respuesta | C058 | Acciones dentro de presupuesto de impacto | Una cascada excedida se detiene antes de afectar otro servicio |
| D059 · Reversión de cambios defensivos | C059 | Restauración del cambio específico | No revertir cambios posteriores ajenos al incidente |
| D060 · Coordinación de respuesta operativa | C060 | Ejecución por etapas con estados persistentes | Reanudar tras fallo sin repetir acciones no idempotentes |

## Recuperación comprobada

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D061 · Gobierno de respaldos | C061 | Cobertura de recuperación por servicio | Distinguir respaldo existente de respaldo probado |
| D062 · Verificación de integridad de respaldos | C062 | Copias aceptadas o rechazadas | Una copia alterada jamás se utiliza para recuperar |
| D063 · Recuperación en entorno aislado | C063 | Instancia restaurada de ensayo | No escribir en producción durante ensayo |
| D064 · Recuperación de configuración administrada | C064 | Archivos propios restaurados y verificados | Fallo parcial mantiene cerrada la admisión |
| D065 · Recuperación de servicios | C065 | Servicio recuperado con comprobación de salud | No declarar recuperación solo por iniciar un proceso |
| D066 · Reconciliación de datos tras incidente | C066 | Diferencias verificadas y pendientes | Reportar registros faltantes sin inventar datos |
| D067 · Validación funcional de recuperación | C067 | Resultado de una operación real de lectura | Consumir exactamente los bytes inspeccionados tras restaurar |
| D068 · Continuidad de negocio | C068 | Tiempos y fallos reales de restauración | Medir recuperación efectiva en un ensayo completo |
| D069 · Capacidad y continuidad de evidencias | C069 | Nuevo segmento enlazado al anterior | Verificar continuidad sin borrar evidencia previa |
| D070 · Evaluación posterior a incidentes | C070 | Cierre motivado y acciones pendientes | Impedir cierre definitivo con pruebas obligatorias ausentes |

## Prevención y desarrollo seguro

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D071 · Seguridad estática de aplicaciones | C071 | Hallazgos con ubicación y evidencia | Reproducir hallazgos en corpus de evaluación propio |
| D072 · Seguridad de dependencias | C072 | Dependencias afectadas y prioridad contextual | Distinguir coincidencia de versión de impacto demostrado |
| D073 · Seguridad de compilaciones | C073 | Procedencia validada | Rechazar una atestación de otro artefacto |
| D074 · Seguridad de distribución de software | C074 | Actualizaciones aceptadas con versión fijada | Rechazar downgrade no autorizado y paquete alterado |
| D075 · Seguridad de autorización de APIs | C075 | Diferencias entre acceso esperado y observado | Un usuario de prueba no accede a datos de otro ámbito |
| D076 · Seguridad de infraestructura como código | C076 | Desviaciones de política antes de aplicar | Detectar exposición introducida en un cambio de laboratorio |
| D077 · Seguridad de imágenes de contenedor | C077 | Política de admisión de imágenes | Rechazar imagen fuera de procedencia permitida |
| D078 · Seguridad de agentes de IA | C078 | Permiso acotado o rechazo | Texto no confiable no amplía permisos del agente |
| D079 · Privacidad técnica | C079 | Reglas de acceso y conservación mínimas | Evitar datos personales innecesarios en una exportación |
| D080 · Modelado de amenazas | C080 | Amenazas, controles y supuestos trazables | Todo riesgo prioritario tiene control probado o deuda explícita |

## Desarrollo propio por validar

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D081 · Correlación de evidencias | C081 | Relaciones con procedencia y confianza | Una coincidencia temporal no se afirma causal automáticamente |
| D082 · Trazabilidad de decisiones | C082 | Explicación reproducible y discrepancias | Recalcular una decisión y detectar hechos cambiados |
| D083 · Priorización de riesgo contextual | C083 | Prioridad con factores visibles | Mostrar incertidumbre cuando falta telemetría |
| D084 · Evaluación contrafactual defensiva | C084 | Diferencia medida frente a política vigente | No ejecutar respuestas mientras compara políticas |
| D085 · Muestreo adaptativo de seguridad | C085 | Asignación y pérdida de cobertura declarada | Reducir costo sin ocultar las señales descartadas |
| D086 · Evaluación de impacto de contención | C086 | Opciones con impacto esperado y evidencia | Marcar estimación como tal y comprobarla en ensayo |
| D087 · Detección por engaño defensivo | C087 | Alertas por interacción con señuelos | Sin credenciales reales ni conexión necesaria a producción |
| D088 · Evaluación de confianza de inteligencia | C088 | Indicadores con vigencia y procedencia | Una fuente vencida no genera bloqueo automático |
| D089 · Preservación selectiva de evidencia | C089 | Plan de adquisición mínimo suficiente | No capturar fuera de alcance ni exceder presupuesto |
| D090 · Evaluación de incertidumbre operativa | C090 | Limitaciones visibles en alertas e informes | Un sensor caído impide declarar cobertura completa |

## Plataforma y evaluación

| ID / disciplina o especialidad | Componente responsable | Entregable concreto | Comprobación |
|---|---|---|---|
| D091 · Seguridad de plataformas multicliente | C091 | Separación comprobada de datos y recursos | Consulta y acción de cliente A no afectan al B |
| D092 · Administración de acceso privilegiado | C092 | Operaciones mínimas con autorización trazable | Una cuenta de lectura no ejecuta respuesta |
| D093 · Gestión criptográfica de claves | C093 | Operaciones criptográficas auditadas | Rotar claves sin perder verificabilidad histórica |
| D094 · Ingeniería de disponibilidad | C094 | Carga aceptada y rechazos explícitos | Saturación no provoca pérdida silenciosa de eventos confirmados |
| D095 · Ingeniería de evidencia verificable | C095 | Historial, checkpoints y exportaciones verificables | Alteración o prefijo incompleto frente a anclaje se rechaza |
| D096 · Ingeniería de capacidad de almacenamiento | C096 | Escrituras dentro de presupuesto | Procesos competidores no exceden último espacio disponible |
| D097 · Ingeniería de fiabilidad del servicio | C097 | Incumplimientos y presupuestos de error | Medir colas, pérdidas y latencias de casos lentos |
| D098 · Ingeniería de actualizaciones seguras | C098 | Despliegue acotado o reversión | Una regresión detiene el avance al siguiente grupo |
| D099 · Evaluación reproducible de seguridad | C099 | Resultados repetibles con costos y errores | Mismo corpus permite comparar versiones sin alterar producción |
| D100 · Medición de cobertura defensiva | C100 | Cobertura medida y pendientes visibles | Una capacidad sin sensor o prueba no aparece como completada |

La primera entrega forense solo conserva observaciones y auditoría local: no adquiere memoria, discos completos ni evidencia de nube. Una cadena de hashes no prueba por sí sola autoría humana ni admisibilidad legal.
