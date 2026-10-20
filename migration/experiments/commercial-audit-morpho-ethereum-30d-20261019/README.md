# NQC — Auditoría comercial Morpho Blue Ethereum, 2026-10-19

**Resultado: 11 liquidaciones REPORTADAS EN LA INTERFAZ de Morpho, 4 mercados, 0 oportunidades rentables capturables demostradas para NQC. NO-GO financiero.** Investigación comercial acotada, NO un nuevo bot NQC068. Esta muestra no pretende ser el universo Ethereum ni una medición exhaustiva de 30 días. Las fechas son las mostradas por Morpho; ninguna constituye una decisión de NQC tomada antes del bloque.

## Evidencia seleccionada (2026-09-20 a 2026-10-19)

| Fecha en interfaz | Mercado (deuda/colateral) | Deuda pagada | Colateral incautado | Diferencia USD de la pantalla* | Liquidador (abreviado) | Tx (abreviada) |
|---|---|---:|---:|---:|---|---|
| 2026-10-15 | RLUSD/FXRP | 1717.97 RLUSD | 1432.43 FXRP | +138.67 | 0xBdE3...5c64 | 0x4df1...ecca |
| 2026-09-23 | RLUSD/FXRP | 1296.36 RLUSD | 920.18 FXRP | -103.68 | 0xbD32...079C | 0x9835...3b9c |
| 2026-09-23 | RLUSD/FXRP | 433.51 RLUSD | 306.72 FXRP | -35.97 | 0x950f...A86F | 0x1945...a190 |
| 2026-09-23 | RLUSD/FXRP | 1698.02 RLUSD | 1194.67 FXRP | -149.56 | 0xbD32...079C | 0x179e...5e84 |
| 2026-09-27 | msETH/ynETHx | 1.9024 msETH | 1.7793 ynETHx | +651.56 | 0x9571...F357 | 0x8037...79b8 |
| 2026-09-25 | msETH/ynETHx | 0.9847 msETH | 0.9211 ynETHx | +337.50 | 0xF968...FbC9 | 0xbc78...3f1e |
| 2026-09-25 | msETH/ynETHx | 1.5032 msETH | 1.4061 ynETHx | +515.21 | 0xF968...FbC9 | 0x4bd6...191d |
| 2026-09-25 | msETH/ynETHx | 2.8878 msETH | 2.7013 ynETHx | +989.75 | 0xF968...FbC9 | 0x9711...4e90 |
| 2026-09-21 | msETH/ynETHx | 0.0928 msETH | 0.0868 ynETHx | +31.92 | 0xDEAD...aeF8 | 0x1f57...bbc7 |
| 2026-10-07 | USDS/wstETH | 253.629 USDS | 0.0824 wstETH | +4.08 | 0x812A...Eaf3 | 0x80b8...9780 |
| 2026-10-18 | USDC/USR | 5.018 USDC | 5.1494 USR | -4.60 | 0x8575...4038 | 0x879b...ad1e |

*Diferencia USD = valoración visual del colateral − valoración visual de deuda. **NO** es venta ejecutable, margen de un trader ni P&L neto. Morpho documenta que las cotizaciones USD de su API usan precios spot actuales y series históricas separadas; la app demostró mutable el marcado de eventos antiguos. No sumamos los dólares visuales a una previsión ni al saldo de NQC. Las cantidades son valores mostrados/redondeados, no unidades onchain autenticadas.*

