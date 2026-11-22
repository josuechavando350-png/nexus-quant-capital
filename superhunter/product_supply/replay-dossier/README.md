# Expedientes conservados de las ejecuciones 139 y 140

Este directorio reúne las entradas, registros y resultados que ya estaban conservados de **dos ejecuciones del perfil 139 y una del perfil 140**. Se creó después de las ejecuciones. Los envoltorios declaran `reconstructed_from_preserved_artifacts: true`; no se presentan como archivos `run-inputs.json` generados antes de lanzar el producto. No se ejecutaron de nuevo los motores al preparar este expediente.

| Perfil y ejecución | Productor Git | Participaciones | Operaciones | Respuestas | Bytes de salida | Duración registrada |
|---|---|---:|---:|---:|---:|---:|
| 139 A | `37a0d5261ae52ece080d18b294042931112f2861` | 139 | 149 | 222 | 1.249.365 | 426,81 s |
| 139 B | `37a0d5261ae52ece080d18b294042931112f2861` | 139 | 149 | 222 | 1.249.365 | 403,85 s |
| 140 A | `a183f60ed7229441a703a8f6ea9e180ff249abf3` | 140 | 150 | 222 | 1.255.491 | 412,74 s |

Cada ejecución conserva 20 alteraciones de evidencia rechazadas y cero grupos nativos o dominios bloqueados. Las dos salidas originales de 139 se compararon byte por byte. Su SHA-256 común es `0e7ceaab460f1b24826f466ad70d93b64201b4a2e7edf5e09b085f675f4cd318`. La salida de 140 tiene SHA-256 `88f7d4a092d9239f1d5e71df3e6132cffeeb95a1d0ab643cd106c5668bf9d2a7`.

## Qué contiene cada archivo

- [Índice](index.json): inventario con tamaño y SHA-256 de los siete archivos JSON de datos, productores y resultados por ejecución.
- [139 A](profile-139-run-a.json), [139 B](profile-139-run-b.json) y [140 A](profile-140-run-a.json): comandos, entorno, resultado del proceso, instrumentación, observaciones de recursos, stderr, comando del verificador y su resultado original.
- [Preparación 139](profile-139-preparation.json) y [preparación 140](profile-140-preparation.json): consultas exactas, manifiesto de kits, preflight, dependencias declaradas, contratos y registros previos de aceptación.
- [Fuentes de los lanzadores](runner-sources.json): bytes originales del lanzador diagnóstico y sus dos wrappers compartidos. Se conservan como texto; el expediente no los ejecuta.
- [Auditoría posterior](audit.json): tres verificaciones nuevas de las transcripciones existentes desde los checkouts productores exactos. Cada resultado coincide con el resultado de verificación original. Esta comprobación sólo lee evidencia; no agrega corridas del producto.

Dentro de `artifacts`, `content_utf8.encode('utf-8')` recupera los **bytes originales**, incluidos espacios y saltos de línea. Cada original tiene su propio tamaño, hash y ruta de procedencia. Los JSON originales no se parsearon y volvieron a serializar dentro de ese campo. Las rutas son las del entorno temporal donde se prepararon las ejecuciones; describen la procedencia y no son una configuración portátil.

Las transcripciones completas ya están en [native-session-139.json](../native-session-139.json) y [native-session-140.json](../native-session-140.json). Cada ejecución apunta al archivo correspondiente mediante el hash del contenedor y el hash de sus bytes descomprimidos. Se conservó una sola copia comprimida de 139 porque los dos archivos originales resultaron idénticos; esa deduplicación no modifica los comandos, tiempos, entornos ni registros separados de A y B.

## Cómo interpretar los registros sin cambiar su historia

`execution.json` conserva literalmente `independent_verifier_run: false`: el runner del producto no invocó al verificador independiente. Después se ejecutó el comando guardado en `verify-command.json`; su resultado se conserva en `verification.json`, con stderr vacío. La nueva comprobación de archivo se identifica por separado en `audit.json`.

El `preflight.json` conserva `PREPARED_NOT_EXECUTED`, `published_checkout_selected: false` y el árbol previo de preparación. Esos datos no certifican una corrida terminada. `command.json` y `execution.json` de cada corrida identifican el productor que realmente se seleccionó; la auditoría posterior cotejó ese commit y árbol contra Git y comprobó que los tres checkouts siguen limpios. Los hashes de consultas, kits, entorno, dependencias y contratos se cotejaron con el preflight preservado. Los contratos también coinciden con los blobs del productor publicado.

`instrumentation.json` diferencia el comando original y el comando efectivamente invocado con el lanzador diagnóstico. Éste ejecutó la entrada original del producto y añadió observación de `OSError` por stderr. Se preservan sus bytes y hashes para hacer visible esa instrumentación; no se la oculta bajo una afirmación de ejecución sin wrapper.

Las horas derivadas de `started_unix` proceden del reloj registrado por la instrumentación, sin autenticación externa. Los dos checkouts de 139 compartían host y dependencias preparadas. La consistencia de hashes y registros permite comprobar la integridad del expediente; **no constituye atestación independiente del host ni autenticación criptográfica del proceso productor**. No se afirma una segunda ejecución completa de 140, descubrimientos originales ni aumento del número de identidades integradas por publicar estos archivos.

## Comprobar integridad sin ejecutar los motores

Desde la raíz del repositorio, este lector comprueba el inventario, todos los originales embebidos y las transcripciones archivadas. Sólo usa JSON, SHA-256 y gzip; no lanza los comandos conservados.

```python
import base64
import gzip
import hashlib
import json
from pathlib import Path

root = Path.cwd()
dossier = root / 'superhunter/product_supply/replay-dossier'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
index = json.loads((dossier / 'index.json').read_bytes())
originals = 0

def check_original(value):
    global originals
    if isinstance(value, dict):
        if 'content_utf8' in value:
            raw = value['content_utf8'].encode('utf-8')
            assert value['encoding'] == 'utf-8'
            assert len(raw) == value['bytes']
            assert sha(raw) == value['sha256']
            originals += 1
        for nested in value.values():
            check_original(nested)
    elif isinstance(value, list):
        for nested in value:
            check_original(nested)

for item in index['files']:
    raw = (dossier / item['path']).read_bytes()
    assert len(raw) == item['bytes'] and sha(raw) == item['sha256']
    check_original(json.loads(raw))

for item in index['runs']:
    run = json.loads((dossier / item['dossier_file']).read_bytes())
    claim = run['transcript']
    raw = (root / claim['archive_repository_path']).read_bytes()
    assert len(raw) == claim['archive_bytes']
    assert sha(raw) == claim['archive_sha256']
    archive = json.loads(raw)
    transcript = gzip.decompress(base64.b64decode(archive['gzip_base64'], validate=True))
    assert sha(transcript) == claim['raw_sha256'] == archive['raw_sha256']
    assert len(transcript) == claim['raw_bytes'] == archive['raw_size']
    assert len(transcript.splitlines()) == claim['responses'] == 222

print({'dossiers': len(index['runs']), 'original_artifacts': originals,
       'integrity': 'PASS', 'product_executions_performed': 0})
```

Esta comprobación de integridad complementa el verificador semántico del producto. Los resultados semánticos y sus 20 controles negativos por ejecución están conservados en los expedientes, junto con el comando que los produjo.
