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

## Alcance de distribución de los archivos publicados

Los archivos añadidos por este lote son código de conexión escrito para NQC, pruebas, documentación y resultados. Los cinco archivos Go upstream se leen sin alterar desde los submódulos en tiempo de compilación y permanecen fuera del commit. El ejecutable se prepara para la sesión local. El lock y los resultados de comparación identifican las dependencias utilizadas. El documento XML de las reglas y el XSD se leen en el checkout local de DependencyCheck. Sus bytes quedan allí.

Grype y OpenSSF Package Analysis incluyen [Apache-2.0 de Grype](https://github.com/anchore/grype/blob/8b2987cf575c69fb715ae4d3b15bb470e3e8f83b/LICENSE) y [Apache-2.0 de Package Analysis](https://github.com/ossf/package-analysis/blob/a149a6f2e1179b8f0c05da6845d8513d360e3b1a/LICENSE). DependencyCheck conserva su [licencia](https://github.com/dependency-check/DependencyCheck/blob/ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1/LICENSE.txt) y su [NOTICE](https://github.com/dependency-check/DependencyCheck/blob/ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1/NOTICE.txt). Si se distribuye el ejecutable Go compilado, el paquete necesitará las licencias y los avisos aplicables a sus fuentes y a los componentes del runtime Go. La auditoría actual cubre el contenido del commit y el uso local. [Apache-2.0, sección 4](https://www.apache.org/licenses/LICENSE-2.0#redistribution) · [Licencia de Go 1.27.3](https://github.com/golang/go/blob/go1.27.3/LICENSE)
