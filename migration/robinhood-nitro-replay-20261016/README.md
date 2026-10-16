# NQC: captura para replay Nitro y costes históricos — 2026-10-16

**El replay completo solicitado no se ha ejecutado.** La captura termina con
`BLOCKED_NO_AUTHORIZED_ARCHIVE_ENDPOINT`, salida 2 y **cero solicitudes RPC**.
No está configurado `NQC_ROBINHOOD_ARCHIVE_RPC`. El intento anterior al endpoint
público recibió 403 y el cupo del conector de esta conversación quedó agotado;
no se repitieron esas solicitudes ni se abrió otra sesión o suscripción.

Este expediente deja preparado el recolector y concilia el componente L1 de los
recibos existentes. No presenta esos resultados como un replay EVM completo ni
como un coste medido del ejecutor NQC.

## Costes que sí existen en la evidencia

`fee_accounting.py` autentica y vuelve a conciliar los 22 recibos del expediente
anterior. **8** informan `gasUsedForL1 > 0` y **14** informan cero. Los costes
totales de esta muestra van de **0.000011784432 a 0.000055604249184 ETH**.
Son operaciones históricas de terceros con tamaños y rutas diferentes; este
rango no sirve como presupuesto garantizado de NQC.

| Recibo | Gas total cobrado | Componente L1 en unidades de gas L2 | Comisión total ETH |
|---|---:|---:|---:|
| `0xf9e0d2e1…1974842`, ruta reconstruida antes | 568870 | 0 | 0.00003840668918 |
| `0x463862d0…7b1f1f04`, salida USDG del pool principal | 835886 | 1346 | 0.000030369410152 |

En el segundo caso quedan `834540` unidades después de restar el componente L1.
Al precio del recibo, las 1346 unidades equivalen a `48902872000` wei, es decir,
**0.000000048902872 ETH**, ya incluidos en el total. El desglose es una asignación
contable a partir del campo de gas reportado; no verifica la factura física de
blobs del secuenciador ni su asignación exacta por transacción dentro del lote.

La documentación de Robinhood confirma que ejecución y publicación de datos se
cobran juntas. `gasUsed × effectiveGasPrice` es el total del recibo; **sumarle otra
vez `gasUsedForL1 × effectiveGasPrice` duplicaría ese componente**. Si falta el
campo L1, el programa informa desconocido, no cero. Un cero observado tampoco
demuestra que DA sea gratuito en otras operaciones o momentos.

## Datos que faltan y captura preparada

El calldata del explorador anterior estaba truncado. El workflow histórico con
“prestate” en el nombre consultaba cabeceras y quoters; no capturaba un witness
completo de storage/código. No permite restaurar toda la ejecución por sí solo.

`capture_replay.py` trabaja exclusivamente sobre la transacción ya minada
`0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842`.
Al disponer de un endpoint autorizado realiza esta secuencia:

1. Verifica chain ID 4663, versión del cliente, transacción íntegra y recibo.
2. Comprueba los datos contra el recibo archivado, el hash del bloque 66744162,
   su padre 66744161 y la posición de la transacción dentro del bloque.
3. Solicita `debug_traceTransaction` con `callTracer` y logs; después con
   `prestateTracer`, en modo completo y en modo diferencias. `reexec: 0` exige
   acceso archive; no intenta reconstruir un número ilimitado de bloques.
4. Contrasta emisor, destino, calldata, gas, contratos de la ruta y multiconjunto
   de logs. Guarda los datos previos y las diferencias sin afirmar que tengan
   pruebas criptográficas ni que verifiquen por sí solos todo ArbOS.
5. Solicita `NodeInterface.gasEstimateComponents` en `0x…00c8`, con el calldata
   íntegro y emisor original, fijando el **hash del bloque padre**. Ese resultado
   se etiqueta como simulación al final del bloque anterior. No equivale al
   estado inmediatamente anterior a la transacción ni a una medición NQC.
