# Colateral agotado y comisión final: Aave revisión 11

`nqc-miner calculate-aave-collateral --input colateral.json` calcula el consumo
de colateral escalado y el límite final de la comisión. Es un cálculo offline
sobre entradas suministradas. No ejecuta ni autentica el token.

```json
{
  "liquidity_index_ray": "1500000000000000000000000000",
  "borrower_scaled_collateral_balance": "3",
  "collateral_to_liquidator": "2",
  "protocol_fee_collateral": "1",
  "collateral_price": "1",
  "collateral_decimals": 0,
  "total_collateral_base": "4",
  "post_liquidator_scaled_balance": "1"
}
```

Los enteros grandes son cadenas decimales canónicas de 256 bits. Decimales es
un entero de 8 bits. Se rechazan campos extra, faltantes, ceros iniciales,
notación científica, negativos y desbordamientos de representación. Que una
entrada quepa en esos tipos no significa que sea un estado válido del protocolo.

## Reglas comprobadas

El contrato convierte por separado el importe del liquidador y la comisión a
unidades escaladas, redondeando ambos hacia arriba. Suma los dos resultados y
limita el consumo al saldo escalado original. El ejemplo consume las tres
unidades escaladas aunque los importes nominales sumen tres y el balance
nominal sea cuatro. Se mantiene el desbordamiento de la suma antes del límite.

El consumo se convierte de nuevo a balance, redondeando hacia abajo, y luego a
valor base. La igualdad con el colateral total suministrado determina
`has_no_collateral_left`. El flag de la reserva se debe limpiar si esa igualdad
se cumple o si se agota su saldo escalado. Son condiciones distintas: puede
haber otras reservas con colateral, o un sobrante cuyo valor base redondee a cero.

La comisión final usa **otro momento del estado**: el saldo que devuelve
`scaledBalanceOf` después de la operación del liquidador. Por eso
`post_liquidator_scaled_balance` es obligatorio y no se deduce de una resta.
Si la comisión escalada supera ese saldo, el contrato la limita al saldo y
recalcula el importe nominal hacia abajo. El límite es estricto (`>`).
Una comisión inicialmente distinta de cero sigue entrando al bloque de
transferencia aunque el límite la reduzca a cero; el informe conserva esa señal.

Si el cálculo revierte, el informe devuelve los bytes completos y no publica
resultados parciales. Las reversiones vacías de los helpers se distinguen del
pánico de aritmética. El informe mantiene desactivadas autenticación,
elegibilidad y activación incluso cuando el cálculo pasa.

## Referencia y composición

El constructor extrae byte por byte la estructura, unidad, aritmética de consumo,
expresión de limpieza y bloque de comisión de la fuente LiquidationLogic
retenida. Importa los helpers originales sin editarlos y conserva sus hashes.
La referencia usa un token artificial que devuelve el saldo posterior aportado
y registra el importe/comisión de la llamada. No reproduce transferencias,
recompensas, permisos, liquidez, escrituras del bitmap o emisión de eventos.

Se comparan ocho palabras ABI o todos los bytes de reversión en REVM/Cancun.
Hay 1089 casos principales y siete ejecuciones dirigidas. Una prueba Python
ejecuta realmente los comandos de reserva, importes y colateral y pasa los
resultados entre ellos, usando el caso de redondeo del ejemplo. Esa prueba
delimita una composición sintética; el estado posterior sigue suministrado.

Los fragmentos de consumo y comisión no son contiguos en la liquidación real.
Entre ambos quedan quema de deuda y operación del colateral, capaces de
revertir o cambiar el estado. El orden de errores del comando solo corresponde
al harness extraído, no al recorrido completo del pool. Faltan esas operaciones,
déficit, salud/eMode, dependencias y estado histórico autenticados, tasas,
transferencias y el fork real. La prueba no acredita rentabilidad.

```sh
python research/build_aave_collateral_harness.py --compiler /ruta/solc-0.8.27 --output /ruta/compilacion-nueva
cargo test --locked --offline --test aave_collateral_tests -- --nocapture
```

Avance ponderado: **43/100**, sin nueva fase operativa cerrada.
