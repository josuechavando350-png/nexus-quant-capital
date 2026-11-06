# NQC Defense 0.11.0 — desarrollo en la rama NQC-defensive

El usuario autorizó publicar este código en `NQC-defensive` el 6 de noviembre de 2026. La rama conserva la base de NQC y no activa despliegues ni operación productiva. Los informes de 0.2.0 describen la validación previa a esa autorización.

Implementación funcional de una capa de admisión de artefactos locales. Lee bytes reales, comprueba su integridad y la de señuelos, consume credenciales de un uso, limita solicitudes, pone activos en cuarentena dentro de esta capa y produce auditoría autenticada exportable.

**No son 100 programas terminados.** Hay 8 implementaciones de alcance parcial vinculadas al catálogo original y 5 componentes adicionales ejecutables. Los otros programas solo están documentados en el catálogo; no hay clases vacías para representarlos. No se han implementado seL4, CHERI, enclaves, FHE ni sensores eBPF. Tampoco hay bloqueos de firewall, aislamiento de hosts, firma de operaciones financieras o despliegue.

La versión 0.9.0 conecta presupuestos persistentes de bytes lógicos y objetos con las escrituras del archivo. La política queda fijada por un hash externo; los escritores cooperantes se coordinan con un bloqueo del directorio, comprueban uso real y rechazan crecimiento que exceda el límite. Un reintento idéntico a capacidad completa no necesita otra copia temporal. Conserva el inventario de 0.8.0, la cobertura de 0.7.0, el archivo de 0.6.0 y los controles anteriores. Amplía la auditoría existente; no aumenta el número de programas del catálogo implementados.

## Protección operativa y catálogos nuevos

La versión 0.10.0 añade `ManagedIntegrity`: inicializa una copia JSON administrada, observa bytes reales, deriva el incidente de auditoría autenticada, bloquea el lector, restaura los dos archivos propios desde referencias fijadas y verifica una lectura posterior. La evidencia se archiva mediante una operación explícita. No modifica el archivo fuente ni conecta automáticamente consumidores productivos.

- [100 componentes operativos](docs/ARQUITECTURA_OPERATIVA_100.md): entradas, salidas, dependencias, candidatos tecnológicos, aceptación y estado.
- [100 disciplinas y especialidades](docs/DISCIPLINAS_100.md): responsables, entregables y comprobaciones.
- [Código y uso de la cadena local](docs/V0_10.md).

Este catálogo nuevo C001–C100 tiene 17 implementaciones parciales y 83 pendientes; ninguno alcanza todavía todo el alcance de su fila. No sustituye retrospectivamente las métricas del catálogo original M. Las conexiones de los componentes pendientes son requisitos, no integraciones ejecutables acreditadas.

## Autenticación y operación compartida

La versión 0.11.0 agrega un lector JSONL de autenticación con cursor transaccional, rotación explícita, regla de fallos repetidos y consulta común de eventos/casos. Importa el estado verificado de la cadena de integridad. No requiere ni modifica SuperHunter. [Uso, evaluación y límites](docs/V0_11.md); [plan de ejecución](docs/PLAN_EJECUCION.md).

La evaluación de nueve escenarios sintéticos expone un falso positivo y un falso negativo; sus métricas no se presentan como precisión productiva. Los registros inválidos y atrasados quedan visibles. La ingesta no ejecuta bloqueos de cuentas o red.

## Ejecutar y comprobar

Requisitos: Linux, Python 3.11 o posterior y biblioteca estándar. Git solo para comprobar la integración con NQC. No se requiere cuenta, suscripción, credencial de nube ni instalación de dependencias para estas instrucciones.

