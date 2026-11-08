# Expediente con secuencia contable obligatoria — perfil v2

Esta ampliación conecta los cuatro verificadores ya existentes: políticas de
programa, diagnóstico estático importado, conciliación de balances y recorrido
ordenado del libro. No compila Solidity, no ejecuta una PoC, no adquiere estados
por RPC ni confirma una vulnerabilidad. Los escenarios de validación son propios
y sintéticos; el diagnóstico de Slither usado como fixture no lo produjo Slither.

## Contrato explícito y compatibilidad

El perfil v1 conserva sus tres paquetes y su interfaz. Ahora declara
`sequence_required=false`, `ordered_model_checked=false` y muestra que el orden
NO se comprobó. No se permite pasarle una secuencia para que la ignore.

El perfil v2 exige `schema_version=2` en el contexto externo, un cuarto hash bajo
`evidence_manifests.sequence` y un objeto `sequence_binding` con dos SHA-256:
`ledger_sha256` y `sequence_sha256`. Los dos son hashes de las representaciones
JSON canónicas definidas por `safe_io.canonical`, no de cadenas inventadas ni de
una reserialización que omita campos. El resto del contexto mantiene los campos
v1: candidato, programa, cadena, bloque, enlace de cuentas y alerta seleccionada.

Los originales de los cuatro paquetes se capturan sin alterarlos. El manifiesto
de la secuencia debe corresponder al hash externo; su libro completo debe ser
canónicamente idéntico al `input.json` del paquete de balances. No basta con que
comparta case_id, dirección, totales o bloque. También se contrastan el estado
agregado y las identidades devueltas por cada verificador.

`verify-case` exige el candidato y contexto externos esperados. No los toma del
propio paquete: un manifiesto recalculado no permite quitar el perfil v2, sustituir
el orden o cambiar de expediente sin que difiera de esas referencias. La autoría
y corrección de las referencias externas siguen siendo responsabilidad de quien
las aporta; los hashes no son autorización, firma ni prueba de estado blockchain.

## Estados

- Orden consistente y demás verificaciones completas: `CASE_REVIEW_REQUIRED`.
- Contradicción en una secuencia con cobertura declarada completa:
  `CASE_REVIEW_BLOCKED`, razón `DECLARED_SEQUENCE_CONTRADICTION`.
- Orden/cobertura desconocidos o presupuesto insuficiente:
  `CASE_REVIEW_INCONCLUSIVE` (salvo que exista además un motivo bloqueante).
- Política vencida, rechazada o contrato excluido: `CASE_REVIEW_BLOCKED` aun cuando
  el orden aritmético sea correcto.
- Identidad de evidencia incompatible: error, sin emitir expediente favorable.

Una contradicción del modelo de transferencias es un problema de los datos o
supuestos que requiere revisión. No demuestra insolvencia, drenaje, causalidad de
una alerta, fallo de contrato o severidad. `order_authenticated=false` y los
indicadores de ejecución/vulnerabilidad continúan en false. Los perfiles no
representan automáticamente crédito, préstamos, rebases o tokens especiales.

## Comandos

Desde la raíz del paquete acumulativo:

```bash
python3 -m superhunter review-case \
  --candidate /privado/candidate.json --context /privado/context-v2.json \
  --programs /privado/policies --static /privado/static \
  --balances /privado/balances --sequence /privado/sequence \
  --out /privado/new-case

python3 -m superhunter verify-case \
  --bundle /privado/new-case \
  --candidate /privado/candidate.json --context /privado/context-v2.json
```

`--sequence` es obligatorio para v2 y se rechaza para v1. El módulo de secuencias
existente crea su paquete mediante `replay-ledger`. No se generan candidatos,
políticas ni diagnósticos reales automáticamente. No hay red ni envíos.

Código 0: consistente para revisión humana, nunca hallazgo confirmado.
Código 1: bloqueado o inconcluso; se conserva el resultado esperado.
Código 2: error o evidencia rechazada.

## Conexiones comprobadas

La CLI existente dirige ambos perfiles a `case_review`. El componente QA
`case_review` depende ahora explícitamente de `ledger_sequence` y requiere pruebas
cruzadas contra paquetes de otros libros, orden incorrecto y degradación de perfil.
La bitácora nativa DIABLO añade la cuarta evidencia y `case.sequence.bind`, que
vincula los hashes externos del libro y del orden. El verificador reconstruye
esos eventos, el resumen y las decisiones históricas/actuales.

## Continuidad

Base recuperada: `SUPERHUNTER_secuencia_contable_1019.zip`, carpeta `codigo/`.
Se conservan sus fuentes y tests salvo los dos módulos modificados expresamente.
Los catálogos 27/50/25 no cambian y no se asignan palomitas amplias nuevas.

Los logs históricos 1055 y 1066 se localizaron, pero no su código asociado. El
primero registra una línea de trabajo similar de case_sequence. Esta ampliación
es una implementación nueva sobre la base recuperada, no una copia certificada
de aquella ni una recuperación de sus 36 tests. El segundo registra cambios de
políticas y caché de inventario; no se afirma incorporarlos aquí. El paquete
incluye las identidades y diferencia de inventarios para no perder esa deuda.

No se reescriben fuentes nativas, workflows ni main. La suite histórica completa
de NQC y su verificador global de aislamiento no forman parte de esta prueba del
paquete local. Consultar el recibo de validación adjunto para las ejecuciones
reales de esta entrega; los documentos y logs anteriores permanecen históricos.
