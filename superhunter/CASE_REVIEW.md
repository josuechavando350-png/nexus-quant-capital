> Ampliación compatible: el contexto v2 exige evidencia de la secuencia contable.
> Ver [ORDERED_CASE.md](ORDERED_CASE.md). El perfil v1 descrito aquí no comprueba
> el orden; las declaraciones y hashes no autentican ejecución externa.

# Expediente de revisión enlazado — alcance exacto

`case_review.py` enlaza Candidate con tres paquetes existentes: políticas locales,
diagnósticos estáticos y conciliación aritmética. Llama a los verificadores reales
de esos módulos, antes de comparar sus identidades. No ejecuta el código del
candidato, una PoC, Slither, compiladores, red, transacciones ni reportes externos.

## Qué comprueba

El mismo Candidate debe aparecer en la referencia externa y en el expediente.
El paquete de políticas debe contener exactamente las solicitudes del repositorio
y todos los contratos afectados, con chain_id explícito y sin solicitudes extra.
Cada exclusión, caducidad o aprobación obsoleta se mantiene como bloqueo.

Las fuentes del diagnóstico deben declarar el mismo repositorio, commit y scope.
La observación seleccionada se identifica por su huella completa; no se escoge
una alerta parecida ni se eleva la etiqueta High a una severidad final.

El libro de balances debe declarar el mismo repositorio, commit, cadena, bloque
y hash de bloque, además del identificador de libro esperado. El contexto debe
asociar cada contrato afectado a una cuenta que realmente aparezca en ese libro.
Esas asociaciones son declaraciones del operador: no se deducen ni autentican
mediante blockchain. Una diferencia de saldo puede coexistir con una alerta sin
que la alerta sea su causa. Este módulo NO demuestra esa relación causal.

## Estados

- CASE_REVIEW_REQUIRED: artefactos consistentes con las referencias declaradas;
  todavía requiere revisión humana, no confirma una vulnerabilidad.
- CASE_REVIEW_BLOCKED: el alcance suministrado deniega o requiere nueva revisión.
- CASE_REVIEW_INCONCLUSIVE: falta selección de alerta, hay ubicaciones incompletas,
  el analizador declaró un error o falta cobertura/valoración de balances.
- CASE_EVIDENCE_REJECTED: error de integridad, identidad o esquema; no se publica
  una revisión favorable.

Los estados nunca generan un Finding final. No se calculan probabilidad de bounty,
severidad final ni ganancias. Un saldo conciliado tampoco certifica ausencia de
vulnerabilidades. Los precios siguen siendo datos aportados, no cotizaciones
verificadas ni necesariamente actuales.

## Interfaz

```bash
python3 -m superhunter review-case \
  --candidate /privado/candidate.json --context /privado/context.json \
  --programs /privado/paquete-politicas \
  --static /privado/paquete-estatico \
  --balances /privado/paquete-contable --out /privado/expediente-nuevo

python3 -m superhunter verify-case --bundle /privado/expediente-nuevo \
  --candidate /privado/candidate-esperado.json --context /privado/contexto-esperado.json
```

La CLI no acepta una hora simulada, objetivos, RPC ni comandos para ejecutar PoCs.
Usa UTC actual. La API Python recibe `at` solo para pruebas/replay explícito: esa
hora no es un reloj autenticado ni debe tomarse como permiso operativo.

El contexto JSON v1 tiene exactamente estos campos:

- schema_version: entero 1.
- candidate_sha256: SHA-256 del Candidate serializado por `safe_io.canonical`.
- platform y program_id: identificadores del registro local existente.
- chain_id: entero explícito, nunca inferido de una dirección.
- state_anchor: block_number y block_hash, iguales a los declarados en el libro.
- ledger_case_id: identificador exacto del libro contable.
- account_bindings: cada dirección afectada en minúsculas a una cuenta del libro.
- static_fingerprint: huella de una alerta importada o null (inconcluso).
- evidence_manifests: SHA-256 de los bytes originales de COMPLETE.json para los
  tres paquetes, con claves programs, static y balances.

Candidate v1 no tiene chain_id; el contexto lo aporta. Esta versión exige bloque
explícito para combinarlo con el libro anclado; no inventa un bloque para None.

Los archivos de referencia esperados se aportan desde fuera del paquete. La CLI
rechaza usarlos desde dentro de la propia carpeta del expediente. Esto evita que
el verificador trate una referencia auto-reemplazada como verdad externa; NO
acredita por sí solo la autenticidad de los archivos que el operador suministró.
Los hashes ligan bytes, no autorizaciones ni realidad económica.

## Evidencia y custodia

Los originales quedan capturados sin modificación, bajo prefijos por módulo.
El inventario es exacto, limitado en cantidad/tamaño, sin symlinks o archivos
ocultos fuera del manifiesto. Los permisos son 0700 para la carpeta y 0600 para
archivos. El resumen omite identificadores y descripciones; el paquete completo
sigue siendo PRIVADO porque contiene fuentes y documentos originales.

La bitácora nativa de DIABLO liga candidato, contexto, manifiestos y resultado.
El verificador reconstruye la bitácora y los resultados desde esos originales,
y comprueba tanto la revisión histórica como el alcance al momento actual.
Una revisión válida ayer no permanece habilitada si su política ya venció.

No se genera firma nueva en este recorrido. El paquete plano es compatible con
el módulo de custodia anterior, pero la compatibilidad no equivale a una firma
ni a autenticación del productor. No se generan claves de producción.

## Integración

CLI -> Candidate -> políticas -> revisión estática -> conciliación contable ->
comprobación cruzada -> AuditLog de DIABLO -> paquete de revisión -> revalidación.
`quality.py` registra el componente, sus dependencias y pruebas obligatorias;
la revisión general del paquete ejecuta esa suite. No se activa un investigador
ni un escaneo. No modifica motores históricos de NQC ni fuentes nativas fijadas.

Las pruebas y la demostración de esta entrega usan código Solidity inocuo y
JSON de formato expresamente sintéticos. No se atribuye a Slither una ejecución
que no se realizó ni se presenta `forge_evidence_sha` del ejemplo como prueba de
Forge. La PoC referenciada no existe ni se ejecuta en estos controles.
