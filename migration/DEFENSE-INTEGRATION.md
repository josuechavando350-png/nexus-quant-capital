# Incorporación local de NQC Defense; activación operativa pendiente

Paquete nuevo: `migration/defense/`. No reemplaza archivos existentes. Base consultada: `16e352225ba8a6a931834c4edf3d86d9a2924b7d` de `josuechavando350-png/nexus-quant-capital`.

Esta ubicación mantiene el código nuevo separado de Census y del código recuperado inmutable, dentro de la zona admitida por el verificador actual. Es preparación local, no activación. Ninguna importación lateral, workflow o hook arranca el motor.

Antes de conectar consumidores productivos:

1. Materializar el checkout completo y comprobar su base. Si otro trabajo avanzó el commit, revisar los cambios y actualizar el anclaje solo después de esa revisión.
2. Incorporar solo los archivos nuevos de esta entrega, preservando todos los bytes originales.
3. Ejecutar `python3 -B migration/defense/tools/check_nqc_base.py .`, el verificador de aislamiento original y las pruebas pertinentes.
4. Seleccionar el consumidor específico de evidencias de NQC y definir cómo deberá actuar cuando una admisión falle. Esa conexión aún no existe y no se presume por compartir repositorio.
5. Medir observación local, errores y falsos positivos antes de cualquier activación que cambie operaciones.

En la versión 0.2.0 se completaron los pasos 1–3: 645 archivos recuperados y verificados por blob Git, adición local aislada, verificador original válido y 9 pruebas de aislamiento aprobadas. Las 100 pruebas propias también pasan. Se inspeccionó un archivo real de Census mediante el motor y se verificó su recibo y auditoría.

La versión 0.3.0 conecta un consumidor local nuevo: `ArtifactReader.read_json` y CLI `read-json` usan obligatoriamente `Engine.admit_bytes`. Los bytes se capturan durante la inspección y solo se entregan después de confirmar la decisión y su auditoría en SQLite. El lector no reabre la ruta. `python3 -B migration/defense/tools/check_nqc_consumer.py .` comprueba esta ruta con el manifiesto real de NQC, preservando sus bytes y verificando recibo, auditoría y aislamiento. Pasan 123 pruebas del paquete y 9 de aislamiento.

Los pasos 4–5 respecto al consumidor productivo de Census siguen pendientes. El lector nuevo es ejecutable localmente, pero no se introduce por importación lateral en el código original. No se afirma nueva certificación canónica ni funcionamiento 24/7. El usuario autorizó publicar código en la rama separada `NQC-defensive`; la activación productiva sigue pendiente. No se modificó ningún archivo de la base previamente rastreada de NQC.

La versión 0.4.0 extiende la auditoría de ese mismo lector con páginas verificables. El control del manifiesto real ahora verifica sus tres registros en tres páginas, incluida la admisión que queda en una página distinta de la autorización del snapshot. Se añaden 25 pruebas del formato, continuidad, reanudación y CLI; la suite total es 148 más 9 de aislamiento. El formato paginado conserva los registros en SQLite y no cambia ninguna ruta de Census.

La versión 0.5.0 agrega un testigo local opcional, con otra base y otra clave. El control del manifiesto crea ese testigo en un directorio temporal separado, registra el primer checkpoint, exige ese prefijo en la segunda lectura y avanza al registro 6 mediante páginas verificadas. El motor comprueba el testigo dentro de cada transacción cuando está configurado. Pasan 173 pruebas del paquete y 9 de aislamiento. El testigo no es un servicio remoto independiente, no sustituye respaldos y no modifica ni activa el circuito productivo de Census.

La versión 0.6.0 conecta un archivo local separado a ese flujo. Las seis páginas del control real se guardan, sincronizan, releen y vinculan a dos manifiestos antes de los avances del testigo. El comando local `archive-audit` expone esta ruta. Pasan 203 pruebas del paquete y 9 de aislamiento. No se borra ninguna fila del historial como parte de la implementación ni se activa retención; las pruebas de fallos utilizan únicamente archivos y bases temporales nuevos.

