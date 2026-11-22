# Procedencia y uso de tres extractos de informes

SUPERHUNTER comprueba la función que calcula el SHA-256 de su propio catálogo. La lee mediante el AST de Python y calcula por separado el digest de los bytes reales del catálogo. En copias en memoria sustituye el algoritmo por MD5 y SHA-1 y añade un byte al catálogo en un segundo control. El original coincide con el digest fijado por NQC. Las dos sustituciones y el cambio del contenido rompen la coincidencia.

| Repositorio | Aporte utilizado | Comprobación |
|---|---|---|
| #1 usestrix/strix | Tres funciones Python originales convierten ubicaciones del código en ubicaciones físicas SARIF. | Reciben dos diagnósticos de los controles de checksum y ocho ubicaciones alteradas. El exportador descarta cinco. El consumidor de NQC coteja cada línea y fragmento con los bytes usados en el experimento y descarta las otras tres. |
| #10 hahwul/dalfox | La tabla original del exportador Rust aporta la convención de severidad que consume el informe. | Las etiquetas asignadas por NQC a los dos controles se traducen en un resultado SARIF `error` y un `warning`. Se valida la salida contra los niveles previstos y se rechazan tablas con claves duplicadas o formatos desconocidos. Esta participación es de referencia. |
| #169 NVIDIA/garak | La función matemática Python `hit_at_k` mide la probabilidad de seleccionar al menos un registro rechazado al examinar ubicaciones sin reemplazo. | El muestreo de una ubicación da 4/5. Con dos da 44/45. Un segundo cálculo usa el cociente exacto de combinaciones y comprueba los resultados. |

Los dos archivos Python se incorporaron como extracciones identificadas y con importaciones locales mínimas. El fragmento de Rust se conserva como texto y el consumidor interpreta sus cláusulas. Las tres selecciones ejecutan o alimentan operaciones de QA de evidencia. La interpretación de severidad se restringe a las dos mutaciones intencionales. Estos resultados no miden precisión en investigación de vulnerabilidades.

El [recibo](product_supply/passive-source-batch-receipt.json) enlaza las contribuciones mediante la huella del informe combinado. Las [procedencias](product_supply/passive-source-excerpts/origins.json) fijan repositorio, revisión, árbol, ruta, blob, tramos de líneas, digest del extracto y del aviso. La verificación ordinaria funciona con los extractos incluidos. La auditoría desde los repositorios originales contrasta además cada selección con los bytes bajo el árbol fijado.

```sh
python3.12 -B -m unittest -v superhunter.tests.test_product_passive_source_batch
python3.12 -B -c 'from pathlib import Path; from superhunter.product_passive_source_batch import review; from superhunter.safe_io import canonical; import sys; sys.stdout.buffer.write(canonical(review(Path("."))))' > /tmp/nqc-passive-source-review.json
cmp /tmp/nqc-passive-source-review.json superhunter/product_supply/passive-source-batch-receipt.json
```

La comprobación adicional usa un directorio local con los objetos originales de las tres revisiones y la disposición `NNN-repositorio` del inventario. Lee solamente los árboles y blobs declarados.

```sh
python3.12 -B -c 'from pathlib import Path; import sys; from superhunter.product_passive_source_batch import compare_originals; print(compare_originals(Path(sys.argv[1])))' "$local_upstream"
```

Se conservan el [aviso de Strix](product_supply/passive-source-excerpts/LICENSE-001.txt), el [de Dalfox](product_supply/passive-source-excerpts/LICENSE-010.txt) y el [de NVIDIA](product_supply/passive-source-excerpts/LICENSE-169.txt). Los dos proyectos Python incluyen la licencia Apache-2.0. El fragmento de Dalfox lleva el aviso MIT de hahwul. Los archivos de origen, los encabezados y las modificaciones de ensamblaje se identifican en la procedencia. La revisión comercial del producto completo continúa pendiente.

## Alcance de las 47 fuentes sin checkout de producto

La revisión de las entradas del [inventario](SOURCE_CHECKOUT.md) mantuvo los 153 gitlinks previos. Los siguientes grupos explican por qué un checkout completo rebasa el consumo pasivo implementado en este lote. Se indican usos concretos y el alcance actual. El agrupamiento no establece una prohibición general de uso de cada proyecto.

| IDs del inventario | Contenido que excede el flujo verificado |
|---|---|
| 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 29, 51, 52, 53, 54, 55, 56, 58, 60, 62, 63, 64, 67, 68, 70, 71, 73, 74, 94 | Reconocimiento web o de red, herramientas de pruebas activas, datos para sondeos o automatización. De ese grupo se usan únicamente los extractos de representación de informes #1 y #10. |
| 78, 79, 81, 96, 100, 169 | Evaluación activa de plataformas, dispositivos o modelos. De ese grupo se usa únicamente la función estadística #169. |
| 19, 21, 170, 192, 193, 194, 195, 196, 197, 198 | Casos reproducibles de fallos, plantillas o sistemas deliberadamente vulnerables. |
| 179, 191 | SmartBugs incluye 273 rutas de archivos en `tools/` y 156 en `samples/`. Crytic incluye 70 en `not-so-smart-contracts/` y 101 en `program-analysis/`. El perfil conserva sus extractos de ubicaciones SARIF y reglas de tipos de tokens ya verificados en el PR 115. |

Al cerrar el lote quedan cinco de las 47 entradas con extractos y 42 con metadatos. El recuento de fuente completa sigue en 153. Las funciones restantes de estos proyectos conservan su estado pendiente.
