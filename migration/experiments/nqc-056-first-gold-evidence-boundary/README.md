# NQC056 — FIRST GOLD

**Resultado: EVIDENCIA_INSUFICIENTE.** La evidencia conservada no permite autenticar el índice cero ni medir el beneficio de esta liquidación. Se cumple el criterio de éxito 3: límite de información verificable y especificación de evidencia faltante. No se ha autenticado nueva evidencia de cadena, descartado una ruta económica ni demostrado beneficio capturable por NQC.

Base directa: `825b9d284fe80669ed999906c298041ad2fcac47`. Rama: `research/nqc-056-first-gold-evidence-boundary-20261019`. Solo archivos nuevos en este directorio. `commercial_admission=false`.

## Hallazgo nuevo y alcance

El candidato ya era el tercero de doce en `morpho-sponsor-e2e-20261017`, commit `937a833a481fd69d2ce96152deb7d4d0760d6596`, puntero `/candidates/2`, con categoría `UNRATED_MISSING_WITNESS`, gas y beneficio desconocidos. Su selección quedó fijada el `2026-10-17T17:28:07.162034+00:00`. El lock identifica exactamente los mismos hashes de las páginas originales y del selector. NQC055 volvió a priorizar una observación existente: no descubrió otra liquidación ni añadió corroboración independiente.

Se buscaron identificadores del candidato, mercado, activo, bloque y padre en **1.293 blobs Git / 95.800.877 bytes**, alcanzables desde **81 ramas / 80 commits distintos**, exclusivamente bajo `migration/experiments/`. Se incluyeron versiones históricas y contenedores ZIP/PYZ, gzip, tar y archivos `.b64`: **3.089 objetos o miembros inspeccionados**, sin errores ni límites alcanzados. Los 15 blobs con coincidencias son páginas del mismo indexador, respuesta nula, selecciones derivadas, documentación o tests. `HIT_REVIEW.json` deja explícita la revisión manual; el programa exige que ninguna coincidencia quede sin revisar.

No se identificó cabecera, cuerpo de bloque, recibo no nulo ni traza del candidato. Esta búsqueda delimitada **no demuestra ausencia universal**: no interpreta todo formato, cifrado o representación semántica posible ni consulta archivos externos. Los hashes prueban integridad/procedencia de archivos; no convierten respuestas de un indexador en pruebas de consenso.

## Identidad y orden

Transacción: `0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4`.

| Campo | Evidencia disponible | Estado |
|---|---|---|
| Cadena y protocolo | Ethereum 1, evento indexado como liquidación Morpho Blue | Afirmación del indexador |
| Bloque / posición | 26104570 / txIndex=0 / logIndex=3 | No autenticados |
| Mercado | `0x0eed5a89c7d397d02fd0b9b8e42811ca67e50ed5aeaa4f22e506516c716cfbbf` | ID reportado; faltan parámetros completos autenticados |
| WETH / pufETH | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` / `0xd9a442856c234a39a81a089c06451ebaa4306a72`, 18 decimales | Identidad y escala reportadas, sin transferencias verificadas |
| Liquidador | `0x8a321218956ee460eaff36171d85d1d0baae5575` | No demuestra sender, runtime ejecutor ni propiedad de NQC |
| Deudor, oracle, IRM, pools, código ejecutado | No identificados para esta transacción | Desconocidos |
| Hash/cabecera, transactionsRoot, bytes de transacción, pertenencia | No identificados | No se puede autenticar el orden |

Las páginas forward `/response/data/marketTransactions/items/91` y reverse `/response/data/marketTransactions/items/51` coinciden en los campos comparados, después de normalizar enteros. Ambas proceden de `https://api.morpho.org/graphql`; son una sola fuente de afirmaciones, no dos fuentes independientes.

El archivo original `receipt-14.json` conserva HTTP 200 con `result:null`, consultado el `2026-10-17T04:50:04.723689+00:00` para este hash. Esto no prueba éxito, fallo, ausencia de liquidación ni costes nulos. No se reintentó la petición.