Desde esta carpeta:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/acceptance.py
```

La aceptación trabaja sobre una copia temporal del código real de `engine.py`: admite el original, detecta una modificación, rechaza liberarlo antes de restaurarlo, admite el archivo restaurado, reabre la base de datos y compara dos exportaciones byte por byte. No sustituye un servicio o hardware por un resultado fingido.

Para incorporar un archivo propio, `tools/init_local.py --help` explica las rutas requeridas. El inicializador calcula el hash de los bytes existentes, crea un señuelo nuevo y un directorio de control nuevo con configuración, clave de auditoría y SQLite. Nunca sobrescribe el artefacto. Si falla a mitad de creación, informa del fallo y deja los archivos nuevos para inspección; no borra directorios de forma automática.

`python3 -m nqc_defense --help` ofrece emisión local de tokens, inspección por entrada estándar, lectura JSON admitida (`read-json`), checkpoint, exportación, recuperación/reproducción de recibos y liberación local. El token no se pasa como argumento de línea de comandos. La emisión devuelve una credencial secreta: el operador debe conservarla en un canal privado. Ninguna ruta HTTP permite emitir credenciales, entregar contenido o liberar cuarentenas.

`ArtifactReader.read_json(request_bytes, token)` y el comando local `read-json` usan `Engine.admit_bytes`. El motor captura los bytes, comprueba el hash y registra `snapshot_authorized` ligado al recibo. Solo los devuelve cuando SQLite confirma la decisión y ese registro. El consumidor analiza ese mismo objeto de bytes con un límite de 1 MiB y 65.536 nodos; nunca reabre el nombre de archivo. Una denegación o fallo al confirmar no entrega contenido. Un fallo posterior del parser conserva el registro de autorización y consume el token: no afirma entrega ni ejecución del consumidor exactamente una vez. La salida local contiene el JSON admitido; debe manejarse según la sensibilidad del archivo.

`tools/verify_export.py --help` permite comprobar una exportación contra una clave, un digest de política y un checkpoint aportados por el operador. No extrae el ZIP ni ejecuta su contenido. La comprobación autentica registros y reproduce decisiones; no demuestra que un sensor externo diga la verdad.

Para historiales mayores, `Engine.export_page(start, target, limit=256, max_bytes=1048576)` produce un ZIP de una página. `start` es el checkpoint de la página anterior o el origen `{sequence: 0, head: 64 ceros}`; `target` es un checkpoint final fijado antes de recorrer. Cada página contiene hasta 512 registros nuevos; el límite de 1 MiB de JSON incluye también el registro anterior de contexto cuando corresponde. La CLI local `export-page` exige `--target` y acepta `--start`, `--limit` y `--max-bytes`. Crea el archivo exclusivamente; no sobrescribe una exportación existente.

`AuditPageVerifier.accept` comprueba cada página y avanza solo al pasar todas las verificaciones; `finish` exige llegar al checkpoint final. `tools/verify_audit_pages.py` aplica ese mismo recorrido a archivos ordenados, uno por vez, con clave y política suministradas por el operador. Las páginas faltantes, duplicadas, reordenadas o adulteradas impiden certificar el recorrido completo. Al reanudar desde un checkpoint distinto del origen, el informe declara `from_genesis: false`: verifica únicamente el intervalo solicitado.

`tools/witness_audit.py --help` ofrece `init`, `status` y `advance`. `init` crea exclusivamente una clave privada nueva y un directorio nuevo; necesita un directorio padre existente. El testigo queda ligado a la política y a la identidad de la clave de auditoría. `advance` exige páginas, un checkpoint final y el recibo esperado del testigo. Verifica las páginas antes de escribir y vuelve a comprobar el recibo bajo bloqueo SQLite: dos avances concurrentes no pueden sobrescribirse. La respuesta se devuelve después del commit e incluye revisión, hash del registro y checkpoint. Si la inicialización falla tras crear archivos, estos permanecen para revisión; no se eliminan automáticamente.

Para exigir el testigo, construir `Engine(..., witness=...)` o proporcionar juntos `--witness-root` y `--witness-key-file` a la CLI del motor. Debe vivir fuera del directorio de estado del motor y de sus padres. Se comprueba en emisión, admisión, lectura, liberación, consulta y exportación. Un testigo ausente o alterado produce rechazo; no se reconstruye ni se desactiva automáticamente. Los clientes existentes que no suministren testigo conservan el comportamiento anterior. `status --expected` compara contra un recibo que el operador haya retenido fuera del testigo.

`tools/archive_audit.py --help` ofrece `init`, `configure-budget`, `budget-status`, `prepare`, `verify`, `finalize`, `coverage`, `verify-coverage` e `inventory`. La API `ArchiveStore.capture(engine, witness, target, expected)` y el comando del motor `archive-audit` conectan exportación, archivo y testigo. Requieren un directorio de archivo inicializado, separado de los directorios de estado y testigo, además del checkpoint final y el recibo esperado. Las páginas se guardan en `pages/<sha256>.zip`; el manifiesto en `manifests/<sha256>.json`. Las rutas se derivan exclusivamente de hashes validados.

Cada archivo se escribe primero en un nombre temporal propio, se sincroniza con `fsync` y se publica mediante creación atómica sin reemplazo. Los objetos existentes solo se reutilizan si sus bytes coinciden. Si falla una escritura o una página no verifica, no se confirma el avance; pueden quedar páginas sin manifiesto o temporales de una interrupción para revisión posterior. La API no borra estos archivos ni historial. Por intervalo se aceptan hasta 4.096 páginas, 256 MiB de páginas y 1 MiB de manifiesto.

`finalize` relee las páginas del archivo y exige que formen el mismo intervalo y hash encadenado que registra el testigo. Puede recuperar una confirmación perdida, incluso después de otros avances, comprobando el registro histórico exacto y volviendo a leer los archivos. No modifica ni retrocede el checkpoint actual al recuperar una confirmación anterior. `--receipt-output` conserva el hash del manifiesto y el recibo mediante creación sin sobrescritura; un reintento idéntico reutiliza ese archivo.

`ArchiveCoverage.verify(manifests, start, target)` recorre los hashes de manifiestos en orden y exige correspondencia uno a uno con las revisiones autenticadas del testigo entre ambos recibos. `seal` publica un catálogo canónico `coverage-<sha256>.json` y lo relee; `verify_catalog` comprueba de nuevo el catálogo y todas sus páginas. La CLI `coverage --seal` y `verify-coverage` requieren `--start-receipt` y `--target-receipt`, además del almacén, política y claves. Estos dos archivos contienen recibos del testigo, no solamente checkpoints del motor, y deben conservarse por separado. Un catálogo no puede escoger por sí mismo qué intervalo se acredita.

La cobertura admite hasta 1.024 manifiestos, 16.384 páginas y 1 GiB de páginas por recorrido; el catálogo admite 256 KiB. Un sufijo declara `from_genesis: false`; un intervalo vacío solo verifica dos recibos iguales. La consulta copia el intervalo autenticado del testigo en una transacción y la libera antes de leer archivos, permitiendo avances posteriores. Al terminar vuelve a comprobar el recibo objetivo. Esta API recibe una lista explícita; el descubrimiento de objetos pertenece al inventario siguiente.

`ArchiveInventory.inspect(selections)` enumera exclusivamente la raíz del almacén, `pages` y `manifests`, con descriptores de directorio y sin seguir enlaces. Cada selección tiene exactamente `catalog_sha256`, `start_receipt` y `target_receipt`. El inventario vuelve a comprobar la cobertura seleccionada, produce referencias catálogo→manifiesto→página y mide objetos y bytes lógicos únicos. Los archivos fuera de la selección, desconocidos o temporales se contabilizan por metadatos; su contenido no se certifica. Una selección incompleta desactiva la clasificación de archivos no referenciados para evitar una conclusión falsa.

La CLI `inventory --selections archivo.json` consume una lista JSON de selecciones de hasta 64 KiB y exige política, clave de auditoría y directorio/clave del testigo. Devuelve JSON; código 0 cuando verifica la selección, 2 si hay referencias faltantes, errores de integridad o límites excedidos. El informe incluye las rutas faltantes, estadísticas por tipo, las referencias y un hash reproducible. No escribe el informe en el almacén ni modifica archivos. El hash permite comparar resultados, no es una firma pública.

Límites del inventario: 32 catálogos seleccionados, 20.000 archivos observados, 4 GiB de tamaños lógicos, 32.768 referencias y 16 MiB de informe. La verificación acumulada se limita a 16.384 lecturas de páginas y 1 GiB, contando de nuevo el trabajo compartido entre catálogos. Se rechazan enlaces simbólicos/duros, archivos especiales, directorios inesperados y permisos de grupo/otros. Dos recorridos de metadatos deben coincidir; si un escritor altera el archivo durante la consulta puede ser necesario repetirla. Estos límites no son cuotas de almacenamiento ni un snapshot atómico.

`ArchiveStore.configure_budget(max_logical_bytes, max_objects)` instala exclusivamente `archive-budget.json` y devuelve su `budget_digest`. Cuenta también la política, archivos previos, desconocidos y temporales. Rechaza presupuestos menores al uso existente; un reintento con los mismos límites recupera la instalación sin sobrescribirla. Para reabrir, usar `ArchiveStore(root, budget_digest=...)` con el digest retenido por separado. Una política presente obliga a suministrar ese pin para escribir, incluso en objetos abiertos antes de configurarla. Un escritor fijado rechaza política ausente, alterada o con otro hash. Los archivos sin política conservan la compatibilidad previa.

La CLI permite `init --max-bytes N --max-objects M`, o `configure-budget` con ambos límites para un almacén existente. `--budget-digest` es un argumento global, antes del subcomando, para reabrir escrituras y consultar `budget-status`. El comando del motor `archive-audit` recibe `--archive-budget-digest`. La lectura/verificación de evidencias sigue disponible sin activar escrituras. El estado informa uso, capacidad restante y si se cumplen ambos límites; si el uso externo supera el presupuesto, la CLI devuelve código 2 y se rechaza cualquier publicación.

Páginas, manifiestos y catálogos pasan por el mismo control. Bajo `flock` sobre el directorio real se relee la política, se enumera uso y se comprueba el incremento antes de crear el temporal. Un objeto idéntico se compara y sincroniza sin nueva copia. Cada publicación confirma nuevamente política y uso. El bloqueo tiene una espera máxima de cinco segundos y se libera al cerrar el descriptor o terminar el proceso. Un intervalo puede quedar parcialmente archivado si se agota presupuesto; no se publica un manifiesto completo ni se avanza el testigo sin todas sus páginas. No se borra evidencia para liberar espacio.

## Qué está conectado y ejecutado

| Componente | Implementación real | Límite explícito |
|---|---|---|
| M10 SOAR | Decisión, revocación de tokens y cuarentena SQLite en una transacción | Solo controla admisión a esta capa; no aísla procesos, hosts o wallets |
| M26 Canary | Creación exclusiva y detección de cambios/desaparición | No detecta lecturas ni bloquea discos |
| M33 CSP | Nonce criptográfico por respuesta y cabeceras WSGI | Probadas por HTTP local; no hay suite de navegador |
| M39 Rate limiter | Cuota por sujeto persistente y atómica | Ventana fija, sin aprendizaje conductual ni ralentización |
| M57 Identity | Tokens aleatorios ligados a activo, expiración y consumo único | Emisión por operador local; sin IdP federado |
| M67 Config | Almacén por SHA3-256 y digest fijado externamente | El operador debe proteger el anclaje y el almacenamiento |
| M75 Schema | Rechazo de campos extra de entrada/salida | Validación runtime; no macros ni prueba de compilación |
| M76 Build | ZIP determinista con hashes y verificador | Exportaciones de datos; no compilador de binarios reproducibles |
| X101 Evidence ledger | Cadena HMAC-SHA256, archivo local con presupuesto, cobertura, inventario y testigo separado con avances atómicos | Sin réplica independiente, anclaje remoto, ZK, consenso, firma pública ni resistencia a root |
| X102 Input guard | JSON limitado por bytes, profundidad y nodos; claves repetidas rechazadas | No rkyv ni parser universal |
| X103 Decision receipts | Hash de recibo, política, observaciones y comprobaciones ordenadas; reproducción independiente | Reproduce hechos registrados, no atestación de hardware |
| X105 Containment budget | Tope atómico de cuarentenas persistentes, también entre procesos | No limita tráfico ni garantiza disponibilidad; la solicitud sospechosa sigue rechazada |
| X106 Evidence expiry | Orden temporal, edad máxima de observación y piso de reloj persistido | Reloj local en segundos; sin fuente de tiempo independiente |

La ruta compartida es: entrada acotada → esquema → configuración anclada → transacción → reloj actual → token → cuota → repetición → observaciones reales → vigencia e integridad → presupuesto de cuarentena → recibo reproducible → decisión/cuarentena → auditoría → contrato de salida → confirmación SQLite. La inspección HTTP agrega cabeceras CSP. El consumidor local agrega la autorización del snapshot a la misma transacción y analiza sus bytes después de confirmar. La exportación comprueba HMAC, continuidad, checkpoint, reproducción de decisiones y vínculo de cada snapshot con su admisión inmediatamente anterior.

## Límites de confianza

- Los directorios de control, la clave HMAC, la configuración anclada y el proceso del operador son de confianza. Un administrador o proceso con el mismo usuario y acceso de escritura puede alterar estado o claves. Esta entrega no promete resistir ese compromiso.
- La cuarentena es una prohibición de admisión en este motor. Un proceso que ignore el motor puede seguir usando el archivo. El lector local nuevo exige admisión; el circuito productivo de Census todavía no lo usa.
- Una inspección es una observación puntual. Los descriptores rechazan enlaces simbólicos y archivos especiales, y comparan metadatos antes/después de leer. El lector local conserva los bytes inspeccionados aunque el archivo cambie después; no impide cambios posteriores en el disco ni protege consumidores que reabran la ruta por su cuenta.
- Una cadena HMAC válida no detecta por sí sola el borrado de su cola. El testigo local conserva un checkpoint fuera del estado del motor y detecta el retroceso de ese motor mientras el testigo permanezca intacto. El testigo también tiene una cadena HMAC; detectar el retroceso de su propia cola exige un recibo conservado por separado. No existe un servicio externo independiente de anclaje.
- La separación de directorios y claves no crea una frontera frente al mismo usuario o un administrador comprometido. Los directorios padre, el proceso y las claves son de confianza. El testigo solo cubre hasta su último checkpoint confirmado, y se avanza mediante una operación explícita. Los eventos posteriores necesitan un nuevo avance.
- El testigo de forma aislada acredita verificación de páginas, no su almacenamiento. La nueva ruta `ArchiveStore.capture/finalize` agrega escritura, sincronización y relectura local; el contenido del manifiesto queda ligado al intervalo y al hash encadenado de las páginas del testigo. El recibo no prueba disponibilidad futura, réplica independiente ni resistencia a pérdida del disco. No autoriza borrar historial; la retención sigue pendiente.
- El archivo es de creación exclusiva desde esta API, no un dispositivo WORM. Un usuario con control del directorio puede borrar o alterar archivos; `verify` y los reintentos lo comprueban cuando se ejecutan. No hay monitor continuo. Se han probado fallos de `fsync` mediante inyección explícita, no cortes eléctricos físicos ni controladoras que incumplan sincronización. El límite de 256 MiB es por intervalo, no una cuota global del directorio.
- La cobertura comprueba cada archivo durante el recorrido; no toma un snapshot atómico del sistema de archivos. No impide que un actor con escritura altere una página ya leída. Su resultado cubre únicamente los recibos externos fijados, no eventos posteriores ni disponibilidad futura. Los límites del recorrido no constituyen cuotas globales de disco. La verificación del testigo sigue siendo lineal con su historial.
- El inventario clasifica referencias únicamente respecto a los catálogos seleccionados. Otro catálogo, operador o proceso puede necesitar los objetos que queden fuera de esa selección. No se llaman huérfanos globales ni se autoriza su eliminación. Los bytes son tamaños lógicos de archivos regulares, no bloques físicos asignados. El contenido de objetos no seleccionados permanece sin verificar. La coincidencia de metadatos antes/después detecta cambios observados, pero no ofrece una instantánea atómica ni resistencia al administrador.
- El presupuesto limita escrituras cooperantes de esta API en el almacén local; no es una cuota del sistema operativo, reserva de bloques físicos o defensa frente a un administrador. No limita SQLite del motor/testigo, exportaciones externas ni archivos de otro directorio. Los límites máximos configurables son 4 GiB lógicos y 20.000 objetos. Directorios y metadatos del sistema de archivos no se contabilizan. No se han validado sistemas de archivos de red ni locks distribuidos.
- Durante la publicación atómica, el temporal y el nombre final comparten brevemente un inode, sin duplicar sus datos. Un cese antes del enlace deja un temporal regular que consume presupuesto. Un cese después del enlace y antes de retirar el temporal puede dejar dos nombres con enlace duro; el escáner los rechaza y exige revisión, sin limpieza automática. Los límites se comprueban antes y después de cada publicación, no son un límite estricto sobre nombres transitorios del directorio. Se probaron salidas abruptas de procesos, no pérdidas físicas de energía.
- La clave HMAC autentica para quienes comparten esa clave. No es una firma verificable públicamente. No se inventaron primitivas criptográficas.
- No hay sensor continuo: cada solicitud inspecciona el activo solicitado. No hay daemon 24/7, integración SIEM, alerta externa ni escalamiento automático.
- Las verificaciones de auditoría son lineales con el historial y SQLite serializa decisiones. Cada exportación paginada vuelve a verificar el ledger completo dentro de una transacción; el presupuesto también enumera el archivo en cada escritura. Estos controles acotan memoria y datos aceptados, pero añaden coste de CPU/E/S y espera entre escritores. Retención, rotación de claves, cuotas del sistema operativo y optimización incremental quedan pendientes.
- La vigencia usa reloj local con resolución de segundos. Detecta retrocesos observados y rechaza inspecciones cuya duración excede la política. No constituye sincronización de tiempo confiable frente a un administrador comprometido.
- El límite de cuarentenas solo acota transiciones persistentes en esta capa. Al agotarse, una petición con integridad alterada se rechaza sin crear otra cuarentena. No se admite el archivo para preservar el límite.
- El verificador de exportación completa admite hasta 8 MiB de auditoría, 10.000 registros y 100.000 nodos JSON. La alternativa paginada admite hasta 1 MiB de JSON y 512 registros nuevos por página; su verificador rechaza ZIPs mayores de 2 MiB. Un presupuesto que no alcanza para el contexto y el siguiente registro se rechaza explícitamente. Los registros históricos permanecen en SQLite; esta versión no borra ni compacta datos.
- El checkpoint final debe provenir del operador o de un anclaje confiable; copiarlo de una exportación no prueba completitud independiente. Un prefijo auténtico puede ser válido como página parcial, pero `finish` no lo acepta como recorrido completo. Los eventos posteriores al checkpoint fijado requieren otro recorrido.
- El hosting WSGI futuro deberá imponer TLS, límite de conexiones, lectura con timeout y framing HTTP correcto. Este paquete no abre puertos por sí mismo. La única escucha utilizada durante pruebas es loopback temporal.

## NQC y trabajo simultáneo

La base consultada fue `josuechavando350-png/nexus-quant-capital`, commit `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. La entrega se coloca como adición en `migration/defense/`, sin modificar Census ni recovered-source. El verificador de aislamiento existente permite adiciones bajo `migration/`; esa ubicación es una zona de preparación, no activación productiva.

