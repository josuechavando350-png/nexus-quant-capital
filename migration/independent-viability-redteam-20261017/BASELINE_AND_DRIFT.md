# NQC - Baseline y diferencias de la auditoría independiente

Fecha de trabajo: 17 de octubre de 2026. Zona de entrega: America/Mexico_City. Las capturas técnicas se expresan en UTC.

## Resultado de integridad

Los cinco HEAD de la Directiva 002 coinciden con las referencias consultadas en GitHub al inicio de esta misión. Esta igualdad fija el alcance de los documentos leídos; no acredita sus resultados históricos en cadena. No se ha recibido en este chat un informe posterior de Astra.

| Repositorio y rama | SHA de la directiva y del inicio de la consulta | Diferencia |
| --- | --- | --- |
| nexus-quant-capital / main | `16e352225ba8a6a931834c4edf3d86d9a2924b7d` | Ninguna |
| nexus-quant-capital / research/morpho-sponsored-gas-20261016 | `0f26557c1f83e12efcf364ece6cebd8505d2e2c2` | Ninguna |
| nexus-quant-capital / research/cross-repo-evidence-audit-20261017 | `ddade5d099e19449e0c4e55079a2b0c9d9ee1141` | Ninguna |
| nexus-quant-capital / nqc/viability-decision-20261016T1713 | `6693542e675f930a7ef0a4fd60cb72e7a6608845` | Ninguna |
| nexus-engine / main, sólo lectura | `380eff1fc14336bd24d93c8ef807525a7078950d` | Ninguna |

