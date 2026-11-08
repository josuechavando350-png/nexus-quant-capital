# Secuencias contables: comprobación temporal delimitada

## Qué ejecuta

`ledger_sequence.py` utiliza el libro `declared-token-ledger-v1` existente y una
secuencia explícita que identifica cada movimiento exactamente una vez.
La conciliación previa comprueba saldos finales; este módulo comprueba además
que cada débito disponga de saldo en ese punto y cada crédito respete uint256.
El orden de las listas no se interpreta como orden de transacción: se requieren
posiciones únicas declaradas. Posiciones repetidas, movimientos omitidos o
adicionales y tipos ambiguos bloquean la entrada.

Se ejecutan dos rutas aritméticas: estado mutable de enteros y ecuaciones Decimal
sobre apertura, créditos acumulados y débitos acumulados. Ambas comparten el
modelo declarado y validación; no son dos EVM ni dos fuentes on-chain. Una
discrepancia entre sus resultados impide crear el paquete.

## Perfil y límites

El perfil `declared-ordered-uint256-transfers-v1` supone transferencias
individuales aplicadas en el orden declarado. No representa cuentas de crédito,
deuda, rebases, callbacks, tokens fee-on-transfer, logIndex ni semántica EVM.
Si ese perfil no representa el activo, no debe usarse su veredicto como conclusión
sobre el protocolo. Los endpoints `null` son entradas/salidas de la frontera del
libro: no se verifican saldos externos, suministro global ni autorización.

El algoritmo se detiene antes de aplicar un movimiento imposible. El estado
emitido es el último prefijo sustentado; el resto queda sin ejecutar. Un problema
posterior no se infiere. El estado final declarado solo se compara cuando todos
los movimientos fueron aplicados correctamente.

Estados:
- `LEDGER_SEQUENCE_CONSISTENT`: todas las precondiciones y saldos coinciden dentro
  del perfil y de las declaraciones completas suministradas.
- `LEDGER_SEQUENCE_CONTRADICTION`: una precondición o saldo final contradice ese
  modelo declarado completo. NO equivale a vulnerabilidad confirmada.
- `LEDGER_SEQUENCE_INCONCLUSIVE`: orden desconocido, movimientos incompletos o
  presupuesto agotado. Se conservan los problemas observados sin inventar
  cobertura del resto.

Un prefijo imposible se informa aunque el presupuesto no permita examinar su
sufijo, siempre que el orden y la cobertura estén declarados completos. La firma
de un paquete no autentica el orden o su cobertura y no promueve su estado.

No hay pérdidas en USD, fondos robables ni severidad calculados aquí. No se
consultan precios, contratos, RPC ni red. No se ejecutan Solidity, Forge o PoCs.

## Interfaz

```bash
python3 -m superhunter replay-ledger \
  --ledger /privado/ledger.json --sequence /privado/sequence.json \
  --ledger-sha256 <sha256-del-json-canonico-del-libro> \
  --sequence-sha256 <sha256-del-json-canonico-de-la-secuencia> \
  --out /privado/expediente-nuevo

python3 -m superhunter verify-ledger-replay \
  --bundle /privado/expediente-nuevo \
  --ledger-sha256 <hash-externo-del-libro-esperado> \
  --sequence-sha256 <hash-externo-de-la-secuencia-esperada>
```

Los hashes de identidad se calculan con `safe_io.canonical`: JSON ordenado,
separadores compactos, ASCII y salto de línea final. No son los hashes del texto
original indentado. El manifiesto conserva aparte los hashes de esos bytes
originales. Los hashes esperados deben mantenerse fuera del paquete; no
constituyen firma o autenticación de la blockchain.

La secuencia requiere schema_version=1, profile, ledger_sha256, order_coverage,
steps_budget y entries. Cada entrada tiene flow_id y position. La correspondencia
con cadena/bloque/commit es la declaración que ya contiene el libro y se conserva
sin añadir afirmaciones de autenticidad. `unknown` nunca provoca ejecución de
un orden escogido arbitrariamente.

Código 0: consistencia limitada al modelo; 1: contradicción o inconclusión;
2: error de entrada/evidencia. Ninguno indica una vulnerabilidad descubierta.
Los archivos son privados (0600/0700), con salida nueva y sin sobrescritura.
La evidencia incluye originales, trazas de estados intermedios mediante hashes,
AuditLog nativo DIABLO, identidad de código y reporte. El verificador recalcula
ambas rutas y cada relación de la bitácora. El resumen no imprime cuentas o
cantidades privadas; el paquete completo sí contiene los datos originales.

## Conexión real

CLI -> validación -> conciliación NQC local -> dos cálculos de secuencia ->
AuditLog DIABLO -> evidencia -> verificación independiente de proceso.

El componente figura en `quality.COMPONENTS`, con pruebas obligatorias.
`review-platform` ejecuta cuatro controles conocidos bajo `sequence/` y
`verify-platform` los vuelve a comprobar y vincula sus hashes al reporte conjunto.
El expediente Candidate anterior no se altera ni recibe una confirmación nueva.
La etapa temporal no autentica ni amplía permisos de ningún programa.

## Controles sintéticos incluidos

Mismo libro y mismos saldos: vault empieza con 10 unidades, alice y fee con 0.
`fund` transfiere 7 de vault a alice; `send`, 7 de alice a fee.
Orden correcto: consistente. Orden inverso: fondos insuficientes antes de aplicar
el primer movimiento, aunque el conciliador agregado da RECONCILED en ambos.
Con cobertura incompleta: inconcluso. Con presupuesto de un paso: un movimiento
aplicado, otro pendiente, inconcluso. Son modelos contables inocuos, no ejemplos
de explotación de protocolos.

Los tests incluyen además overflow transitorio, diferencias de una unidad,
valores mayores que la precisión de float, 96 órdenes contra un tercer cálculo
de referencia con Fraction, alteraciones de manifiestos y cambios de fuentes.
No se instala ninguna dependencia nueva.
