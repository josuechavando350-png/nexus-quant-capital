# Continuidad — enlace nativo de admisión reparado

Base acumulativa exacta: `codigo/` de `SUPERHUNTER_evaluacion_877.zip`.
No se sustituye esa base por las ramas remotas más pequeñas. Se preservan sus
96 archivos originales, salvo los cambios enumerados por el parche de esta
entrega. Los 877 IDs de prueba se mantienen; hay 48 adicionales: 32 de admisión, seis de caché exacta del grafo y diez de particionado/conciliación de QA.

Cambios: quinta fuente nativa `diablo/ratelimit.py`, identidad original fijada;
cargador y procedencia de cinco fuentes; adaptador `rate_control.py`; integración
antes del cálculo local NQC; verificación de las nuevas declaraciones; controles
negativos, de concurrencia, de recarga y de fracciones exactas. Los cuatro archivos
nativos previos conservan exactamente sus bytes.

Se mantienen intactos los catálogos de 27 requisitos, 50 capacidades y 25
iniciativas. No se marca una capacidad amplia como completa por este arreglo.
Los reportes previos de cuatro fuentes no se reescriben para convertirlos en
recibos de cinco fuentes; se regeneran con la nueva versión.

La base remota consultada del PR43 continúa en
`8a6206d66abc949a7c0115dcd3bc1e2a499845af`. Se preparó además una variante focalizada
con 412 tests (380 de esa base + 32 nuevos), pero no debe confundirse con la base
acumulativa final de 925 tests. Consultar VALIDATION_RATE_REPAIR.json de la entrega para
el estado final de publicación: preparar objetos Git no equivale a publicar un
commit, actualizar una rama o fusionar un PR.

Intentos de ejecución no aprobados también se conservan. En particular, el primer
recorrido de 909 pruebas tuvo un timeout en un test heredado de argumentos de
CLI; no se quitó ni se aumentó su timeout. Se preparó un entorno virtual local
sin pip, reutilizando exactamente los bytes de las dependencias ya instaladas,
para repetir la ejecución sin los paquetes de inicio del entorno general.

Pendientes materiales: consolidación remota canónica; recuperación del código
asociado al log854/signed_scope y conciliación de la línea809; Slither/solc/EVM;
conectores externos; investigación efectiva y evaluación ciega. Slither y solc
siguen ausentes, y fallaron la resolución DNS de PyPI y una descarga oficial de
Solidity. No se inventó su ejecución.

Optimización adicional: una sola entrada de caché para el grafo sintáctico,
ligada a los bytes exactos capturados y a la identidad del analizador. Se leen
las fuentes antes y después incluso al reutilizar el resultado. No se aceptan
mtime, conteos o hashes declarados en vez de bytes; se devuelve una copia nueva.
Se mantienen los límites de tiempo originales de pruebas y workers.

La repetición monolítica del control completo también excedió 180 segundos,
incluso con el entorno limpio y la caché. El gate ahora ejecuta cuatro particiones
deterministas, manteniendo cada módulo de tests junto. Cada worker conserva sus
límites de 90 segundos de CPU y 180 de tiempo real; el total permitido pasa a
cuatro workers secuenciales. No se modifica el timeout de ninguna prueba.
La agregación exige mismo código e inventario global, todos los grupos, todos
los IDs exactamente una vez y resultados individuales; un grupo incompleto o
con fallo no puede convertirse en PASS global. Los recibos originales de cada
worker permanecen en receipt.json y son recomputados por el verificador.
