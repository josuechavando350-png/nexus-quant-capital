# Gestión multiplataforma — incremento focalizado remoto

Registro offline de políticas de programas, no conectores de cuentas ni escaneo.
Implementación, perfil y limitaciones: esta entrega añade program_registry.py,
privacy.py (parser privado compartido), tests del registro, rutas CLI y QA.
Las funciones de redacción de privacy.py se conservan pero este incremento no
las activa globalmente en los demás comandos históricos.

Plataformas identificables: Immunefi, HackenProof, Sherlock, Cantina, HackerOne,
Bugcrowd, Intigriti y YesWeHack. Un identificador no implica conexión API.
Los programas se cargan desde JSON normalizado y documentos locales suministrados.
Cada política debe tener hashes, activos explícitos, revisión humana vinculada,
ventana y caducidad de revisión. Las exclusiones prevalecen. Los activos de
repositorio quedan fijados por commit; los de contrato, por cadena y hash de
código declarado. No se autentica ese commit/código contra un servicio externo.

Solo review_source, review_evidence, review_model y draft_report pueden ser
LOCAL_REVIEW_ELIGIBLE. No se ejecuta ninguna acción: scan, exploit, deploy,
broadcast, submit_report y otras operaciones activas se bloquean siempre.
LOCAL_REVIEW_ELIGIBLE no es un permiso autenticado para investigar servicios.

```bash
python3 -m superhunter review-programs --catalog /privado/catalog.json \
  --requests /privado/requests.json --evidence-root /privado/documentos \
  --out /privado/revision-nueva
python3 -m superhunter verify-programs --bundle /privado/revision-nueva
```

Los dos comandos admiten --at ISO8601 para reproducir un instante explícito.
Sin --at se usa hora UTC actual. Una comprobación histórica satisfactoria puede
estar vencida al verificarla hoy. verify-programs reconstruye primero la
historia y luego vuelve a evaluar la vigencia actual. Sus códigos son 0 para
solicitudes todas elegibles localmente, 1 para bloqueo/pendiente/vacío y 2 para
error de esquema/evidencia. No presentar 0 como aprobación de seguridad.

El formato completo se documenta mediante validate_catalog y validate_requests,
y los ejemplos generados por example_catalog están etiquetados como sintéticos:
no son programas reales ni permiten operar sobre ellos. No se generan revisiones
aprobadas para entradas del usuario. La caducidad máxima de 30 días es un límite
interno, no una garantía de actualidad de las reglas. Deben revisarse siempre
las reglas oficiales antes de investigar. Las cláusulas en prosa no se interpretan
ni se validan automáticamente; su mapeo JSON requiere revisión humana.

La bitácora nativa AuditLog de DIABLO vincula cada decisión mediante hashes.
El verificador recalcula valores y eventos; no autentica al revisor ni al productor.
Las salidas son privadas 0700/0600 y no sobrescriben. El resumen omite nombres,
URLs y texto privado; el paquete original sí contiene información sensible.
No tiene conexiones de cuentas, registro, envíos de reportes ni peticiones HTTP.

Esta rama focalizada NO sustituye la versión LOCAL consolidada que además conserva
balances, SMT, grafo, permisos, regresiones y review-platform --programs. Esa
variante y sus resultados se entregan aparte, con identidad de código distinta.
No se modifican fuentes originales, workflows ni main. No se ha demostrado
un hallazgo real, ausencia universal de errores ni efectividad de bug bounty.

Referencias de diseño consultadas 2026-11-04:
- https://docs.hackerone.com/en/articles/8494552-defining-scope
- https://www.hackerone.com/terms/disclosure-guidelines
- https://immunefi.com/rules/
- https://docs.bugcrowd.com/researchers/participating-in-program/reviewing-bounty-briefs/
- https://docs.hackenproof.com/welcome/code-of-conduct
- https://kb.intigriti.com/en/articles/5379096-in-scope-or-out-of-scope

Estas referencias no autorizan pruebas en programas específicos.
