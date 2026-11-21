# Preparar y verificar fuentes con menos trabajo repetido

La rama de producto incorpora el trabajo del [PR 116](https://github.com/josuechavando350-png/nexus-quant-capital/pull/116) sobre `672c31392929b8efbd6b3d5983c44e8560232add`. El PR original se midió sobre `ae02690627443df08b8eedb9d63a7a30cbda6c0e`. El nuevo lector conserva las consultas y entradas nativas introducidas por los PR 115 y 117.

## Cambios ejecutables

1. `product-sources --jobs 4` comprueba checkouts y árboles Git con hasta cuatro
   trabajadores. Acepta de uno a ocho; uno conserva el modo serial. Antes de
   iniciar los trabajadores valida el manifiesto completo, el catálogo, las
   rutas y el índice del superproyecto. Conserva las comprobaciones de HEAD,
   árbol, índice y archivos rastreados. Un fallo impide emitir el inventario.
2. `scan_session(release)` verifica y extrae ScanCode una vez por inventario.
   Cada lote mantiene entradas, HOME y reporte nuevos. La sesión sirve también
   al aviso resuelto desde un enlace Git. El aislamiento sin red, la validación
   de resultados y la limpieza al terminar o fallar permanecen activos.
3. `catalog_session --prepare --download-cache RUTA` reutiliza los diez
   archivos fijados en `ASSETS`. Cada copia vuelve a comprobar su SHA-256.
   Publica solo archivos completos; una copia de sesión no comparte su inode
   con la caché. Una entrada corrupta o enlazada falla sin aceptarla.

La caché es opcional, externa y separada de la sesión. No incluye wheels,
dependencias npm, los 200 avisos, resultados ni recibos. Un fallo posterior
elimina la sesión incompleta y conserva los assets ya verificados en caché.
Si dos preparaciones necesitan el mismo contenido, un bloqueo por SHA-256 permite que una sola lo descargue. Cada lector verifica su copia y cada digest diferente puede progresar en paralelo. Los archivos vacíos `.lock-<digest>` permanecen en el directorio de caché para conservar el mismo bloqueo entre procesos y reintentos.

## Ensayo sobre la rama de producto

El [recibo de producto](product_supply/acceleration-product-replay.json) registra la comparación de checkouts, el inventario, las entradas de caché, los lotes de ScanCode y las pruebas ejecutadas sobre esta base. El recibo anterior se conserva como evidencia histórica del PR 116.

Al restaurar el almacenamiento o verificarlo desde otro espacio de usuarios, Git puede observar diferencias de metadatos del sistema de archivos para un archivo que conserva su contenido. Para esas rutas el verificador calcula el identificador del blob desde los bytes reales, comprueba el modo Git y trata los enlaces por su texto. Un repositorio Git temporal reconstruye las representaciones `eol=crlf` e `ident` a partir de los atributos del commit, incluido el identificador de blob expandido en el archivo. El repositorio temporal solo comparte objetos y emplea configuración vacía. El cálculo trabaja por bloques y conserva el índice compartido. Las pruebas introducen cambios de contenido del mismo tamaño, alteraciones de permisos, eliminación, sustitución de un enlace y una expansión parcial de finales de línea.

El escáner procesó los textos únicos con una sola preparación de ScanCode. La comprobación de caché materializó los diez archivos del catálogo en un espacio sin red y cotejó sus SHA-256 en copias independientes.

## Mediciones originales del PR 116

| Operación | Antes / serial | Después | Comprobación |
|---|---:|---:|---|
| Verificar los 153 checkouts | 16.5642 s, un trabajador | 3.9044 s, cuatro trabajadores | 76.43% menos tiempo; JSON canónico idéntico |
| ScanCode real, 60 avisos en dos lotes de 30 | 59.5177 s, preparación por lote | 38.7993 s, preparación compartida | 34.81% menos tiempo; resultados normalizados idénticos |
| Inventario de árboles sin escaneo de licencias | No se repitió medición serial | 16.4400 s, cuatro trabajadores | 153 árboles y 47 registros remotos iguales al snapshot revisado |

Son mediciones locales de una pasada, con Python 3.12.14 en el mismo equipo.
La caché del sistema y la actividad de otras tareas no estaban controladas.
Estos porcentajes no estiman cuánto tardarán todas las integraciones restantes.
El ensayo de ScanCode cubrió los primeros 60 textos distintos de los 144 del
corpus; no volvió a ejecutar la auditoría completa de las 200 identidades.

El inventario se comparó con `source-inventory.json` de la base, quitando solo
`notice_scan`, `resolved_notice_scan` y `notice_producer`, y recalculando
`entries_sha256`. No se eliminaron observaciones de árboles o procedencia.
El [recibo de revisión](product_supply/acceleration-review.json) conserva
tiempos, hashes de resultados, hashes de implementación y límites.

Otra tarea avanzó el checkout original durante el baseline de ScanCode. Se
comprobó que el escáner, corpus, `safe_io` y las funciones utilizadas `sha` y
`copy_release` coincidían con la base; los cambios eran rutas de producto no
usadas. Los módulos ya importados siguieron residentes. Las mediciones de
checkouts e inventario tuvieron hashes de código estables durante la ejecución.

## Uso por Astra

Los comandos aceptan los checkouts ya materializados que corresponden a la revisión fijada.

Desde un checkout con los submódulos inicializados:

```sh
python -B -m superhunter product-sources --require-checkout --jobs 4
python -B -m superhunter product-sources --inventory --jobs 4
```

La auditoría con licencias usa automáticamente la sesión compartida:

```sh
python -B -m superhunter product-sources --inventory --jobs 4 \
  --notice-bundle "$NOTICE_BUNDLE" --scancode-release "$SCANCODE_RELEASE"
```

Para preparar una sesión nueva y conservar descargas para reintentos, definir
`SESSION_DIR` como una ruta nueva y `DOWNLOAD_CACHE` como otra carpeta externa
al checkout. Ninguna debe contener a la otra:

```sh
python -B -m superhunter.tools.catalog_session --prepare \
  --download-cache "$DOWNLOAD_CACHE" "$SESSION_DIR" integration-coverage
```

Las preparaciones siguientes reutilizan la misma caché y una nueva ruta de
sesión. Las instrucciones completas de entradas fijadas y herramientas están
en [SOURCE_AUDIT.md](SOURCE_AUDIT.md) y [CATALOG_SESSION.md](CATALOG_SESSION.md).
La falta de un asset en caché requiere descargarlo desde su origen fijado.

## Reproducir la equivalencia de checkouts

Usar `DATA_CHECKOUT` para el checkout con las fuentes materializadas. Este
ejemplo ejecuta ambos modos de forma consecutiva; no descarga ni ejecuta
código de esos repositorios:

```sh
python -B - "$DATA_CHECKOUT" <<'PY'
import hashlib
from pathlib import Path
import sys
import time
from superhunter.product_sources import verify
from superhunter.safe_io import canonical
results = []
for jobs in (1, 4):
    start = time.perf_counter()
    raw = canonical(verify(Path(sys.argv[1]), require_checkout=True, jobs=jobs))
    print(jobs, time.perf_counter() - start, hashlib.sha256(raw).hexdigest())
    results.append(raw)
assert results[0] == results[1]
PY
```

Para repetir ScanCode, seleccionar los primeros 60 documentos únicos por
SHA-256 de `verified_corpus`, en orden de catálogo, y formar dos lotes de 30.
Ejecutar `scan(release, lote)` en un checkout inmutable de la base para cada
lote; en este cambio ejecutar ambos lotes dentro de un mismo
`with scan_session(release) as scanner`. Comparar el JSON canónico de las dos
listas de resultados. Los temporizadores incluyen preparación y limpieza.

## Validación original del PR 116

Pasaron 85 pruebas focalizadas de ocho módulos: los cuatro nuevos de caché,
sesión de licencia, checkouts e inventario paralelo, y los existentes
`test_product_supply`, `test_product_source_audit`,
`test_product_catalog_session` y `test_repository_boundary`.
El verificador de límites confirmó los 642 archivos históricos.

La suite histórica de migración pasó sus nueve casos en su ámbito original.
Ejecutada sobre todo el árbol ampliado de producto produjo ocho PASS y un
error `unreviewed root file`; el mismo caso falla en la base sin cambios.
No se modificó ese verificador ni se presentaron sus resultados como una
aceptación del producto ampliado. Esa comprobación la realiza por separado
`repository_boundary`.

Las pruebas de fallos del ciclo de ScanCode usan un productor simulado y no
acreditan ejecución nativa; esta se comprobó por separado en la medición de
60 avisos. No se repitieron la QA global de SuperHunter, las pruebas Rust
(su código no cambia) ni una preparación completa con descargas de red.
Este cambio añade cero integraciones funcionales de repositorios y acredita
cero vulnerabilidades originales: reduce el costo de verificar el trabajo.