`tools/check_nqc_base.py` verifica la base fijada o un descendiente que solo cambie `migration/defense/` y `migration/DEFENSE-INTEGRATION.md`, comprueba el blob del verificador original y ejecuta su validación completa. `tools/init_local.py --nqc-repo` exige ese control antes de crear estado. Un cambio fuera de esos límites requiere nueva revisión.

Se resolvió la descarga incompleta recuperando los 645 archivos de la revisión y verificando tamaño y hash de cada blob Git. El checkout base quedó limpio. Se añadieron únicamente `migration/defense/` y `migration/DEFENSE-INTEGRATION.md` a la copia local.

Pasaron el verificador de aislamiento original sobre la copia combinada, sus 9 pruebas y las 345 pruebas del paquete. `tools/check_nqc_artifact.py` inspeccionó los bytes reales de `nqc-census/Cargo.toml`. `tools/check_nqc_consumer.py .`, ejecutado desde la raíz NQC, consumió los 337.100 bytes reales de `migration/source-manifest.json`, archivó y releyó tres páginas antes del primer avance, realizó una segunda lectura exigiendo ese prefijo y archivó otras tres páginas hasta el registro 6. Los dos manifiestos se verificaron nuevamente y quedaron enlazados por un catálogo de cobertura desde el recibo inicial al final. El almacén se reabrió con presupuesto fijado de 1 MiB/64 objetos; el inventario y el estado del presupuesto coincidieron en diez objetos: política, catálogo, dos manifiestos y seis páginas. El manifiesto de NQC contiene 637 entradas históricas, no 637 módulos de defensa. Los controles crean y retiran un señuelo nuevo propio sin modificar los artefactos originales.

