# SUPERHUNTER — adaptadores de evidencias offline

Estado: **intercambio de datos implementado; motores de investigación no conectados**.
Todo el código de integración vive en NQC. DIABLO y los motores históricos de
NQC permanecen sin cambios. No se ejecutan PoCs, Forge, RPC, transacciones,
exploración de objetivos ni envíos de reportes.

## Flujo implementado

1. `export_diablo()` recibe un `Finding` nativo de DIABLO (dataclass o JSON),
   contexto explícito del objetivo y un archivo de resultados ya existente.
   Produce `Candidate` sin verificar y `request.json` con identificadores
   deterministas, cadena, bloque, hash de bloque y hashes de contenido.
2. `import_nqc()` recibe esa solicitud y una respuesta de evidencia existente.
   Comprueba la asociación solicitud/respuesta, cadena y estado antes de aplicar
   las puertas de revisión del puente. No ejecuta una reconstrucción.
3. Produce `decision.json`, `diablo-feedback.json` y, cuando corresponde,
   `review.md`. El feedback conserva el ID original de DIABLO.

El `Finding` nativo de DIABLO NO se considera un hallazgo confirmado. Su
severidad y su descripción no acreditan la ejecución de una prueba.

## Veredictos y cambio respecto a fase 1

- `EXPORTED_UNVERIFIED`: candidato exportado; no confirma alcance ni ejecución.
- `REJECTED`: datos inválidos o comprobaciones de consistencia fallidas.
- `INCOMPLETE`: artefacto sin la reconstrucción requerida.
- `REVIEW_REQUIRED`: declaraciones y artefactos consistentes; falta revisión.

**Se retira `REPORT_READY`. No se emite un `Finding` final.** El resultado válido
contiene `draft`, `execution_verified=false` y `proposed_severity`, no
`final_severity`. Los antiguos `scope_pass` y `forge_pass` se identifican como
`declared_scope_approved` y `declared_forge_pass`: son declaraciones, no hechos
verificados por el conector. Esta es una modificación deliberada del contrato
para evitar una confirmación falsa.

Un SHA-256 vincula bytes, pero no autentica al productor. El manifiesto de
alcance, el nombre del revisor, `target_bound`, `run_ok` y la confianza siguen
siendo declaraciones externas. La coincidencia de cadena entre solicitud y
respuesta tampoco constituye autorización del programa para esa cadena.

## Uso

Python 3.11+ y librería estándar. IO seguro requiere POSIX con openat/O_NOFOLLOW.
Desde la raíz del repositorio:

```bash
python3 -m unittest discover -s superhunter/tests -v

python3 -m superhunter export-diablo \
  diablo-finding.json context.json forge.log \
  --out /directorio-privado/caso-001-request

python3 -m superhunter import-nqc \
  /directorio-privado/caso-001-request/request.json \
  nqc-response.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/caso-001-review
```

`context.json` requiere `scope_id`, `repo`, `commit`, `chain`, `chain_id`,
`fork_block`, `block_hash`, `family` y `poc_path`. No se deduce la función de
prueba a partir del nombre de un archivo. El contexto debe precisar
`archivo.t.sol::test_nombre`. Para un bloque conocido se exige su hash.

Respuesta de intercambio para evidencia de reconstrucción:

```json
{
  "schema_version": 1,
  "request_sha256": "hash de la solicitud exportada",
  "chain_id": 31337,
  "reconstruction": {"...": "Reconstruction original completa"}
}
```

Ese formato define un **contrato de recepción**, no un productor ya construido
dentro del motor NQC. Una reconstrucción debe suministrarse desde un proceso
independiente de revisión. No generar datos inventados para satisfacerlo.

El puente legacy también conserva su interfaz de argumentos original:

```bash
python3 -m superhunter candidate.json reconstruction.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/caso-002-review
```

`Admission` conserva sus secciones `scope`, `forge`, `nqc`, `duplicate` y
`severity`. El archivo NQC referenciado debe contener la Reconstruction completa,
incluidos severidad, confianza y notas. Los importes no se recalculan ni se
presentan como mediciones realizadas por este módulo. `amount_wei` se conserva
por compatibilidad: el productor debe precisar la unidad mínima y decimales del
token; el nombre del campo no autoriza asumir 18 decimales.

Códigos de salida: 0 para exportación o borrador de revisión, 1 para rechazo o
información incompleta, 2 para error de esquema/IO. **0 no significa hallazgo**.
La consola no imprime reportes ni datos económicos. Cada ejecución necesita un
directorio nuevo: no se sobrescriben decisiones anteriores.

## Compatibilidad nativa comprobada

- Modelo DIABLO: `nexus-offensive/core/models.py`, commit
  `0c27792fba1af1f925bfff03fbcc6fd82a3791b0`, blob
  `bd832c728e71dc18bb4e9fa76bca7b36bf714a8b`.
- Cierre NQC: `ci/nqc-protocol-fork/PROTOCOL_FORK_FINAL_CLOSEOUT.json`, commit
  `16e352225ba8a6a931834c4edf3d86d9a2924b7d`, blob
  `8c12db5323f2bcd0c50f242f7e720a9780b30b76`.

El segundo es un documento de políticas/historia, **no** una reconstrucción de
un candidato. El adaptador devuelve `INCOMPLETE`, aunque sus checkpoints digan
PASS. No convierte resultados de trading o liquidaciones históricas en pérdidas
por vulnerabilidades.

## Protección de artefactos

JSON sin claves duplicadas ni números no finitos; límites de tamaño; tipos
estrictos; enteros canónicos hasta uint256; lectura sin symlinks, dispositivos o
traversal. Las salidas usan directorios 0700 y archivos 0600. `COMPLETE.json`
se escribe al final con hashes; un consumidor debe comprobarlo antes de usar
una carpeta. Un cierre abrupto puede dejar una carpeta incompleta, no un caso
válido. El contenido sensible debe mantenerse fuera del checkout público.

## Qué falta y qué no se afirma

No hay ejecución coordinada de los motores DIABLO y NQC, reconstrucción
independiente, confirmación de vulnerabilidades, autenticación criptográfica de
productores, actualización automática de reglas de bounty ni envío automático.
No hay certificación nueva de PFT/Census ni evidencia de recompensas.
Ver `VALIDATION.md` para el alcance real de las pruebas ejecutadas.
