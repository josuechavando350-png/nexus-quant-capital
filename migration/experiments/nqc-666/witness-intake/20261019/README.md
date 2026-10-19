# NQC 666 — revisión de testigos, 19 de octubre de 2026 UTC

**No se recibió un testigo auténtico compatible.** R5 permanece predeterminado;
R7 permanece experimental. Esta entrega registra la revisión de insumos y no
crea R8, modifica el motor ni declara una mejora de rendimiento.

Base inspeccionada: `41a354e604f1ecef50a4a31b3f1a7210b419f3ba`.
`main` observado: `16e352225ba8a6a931834c4edf3d86d9a2924b7d`.

## Qué se comprobó

Se verificaron localmente los tamaños y SHA256 de los **257 archivos** incluidos
en los manifiestos de dos entregas técnicas. No hubo entradas duplicadas ni
archivos adicionales fuera de sus respectivos manifiestos y del propio
`MANIFEST.json`. Se preservan aquí ocho documentos originales, sin modificaciones.
Los hashes comprueban integridad del paquete; no autentican blockchain.

| Entrega | Archivos verificados | Datos de estado declarados | Resultado para NQC 666 |
|---|---:|---|---|
| NQC032 R4 | 49 | 71 valores observados, 11 faltantes; 0 pruebas de cuenta y storage verificadas | No es testigo auténtico; usa un paquete anterior de NQC031 |
| NQC031 contratos exactos y bloqueo histórico | 208 | 82 lecturas cubiertas, 0 autenticadas; 0 nodos de prueba recibidos; raíz pretransacción null | Avance de reproducción de código, sin desbloqueo de estado |

El archivo NQC031 actual fue publicado después de la primera inspección de esta
sesión y se incorporó a esta revisión. Sus diagnósticos de constructores y código
se leen como evidencia del productor: aquí no se recompilaron contratos ni se
repitió la auditoría NQC032. La diferencia 71/82 no es una regresión: NQC032 R4
consumió el archivo `6f5e67ce8f1ab7504366a1abb36ece43ffbe2739804b6176e817e2156c92873d`,
anterior a la recuperación de once valores por eventos. Valores recuperados y
bytes de código reproducidos siguen siendo distintos de pruebas históricas.

Ambas entregas se refieren a chainId **4663**, bloque **66744162**, antes de
txIndex **1**. La interfaz R5 corresponde a chainId **1**, estado al **final del
bloque**. No se adaptaron etiquetas, no se rellenaron valores desconocidos y no
se sustituyó la raíz intermedia por la del bloque padre o la del bloque final.

La búsqueda acotada en los archivos disponibles, la rama NQC666 y documentación
pública estática no encontró otro paquete utilizable. Esto no prueba que no
exista uno en otra fuente. No se reintentó el RPC que devolvió 403, no se cambió
de endpoint para eludirlo y no se renovaron cuotas de otro frente.

## Reproducción de esta revisión

Desde este directorio:

```sh
sha256sum --check SHA256SUMS
```

Para verificar también todos los archivos de los ZIP originales, conservados
por su propietario, indique las rutas en el orden siguiente. Solo se leen datos;
no se extraen ni ejecutan scripts de los paquetes. Se requiere Python estándar.

```sh
python - /ruta/NQC032_R4.zip /ruta/NQC_031_R2_CONTRATOS_EXACTOS_Y_BLOQUEO_HISTORICO.zip <<'PY'
import hashlib, json, sys, zipfile
from pathlib import Path, PurePosixPath

record = json.loads(Path('INTAKE.json').read_text())
assert len(sys.argv) == 3
for path, item in zip(sys.argv[1:], record['archives']):
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == item['archive_sha256']
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        root = item['archive_root'] + '/'
        manifest = json.loads(archive.read(root + 'MANIFEST.json'))
        entries = manifest['files']
        assert len(entries) == item['manifest_files_verified']
        paths = [entry['path'] for entry in entries]
        assert len(paths) == len(set(paths))
        assert set(names) == {root + p for p in paths} | {root + 'MANIFEST.json'}
        for entry in entries:
            relative = PurePosixPath(entry['path'])
            assert not relative.is_absolute() and '..' not in relative.parts
            data = archive.read(root + entry['path'])
            assert len(data) == entry['bytes']
            assert hashlib.sha256(data).hexdigest() == entry['sha256']
        for relative, expected in item['selected_originals'].items():
            data = archive.read(root + relative)
            assert data == (Path(item['reference_directory']) / relative).read_bytes()
            assert len(data) == expected['bytes']
            assert hashlib.sha256(data).hexdigest() == expected['sha256']
    print(item['name'], len(entries), 'INTEGRITY_PASS_NOT_STATE_AUTHENTICATION')
PY
```

Se ejecutaron el verificador de aislamiento y sus nueve pruebas; los registros
se conservan en `evidence/`. No hay código de motor afectado. No se repitieron
pruebas Python/Rust del motor ni benchmarks: los resultados R5/R6/R7 anteriores
conservan su alcance original y no se convierten en mediciones de estado real.

## Dependencia concreta para continuar

Hace falta **un paquete Ethereum de una posición Morpho identificada**, con:

1. Encabezado completo y evidencia independiente de su anclaje canónico, al
   final de un bloque fijado por hash.
2. Prueba de cuenta desde `stateRoot`, runtime cuyo Keccak coincida con el
   `codeHash` probado y pruebas de los nueve slots que R5 deriva para ese
   mercado/borrower. Las ausencias requieren prueba; no se inventan ceros.
3. Respuestas crudas, solicitudes, tiempos y procedencia, junto con una política
   independiente. Una etiqueta de autenticación no reemplaza las pruebas.
4. Para el recorrido completo, dependencias auténticas del oráculo/IRM y contexto
   de ejecución que permitan validar precio, intereses, vigencia y candidato.

El formato ya existe en [WITNESS_REQUIREMENTS](../../r6-witness-ingress/WITNESS_REQUIREMENTS.md)
y el importador R6 genera las solicitudes exactas **sin enviarlas**. R7 puede
reproducir una captura local con R5 mediante su `scripts/replay_capture.py`.
No se pide repetir financiación ni reconstrucción de contratos de otros frentes.
El objetivo Nitro de NQC031 requiere su propio anclaje y prefijo histórico; no se
presenta ese trabajo como compatible con R5 ni se lo duplica aquí.

Al disponer del paquete, el orden de aceptación sigue siendo: autenticar raíz y
contexto, verificar cuenta/código/storage, validar dependencias y ejecución,
reproducir decisiones y rechazos, medir la ruta offline completa con muestras
individuales y comparar medianas/p95/p99/p99.9/máximo. Red, builder e inclusión
seguirán siendo alcances separados. Ninguna operación queda autorizada por este
registro y **la estabilización integral permanece sin demostrar**.
