# Variante cero principal - NO EJECUTADA

Estado: BLOCKED_BY_ORIGINAL. No hay tx local, receipt, gas medido, callbacks ejecutados, deuda pagada ni flash swap devuelto por la variante. La puerta A no pasó y por ello no se lanzaron test_02, test_03 ni test_04.

Se conservan sin modificar HistoricalFlashExecutor.sol y HistoricalFlashReplay.t.sol como fuentes previas. La variante propuesta solicita 616687327559 unidades USDC del V2 original, liquida la misma posición Morpho y vende UNI mediante V3 antes de devolver WETH. Esta descripción del código no afirma ejecución.

La lectura real del slot 8 de V2 al padre permite contrastar aritméticamente 266862310264222944156 wei WETH como mínimo del modelo V2 para ese output. La coincidencia no sustituye el prefijo, el oráculo, la ejecución V3 ni la invariante al finalizar el callback.

Pendientes: capital inicial cero comprobado en un ejecutor efectivamente desplegado en el fork, callbacks autenticados y spoofing, devolución atómica, slippage, 1 wei, insuficiencia de saldo, rollback completo, receipt íntegro, coste intrínseco/deployment/aprobaciones y saldo del beneficiario. Ninguna prueba pendiente se marca PASS.

Limitación adicional de la fuente heredada: sponsorPayment=0 aisla la ruta de tokens; gasleft mide scopes internos, no un receipt facturado. Incluso si esos tests pasaran en el futuro, habría que completar los requisitos de logs, recibos, costes y financiación de la Directiva 068 para aceptar B/C/D.
