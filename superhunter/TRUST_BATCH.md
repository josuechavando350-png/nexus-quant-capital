# Dependencias del comparador de encabezados de NQC

El lote comparte el lock npm del comparador de encabezados entre tres contribuciones. Los proyectos se cargan desde sus objetos Git en las revisiones de `PINS`. Los resultados son reproducibles en Linux x86-64 con Go 1.27.3 del kit de revisión de NQC, Python 3.12, lxml y Git. La prueba de contraste usa Node con `semver` accesible a `require`.

| Origen | Operación | Resultado de la revisión del lock fijado |
|---|---|---|
| Anchore Grype | Su parser de rangos y su predicado de comparación reciben los límites de las dependencias resueltas, incluidas las copias anidadas. NQC normaliza los selectores exactos, caret y tilde de este lock y compara las versiones observadas. | 61 arcos válidos y 61 cambios de versión rechazados. Un segundo proceso con `node-semver` y recorrido independiente de las rutas reprodujo las 122 decisiones. |
| OpenSSF Package Analysis | Las funciones originales de análisis estático calculan SHA-256 y longitudes de línea en bytes para cuatro entradas del comparador. El consumidor coteja cada digest y cada línea con los bytes leídos desde NQC. | Una sustitución del mismo ancho cambia el digest. Al compactar el lock se mantiene el contenido JSON y cambia el perfil de líneas. |
| OWASP DependencyCheck | El consumidor valida el documento de supresión contra el XSD 1.4 y ejecuta los dos predicados declarados por la regla upstream #5454 sobre las identidades del lock. | Rechaza la atribución controlada del CPE `flat` a 33 identidades ajenas. Conserva la identidad `flat` y el control de un CPE diferente. Se acredita como referencia de atribución y descarte de falsos positivos. |

El caso CPE es un control de atribución. El expediente no contiene consultas a bases de vulnerabilidades ni atribuye hallazgos al contenido del lock. La interpretación de selectores está acotada a las formas del lock de NQC; una sintaxis sin soporte detiene esta revisión.

Con `NQC_TRUST_TEST_SOURCES` apuntando al directorio de checkouts `upstream` y el binario `go` de la distribución fijada en `PATH`, ejecutar en la raíz de NQC:

```sh
python3.12 -B -m unittest -v superhunter.tests.test_product_trust_batch
```

Para reutilizar el binario entre lotes, compilar una vez en una carpeta temporal vacía desde los objetos Git y copiar `build_native(work, original_sources(source_root))` al directorio de herramientas verificadas. `NQC_TRUST_BINARY` acepta esa ruta. El adaptador copia los bytes a un espacio privado y verifica su SHA-256 antes de ejecutarlos. Los datos, controles y resultados se calculan de nuevo en cada uso. El [expediente completo](product_supply/trust-batch-receipt.json) conserva los 61 arcos y la procedencia por proyecto. El artefacto ejecutable no se distribuye en el producto.
