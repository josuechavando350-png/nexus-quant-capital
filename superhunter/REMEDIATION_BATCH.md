# Comprobaciones de remediación al abrir evidencia de NQC

El producto aplica tres selecciones pequeñas de soluciones defensivas publicadas al índice de revisiones Git y al archivo de evidencias de NQC. La salida conserva la huella del informe combinado en las tres participaciones.

| Proyecto | Operación que consume NQC | Resultado observado |
|---|---|---|
| #194 Juice Shop | Node ejecuta los siete renglones originales de la corrección TypeScript que comprueba igualdad exacta de URL. NQC le entrega los destinos del índice verificado para cotejarlos con la revisión y el repositorio admitidos. Un segundo lector analiza por separado esquema, autoridad y segmentos de la ruta. | Las 47 URL del índice pasaron. Ambos métodos rechazaron 188 variaciones locales de ruta, consulta, fragmento o tipo de objeto. Las URL se procesan como texto. |
| #195 WebGoat | La especificación de remediación exige que la ruta canónica permanezca dentro del directorio previsto. NQC aplica ese criterio al abrir dos archivos reales de evidencia, comprueba de nuevo los componentes del camino y utiliza el lector de descriptores y hashes de NQC. | Se leyeron ambos archivos. Dos referencias a un directorio hermano que compartía prefijo refutaron la alternativa de comparar cadenas por prefijo. El lector rechazó además un enlace interno y el control con un byte alterado. |
| #197 DVWA | El ejemplo reparado define una lista de nombres de archivo y la denegación para el resto. Se usa como referencia semántica y corpus de nombres para comprobar el control de admisión del índice. Sólo se comparan cadenas de nombres de archivo. | El lector admitió los nombres de los dos archivos de evidencia e impidió leer un tercer archivo real con contenido y ubicación válidos que estaba fuera de la lista. El corpus original aportó cuatro nombres admitidos y se rechazaron tres variaciones independientes. |

El informe califica la admisión de evidencia de esta plataforma. Estas pruebas no demuestran descubrimiento de vulnerabilidades ni evalúan servidores externos. Sólo se ejecuta una función de comparación de cadenas del primer origen. Las otras dos participaciones corresponden a uso de referencias documentales y de código como datos.

La [procedencia](product_supply/remediation-excerpts/origins.json) fija revisiones, árboles, blobs, tramos de líneas, digests y avisos. El fragmento de Juice Shop conserva sus bytes bajo su aviso MIT. Se conservan los avisos de WebGoat, la GPL-2 y la licencia GPL-3 distribuida por DVWA. La presentación local del fragmento y de la licencia de DVWA normaliza los finales de línea y el espacio final. Los digests originales se conservan para cotejarlos con Git. Las selecciones documentales se publican como texto legible con sus avisos. La evaluación de distribución comercial del producto completo sigue pendiente.

## Reproducir

La ejecución nativa usa el binario de Node 24.22.3 para Linux x86-64 con SHA-256 `acbe4b8d9153b841ed0697cbfc4f93e767386620edb745ab9358306c0a6f31aa`. Se localiza en PATH o en `NQC_REMEDIATION_NODE`. El proceso recibe el mismo archivo verificado, un espacio de red aislado, el modo de permisos de Node y un límite temporal. La preparación externa del intérprete corre por cuenta del entorno. El procedimiento fallará si el intérprete tiene otra huella.

```sh
python3.12 -B -m unittest -v superhunter.tests.test_product_remediation_batch
unshare --user --map-current-user --net python3.12 -B -c 'from pathlib import Path; import sys; from superhunter.product_remediation_batch import review; from superhunter.safe_io import canonical; sys.stdout.buffer.write(canonical(review(Path("."))))' > /tmp/nqc-remediation-review.json
cmp /tmp/nqc-remediation-review.json superhunter/product_supply/remediation-batch-receipt.json
```

Para comprobar los extractos y avisos contra objetos locales de los proveedores, el directorio de entrada debe tener los nombres `NNN-repositorio` y contener las revisiones fijadas. La comprobación no inicializa submódulos ni ejecuta sus aplicaciones.

```sh
python3.12 -B -c 'from pathlib import Path; import sys; from superhunter.product_remediation_batch import origins; print([x["id"] for x in origins(Path(sys.argv[1]))])' "$local_upstream"
```

Este lote incorpora tres extractos a los cinco anteriores. Los tres no se contabilizan como checkouts completos. [Recibo reproducible](product_supply/remediation-batch-receipt.json)
