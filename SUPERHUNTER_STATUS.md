# SUPERHUNTER — estado oficial verificable y continuidad

## Trabajo posterior en verificación — PR #54 y respaldo local M9 (2026-11-06)
- **PR #54 publicado, en borrador:** [Bounded higher-order evidence dependency](https://github.com/josuechavando350-png/nexus-quant-capital/pull/54), HEAD inicial `4a51ecbbcad73368f3f18c503af96501d2e005cf`, dependiente de PR #53; solo seis archivos `superhunter/` y **14 pruebas específicas** documentadas. Su **QA completa por HEAD de GitHub no queda certificada** por la prueba de un árbol local más amplio.
- **Árbol local combinado M9, distinto de PR #54:** añade también un motor exacto de cortes mínimos de evidencia `evidence_cut_sets.py`, con 14 pruebas propias (600 casos contra oráculo exhaustivo). La versión combinada documentada en los artefactos de conversación `SUPERHUNTER_M9_COMPLETE_20261106.zip` (SHA-256 `73bec007b5c261315321868030446ff3303534bc80b5050432f8637be7f90883`) y `SUPERHUNTER_M9_COMPLETE_TRANSFER_20261106.json` (9 archivos fuente y hashes) fue **reejecutada localmente 2,221/2,221 `LOCAL_QA_PASS`**, con `verify-check` independiente PASS y `source_digest=e335c9ea0dab9b6466f33dd246bd11edfc873fad784d036f9eb35368a9d1f51d`. **Esta versión combinada no está publicada íntegramente en GitHub.**
- **Próxima entrega necesaria:** comparar PR #54 con el ZIP M9 combinado, reconciliar las modificaciones compartidas de `quality.py`, `quality_worker.py` y `__main__.py`, publicar solo la diferencia exacta en rama dependiente, verificar los Git blob SHA, crear PR borrador y reejecutar QA en el HEAD resultante. No fusionar PR antiguos ni tocar NQC histórico.
- Ambos análisis son **solo de disponibilidad de evidencia**. No prueban causalidad, autenticidad de productores, vulnerabilidades reales o severidad crítica; ninguna prueba externa fue autorizada.

