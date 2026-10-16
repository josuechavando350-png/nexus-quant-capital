# NQC: caducidad del patrocinio, presupuesto y admisión temporal

La fixture anterior devolvía `validationData=0`: una ruta vencida podía fallar
durante ejecución y cobrar gas al patrocinador. Esta prueba añade una ventana
finita durante validación y una autorización para una sola UserOperation.
EntryPoint v0.7 rechaza fuera de la ventana antes de ejecutar la ruta.

**Resultado: mejora técnica verificada; monetización todavía no demostrada.**
Se conservan 32.060665 USDG de excedente de ruta antes de gas en el mismo estado
histórico, con menor cargo al patrocinador. Los ETH y USDG son unidades distintas;
no se utiliza una cotización para presentar beneficio en dólares.

Base: [PR9](https://github.com/josuechavando350-png/nexus-quant-capital/pull/9),
commit `aed8a0ccfb80bffe055b17476664781a2f0b8a1d`. Solo se añaden archivos en
esta carpeta. Los contratos recuperados, workflows y clientes permanecen intactos.

## Qué se cambió y qué se mantuvo fijo

`NqcWindowedPaymasterFixture.sol` es un contrato de investigación para una
operación preaprobada, no un servicio de patrocinio desplegable por cada señal.
Solo admite el sender y el hash exactos suministrados por EntryPoint. El hash
v0.7 liga cadena, EntryPoint, nonce, calldata, límites/precios de gas y datos del
paymaster; la cuenta sigue verificando su firma. El máximo por operación es
**0.00024954124 ETH**. La validación descuenta el prefund completo del presupuesto
y nunca recicla esa reserva por haber gastado menos. Un revert de la transacción
completa revierte también la reserva.

Devuelve `validAfter`/`validUntil` finitos y contexto vacío, sin leer el reloj
desde el paymaster y sin `postOp`. EntryPoint verifica el tiempo. El constructor
limita esta política de laboratorio a ventanas de hasta 60 segundos. El saldo
compartido `budgetRemaining` sigue requiriendo revisión de admisión, storage,
stake y reputación; quitar `postOp` no acredita esos requisitos.

Las variantes usan ventanas de **1 y 31 segundos**, el mismo hash de UserOperation
`0x3bb989202b5f549e643a482368bc2a7e259815e00c3fc9b5bb79cd6dba5377e1`, la misma
firma pública de laboratorio, los mismos límites de gas y la misma caducidad L2.
Solo cambia la fixture del paymaster respecto de PR9. Los otros cinco overrides
son idénticos; no se reemplaza estado de Morpho, tokens, pool, oracle ni ArbSys.
Los balances de EntryPoint/bundler siguen siendo hipotéticos, no financiación real.

## Resultado en Nitro y quién paga

Bloque fijo **66744162**, índice **1**, timestamp `T=1789786800`, hash
`0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7`.
Se usa el runtime histórico de EntryPoint v0.7 autenticado en PR8. Las llamadas
remotas son `debug_traceCall` y lectura de cabecera, nunca envío de transacciones.

| Caso simulado | Resultado | Gas Nitro | Tarifa nativa ETH | Cargo al paymaster ETH |
| --- | --- | ---: | ---: | ---: |
| Ventana de 1 s, antes de T | AA32, sin ejecución | 87,087 | 0.000005879591718 | 0 |
| Cualquiera de las ventanas, exactamente T | Ruta completa | 814,917 | 0.000055018306338 | 0.000076653394686 |
| Ventana de 1 s, exactamente T+1 | Ruta completa | 814,917 | 0.000055018306338 | 0.000076653394686 |
| Ventana de 1 s, T+2; ventana de 31 s, T+32 | AA32, sin ejecución | 87,078 | 0.000005878984092 | 0 |

En T coinciden los **29 logs de protocolo** entre Anvil y Nitro y el excedente
es **32.060665 USDG** para ambas ventanas. El cargo al patrocinador baja
**3.72204%** frente a PR9; los límites de gas no se optimizaron en esta comparación.
El `UserOperationEvent` registra 1,118,799 unidades facturadas a 68,514,000 wei.
Esas unidades no son el `gasUsed` de la transacción Nitro.

La tarifa nativa se concilia de tres formas: pago inicial menos devolución,
suma de cobros nativos y caída de saldo del EOA. El cargo del patrocinador
coincide con la caída del saldo de EntryPoint y el aumento del beneficiario.
Es un reembolso interno al bundler: **no se suma otra vez a la tarifa de red**
al consolidar ambas entidades. Las diferencias de estado vencidas solo contienen
el EOA pagador y el almacenamiento de contabilidad de ArbOS.

La fixture no cobra tokens al ejecutor, no reparte el excedente con un financiador
y no convierte USDG en ETH para reponer depósitos. Esas funciones económicas
siguen pendientes; el excedente simulado por sí solo no vuelve autosuficiente
al patrocinio.

La tarifa nativa incluye los movimientos de comisiones observados por Nitro.
No se obtuvo una nueva descomposición separada de DA para estas variantes.
Los estimadores históricos de PR8 no garantizan DA gratuita futura. Creación de
cuenta/paymaster, stake, infraestructura, financiación y facturación comercial
quedan fuera de este ciclo histórico.

**Patrocinador protegido no significa sistema sin pérdidas.** Si un bundler
enviara el bundle ya vencido, gastaría la tarifa indicada aunque el paymaster
no pagara. Si ambos pertenecen al mismo fondo, la pérdida sigue siendo del fondo.

## Restricción de admisión encontrada

El código de Rundler fijado en commit
[`9852824c649fbe56fea9712b26d4188bc25e38fc`](https://github.com/alchemyplatform/rundler/tree/9852824c649fbe56fea9712b26d4188bc25e38fc)
contiene un margen de vigencia restante de **20 segundos**. Su simulador regular
requiere `validUntil > now + 20`; el constructor del bundle usa un límite
inclusivo. `evidence/rundler-reference.json` conserva rutas, SHA de blobs,
fragmentos breves y líneas de las cinco fuentes consultadas.

| Ventana / momento | Comprobación temporal EntryPoint v0.7 | Simulador de referencia | Constructor de bundle de referencia |
| --- | --- | --- | --- |
| 1 s, T o T+1 | Pasa | Rechaza | Rechaza |
| 31 s, T a T+10 inclusive | Pasa | Pasa | Pasa |
| 31 s, T+11 | Pasa | Rechaza | Pasa |
| 31 s, T+12 | Pasa | Rechaza | Rechaza |
| 31 s, T+31 | Pasa | Rechaza | Rechaza |
| 31 s, T+32 | Rechaza | Rechaza | Rechaza |

El margen de 20 segundos es **vigencia restante, no una espera obligatoria**.
La versión/configuración de Alchemy en Robinhood no se autenticó y no se ejecutó
Rundler: la tabla compara predicados de código fijado, no acredita admisión real.
Alchemy documenta [rechazo por caducidad próxima](https://www.alchemy.com/docs/wallets/reference/bundler-rpc-errors).

En la traza nueva `preOpGas=129999`, frente a 780000 de límite previo: 16.666538%.
La llamada de ejecución usa 913668 de 1500000: 60.9112%. Ambos ratios superan el
15% descrito en las [FAQ de Alchemy](https://www.alchemy.com/docs/wallets/reference/bundler-faqs),
pero la comparación con una traza histórica no sustituye su simulación, precio
prioritario requerido ni el resto de sus controles.

## Riesgo que sigue abierto

La autorización de 31 segundos **no extiende el bloque límite de la ruta ni la
vida de la oportunidad**. En Anvil, con tiempo T dentro de autorización y reloj
L2 adelantado un bloque, el bundle tiene recibo exitoso pero `UserOperationEvent`
indica fallo. Cobra **0.000021093268152 ETH** al paymaster, reserva todo el prefund
y no genera USDG. Ese importe es local; no se presenta como una medición Nitro.

Las pruebas en T+1 y T+31 mantienen fijo el estado de protocolo y el número de
bloque. No representan bloques futuros reales ni supervivencia frente a otros
liquidadores. El horizonte T+31 solo tiene recibo local; no se pidió esa traza
remota. El prestatario y el tamaño proceden de una operación conocida. Persisten
el sesgo retrospectivo y la falta de tasa prospectiva de captura.

Para decidir si financiar la estrategia siguen faltando: admisión completa con
un operador concreto; latencia de detección/simulación/inclusión contra señales
nuevas; resultados netos incluyendo fallos, ausencia de señales y todos los
costes; y un fondo externo prepagado con reparto y límite contractual de pérdidas.
El techo de prefund del contrato no elimina facturas, stake inmovilizado ni
pérdidas del bundler. No existe compromiso de financiación acreditado ni ingreso
propio cobrado. El observador prospectivo sigue sin estar desplegado.

## Evidencia y reproducción

- `evidence/local/`: cinco recibos/trazas de ventana corta, contexto y plan.
- `evidence/local-31/`: cinco recibos/trazas locales de ventana larga.
- `evidence/nitro/` y `evidence/nitro-31/`: **12 respuestas nuevas** con solicitudes exactas y SHA-256; ningún error RPC.
- `evidence/audit-report.json`: conciliación offline, balances, límites, costes y alcance.
- `evidence/verification/`: compilación, pruebas y preservación de fuentes.

El primer constructor limitaba ventanas a 4 segundos. Se conserva ese texto y
su log de 13 pruebas con prefijo `initial-`. Tras ampliar el máximo a 60 segundos,
una compilación fresca reprodujo **exactamente** el runtime, contexto, reporte
y plan de la variante corta. Añadir dos pruebas de presupuesto dejó idénticos
los bytecodes de creación y ejecución de la fixture. La compilación final tiene
16 pruebas Solidity; los locks finales corresponden a los archivos publicados.

Desde la raíz del repo, sin red:

```bash
python migration/robinhood-sponsor-window-20261016/audit_window.py --out /tmp/nqc-window-audit.json
python -m unittest discover -s migration/robinhood-sponsor-window-20261016 -p test_window.py -v
python -m unittest discover -s migration/robinhood-opportunity-economics-20261016 -p test_opportunity.py -v
python -m unittest discover -s migration/robinhood-real-state-replay-20261016 -p test_result.py -v
python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Para reconstruir, `prepare_window.py` acepta `--dependencies`, `--foundry-bin`,
`--solc` y `--build` (directorio nuevo fuera del repo). Reutiliza los pins y el
preparador de PR8; copia las dos fuentes nuevas a la copia externa. Después:

```bash
python migration/robinhood-sponsor-window-20261016/local_window.py \
  --build /ruta/build-nuevo --foundry-bin /ruta/foundry-bin \
  --out /tmp/nqc-window-local-nuevo --window-seconds 31
```

El replay local fija loopback y arranca/cierra Anvil; no acepta una URL remota.
La firma reutilizada y la clave `0x1234` de los tests son públicas de laboratorio.
Los planes Nitro exportados no se ejecutan automáticamente.

Validación final: **16 Solidity + 61 Python pasan**, cero fallos/omitidos en esas
suites. Se ejecutaron 16 pruebas Python nuevas, 20 de PR9, 16 de PR8 y 9 de
aislamiento. El verificador conserva **377 blobs originales**, 106 workflows
deshabilitados y cero activos. No hubo cambios Rust ni ejecución nueva de sus
suites; tampoco una ejecución global de todas las suites Solidity históricas.
Permanece un warning de mutabilidad en `Fixtures.sol` heredado, sin error de
compilación. No hubo despliegue, firma real, envío, suscripción ni gasto real.
