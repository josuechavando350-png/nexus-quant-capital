# Custodia firmada de evidencia — Ed25519

Estado: implementación de alcance acotado de IMMUNEFI.D1. No es certificación de
seguridad, autorización de un programa, prueba de ejecución ni verificación de
una vulnerabilidad. No se implementa criptografía propia: se utiliza
`cryptography==46.0.4`, ya instalada en el entorno de validación, y el primitivo
Ed25519 se contrasta con el vector público 1 de RFC 8032 §7.1.

## Qué cambia respecto a los hashes

Un tercero que modifica un archivo puede recalcular su SHA-256 y COMPLETE.json.
Esta unidad añade una firma sobre el inventario exacto y el hash del manifiesto,
vinculada a un expediente UUID y un productor. Cambiar los archivos y recalcular
solo los hashes deja la firma sin correspondencia con el nuevo contenido.
Una firma hecha por otra clave tampoco se acepta aunque sea matemáticamente
válida: la clave debe figurar en el registro externo de confianza, con permisos
para ese productor y expediente.

**Una clave de firma puede firmar datos falsos.** La firma autentica custodia de
bytes frente a la política de confianza elegida, no la verdad de esos bytes,
la identidad legal de una persona, el análisis realizado o su calidad. Siempre
se conservan execution_verified=false, vulnerability_confirmed=false,
data_truth_verified=false y scope_authorization_verified=false. No se promociona
una hipótesis, una observación estática ni un REVIEW_REQUIRED a Finding.

## Integración

Se usan `safe_io` y sus límites, `AuditLog` nativo de DIABLO, la CLI del paquete,
las pruebas obligatorias de QA y el registro de las 25 iniciativas. Los reportes
generados por review-platform reflejan el componente y su soporte parcial.
La firma puede cubrir el paquete portátil `publication/` producido por el
recorrido conjunto, o un bundle plano de QA, laboratorio, permisos, contabilidad
o política. No ejecuta comandos referenciados dentro de esos archivos.

El flujo operativo es: ejecutar el productor → su verificador semántico → firmar
el paquete original mediante una clave propia de custodia → verificar firma,
registro de confianza y bytes → repetir el verificador semántico que corresponda.
La custodia NO sustituye ninguna de esas comprobaciones. No se firma
silenciosamente dentro de review-platform: se requiere una clave seleccionada
explícitamente, separada de fondos, wallets, API keys y claves de infraestructura.

## Interfaces

```bash
python -m superhunter seal-evidence \
  --bundle /privado/revision/publication \
  --key-file /privado/claves/custodia.pem \
  --trust /privado/confianza/claves-publicas.json \
  --case-id <UUID-canonico> --producer <identificador> \
  --expires-at <fecha-ISO8601-con-zona> --out /privado/firma-nueva

python -m superhunter verify-custody \
  --bundle /privado/revision/publication --seal /privado/firma-nueva \
  --trust /privado/confianza/claves-publicas.json \
  --case-id <UUID-canonico> --producer <identificador>
```

Son plantillas de argumentos, no credenciales ni fechas precargadas. No hay
keygen público, inscripción automática de claves ni sustitución de la confianza
por una clave que venga en el paquete. La CLI usa el reloj actual y NO admite
--at para eludir vencimientos. La API permite reloj explícito para tests; sus
resultados no son sellos de tiempo confiables.

Registro de confianza externo:

- schema_version: entero 1; profile: superhunter-bytes-custody-v1.
- keys: lista explícita de claves públicas, máximo 64.
- Cada clave: key_id (SHA-256 de sus 32 bytes públicos), public_key_hex,
  producer_id, case_ids (UUIDs exactos, sin comodines), valid_from, valid_until,
  revoked (booleano estricto).

La confianza proviene del operador y debe distribuirse por un canal controlado.
No colocar el registro dentro del bundle ni dentro del sello; el comando lo
rechaza. Modificar ese registro puede cambiar las decisiones de confianza, por
diseño; la herramienta no autentica por sí sola al administrador del registro.

## Protección de claves y artefactos

La clave de custodia usa formato PEM/PKCS8 Ed25519. La primera interfaz solo admite
un archivo local sin cifrar, regular, del usuario actual, sin permisos para grupo
o terceros y sin enlaces duros o simbólicos. Usar directorios privados y una
clave exclusiva para evidencia. No compartirla ni incluirla en el repositorio.
No se admiten claves RSA ni contraseñas en argumentos. HSM, agente de firma y
almacenamiento cifrado con desbloqueo seguro son pendientes, no capacidades
implícitas de esta interfaz.

El sello contiene attestation.json, REVIEW.md y COMPLETE.json. No copia fuentes,
políticas, logs o claves. Los originales se conservan byte a byte. El propio sello
contiene nombres y hashes de archivos: no es cifrado ni anonimización y también
puede revelar metadatos. Los nombres visibles en consola están minimizados.

Solo bundles planos con manifiesto completo, hasta 512 archivos, 2 MB por archivo
y 32 MB agregados. Archivos extra, rutas no soportadas, directorios, symlinks,
claves JSON duplicadas o entradas incompletas se rechazan. Directorios de salida
nuevos con permisos 0700 y archivos 0600. Un filesystem controlado por un adversario
o cambios concurrentes de ida y vuelta no quedan excluidos de forma absoluta:
las dobles capturas detectan cambios observables; no son un snapshot atómico.

## Garantías y límites

La verificación exige firma Ed25519, mismo expediente/productor, clave incluida
explícitamente y no revocada, período de clave válido, firma no futura ni vencida,
inventario idéntico y auditoría coherente. Una revocación es conservadora: invalida
la aceptación actual de firmas anteriores de esa clave. No se emiten certificados
históricos ni se autentica la fecha de firma. Una firma robada o una clave
comprometida requiere revocación y análisis externo.

La firma utiliza un prefijo de dominio fijo y JSON canónico interno (sort_keys,
ensure_ascii y salto final). No se presenta este formato como JCS, DSSE, in-toto,
SLSA, RFC de transporte o certificación de cadena de suministro.

El registro de 809 pruebas corresponde a otra línea remota (b696ef78...), no al
ZIP de 769. Esta entrega es un incremento explícito sobre ese ZIP verificable;
no afirma haber integrado el comparador remoto de la línea 809. Sus archivos y
commits permanecen intactos y quedan identificados en HANDOFF_CUSTODY.md.

Fuentes técnicas consultadas el 4 de noviembre de 2026:
- https://cryptography.io/en/46.0.4/hazmat/primitives/asymmetric/ed25519/
- https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1
