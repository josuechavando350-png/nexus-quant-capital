# Trazabilidad con NQC Miner v1.0

Fuente: PDF aportado por el usuario, 22 octubre 2026. El PDF declara ser arquitectura, no un sistema construido. Su instrucción actual exige no cruzar datos con el observador; prevalece sobre el almacenamiento compartido sugerido en las páginas 5–6.

## Componentes

| # / página | Componente | Implementación disponible | Pendiente para cierre operacional |
|---|---|---|---|
| 1 / 4 | Nacimientos | Alloy ABI, Morpho CreateMarket, Aave ReserveInitialized, ingesta histórica acotada, proveedores concordantes, journal | Suscripciones continuas, inventario de fábricas/cadenas, despliegues/proxies certificados y cobertura sostenida |
| 2 / 4 | Forks | Extracción de selectores, MinHash determinista, candidatos y referencias de código | Colector global, integración heimdall-rs y certificación semántica |
| 3 / 4 | Timelocks | Libro de operaciones, predecesores, cancelación y ejecución observada; sandbox REVM | Decodificadores de gobernanza, posiciones reales y simulación del cambio sobre estado autenticado |
| 4 / 4 | Ballenas | Grafo de asociaciones con procedencia, confianza y tiempo | Colectores multichain, resolución de falsas asociaciones y almacén de grafos |
| 5 / 4 | Incentivos | Campañas, fecha de fin y señales temporales | Colector, series reales de apalancamiento y almacenamiento integrado |
| 6 / 4 | Intereses/vencimientos | Aritmética entera Morpho documentada, supuestos de tasa constante, calendario de vencimientos | Adaptadores adicionales y proyecciones prospectivas certificadas por protocolo |
| 7 / 5 | Saturación | Liquidadores únicos, demora y propina opcionales, umbrales versionados, datos insuficientes explícitos | Medición de elegibilidad/propinas/precios, calibración y vistas ClickHouse ejecutadas |
| 8 / 5 | Valuación | Bootstrap de bloques de economía diaria, distribución, costes de fallos, score con unidades coherentes | Remuestreo de precios con liquidaciones y ejecución causal, evaluación fuera de muestra real |
| 9 / 5 | Genoma | Pipeline de investigación LightGBM y contribuciones TreeSHAP, separado del runtime | Etiquetas realizadas suficientes, validación económica y retroalimentación a colectores |
| 10 / 5 | Rival | Mezcla bayesiana Beta-Bernoulli, detección de direcciones nuevas, reset por reorg | Calibración, servicio continuo y ajustes de puja a través del observador autorizado |
| 11 / 5 | Puntos ciegos | Universo explícito, denominadores completos, vigilancia temporal y razones de omisión | Escaneo continuo suficientemente amplio y reconstrucción causal profunda |
| 12 / 5 | Adaptadores IA | Candado de evidencia diferencial/propiedades/fuzzing, REVM cerrado y pruebas por propiedades | Generación en cuarentena, Foundry fuzzing real y certificación independiente del adaptador completo |
| 13 / 5 | Bandits | Thompson sampling determinista, deduplicación de resultados y presupuesto entero de investigación | Asignación real de recursos, optimización por magnitud neta y operación presupuestada |
| 14 / 5 | Toxicidad | Evaluación de casos de transferencia y estrés de oráculo suministrados; desconocido bloquea | Generación y autenticación de baterías amplias por actor/importe/estado/proxy |
| 15 / 5 | Puente | Contrato export-only con identidad de Miner y ninguna autoridad operativa | Integración coordinada y revisada; permanece desconectado por instrucción del usuario |

## Ciclo de vida (página 3)

El camino preparatorio es `Detected → Classified → Valued → WindTunnel → Shadow → Proposed`. Cada avance exige su evidencia, alcance, código, adaptador, bloque canónico y vigencia. Los reportes de fases anteriores se revalidan al avanzar. Retirarse conserva la razón; reactivar reinicia los gates.

`Active` y `Watched` permanecen bloqueados. Una referencia de aprobación no se considera una firma verificada ni permite ejecutar. Una prueba que crea metadatos históricos en memoria sigue siendo una prueba sintética del software.

## Infraestructura (página 6)

Rust/Alloy/REVM funcionan localmente. El journal local permite desarrollar y auditar sin compartir sistemas del observador. Redpanda, Temporal, ClickHouse, Postgres, almacenamiento de objetos y observabilidad completa necesitan integración y pruebas de reinicio/carga/recuperación. Los esquemas preparados no se contabilizan como servicios funcionando. El exportador Parquet es local y no sube archivos.

Nix necesita cierre de dependencias y una construcción ejecutada para afirmar reproducibilidad de build. Los resultados estadísticos fijan semillas y dependencias, pero no se promete igualdad de coma flotante entre plataformas distintas.

## Resoluciones de auditoría

- Un timelock acredita elegibilidad, no el bloque futuro exacto de ejecución.
- El score convierte horas a coste con una tarifa explícita; no suma horas y dinero.
- Cero eventos no acredita un mercado virgen; cobertura con denominador cero es indefinida.
- La demora necesita el primer bloque liquidable; un log de liquidación por sí solo no lo proporciona.
- La propina desconocida no es cero; se separa de gas para evitar doble conteo.
- Una dirección nueva es un actor observado, no una identidad personal demostrada.
- La coincidencia de bytecode/selectores no certifica semántica ni ausencia de trampas.
- Hashes de archivos y acuerdo RPC comprueban integridad/coherencia; no reemplazan pruebas de estado o autenticación independiente.
- El entrenamiento realizado, la simulación, los fixtures y Shadow permanecen separados.
- Una interrupción deja datos provisionales; solo el cierre reconciliado del lote y del scope habilita cobertura completa.

## Salidas de fase (página 8)

| Fase | Evidencia requerida | Estado de esta entrega |
|---|---|---|
| A | Saturación completa en 2–3 cadenas y cobertura conocida | Código preparatorio; lecturas acotadas se documentan aparte y no cierran calibración económica |
| B | Minas valuadas y contrastadas con realidad durante Shadow | No realizada la ventana prospectiva |
| C | Minas propuestas, aprobadas y operadas dentro de presupuesto | No autorizada/ejecutada; firma y operación bloqueadas |
| D | Descubre, prueba, propone y aprende en un ciclo autónomo validado | Primitivas y pipeline de investigación; ciclo operacional pendiente |
