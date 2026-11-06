# Continuación después de 0.24

Recuperar el HEAD actual de `NQC-defensive` y leer CONTINUIDAD, VALIDACION, PROGRESO y TURNO_8H_20261106. Respetar la ventana ya solicitada y no crear otra tarea ni extenderla. Trabajar exclusivamente en las rutas de defensa autorizadas, con checkout aislado y actualización remota condicionada al HEAD esperado.

La base funcional actual reúne admisión de artefactos, cadena local de integridad/restauración, ingesta de autenticación, casos, evidencia, revisión, firma, registro/receptor, prioridad explicada, evaluación y comparación de políticas. El comparador no recomienda ni instala la candidata. Conservar los corpora y sus errores; cualquier cambio de regla necesita un informe separado.

Antes de iniciar otra prueba larga, ejecutar `tools/check_endurance_provenance.py` y revisar las entradas pendientes. No atribuir los ensayos de 0.19, 0.20 o 0.22 a versiones posteriores. Sus checkouts congelados sirven como fuentes históricas; el resultado registrado y los hashes tienen prioridad sobre una nota antigua de “en curso”.

El siguiente candidato de implementación local es un subconjunto de C011: observación de procesos propios de laboratorio, con selección explícita de PIDs e identidad de inicio para distinguir reutilización de PID. Probar con procesos benignos creados por el propio harness; no enumerar ni controlar equipos externos. Confirmar primero qué datos del entorno están disponibles y rechazar explícitamente observaciones incompletas o permisos insuficientes.

La entrega debe conectar observaciones con el almacén operativo y preservar referencias verificables. Un snapshot no acredita captura de todos los eventos de creación/terminación, origen autenticado ni cobertura de intervalos no observados. La desaparición de un proceso debe producir un estado explícito, sin inventar una lectura limpia. No presentar este sensor como eBPF ni activar un daemon productivo por importación.

Si la interfaz requerida no está disponible, conservar el bloqueo preciso y avanzar otra dependencia realizable en el mismo ámbito. No sustituir una captura real por datos simulados sin declararlo. La procedencia independiente, separación administrativa, captura productiva y recuperación distribuida siguen requiriendo recursos concretos; no se resuelven con etiquetas.

Cada ciclo debe conservar código ejecutado y evidencia. Verificar las pruebas afectadas y el aislamiento antes de publicar. Reportar siempre cierres/200, porcentaje pendiente, cobertura parcial de componentes y criterios del bloque; actualmente 0/200 cerrados, 200/200 pendientes y 24/100 componentes con alcance parcial.
