# NQC Defense 0.2.1 — desarrollo en la rama NQC-defensive

El usuario autorizó publicar este código en `NQC-defensive` el 6 de noviembre de 2026. La rama conserva la base de NQC y no activa despliegues ni operación productiva. Los informes de 0.2.0 describen la validación previa a esa autorización.

Implementación funcional de una capa de admisión de artefactos locales. Lee bytes reales, comprueba su integridad y la de señuelos, consume credenciales de un uso, limita solicitudes, pone activos en cuarentena dentro de esta capa y produce auditoría autenticada exportable.

**No son 100 programas terminados.** Hay 8 implementaciones de alcance parcial vinculadas al catálogo original y 5 componentes adicionales ejecutables. Los otros programas solo están documentados en el catálogo; no hay clases vacías para representarlos. No se han implementado seL4, CHERI, enclaves, FHE ni sensores eBPF. Tampoco hay bloqueos de firewall, aislamiento de hosts, firma de operaciones financieras o despliegue.

Esta versión añade recibos reproducibles de decisión (X103), un presupuesto de cuarentenas persistentes (subconjunto de X105), vigencia de evidencia local (subconjunto de X106) y un verificador independiente de exportaciones. Corrige además la lectura prematura del reloj antes de adquirir el bloqueo de SQLite.

## Ejecutar y comprobar

Requisitos: Linux, Python 3.11 o posterior y biblioteca estándar. Git solo para comprobar la integración con NQC. No se requiere cuenta, suscripción, credencial de nube ni instalación de dependencias para estas instrucciones.

Desde esta carpeta:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/acceptance.py
```

La aceptación trabaja sobre una copia temporal del código real de `engine.py`: admite el original, detecta una modificación, rechaza liberarlo antes de restaurarlo, admite el archivo restaurado, reabre la base de datos y compara dos exportaciones byte por byte. No sustituye un servicio o hardware por un resultado fingido.

Para incorporar un archivo propio, `tools/init_local.py --help` explica las rutas requeridas. El inicializador calcula el hash de los bytes existentes, crea un señuelo nuevo y un directorio de control nuevo con configuración, clave de auditoría y SQLite. Nunca sobrescribe el artefacto. Si falla a mitad de creación, informa del fallo y deja los archivos nuevos para inspección; no borra directorios de forma automática.

`python3 -m nqc_defense --help` ofrece emisión local de tokens, inspección por entrada estándar, checkpoint, exportación, recuperación/reproducción de recibos y liberación local. El token no se pasa como argumento de línea de comandos. La emisión devuelve una credencial secreta: el operador debe conservarla en un canal privado. Ninguna ruta HTTP permite emitir credenciales o liberar cuarentenas.

`tools/verify_export.py --help` permite comprobar una exportación contra una clave, un digest de política y un checkpoint aportados por el operador. No extrae el ZIP ni ejecuta su contenido. La comprobación autentica registros y reproduce decisiones; no demuestra que un sensor externo diga la verdad.

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
| X101 Evidence ledger | Cadena HMAC-SHA256 y checkpoint externo | No ledger ZK, consenso, firma pública ni resistencia a root |
| X102 Input guard | JSON limitado por bytes, profundidad y nodos; claves repetidas rechazadas | No rkyv ni parser universal |
| X103 Decision receipts | Hash de recibo, política, observaciones y comprobaciones ordenadas; reproducción independiente | Reproduce hechos registrados, no atestación de hardware |
| X105 Containment budget | Tope atómico de cuarentenas persistentes, también entre procesos | No limita tráfico ni garantiza disponibilidad; la solicitud sospechosa sigue rechazada |
| X106 Evidence expiry | Orden temporal, edad máxima de observación y piso de reloj persistido | Reloj local en segundos; sin fuente de tiempo independiente |

La ruta es: entrada acotada → esquema → configuración anclada → transacción → reloj actual → token → cuota → repetición → observaciones reales → vigencia e integridad → presupuesto de cuarentena → recibo reproducible → decisión/cuarentena → auditoría → contrato de salida → cabeceras CSP. La exportación sale de esa auditoría y el verificador independiente comprueba HMAC, continuidad, checkpoint y reproducción de cada decisión nueva.

## Límites de confianza

- Los directorios de control, la clave HMAC, la configuración anclada y el proceso del operador son de confianza. Un administrador o proceso con el mismo usuario y acceso de escritura puede alterar estado o claves. Esta entrega no promete resistir ese compromiso.
- La cuarentena es una prohibición de admisión en este motor. Un proceso que ignore el motor puede seguir usando el archivo. La conexión obligatoria con consumidores de NQC está pendiente de integración y revisión.
- Una inspección es una observación puntual. Los descriptores rechazan enlaces simbólicos y archivos especiales, y comparan metadatos antes/después de leer. No garantizan que nadie cambie el archivo después de la decisión.
- Una cadena HMAC válida no detecta por sí sola el borrado de su cola. Hay que guardar un checkpoint fuera del estado local. La API permite comprobar un checkpoint exacto al reabrir; no existe todavía un servicio externo de anclaje.
- La clave HMAC autentica para quienes comparten esa clave. No es una firma verificable públicamente. No se inventaron primitivas criptográficas.
- No hay sensor continuo: cada solicitud inspecciona el activo solicitado. No hay daemon 24/7, integración SIEM, alerta externa, escalamiento automático ni publicación.
- Las verificaciones de auditoría son lineales con el historial y SQLite serializa decisiones. Esta entrega no afirma rendimiento de nanosegundos ni escala de producción. Retención, rotación de claves, cuotas de disco y exportaciones paginadas quedan pendientes.
- La vigencia usa reloj local con resolución de segundos. Detecta retrocesos observados y rechaza inspecciones cuya duración excede la política. No constituye sincronización de tiempo confiable frente a un administrador comprometido.
- El límite de cuarentenas solo acota transiciones persistentes en esta capa. Al agotarse, una petición con integridad alterada se rechaza sin crear otra cuarentena. No se admite el archivo para preservar el límite.
- El verificador de exportaciones admite hasta 8 MiB de auditoría, 10.000 registros y 100.000 nodos JSON. Superar un límite se rechaza explícitamente; no se omiten registros para producir un resultado válido.
- El hosting WSGI futuro deberá imponer TLS, límite de conexiones, lectura con timeout y framing HTTP correcto. Este paquete no abre puertos por sí mismo. La única escucha utilizada durante pruebas es loopback temporal.

## NQC y trabajo simultáneo

La base consultada fue `josuechavando350-png/nexus-quant-capital`, commit `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. La entrega se coloca como adición en `migration/defense/`, sin modificar Census ni recovered-source. El verificador de aislamiento existente permite adiciones bajo `migration/`; esa ubicación es una zona de preparación, no activación productiva.