`tools/check_audit_pagination.py` verificó 10.003 registros en 20 páginas, superando el límite del formato de exportación completa. Son tres registros de admisión de una copia real de `engine.py` y 10.000 marcadores sintéticos explícitos para probar volumen con SQLite y HMAC reales. El control también añade un evento posterior al checkpoint y comprueba que no cambia el destino del recorrido. No representa tráfico productivo ni una medición de rendimiento.

`tools/check_witness.py` conserva un checkpoint de cuatro registros y elimina la cola solo de una base temporal de prueba. El prefijo restante de dos registros sigue teniendo HMAC válido; el motor con testigo lo rechaza sin consumir el token pendiente. También comprueba que un recibo retenido detecta la eliminación de la cola del propio testigo. Las pruebas de concurrencia y fallos de inserción/commit utilizan SQLite real.

`tools/check_archive.py` archiva una admisión de una copia real de `engine.py`, reabre y verifica el archivo, recupera la confirmación sin duplicar el avance y comprueba que una página alterada impide confirmar de nuevo su disponibilidad. El historial del motor permanece completo.

`tools/check_archive_coverage.py` sella tres intervalos reales con nueve registros/páginas; rechaza omitir el intervalo intermedio o final. Añade un cuarto intervalo y demuestra que el catálogo previo sigue válido para el objetivo original, pero no acredita el nuevo. Después altera una página temporal y comprueba que la verificación del catálogo detecta la corrupción.

