# Limpieza de procesos del QA

Cada worker QA inicia una sesión propia. El padre espera hasta 180 s y, al terminar
por éxito, error, timeout o interrupción, envía SIGKILL a los miembros restantes
del mismo grupo y recoge el proceso directo. Un fallo de limpieza no se convierte
en aprobación; se intenta terminar también el proceso directo antes de propagarlo.
Los recibos y logs explícitos siguen siendo la evidencia del QA. La salida arbitraria
de consola se descarta, sin acumularla en la memoria del padre ni publicarla.

Un control propio con un hijo durmiente mostró que el lanzador anterior dejaba ese
hijo ejecutándose después del timeout. Los tests actuales comprueban procesos reales
para timeout, éxito y salida no nula; comprueban además interrupción y rechazo de una
limpieza fallida. No se señalan procesos ajenos ni se usan destinos de red.

Se conservan ocho workers, 180 s de pared, 90 s CPU, 2 GiB y 20 MiB por archivo, el
prefijo de caché nuevo de #62 y la preservación de evidencia fallida de #61. Los
controles unitarios usan plazos menores solo para sus propios procesos sintéticos;
no alteran los límites de los workers del QA completo.

Alcance: descendientes que permanecen en el mismo grupo. Un descendiente que crea
otra sesión/grupo queda fuera de esta limpieza. No es un cgroup, un sandbox ni una
prueba de aislamiento completo. Tampoco convierte contadores por proceso en un
presupuesto agregado de CPU o memoria de todos los descendientes.
