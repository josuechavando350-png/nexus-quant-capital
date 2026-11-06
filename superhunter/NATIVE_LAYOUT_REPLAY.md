# Revisión de almacenamiento respaldada por compilaciones nativas

`native_layout.py` une el ejecutor nativo fijado y el verificador de artefactos
v4. No ejecuta contratos, una EVM ni pruebas de vulnerabilidades. No autoriza
actualizaciones. El compilador debe existir fuera del checkout; no hay descarga,
sustitución o modo de simulación en esta ruta.

## Recorrido

Entrada Standard JSON con fuentes incluidas -> verificación del SHA-256 del
binario -> compilación por descriptor sellado y worker limitado -> repetición
exacta con el mismo compilador -> contraste fuente/AST/inventario/tipos/slots ->
comparación entre las dos versiones -> AuditLog de DIABLO -> paquete privado.

En cada verificación se ejecuta de nuevo el compilador para ambas entradas.
Un paquete JSON internamente consistente no sustituye esa repetición. Es el
mismo compilador: no constituye triangulación entre compiladores independientes.
Tampoco acredita que un productor remoto lo ejecutara anteriormente.

Se conserva el significado del comparador de artefactos: su campo anidado
`compiler_executed_here=false` describe SOLO ese componente. El resultado del
nuevo recorrido registra por separado `native_compiler_reexecuted=true` y los
replays efectivos que precedieron al análisis. No se modifica retrospectivamente
el significado de recibos de la entrega anterior.

## Requisitos

Linux x86-64, Python 3.11+, las dependencias del paquete existente y el archivo
oficial `solc-linux-amd64-v0.8.30+commit.73712a01`.

SHA-256 requerido:
`f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7`.

Referencia de identidad: https://binaries.soliditylang.org/linux-amd64/list.json

Las fuentes se incorporan como `content` de Standard JSON. El perfil usa
`native_compile.standard_input(...)` para fijar las opciones. Solo solicita AST
 y storageLayout: no genera ni ejecuta bytecode EVM, no habilita SMT del compilador
ni callbacks de importación desde disco. Una importación debe estar suministrada
entre las fuentes inline.

## Referencia externa

Archivo JSON con estas claves exactas:

- `schema_version`: 1.
- `repo`: identificador declarado `owner/repo`.
- `source`: nombre relativo `.sol` presente en las entradas.
- `contract`: nombre del contrato seleccionado.
- `before` y `after`: cada uno con `commit` (40 hex) e `input_sha256` (64 hex).

Los hashes corresponden a los BYTES completos de los dos archivos Standard JSON.
No se suministran outputs ni versiones libres de compilador. La ruta obliga al
perfil v4 de artefactos y al solc fijado. Repo y commits siguen siendo referencias
declaradas: no se autentica su pertenencia a un repositorio o un despliegue.

```bash
python3 -m superhunter review-native-layout \
  --binary /herramientas/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --expected /privado/referencia.json \
  --before-input /privado/antes.json --after-input /privado/despues.json \
  --out /privado/revision-nueva

python3 -m superhunter verify-native-layout \
  --binary /herramientas/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --expected /privado/referencia.json --bundle /privado/revision-nueva
```

El paquete conserva ambas compilaciones, recibos y manifiestos originales, los
artefactos de la revisión v4 y un registro DIABLO de las relaciones. La referencia
externa no puede ser el archivo embebido en el propio paquete. Archivos 0600 y
carpeta 0700, sin sobrescribir. La firma de custodia sigue siendo una operación
separada; este recorrido no firma nada ni utiliza claves.

## Resultados y salidas

- `NATIVE_LAYOUT_PRESERVED_IN_PROFILE`: no se detectó cambio estructural bajo
  todas las restricciones del perfil; código 0. No certifica seguridad.
- `NATIVE_LAYOUT_CHANGE_DETECTED`: diferencia estructural; código 1. No confirma
  por sí misma una vulnerabilidad o pérdida de fondos.
- `NATIVE_LAYOUT_REVIEW_REQUIRED`: incertidumbre o sintaxis fuera del perfil;
  código 1. No se aprueba una parte que no se comprobó.
- `NATIVE_LAYOUT_REJECTED`: datos, identidad, reproducción o comprobación
  incompatibles; código 2. No se produce una revisión favorable.
- `NATIVE_LAYOUT_BLOCKED`: compilador fijado ausente o plataforma incompatible;
  código 3. No hay fallback al AST suministrado.

Los errores de compilación se conservan con el comando general
`compile-solidity`; la revisión entre versiones exige que ambas compilaciones
sean satisfactorias y no crea un paquete de éxito si una falla.

## Pruebas y límites

`test_native_layout.py` comprueba referencias, integridad y enlaces. Usa una
captura REAL de solc como dato de test y sustituye llamadas de replay en algunos
tests de orquestación. Esos tests no son evidencia de nuevas compilaciones.

El script de aceptación distribuido en `validation/run_native_acceptance.py`
invoca las CLI en procesos separados con el binario real. Sus entradas son
contratos propios e inocuos, no objetivos de terceros ni PoCs. Requiere una
carpeta nueva. No instala dependencias ni requiere acceso a Internet.

No se heredan autorizaciones del programa, no se autentican estados desplegados,
no se analizan todas las instrucciones de funciones ni se descubren exploits.
Los límites del worker son defensa de recursos, no un sandbox del kernel para
procesar código hostil. No hay EVM, RPC, Slither, Foundry ni despliegues en este
perfil. Mantener los artefactos privados cuando contengan fuentes privadas.
