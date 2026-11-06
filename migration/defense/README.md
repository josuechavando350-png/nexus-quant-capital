# NQC Defense 0.4.0 — desarrollo en la rama NQC-defensive

El usuario autorizó publicar este código en `NQC-defensive` el 6 de noviembre de 2026. La rama conserva la base de NQC y no activa despliegues ni operación productiva. Los informes de 0.2.0 describen la validación previa a esa autorización.

Implementación funcional de una capa de admisión de artefactos locales. Lee bytes reales, comprueba su integridad y la de señuelos, consume credenciales de un uso, limita solicitudes, pone activos en cuarentena dentro de esta capa y produce auditoría autenticada exportable.

**No son 100 programas terminados.** Hay 8 implementaciones de alcance parcial vinculadas al catálogo original y 5 componentes adicionales ejecutables. Los otros programas solo están documentados en el catálogo; no hay clases vacías para representarlos. No se han implementado seL4, CHERI, enclaves, FHE ni sensores eBPF. Tampoco hay bloqueos de firewall, aislamiento de hosts, firma de operaciones financieras o despliegue.

La versión 0.4.0 añade auditoría por páginas acotadas y un verificador secuencial que exige alcanzar un checkpoint final fijado por el operador. Conserva el consumidor JSON conectado a la admisión de 0.3.0 y los recibos, presupuesto de cuarentenas, vigencia local y verificación de 0.2.0. Las páginas amplían la auditoría existente; no se cuentan como nuevos programas del catálogo.

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
| X101 Evidence ledger | Cadena HMAC-SHA256, checkpoint aportado y exportaciones completas o paginadas | Sin servicio de anclaje externo, ZK, consenso, firma pública ni resistencia a root |
| X102 Input guard | JSON limitado por bytes, profundidad y nodos; claves repetidas rechazadas | No rkyv ni parser universal |
| X103 Decision receipts | Hash de recibo, política, observaciones y comprobaciones ordenadas; reproducción independiente | Reproduce hechos registrados, no atestación de hardware |
| X105 Containment budget | Tope atómico de cuarentenas persistentes, también entre procesos | No limita tráfico ni garantiza disponibilidad; la solicitud sospechosa sigue rechazada |
| X106 Evidence expiry | Orden temporal, edad máxima de observación y piso de reloj persistido | Reloj local en segundos; sin fuente de tiempo independiente |

La ruta compartida es: entrada acotada → esquema → configuración anclada → transacción → reloj actual → token → cuota → repetición → observaciones reales → vigencia e integridad → presupuesto de cuarentena → recibo reproducible → decisión/cuarentena → auditoría → contrato de salida → confirmación SQLite. La inspección HTTP agrega cabeceras CSP. El consumidor local agrega la autorización del snapshot a la misma transacción y analiza sus bytes después de confirmar. La exportación comprueba HMAC, continuidad, checkpoint, reproducción de decisiones y vínculo de cada snapshot con su admisión inmediatamente anterior.

## Límites de confianza

- Los directorios de control, la clave HMAC, la configuración anclada y el proceso del operador son de confianza. Un administrador o proceso con el mismo usuario y acceso de escritura puede alterar estado o claves. Esta entrega no promete resistir ese compromiso.
- La cuarentena es una prohibición de admisión en este motor. Un proceso que ignore el motor puede seguir usando el archivo. El lector local nuevo exige admisión; el circuito productivo de Census todavía no lo usa.
- Una inspección es una observación puntual. Los descriptores rechazan enlaces simbólicos y archivos especiales, y comparan metadatos antes/después de leer. El lector local conserva los bytes inspeccionados aunque el archivo cambie después; no impide cambios posteriores en el disco ni protege consumidores que reabran la ruta por su cuenta.
- Una cadena HMAC válida no detecta por sí sola el borrado de su cola. Hay que guardar un checkpoint fuera del estado local. La API permite comprobar un checkpoint exacto al reabrir; no existe todavía un servicio externo de anclaje.
- La clave HMAC autentica para quienes comparten esa clave. No es una firma verificable públicamente. No se inventaron primitivas criptográficas.
- No hay sensor continuo: cada solicitud inspecciona el activo solicitado. No hay daemon 24/7, integración SIEM, alerta externa ni escalamiento automático.
- Las verificaciones de auditoría son lineales con el historial y SQLite serializa decisiones. Cada exportación paginada vuelve a verificar el ledger completo dentro de una transacción; acota el tamaño de los bloques y la memoria del recorrido, no elimina ese coste de CPU ni la espera de escritores. Retención, rotación de claves, cuotas de disco y optimización incremental quedan pendientes.
- La vigencia usa reloj local con resolución de segundos. Detecta retrocesos observados y rechaza inspecciones cuya duración excede la política. No constituye sincronización de tiempo confiable frente a un administrador comprometido.
- El límite de cuarentenas solo acota transiciones persistentes en esta capa. Al agotarse, una petición con integridad alterada se rechaza sin crear otra cuarentena. No se admite el archivo para preservar el límite.
- El verificador de exportación completa admite hasta 8 MiB de auditoría, 10.000 registros y 100.000 nodos JSON. La alternativa paginada admite hasta 1 MiB de JSON y 512 registros nuevos por página; su verificador rechaza ZIPs mayores de 2 MiB. Un presupuesto que no alcanza para el contexto y el siguiente registro se rechaza explícitamente. Los registros históricos permanecen en SQLite; esta versión no borra ni compacta datos.
- El checkpoint final debe provenir del operador o de un anclaje confiable; copiarlo de una exportación no prueba completitud independiente. Un prefijo auténtico puede ser válido como página parcial, pero `finish` no lo acepta como recorrido completo. Los eventos posteriores al checkpoint fijado requieren otro recorrido.
- El hosting WSGI futuro deberá imponer TLS, límite de conexiones, lectura con timeout y framing HTTP correcto. Este paquete no abre puertos por sí mismo. La única escucha utilizada durante pruebas es loopback temporal.

