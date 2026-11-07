# SUPERHUNTER — estado oficial verificable y continuidad

## Estado vigente — dos motores EVM y revisión de límites (2026-11-07 00:16 UTC)

Este bloque prevalece sobre las instantáneas inferiores.

- **Último código publicado:** [PR #57](https://github.com/josuechavando350-png/nexus-quant-capital/pull/57), `110a533958baa6387bac7dfe039b05fcc1609541`, árbol `7376d2b08227d047926678824e59b40d0060c5b1`. Depende de #56 → #55 → #54 y la cadena anterior. Todos siguen en borrador; no se fusionó código con main.
- **PR #56:** `a9b4b68dd6e5f022acaadb43a4bed4ff3dd738b7`, árbol `f6fa627a041c514ae7a35bead04bb978283d787d`; 2,245/2,245 QA y verificación del recibo PASS. Digest `4a4430d3cf7658910726c2b5b75eeedfef483a04f98b24d913507656ab3367af`.
- **PR #57:** 2,261/2,261 QA y verificación del recibo PASS, sin fallos/errores/omisiones. Digest `81ba5efbfdc3380aa6d9399336dc72a18ba876cb903d0c6025d679286d021254`. Árboles remotos reconstruidos idénticos a los bytes locales probados.
- **Comparación ejecutada en ambos digests:** Geth y py-evm ejecutaron ocho constructores y 144 llamadas por motor; se repitió la comparación con recompilación y ejecución real. Coincidieron estados, reversiones, gas agotado y retornos. Cuatro controles propios conocidos: 2 TP, 2 TN, 0 FP, 0 FN. Dos compilaciones no duplican el número de casos.
- Dependencias opcionales del segundo motor: 22 distribuciones y 1,021 archivos fijados. Instalación limpia con hashes comprobada. Se corrigió la lectura de cachés Python anteriores usando un prefijo nuevo por ejecución; una regresión reproduce el defecto con un módulo propio.
- py-evm 0.12.1b1 está archivado: el perfil es histórico y fijo, Cancun. Dos implementaciones comparten fuente/compilador/host; no demuestran productores independientes, generalización, costes de gas ni validez para reglas actuales.
- **Revisión estructural del repositorio:** `REPOSITORY_BOUNDARY_PASS`; 642 archivos históricos y sus árboles exactos preservados, cero workflows activos. 16 controles nuevos rechazan cambios históricos, raíces no revisadas, clientes, binarios, enlaces y cambios durante la lectura.
- El verificador histórico **permanece intacto y sigue rechazando el checkout ampliado**; pasa en la copia exclusivamente histórica. La nueva revisión no convierte ese resultado en PASS. No se certificaron aislamiento durante ejecución, ausencia de secretos, objetos originales ni Rust/NQC completo.

**Siguiente trabajo activo:** diagnóstico de requisitos locales para que una biblioteca, Python o binario incompatible produzca una causa concreta antes de ejecutar QA largo. Después, consolidar evidencia y continuar evaluación defensiva acotada.

**Avance global:** 40–42% sigue siendo referencia histórica no certificada. Vulnerabilidades originales confirmadas: 0.

## Estado vigente — QA reparada y benchmark nativo repetido (2026-11-06 23:50 UTC)

Este bloque prevalece sobre las instantáneas históricas inferiores.

| Rama | HEAD verificado | QA completa | Digest fuente |
| --- | --- | --- | --- |
| PR #54 | `9a13a11016ffadac127bdfcce1fec2ef1aa9cd1e` | 2,211/2,211 PASS | `a90f784943cd6a7cbdd5d6e3cc7a890a522699d5ff00c5ad8a12aecda9b38be7` |
| PR #55 | `63699780ae8755358c46dd0960138bca41ab321c` | 2,225/2,225 PASS | `5305d0cb78e5131ec8d3ca0b1d7f758520cad57097bc4e2e748cb4962eee7f50` |

- Se corrigió la asignación inestable de módulos entre ocho procesos. Cuatro regresiones nuevas; ninguna prueba anterior eliminada. Dos regresiones fallaban con el reparto anterior. Se separó `test_platform` de los estudios EVM, sin ampliar 180 s de pared, 90 s de CPU ni 2 GiB por proceso.
- Ambos recibos fueron verificados en procesos separados: cero fallos/errores/omisiones. Esa verificación comprueba los recibos y no equivale a repetir toda la suite. Máximos medidos por partición: 58.10 s (#54) y 60.02 s (#55). El timeout histórico no se reprodujo en este host; no se garantiza el mismo rendimiento en otros equipos.
- Árboles Git publicados y cotejados con los bytes locales: #54 `76df85b4aa236bd851cad13498ba468eb8087920`, #55 `872344f62cc708b6089bc323b59de306f5a6ee45`. Actualizaciones fast-forward con comprobación del HEAD esperado; ambos PR siguen en borrador y no se fusionó código con main.
- Entorno reproducido: Python Linux 3.12.3; Z3 4.13.3.0 con SHA-256 `7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`. No se cambiaron los pins para acomodar otra biblioteca.
- **Benchmark real sobre los cuatro contratos propios conocidos del digest #55:** solc 0.8.30 y Geth 1.17.10, bytes fijados; 2 TP, 2 TN, 0 FP, 0 FN, sin abstenciones/errores. `verify-owned-evm-score` recompiló y reejecutó los mismos controles en un segundo proceso y pasó. Dos configuraciones de compilación por caso son corroboración, no ocho muestras independientes.
- Sigue siendo una evaluación conocida, pequeña y no ciega. No acredita un segundo motor EVM, generalización, impacto económico ni vulnerabilidad original.
- Aislamiento: 642 archivos originales en `ci/`, `migration/`, `nqc-census/` conservan sus bytes. La copia exclusivamente histórica pasó su verificador (637 correspondencias) y nueve pruebas. El verificador global rechaza raíces nuevas fuera de su lista: revisión global todavía pendiente. Rust histórico no ejecutado.

**Siguiente trabajo:** comparación de ejecución sobre los mismos contratos propios con una implementación EVM diferente; mantener el límite de laboratorio y comprobar los errores, reversiones y persistencia de estado. Después, resolver la revisión global de aislamiento sin modificar los árboles históricos.

**Avance:** no se inventa un nuevo porcentaje global; 40–42% sigue siendo referencia histórica no certificada. Hallazgos originales confirmados: 0.

## Último estado — PR #55 (2026-11-06; prevalece sobre instantáneas inferiores)

- **Último PR de código:** [#55](https://github.com/josuechavando350-png/nexus-quant-capital/pull/55), borrador; rama `feat/superhunter-exact-evidence-cut-sets-20261106`; SHA `bf82b9aa92bba77e3255c1d309ec1392bc5cf7d1`. Depende de **#54 → #53 → #52 → #51 → #50 → #49 → #48 → #47 → #46 → #45 → main**. No fusionar a ciegas; todos los expedientes y originales privados quedan fuera de GitHub.
- **PR #54 corrigió referencia a módulo aún no publicado** en la CLI/quality/worker; commit de reparación `63978b85be00c20c74ba837f10d0decee14e9ac7`. Sus 14 pruebas específicas pasan. La ejecución integral sobre este commit devolvió **`LOCAL_QA_ERROR` / `TimeoutExpired` en partición 6 (límite 180 s)**; **NO es 2,207/2,207 PASS**. Necesita reequilibrio de particiones y nueva ejecución completa; el PASS de PR #55 no sustituye ese control.
- **PR #55 añade motor real `evidence_cut_sets.py`**, pruebas y documentación: seis Git blobs equivalentes exactamente a los bytes probados; 14/14 pruebas específicas, comparación 600/600 casos con un oráculo independiente y **2,221/2,221 `LOCAL_QA_PASS`** en el árbol acumulativo. `verify-check` independiente confirmó 2,221 y `source_digest=e335c9ea0dab9b6466f33dd246bd11edfc873fad784d036f9eb35368a9d1f51d`.
- **Qué aporta:** cortes mínimos por inclusión de pérdida simultánea de respaldos de evidencia ya verificados; aliases de idénticos bytes cuentan como una misma fuente de disponibilidad; recalcula triaje y registra obligaciones de evidencia que quedarían sin apoyo. **No** acredita causalidad, identidad de productor, vulnerabilidad real, impacto crítico ni autorización para acciones externas.
- **Próximos gates:** completar QA/verificación separada de PR #54, revisar aislamiento histórico NQC y ramas paralelas, validación EVM nativa independiente y evidencia de mundo real **en laboratorios propios/autorizados**. Ninguna operación sobre objetivos externos sin autorización verificable.
- **Meta de producto vigente:** investigación multidominio especializada en fallos críticos y cadenas potencialmente críticas, con forense digital y evaluación científica; ver [SUPERHUNTER_CRITICAL_RESEARCH.md](SUPERHUNTER_CRITICAL_RESEARCH.md).
- Los 40–42% históricos **no son un avance auditado** y las 2,221 pruebas no equivalen a un porcentaje ni demuestran liderazgo comercial.

---


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
