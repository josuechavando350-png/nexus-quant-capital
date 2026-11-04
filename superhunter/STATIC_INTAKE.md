# Recepción verificable de diagnósticos Slither

Implementación original de un consumidor de JSON. NO ejecuta Slither, solc,
Forge, un contrato ni una PoC. No busca objetivos, abre conexiones ni genera
exploits. La validación confirma asociaciones entre bytes suministrados, no
la autoría de un informe, la autorización de un programa ni explotabilidad.

## Función implementada

`import-static` recibe un manifiesto, un informe Slither JSON ya existente y
una carpeta con fuentes Solidity propias/autorizadas. Verifica hashes SHA-256,
listas explícitas de archivos/detectores, ubicaciones en bytes UTF-8, límites y
números de línea. No usa rutas absolutas del informe para abrir archivos.

Agrupa observaciones con la misma regla y ubicaciones ligadas a los mismos bytes,
repositorio/commit declarados y scope_id. Conserva cada registro de entrada,
su índice, texto, impacto y confianza declarados por la herramienta. Etiquetas
contradictorias se conservan y señalizan. Esto NO decide duplicados de bounty.

La salida es un paquete privado y autocontenido: manifiesto e informe originales,
fuentes capturadas, observations.json, resumen REVIEW.md y COMPLETE.json.
`verify-static` vuelve a calcular la normalización desde esos bytes; rechaza
alteraciones del informe derivado incluso si se regeneró su manifiesto.
No es un segundo motor de análisis estático ni una autenticación criptográfica.

## Estados

- STATIC_REVIEW_REQUIRED: existen observaciones estáticas no verificadas.
- STATIC_NO_DIAGNOSTICS: la lista explícita de diagnósticos está vacía. No prueba seguridad.
- STATIC_COVERAGE_UNKNOWN: no se suministró results.detectors. Slither puede
  omitirla por resultados vacíos o por selección de salida; no se adivina cuál.
- STATIC_TOOL_ERROR: success=false con información de error; no se trata como éxito.
- STATIC_INTAKE_REJECTED: datos incompatibles, no soportados o inválidos.

No se produce Candidate con PoC inventada ni Finding confirmado. La pertenencia
al commit, versión de herramienta y scope declarados NO se autentica por aceptar
el manifiesto. No existe severidad final ni afirmación de "todas las vulnerabilidades".

## Uso

```bash
python3 -m superhunter import-static --manifest /privado/manifest.json \
  --report /privado/slither.json --sources /privado/fuentes \
  --out /privado/caso-nuevo
python3 -m superhunter verify-static --bundle /privado/caso-nuevo
```

El mismo componente admite `python3 -m superhunter.static_intake ...`.
El directorio debe ser nuevo, fuera del checkout y de las fuentes de entrada.
Archivos 0600, carpeta 0700. La consola no imprime rutas, mensajes de los
analizadores ni código. El paquete COMPLETO sigue siendo privado: incluye
código y textos originales, que pueden contener información sensible.

Manifiesto v1:

```json
{
  "schema_version": 1,
  "scope_id": "revision-local-declarada",
  "target": {"repo": "owner/repo", "commit": "40 caracteres hexadecimales"},
  "tool": {
    "name": "slither", "version": "version-declarada",
    "report_sha256": "sha256 real del archivo slither.json",
    "detectors": ["naming-convention"]
  },
  "sources": [{"path": "contracts/Counter.sol", "sha256": "sha256 real del archivo"}]
}
```

Los hashes ilustrativos anteriores no son valores válidos. El paquete de
validación contiene manifiestos completos calculados, claramente etiquetados
como ejemplos sintéticos; no se fabricó una ejecución de Slither.

## Perfil soportado y límites

Formato envelope success/error/results con results.detectors, siguiendo la
interfaz pública documentada. start/length son offsets de BYTES, no caracteres.
La función de Slither _compute_line incluye la línea del offset final exclusivo;
el comprobador respeta esa convención. No se verifican columnas, AST, SlithIR,
semántica del nombre de elemento ni el contenido de type_specific_fields.
Un rango válido puede señalar un texto distinto del pretendido; su hash permite
ver exactamente qué bytes se asociaron, pero no adivina la intención del detector.

Solo rutas relativas canónicas .sol, 64 fuentes, 8 MB de fuente agregada,
2 MB por artefacto, 1.000 diagnósticos y 100 elementos por diagnóstico.
Cualquier diagnóstico sin ubicación, con rango de longitud cero, fuera de las
fuentes declaradas o de tipo no soportado bloquea la importación: no se descarta
silenciosamente. La disponibilidad de este subconjunto no implica compatibilidad
con todas las versiones o detectores de Slither. Los resultados producidos por
herramientas deben revisarse antes de usar este perfil.

Referencias de interfaz consultadas el 4 de noviembre de 2026:
- https://github.com/crytic/slither/wiki/JSON-output
- https://crytic.github.io/slither/slither/core/source_mapping/source_mapping.html

No se copiaron fuentes de Slither ni código propietario en esta implementación.
No se agregaron ejecutables/dependencias de terceros. Las licencias de futuras
integraciones ejecutables deben revisarse por separado antes de distribuirlas.

## Contexto

Avance parcial de TRAIL-R1 y P1 del segundo PDF. No implementa todavía los
puntos 1/2 de SlithIR y taint, detectores nuevos ni el Hunter autónomo.
Los 25 nuevos requisitos se conservan en initiatives.json en la versión local
consolidada; los 27 y 50 anteriores siguen siendo registros separados.
