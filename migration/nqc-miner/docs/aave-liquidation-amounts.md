# Importes de liquidación: núcleo de la revisión 11

`nqc-miner calculate-aave-amounts --input datos.json` calcula sin red el tramo
aritmético posterior a las condiciones iniciales y anterior a las operaciones
con tokens. Se vincula a la misma revisión histórica cuyo runtime se comparó
previamente, sin identificar por ello una versión semántica ni autenticar los
valores aportados.

Incluye unidades decimales; valoración de deuda con redondeo hacia arriba y
colateral hacia abajo; límite de cierre; importe solicitado; colateral disponible;
bonus; comisión de protocolo y rechazo `MustNotLeaveDust`. Los enteros son
exactos de 256 bits. Se distinguen reversiones vacías de los helpers assembly,
pánicos Solidity de desbordamiento/división y el error de polvo. Una reversión
no devuelve importes parciales. El JSON ambiguo o fuera de rango se rechaza.

## Reglas contrastadas con la fuente retenida

- El umbral del factor de cierre es estrictamente mayor que `0.95e18`.
- El límite del 50% puede aplicarse cuando tanto deuda como colateral del activo
  valen al menos `2000e8`. Ese 50% se calcula sobre la **deuda total** de la cuenta.
- Si se agota el colateral, el repago se recalcula con los redondeos originales.
- La comisión se calcula sobre el bonus; usa redondeo hacia arriba. Las cantidades
  devueltas todavía no incluyen la conversión posterior a saldos escalados ni el
  ajuste final de comisión por saldo disponible.
- Si quedan deuda y colateral, ambos deben alcanzar `1000e8` de valor restante.
  Agotar toda la deuda o todo el colateral evita ese rechazo concreto.

Los umbrales son constantes de esta fuente Ethereum retenida, en unidades base;
no se generalizan a otros despliegues. El bonus ya seleccionado según reserva o
eMode, los balances actualizados, salud y deuda total son entradas del llamador.
Este comando no calcula eMode, índices, salud ni las condiciones iniciales.

## Ejemplo sintético

Con balances de 6 decimales, precios de `1e8`, colateral `20000000000`, deuda del
activo `10000000000`, deuda total base `1000000000000`, salud
`970000000000000000`, bonus `10500`, comisión `1000` y solicitud máxima:

| Resultado | Unidades mínimas |
| --- | ---: |
| Deuda máxima / repagada | 5000000000 |
| Colateral para el liquidador | 5225000000 |
| Comisión en colateral | 25000000 |

No es un resultado histórico ni una ganancia: faltan adquisición del activo de
repago, venta del colateral, costes y la ejecución de transferencias.

## Referencia y pruebas

`research/build_aave_amount_harness.py` conserva las fuentes originales sin
modificar. Genera un contrato sintético con el tramo contiguo de importes y
polvo, sus constantes y estructura, copiados **byte por byte** de
`LiquidationLogic.sol` (`385c9761…bcf9a0`). La función de colateral se llama
directamente desde la biblioteca original importada. Se fijan el hash completo
de la fuente, los segmentos, todos los imports, el compilador y su entrada/salida.
No se copian los predicados Rust a la referencia Solidity.

Esta extracción excluye expresamente el contexto anterior y posterior: no es
`executeLiquidationCall` completo ni un replay de la transacción. El contrato
sintético se ejecuta en REVM con Cancun y un estado cerrado. Los resultados
comparan las seis cantidades ABI o todos los bytes de reversión. La selección
Cancun corresponde al harness; no certifica el fork histórico de Ethereum.

El conjunto principal contiene 2205 casos: límites exactos, valores extremos y
2048 casos con semilla fija. Una comprobación adicional verifica agotamiento del
colateral con repago y comisión redondeados hacia arriba. Se añaden pruebas del
CLI, de procedencia y de rechazo de una fuente original modificada.

```sh
python research/build_aave_amount_harness.py --compiler /ruta/solc-0.8.27 --output /ruta/compilacion-nueva
cargo test --locked --offline --test aave_amount_tests -- --nocapture
nqc-miner calculate-aave-amounts --input /ruta/datos.json
```

## Pendiente para certificar liquidabilidad real

Actualizar índices y saldos escalados; seleccionar eMode desde el estado; simular
consumo de colateral, déficit, quema y transferencias; autenticar dependencias,
oráculos y estado inmediatamente anterior a cada transacción; ejecutar bajo el
fork real, y reconciliar costes y resultados. Las observaciones anteriores siguen
siendo tres eventos y 48 estados al cierre del bloque. Este trabajo no agrega
nuevos eventos, no cierra una fase operativa y conserva el avance **43/100**.
