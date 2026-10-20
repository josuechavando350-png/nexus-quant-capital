# NQC — Censo masivo de riesgo Morpho Blue Ethereum (solo lectura)

**Resultado: motor de descubrimiento por lotes implementado y probado offline; cero capturas recientes de Morpho y cero beneficios NQC demostrados.** No es un nuevo ejecutor. Esta entrega sustituye el cuello de botella de **1 a 3 mercados por consulta de NQC067** por un filtro *global server-side* de prestatarios en riesgo en **todos los mercados LISTADOS de Morpho Blue indexados para Ethereum 1**. Un directorio REST independiente, paginado con cursor, permite enumerar mercados (incluyendo no listados si la API los devuelve), pero un directorio no equivale a posiciones ni a márgenes.

## Hallazgo que cambia la escala

La fuente primaria [`morpho-org/morpho-bots` / `bots/blue-liquidation/src/discovery/borrowers.ts`](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/blue-liquidation/src/discovery/borrowers.ts), commit anclado `08d0a415d6d027f7e401fd6a904b09bedb441668`, blob `2e4c3ff687defdf7035f303e69881273ad1aec18`, ya utiliza:

- `marketPositions(where:{chainId_in:$chainIds,healthFactor_lte:$hfLte,marketListed:true},orderBy:HealthFactor,orderDirection:Asc,first:1000,skip:$skip)`;
- paginación de **1,000 posiciones** por página hasta una barrera de **10 páginas**; y
- normalización de pares únicos `(marketId, borrower)`, seguimiento de errores, y lectura onchain *posterior* para confirmar la liquidabilidad.

El bot de referencia soporta **Base y Robinhood**, NO debe confundirse con software validado para Ethereum. NQC reutiliza solo el **documento GraphQL de descubrimiento**, **especifica `chainIds:[1]`** y excluye firmas, motores TS, bundles y ejecución. Esta búsqueda evita seleccionar manualmente mercados; su límite de 10,000 **NO representa observaciones reales ni promete cobertura total** cuando se alcanza.

La documentación [Morpho Blue API](https://docs.morpho.org/developers/api/morpho/) y [List markets REST](https://docs.morpho.org/api/markets/list-markets/) documenta `GET /v1/blue/markets?chain_id=1&limit=1000` con envoltorio `{data,cursor}` y la consulta GraphQL. El directorio REST contiene parámetros inmutables; no suministra precio ejecutable ni estado de borrowers. Documentación no es respuesta viva.

## Lo implementado, sin despliegues

`bulk_shadow.py` (biblioteca estándar Python) tiene tres funciones operativas independientes:

1. **Pantalla masiva de riesgo:** una consulta sobre los mercados *listados*, filtro indexado HF ≤1.02, orden ascendente, paginación `skip` de hasta 10 páginas × 1,000 pares (cap, no muestra). Una pasada jamás puede probar que un borrower es liquidable, que tenemos prioridad ni que exista margen positivo.
2. **Directorio completo acotado:** REST `/v1/blue/markets`, hasta 10 páginas × 1,000 mercados con cursor opaco y validación de cadena, token, identificador y LLTV. Cuenta mercados solo si realmente se ingieren páginas. Si queda cursor tras el límite, marca truncamiento. Dado que no es una foto atómica del estado de blockchain, `canonical_universe_complete=false` siempre.
3. **Reutilización de fuentes originales:** `import_nqc067_pinned_parser` carga el original `shadow.py` mediante hash de blob Git exacto; `refine_with_pinned_nqc067` analiza snapshots detallados SOLO de 1–3 mercados finalistas. `reference_scope` importa los números publicados en NQC055 (**142 expedientes, 61 mercados, 54 pares; 140 sin datos suficientes y 2 pendientes**), marcados estrictamente como ARCHIVADOS, no observaciones actuales. Ninguna otra contabilidad reemplaza el kernel de NQC055 ni se inventa un ranking por beneficio bruto.

Los datos REST y GraphQL se guardan por páginas inmutables, con SHA256, controles de posición, deduplicación, cap, coherencia del total y señalización de paginación inestable. El modo de red está **desactivado por defecto**, requiere autorización explícita por ejecución, usa solo `api.morpho.org`, no reintenta llamadas fallidas, no utiliza API keys ni hace operaciones onchain, y bloquea reinicios sobre directorios utilizados. **No hemos ejecutado las rutas de red ni el recolector en modo live.**

## Resultados medidos — sin falsear el resultado comercial

| Métrica | Observación |
|---|---:|
| Límite teórico de candidatos por pasada | 10,000 indexados listados, no ejecutados |
| Límite teórico de mercados REST por pasada | 10,000 indexados, no ejecutados |
| Expedientes archivados en el radar anterior | 142 |
| Mercados de esa muestra histórica, NO censo actual | 61 |
| Expedientes históricamente no evaluables | 140 |
| Páginas reales Morpho obtenidas durante esta entrega | **0** |
| Candidatos actuales observados y autenticados | **desconocido** |
| Cotizaciones ejecutables, financiación o ganancia NQC | **no demostradas** |

El reporte `RESULTS_OFFLINE.json` importa SOLO la transcripción delimitada de las métricas publicadas de NQC055. **No confunde ausencia de nuevos datos con cero liquidaciones**: `authenticated_live_candidate_count=null`, `authenticated_live_market_count=null`, `NQC_actual_profit=null`.

**Bloqueo físico:** la API no resolvía DNS desde el runtime local en NQC067. Posteriormente el equipo remoto NQC en línea rechazó la primera ejecución porque Desktop Commander informó cuota mensual agotada; no hubo respuesta de la API desde él y **no se volverá a intentar allí mientras siga esa limitación**. Tampoco se usan GitHub Actions/workflows, Railway, nuevas suscripciones, proxys o un proveedor alterno para eludir una negativa.

## No confundir candidatos con dinero

Un HF de indexador ≤1.02 puede seleccionar demasiado: el protocolo exige liquidabilidad real bajo oráculo/interés/estado canónico, más venta/callback, financiamiento de gas, puja, competencia y sponsor. Si la consulta retorna 0, eso solo es **0 filas según el indexador con ese filtro y esa consulta**, no prueba de ausencia de mercados, operaciones o oportunidades. Cualquier paginación truncada, duplicada o inconsistente invalida incluso la afirmación de cobertura filtrada.

**Admisión comercial `false`**, `canary_enabled=false`; NQC no ha realizado ni ganado operación, no existe sponsor Titan comprometido ni garantía de no recurso personal. Census/Shadow: cero fondos. No se publican claves, wallets ni transacciones y no se han tocado Cano, `nexus-engine`, Vercel, workflows ni `main`.

## Validación y próximo paso verdaderamente comercial

`run_checks.py`: **57 pruebas nuevas locales aprobadas** (paginación, datos incompletos, cadenas, identidad, duplicados, red sin autorización, cero retries/403, permisos y reutilización de NQC067). Regresión directa NQC067: **28 pruebas aprobadas**, total **85** pruebas de estas dos suites. No se ejecutó el verificador global PFT/Census ni suites Rust/EVM, ya que el checkout original completo no está disponible aquí.

**Siguiente acción:** obtener acceso legítimo que realmente responda al GET REST + una consulta paginada GraphQL, capturar un baseline con procedencia y repetirlo para medir cambios. Después, usar el NQC055 existente para descartar por economía, y cotizar solo candidatos auténticos. No realizar ninguna predicción de ganancia mensual ni proceder a Canary por resultados offline.