## NQC y trabajo simultáneo

La base consultada fue `josuechavando350-png/nexus-quant-capital`, commit `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. La entrega se coloca como adición en `migration/defense/`, sin modificar Census ni recovered-source. El verificador de aislamiento existente permite adiciones bajo `migration/`; esa ubicación es una zona de preparación, no activación productiva.

`tools/check_nqc_base.py` verifica la base fijada o un descendiente que solo cambie `migration/defense/` y `migration/DEFENSE-INTEGRATION.md`, comprueba el blob del verificador original y ejecuta su validación completa. `tools/init_local.py --nqc-repo` exige ese control antes de crear estado. Un cambio fuera de esos límites requiere nueva revisión.

Se resolvió la descarga incompleta recuperando los 645 archivos de la revisión y verificando tamaño y hash de cada blob Git. El checkout base quedó limpio. Se añadieron únicamente `migration/defense/` y `migration/DEFENSE-INTEGRATION.md` a la copia local.

Pasaron el verificador de aislamiento original sobre la copia combinada, sus 9 pruebas y las 148 pruebas del paquete. `tools/check_nqc_artifact.py` inspeccionó los bytes reales de `nqc-census/Cargo.toml`. `tools/check_nqc_consumer.py .`, ejecutado desde la raíz NQC, consumió los 337.100 bytes reales de `migration/source-manifest.json` a través del lector, reprodujo el recibo y verificó tanto la exportación completa como tres páginas de auditoría. El manifiesto contiene 637 entradas históricas, no 637 módulos de defensa. Ambos controles crean y retiran un señuelo nuevo propio sin modificar los artefactos originales.

`tools/check_audit_pagination.py` verificó 10.003 registros en 20 páginas, superando el límite del formato de exportación completa. Son tres registros de admisión de una copia real de `engine.py` y 10.000 marcadores sintéticos explícitos para probar volumen con SQLite y HMAC reales. El control también añade un evento posterior al checkpoint y comprueba que no cambia el destino del recorrido. No representa tráfico productivo ni una medición de rendimiento.

**La incorporación al código y la comprobación local no equivalen a activar un consumidor productivo obligatorio.** No existe todavía ese enlace con la operación de Census. La certificación canónica sigue siendo falsa; no se verificó la historia Git del repositorio productor original. No se ejecutaron pruebas Rust de Census porque no se modificó su código. Tampoco se validó hardware externo.

## Archivos de seguimiento

- `docs/CATALOGO_100.md` y `docs/catalog_100.json`: correspondencia exacta con los 100 nombres del PDF, alcance corregido y pendientes individuales.
- `docs/PRIMEROS_10_Y_PROPUESTAS.md`: explicación de los primeros 10 y 10 propuestas de diseño.
- `docs/PRUEBAS.txt`, `docs/ACEPTACION.json` y `docs/VALIDACION.json`: resultados efectivamente obtenidos.
- `docs/CLOCK_LOCK_REGRESSION.json`: comparación ejecutada entre 0.1.0 y 0.2.0 con un bloqueo real de SQLite y reloj controlado.
- `docs/NQC_ARTIFACT_CHECK.json`, `docs/NQC_CONSUMER_CHECK.json`, `docs/NQC_ISOLATION.json` y `docs/NQC_ISOLATION_TESTS.txt`: validación de la incorporación local.
- `docs/AUDIT_PAGINATION_CHECK.json`: prueba de volumen paginado con marcadores sintéticos identificados.
- `docs/V0_2.md`, `docs/V0_3.md`, `docs/V0_4.md` y `docs/CONTINUIDAD.md`: cambios, compatibilidad y siguiente trabajo concreto.
- `docs/FUENTES.md`: fuentes primarias y distinciones respecto a las afirmaciones del PDF.

La publicación autorizada es únicamente de código en `NQC-defensive`. No se habilitan workflows, despliegues, envíos de correo ni ejecución productiva.
