# Findings operativos y corrección sustentada en el diagnóstico

El diagnóstico existente incorpora el resultado a su flujo real de adquisición,
reporte y verificación. No se añade un ejecutor de reparaciones. El perfil v2
`owned-boundary-fault-repair-experiment-v2` emite dos findings operativos y sus
planes únicamente cuando los cinco ensayos reales del laboratorio coinciden.

| Finding operativo | Intervención observada | Corrección propuesta | Evidencia requerida |
| --- | --- | --- | --- |
| Archivo de referencia ausente | Retirada del archivo fijo en la copia temporal | Restituir bytes revisados y modo Git | Baseline, fallo y restauración: ensayos 0, 1 y 2 |
| Modo Git distinto | Bytes iguales, modo 100644 cambiado a 100755 | Restituir únicamente el modo revisado | Baseline, fallo y restauración: ensayos 0, 3 y 4 |

Cada finding conserva ruta relativa, referencia SHA-256/modo, delta observado,
hashes de stdout/stderr, retornos, inventarios y tiempos del proceso. Las dos
causas comparten el mismo código de rechazo; el código solo no identifica la
causa. Los relojes siguen perteneciendo al mismo host.

El plan exige revisar una copia propia nueva, preservar su estado, verificar la
referencia y volver a comprobar el delta antes de actuar. La poscondición exige
inventario completo y salida del revisor iguales al baseline, sin modificaciones
ajenas. Una referencia no verificable, estado distinto o regresión obliga a
detenerse y conservar evidencia nueva. El reporte nunca afirma que esas
precondiciones se hayan comprobado sobre un destino actual.

Un diagnóstico incompleto o inesperado produce cero findings y cero acciones,
con retorno 1. El verificador deriva de nuevo el diagnóstico, findings, plan y
Markdown a partir de las observaciones verificadas. No acepta habilitar
ejecución, inventar aprobación humana, modificar el archivo propuesto, cambiar
su referencia, eliminar condiciones o elevarlo a vulnerabilidad/incidente.

Se conservan `diagnose-owned-boundary` y `verify-owned-boundary-diagnosis` con
sus anclas y digest externos obligatorios. La consola añade solo conteos de
findings y acciones, y `remediation_execution_enabled=false`. Los detalles
permanecen en `diagnosis.json` y `REVIEW.md` privados. El verificador no vuelve
a ejecutar ensayos ni repara nada.

La nueva versión usa `schema_version: 2`. Los expedientes v1 anteriores no se
reescriben ni se renombran como v2; su verificación semántica requiere su lector
y checkout originales. Las herramientas de preservación pueden seguir
conservando sus bytes, sin afirmar validación semántica.

La restauración ya observada pertenece exclusivamente a la copia temporal del
experimento fijo. Estos son fallos de integridad operativa propios, con
`security_severity: null`, sin vulnerabilidad o incidente confirmados. No
demuestra aislamiento del sistema operativo, adquisición externa ni cierre de
M1. La prueba de Bubblewrap de esta sesión falló en el entorno antes de ejecutar
su payload; no se presenta aislamiento como aprobado.

42 pruebas focales aprobadas: 24 anteriores y 18 nuevas. La suite completa
terminó con 3,166 pruebas aprobadas, cero fallos, errores u omisiones. Los
3,148 IDs anteriores conservan sus grupos; las 18 nuevas van al grupo 0.
La preparación y telemetría usaron el SDK real; un proceso separado sin SDK
revalidó los recibos. El worker más lento tardó 96.911316 s; el grupo nuevo,
63.572750 s, sin ampliar presupuestos.

La aceptación separada conserva la adquisición real de los cinco ensayos,
los controles CLI y la instrumentación explícita de SIGSTOP sobre workers
propios. Cada timeout usa el presupuesto original de 30 s y debe terminar en
INCONCLUSIVE, sin findings o acciones. Los recibos del expediente distinguen
esa intervención real de los registros truncados o alterados de prueba; ninguno
se presenta como fallo natural del host. No se fabrica stdout, tiempo o retorno
para la aceptación de SIGSTOP.

Los resultados y límites se registran en CONTINUATION.md y en el expediente
de aceptación. Los 642 archivos históricos permanecen intactos; el verificador
legado conserva su rechazo previo. No se recertifica NQC ni se cierra M1.
