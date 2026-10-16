# NQC: ciclo histórico con estado real y simulación Nitro

**La ruta NQC completa, con cuenta, EntryPoint, paymaster y adaptador, funciona
en una simulación de Nitro sobre el estado anterior a una liquidación real.**
Produce **32.060665 USDG antes de gas**. La comisión nativa simulada es
**0.000057601054408 ETH**, incluido lo cobrado por Nitro; el paymaster transfiere
**0.000079616762214 ETH** al beneficiario del bundler. No son ingresos realizados.

El resultado corresponde exclusivamente al bloque **66744162**, índice de
transacción **1**, del 19 de septiembre de 2026. Se conserva el historial de
intentos; este expediente supera el bloqueo de acceso documentado en el PR
anterior sin modificarlo retroactivamente.

## Evidencia y alcance

El endpoint público de demostración que publica QuickNode permitió **29
solicitudes de lectura**: once de captura y dieciocho de diagnóstico/simulación.
No hubo cuenta nueva, suscripción, firma con una wallet real, despliegue remoto
ni transacción enviada. Las firmas de la fixture usan la clave pública de prueba
`0x1234`, igual que el laboratorio previo.

Se recuperaron 1636 bytes de calldata, trazas de llamadas, estado previo de 23
cuentas/126 slots y diferencias de estado. La transacción histórica es:
`0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842`.

La reproducción independiente en Anvil conserva el bytecode y storage capturados.
Coinciden los **21 eventos en orden**, **18 slots modificados**, el retorno y
**568870 unidades de gas**. Esto verifica esa ejecución contractual; no convierte
a Anvil en Nitro ni autentica criptográficamente todo el estado de la cadena.

La simulación NQC usa `debug_traceCall` con hash de bloque e índice fijados. Antes
de usar ese contexto se reprodujo allí la transacción original: mismo gas,
retorno y eventos. También se comprobó el runtime del EntryPoint en el bloque
padre: SHA-256 `674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5`.
El proveedor informa Nitro `v3.12.1+70fa99a`; no se verificó su binario.

Las sustituciones temporales provisionan únicamente las cuatro fixtures NQC,
el depósito del EntryPoint y el bundler de prueba. El depósito simulado es
**0.1 ETH** y el saldo del bundler **0.01 ETH**; son supuestos de financiación,
no dinero disponible ni mínimos requeridos. Los contratos, saldos, oracle y
liquidez del protocolo no se sustituyen. **112 lecturas de storage de los
contratos del protocolo** del ensayo local coinciden con la traza de Nitro.
El reloj nativo ArbSys devuelve correctamente el bloque L2 66744162.

## Integración y resultado económico

`NqcHistoricalNetRoute.sol` implementa la ruta fija observada:
wsNET → sNET → NET → pool NET/USDG → ejecutor NQC → Morpho/cuenta.
Sus selectores de retirada se verificaron contra las llamadas capturadas.
La venta se calcula con el incremento real del saldo NET del pool después del
impuesto. No fija un descuento universal del 5% ni presume exención para NQC.
Comprueba mínimos, activos esperados, inventario y deltas de balance.

| Magnitud | Simulación NQC en el índice histórico | Estado del bloque anterior |
|---|---:|---:|
| Resultado UserOperation | Éxito | Rechazo: posición sana |
| USDG que quedan en la cuenta | 32.060665 | 0 |
| Gas de la simulación Nitro | 853172 | 588563 |
| Comisión nativa de red, ETH | 0.000057601054408 | 0.00003963971805 |
| Cargo del paymaster, ETH | 0.000079616762214 | 0.0000502011612 |

La red cobra `feePayment − gasRefund`; esa diferencia coincide exactamente con
la suma de `feeCollection` y con la caída del saldo del pagador. El cargo del
paymaster coincide con `UserOperationEvent`, la caída del saldo ETH del
EntryPoint y el aumento del beneficiario. **No se suman ambos cargos como si
fueran dos comisiones de red.** Con un bundler externo, el cargo del paymaster
es el flujo relevante del patrocinador; operando ambos, se consolida la
transferencia interna y se contabiliza la comisión de red y demás costes.

Se restituyen **194.034131 USDG** a Morpho y se pagan **0.015442822 NET** de
impuesto. Los 29 eventos distintos de los emitidos por EntryPoint coinciden
en orden entre Anvil y Nitro. No quedan activos de esta ruta en el ejecutor
ni en el adaptador según las transferencias; el ensayo local comprueba el
saldo de la cuenta receptora.

La ruta local con mínimos de 40 USDG de excedente, o usando la cotización que
omite el impuesto, revierte y cobra gas. La prueba remota con el estado del
bloque anterior también revierte porque **Morpho considera sana la posición**.
El oracle devuelve valores diferentes en los dos contextos. No se ha aislado
qué parte del cambio proviene del tiempo, del estado o de las actualizaciones
del protocolo. Sí se demuestra que no basta reutilizar una oportunidad sin
comprobar su estado de ejecución.

## Nitro y DA

