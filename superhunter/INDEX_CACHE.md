# Verificación de aliases sin trabajo redundante

El perfilado del lector de PR100 sobre 64 aliases idénticos observó 130 llamadas a source_snapshot. La ruta portable repetía la comprobación semántica y la identidad del mismo lector para cada copia. El perfilado añade overhead y no es por sí mismo un benchmark de producción.

La colección ahora reutiliza el resultado de portable.verify solo dentro de una llamada y bajo una clave con la identidad del lector y las cuatro anclas: archivo ZIP, inventario original, paquete preservado y productor declarado. No hay caché global, persistente o compartida entre ejecuciones. Archivos idénticos con un contexto distinto deben verificarse nuevamente y se rechazan si sus anclas no concuerdan.

Cada entrada sigue leyendo y calculando el hash de su archivo, comprobando su identidad antes/después y sumando sus bytes al presupuesto. Todas las entradas se vuelven a comprobar al terminar; también se vuelve a comprobar el código. La reutilización no omite la lectura de aliases ni las comprobaciones finales. Conteos, grupos, estados incompletos, perfiles y CLI conservan el contrato anterior.

Ocho pruebas nuevas cubren 64 aliases, contextos distintos, conflicto de cualquiera de las anclas del contexto, alias alterado, cambio de un archivo anterior durante una copia reutilizada, presupuesto con duplicados, ausencia de reutilización entre llamadas y cambio del código. Pasaron 72 focales: ocho nuevas más las 34 de índice y las 30 de conservación, sin reescribir pruebas anteriores.

La comparación preparada usa tres pares alternados antes/después por corpus, el mismo Python y los mismos archivos: 64 aliases de un ZIP y 64 ZIP distintos del mismo inventario. El segundo corpus varía explícitamente identidades sintéticas dentro de reportes propios; no acredita 64 productores ni ejecuciones históricas. Se registra tiempo de construcción/verificación, CPU, memoria y conteos, con validación sostenida concurrente en el mismo host. No garantiza rendimiento general. QA integral final: 3,129 PASS, cero fallos/errores/skips; los 3,121 IDs anteriores conservan sus grupos y hay ocho nuevos. SDK real y verificación separada sin SDK aprobados. Seis controles CLI adicionales confirman compatibilidad con índices y reportes históricos sin reescribirlos.

## Medición local observada

Tres pares alternados, mismo corpus y Python 3.12.3, con la validación sostenida concurrente:

| Corpus | Construcción antes / después | Verificación antes / después |
| --- | --- | --- |
| 64 aliases idénticos | 4.981023 s / 0.267334 s | 5.078716 s / 0.194029 s |
| 64 ZIP distintos | 5.087222 s / 5.058754 s | 5.201839 s / 5.103855 s |

Son medianas de esta muestra local: 18.63 veces para construir y 26.18 veces para verificar aliases. Los archivos distintos conservaron tiempos similares; no se afirma una mejora universal ni significancia estadística. Antes: digest e7a91e7a14498996f814e7fa6af2aec53f5a712a4c6903dcdc94cf816b3ab60a. Después: 547353d03eaae284d66215e48f6df020bff468de5ec448266aaa95409011b8f8. Todos los conteos coincidieron y los fixtures permanecieron intactos.