Fuentes: [Morpho RLUSD/FXRP](https://app.morpho.org/ethereum/variable/0x4fa31e3f8ba345227d44e1cf48559eea53a90dd5311dc006984c060f2f311d96/rlusd-fxrp), [Morpho msETH/ynETHx](https://app.morpho.org/ethereum/variable/0xd2630c0ebf33ba83c82e8cd400a8e6345370238ca695ce58773b2d3e43de1b0a/mseth-ynethx), [Morpho USDS/wstETH](https://app.morpho.org/ethereum/variable/0xb374528d44b6ab6e0cecc87e0481f45d892f38baec90c1d318851969ec14ea5f/usds-wsteth), [Morpho USDC/USR](https://app.morpho.org/ethereum/variable/0x8e7cc042d739a365c43d0a52d5f24160fa7ae9b7e7c9a479bd02a56041d4cf77/usdc-usr). Solo **un hash completo de la interfaz** fue identificado: `0x4df17ad0a3aad6ee9962458ddbefaf154d86993cbed64c73ddb353d6d101ecca` de la fila RLUSD 15 oct; Etherscan no permitió abrir el recibo (403), y no se reintentó ni buscó otra ruta de evasión.

## Decisión comercial por mina

### RLUSD / FXRP: único caso relativamente convencional para investigar primero

La fila 15 oct muestra deuda **1,717.97 RLUSD** ($1,718.15 pantalla) y colateral **1,432.43 FXRP** ($1,856.82 pantalla), **+$138.67 de valoración**. El mismo mercado tiene TRES filas grandes del 23 sep con diferencias visuales **−$103.68, −$35.97, −$149.56**. Se observan al menos **tres identificadores de liquidador diferentes** en esta muestra: `0xBdE3...5c64`, `0xbD32...079C`, `0x950f...A86F`. Eso es participación observable, NO competencia ex ante reconstruida, ni operadores económicos independientes comprobados.

**Puerta monetaria:** venta *ejecutable* de FXRP→RLUSD antes/de la liquidación, monto repagado con unidades exactas, gas, comisión de swap, puja privada/builder, sponsor y control del excedente. Una diferencia positiva de $138.67 no cumple ninguna de esas puertas. No se ha identificado cotización real de venta ni financiador.

### msETH / ynETHx: aparentemente grande pero con riesgo decisivo de realización

Cinco eventos entre 21 y 27 sep tuvieron diferenciales visuales positivos; tres fueron capturados por `0xF968...FbC9`, uno por `0x9571...F357` y uno por `0xDEAD...aeF8` (identificadores de pantalla). **No hay exclusividad.** La fuente Morpho califica el mercado como *Unverified* y muestra un precio de oráculo **1 ynETHx = 1.09 msETH** frente a referencia DefiLlama **1.24 msETH**, una discrepancia que exige arbitrar autenticidad, unidad, liquidez y ruta, NO elegir la cifra favorable.

El **27 sep** los mismos **1.9024 msETH / 1.7793 ynETHx** figuraron en un resultado anterior como **$4,491.60/$5,216.30** (diferencia $724.70) y después como **$4,039.32/$4,690.88** ($651.56): las valoraciones USD cambiaron sin cambiar las cantidades registradas. [YieldNest](https://docs.yieldnest.finance/protocol-design/max-vaults/yneth-max-ynethx) declara rescate instantáneo limitado por colchón de liquidez, que puede pausarse. Un canje en días no sirve para repagar atómicamente en Morpho. Falta una **cotización real ejecutable ynETHx→msETH en el mismo bloque**, y la validación de código/oráculo. **Posponer como mina comercial** hasta evidencia de ruta.

La UI muestra varios prestatarios con `Health < 1` en la vista consultada, incluyendo 708.149 msETH de deuda para una posición con indicador 0.994. **Es solo el cálculo del indexador**, no prueba onchain de elegibilidad actual, ni venta, ni oportunidad reservada para NQC. No se puede declarar dinero disponible.

### USDS / wstETH: bajo margen y un problema de reproducibilidad de página

La liquidación del **7 oct**, 253.629 USDS y 0.0824 wstETH, marca **+$4.08** en un índice/caché oficial de Morpho. Una consulta directa posterior de esa misma ficha ya no incluyó la fila de octubre y solo mostró una liquidación de junio. Se clasifica como **pendiente de corroboración independiente**; incluso si existió, $4.08 visuales no prueban margen suficiente para swap/gas/puja.

### USDC / USR: no señal de beneficio

El 18 oct se reporta 5.018 USDC (valor $5.01) y 5.1494 USR (pantalla $0.41), diferencia visual **−$4.60**. La fuente muestra deuda mala/no realizada y una gran brecha de valor, que no debemos tratar como liquidación rentable. El resultado de un liquidador real podría incluir flujos externos que no vimos; por tanto se descarta **la interpretación de que este registro demuestre profit**, no se afirma pérdida de un operador identificado.

## Advertencias económicas y de cobertura

- Se encontraron **11 filas** en **4 mercados seleccionados**, de las cuales **7 parecen positivas y 4 negativas según el marcado visual**. Estos no son indicadores estadísticos de todo Ethereum: la selección no es aleatoria ni exhaustiva. No hay 11 auditorías completas de recibos, ni gas/builder/flash/sponsor por operación.
- **0 recibos originales autenticados, 0 ganancias reales de NQC, 0 oportunidades predecisión certificadas y 0 sponsors comprometidos.** Las cifras históricas de Dune/1inch son **multicadena** y su último evento visible ronda el 5 oct; no sustituyen el conjunto Ethereum a 19 oct.
- Las direcciones liquidadoras abreviadas son distintos identificadores visibles, no prueba de propietarios distintos, órdenes privadas rivales o bajas barreras de entrada.
- No se tocó Titan ni ningún proveedor; no se llamó RPC, no se usó Triport, no se firmó, no hubo transacción, gas ni fondos. La cuenta de gas futura MXN2,000 y prohibición de principal siguen intactas. `commercial_admission=false`, `canary_enabled=false`.

## La única próxima acción que justifica más trabajo

**Prioridad A: cotización real ejecutable o traza de venta FXRP→RLUSD** (referenciada por una operación fechada) más recibo y costos; si existe una ruta líquida verificable, medir el margen *con oferta y comisiones*, no con precio spot. **Prioridad B: probar/refutar ruta atómica ynETHx→msETH a tamaño histórico**; si hay retiro condicionado o menos salida que repago, descartar la mina para capital cero. Solo tras cubrir precio y gas, solicitar admisión específica de Titan con responsabilidad por fallas. Si no hay acceso legítimo a datos de ejecución, **detener trabajo económico sobre estas muestras**, no simular otra oportunidad.

Este expediente es una **auditoría comercial basada en páginas**, no un reemplazo de Census ni una certificación onchain. Se agrega en rama aislada, sin tocar código ni producción. Ni scripts del repositorio ni verificador original PFT/Census se ejecutaron; se verificó aritmética/documentos localmente.