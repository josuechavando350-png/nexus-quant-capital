# Contrato de tipos del lector de evidencia

En NQC, `read_json(path)` llama a `read_artifact(path.parent, path.name)` y entrega el resultado a `strict_json`. El control mide si ese consumidor puede enlazar los argumentos posicionales y si la firma declarada suministra tipos admisibles. Comprueba además que el lector real procesa el expediente del bloque 25437474 y que el decodificador rechaza `None`.

| Proyecto | Operación en el producto |
|---|---|
| #23 meta/Pysa | Se ejecutan sus funciones de descubrimiento de módulos y carga de AST. En cada caso seleccionan la implementación o la interfaz `.pyi` presente. Una interfaz inválida detiene ese caso aun cuando existe una implementación válida. |
| #22 Fraunhofer-AISEC/cpg | Se consumen dos definiciones fijadas del frontend Python. Los campos del AST y las reglas del manejador determinan cómo agrupar los parámetros posicionales y exclusivos de palabra clave. El resultado vincula los dos argumentos del lector real. Esta participación es de referencia. |
| #101 meta/infer | Se compila y ejecuta la biblioteca Java de aserciones de Infer con la API de anotaciones compilada desde los fuentes de su checkout. La biblioteca admite o rechaza los testigos tipados de cada argumento y del retorno. Los recibos identifican también las declaraciones del analizador para estos métodos. |

El procedimiento toma el archivo real de NQC y nueve interfaces controladas. Acepta cuatro casos, incluidos el cambio de nombre de un argumento posicional y la restricción a argumentos exclusivamente posicionales que este consumidor admite. Detecta el paso a argumento exclusivo de palabra clave, un tipo de origen incompatible, el retorno anulable, una anotación ausente, un parámetro ausente y una interfaz ilegible. Se contrasta cada decisión usando el enlazador de firmas de CPython, los tipos resueltos por su biblioteca estándar y los valores que originan los argumentos reales. El ensayo mide esta interfaz concreta. [Recibos y revisiones](product_supply/static-contracts.json)

## Reproducir

Se requieren Linux con espacios de nombres de red, Git, Python 3.12 y Java 21 con compilador. Los tres repositorios deben estar en la raíz de checkouts indicada. Los archivos temporales se eliminan al salir.

```sh
python3.12 -B -m unittest superhunter.tests.test_product_static_contracts
NQC_UPSTREAM=/ruta/a/upstream python3.12 -B - <<'PY'
import json, os
from pathlib import Path
from superhunter.product_static_contracts import canonical, review, sha
data = review(Path(os.environ['NQC_UPSTREAM']))
if data != json.loads(Path('superhunter/product_supply/static-contracts.json').read_bytes()):
    raise SystemExit('El contrato observado difiere del publicado')
print(sha(canonical(data)))
PY
```

La huella canónica es `0e2cc6e9c24e7cb0f6dfdad78758faa07a0a5ed870ff9870b3a07d68db3f2125`. Estas tres funciones acreditan compatibilidad de interfaces de NQC. Las ejecuciones se limitan a los componentes descritos en la tabla.
