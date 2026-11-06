# Conciliación de efectos persistentes EVM — perfil fijo

Esta ruta conecta los controles EVM propios existentes con el motor de
conciliación. No ejecuta contratos arbitrarios ni representa balances de tokens.
Las unidades son exclusivamente las variables enteras `debit` y `credit` de
los tres controles conocidos. No se inventan direcciones de tokens, precios,
commits, hashes de bloque ni datos de una red para adaptar esas variables a una
contabilidad monetaria.

## Flujo y decisiones

1. `evm_execution.execute` regenera las fuentes fijas, compila con el solc fijado,
   resuelve sus propiedades con Z3 y ejecuta constructor y llamadas en la EVM fijada.
2. Se comprueban todos los enlaces de código, calldata, estado anterior, retorno,
   estado posterior y reversión mediante el verificador existente.
3. El nuevo `evm_accounting.derive` vuelve a decodificar los saldos desde el stdout
   y almacenamiento de la EVM. No obtiene los saldos de la referencia matemática.
4. La intención de mover una cantidad se obtiene de la llamada/código fijo ligado,
   NO se inventa una transferencia igual al delta observado para hacer cuadrar todo.
   Solo una llamada terminada correctamente crea el movimiento correspondiente.
   Reversión por precondición, aserción o gas no crean movimientos aplicados.
5. `balance_reconciliation.reconcile_internal_units` contrasta las ecuaciones
   mediante las rutas de enteros y Decimal existentes, por llamada y por caso.
   Una diferencia individual bloquea el resultado aunque el total sea cero.
6. AuditLog original de DIABLO liga el resultado y cada fila al material original.
   El paquete privado conserva la ejecución completa, no solo los totales.

`derive` es una comprobación de datos capturados y **no afirma haber ejecutado la
EVM**. `create` y `replay` sí llaman al ejecutor nativo. El replay genera nuevamente
los controles desde el código actual: nunca utiliza las consultas, fuentes o
calldata del paquete como instrucciones de ejecución. Compara todos los artefactos.

## Uso

Desde la raíz de `codigo/`, usando los binarios previamente verificados:

```bash
python3 -m superhunter run-evm-accounting \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm --out /ruta/privada/contabilidad-nueva
python3 -m superhunter replay-evm-accounting \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm --bundle /ruta/privada/contabilidad-nueva
```

No se admiten `--rpc`, `--target`, fuentes ni calldata personalizados. La salida
requiere una carpeta nueva fuera del checkout. Código 0: esta comprobación fija
terminó; código 2: rechazo/error, nunca una confirmación de vulnerabilidad.
El módulo está registrado en el gate de QA y en la CLI. La aceptación EVM se
realiza separadamente: el `review-platform` general no se describe como ejecución
nativa solo porque pasen sus pruebas unitarias con capturas y mocks de orquestación.

## Resultado esperado de estos controles conocidos

Tres constructores, 18 llamadas: cinco aplicadas, ocho reversiones de precondición,
dos de aserción y tres agotamientos de gas. Se comprueban 36 celdas por llamada y
los tres balances agregados de dos celdas cada uno.

| Control | Debit final | Credit final | Unidades del modelo trasladadas |
|---|---:|---:|---:|
| conservation | 6 | 9 | 9 |
| delayed_credit | 10 | 5 | 5 |
| unreachable | 15 | 0 | 0 |

El estado tentativo con credit=10 del tercer paso incorrecto se etiqueta como
modelo descartado, NO almacenamiento observado. Su reversión deja credit=5.
No se suma una cifra económica entre contratos/variantes distintas.

## Límites expresos

- No es un lector universal de eventos ERC20 ni de balances de usuarios.
- No mide costo monetario del gas; revertir almacenamiento NO demuestra gas gratis.
- `monetary_valuation_usd`, `gas_cost_usd` y `financial_loss_usd` permanecen desconocidos.
- La conciliación es aritmética, no prueba causal de explotación ni una garantía de seguridad.
- El agotamiento de gas no permite certificar la propiedad bajo un presupuesto mayor.
- Se reutilizan las mismas herramientas al reproducir; no es una segunda EVM independiente.
- Enteros y Decimal son cálculos distintos sobre el mismo modelo, no fuentes de evidencia independientes.
- La captura de tests proviene de una ejecución real, pero releerla no cuenta como nueva ejecución.
- Se mantiene pendiente el análisis general, el benchmark ciego y la publicación del acumulado.

Referencias primarias: Solidity 0.8.30, Expressions and Control Structures
(https://docs.soliditylang.org/en/v0.8.30/control-structures.html), y firmas de
Geth (https://geth.ethereum.org/downloads). La identidad del ejecutable Geth
recibido se verificó de nuevo con GnuPG y la huella oficial completa.
