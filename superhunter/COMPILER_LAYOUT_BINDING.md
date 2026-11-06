# Correspondencia fuente–AST–layout de Solidity

## Alcance exacto

`compiler_layout.py` recibe los JSON de entrada y salida **ya existentes** de
solc y un manifiesto esperado externo. No ejecuta solc, Slither, bytecode,
transacciones, PoCs ni objetivos externos. Es una comprobación de consistencia
entre artefactos suministrados, no una certificación de compilación.

La verificación requiere una entrada Standard JSON con `language=Solidity`,
`sources` de contenido inline y `settings.outputSelection` que solicite AST y
storageLayout. No carga URLs ni resuelve archivos desde texto de la fuente.
El perfil consume AST compacto de la familia Solidity 0.8 que incluya
`nameLocation`. No es compatible por promesa con todas las versiones del formato.

## Conexiones implementadas

CLI → captura de originales → identidades/hashes esperados → diagnósticos →
inventario de fuentes → AST de contratos y declaraciones → layout seleccionado →
`storage_layout.compare()` existente → AuditLog nativo DIABLO → evidencia privada
recalculable. El componente aparece en QA y sus pruebas obligatorias se ejecutan
con el resto del paquete. Los artefactos derivados pueden consumirse con el
comparador anterior; no se altera su comportamiento para afirmar una nueva garantía.

Se comprueba:

- Inventarios de archivos y IDs de fuente exactos, sin fuentes ocultas ni URLs.
- Ausencia de errores de compilador en la salida. `exit 0` no se usa como prueba
  de compilación válida: la interfaz Standard JSON comunica errores en JSON.
- IDs AST únicos; referencias de herencia conocidas, cierre sin ciclos y sin
  ancestros omitidos. **No** se vuelve a calcular la linealización C3.
- Rangos en bytes UTF-8 dentro de la fuente y del contrato declarado. El rango
  `nameLocation` debe contener exactamente el nombre declarado de la variable.
- Cobertura exacta de variables persistentes: ninguna omitida, duplicada o
  sustituida por una variable de otro contrato. Constants, immutables y transient
  quedan contabilizadas como excluidas del layout persistente, no verificadas.
- Identidad `archivo:contrato` de cada fila, correspondencia de nombres e IDs,
  diferencias de settings y de bytes fuente, y comparación estructural existente.

No se comprueba que un rango sea realmente una declaración al analizar la sintaxis
Solidity, ni que el tipo del AST coincida semánticamente con el código. Un atacante
con control de todos los artefactos puede fabricar un AST consistente. La identidad
del commit y la versión del compilador permanecen declaradas, no autenticadas.
Tampoco se revisan bytecode, inicializadores, migraciones ni estado desplegado.

## Uso

```bash
python3 -m superhunter review-compiler-layout \
  --expected /privado/expected.json \
  --before-input /privado/before-input.json \
  --before-output /privado/before-output.json \
  --after-input /privado/after-input.json \
  --after-output /privado/after-output.json \
  --out /privado/caso-nuevo

python3 -m superhunter verify-compiler-layout \
  --bundle /privado/caso-nuevo --expected /privado/expected.json
```

El manifiesto esperado incluye schema_version=1, repo, source, contract y registros
before/after con commit, compiler_version, input_sha256 y output_sha256. Los hashes
son SHA-256 de los archivos exactos, no de una versión reserializada. El manifiesto
no puede tomarse de dentro del paquete que pretende autenticar. Debe conservarse
externamente; sigue siendo una referencia de confianza del operador, no una firma.

La carpeta debe ser nueva y fuera del checkout. Se preservan originales, se generan
layouts derivados y se escriben result.json, audit.json y REVIEW.md. Los archivos
son 0600, la carpeta 0700 y COMPLETE.json se escribe al final. La verificación
reconstruye todo y no acepta que una bandera modificada se apruebe solo recalculando
el manifiesto del paquete. El paquete incluye fuentes privadas: no publicarlo.

Estados:

- SOURCE_LAYOUT_PRESERVED_IN_PROFILE: declaraciones compatibles dentro del perfil.
- SOURCE_LAYOUT_CHANGE_DETECTED: diferencias estructurales observadas.
- SOURCE_LAYOUT_REVIEW_REQUIRED: settings, versiones o formas que requieren revisión.
- COMPILER_LAYOUT_REJECTED: artefactos incompletos, incompatibles o fuera del perfil.

Exit 0 corresponde al primer estado; 1 a diferencias/revisión; 2 a rechazo/error.
Ninguno autoriza upgrades, confirma vulnerabilidades o promete seguridad.
`compiler_executed_here=false` y `vulnerability_confirmed=false` son explícitos.

## Límites de recursos

32 archivos fuente; 1 MB agregado de contenido fuente; 2 MB por artefacto; 40,000
objetos AST; 128 contratos. Los límites previos del comparador de layouts también
se aplican. Los excesos se rechazan, no se truncan silenciosamente.

## Documentación de interfaz consultada

- https://docs.soliditylang.org/en/v0.8.30/using-the-compiler.html
- https://docs.soliditylang.org/en/v0.8.30/internals/layout_in_storage.html

Implementación propia; no se copió ni redistribuyó código del compilador.
No hay dependencias nuevas. Los fixtures son fuentes inocuas y AST/JSON
explícitamente sintéticos; no se presentan como salidas obtenidas de solc.


## Ampliación explícita de perfil

La versión 2 del manifiesto exige comparación de tipos de fuente, AST y layout
para el subconjunto documentado en TYPE_CORRESPONDENCE.md. La versión 1 no cambia
su alcance. Ninguna de las dos prueba la ejecución ni autenticidad de solc.


## Perfil v4: inventario obtenido de los bytes fuente

La versión 4 añade SOURCE_DECLARATION_INVENTORY.md. Reutiliza las capas v2/v3,
pero contrasta primero la lista de declaraciones frente a la fuente completa
seleccionada dentro de un perfil explícito. Omitir la misma variable del AST y
del layout ya no acredita inventario completo. Las funciones se delimitan como
regiones opacas; no se valida su cuerpo ni la gramática Solidity completa.
La nueva comprobación no se aplica silenciosamente a los perfiles 1–3.
