# Program Intelligence — registro multiprograma offline

Esta unidad administra snapshots suministrados y revisados localmente. No es
un conector de cuentas, crawler, escáner ni servicio autónomo. No autentica la
política, su vigencia real, una invitación ni la autoridad del revisor.

## Implementado

Identificadores: Immunefi, HackenProof, Sherlock, Cantina, HackerOne, Bugcrowd,
Intigriti y YesWeHack. Se admiten programas de bounty, concursos y VDP; no se
confunden sus políticas. Los ocho identificadores NO son ocho API integradas.

Cada programa conserva: alcance, tipo/visibilidad, participación declarada,
permisos de automatización offline, divulgación, versión, URL de procedencia,
ventana de validez, bytes y hash de política, revisión humana local y activos.
La revisión se liga por hash a TODO el snapshot normalizado, incluidos activos
excluidos. Cambiar una regla deja obsoleta la revisión anterior.

Coincidencia exacta: repositorio + commit, contrato + chain_id, o hostname
completo. Una exclusión prevalece sobre una inclusión. No se expanden comodines,
se resuelven dominios ni se interpreta texto natural para inventar permisos.
Los formatos no soportados se rechazan explícitamente.

`requests_for_candidate()` convierte los metadatos Candidate existentes en
comprobaciones de repositorio y de CADA contrato afectado. Exige chain_id
explícito porque Candidate v1 no lo incluye. No ejecuta la PoC referenciada.

`changes()` compara snapshots y señala altas, bajas y cambios que requieren
revisión nueva. No renueva aprobaciones ni acepta que el nombre de una plataforma
signifique autorización automática.

## Comandos

```bash
python3 -m superhunter review-programs \
  --registry /privado/programas.json --requests /privado/solicitudes.json \
  --evidence /privado/politicas --out /privado/revision-nueva
python3 -m superhunter verify-programs --bundle /privado/revision-nueva
```

Por defecto se usa la hora UTC actual. `--at` sirve para replay explícito offline,
no es un reloj confiable ni debe usarse para sortear la caducidad. El verificador
comprueba las decisiones históricas y vuelve a evaluar al tiempo solicitado:
una decisión antigua favorable no se perpetúa al vencer el snapshot.

Salidas: LOCAL_SCOPE_ELIGIBLE, LOCAL_SCOPE_DENIED y LOCAL_SCOPE_REVIEW_REQUIRED.
ELIGIBLE solo significa que los metadatos coinciden con las reglas DECLARADAS;
`platform_authorization_verified=false` y `network_execution_allowed=false`
siempre. Acciones de red, broadcasts y envíos se deniegan aunque el snapshot
pretenda permitirlas. No se presentan decisiones como autorización legal.

Exit 0: todas las solicitudes coinciden con este perfil offline. Exit 1: existe
un rechazo o una revisión pendiente; la evidencia se conserva. Exit 2: error de
entrada, código o evidencia. Ningún exit code acredita una vulnerabilidad.

El paquete es privado, autocontenido y no sobrescribe salidas. Conserva originales,
solicitudes, decisiones y AuditLog nativo de DIABLO, ligado a los hashes del código.
Los hashes demuestran consistencia, no firma ni autenticidad de un productor.
La consola y el resumen omiten políticas e identificadores sensibles.

## Validación de esta entrega

51 tests nuevos de esquema, inclusión/exclusión, cadena/commit, revisión obsoleta,
ventanas temporales, aislamiento de programas, integridad, privacidad, Candidate,
AuditLog nativo, CLI y revalidación. 20 programas sintéticos con ocho plataformas
se comprobaron; esto NO demuestra 20 programas externos ni ejecución concurrente.

Demostración por CLI separada: 15 elegibles, 2 denegados y 3 pendientes sobre 20
registros sintéticos. Tras caducar: 0 elegibles, 2 denegados y 18 pendientes.

Rama focalizada sobre PR40: 380 tests (329 conservados + 51 nuevos), sin fallos,
errores ni omisiones; check y verify-check ejecutados. Acumulado local: 769 tests
(718 anteriores distintos + 51), ejecutados en seis grupos disjuntos con idéntica
huella de fuentes y control de inventario completo. Las primeras ejecuciones
largas interrumpidas por timeout NO se cuentan como aprobaciones.

El acumulado conserva los incrementos hermanos de contabilidad (640), conexiones
(622) y SMT (638), todos basados en 591. Esas cifras anteriores no se suman: se
conservó la unión de 718 identidades, sin eliminar tests. Esta rama focalizada NO
incluye toda esa consolidación; se entrega por separado con parche y manifiestos.

No se ejecutaron Slither, solc, Forge, objetivos externos, CI de GitHub ni la suite
histórica completa NQC o su aislamiento global. Solo cambia superhunter/.

## Referencias de diseño, no políticas de autorización precargadas

Consultadas el 4 de noviembre de 2026:
- https://www.hackerone.com/policies/code-of-conduct
- https://docs.bugcrowd.com/researchers/participating-in-program/reviewing-bounty-briefs/

Se revisó que las reglas específicas del programa y la revisión humana no se
pueden sustituir por pertenecer a una plataforma. El registro no hace búsquedas
online ni actualiza esas reglas automáticamente.

## Próximos pasos no implementados

Autenticación/conectores oficiales por plataforma, obtención completa de políticas,
comparación semántica revisada de documentos, revisión de invitaciones con el
usuario y enlace a las decisiones reales de cada programa. No inferir ninguno
de esos pasos del importador offline ni activar explotación automática.