`tools/check_archive_inventory.py` usa dos admisiones de una copia real de `engine.py`, dos catálogos superpuestos y un archivo temporal explícito con esos bytes fuente. Cuenta once objetos, seis páginas únicas y nueve referencias. Verifica que consultar conserve todos los bytes y checkpoints. Después elimina deliberadamente una página de ese almacén temporal de prueba y comprueba que se reporta su ruta y se desactiva la clasificación de referencias incompletas.

`tools/check_archive_budget.py` llena seis objetos con política, tres páginas, manifiesto y catálogo de una admisión real de código. Recupera el mismo archivo y catálogo a capacidad completa sin añadir objetos. Otra admisión genera registros nuevos, pero su archivo se rechaza por presupuesto: los bytes previos y el checkpoint del testigo permanecen intactos, y los registros nuevos permanecen en el motor pendientes de archivar.

**La incorporación al código y la comprobación local no equivalen a activar un consumidor productivo obligatorio.** No existe todavía ese enlace con la operación de Census. La certificación canónica sigue siendo falsa; no se verificó la historia Git del repositorio productor original. No se ejecutaron pruebas Rust de Census porque no se modificó su código. Tampoco se validó hardware externo.

## Archivos de seguimiento

- `docs/CATALOGO_100.md` y `docs/catalog_100.json`: correspondencia exacta con los 100 nombres del PDF, alcance corregido y pendientes individuales.
- `docs/PRIMEROS_10_Y_PROPUESTAS.md`: explicación de los primeros 10 y 10 propuestas de diseño.
- `docs/PRUEBAS.txt`, `docs/ACEPTACION.json` y `docs/VALIDACION.json`: resultados efectivamente obtenidos.
- `docs/CLOCK_LOCK_REGRESSION.json`: comparación ejecutada entre 0.1.0 y 0.2.0 con un bloqueo real de SQLite y reloj controlado.
- `docs/NQC_ARTIFACT_CHECK.json`, `docs/NQC_CONSUMER_CHECK.json`, `docs/NQC_ISOLATION.json` y `docs/NQC_ISOLATION_TESTS.txt`: validación de la incorporación local.
- `docs/AUDIT_PAGINATION_CHECK.json`: prueba de volumen paginado con marcadores sintéticos identificados.
- `docs/WITNESS_CHECK.json`: prueba local de retroceso del motor y comparación del recibo del testigo.
- `docs/ARCHIVE_CHECK.json`: archivo, relectura, recuperación de confirmación y detección de corrupción local.
- `docs/ARCHIVE_COVERAGE_CHECK.json`: continuidad entre intervalos, destino externo fijado y detección de archivos alterados.
- `docs/ARCHIVE_INVENTORY_CHECK.json`: objetos/referencias compartidos, tamaños lógicos, falta de páginas y conservación de archivos durante consultas.
- `docs/ARCHIVE_BUDGET_CHECK.json`: política fijada, capacidad completa, reintento sin crecimiento y rechazo sin avanzar el testigo.
- `docs/V0_2.md`, `docs/V0_3.md`, `docs/V0_4.md`, `docs/V0_5.md`, `docs/V0_6.md`, `docs/V0_7.md`, `docs/V0_8.md`, `docs/V0_9.md` y `docs/CONTINUIDAD.md`: cambios, compatibilidad y siguiente trabajo concreto.
- `docs/FUENTES.md`: fuentes primarias y distinciones respecto a las afirmaciones del PDF.

La publicación autorizada es únicamente de código en `NQC-defensive`. No se habilitan workflows, despliegues, envíos de correo ni ejecución productiva.
