# Verificación defensiva de fuentes en NQC

El punto de partida es el commit de producto `ae02690627443df08b8eedb9d63a7a30cbda6c0e`. Los primeros 153 submódulos y sus revisiones se conservan. En el lote de los 47 restantes se verificaron todos los objetos de árbol raíz y se consumieron 34 manifiestos desde sus blobs. Dos proyectos aportan además extractos de fuente con licencia y un consumidor ejecutado. Las consultas `root-declarations` y `owned-source-checks` comparten las identidades del producto. [Árboles y declaraciones](REMOTE_ROOTS.md) · [Origen de los extractos](product_supply/source-excerpts/ORIGINS.md)

| Proyecto | Entrada y consumidor | Control comprobado |
|---|---|---|
| PyCQA/Bandit | El analizador B506 de Bandit 1.9.4 procesa el lector de políticas YAML de NQC. Los 69 archivos Python de la distribución coinciden con los blobs del submódulo. | `safe_load` y `SafeLoader` explícito se aceptan. La copia que usa `load` sin seleccionar cargador produce un diagnóstico en la línea 127. Sólo se analiza la sintaxis. |
| SmartBugs | La función original `result_region` recibe las coordenadas de Bandit y las incorpora a un resultado SARIF 2.1.0 que devuelve la consulta. | La región empieza en la columna 20 y termina en la 33. Un lector independiente coteja la línea con el AST de Python y los caracteres exactos en la fuente. |
| OpenSSF malicious-packages | Un árbol fijado de 12,065 nombres de PyPI se contrasta con los 38 nombres y 39 pares nombre/versión declarados por NQC. | Cero coincidencias de nombre en ese conjunto y revisión. Un registro OSV publicado distingue una versión que figura y otra que no figura. El proceso lee metadatos y no adquiere paquetes descritos en los avisos. |
| Crytic building-secure-contracts | Dos cláusulas originales sobre tipos de retorno se combinan con las declaraciones de NQC, el AST de solc y la interfaz IERC20 de OpenZeppelin. | Las tres declaraciones se ajustan a las cláusulas. Se detectan exactamente dos diferencias al alterar `decimals` y `transfer` en memoria. |

Los 47 proyectos siguen sin checkout completo. Entre ellos, SmartBugs aporta código de biblioteca y Crytic aporta una referencia documental. Los otros 45 mantienen alcance de metadatos en este lote. Las herramientas de intrusión y los laboratorios de explotación permanecen fuera del flujo autónomo. El registro de una dependencia o un aviso por sí solo no acredita una herramienta. La revisión comercial integral y la evaluación externa ciega de descubrimiento siguen pendientes.

## Reproducir

Usar Linux x86-64 y CPython 3.12. Partir de un checkout con los 153 submódulos, una [sesión estándar preparada y el comparador de Geth reproducible](SOURCE_AUDIT.md). Los comandos de preparación requieren rutas nuevas. Los procedimientos comprueban los objetos Git y los hashes de los wheels antes de usarlos.

```sh
python3.12 -B -m superhunter.tools.fetch_root_manifests "$work/manifests"
python3.12 -B -m superhunter.tools.prepare_owned_source_checks "$work/owned"
python3.12 -B -m superhunter.tools.catalog_session --source-inventory --source-references "$root" \
  --root-manifests "$work/manifests" --owned-source-kit "$work/owned" \
  --geth-header "$work/geth-header" "$work/product" root-declarations owned-source-checks integration-matrix
```

La matriz Markdown se puede regenerar con los mismos argumentos de la sesión. El renderizador abre la sesión, exige los recibos y devuelve un error si un productor falla. La salida de la ejecución se puede cotejar antes de reemplazar la matriz publicada.

```sh
python3.12 -B -m superhunter.tools.render_product_matrix --source-inventory --source-references "$root" \
  --root-manifests "$work/manifests" --owned-source-kit "$work/owned" \
  --geth-header "$work/geth-header" "$work/product" > "$work/matrix.md"
cmp "$work/matrix.md" superhunter/INTEGRATION_STATUS_200.md
```
