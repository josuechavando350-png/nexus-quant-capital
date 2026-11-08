# Temporales propios con limpieza comprobada

Captura y diagnóstico usan ahora `owned_workspace.Workspace` directamente.
Antes de publicar su expediente, ambos comprueban que la carpeta temporal
creada por esa instancia ya no existe. Una limpieza fallida, identidad
distinta, permisos alterados o reaparición impide publicar éxito.

La clase asigna un nombre aleatorio bajo el directorio temporal del sistema,
con modo 0700. Excluye los árboles de código y salida indicados por el
consumidor. Mantiene abiertos los descriptores del padre y de su carpeta,
comprueba dispositivo/inode y borra descendientes desde el descriptor propio.
Los enlaces se retiran sin seguirlos. Una sustitución de la raíz no autoriza
borrar recursivamente el reemplazo. No hay recolector de carpetas históricas,
limpieza por prefijo, finalizador ni API para borrar una ruta ajena.

Los errores no se ignoran ni se convierten en éxito. La instancia queda
cerrada después de intentar limpiar, también ante error. Una segunda llamada
no vuelve a adquirir propiedad sobre un nombre recreado. El consumidor vuelve
a comprobar ausencia después de sus verificaciones finales y antes de escribir
el expediente. Las fuentes y los formatos previos conservan su significado;
la lectura de un expediente no reejecuta la limpieza.

El cierre intenta liberar ambos descriptores incluso si se pierde uno. Una
reasignación observada a otro objeto no se cierra como si aún fuera el
descriptor original. La pérdida de propiedad invalida la observación de éxito.

La observación interna distingue el instante de creación y el intervalo de
limpieza. `future_absence_proved` y `host_isolation_proved` permanecen falsos.
Es un ciclo de vida para procesos propios con un solo dueño; no un sandbox
frente a código hostil, otros escritores del mismo UID o el kernel. La ausencia
comprobada en un instante no garantiza que otro actor no recree el nombre.

## Reproducción del pendiente de la sesión anterior

La prueba anterior dejó 1,817 carpetas residuales. Se conservó su inventario,
sin borrarlo ni atribuirle una causa no establecida. Un control mínimo de 24
carpetas pasó. La reproducción prolongada bajo la carpeta de evidencia se
detuvo en la sexta observación: la carpeta corriente ya no existía, pero
reapareció una anterior con un inode diferente. Los recibos previos registran
su ausencia; esto no identifica por sí solo qué componente recreó la ruta.

El mismo patrón de copia y verificación bajo temporales del sistema aprobó
64 ciclos, con revisión posterior desde otro proceso y cero residuos. Es una
comparación delimitada del entorno; no demuestra causalidad general ni
disponibilidad 24/7. Los nuevos ensayos prolongados conservan su propia fuente,
tiempo, entradas y comprobaciones de limpieza, separados de los históricos.

## Validación y límites

La base PR104 volvió a aprobar 3,166 pruebas con SDK real y verificador sin
SDK. Las primeras 24 regresiones nuevas del ciclo de vida aprobaron, incluidas
captura y diagnóstico reales, sustitución de sus raíces antes de limpiar,
enlaces, FIFO, errores de IO declarados, reaparición y cierre de descriptores.
La versión corregida aprobó 26 pruebas focales y 3,192 en la suite integral,
con SDK real y verificador separado sin SDK; los detalles están en CONTINUATION.

El candidato inicial pasó 3,190 pruebas, pero un control adicional cerró
deliberadamente su FD raíz y encontró que quedaba abierto el FD padre. Ese
resultado se conserva. La corrección comprueba cada identidad y continúa
liberando el otro descriptor; añade dos regresiones de pérdida y reasignación.
Las corridas del candidato inicial no validan automáticamente la corrección.

Las sondas locales de Landlock y chroot no permitieron aplicar aislamiento
de filesystem en este entorno. No se ampliaron permisos ni se acredita
aislamiento del SO. M1 continúa parcial; no hay hallazgos externos nuevos.

## Corrección posterior durante la admisión

Un control adicional reemplazó la carpeta entre stat y open. La versión de
PR105 rechazó correctamente la identidad, pero dejó abierto el descriptor que
acababa de abrir sobre el reemplazo. El recibo conserva el cambio de cuatro a
cinco FD. La corrección registra por separado la identidad del FD adquirido;
lo cierra aunque no corresponda a la identidad esperada de la ruta. No elimina
el reemplazo. La comparación con la versión anterior conserva una regresión
fallida y cuatro aprobadas con la corrección, usando operaciones reales de IO
y una interposición declarada para programar el instante de sustitución.

Las 26 pruebas anteriores se preservan y se añaden cuatro para admisión.
Los resultados de la suite completa pertenecen al digest de CONTINUATION.
