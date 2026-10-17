# Temporalidad: recepción no equivale a descubrimiento retrospectivo

**CAPTURA_TEMPORAL_NO_DEMOSTRADA** en las tres rutas. No se abrió un stream ni proceso persistente. No se repitieron endpoints denegados. Esta auditoría usa expedientes conservados, inspección de fuente y comprobaciones offline. No presenta sus horas de auditoría como horas de recepción de una oportunidad.

| Etapa requerida | Aave/SVR | Robinhood | Morpho Ethereum |
|---|---|---|---|
| Cambio efectivo y estado | One-shot en 26142068; ruta de oráculo documentada aparte | Tercero en 66744162, índice 1 | Caso B en 26190955, índice 1 |
| Primera disponibilidad legítima de trigger | DESCONOCIDA para NQC | DESCONOCIDA para candidato histórico | DESCONOCIDA antes del tercero |
| Primera recepción local | Sin hint autorizado prospectivo conservado | Benchmark de transporte, sin candidato liquidable | Muestra posterior completa a 2026-10-17T05:38:26.670478Z |
| Mercado/posición/oráculo/IRM/DEX coherentes | Fuente histórica no demuestra señal actual | Estado de proveedor en contrafactual; benchmark no simula ruta | Muestra mezcla 26210230/26210231/26210229: RECHAZADA |
| Liquidabilidad validada a tiempo | PENDIENTE | Histórica simulada; recepción previa PENDIENTE | PENDIENTE |
| Simulación y neto antes del corte | PENDIENTE | PENDIENTE | PENDIENTE |
| Preparación local antes del corte | PENDIENTE | PENDIENTE | PENDIENTE |
| Corte independiente subasta/secuenciador | DESCONOCIDO | DESCONOCIDO | DESCONOCIDO |
| Primer competidor y orden | Orden histórico no demuestra recepción temprana | Orden histórico conocido; latencia de captura desconocida | Tx0 seguida por tercero; efectos tx0 incompletos |
| Motivo de no admisión actual | No señal/financiación/ejecutor actual | No bundler integral/financiación/tiempos | Sin preestado coherente/financiación/tiempos |

`before_cutoff` comprueba únicamente `recepción <= preparación < min(corte, captura competidor)` con relojes comparables y zona horaria. Tiempos faltantes producen PENDIENTE; igualdad con corte produce rechazo; preparación anterior a recepción es inválida. Incluso satisfacer esa desigualdad no prueba inclusión ni beneficio. Los cinco tests nuevos incluyen estos controles. No fabricamos una medición de reloj comparable con el secuenciador.

## Aave/SVR

