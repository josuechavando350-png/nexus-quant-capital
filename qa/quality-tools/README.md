# Inventario y controles de calidad

El producto de esta prueba está fijado al commit `066cf0876cc921b89c8a2f2229b39e9e1a2b3366`. Desde ese checkout, el comando siguiente recorre los archivos de QA y guarda el progreso fuera del repositorio. Repetirlo reanuda el mismo commit. Con `--status` devuelve las rutas revisadas y pendientes. La finalización exige que el contenido en disco coincida con los objetos de Git y la captura independiente del paquete.

```sh
python3.12 -B -m superhunter inventory --state /tmp/nqc-inventory.sqlite
```

GitHub Actions detiene el proceso a mitad de una transacción tras 254 archivos. Reabre la base, arranca dos lectores que reanudan el trabajo y compara con una ejecución limpia. La versión anterior aporta 742 archivos y la nueva 743, incluido el módulo de reanudación. También se prueban un archivo modificado, un registro de progreso alterado y la correspondencia entre los módulos y sus componentes.

Las tres regresiones históricas de NQC tienen pruebas dirigidas de antes y después. La prueba de Go usa el ejecutable fijado por el producto y observa si el directorio privado de telemetría estaba configurado antes de iniciarlo. Se prueban también un manifiesto válido y uno rechazado y se comprueba la limpieza del directorio. La prueba de Scorecard compara evidencias con entradas generadas por Hypothesis (32 ejemplos deterministas). Coverage.py registra líneas y ramas ejecutadas. Mutmut cambia una copia textual exacta de la función de comparación de Scorecard, cargada con sus dependencias originales. El informe conserva el resultado de cada mutación.

## Muestra histórica de YAML

Se fijaron veinte archivos completos de diez proyectos de OpenStack. Cada par contiene el padre inmediato y el cambio publicado para usar un lector seguro de YAML. La selección tomó un archivo Python modificado por proyecto y excluyó una copia del mismo controlador. Las líneas esperadas proceden del diff. Los nombres, commits, líneas y SHA-256 están en `yaml-cases.json`. Los archivos incluyen código de producto, documentación y pruebas. Una llamada corregida acredita ese patrón en el código y por sí sola no determina su explotabilidad.

La etapa de preparación descarga únicamente archivos públicos históricos y comprueba sus hashes. En un proceso sin red, Bandit 1.9.4 aplica la regla B506 ya usada en Hunter, a los veinte archivos como texto, con nombres opacos. Se guardan sus predicciones antes de leer las respuestas. Un acierto exige señalar todas las líneas modificadas en el archivo anterior. Se cuentan también las alertas sobre cada archivo corregido completo. La comparación solo mide esta regla sobre esta muestra retrospectiva.

Las dependencias de QA para Linux x86-64 y CPython 3.12 están fijadas por versión y hash. La ejecución deja inventarios, diagnósticos, cobertura, mutaciones y las respuestas del transporte antes y después de su reinicio en el artefacto `hunter-inventario-propiedades-yaml`.