Fuentes: API de ramas de [NQC](https://api.github.com/repos/josuechavando350-png/nexus-quant-capital/branches?per_page=100) y [main de Engine](https://api.github.com/repos/josuechavando350-png/nexus-engine/branches/main). Primera verificación dentro de 2026-10-17 15:39-15:44 UTC; se conservó el resultado, pero no el segundo individual de cada respuesta. El registro posterior no sustituye la hora de adquisición. La colección devolvió 46 ramas. El número de ramas es inventario administrativo, no avance económico.

La base de la rama nueva es el commit de auditoría `ddade5d0...`, cuyo árbol declarado por Git Data es `840387bcd4c887ecc13005148dec44585ecb021f`. Se inspeccionó un árbol recursivo no truncado de 768 entradas para delimitar instrucciones y verificar ausencia de workflows activos. No se hizo un barrido del contenido de miles de archivos.

## Documentos leídos primero

- [AGENTS.md](https://github.com/josuechavando350-png/nexus-quant-capital/blob/ddade5d099e19449e0c4e55079a2b0c9d9ee1141/AGENTS.md), blob `6c2fe3771bad272bb1839aabc2b45ef636a16531`, 1,107 bytes; hash del caché exacto comprobado.
- En la rama de auditoría: `migration/cross-repo-evidence-audit-20261017/AUDIT_STATUS.md`, `CLAIM_LEDGER.json` y `CHECKPOINTS.md`.
- En Morpho: `migration/experiments/morpho-sponsored-gas/RESEARCH_STATUS.md`, `MONTHLY_POTENTIAL.md`, `PROFITABILITY_RESULTS.md`, `CASE_B_PRESTATE.md`, `PROSPECTIVE_OBSERVATION.md`, `PUBLIC_DATA_PROGRESS.md`; después, sólo recibos, trazas y páginas guardadas necesarios para contabilidad y censo.
- En viabilidad: `migration/robinhood-real-state-replay-20261016/README.md`, `migration/robinhood-viability-decision-20261016T1713/DECISION.md` y `REOPENING.md`.
- Aave/SVR: `migration/engine-v2-20261015/source/ci/nqc-census/rmc-v2-shadow/SVR_EXECUTOR_AUCTION_CAPITAL_CONTRACT.md`, en el mismo SHA de viabilidad.

Las rutas completas, blobs y hashes de los insumos analizados están en `SOURCE_LEDGER.json` y los registros parciales de `evidence/`. El estado VERIFICADO_DOCUMENTALMENTE significa que se leyó una fuente fijada; un resultado de replay escrito por su autor conserva la condición REPORTADO o SIMULADO hasta que esta misión lo reproduzca.

## Ausencias y accesos limitados

1. Está adjunto `NQC_MODELO_NORMAL_DIRECTIVA_002.pdf`. El archivo `NQC_RELEVO_MAESTRO_2026-10-17.pdf` no fue adjuntado ni leído. La directiva y los repositorios accesibles son las fuentes de este expediente. No se sustituyó el PDF ausente por recuerdos de conversaciones.
2. Tres consultas de ramas con slash codificado fueron rechazadas por el validador de URL del conector con 400/INVALID_ARGUMENT. La colección oficial de ramas, operación soportada, permitió verificar sus HEAD. No fue una denegación RPC ni una expansión de permisos.
3. Un intento de clonar por HTTPS terminó con código 128: no se pudo conectar al proxy del entorno. No se reintentó ni se solicitaron credenciales o permisos. Las lecturas posteriores utilizaron el conector GitHub ya disponible.
4. No se repitieron los RPC que habían devuelto 403/405, estado podado o método no permitido en los expedientes. Esos rechazos históricos se auditaron como respuestas guardadas; no son fallos de red nuevos de esta misión.
5. No se descargaron los 637 payloads de la importación completa sólo para una adición documental. El verificador de aislamiento original se ejecutó con los insumos disponibles y quedó BLOCKED por un payload ausente. No se declara aprobada esa certificación ni se suman sus nueve pruebas históricas a los controles nuevos. La publicación, si se completa, requiere una comparación independiente de todos los blobs/modos preexistentes entre árboles Git, preservados sin cambios.

## Diferencias frente al punto de partida

| Tema | Lectura del relevo/directiva | Tratamiento en esta auditoría |
| --- | --- | --- |
| Contadores de Morpho | La auditoría cruzada retiene 159/50/9; la directiva y el estado posterior citan 168/50/9 | Diferencia temporal entre informes, no pruebas adicionales nuestras; se preserva cada alcance. |
| Capital personal | Expedientes antiguos mencionan reserva MXN 2,000 | Para esta misión rige $0 de aportación, deuda, garantías y gasto; la cifra antigua no es caja disponible. |
| Caso B | Residual de un tercero y frontera de gas | Se recalcula con enteros desde los insumos guardados; no se promueve a replay NQC ni P&L realizado. |
| Censo 143/141 | Eventos/transacciones observados | Se recalculan filtros, concentración y recibos; ninguna reducción se llama automáticamente universo rentable. |
| Seguimiento de 95 segundos | Sin eventos indexados | Se audita también cuándo se fijó la ventana y cuándo se recibieron inputs; ausencia de resultados no prueba ausencia de oportunidades. |
| Financiación publicada | Titan y Quasar describen sponsorship | Se distingue la condición técnica de un compromiso aplicable a NQC que cubra también los fallos sin recurso. |

## Control de originales y publicación

Único destino permitido: `migration/independent-viability-redteam-20261017/`, en una rama propia derivada del SHA de auditoría. No se editan `main`, la rama Morpho, la rama original de auditoría ni `nexus-engine`. Tampoco se modifican contratos, importaciones, workflows o integraciones.

El estado de publicación, SHA nuevo y comparación antes/después se reportan con el recibo de entrega. Hasta completar creación y lectura del commit, los archivos son trabajo local y no se consideran publicados. El permiso técnico de escritura de NQC se consultó como metadato; no se alteró ningún permiso.

No hubo firmas, transacciones, solicitudes de admisión a builders, cuentas de proveedores ni mensajes a terceros. Gasto externo iniciado por las acciones de esta misión: $0. Esto no es una inspección de la facturación de servicios preexistentes del usuario.