Si en el futuro se autentica txIndex=0, se eliminan las transacciones ordinarias anteriores del bloque. Permanecen necesarios el estado autenticado del padre 26104569, transiciones de sistema previas, configuración de fork/EVM, contexto de bloque y código/almacenamiento histórico de todas las cuentas alcanzadas. No se intentó replay ni se reemplazaron entradas por ceros. Sin traza ni identidades completas tampoco puede enumerarse honestamente el conjunto exacto de slots transitivos.

## Contabilidad y descarte temprano

Importes **reportados**, no reconciliados con recibo/transferencias: deuda `0.590976235877976338 WETH`, colateral `0.569144086683595914 pufETH`. No son cantidades intercambiables. No existe valoración histórica ejecutable del pufETH en los archivos identificados para esta operación.

| Magnitud | Resultado |
|---|---|
| Venta, ingresos brutos y excedente sobre deuda | Desconocidos |
| Gas usado, precio efectivo, transferencia a coinbase | Desconocidos |
| Prima de financiación, obligaciones adicionales, pérdidas por fallos | Desconocidos |
| Cota superior/inferior del beneficio neto | Desconocidas |
| Beneficio neto capturable por NQC | No demostrado |

Única condición aritmética necesaria: **si** las cantidades reportadas fueran las realmente recibidas/repagadas, se vendiera todo el colateral y las restantes obligaciones fueran no negativas, un residuo estrictamente positivo exigiría obtener al menos `590976235877976339` unidades mínimas de WETH (`0.590976235877976339 WETH`), antes de cubrir las otras obligaciones. El umbral medio de cobertura de deuda es exactamente `295488117938988169 / 284572043341797957 WETH/pufETH`. No es precio observado, cotización, cota superior de venta ni prueba de liquidez; superar el umbral no basta para beneficio neto.

No hay una cota superior no positiva que permita descartar este candidato, ni margen positivo acreditado que permita promoverlo. La conclusión económica permanece desconocida. El descarte condicionado del caso B no se transfiere a esta liquidación.

## Financiación sin principal propio

Se reutilizó la fuente conservada de Morpho, upstream `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`. El chequeo confirma el orden textual en `liquidate`: transferencia del colateral al llamante, callback `onMorphoLiquidate` si `data.length > 0`, y cobro de `repaidAssets` mediante `safeTransferFrom`. No recompila ni vincula esa fuente con el runtime histórico del candidato.

| Ruta condicionada | Lo que permitiría | Lo que falta |
|---|---|---|
| Colateral primero, venta en callback y repago | Evitar adelantar todo el principal si la venta entrega suficiente activo de deuda | Runtime verificado, posición liquidable, callback ejecutor, pool/ruta y liquidez histórica, salida neta, allowances, obligaciones y condiciones de inclusión |
| Financiación temporal de un tercero | Adelantar deuda o liquidez de ejecución | Oferta/capacidad verificables, activo y monto disponibles, prima, devolución y condiciones; ninguna gratuidad se presupone |
| Adelanto/patrocinio de gas | Cubrir la obligación inicial de ejecución | Compromiso y saldo del pagador, límites, reembolso, costes de fallos; no existe patrocinador acreditado para NQC |

Una venta posterior dentro de la transacción no elimina la obligación inicial de gas del mecanismo de envío aplicable. No hay préstamo ni gas gratuitos demostrados. Tampoco se puede conservar una hipotética puja del competidor y asumir la misma inclusión. Solo tras reconciliar venta, principal, gas, financiación, inclusión y otras obligaciones podría delimitarse un residuo; los costes ya incorporados en una venta neta no se descontarían otra vez. No se implementó una reconciliación ficticia sin transferencias.

## Paquete mínimo que cambiaría la decisión

