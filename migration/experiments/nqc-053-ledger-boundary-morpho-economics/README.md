# NQC053 — límites del registro y de la economía Morpho

19 de octubre de 2026. Resultado: **la adquisición real permanece bloqueada y la viabilidad comercial no está demostrada**. Se añadieron pruebas que refutan garantías todavía ausentes del registro heredado y un análisis económico nuevo de financiación, pérdidas por intentos fallidos y volumen requerido. `commercial_admission=false`.

Base exacta: `fe90dd6653968363fdbffb36586fbd4f361786ea` (NQC052). Rama: `research/nqc-053-ledger-boundary-morpho-economics-20261019`. Antes de escribir se consultaron las ramas remotas: NQC052 seguía siendo la última continuación. `main` conservaba `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. Solo se agregan archivos de este directorio; ningún experimento anterior se modifica.

## Qué aporta esta entrega

1. `ledger_worker.js`, `ledger_model.js` y `test_ledger.js`: ejecutores en procesos OS independientes contra un modelo compartido de almacenamiento con CAS por contenido. Usan el motor NQC048 y el plan NQC038 originales, comprobados por SHA-256. Hay ocho procesos simultáneos en la carrera y procesos nuevos en las recuperaciones. No son subagentes. No hay cliente HTTP ni transporte real.
2. `economics.py`: lectura offline de 33 archivos originales fijados por commit, blob Git y SHA-256; reconcilia censo, recibo, traza y transferencias del caso B; calcula la frontera de financiación y pérdidas, y las necesidades de captura para US$5.000, US$15.000 y US$45.000 mensuales.
3. `run_checks.py`, pruebas y evidencias: reproducción con Python estándar y Node, sin dependencias nuevas ni acceso a RPC. Los JSON distinguen observaciones de supuestos y mantienen cerrada la admisión comercial.

## Credencial y presupuesto

La documentación oficial describe **Network secrets** para Codex Cloud: el programa recibe un marcador y un proxy sustituye la credencial para destinos HTTPS configurados. En esta sesión Work no hay una herramienta expuesta para confirmar ese enlace, identidad de entorno o configuración Triport. Las comprobaciones booleanas de `NQC_TRIPORT_API_KEY` y `NQC_ARCHIVE_RPC` dieron falso; `triport.io` tampoco figura en la lista declarada de destinos del ejecutor. Esto no demuestra que la credencial del propietario no exista en otro entorno. La documentación no demuestra su disponibilidad aquí. Véase `WORK_ACCESS_REVIEW.json`.

El transporte NQC038 toma `NQC_TRIPORT_API_KEY` y la coloca en `x-token`. Pasarle una clave cruda incumpliría la nueva condición de que el código no la vea. Un marcador oficial podría ser compatible en principio; no se inventó ni se probó uno. Tampoco se ha demostrado protección frente a una eventual reflexión del secreto en una respuesta que deba conservarse. No se inspeccionaron valores, cookies, sesiones ni capturas; no se modificaron permisos o integraciones.

**Consumo Triport acumulado documentado: 0 de 8; NQC053: 0.** No se abre un presupuesto nuevo. No existe un registro LIVE habilitado. El journal sintético NQC052 y sus reservas permanecen intactos. La ausencia de observaciones fuera del repositorio no equivale a una auditoría de la cuenta del proveedor.

El plan y el transporte originales permanecen byte a byte iguales. Cadena 4663; padre 66744161, hash `0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917`, raíz `0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a`; objetivo 66744162, `txIndex=1`; PairOracle `0x929631b33f4070d6f54477fba3fd27566567daca`. Un estado del padre seguiría sin autenticar automáticamente ese preestado exacto. Se conservan 0 pruebas de estado adquiridas y 0/11 slots prioritarios autenticados en dicho preestado.

## Registro: conclusión operacional

`LEDGER_BOUNDARY.md` documenta las garantías y sus contraejemplos. Con una autoridad sin retroceso, el modelo admite un solo ganador entre ocho procesos y mantiene el límite de ocho al cambiar de proceso. Sin embargo, restaurar la autoridad inicial permite un noveno intento simulado; copiarla permite dos intentos ID 1 con el mismo scope. Un error RPC se rechaza sin guardar su cuerpo. La interfaz de objetos JSON tampoco conserva los bytes HTTP originales.

Se ha refutado que **el diseño actual, por sí solo**, garantice el presupuesto global requerido. No se ha refutado la posibilidad de construir otro sistema bajo controles distintos. La política operacional vigente es detener toda adquisición: no recrear, copiar, reinicializar o migrar un registro para obtener intentos nuevos; no forzar refs; una confirmación ambigua consume la reserva y no autoriza reenvío. Esta política impide consumo adicional porque LIVE está deshabilitado; **no se presenta como una solución que habilite ocho lecturas seguras**.

## Economía auténtica disponible y límite nuevo

La fuente es otra rama del mismo repositorio autorizado, `research/morpho-sponsored-gas-20261016`, fijada en `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`. No se repitieron sus consultas. Los archivos originales se leen por su commit, se verifican y no se sobrescriben. `SOURCE_MANIFEST.json` conserva su procedencia completa. Las observaciones anteriores de Blockscout son archivos ya adquiridos: **ninguna consulta nueva a Blockscout**.

La muestra de Ethereum/Morpho comprende 143 eventos en 141 transacciones, 60 mercados y 49 direcciones liquidadoras durante 30 días. Hay 43 eventos con deuda incobrable. De 23 recibos seleccionados para diagnóstico, 22 eran nulos; solo el caso B tiene el recibo utilizable conservado. Un control `eth_getLogs` omitió ese evento conocido. Las paginaciones coincidentes de un mismo proveedor no subsanan esa contradicción. El volumen no está certificado como exhaustivo y no mide capturas rentables disponibles para NQC.

Caso B: Ethereum **1**, Morpho Blue, bloque **26190955**, transacción `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`, índice **1**. El informe JSON incluye mercado, deudor, contratos, activos, ejecutor externo y pagador del gas. Este caso **no pertenece a Robinhood Chain 4663**.

| Movimiento observado | Cantidad |
|---|---:|
| Deuda repagada | 26,039738525656992415 WETH |
| Colateral incautado y convertido | 24,343983926960874121 ezETH |
| Salida de la venta | 26,409680973611 ETH |
| Venta menos deuda, antes de gas/pago a coinbase/otras obligaciones | 0,369942447954007585 ETH |
| Transferencia a coinbase | 0,368092735714237547 ETH |
| Gas del remitente | 0,000198416195275125 ETH |
| Residuo aritmético máximo antes de obligaciones desconocidas | **0,001651296044494913 ETH** |

El pago a coinbase absorbe aproximadamente el 99,5% de venta menos deuda. No se atribuye automáticamente a ingresos de un builder. La venta ya incorpora efectos de la ruta: no se vuelve a descontar una comisión o impacto hipotético. No hay precio USD histórico autenticado, P&L consolidado ni ganancia de NQC demostrada.

El resultado nuevo más útil es la **tolerancia a obligaciones adicionales**: manteniendo la misma ruta, gas y pago a coinbase, el punto de equilibrio de una prima sobre toda la deuda repagada es aproximadamente **0,6341 puntos básicos**. Una prima hipotética de 0,5 pb deja 0,000349309118212063 ETH; **1 pb (0,01%) produce −0,000952677808070787 ETH**, antes de otros costes. Son escenarios, no cotizaciones de financiación. Si cada intento fallido costara el mismo gas observado, ocho fallos por una captura idéntica aún dejarían residuo; nueve lo eliminarían. No se conoce esa tasa de fallos ni ese coste en producción.

La fuente Morpho fijada transfiere el colateral antes de `onMorphoLiquidate` y cobra `repaidAssets` después del callback. Esto permite conceptualmente vender el colateral y repagar dentro de la misma transacción, sin asumir un préstamo adicional sobre toda la deuda. La financiación del gas debe estar resuelta antes de incluirla. El ejecutor histórico tenía activos previos; no demuestra un ejecutor NQC sin fondos. La función `flashLoan` de esa fuente cobra el principal recibido, pero su disponibilidad de caja, identidad de runtime histórico y viabilidad para NQC no están autenticadas. No se confunde esa semántica con una oferta de financiación gratuita ni con un compromiso de patrocinio.

## Volumen necesario, no pronóstico

Escenarios con beneficio **neto por captura** ya descontados deuda, costes de venta, financiación, gas y pago competitivo, y sin costes mensuales adicionales. Si existieran esos costes, la fórmula es `capturas × neto_por_captura − pérdidas_de_intentos − costes_fijos ≥ objetivo`.

| Neto hipotético por captura | Capturas para US$5.000 | Para US$15.000 | Para US$45.000 |
|---|---:|---:|---:|
| US$50 | 100 | 300 | 900 |
| US$100 | 50 | 150 | 450 |
| US$500 | 10 | 30 | 90 |
| US$1.000 | 5 | 15 | 45 |

Otra lectura condicionada a esta muestra: con **14 capturas** hipotéticas de las 141 transacciones observadas, harían falta US$357,15, US$1.071,43 o US$3.214,29 netos por captura. Incluso suponiendo capturar las 141, harían falta US$35,47, US$106,39 o US$319,15, respectivamente. Ni las 14 ni las 141 se consideran oportunidades ejecutables. La muestra no es un límite del mercado entero ni una predicción del siguiente mes. Volumen económicamente capturable demostrado por NQC: **0**; expectativa mensual: **no estimable**.

## Validación y reproducción

Resultado final: **13 pruebas Python nuevas + 10 escenarios Node nuevos + 9 pruebas de aislamiento aprobados**, además del verificador de aislamiento. Los cuatro archivos de control fijados conservan sus hashes. Logs completos y resultados estructurados: `evidence/` y `VALIDATION.json`.

Se declaran dos fallos iniciales de desarrollo en `evidence/development-failures.json`: una llave ausente en el nuevo worker hizo fallar los 10 escenarios antes de ejecutarlos; el parser inicial rechazaba importes enteros codificados como cadenas. Ambos se corrigieron solo en NQC053. Cero fallos u omisiones dentro de las suites finales ejecutadas. No se repitieron las suites NQC037/NQC052, sin regresión concreta; no se ejecutaron Rust/Solidity porque sus fuentes no cambian. No hubo ensayo real entre hosts, rollback remoto, autenticación Triport ni operación financiera.

Para un ejecutor técnico con checkout íntegro y el commit de la rama Morpho disponible:

```sh
python migration/experiments/nqc-053-ledger-boundary-morpho-economics/run_checks.py
```

Este comando es documentación de reproducción para agentes/revisores, **no una tarea para el propietario que usa Android**. No instala dependencias. El JSON económico es determinista; tiempos y PIDs de las pruebas varían. `SHA256SUMS` registra los archivos entregados; los originales se verifican separadamente mediante `SOURCE_MANIFEST.json`.

## Siguiente movimiento con mayor impacto económico

Priorizar un paquete de evidencia del **preestado exacto de un caso Morpho**, acompañado de condiciones verificables de venta, inclusión competitiva y financiación del gas. El caso B es un punto de partida concreto, pero su margen no soporta cualquier financiación. Un replay reproducible y un presupuesto completo permitirían aceptar o descartar una oportunidad; otro componente de infraestructura, por sí solo, no lo hará.

Triport mantiene un trabajo separado: solo reconsiderarlo cuando una capacidad oficial accesible confirme la credencial protegida **y** exista una autoridad única de consumo con exclusión, política antirrollback comprobable y conservación segura de todas las respuestas. Nada de esta entrega autoriza ampliar permisos, contratar servicios o consumir RPC adicional.
