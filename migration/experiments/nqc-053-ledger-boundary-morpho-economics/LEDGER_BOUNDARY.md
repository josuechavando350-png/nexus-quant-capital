# NQC053 — límite verificable del registro NQC047–048/052

El motor original NQC048 se importa sin modificaciones y con hash fijado. Los nuevos procesos usan exactamente las ocho operaciones NQC038, pero sus respuestas son siempre sintéticas. El callback de estas pruebas comprueba únicamente el control del registro; **no sustituye a NQC037 ni autentica pruebas históricas**. La integración auténtica de NQC052 se conserva y no se vuelve a certificar aquí.

## Modelo y garantías observadas

Un proceso supervisor representa el almacén remoto. Serializa CAS por hash del contenido, guarda instantáneas inmutables en archivos temporales con `fsync`, y responde por IPC. Los ejecutores Node son procesos distintos con memoria independiente. Los punteros de cabeza están en memoria del supervisor: no se prueba supervivencia a un fallo de ese servidor, a caída de energía ni a pérdida del host. El directorio temporal se elimina al terminar. **No es un registro operativo ni crea presupuesto real**.

La carrera fuerza que ocho procesos lean el mismo estado y lleguen a la reserva antes de resolver los CAS. Se confirma un ganador, siete conflictos y un único envío simulado. Otras pruebas matan procesos después de reservar, al enviar y después de guardar RECEIVED. Un proceso nuevo se detiene; en RECEIVED revalida y exige revisión. Ocho procesos sucesivos consumen como máximo los ocho IDs mientras la autoridad no se copie ni retroceda.

| Requisito | Evidencia nueva | Alcance / límite |
|---|---|---|
| Reserva previa al intento | Cada despacho exige RESERVED; commit consta en el rastro | Modelo de almacenamiento, no nuevo ensayo GitHub |
| Exclusión | 8 procesos simultáneos, un ganador de CAS | Un host y un supervisor; no prueba multihost ni todos los interleavings |
| Un intento por reserva | Muerte al enviar, recuperación bloqueada | Bajo autoridad sin retroceso; el intento ambiguo no se reenvía |
| Recuperación de respuesta | Muerte tras RECEIVED; otro proceso revalida y se detiene | Validador sintético de control; NQC037 cubierto previamente por NQC052 |
| Presupuesto ocho | 8 procesos sucesivos + proceso de revisión | Solo bajo la misma autoridad sin retroceso |
| Resistencia a rollback | Contraejemplo: 8 intentos, restauración local inicial, ID 1 de nuevo | **Falla: 9 intentos globales**; ningún force-push ni ref remoto usado |
| Identidad global | Dos autoridades copiadas con idénticos scope/plan/spec | **Falla: dos ID 1**; el motor no conoce identidad externa del store |
| Conservar cada respuesta | Error JSON-RPC sintético causa REJECTED sin partes | **Falla: se pierde el cuerpo del error** |
| Conservar bytes originales | JSON equivalente se serializa sin formato HTTP original | **No demostrado; la interfaz de objeto ya pierde información** |

El adaptador GitHub NQC052 fija su rama/ruta y dificulta una copia accidental sin cambios de código. Eso no resuelve el retroceso a un journal anterior en la misma ruta. Los commit SHA identifican historia, pero el contenido antiguo sigue siendo válido para un ejecutor nuevo sin testigo monotónico independiente. Comparar únicamente el SHA del blob no distingue una restauración del mismo contenido (problema ABA). Un registro que incluya su propio checkpoint también puede retroceder con él.

Los ensayos reales de NQC047 conservaron evidencia de rechazo 409 ante SHA obsoleto y una colisión concurrente desde un solo runtime. NQC052 demostró recuperación durable con Python auténtico después de perder una confirmación. No se repiten: no aportan por sí mismos la garantía global que falta. Este experimento tampoco reclama haber atacado o revertido GitHub.

## Por qué la adquisición real sigue cerrada

No hay un servicio accesible que una de forma demostrable una identidad única de autorización, contador irreversible, exclusión de todos los ejecutores y el único punto habilitado para utilizar la credencial. Cambiar de branch, host o sesión no puede tratarse como autorización nueva. Ningún journal de ensayo es el registro LIVE del permiso original.

Para aceptar un diseño futuro haría falta declarar su modelo de confianza y probar su autoridad monotónica o una política operacional equivalente con controles efectivos: impedir restauraciones/copias que recuperen intentos, excluir otros emisores, gastar conservadoramente toda reserva ambigua y bloquear pérdida de ancla. También faltan conservación de cuerpos de error y bytes completos, tratamiento seguro de contenido sensible y revalidación NQC037 antes de cualquier siguiente operación. No basta un flag, un lock local, un documento de procedimiento o un hash guardado junto al estado restaurable.

La política efectiva ahora es **cero despachos reales**. No se habilita LIVE, no se crea un nuevo presupuesto y no se modifica ningún journal anterior. Se alcanzó un límite verificable del diseño actual bajo las restricciones vigentes, sin solicitar credenciales ni ampliar permisos.