1. **Identidad/orden:** cabecera canónica del bloque objetivo con procedencia y anclaje verificables, bytes de la transacción y prueba de pertenencia al índice real contra `transactionsRoot`, o cuerpo completo que permita reconstruir esa raíz. Un campo txIndex de otro indexador tampoco sería prueba suficiente.
2. **Evento y gas:** recibo completo asociado criptográficamente al bloque/índice y `receiptsRoot`, logs íntegros y gas de la transacción. El precio efectivo debe poder derivarse de los campos de transacción/cabecera o verificarse; no es un campo comprometido por el recibo de consenso. Si no fuera índice cero, haría falta el recibo anterior o evidencia equivalente para separar gas acumulado.
3. **Venta y flujos:** traza íntegra o cambios de balances/estado equivalentes, con procedencia y vínculo a esa ejecución; transferencias de WETH/pufETH/ETH, contratos, venta, pago de inclusión, entradas/salidas del ejecutor y obligaciones de repago. El recibo solo no descubre necesariamente transferencias nativas internas ni obligaciones fuera de cadena.
4. **Obligaciones y captura:** términos de financiación y adelanto de gas, reembolsos/pagos externos y propiedad de balances. Para evaluar ejecución por NQC, además disponibilidad real de esos acuerdos, ruta a su alcance y evidencia competitiva. El éxito de otro operador no prueba captura por NQC.

Primero ese paquete permitiría medir la operación histórica y decidir si merece reconstruir el estado. Un replay defendible exigiría después el padre y testigos de cuentas/slots/código, resolución de proxies/dependencias y configuración/transiciones EVM. Ninguno de estos datos se adquirió ni su adquisición queda autorizada aquí.

El siguiente movimiento de mayor valor informativo es **obtener un paquete histórico completo bajo autorización específica futura**, si existe una fuente permitida que pueda entregarlo sin reintentar o eludir la restricción vigente. Ese valor es condicional a su disponibilidad, integridad y coste; no se asigna una rentabilidad esperada. Mientras falte, suspender este candidato. Reordenar de nuevo las mismas doce observaciones no resuelve el bloqueo. No hay base para proyectar $5.000, $15.000 o $45.000 mensuales.

## Archivos, reproducción y validación

- `corpus_scan.py`, `REF_SNAPSHOT.json`, `evidence/corpus.json`: inventario acotado reproducible, blobs y SHA256.
- `check_evidence.py`, `SOURCE_MANIFEST.json`, `HIT_REVIEW.json`, `evidence/decision.json`: verificación dirigida de 16 fuentes y explicación de la decisión. Reutiliza `core.py` NQC055 sin modificarlo ni reconstruir el radar.
- `test_evidence.py`, `run_checks.py`, `VALIDATION.json`, logs: **9 tests nuevos + 9 tests de aislamiento aprobados; 0 fallos, 0 omitidos en esas suites**. Verificador de aislamiento: `ISOLATED_SOURCE_IDENTITY_PASS`; no recertifica el productor ni verifica todos los objetos originales.
- `STATUS.json`, `PREPUBLICATION.json`, `SHA256SUMS`: estado, comprobación remota previa y hashes de todos los demás archivos nuevos.

En un checkout íntegro con los commits de `REF_SNAPSHOT.json` y las fuentes originales disponibles, sin dependencias externas nuevas:

```sh
PYTHONDONTWRITEBYTECODE=1 python migration/experiments/nqc-056-first-gold-evidence-boundary/run_checks.py
```

Python usado: 3.12.14; biblioteca estándar y dependencia NQC055 fijada por hash. `run_checks.py` regenera resultados/logs locales; los tiempos y rutas de logs pueden variar. El corpus y la decisión son deterministas para los mismos objetos. No necesita acceso de red. No se exige al propietario ejecutar terminales.

No se repitieron suites anteriores sin cambios, ni Rust/Solidity. Replay no ejecutado por falta de entradas; RPC no ejecutado por prohibición. Las mutaciones y el archivo comprimido sintético de tests solo prueban el detector, no representan observaciones de mercado.

Seguridad: cero peticiones RPC nuevas; Triport conserva **0 consumidas conocidas de 8 vitalicias**, sin reinicio. Registro global y canal seguro no demostrados. Sin inspección de secretos, fondos, firmas, broadcasts, pagos, despliegues, nuevas cuentas o subagentes. Sin Canary ni capital propio; los límites de gas futuro no autorizan gasto ahora. No se modificaron main, experimentos previos, PFT/Census ni integraciones.
