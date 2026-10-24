# Quema de deuda, déficit y reserva: Aave revisión 11

`nqc-miner calculate-aave-debt --input deuda.json` reproduce la contabilidad de
`LiquidationLogic._burnDebtTokens`, incluida su llamada a
`ReserveLogic.updateInterestRatesAndVirtualBalance`. Las respuestas del token
y de la estrategia de tasas son entradas explícitas; el comando no las verifica.

```json
{
  "borrower_reserve_debt": "100",
  "actual_debt_to_liquidate": "40",
  "has_no_collateral_left": true,
  "next_variable_borrow_index_ray": "1500000000000000000000000000",
  "current_scaled_variable_debt": "1000",
  "reserve_deficit": "5",
  "virtual_underlying_balance": "200",
  "reserve_id": 1,
  "user_configuration": "255",
  "reserve_factor": "1000",
  "token_burn": {
    "status": "return",
    "no_more_debt": true,
    "next_scaled_variable_debt": "933"
  },
  "rate_quote": {
    "status": "return",
    "liquidity_rate_ray": "10",
    "variable_borrow_rate_ray": "20"
  }
}
```

Este ejemplo es sintético; no demuestra consistencia entre una deuda nominal,
un saldo escalado y un token real. Los enteros son cadenas decimales canónicas
de 256 bits; déficit y liquidez virtual de entrada tienen 128 bits; `reserve_id`+tiene 16 bits. Los dos resultados externos son obligatorios y rechazan campos
extra o faltantes. Cualquiera puede ser `{"status":"revert","data":"0x"}`:
se conserva incluso una reversión vacía. El ámbito del adaptador admite bytes
hexadecimales canónicos en minúsculas, con un máximo declarado de 4096 bytes.

## Recorrido comprobado

- Si la deuda es cero, no se llama al token, se conserva el total escalado de
  la caché y se limpia el indicador de préstamo antiguo. No se interpreta un
  resultado externo no utilizado como una llamada que sí ocurrió.
- Con deuda, el importe a quemar es el repago si queda colateral o toda la deuda
  si ya no queda. Se convierte a unidades escaladas redondeando hacia abajo.
  Se usan exactamente el booleano y el total escalado devueltos por el token;
  no se infieren restándolos de los valores anteriores.
- La diferencia deuda menos repago aumenta el déficit solo cuando no queda
  colateral. Se preservan la resta comprobada, SafeCast a 128 bits y el posible
  desbordamiento de la suma de déficit.
- El indicador de préstamo se limpia únicamente si `noMoreDebt` lo requiere.
  El índice de reserva se comprueba en esa rama y se preservan los demás bits.
- La estrategia recibe el déficit ya aumentado, la deuda total convertida con
  redondeo hacia arriba y la liquidez virtual **anterior** a sumar el repago.
  El informe expone esos argumentos numéricos en `rate_inputs`.
- Después de recibir las tasas se convierten a 128 bits en el orden original.
  Por último se convierte el repago a 128 bits y se suma a la liquidez virtual.

Una reversión de token o estrategia se propaga en su punto exacto. Los errores
anteriores conservan prioridad. El informe no devuelve resultados parciales
cuando falla el recorrido. Sus indicadores de autenticación, elegibilidad y
activación siempre permanecen desactivados.

## Referencia y alcance

El harness importa y llama a la función interna original completa, sin extraer
ni modificar su cuerpo. También ejecuta los helpers originales de configuración,
déficit y actualización de reserva. El token artificial devuelve la respuesta
suministrada y la estrategia artificial devuelve tasas o errores suministrados.
Una segunda llamada de prueba revela los ocho argumentos ABI reales de la
estrategia mediante una reversión deliberada; esa sonda revierte sus efectos.

La comparación principal cubre 579 entradas: 579 llamadas de resultado y 500
sondas de argumentos en los casos exitosos, 1079 ejecuciones. Se comparan diez
palabras de resultado, argumentos de tasas, eventos completos y reversiones.
Las pruebas dirigidas añaden 24 llamadas. Se comprueba ausencia de eventos y
escrituras de storage del contrato después de las reversiones de resultado.
Las 256 posiciones dinámicas para bytes de error se declaran explícitamente en
el estado sintético; nunca se aplica una política de cero por omisión histórica.

Una prueba CLI conecta el resultado de colateral agotado con este comando y
comprueba la creación de déficit, conservando las respuestas externas como
supuestos. Esto no ejecuta una liquidación completa, el recorrido `_burnBadDebt`
sobre otras reservas, transferencias reales, incentivos del token o la fórmula
de la estrategia. Faltan implementación y estado histórico de dependencias,
salud/eMode, liquidez, secuencia intrabloque, fork real e integración operativa.

```sh
python research/build_aave_debt_harness.py --compiler /ruta/solc-0.8.27 --output /ruta/compilacion-nueva
cargo test --locked --offline --test aave_debt_tests -- --nocapture
```

Avance global: **43/100**, sin nueva fase operativa ni certificación económica.
