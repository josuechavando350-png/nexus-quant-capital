# Perfil v2: coherencia del tipo declarado entre fuente, AST y layout

Implementación defensiva local. No ejecuta solc, Slither ni EVM; no es un
compilador de Solidity ni un verificador universal de actualizaciones.

## Problema delimitado y comprobación

El perfil v1 comprueba nombres, ubicación de declaraciones y cobertura del AST,
pero no promete comprobar tipos desde la fuente. Un artefacto con una declaración
`uint128` y un descriptor de almacenamiento `uint256` puede conservar nombres y
posiciones válidos. El v1 puede considerarlo estructuralmente preservado.

El perfil v2 añade tres comprobaciones separadas:

1. Un analizador léxico/sintáctico limitado lee el fragmento de tipo desde los bytes
   de fuente, ignorando comentarios y espacios sin unir tokens separados.
2. Un recorrido del AST obtiene una forma estructural independiente. Comprueba
   los rangos de todos sus nodos contra la fuente y los límites de la declaración.
3. Un recorrido de los descriptores de almacenamiento reconstruye otra forma,
   independiente de los IDs internos del compilador. Debe coincidir con las dos
   anteriores. El comparador de layouts existente sigue comprobando su geometría.

Una incompatibilidad explícita rechaza los artefactos. Un tipo fuera del perfil
produce revisión pendiente; no se supone que su forma sea compatible.

## Cómo usarlo

Se mantiene la CLI existente y el mismo conjunto de campos del manifiesto.
Cambiar `schema_version` a **2** exige el perfil estricto. No agregar un booleano
al resultado para "activar" una comprobación: el resultado se deriva de entradas.

```bash
python3 -m superhunter review-compiler-layout \
  --expected /privado/expected-v2.json \
  --before-input /privado/before-input.json \
  --before-output /privado/before-output.json \
  --after-input /privado/after-input.json \
  --after-output /privado/after-output.json \
  --out /privado/revision-nueva

python3 -m superhunter verify-compiler-layout \
  --expected /privado/expected-v2.json --bundle /privado/revision-nueva
```

`expected-v2.json` conserva repo, source, contract y los registros before/after
con commit, compiler_version y hashes de input/output. El manifiesto esperado
es externo al paquete. Downgrade a v1 dentro del paquete se rechaza. El manifiesto
externo sigue siendo una referencia que debe custodiar el operador, no una prueba
de autorización ni firma del productor.

## Perfil admitido

Tipos elementales: uint/int con anchuras válidas, bool, address/address payable,
bytes1..bytes32, bytes y string. uint/int se normalizan a su anchura por defecto.
Arrays fijos con longitud literal decimal positiva y arrays dinámicos, anidados.
Mappings entre tipos admitidos, incluidos nombres opcionales de clave/valor;
los nombres de esos parámetros no cambian la forma del tipo.

El AST debe incluir typeName y rangos src. La falta de información obligatoria
se rechaza, no se rellena. El rango de tipo debe empezar la declaración y terminar
antes de su nombre. El texto intermedio solo admite modificadores del perfil:
public, private, internal y override simple. No se permite recortar `uint128` a
`uint` e ignorar el sufijo `128` para hacerlo coincidir con uint256.

Las estructuras, enums, tipos definidos por el usuario, punteros a funciones y
longitudes que requieren evaluar expresiones quedan fuera del perfil. El módulo
no utiliza eval, importación dinámica, compilación o ejecución de las fuentes.
Los modificadores/formatos no contemplados se rechazan o requieren revisión;
no se promete compatibilidad con todos los artefactos que produce solc.

Los límites de bytes, tokens, nodos y profundidad impiden búsquedas ilimitadas.
Los límites de cantidades y geometría del layout original siguen aplicando.

## Resultados y límites

La revisión v2 indica checked/review_required por declaración y hashes de las
formas comprobadas. `all_declared_types_checked` describe solo ese conjunto.
Una revisión de un contrato sin variables lleva un conteo explícito de cero.

`SOURCE_LAYOUT_PRESERVED_IN_PROFILE` NO significa que la compilación se ejecutó,
que el AST sea auténtico o que un upgrade sea seguro. `source_syntax_reparsed`
sigue siendo false: no se analiza todo el programa, solo fragmentos de tipo.
`type_semantics_from_source_checked` sigue siendo false para semántica general;
el campo type_correspondence documenta el alcance parcial de la comprobación.
No se comprueban expresiones, resolución semántica de nombres, herencia C3,
inicializadores, migraciones, bytecode o estado desplegado. Un AST fabricado
coherentemente todavía es posible. Firmar bytes tampoco transforma su contenido
en hechos observados.

El perfil v1 se conserva y no hereda las comprobaciones nuevas. No se modificaron
los tests anteriores para hacerlos pasar por el perfil v2.

## Conexión y pruebas

source_types -> compiler_layout -> storage_layout -> AuditLog DIABLO -> CLI/QA.
source_types.py está incluido en la huella de código que verifica el paquete.
El registro de componentes exige cuatro pruebas negativas nuevas y ejecuta toda
la suite del módulo. El verificador reutiliza las mismas fuentes e input/output
originales para recalcular la correspondencia, sin modificar esos originales.

La nueva suite contiene 46 tests y 64 combinaciones de anchura/signo con semilla
fija. Se comprueban límites, comentarios Unicode, aliases, arrays, mappings,
contradicciones, degradación de perfil, artefactos alterados, CLI y privacidad.
Los fixtures son propios e inocuos. Ninguno se presenta como output real de solc.
Los recibos de VALIDATION.json de la entrega registran las ejecuciones realizadas.

Referencias primarias del formato/gramática consultadas:
https://docs.soliditylang.org/en/v0.8.30/types.html
https://docs.soliditylang.org/en/v0.8.30/using-the-compiler.html
https://docs.soliditylang.org/en/v0.8.30/internals/layout_in_storage.html

No se ha copiado una implementación de terceros ni añadido dependencias.
