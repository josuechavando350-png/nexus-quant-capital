# Revisión estructural de almacenamiento Solidity

## Alcance exacto

`storage_layout.py` compara dos artefactos suministrados con el formato público
`storage`/`types` de Solidity. No invoca un compilador, no carga un contrato ni
observa una red. La revisión identifica diferencias en las declaraciones: no
certifica que el artefacto corresponda a una compilación, a un commit real o a
una implementación desplegada. Tampoco asigna severidad o habilita upgrades.

El análisis trata slots y tamaños como enteros exactos. Comprueba posiciones,
offsets, empaquetado, solapamientos, límites numéricos y referencias de tipos.
Genera huellas estructurales de tipos primitivos, mappings, arrays y structs,
incluidos los tipos de sus componentes. Los identificadores internos del
compilador y `astId` no se utilizan como identidad semántica entre compilaciones.
Los nombres de miembros de estructuras sí forman parte de esta revisión
conservadora; un renombrado anidado puede señalarse como cambio de estructura
sin que ello demuestre corrupción de almacenamiento.

Los tipos no alcanzados desde las variables de storage no son afirmaciones de
cobertura. Los intervalos para mappings y arrays dinámicos corresponden solo
al slot cabecera. No se calculan direcciones Keccak ni valores de sus elementos.

## Estados

- `LAYOUT_PRESERVED_IN_PROFILE`: las declaraciones anteriores tienen la misma
  posición y estructura dentro del perfil soportado; las adiciones se encuentran
  después del área ocupada anteriormente. Permite una adición empaquetada en el
  espacio restante del último slot cuando corresponde. No es aprobación para
  producción ni garantía semántica.
- `LAYOUT_CHANGE_DETECTED`: cambió la posición de una declaración identificada
  o la estructura de su tipo. Esto es un cambio observado, no una vulnerabilidad
  demostrada. Una migración explícita puede requerir una evaluación diferente.
- `LAYOUT_REVIEW_REQUIRED`: renombrados o eliminaciones ambiguas, reservas
  `__gap`, cambios de compilador, tipos fuera del perfil o ausencia de estado
  anterior. No convierte un caso no soportado en éxito.
- `LAYOUT_REVIEW_ERROR`: esquema o evidencia inválidos, referencias incompatibles,
  límites excedidos, solapamiento o resultados derivados alterados.

No se admite automáticamente consumo de gaps, almacenamiento no estructurado,
ERC-7201, acceso por assembly, transient storage, tipos recursivos, enums,
funciones o tipos personalizados. No se comprueban inicializadores, permisos
de upgrade, código ejecutable ni herencia semántica. El límite es intencional:
no interpretar silenciosamente extensiones desconocidas del formato.

## Identidad y enlace

El manifiesto externo fija repo, contrato, commits declarados y hashes de ambos
artefactos. `verify-layout` exige de nuevo ese manifiesto externo; una copia
incluida en el paquete no sustituye la referencia esperada por quien verifica.
Esto liga bytes, no autentica al autor ni a GitHub. Los cambios de clave, cuenta
u origen deben examinarse por separado.

El paquete conserva originales, resultado, resumen y `AuditLog` nativo de DIABLO.
Los eventos deterministas usan una fecha de referencia constante, explícitamente
marcada como NO cronología real. La evidencia generada permite volver a calcular
la comparación. El registro incluye la identidad del código verificador.

La CLI despacha al módulo; el control de calidad registra sus dependencias y
pruebas negativas obligatorias. El recorrido conjunto ejecuta esas pruebas y
muestra el componente en su informe. Los controles de layout por comandos son
una demostración adicional separada: no se presentan como una nueva etapa EVM.

## Ejecución

```bash
python3 -m superhunter review-layout \
  --manifest /privado/expected.json \
  --before /privado/before.json --after /privado/after.json \
  --out /privado/revision-nueva

python3 -m superhunter verify-layout \
  --bundle /privado/revision-nueva --expected /privado/expected.json
```

Salida 0 significa preservación según el perfil; 1 significa cambio/revisión;
2 indica entrada o evidencia inválida. Todos los estados requieren revisión
humana. Los directorios nuevos son 0700 y los archivos 0600. El paquete completo
es privado; la consola/resumen no repiten nombres, rutas ni contenido del layout.

Artefacto de entrada (esquema, no valores de prueba):

```text
schema_version: 1
target: {repo, commit, contract}
compiler_version: versión 0.8.x declarada
storage_layout: {storage: entradas estándar, types: descriptores estándar}
```

Manifiesto:

```text
schema_version: 1
repo: owner/repo
contract: unidad.sol:Nombre
before: {commit: SHA de 40 caracteres, sha256: hash exacto del artefacto anterior}
after:  {commit: SHA de 40 caracteres, sha256: hash exacto del artefacto nuevo}
```

Se mantienen como strings decimales canónicos `slot` y `numberOfBytes`.
Offsets/astId usan enteros, nunca booleanos. Los límites son 512 tipos, 2048
entradas, profundidad 32 y 2 MB por artefacto. Se rechaza truncar para aprobar.
La API no descubre objetivos, ejecuta pruebas de explotación, actualiza
contratos ni envía reportes externos.

## Fuentes de interfaz

Se consultó la documentación oficial de Solidity 0.8.30 y OpenZeppelin:

- https://docs.soliditylang.org/en/v0.8.30/internals/layout_in_storage.html
- https://docs.openzeppelin.com/upgrades-plugins/writing-upgradeable

Implementación original del comparador. No se copiaron implementaciones de
Slither, OpenZeppelin ni herramientas comerciales, y no se añadieron dependencias.
La salida del compilador es experimental: el perfil conservador no implica
compatibilidad con todas las versiones o extensiones presentes y futuras.

## Validación

Los ejemplos incluidos son modelos JSON propios con forma de artefactos del
compilador. No son salidas inventadas atribuidas a una ejecución: **solc no se
ejecutó**. Incluyen adición al final, reordenación con idéntico tamaño total,
cambio uint/int de igual anchura, renombrado, tipo no soportado y renumeración
de IDs. El registro de entrega externo al código contiene resultados, comandos,
hashes y límites de las ejecuciones realmente realizadas.
