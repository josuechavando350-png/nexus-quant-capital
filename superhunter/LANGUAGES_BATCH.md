# Tipos enteros de Census y compatibilidad de diagnósticos

El módulo `product_languages_batch.review` produce cuatro resultados deterministas sobre entradas fijadas en NQC. Los enlaces entre productores son los campos `cppcheck_sha256` y `schema_result_sha256`. El [recibo reproducible](product_supply/languages-batch.json) contiene resultados y huellas de todos los objetos usados.

| Proyecto | Operación | Comprobación independiente |
|---|---|---|
| Cppcheck #103 | Su modelo C++ de plataformas comprueba qué tipos enteros con signo admiten diez valores del bloque 25437474 y seis valores frontera en Unix32, Unix64 y Win64. | 144 cotejos contra la codificación binaria de enteros con signo de Python. Tres magnitudes derivadas exceden cinco combinaciones de ABI y tipo. |
| CodeChecker #102 | Su modelo de informes y su implementación del identificador de diagnósticos agrupan las tres incompatibilidades anteriores con copias en que cambia la sangría. | Un segundo cálculo a partir de la ubicación, el texto y el mensaje reproduce las tres claves. Se conservan seis informes de entrada y tres identidades distintas. |
| SpotBugs #109 | Su XSD valida el descriptor de complementos que usa el clasificador de NQC. En las revisiones fijadas, el original de FindSecBugs sitúa `EngineRegistrar` antes de `Detector` y falla la validación. | JAXP acepta la copia que reordena ese nodo y conserva los 266 elementos. Rechaza también un CWE inválido y un identificador duplicado. La prueba se limita a la compatibilidad del descriptor con el XSD. |
| FindSecBugs #110 | La taxonomía de su detector aporta el CWE y la explicación que recibe el comparador de digest de Census. Las referencias provienen del registro de patrones, de la clase registrada y de sus mensajes. | El consumidor comprueba la expresión de Go en tres copias fijadas. Asigna el patrón MD5 a una y deja limpias las dos variantes SHA-2. |

Cppcheck y CodeChecker aportan ejecución de sus bibliotecas. SpotBugs y FindSecBugs aportan contratos y taxonomía de referencia. La incompatibilidad de la representación de enteros depende del tipo elegido por el consumidor. El control MD5 es una modificación deliberada. Hallazgos de seguridad originales confirmados por este perfil: 0.

## Reproducir

Se necesita Linux con Git, G++ compatible con C++17, Java con compilador de fuentes y JAXP, Python 3.12 y espacios de nombres de red sin privilegios habilitados. Cada compilador y proceso de proveedor se ejecuta con red aislada y archivos temporales. La lectura de las fuentes se limita a objetos Git de las cuatro revisiones fijadas. `NQC_UPSTREAM` debe señalar el directorio que contiene los checkouts `102-codechecker`, `103-cppcheck`, `109-spotbugs` y `110-find-sec-bugs`.

```sh
python3.12 -B -m unittest superhunter.tests.test_product_languages_batch
NQC_UPSTREAM=/ruta/a/upstream python3.12 -B - <<'PY'
import json, os
from pathlib import Path
from superhunter.product_languages_batch import canonical, review, sha
live = review(Path(os.environ['NQC_UPSTREAM']))
saved = json.loads(Path('superhunter/product_supply/languages-batch.json').read_bytes())
if live != saved:
    raise SystemExit('El recibo reproducido difiere del publicado')
print(sha(canonical(live)))
PY
```

En dos procesos de verificación del lote se obtuvo la huella canónica `d8646679ee267bffcfa4366b9910d2df0f1bc014a240de769d7ce053d4d09b96`. El módulo extrae los blobs del checkout en cada ejecución. Los binarios compilados son temporales. La revisión de obligaciones de redistribución del producto completo continúa pendiente.
