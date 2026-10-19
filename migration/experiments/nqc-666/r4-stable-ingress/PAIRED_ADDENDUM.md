# Comprobación adicional por regresión concreta

La matriz registrada terminó sin descartes y con igualdad de resultados. El ingreso
R4+nativo frente a R3+IPC tuvo mediana +3,87%, p99 +25,76% y p99.9 +66,36%, mientras
que el máximo bajó 11,96%. El escenario preparado y la matemática mejoraron. No se
declara estabilización del camino completo ni se atribuye causalidad a un componente.

Para reducir la influencia de deriva temporal del host se hará una comprobación
adicional, **sin cambiar código de ejecución**, comparando R3+nativo con R4+nativo
sobre la misma entrada inmediatamente uno tras otro, alternando cuál se ejecuta
primero. Así se estudia específicamente el coste del nuevo gateway; no se vuelve
a cambiar el transporte entre variantes.

12.288 pares, 24.576 ventanas individuales. Un corpus sintético R3 común, mismos
precios supuestos, comprobación de igualdad por par, afinidad a la misma CPU y todas
las muestras conservadas. Orden del corpus mezclado con semilla 666405; el orden
de variantes se alterna exactamente. 64 pares de calentamiento. No se elige el mejor
resultado ni se reemplaza la matriz original.

La distribución de diferencias dentro de cada par se publica además de percentiles
de cada variante. Se conservan descartes y se verifica que la recuperación no quede
incluida tácitamente en una ventana que no la mide. La prueba puede ayudar a localizar
el coste, pero no elimina jitter de la VM, efectos de caché o limitaciones de cola.
Si los percentiles siguen regresando, se conserva esa conclusión y el cambio queda
experimental por sus correcciones de integridad; no se anuncia como más rápido en
todo el sistema ni como listo para producción.