## Estado más reciente — PR #53: 2,193 pruebas verificadas (2026-11-06)
- **Último código publicado y probado:** [PR #53](https://github.com/josuechavando350-png/nexus-quant-capital/pull/53), commit `9a432391858498f297f7dc3d84a9e54695b60df7`, rama `feat/superhunter-common-bundle-evidence-20261106`, basada en PR #52 → #51 → #50 → #49 → #45. **Borradores abiertos, NO fusionados con main.**
- **2,193/2,193 `LOCAL_QA_PASS`** (2,180 anteriores + 13 tests de alias de evidencia), 0 fallos/errores/omisiones. **`verify-check` separado confirmó 2,193/2,193 `LOCAL_QA_PASS`**, source digest `47f1cd3ccd104c39a3fb8013850eb0b13c00ff5fe0240e6e815147759ea6c8e1`. El check actual corre en el paquete publicado sin activar ninguna actividad externa.
- PR #52: [análisis contrafactual de pérdida de fuentes](https://github.com/josuechavando350-png/nexus-quant-capital/pull/52), commit `f227b00f83fbff90db15c3de83a09c617d0a220a`, 2,180/2,180 `LOCAL_QA_PASS`, oráculo enumerativo 500/500. PR #53: grupos de alias por bytes idénticos de `COMPLETE.json`, ablación conjunta y revisión independiente de la prioridad.
- El nuevo código NO demuestra independencia de productores cuando los hashes difieren; tampoco autentica productores, confirma vulnerabilidades o da permiso para escanear objetivos. Solo evidencia offline privada de laboratorio.
- Diff de PR #53: **6 archivos `superhunter/`**; 6 Git blobs comparados con el manifiesto antes del commit; **NQC histórico, workflows, `ci/`, `migration/` y `nqc-census/` no modificados**.
- El control estático reporta **81 módulos, 0 imports locales sin resolver**, pero `SOURCE_GRAPH_REVIEW_REQUIRED` por carga dinámica heredada, no certificación total del wiring. Suite NQC/Rust histórica, aislamiento global y benchmarks ciegos **pendientes**.
- **Siguiente hito:** evaluar cortes mínimos de pérdida combinada de respaldos (`minimum evidence cut sets`) y comparar el algoritmo con un oráculo exhaustivo; ejecutar QA integral antes de incorporarlo como prueba oficial. No deducir porcentajes nuevos del conteo de tests.

## Estado más reciente — PR #51 con 2,164 pruebas verificadas (2026-11-06)
- **Último código público:** [PR #51](https://github.com/josuechavando350-png/nexus-quant-capital/pull/51), commit `539365f47bf46d86c623952f2d1de0682aa5bf33`, rama `feat/superhunter-directed-chain-audit-20261106`, base **PR #50** y cadena #49→#45. Todos siguen en **borrador sin fusionar a main**.
- **QA integral de PR #51: 2,164/2,164 `LOCAL_QA_PASS`**, 0 fallos, errores u omisiones; `verify-check` independiente **2,164/2,164 `LOCAL_QA_PASS`**. Source digest `d41f0597f53149100cffc310bae4f88985b74b2bf969c779d3aaa972f215cc4e`.
- PR #50 regresión histórica **2,140/2,140** confirmada; PR #51 preserva esas pruebas y añade **24/24 específicas**. Oráculo enumerativo independiente: **1,600/1,600 DAG sintéticos** coinciden con auditoría de recorridos.
- `chain_path_audit.py`: reabre triaje y originales privados, detecta aristas/observaciones sin soporte, secuencias dirigidas, ramas sin cobertura completa y obligaciones de prueba. Nunca eleva severidad potencial a vulnerabilidad confirmada; no ejecuta objetivos externos.
- **Seis Git blob SHA** del incremento comprobados contra código probado; diff exactamente seis archivos `superhunter/`, **cero** modificaciones históricas NQC ni workflows. `audit-wiring`: 79 módulos, 0 imports locales sin resolver; `SOURCE_GRAPH_REVIEW_REQUIRED` por carga dinámica heredada, no certificación runtime completa.
- **No se ejecutaron** la suite histórica completa NQC/Rust ni el verificador global de aislamiento; sin benchmark ciego externo, escaneos, hallazgos de terceros, vulnerabilidades confirmadas, programas 24/7 ni pagos. No fusionar PRs hasta revisión.
- **Próximo gate:** validación de reproducción independiente de impacto en laboratorio, autenticación de reglas/participación y aislamiento histórico. No asignar porcentaje global a partir del conteo de tests. El 40–42% es referencia informal no auditada.
- Estrategia crítica/multidominio: [SUPERHUNTER_CRITICAL_RESEARCH.md](SUPERHUNTER_CRITICAL_RESEARCH.md). No mezclar con la plataforma defensiva independiente.

## Actualización en curso — PR #50 (2026-11-06)
- **Último código publicado:** [PR #50](https://github.com/josuechavando350-png/nexus-quant-capital/pull/50), commit `ac1952603db0c46ea7b490cfd945ddeebb221653`, rama `feat/superhunter-critical-chain-triage-20261106`, base **PR #49**. PR abierto en borrador, **NO fusionado**.
- Implementa `critical_chain.py`: triaje offline de hipótesis potencialmente críticas y cadenas bajo/medio; valida DAG, identidades, referencias exactas a fuentes forenses, correlación y replay EVM; siempre `critical_impact_confirmed=false`, `vulnerability_confirmed=false`, `active_testing_permitted=false`.
- **27/27 pruebas nuevas específicas PASS.** **QA integral 2,113 anteriores + 27 nuevas: en ejecución, NO aprobar anticipadamente.** Fuente Git: seis archivos bajo `superhunter/`, seis Git blob SHA verificados; ningún otro directorio modificado.
- `audit-wiring`/ `verify-wiring`: 78 módulos, 0 imports locales sin resolver; `SOURCE_GRAPH_REVIEW_REQUIRED` por carga dinámica heredada, salida 1 deliberada, no conectividad runtime certificada.
- Estrategia mundial con prioridad crítica publicada en [SUPERHUNTER_CRITICAL_RESEARCH.md](SUPERHUNTER_CRITICAL_RESEARCH.md). El próximo agente DEBE revisar PR #50 y su validación antes de reanudar. Mantener las dependencias #45–#49 y el aislamiento NQC intactos.


**Corte:** 2026-11-06. **Plan completo:** [SUPERHUNTER_MASTER_PLAN.md](SUPERHUNTER_MASTER_PLAN.md). **Principio:** no inventar pruebas, hallazgos, porcentajes ni capacidades completas. Esta página se actualizó después de ejecutar la regresión del PR #49.

## Cómo retomar en otra conversación
1. Leer este documento y el [plan maestro](SUPERHUNTER_MASTER_PLAN.md), luego `AGENTS.md` y la configuración de aislamiento NQC. Comprobar cabezas Git actuales, no confiar ciegamente en las SHA escritas aquí si el repositorio avanzó.
2. **Fuente más avanzada publicada:** [PR #49](https://github.com/josuechavando350-png/nexus-quant-capital/pull/49) (borrador; rama `feat/superhunter-evm-semantic-replay-20261106`, SHA `81f8d04637e15aa44d3b90a8b226e5a37311850f`). Depende estrictamente de PR #48 -> #47 -> #46 -> #45 -> `main`. No sacar código de una rama anterior y reemplazar el acumulado.
3. La rama `main` contiene la documentación de continuidad, **no** el paquete `superhunter/` consolidado. No fusionar sin reconciliar dependencias, revisar aislamiento histórico y comprobar resultados.
4. Recuperar rama/PR y reejecutar todas las pruebas con sus límites, verificadores y evidencias. Los expedientes de casos privados NO están en GitHub ni deben publicarse.

## Cadena de código, commits y evidencia

| PR | Commit HEAD verificado | Trabajo implementado | Pruebas del paquete en la rama (localmente) |
|---|---|---|---|
| [#45](https://github.com/josuechavando350-png/nexus-quant-capital/pull/45) | `738511fa90cb7fd2bae5e6f9aec6cc64529bc2b8` | Recuperación de 214 archivos públicos con hashes Git comprobados | 2,005/2,005, `LOCAL_QA_PASS` |
| [#46](https://github.com/josuechavando350-png/nexus-quant-capital/pull/46) | `97240f29cab405ed2524f6e0a1c70a2041e5f25e` | Cronología forense, parser de exportaciones `journalctl -o json` y verificación de bytes | 2,041/2,041 |
| [#47](https://github.com/josuechavando350-png/nexus-quant-capital/pull/47) | `08f91972845876f807e64a246a0944b0bb5871c9` | Correlación declarativa entre fuentes forenses, incertidumbre y ciclos | 2,062/2,062 |
| [#48](https://github.com/josuechavando350-png/nexus-quant-capital/pull/48) | `4e66ae5c71dd7ec77b95a15f3a55473539715664` | Enlace SHA-256 exacto de journal con traza EVM, decodificación de PCs y replay del expediente | 2,084/2,084 |
| [#49](https://github.com/josuechavando350-png/nexus-quant-capital/pull/49) | `81f8d04637e15aa44d3b90a8b226e5a37311850f` | Intérprete EVM propio **acotado**; replay independiente de stack, saltos y secuencia PC; trazas falsas semánticamente imposibles rechazadas | **2,113/2,113** |

Todos los PR listados están **abiertos en borrador y no fusionados** al corte. El incremento #49 cambió exactamente **6 archivos bajo `superhunter/`**: 3 añadidos y 3 editados; **219** archivos anteriores locales no cambiaron, 0 eliminados. Los 6 Git blob SHA-1 se verificaron contra la fuente de prueba antes del commit.

## Validación efectiva más reciente (PR #49)
- Ejecutados los 8 grupos de control de calidad, sin retirar test IDs ni aumentar los límites de los workers. Resultado: **`LOCAL_QA_PASS`, 2,113 pruebas, 0 fallos, 0 errores, 0 omisiones, 0 expected failures y 0 unexpected successes**.
- Ejecutado en proceso separado `verify-check` sobre el paquete completo: **`LOCAL_QA_PASS`, 2,113 pruebas**.
- Identidad de fuentes: `d1cdf6e398c123481f9f6974b9075b682e15fdcf10eecaaed2a9593065159cf9`.
- `audit-wiring` + `verify-wiring`: **77 módulos, 0 imports locales sin resolver**; estado `SOURCE_GRAPH_REVIEW_REQUIRED` por carga dinámica heredada en `native_runtime.py`. El código de salida 1 es deliberado; NO certificar todas las conexiones runtime.
- 29 pruebas nuevas enfocadas pasan sobre el intérprete; se incluyen escenarios con `JUMPI` declarado incorrectamente, errores de pila, opcodes no soportados, alteración de evidencia aun con hash re-sellado, verificador en proceso separado y preservación de privacidad.

**Comandos (usar desde raíz del repositorio en el HEAD del PR #49):**
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m superhunter check --out /ruta/privada/qa-nueva
PYTHONDONTWRITEBYTECODE=1 python3 -m superhunter verify-check --bundle /ruta/privada/qa-nueva
PYTHONDONTWRITEBYTECODE=1 python3 -m superhunter audit-wiring --out /ruta/privada/wiring-nuevo
PYTHONDONTWRITEBYTECODE=1 python3 -m superhunter verify-wiring --bundle /ruta/privada/wiring-nuevo
```

### Qué demuestra y qué NO demuestra
- El módulo #49 **sí calcula** por un intérprete separado una semántica acotada de stack y flujo PC para trazas de laboratorio. No es otro validador de nombres: rechaza saltos imposibles dados los operandos reales, y conserva evidencia privada verificable.
- **NO** ejecuta Geth nativo, RPC, cadena real, storage, gas exacto, llamadas externas, contratos arbitrarios ni sensores remotos. Los datos pueden ser fabricados por el productor, de modo que el resultado `BOUNDED_STACK_PC_REPLAY_MATCH` **no** prueba autenticidad, incidente o vulnerabilidad real.
- No se ejecutaron en esta entrega el verificador completo de aislamiento histórico, toda la suite NQC/Rust ni GitHub Actions; no hay certificación nueva de PFT/Census ni hallazgos originales confirmados. No hay benchmark ciego externo, resultados económicos ni operación 24/7/20 programas validada.

## Inventario y metas sin inventar porcentajes
- Baseline de Biblioteca: `SUPERHUNTER_holdout_etiquetas_2005.zip`, SHA-256 `c5a3ce77720213a3fa4e19da8faac84a41594b7823e90d2ac246d5119e57267f`; solo el código/manifest público se recuperó al PR #45.
- Catálogos originales en `superhunter/`: `integration-checklist.json` **27**, `capabilities.json` **50**, `research_initiatives.json` **25**; el plan agrega 100 capacidades propuestas en 10 disciplinas y cinco líneas originales de investigación. No declararlas implementadas por figurar en listas.
- La referencia conversacional **40–42% no es un porcentaje técnico auditado**. El progreso técnico actual consta por los hitos y tests arriba; el porcentaje total sigue **sin determinar**.

## Próximas acciones técnicas priorizadas
1. Revisar y cerrar aislamiento y conflictos de las ramas encadenadas #45–#49 sin afectar `ci/`, `migration/`, `nqc-census/`, sus artefactos originales ni `nexus-engine`.
2. Reproducir la nueva vinculación contra una **ejecución EVM nativa e independiente** con binario autenticado y propiedad de prueba delimitada; fallar si falta herramienta, sin fabricarla.
3. Extender M1 con una segunda fuente de evidencia autentificada, grafo de hipótesis y estudio causal reproducible, separado estrictamente de hechos demostrados.
4. Ampliar formalización, DFIR y sensores propios según el plan maestro, con pruebas negativas, integraciones end-to-end y benchmark ciego externo antes de alegar superioridad.
5. Mantener PRs en borrador sin fusionar hasta cumplir gates históricos; registrar hashes, pruebas y límites en cada entrega.

**Límites permanentes:** investigación white/grey hat únicamente autorizada u offline; nada de exploración intrusiva de terceros, firma, fondos, despliegues, cuentas externas o reportes automáticos fuera de reglas. No mezclar con la plataforma defensiva independiente. Nunca tocar Cano, Vercel o repositorios clientes.