El contrato `SVR_HINT_ADMISSION_CONTRACT.md` en `6693542e675f930a7ef0a4fd60cb72e7a6608845` clasifica un hint decodificado como no autenticado y exige recepción y corte independientes. Un oráculo encontrado en cadena no acredita acceso privado antes de su inclusión. [Chainlink](https://docs.chain.link/data-feeds/svr-feeds/searcher-onboarding-ethereum) describe su ruta de señales y puja; [Flashbots](https://docs.flashbots.net/flashbots-auction/advanced/rpc-endpoint) fija restricciones del paquete. No se realizó onboarding. Un timestamp de bloque minado no sustituye el cierre de la subasta.

## Robinhood: verificación acotada de métricas existentes

Se releyó `migration/robinhood-transport-benchmark-20261016T0821/evidence/summary.json` en el commit de decisión. Se recalculan sus medianas offline en `evidence/secondary-evidence.json`; **no se repite la captura de red**.

Son 6 bloques, 30 cuentas, 49 llamadas y 114.687481725 segundos de journal, el 16/oct/2026 08:38:26–08:40:21 UTC. En las 5 rondas de conexión reutilizada: mediana de entradas **82.42736 ms**, estado verificado **234.250541 ms**. Incluyendo arranque frío, medianas **154.6604265 ms** y **305.249701 ms**. Desde comenzar la petición de cabecera hasta estado verificado, las seis rondas persistentes tardaron **2722.970287–26398.132773 ms**: incluyen orden y espera entre controles. No se midieron ruta, simulación, admisión o inclusión. No publicamos p95/p99 de cinco muestras.

Cobertura de deuda del cohorte: 175104105238630296 / 865114351430594397 shares (aproximadamente 20.24%); 24 cuentas endeudadas, ninguna no saludable en esos seis bloques. No demuestra ausencia fuera de la cohorte. Otras cifras de captura caliente 980.560–1130.925 ms pertenecen a otro experimento; no se mezclan para obtener una latencia nueva.

## Caso B y observación prospectiva Ethereum

El hash del bloque fijado es `0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8`. La raíz de 602 transacciones reconstruida es `0xc408c2823145b6f024162fd4c51bc8e34d4bae302bd2fa456bd8556d0e41167f`. La suite Morpho reejecutada incluye el verificador de orden. Esto no prueba raíz de recibos, consenso/finalidad ni estado de ejecución.

| Componente del replay | Estado actual |
|---|---|
| Bytes de transacciones, encabezado y orden relativo al encabezado | VERIFICADO offline |
| Recibo de B y observaciones internas Morpho/Fluid | OBTENIDO; testigo de preestado insuficiente |
| Estado padre autenticado, código y storage completo | FALTA |
| Tx0 `0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`: efectos y paridad | FALTA |
| Morpho, IRM, oráculo y posición inmediatamente antes de tx1 | FUENTE_INSUFICIENTE |
| Fluid: reservas reales/imaginarias, límites y tasas en ese índice | FUENTE_INSUFICIENTE |
| Ejecución original seguida de NQC sobre el mismo estado | NO_EJECUTADO |

El expediente preserva denegaciones HTTP 403/405, estado podado y respuestas null, además de intentos cuya respuesta bruta se perdió al reiniciarse un entorno. No inventamos esos bytes ni los contamos como evidencia conservada. La cuota Blockscout de aquel ensayo se agotó (8/8); no se reinició. No se hizo nueva consulta de estado en esta auditoría porque no había una fuente nueva autorizada que cerrara ese bloqueo.

La observación prospectiva conservada rechazó la mezcla de alturas. La consulta posterior de 95 segundos con cero eventos indexados carece de cobertura/lag certificado; no estima frecuencia cero. Un nuevo muestreo solo tendría valor con cadena/hash/altura coherentes, semántica de accrual validada y disponibilidad antes de un candidato; no resolvería por sí mismo la financiación.

## 11 µs y magnitudes heredadas

Lectura acotada, sin búsqueda ilimitada: `runtime/bench/src/main.rs` de Nexus Engine en `380eff1fc14336bd24d93c8ef807525a7078950d`, PR730 y auditoría cruzada `ddade5d099e19449e0c4e55079a2b0c9d9ee1141`. El benchmark inspeccionado es procesamiento en memoria; excluye red y presenta límites de buckets de histogramas. No ejecutamos Rust ni encontramos una medición trazable de 11 µs extremo a extremo. PR730 reporta dos muestras por modo y una razón aproximada de **11.3288 veces**, no 11 µs; su head no fusionado es `e1c8435badc24a64b2e58329b4d0ad80f4d843eb`. No se descargaron sus artefactos de ejecución: sigue siendo una afirmación del PR.

«11 µs» y «$14,000 billones»: **NO LOCALIZADOS / NO VERIFICADOS**, no universalmente refutados. T37 cuenta señales/superficies sintéticas; 215036×67 = 14407412 coordenadas de precios no son mercados rentables. RMC016 reporta 127 transacciones/139 eventos y margen bruto de oráculo, población distinta de las 143 liquidaciones Morpho. Ninguno acredita ingresos propios, liquidez ejecutable o capacidad mensual.
