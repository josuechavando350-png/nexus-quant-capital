# Inventario de declaraciones desde la fuente — perfil v4

Esta revisión lee los bytes completos de la fuente seleccionada y obtiene su
inventario de variables de estado sin usar la lista de declaraciones del AST
como punto de partida. Lo contrasta después con el AST suministrado y con el
recorrido de tipos/layout/posiciones existente. **No es solc ni una compilación.**

## Por qué se añadió

Una fuente puede contener dos variables mientras un AST fabricado y su layout
omiten conjuntamente la segunda. El perfil v3 verifica los elementos declarados,
pero puede devolver `SOURCE_LAYOUT_PRESERVED_IN_PROFILE` para ese conjunto
incompleto. El perfil v4 rechaza ese control con
`SOURCE_AST_DECLARATION_SET_MISMATCH`. La garantía adicional pertenece al v4;
los perfiles 1–3 no pasan a prometer cobertura de la fuente.

## Qué se lee y qué se comprueba

Se tokenizan comentarios, identificadores, números, símbolos y cadenas,
conservando offsets en bytes UTF-8. Comentarios y cadenas no crean declaraciones.
Se recorre una unidad fuente con un solo contrato ordinario y pragmas admitidas.
De cada variable se obtiene nombre, tipo, rango, visibilidad, mutabilidad y uso
de almacenamiento transitorio. Las variables no persistentes también se cotejan:
marcar en el AST una variable mutable como constante no permite desaparecerla.

Se comprueba el rango real del contrato desde su cabecera hasta la llave de
cierre, no un segmento recortado proporcionado por el AST. Las declaraciones se
asocian por sus rangos físicos de nombre, no por el orden de arrays ni los IDs.
La declaración y el fragmento de tipo deben abarcar exactamente los tokens
admitidos. Se permiten los endpoints con o sin el terminador punto y coma,
porque estos artefactos proceden de productores declarados, no autenticados.

La ruta existente sigue comprobando las filas persistentes del layout y los
algoritmos de posiciones v3. El `AuditLog` nativo de DIABLO liga los nuevos
hechos al expediente; la identidad del motor incluye `solidity_inventory.py`.
Los originales no se modifican y la CLI continúa requiriendo referencia externa.

## Perfil admitido y límites

- Versión de compilador **declarada** 0.8.30; contrato individual, sin herencia,
  importaciones, base personalizada ni otras definiciones a nivel de archivo.
- Tipos elementales, mappings, arrays de longitudes literales, cabeceras dinámicas
  y calificadores documentados. Se admiten inicializadores literales simples;
  las expresiones generales requieren revisión y no se evalúan.
- Definiciones de funciones con nombre, constructor, receive, fallback, modifiers,
  events, errors, structs y enums se delimitan como regiones opacas. Se comprueba
  el equilibrio de delimitadores, **no sus instrucciones, parámetros, semántica
  ni correspondencia del cuerpo con el AST**. Los miembros de una struct y las
  variables locales de una función no son variables de estado del contrato.
- Las variables con tipo de función, tipos definidos por el usuario, `using`,
  `override`, sintaxis no soportada, otras versiones y archivos con más contratos
  no reciben una comprobación completa del inventario; requieren revisión.
- Máximo 1 MB de fuente, 100,000 tokens, 2,048 declaraciones y 64 niveles de
  delimitadores. Un exceso o estructura inválida no se trunca para producir éxito.

`all_source_state_declarations_matched=true` se refiere SOLO al inventario de
estado y al perfil léxico admitido. No prueba que el programa sea Solidity válido,
que solc produjera el AST, que todos los nodos AST sean correctos ni que haya
seguridad, explotación, autorización o compatibilidad total de una actualización.
La normalización de tipos reutiliza `source_types`; no es un compilador
independiente. El resultado mantiene `compiler_executed_here=false` y
`source_syntax_reparsed=false` para la gramática completa.

Una sintaxis fuera del perfil da `DECLARATION_INVENTORY_REVIEW_REQUIRED`, con
inventario completo sin comprobar; una contradicción de inventario/tipo/rango
rechaza el expediente. Las diferencias estructurales y límites de las capas
anteriores continúan visibles. No se acepta un `PASS` declarado por el emisor.

## Uso

El manifiesto esperado debe usar `schema_version: 4`, manteniendo los demás
campos existentes. No se introducen comandos de red, compilador o ejecución.

```bash
python3 -m superhunter review-compiler-layout \
  --expected /privado/expected-v4.json \
  --before-input /privado/before-input.json --before-output /privado/before-output.json \
  --after-input /privado/after-input.json --after-output /privado/after-output.json \
  --out /privado/revision-nueva
python3 -m superhunter verify-compiler-layout \
  --expected /privado/expected-v4.json --bundle /privado/revision-nueva
python3 -m unittest discover -s superhunter/tests -p test_solidity_inventory.py -v
```

La verificación vuelve a leer fuentes, recalcula los hechos y comprueba el
manifiesto externo. Degradar v4 a v3 o recalcular solo COMPLETE.json no sustituye
esa referencia. Los paquetes contienen código privado y deben conservarse fuera
del checkout público. El informe resumen omite el código y los nombres.

Referencia primaria de gramática consultada el 5 de noviembre de 2026:
https://docs.soliditylang.org/en/v0.8.30/grammar.html

Los controles incluidos usan fuentes benignas y AST/JSON construidos explícitamente
para probar el perfil. No se etiquetan como salidas de un compilador ejecutado.
