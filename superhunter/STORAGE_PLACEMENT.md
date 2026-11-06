# Reconstrucción de posiciones de almacenamiento — perfil v3

Esta unidad verifica una restricción adicional de los artefactos suministrados:
la posición de cada cabecera de variable debe corresponder a la regla de empaquetado
calculada desde sus tipos y el orden de sus declaraciones. NO ejecuta solc ni EVM.

## Integración

El manifiesto externo de `review-compiler-layout` y `verify-compiler-layout` admite
`schema_version: 3`. Conserva los campos de v2. Primero se comprueban fuentes,
AST, cobertura de declaraciones y correspondencia de tipos mediante los módulos
existentes. Después se calcula la colocación mediante `storage_placement.py`.
Los perfiles 1 y 2 continúan disponibles, sin heredar esta garantía nueva.

El orden se obtiene de offsets en bytes de las declaraciones, no de sus IDs ni
del orden arbitrario de las filas del layout o del array AST. Los spans de las
declaraciones no pueden solaparse. Para cada variable se contrasta slot y offset
con lo calculado. La posición de la carga dinámica NO se sigue ni se interpreta.

La auditoría nativa de DIABLO incluye los nuevos hechos y la identidad de su
implementación. QA registra la dependencia de tipos separadamente y exige los
controles de posición incorrecta, perfiles no soportados y cálculo de referencia.

## Modelo explícito y sus límites

Solo Solidity 0.8.30 declarado, contrato individual sin herencia y cabecera
ordinaria `contract Nombre {` o `abstract contract Nombre {`, con espacios o
comentarios. La primera cabecera usa la base por defecto cero. Las cabeceras con
`layout at`, una base personalizada declarada en el AST, herencia y otros
compiladores generan revisión requerida. No se finge soportar esos casos.

Se admiten tipos elementales ya normalizados, arrays de longitudes literales,
arrays dinámicos, bytes/string y mappings. Los agregados alinean sus cabeceras
al límite de slot; las arrays fijas ocupan una región completa calculada.
Las cabeceras dinámicas reservan un slot pero no se verifican sus datos.

Dos implementaciones aritméticas distintas deben coincidir: cursor slot/offset
y cursor de dirección absoluta. Sus fórmulas de extensión de arrays también son
distintas. Comparten el modelo, la validación de esquema y la interpretación de
nombres de tipos: NO son dos compiladores independientes ni una prueba formal.
Arrays grandes se calculan algebraicamente, sin expandir cada elemento.

La correspondencia de cada tipo ya se comprobó desde su span de fuente en v2.
Un tipo no soportado impide declarar la colocación completa. Ni este perfil ni
los anteriores prueban que el AST enumere todas las declaraciones de una fuente:
un AST fabricado de forma coherente continúa siendo posible. No se comprueba
sintaxis/semántica completa, bytecode, assembly, valores desplegados o autorización.

## Resultados

- `HEAD_POSITIONS_RECONSTRUCTED`: todas las cabeceras declaradas corresponden al
  modelo soportado. No certifica una compilación, upgrade ni ausencia de fallos.
- `PLACEMENT_REVIEW_REQUIRED`: el perfil no permite concluir la colocación.
- `DECLARED_PLACEMENT_MISMATCH`: el artefacto contradice la colocación calculada;
  la importación falla sin producir un expediente de éxito.
- Un desacuerdo entre los dos algoritmos también bloquea la importación.

El verificador exige el mismo manifiesto externo. Degradar v3 a v2 o alterar el
resultado y recalcular COMPLETE.json no sustituye esa referencia ni el recálculo.

```bash
python3 -m superhunter review-compiler-layout \
  --expected /privado/expected-v3.json \
  --before-input /privado/before-input.json --before-output /privado/before-output.json \
  --after-input /privado/after-input.json --after-output /privado/after-output.json \
  --out /privado/revision-nueva
python3 -m superhunter verify-compiler-layout \
  --expected /privado/expected-v3.json --bundle /privado/revision-nueva
```

## Pruebas de esta entrega

44 pruebas nuevas. Incluyen cabeceras erróneas que el perfil v2 no contrastaba,
paquetes reescritos, perfiles degradados, arrays, límites de 256 bits,
orden AST/filas permutado, posición de variables, ausencia de efectos de red y
CLI en procesos separados. Otras 256 secuencias reproducibles de tipos escalares
se contrastan con un tercer cálculo discreto de ocupación de bytes.

Los controles contienen fuentes propias inocuas y AST/JSON explícitamente
sintéticos. No se presentan como resultados del compilador. El log de validación
registra qué se ejecutó y qué sigue pendiente, incluida la publicación remota.

Referencia primaria de las reglas del modelo, consultada el 5 de noviembre de 2026:
https://docs.soliditylang.org/en/v0.8.30/internals/layout_in_storage.html
