# NQC y SuperHunter · evidencia de los 200 repositorios

El procedimiento de este documento reproduce el PR 112. La sesión ampliada incorpora Geth y dos comparaciones de tipos. [Reproducir las 211 respuestas](SOURCE_AUDIT.md) · [Matriz actual](INTEGRATION_STATUS_200.md).

La CLI de SuperHunter consulta los aportes de los 200 proyectos junto con las dependencias y las fuentes históricas de NQC. En la sesión de inventario, las 200 filas tienen una revisión Git, un documento de licencia verificado y un enlace al archivo exacto de origen. Al reconciliar el expediente del PR 111 con esta ejecución, 46 identidades tienen una función demostrada en el producto. De ellas, 42 aportaron código ejecutado y cuatro aportaron especificaciones o controles de referencia. Las otras 154 tienen procedencia documental verificada y su uso funcional sigue pendiente.

[Ver las 200 identidades, el documento de cada una y la procedencia de sus recibos](CATALOG_COVERAGE.md).

| Evidencia | Lote 1 | Lote 2 | Total |
|---|---:|---:|---:|
| Documentos de origen verificados en esta sesión | 100 | 100 | 200 |
| Función demostrada en el expediente previo | 38 | 0 | 38 |
| Identidades con función demostrada por primera vez en esta sesión | 3 | 5 | 8 |
| Identidades con recibo en esta sesión, incluidas las que se repitieron | 11 | 5 | 16 |
| Identidades distintas con función demostrada entre ambas sesiones | 41 | 5 | 46 |
| Uso funcional pendiente | 59 | 95 | 154 |

El expediente histórico corresponde al commit `d94b58f017a62d5e91c6794478c626e0b3435e8d`. La consulta `integration-coverage` devuelve las 200 filas e identifica el recibo anterior, su huella y el recibo obtenido en la sesión actual. `batch:1` y `batch:2` siguen informando exclusivamente de las herramientas y referencias que participaron en la sesión abierta. [Base del PR 111](https://github.com/josuechavando350-png/nexus-quant-capital/pull/111) · [Recibos anteriores](product_supply/coverage-d94b58f.json) · [Revisiones y documentos de los 200 proyectos](product_supply/upstream-notices.json)

## Resultados que comparten las herramientas

- **Documentos de licencia.** Los 200 proyectos aportan 144 textos distintos por contenido. Se seleccionó un archivo por identidad. En dirsearch se conserva la línea de licencia del manifiesto. En algunos monorepos se seleccionó el aviso de un componente. Cada fila devuelve la URL exacta y los ID de las demás filas con los mismos bytes. La selección documenta el archivo observado y deja abierta la evaluación jurídica del proyecto completo.
- **Búsqueda conjunta.** PMD comparó los 200 documentos con 14 avisos de dependencias de NQC y localizó 732 pasajes repetidos en 3,624 ubicaciones. Qdrant y Haystack indexaron los mismos 214 documentos y coincidieron en los 102 resultados de `notice:redistribution`. Cada resultado incluye el nombre y la huella del documento. Los archivos `upstream-NNN-license.txt` corresponden al ID original del catálogo.
- **Solidity de NQC.** Foundry 1.10.0 leyó cuatro perfiles. El lector de cabeceras de Wake 5.0.0 y el analizador sintáctico de solc 0.8.24 contrastaron 25 fuentes del manifiesto de migración. Doce tienen un perfil en su directorio o en un directorio padre. De las 21 importaciones distintas por fuente, ocho se resuelven en su ruta relativa y trece quedan abiertas en esa copia. Las cuatro configuraciones y las 25 filas también coincidieron con la prueba previa conservada fuera del producto. La integración sólo usa metadatos de estas fuentes.
- **Encabezado de Census.** EthereumJS reconstruyó el encabezado del bloque histórico 25,437,474 con su lector RPC local. ethers.js y viem codificaron los 21 campos tomados del lector Rust de NQC. Los tres obtuvieron los mismos 649 bytes RLP y el hash registrado en el archivo de prueba. Al aumentar una unidad el campo `gasUsed`, los tres obtuvieron el mismo hash alternativo y se rechazó la coincidencia con el original. El esquema de Prague en execution-specs comprobó el orden de los campos y cuáles eran cantidades. EIP-7685 aportó la referencia del compromiso para solicitudes vacías. La prueba comprueba el encabezado guardado. El cuerpo del bloque y su pertenencia actual a la cadena quedan fuera de su alcance. Los paquetes JavaScript comparten algunas dependencias.

## Reproducir desde el checkout

La preparación usa Linux x86-64, CPython 3.12 con pip y venv, Node, npm, Java, curl y util-linux con espacios de nombres de usuario, red y PID. En la ejecución registrada se usaron Node 24.22.3 y npm 11.19.1. Ejecutar en la raíz de NQC con una ruta nueva fuera del repositorio. La preparación descarga distribuciones fijadas, verifica los archivos y genera los expedientes de Syft, cvc5 e in-toto. La consulta posterior funciona sin red externa. Las respuestas son JSON, una por línea.

```sh
workspace="$(mktemp -d)/catalogo"
python3.12 -B -m superhunter.tools.catalog_session --prepare "$workspace" upstream-notices integration-coverage
```

La misma carpeta sirve para nuevas consultas. Una sesión abre los índices una vez y responde a todas las claves recibidas.

```sh
python3.12 -B -m superhunter.tools.catalog_session "$workspace" \
  foundry-rs/foundry ack3-ai/wake argotorg/solidity solidity-headers \
  ethers-io/ethers.js wevm/viem ethereumjs/ethereumjs-monorepo census-header \
  notice:redistribution batch:1 batch:2
```

Para reproducir las 208 respuestas usadas en la comprobación, consultar los 200 nombres en el orden de `repositories_200.json` y añadir las ocho claves mostradas. El SHA-256 de la transcripción de control es `4a4757ec107cd88dc698ae30cc62be7b93d651732279afffe2938d4074219f59`.

```sh
python3.12 - <<'PY' | python3.12 -B -m superhunter.tools.catalog_session "$workspace" > respuestas.jsonl
import json
from pathlib import Path

for row in json.loads(Path('superhunter/repositories_200.json').read_bytes())['entries']:
    print(row['repository'])
for key in ('batch:1', 'batch:2', 'upstream-notices', 'solidity-headers', 'notice:redistribution',
            'notice-overlaps:upstream-002-license.txt', 'census-header', 'integration-coverage'):
    print(key)
PY
sha256sum respuestas.jsonl
```

Para añadir estos aportes a otro expediente ya verificado, `query-product` acepta las opciones `--upstream-notices`, `--solidity-metadata-kit` y `--census-header-kit`. El inventario de procedencia compara SHA-256, el objeto Git del archivo descargado y la identidad registrada en NQC. El material histórico de PR 111 conserva la huella de sus 205 respuestas y la huella de cada línea con recibo. La consulta de cobertura cuenta cada identidad una vez. [Procedimiento de los otros productores del producto](PRODUCT_REVIEW.md)