`tools/check_nqc_base.py` verifica la base fijada o un descendiente que solo cambie `migration/defense/` y `migration/DEFENSE-INTEGRATION.md`, comprueba el blob del verificador original y ejecuta su validación completa. `tools/init_local.py --nqc-repo` exige ese control antes de crear estado. Un cambio fuera de esos límites requiere nueva revisión.

Se resolvió la descarga incompleta recuperando los 645 archivos de la revisión y verificando tamaño y hash de cada blob Git. El checkout base quedó limpio. Se añadieron únicamente `migration/defense/` y `migration/DEFENSE-INTEGRATION.md` a la copia local.

Pasaron el verificador de aislamiento original sobre la copia combinada, sus 9 pruebas y las 100 pruebas del paquete. `tools/check_nqc_artifact.py` inspeccionó los bytes reales de `nqc-census/Cargo.toml`, reprodujo su recibo y verificó su exportación sin modificar ese archivo. La prueba crea y retira un señuelo nuevo propio bajo `migration/`.

**La incorporación al código y la comprobación local no equivalen a activar un consumidor productivo obligatorio.** No existe todavía ese enlace con la operación de Census. La certificación canónica sigue siendo falsa; no se verificó la historia Git del repositorio productor original. No se ejecutaron pruebas Rust de Census porque no se modificó su código. Tampoco se validó hardware externo.

## Archivos de seguimiento

- `docs/CATALOGO_100.md` y `docs/catalog_100.json`: correspondencia exacta con los 100 nombres del PDF, alcance corregido y pendientes individuales.
- `docs/PRIMEROS_10_Y_PROPUESTAS.md`: explicación de los primeros 10 y 10 propuestas de diseño.
- `docs/PRUEBAS.txt`, `docs/ACEPTACION.json` y `docs/VALIDACION.json`: resultados efectivamente obtenidos.
- `docs/CLOCK_LOCK_REGRESSION.json`: comparación ejecutada entre 0.1.0 y 0.2.0 con un bloqueo real de SQLite y reloj controlado.
- `docs/NQC_ARTIFACT_CHECK.json`, `docs/NQC_ISOLATION.json` y `docs/NQC_ISOLATION_TESTS.txt`: validación de la incorporación local.
- `docs/V0_2.md` y `docs/CONTINUIDAD.md`: cambios, compatibilidad y siguiente trabajo concreto.
- `docs/FUENTES.md`: fuentes primarias y distinciones respecto a las afirmaciones del PDF.

La publicación autorizada es únicamente de código en `NQC-defensive`. No se habilitan workflows, despliegues, envíos de correo ni ejecución productiva.
