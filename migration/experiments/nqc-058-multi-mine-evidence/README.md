# NQC058 — Ultra Miner: comparación económica con evidencia pública

**OPORTUNIDAD_RENTABLE_NO_DEMOSTRADA.** Se comparan dos protocolos de Ethereum y una sola familia estratégica: liquidaciones. Hay 142 expedientes Morpho heredados y 11 observaciones Aave nuevas para NQC. No son 153 oportunidades comerciales, ni vigilancia en tiempo real. No existe beneficio neto capturado por NQC, financiador comprometido o ganadora económica acreditada.

Rama `research/nqc-058-multi-mine-evidence-20261019`, padre directo `72bc4fa2556e859ac261b1e1223b5f404068e42c`. Se verificaron las 83 ramas remotas antes de escribir: NQC057 era la última continuación. Solo se añaden archivos en este directorio. `commercial_admission=false`.

## Mejora concreta frente a NQC055

`miner.py` reutiliza por hash el kernel de unidades, intervalos, procedencia y deduplicación de NQC055. `MorphoPublished` proyecta su resultado publicado sin repetir las simulaciones ni reconstruir el radar. `AavePublic` admite diez filas de un informe primario y una llamada fallida con gas reportado por un explorador. La comparación mantiene separados bloque/orden reportados, prueba canónica, contabilidad, financiación y P&L capturable.

Se conservan exactamente las cotas y el descarte condicionado de Morpho B. El candidato pufETH permanece suspendido por NQC056: el motor no vuelve a proponer adquirir su recibo nulo. No se añade una tercera mina. Compound quedó fuera de esta entrega tras errores de lectura documental, sin reintentar los destinos bloqueados ni implementar un adaptador sin datos.

| Mina / alcance | Datos realmente disponibles | Resultado económico | Financiación | Siguiente prueba decisiva |
|---|---|---|---|---|
| Morpho Blue, Ethereum 1 | 142 expedientes publicados; muestra mensual incompleta de 143 eventos/141 tx más caso A anterior | B conserva techo histórico 0,001651296044494913 ETH antes de obligaciones desconocidas. Escenario de financiar toda la deuda con prima >=1 bp, misma venta/puja, descartado incluso con gas cero | Callback colateral primero verificado en laboratorio previo; gas y aceptación real pendientes | Nuevo libro completo o términos aplicables, sin reabrir expedientes agotados con los mismos datos |
| Aave V3, Ethereum 1: llamada fallida | Una página pública con calldata, estado Fail, bloque/índice reportados y gas | Cota condicionada de esta ejecución <= **−0,000018435515899836 ETH**, sin compensación externa y con demás costes no negativos | No se identifica financiador; quien paga gas en la tx es el sender; titularidad y reembolsos externos desconocidos | No optimizar este intento cerrado; autenticar la fuente solo si otra decisión lo requiere |
| Aave V3, Ethereum 1: informe de diez liquidaciones | Hash y bloque, valoraciones USD redondeadas de AAVE/USDC | **EVIDENCIA_INSUFICIENTE** en las diez: sin venta, gas, unidades de tokens ni obligaciones completas | Flash documental condicionado; sin monto disponible, prima aplicable ni patrocinio acreditados | Un paquete íntegro de evento, venta, gas y obligaciones antes de pedir preestado |

**Dos minas por protocolo; una familia de estrategia.** No hay arbitraje autónomo evaluado, rentabilidad relativa calculable ni cobertura live. El tamaño de una liquidación no altera la prioridad económica.

## Nueva evidencia y autenticidad delimitada