`NodeInterface.gasEstimateL1Component` recibe el calldata completo de `handleOps`.
En las consultas al bloque padre y al final del bloque seleccionado devuelve
cero para el componente L1 y su precio estimado. La contabilidad nativa de la
simulación concilia la comisión total sin añadir un cargo DA inventado.
**No demuestra DA gratuito en otros bloques ni verifica la factura física de
blobs del secuenciador.** Las consultas L1 se hicieron antes de normalizar el
bundler a EOA; el calldata NQC es idéntico y se conservan sus contextos exactos.

`gasEstimateComponents` completo sigue devolviendo `execution reverted` en los
intentos guardados. No se presenta como una estimación exitosa ni se atribuye
una causa no comprobada. El coste informado procede de la ejecución Nitro
exitosa en el índice correcto y de sus movimientos nativos, corroborados por
la diferencia de balances. Es una **simulación**, no un recibo minado de NQC.

El gas local de NQC es 874544, distinto de 853172 en Nitro. Se conservan ambos;
no se usa Anvil como sustituto de la medición nativa ni se atribuye toda la
diferencia a un precompilado sin demostrarlo.

## Límites y siguiente decisión

- Las fixtures se consideran previamente desplegadas. Faltan costes de
  despliegue, creación de cuenta, infraestructura, staking y capital inmovilizado.
- No hay patrocinador comprometido ni admisión de producción acreditada. Siguen
  vigentes los límites del paymaster sobre stake, validación y política comercial.
- Es un único caso histórico seleccionado; no mide frecuencia, competencia,
  prioridad de inclusión ni probabilidad de capturar una operación futura.
- No se verificaron pruebas criptográficas de estado ni se ejecutó un nodo Nitro
  independiente. El proveedor y sus trazas siguen siendo parte de la confianza.
- No se acreditan ingresos propios. Sin una conversión ETH/USDG y los demás
  costes, no se publica un beneficio neto en USDG.

La evaluación técnica pasa de ruta pendiente a **viabilidad histórica demostrada
en simulación**. La siguiente prueba comercial es medir captura repetible y
fallos con decisiones tomadas antes de cada oportunidad, y cerrar la admisión
del bundler y financiación sin recurso al fundador. Ningún saldo simulado
resuelve por sí solo esos puntos.

## Reproducción

Desde la raíz, con las dependencias y toolchain fijados en el laboratorio previo:

```bash
python migration/robinhood-real-state-replay-20261016/prepare_cycle.py \
  --dependencies /ruta/dependencias --foundry-bin /ruta/foundry \
  --solc /ruta/solc-0.8.23 --build /tmp/nqc-build-nuevo
python migration/robinhood-real-state-replay-20261016/local_replay.py \
  --anvil /ruta/foundry/anvil --out /tmp/nqc-historico-nuevo
python migration/robinhood-real-state-replay-20261016/nqc_local_cycle.py \
  --foundry-bin /ruta/foundry --build /tmp/nqc-build-nuevo --out /tmp/nqc-ciclo-nuevo
python migration/robinhood-real-state-replay-20261016/audit_result.py \
  --out /tmp/nqc-auditoria.json
python -m unittest discover -s migration/robinhood-real-state-replay-20261016 \
  -p test_result.py -v
```

Las lecturas remotas son explícitas mediante `nitro_read.py --requests … --out …`.
Los cuerpos exactos están en los registros `requests.json`; no se repiten durante
los tests offline. El lector limita métodos, bloques, destinos de overrides,
tamaño de respuestas y duración. Se detiene ante errores HTTP, sin reintentos.

Validación: **16 tests Python**, **9 de aislamiento**, reproducción histórica y
los tres casos del ciclo NQC. Una segunda compilación y ejecución desde copias
nuevas confirma los resultados. Los 377 blobs de origen se conservan. No cambió
Rust ni se repitieron suites Rust ajenas a este cambio.

Intentos conservados: falta inicial de saldo del bundler; rechazo de NodeInterface;
normalización de una delegación EIP-7702 existente en la dirección de prueba a
una EOA hipotética (sin cambio del resultado). En desarrollo local se corrigieron
checksums de literales, espera del recibo y reconstrucción del orden de logs por
`position` cuando la traza no informa `index`. Las comprobaciones finales pasan.

Fuentes primarias consultadas el 16 de octubre de 2026:

- [QuickNode: archive Robinhood](https://www.quicknode.com/docs/robinhood/api-overview).
- [QuickNode: trazas y endpoint público de demostración](https://www.quicknode.com/docs/robinhood/debug_traceTransaction).
- [QuickNode: debug_traceCall](https://www.quicknode.com/docs/robinhood/debug_traceCall).
- [Geth: trazas e índice de transacción](https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-debug).
- [Geth: sustituciones temporales de estado](https://geth.ethereum.org/docs/interacting-with-geth/rpc/objects).
- [Arbitrum: estimación y componente L1](https://docs.arbitrum.io/arbitrum-essentials/how-to-estimate-gas).
- [Arbitrum: NodeInterface](https://docs.arbitrum.io/arbitrum-essentials/nodeinterface/overview).
