# Prueba de conciliación para valorar la preparación de Hunter

Metric publica auditorías previas y distingue sus problemas conocidos del material elegible para recompensas. Para evaluar la preparación de Hunter se eligió una tarea de contabilidad básica. Los doce contratos Solidity de esta carpeta son originales de NQC y representan hojas de cálculo de dos columnas. La muestra es sintética. No incorpora código, datos de cuentas ni reglas de precios de Metric.

Fuentes públicas del programa: [información y auditorías](https://immunefi.com/bug-bounty/metric/information/) y [alcance](https://immunefi.com/bug-bounty/metric/scope/).

## Pregunta y criterio de puntuación

Dos columnas guardan unidades de papel. Cada fila no vacía mueve una cantidad de la izquierda a la derecha. El informe debe mostrar ambos saldos finales, la cantidad de filas no vacías y el total de ambas columnas. Se eligieron seis errores y sus seis correcciones. Hay seis entradas fijas por hoja, entre ellas filas vacías, cantidades pares e impares y cantidades mayores a un millón en el saldo inicial.

El productor de Hunter está fijado a `066cf0876cc921b89c8a2f2229b39e9e1a2b3366`. Solc 0.8.30 compila las hojas y Forge 1.10.0 registra los cuatro campos calculados por cada una. Los ejecutables se verifican contra los hashes del producto. Toda la ejecución de los contratos se efectúa en un entorno local sin red.

El conciliador de Hunter recibe los dos saldos iniciales y finales y los movimientos declarados por las entradas de la prueba. Recibe identificadores opacos y carece de acceso a la clave de corrección en su interfaz. Los campos de presentación (contador y subtotal) quedan fuera de la interfaz del conciliador. Se congelan observaciones y predicciones. Un segundo proceso de Forge repite las entradas en orden inverso. Después se contrasta la clave con una implementación independiente que revisa los cuatro campos.

Se cuenta un acierto por par si Hunter alerta en al menos una entrada con salida incorrecta y la hoja corregida no produce alertas. El resultado desglosa también cada entrada. Un control adicional declara incompleta la cobertura de movimientos y comprueba que Hunter se abstenga. La repetición no aumenta el tamaño de la muestra. El resultado mide un conciliador con entradas contables conocidas y no establece detección general por lectura del código fuente.

Las salidas completas de cada ejecución se guardan en el artefacto `hunter-metric-contabilidad-propia`. La rama conserva `score.json` como referencia.

## Prueba ampliada de las hojas de NQC

Se evalúan las mismas doce hojas con 128 entradas distintas por hoja. La matriz cruza cuatro escalas de unidades, las cuatro combinaciones de partidas vacías y ocho variaciones de cada combinación. Se observan los cuatro campos producidos por la implementación nativa. El conciliador original recibe los saldos y los movimientos. Un control adicional de presentación compara el contador con las partidas no vacías y el subtotal impreso con la suma de las dos columnas impresas.

Las observaciones y predicciones se escriben antes de abrir la clave y utilizar el modelo independiente para puntuar. Las 1.536 salidas incluyen 514 con un valor incorrecto. El conciliador original detecta 290 de ellas. Al añadir los dos controles de presentación se detectan las 514. Los dos modos dan cero alertas en las 1.022 salidas correctas. Los dos controles se diseñaron después de conocer las omisiones del ensayo inicial. Es una comprobación de regresión de seis defectos conocidos en hojas propias. El artefacto de GitHub incluye los 128 vectores, las predicciones por hoja y el resultado en la subcarpeta `fields/`.