La versión 0.7.0 enlaza esos dos manifiestos en un catálogo de cobertura, con el recibo inicial retenido antes de consumir y el final confirmado por el testigo. Se verifican de nuevo sus seis páginas y la correspondencia exacta entre cada intervalo y cada avance. El recorrido rechaza huecos, solapamientos y objetivos elegidos por el propio catálogo. Pasan 227 pruebas del paquete y 9 de aislamiento. Los catálogos son compatibles con el almacén 0.6.0 y se crean sin migrar sus bases ni sobrescribir archivos. La verificación del almacén es una lectura secuencial local, no un snapshot atómico del sistema de archivos ni garantía de disponibilidad futura.

La versión 0.8.0 conecta ese catálogo al inventario del almacén: nueve archivos reales, sus tamaños lógicos y referencias. Repite la cobertura seleccionada y compara metadatos antes/después del recorrido. Pasan 255 pruebas del paquete y 9 de aislamiento. Una referencia faltante queda identificada por ruta y desactiva la clasificación de objetos fuera de selección. El inventario no borra, repara, impone cuotas ni modifica fuentes originales o el consumidor productivo.

La versión 0.9.0 configura y reabre el almacén de la comprobación local con un presupuesto fijado de 1 MiB/64 objetos. Todas sus páginas, manifiestos y catálogo se escriben bajo ese control; inventario y estado concuerdan en diez objetos, incluida la política. Pasan 285 pruebas del paquete y 9 de aislamiento. Una aceptación adicional llena seis objetos y demuestra que la siguiente entrada se rechaza sin modificar el archivo ni avanzar el testigo. Es un control local de escritores cooperantes, no una cuota del SO ni retención de SQLite; Census productivo sigue pendiente de integración.

La versión 0.10.0 añade una cadena local de protección de una copia administrada del manifiesto: observación, detección, caso persistente derivado del ledger, bloqueo de admisión, restauración verificada y lectura posterior. La aceptación muta solamente una copia temporal. Archivo y testigo verifican tanto incidente como recuperación. Los catálogos nuevos contienen 100 componentes y 100 especialidades como requisitos enlazados; 9 componentes tienen alcance parcial ejecutable, ninguno completo. No se conecta el consumidor productivo ni se activa un servicio.

La versión 0.11.0 añade ingesta JSONL de autenticación en un almacén operativo local, con cursor/detección/caso confirmados juntos y rotación explícita. Importa el estado verificado de ManagedIntegrity a la misma vista de casos. No modifica SuperHunter, las fuentes originales ni la operación de Census.

La versión 0.12.0 añade formatos OpenSSH/journald sobre la misma ingesta transaccional y casos. Los cursores nativos se deduplican dentro de cada fuente. Se prueba con fixtures explícitos, sin cambiar servicios ni fuentes originales; SuperHunter permanece separado.

La versión 0.13.0 conecta los casos de autenticación con adquisición acotada de sus registros y paquetes verificables offline mediante pins externos. Las pruebas usan archivos temporales propios; no cambian fuentes originales, servicios ni SuperHunter.

La versión 0.14.0 conecta la evidencia preservada con revisión local por permisos, historial HMAC, notas, valoraciones y cierre benigno confirmado por otra credencial. Conserva el registro original para no invalidar sus pins. No modifica producción ni SuperHunter.

La versión 0.15 incorpora revocación, rotación y renovación de credenciales de revisión en el mismo almacén operativo. Conserva registros anteriores y requiere checkpoints después de cambios. Alcance local a la base/política y actualización de todos sus procesos; sin despliegue ni cambios a SuperHunter.

La versión 0.16 incorpora caducidad configurable y observación autenticada del reloj en la base de revisión. Verifica vencimientos y conserva observaciones de rechazo tras revertir acciones; no es una autoridad temporal independiente. Mantiene separación de SuperHunter y producción desactivada.

La versión 0.17 exporta expedientes privados de autenticación con evidencia e historiales enlazados y un verificador sin acceso a la base original. El alcance sigue siendo local y sin custodia independiente. Registra además las métricas de cierre y cobertura parcial solicitadas por el usuario.
