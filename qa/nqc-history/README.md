# Tres correcciones históricas de NQC

Pregunta: ¿qué defectos propios señala el Hunter publicado al recibir una versión completa de NQC sin una pista sobre el fallo?

Se eligieron retrospectivamente tres correcciones previas al experimento y su padre inmediato. Las causas están en cases.json y pueden contrastarse con los cambios en Git. Cada versión usa un identificador derivado de su SHA. El proceso de revisión recibe el directorio y el producto fijado, sin identificadores Git, parches, rúbrica ni indicación de qué archivo revisar. Los cambios ya eran públicos al congelar el producto. Es una evaluación interna, no una prueba prospectiva independiente.

La prueba usa dos controles existentes. El primero revisa el perímetro del repositorio. El segundo verifica el inventario declarado de componentes. Los dos revisores proceden del mismo commit 05002c36c12a1b572b5d425b7b0714189c448109. Para interpretar cada versión se carga su propio registro de componentes y se intenta obtener su inventario nativo. Si el capturador histórico alcanza su límite de archivos, se conserva la causa y se suministran al validador los nombres de los archivos de superhunter del checkout, sin añadir ni quitar diagnósticos. El control de inventario utiliza únicamente la presencia de esas rutas. No se ejecutan las pruebas añadidas en los arreglos, ni código de proyectos externos.

El orden de las seis entradas se invierte en una segunda ejecución. Los resultados deben coincidir por identificador. Se conservan los diagnósticos originales antes de cotejarlos con las respuestas. Un acierto requiere una alerta que identifique la causa concreta antes del arreglo y desaparezca después. Un pase genérico o un bloqueo sin identificar la causa no cuentan como acierto. Un fallo de infraestructura invalida la ejecución. Las versiones corregidas son controles negativos únicamente para los tres fallos elegidos. Una alerta ajena queda sin clasificar salvo verificación adicional. La muestra contiene fallos de ingeniería. No mide vulnerabilidades explotables ni la precisión general del producto.

Para repetir, ejecutar desde un checkout limpio del producto fijado con los seis commits en el historial, con Python 3.12 y Git disponibles. Pasar directorios externos al checkout.

```sh
python3.12 -B /ruta/qa/nqc-history/benchmark.py /ruta/al/producto /ruta/a/evidencia-nueva
```

## Resultado observado

| Corrección | Antes del arreglo | Después del arreglo |
| --- | --- | --- |
| Inventario | El validador identificó por nombre el módulo sin asignar. | Sin alerta. |
| Comparación de informes | Ninguna alerta sobre el cambio legítimo de revisión en Scorecard. | Sin alerta. |
| Limpieza temporal | Ninguna alerta sobre la carrera con la telemetría de Go. | Sin alerta. |

El perímetro pasó en las seis entradas. El capturador nativo del inventario alcanzó su límite de 500 archivos en las seis. Con los nombres completos proporcionados por la prueba, el validador de Hunter encontró uno de tres fallos. Ninguno de los tres controles corregidos produjo una alerta y ambas pasadas dieron los mismos diagnósticos.

Los diagnósticos están en `predictions.json`. La acción de GitHub compara la primera pasada con esta referencia y conserva las dos pasadas, junto con las correspondencias entre identificadores y commits.
