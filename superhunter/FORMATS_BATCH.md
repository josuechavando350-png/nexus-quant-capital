# Preservación de obligaciones al emitir un objeto de prueba

SUPERHUNTER comprueba las etiquetas de tres obligaciones de su emisor C para CBMC. Las expresiones proceden de las filas 108, 129 y 199 del inventario de avisos ya registrado. Esta revisión verifica la representación del emisor. No reevalúa licencias ni certifica las propiedades del programa.

| Componente | Participación | Resultado observado |
|---|---|---|
| radare2 #129 | Referencia de formato. El lector aplica los formatos declarativos de cabecera y sección ELF64 y las enumeraciones de radare2 a los tres objetos de NQC. | Extrae las secciones de código y de etiquetas. GNU objcopy reproduce todos sus bytes. |
| Capstone #132 | Ejecución. El decodificador x86 se compila desde 114 blobs autenticados y procesa las secciones obtenidas mediante la referencia de radare2. | En el objeto original se decodifican 77 instrucciones. Sus fronteras coinciden con GNU objdump. Las reubicaciones de GNU readelf identifican las tres aserciones y sus argumentos de etiqueta. |

El consumidor acepta el objeto con las tres etiquetas previstas. Rechaza el objeto con una obligación omitida. Rechaza también un objeto con tres llamadas y una etiqueta repetida, aun cuando conserva las mismas 77 instrucciones y sus fronteras coinciden con el original. Los objetos ELF de entrada permanecen sin ejecutar. El enlace entre productores y las huellas por caso se encuentran en [el recibo](product_supply/formats-batch.json).

## Reproducción local

Se requiere Python 3.12, GNU GCC para SysV AMD64, GNU Make, binutils y Linux con espacios de nombres de red sin privilegios. El módulo trabaja en directorios temporales y compila una sola biblioteca de Capstone para los tres casos. Las dos revisiones de los submódulos están en el recibo. La compilación y el análisis se realizan con la red aislada. El objeto y las instrucciones pueden variar en otra versión del compilador.

```sh
python3.12 -B -m unittest superhunter.tests.test_product_formats_batch
NQC_UPSTREAM=/ruta/a/upstream python3.12 -B - <<'PY'
import json, os
from pathlib import Path
from superhunter.product_formats_batch import canonical, review, sha
rows = review(Path(os.environ['NQC_UPSTREAM']))
if rows != json.loads(Path('superhunter/product_supply/formats-batch.json').read_bytes()):
    raise SystemExit('El resultado difiere del recibo publicado')
print(sha(canonical(rows)))
PY
```

La huella canónica de aceptación es `137ad2e85120cef80b3bbff8bf470028e2d0637ced971c86afab332f041ea8ed`.
