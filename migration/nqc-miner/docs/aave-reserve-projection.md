# Índices y saldos escalados de Aave: revisión 11

`nqc-miner project-aave-reserve --input reserva.json` reproduce sin red la
actualización de una reserva y calcula el balance del usuario a partir de sus
saldos escalados. Recibe índices, tasas y tesorería de 128 bits; timestamps de
40 bits; factor de reserva de 16 bits; y saldos escalados de 256 bits. Los
enteros grandes son cadenas decimales canónicas. Un campo requerido ausente,
fuera de rango o ambiguo es un error de entrada, nunca un cero inferido.

## Qué calcula

- Interés lineal de liquidez y la aproximación polinómica de interés variable
  de la fuente retenida, con su orden de operaciones y redondeos.
- Actualización del índice de liquidez solo si su tasa es distinta de cero;
  actualización del índice de deuda solo si existe deuda variable escalada.
- Intereses acumulados para tesorería: diferencia del índice, porcentaje del
  factor de reserva, conversión a saldo escalado y suma de 128 bits.
- Balance de colateral redondeado hacia abajo y balance de deuda redondeado
  hacia arriba, mediante las reglas de `TokenMath`.
- Salida de reserva sin cambios de índices al repetir la actualización en el
  mismo timestamp. El timestamp de la reserva sí avanza cuando se visita una
  reserva inactiva en un bloque posterior.

El interés no se aproxima con números flotantes ni una exponencial genérica.
Se conserva el polinomio exacto del contrato, sus operaciones unchecked y los
helpers que revierten sin datos. Las conversiones a 128 bits conservan el error
`SafeCastOverflowedUintDowncast` con sus argumentos; el desbordamiento de la suma
de tesorería produce el pánico aritmético original. Si ocurre una reversión, no
se devuelven índices o balances parciales.

## Referencia ejecutable

`fixtures/AaveReserveHarness.sol` importa las fuentes originales sin cambiar
sus bytes. Invoca directamente `ReserveLogic.cache`, `ReserveLogic.updateState`
y los helpers originales de `TokenMath`. La lectura externa `scaledTotalSupply`
devuelve un valor **suministrado sintéticamente** por el harness. Por tanto, se
prueba el recorrido de caché/actualización, no un token histórico autenticado.

La compilación usa solc 0.8.27 de hash fijado y los ajustes originales del pool.
Se guardan entrada, salida, layout de storage y hashes de cada fuente. REVM
recibe todas las posiciones de almacenamiento declaradas, explícitamente en
cero antes de cargar los datos sintéticos; no se inventan ceros para una prueba
histórica. El entorno de prueba usa Cancun, sin certificar el fork histórico.

La prueba principal contrasta 1106 entradas dos veces: una actualización, y una
segunda recarga de caché/actualización en el mismo bloque. Compara nueve valores
ABI, incluidos índices y timestamp de la caché, o todos los bytes de reversión.
Esto comprueba el caso de actualización repetida que aparece cuando deuda y
colateral usan la misma reserva. No ejecuta por ello el resto de la liquidación.

```sh
python research/build_aave_reserve_harness.py --compiler /ruta/solc-0.8.27 --output /ruta/compilacion-nueva
cargo test --locked --offline --test aave_reserve_tests -- --nocapture
nqc-miner project-aave-reserve --input /ruta/reserva.json
```

## Límites y siguiente integración

Los datos de reserva, el total escalado y los balances del usuario son entradas
aportadas. Aún hay que obtenerlos en el estado histórico correcto y autenticar
sus contratos. El comando no calcula la salud agregada/eMode, no recalcula las
tasas tras una operación y no ejecuta transferencias ni verifica liquidez.
La proyección de cada reserva tampoco demuestra la consistencia entre reservas.

Los balances proyectados son un insumo para los comprobadores de condiciones e
importes; todavía no se compone automáticamente una certificación entre estos
comandos. El próximo paso es verificar el consumo de colateral escalado, el tope
final de comisión, la quema de deuda y el déficit con el estado y dependencias
correctos. No se añadieron eventos históricos ni se cerró una fase operativa.
Avance global: **43/100**.