1. [Chaos Labs, seguimiento del 7 de febrero de 2026](https://governance.aave.com/t/chaos-labs-risk-report-insights-from-recent-market-events-02-02-26/23986), sección *AAVE Holder Liquidation*, tabla de diez transacciones: bloques 24393011–24394116. El autor describe restricciones de liquidez y plantea una posible distribución alternativa del inventario para la última operación; advierte que la atribución no es definitiva. No se demuestra una venta atómica de esa operación ni se extiende esa inferencia a las otras nueve. El post declara CC0. Se conserva la tabla factual en `inputs/aave_report.json`.
2. [Intento fallido `0xd5cf47…d700c`](https://etherscan.io/tx/0xd5cf47f4a895f6e44eb09fd7fe98357e91c5b94a3a985e580b5e5411d89d700c), bloque 24563287, posición reportada 259, 2026-03-01 14:47:47 UTC. Primera lectura pública legible; el lector indicó caché de dos meses. Una petición posterior de rango de líneas al mismo resultado devolvió 403; se detuvo esa vía. La transcripción inicial permanece en `inputs/aave_failed.json`. **No se obtuvo recibo crudo, prueba de pertenencia ni traza completa.**
3. [API oficial del Pool Aave](https://www.aave.com/docs/aave-v3/smart-contracts/pool), secciones `liquidationCall`, `flashLoan`, `flashLoanSimple`. Sustenta mecanismos documentales, no implementación histórica, parámetros efectivos o aceptación de NQC. No se aplica un close factor o una prima actual a bloques históricos sin evidencia.

Se verifican **26 archivos heredados** por commit, blob Git y SHA256, incluidas las 18 fuentes del radar original. Otros cuatro registros locales de transcripción/revisión tienen tamaño, blob y SHA256 en `INPUT_MANIFEST.json`. Esos hashes fijan nuestros registros; **no son hashes del cuerpo HTTP ni pruebas de consenso**. La extracción pública fue humana; las pruebas comprueban coherencia e integridad, no autentican por sí solas el contenido de una web.

`PUBLIC_REVIEW.json` enumera seis errores de lectura: dos páginas Compound redirigidas/inaccesibles, una guía Aave, otra tx Etherscan con 403, la página de una tx del informe inaccesible y la lectura posterior del resultado inicialmente legible. No se reintentó un destino ya denegado ni se sustituyó por proxy/proveedor. El snippet de otra tx fallida no se admite en el lote. No hubo RPC, Blockscout ni llamadas autenticadas.

## Descarte nuevo: alcance, unidades y participantes

La llamada va al contrato etiquetado por el explorador como Aave Pool V3, `0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2`. Su selector coincide con la ABI documentada; no se verificó el runtime/proxy histórico. El decodificador distingue los activos y el monto **solicitados** de lo efectivamente transferido. El campo de deuda de calldata no se registra como deuda pagada. Si el estado Fail reportado es correcto, las transferencias de la llamada revertida no se consolidan; el gas de la transacción incluida sí se cobra.

Contabilidad ETH exacta, sin conversión USD:

- `213052 × 86530593 = 18435515899836 wei` de gas.
- Base quemada: `18435509508276 wei`.
- Prioridad al receptor de tasas del bloque: `6391560 wei`.
- Ambas partidas suman el gas; no se añaden nuevamente como una segunda comisión.

El pagador reportado es `0xb323c6e32c6efe28fb9cfb1a83f4071c544ea1e4`. No se atribuye su titularidad a NQC. Identidad del financiador, builder, proponente y dirección receptora de tasas: desconocidas. Tampoco se conoce compensación externa o responsabilidad residual. El receptor de prioridad no se identifica automáticamente como builder.

**Escenario cerrado:** esa llamada fallida, fuente correcta, sin compensación externa, obligaciones adicionales no negativas. Ingreso consolidado de la llamada cero; techo neto igual a menos el gas. La cota inferior sigue desconocida. Si se permiten compensaciones externas desconocidas, también la cota superior vuelve a `null`. No se afirma pérdida total de la cartera, inutilidad de Aave ni pérdida de NQC.

En las diez filas del informe, restar valoraciones USD de colateral y deuda no produce una venta ni un P&L. Se preservan como metadatos redondeados; direcciones/decimales/montos brutos no verificados quedan nulos. No se calcula una falsa ganancia a partir de la operación más grande. Ingresos del protocolo, principal prestado y activos retenidos por un financiador tampoco son ingresos NQC.

## Financiación y comparación reproducible

Morpho conserva la ruta colateral → venta en callback → repago del expediente anterior. Aave exige cubrir la deuda de liquidación; su API ofrece liquidez temporal con devolución y prima aplicable. Como estructura documental podría usarse `flashLoanSimple` o `flashLoan` con modo 0. Los modos que abren deuda residual quedan excluidos. No se presupone saldo suficiente, gratuidad, waiver, venta rentable ni liquidez histórica. Esa liquidez temporal no adelanta el ETH inicial del gas.

Las condiciones de gas y reparto siguen las fronteras de NQC057: patrocinio Titan/Quasar documentado, ningún compromiso demostrado, recurso personal **UNKNOWN**. El propietario informa que contactó Titan y espera respuesta; no se verificó ese contacto ni se contactó a nadie. Una respuesta genérica tampoco demostraría fondeo. Harían falta condiciones aplicables de anticipo, retorno, prima, pérdidas, pagos builder/proponente y ausencia de recurso, además de una oportunidad compatible.

Política determinista de esta ampliación:

1. Verificar hashes, identificadores y unidades; rechazar duplicados contradictorios.
2. Cerrar solo el escenario con cota no positiva, manteniendo explícitas sus condiciones.
3. Congelar expedientes heredados agotados y no inferir índice cero de un valor desconocido.
4. Mantener las diez filas Aave empatadas en información económica. Excluir el hash con acceso denegado de una sugerencia operativa. Usar identificador canónico solo para elegir un representante reproducible entre los restantes.
5. Dejar ranking de beneficio, probabilidad, coste de adquisición y retorno esperado en `null`.

Representante documental: `0x0ec3a4ce06ab809e82cb454a6e41b149d3bd8c5e72d0606a17fd039a2240753d`, bloque 24393012. No se afirma superioridad frente a Morpho ni frente a los otros Aave. No se adquirió su recibo. La elección sirve para especificar **un** paquete de evidencia, sin volver a escoger pufETH ni fabricar una ganadora.

## Respuestas económicas y siguiente movimiento

1. **¿Cuántas familias?** Una estrategia de liquidaciones, en dos protocolos; solo Morpho B posee un libro histórico parcial y un Aave fallido permite acotar el coste de su ejecución. Los demás son expedientes insuficientes.
2. **¿Qué se descarta?** Se conserva el escenario Morpho B de financiación >=1 bp; se añade el intento Aave fallido dentro del alcance descrito. No se descartan protocolos completos.
3. **¿Margen neto positivo demostrado?** No. El residuo superior de B no cubre obligaciones desconocidas; los importes del informe Aave no son beneficios.
4. **¿Cómo financiar/capturar?** Principal por callback o préstamo temporal condicionado, gas adelantado bajo términos verificables, venta suficiente y beneficio compatible para cada participante. Faltan pruebas de disponibilidad, pérdidas sin recurso e inclusión competitiva. No hay patrocinador comprometido.
5. **¿Fuente más útil?** Un paquete histórico completo de una liquidación Aave, con recibo, transferencias, traza de venta y financiación. Primero permitiría rechazar una ruta o medir su residuo; solo después tendría sentido reconstruir el estado y estudiar captura.

`ACQUISITION_GAPS.json` especifica ese paquete, decisiones habilitadas y términos faltantes. **No se identificó una fuente permitida que entregue el paquete completo**: identidad de proveedor, precio, disponibilidad y permisos específicos permanecen desconocidos. Una alternativa legítima futura sería un artefacto histórico público íntegro o una exportación de archivo expresamente autorizada; no se propone eludir el bloqueo del explorador ni consultar RPC ahora. Su valor informativo depende de que exista y sea accesible a coste aceptable. No se asigna valor monetario esperado ni probabilidad de éxito.

Decisión: **GO** para revisar evidencia adicional permitida y acotada; **UNKNOWN** para viabilidad económica; **NO-GO** para ejecución financiera. Las metas USD 5.000/15.000/45.000 no tienen frecuencia capturable ni neto por captura demostrados. Esta muestra no permite pronóstico mensual ni escalabilidad sin principal propio.

## Reproducción y límites

```sh
PYTHONDONTWRITEBYTECODE=1 python migration/experiments/nqc-058-multi-mine-evidence/run_checks.py
```

Checkout íntegro, Git y Python estándar 3.12.14; sin instalación ni red. La comparación y hashes de decisiones son deterministas; rutas/tiempos de logs pueden variar. No se pide al propietario Android ejecutar nada.

**12 pruebas nuevas y 9 de aislamiento aprobadas; cero fallos u omisiones en las suites ejecutadas.** Comprueban gas con cálculo Decimal independiente, compensaciones desconocidas, calldata frente a transferencias reales, pérdida de precisión, activos/cadenas distintos, doble coste, duplicados, alteraciones de fuentes, conservación de 142 decisiones y determinismo entre órdenes de lote. Mutaciones de prueba son entradas adversarias, no observaciones económicas simuladas.

Verificador: `ISOLATED_SOURCE_IDENTITY_PASS`; 531 archivos de identidad y 106 workflows deshabilitados; `original_objects_checked=false`, sin recertificación canónica. No se repiten suites anteriores sin cambios ni Rust/Solidity. No se intenta replay por falta de entradas. Los errores web y del checkout inicial ausente quedan registrados; el clon íntegro se recuperó. No hubo fallos en las pruebas ejecutadas.

Archivos: `miner.py`, `test_miner.py`, `run_checks.py`; dos entradas públicas; manifiestos Git/local; revisión documental y requisitos; comparación completa/resumen; logs, `VALIDATION.json`, `STATUS.json`, control prepublicación y `SHA256SUMS`. No se añade infraestructura live.

Seguridad: cero consultas RPC nuevas; Triport **0 conocidas/8 vitalicias**, sin canal seguro ni autoridad antirollback demostrados. Sin secretos, firmas, bundles, fondos, transacciones, cuentas, suscripciones, contactos o subagentes. Cero fondos Census/Shadow. Canary deshabilitado; los límites futuros 2.000 MXN gas, recargas 500 y revisión al gastar 1.000 sin captura no autorizan gasto ahora. Main, fuentes previas, PFT/Census, aplicaciones e integraciones intactos.