6. Vuelve a verificar el bloque canónico antes de aceptar la captura. Conserva
   respuestas originales y SHA-256, sin registrar tokens de acceso del endpoint.

La secuencia normal contiene once solicitudes y tiene un techo de doce. Límite
de 20 segundos por petición, 10 segundos por traza, 8 MiB por respuesta y 32 MiB
por captura. Sin reintentos ni cambios de endpoint; un error HTTP detiene el
proceso. Un error RPC de la estimación NodeInterface se conserva como estimación
no disponible, aunque las trazas ya obtenidas puedan ser útiles.

La captura nativa permitiría revisar una reejecución del **tercero** en Nitro.
Aun si coincide, faltaría integrar/verificar la ruta en NQC y simular su cuenta,
paymaster y `handleOps` completos. Ni el calldata del tercero ni el DEX sintético
anterior representan ese coste. Tampoco un Anvil configurado como chain 4663
reproduce automáticamente ArbOS, sus precompilados o la tarifa DA.

Los límites pendientes se reflejan siempre en los campos
`nqc_full_route_replayed: false` y `nqc_cost_measured: false`. El recolector no
incluye ejecutor comercial ni certifica admisión del bundler. La comparación de
logs es por multiconjunto; el orden intercalado requiere revisión posterior.

## Cómo continuar

Se necesita un RPC **archive Nitro de Robinhood accesible desde este entorno**,
con lecturas históricas de los bloques indicados, `debug_traceTransaction`,
los dos tracers y `eth_call` de NodeInterface con bloque fijado. Un endpoint que
sólo entregue balances actuales no basta. La documentación oficial recomienda
endpoints archive para lecturas históricas.

Con el endpoint configurado mediante `NQC_ROBINHOOD_ARCHIVE_RPC`, ejecutar desde
la raíz del repositorio, usando un destino nuevo:

```bash
python migration/robinhood-nitro-replay-20261016/capture_replay.py \
  --out /tmp/nqc-nitro-capture-new
```

El script no recibe claves de wallet ni contiene RPC de firma, envío, despliegue
o modificación de estado. No habilita workflows. Si faltan acceso o capacidades,
guarda el bloqueo y termina; no completa los datos con simulaciones sintéticas.

Para reproducir lo que sí se verificó:

```bash
python migration/robinhood-nitro-replay-20261016/fee_accounting.py \
  --out /tmp/nqc-historical-fees.json
python -m unittest discover -s migration/robinhood-nitro-replay-20261016 \
  -p test_nitro_capture.py -v
```

**20 tests nuevos** verifican contabilidad, ABI, límites del recolector y rechazo
de trazas incompletas. Los fixtures de trazas son pruebas del parser, no ejecuciones
reales de la cadena. También pasan los nueve tests de aislamiento y los verificadores
de integridad. No se repitieron tests Solidity/Rust: no se modificó código de esos
lenguajes. La ejecución del recolector quedó bloqueada, no aprobada como replay.

Confianza: **alta** en las cuentas de los recibos archivados; **sin evidencia
suficiente** para afirmar el coste completo actual de NQC. El dato que desbloquea
la siguiente ejecución es acceso archive con las capacidades anteriores.

Fuentes primarias consultadas:

- [Robinhood: Gas & Fees](https://docs.robinhood.com/chain/gas-and-fees/).
- [Robinhood: conexión y endpoints archive](https://docs.robinhood.com/chain/connecting/).
- [Arbitrum: estimación de gas y componentes](https://docs.arbitrum.io/arbitrum-essentials/how-to-estimate-gas).
- [Geth: callTracer y prestateTracer](https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers).
- [Robinhood: nodo Nitro](https://docs.robinhood.com/chain/run-a-full-node/). Su
  configuración publicada parte de ArbOS 51 y la guía actual menciona ArbOS 61;
  no se supuso ninguna de ellas como versión acreditada del bloque histórico.
