# SUPERHUNTER — estado oficial verificable y continuidad

## Corte de continuidad — PR #50 QA cerrada y auditoría M6 local (2026-11-06)
- **Último código totalmente publicado en rama:** [PR #50](https://github.com/josuechavando350-png/nexus-quant-capital/pull/50), head `ac1952603db0c46ea7b490cfd945ddeebb221653`, dependiente de #49–#45. Sigue en borrador, sin fusionar a `main`.
- **QA integral del PR #50 cerrada y re-verificada:** `LOCAL_QA_PASS` **2140/2140**, 0 fallos/errores/skips; `verify-check` independiente aprobado; digest `9fa0f1e8e2f1dda64c5e216d7ac142588b0e1a378f47f8c2c9e3220176c2299b`. Reemplaza el registro anterior de «QA en ejecución».
- **M6 en trabajo local, NO publicado como código en GitHub en este corte:** auditoría de caminos dirigidos y brechas de evidencia `chain_path_audit.py`; 24/24 tests específicos aprobados; oráculo independiente en 1600 grafos DAG sintéticos, sin divergencias. Regresión completa M6 **pendiente de resultado**, no contada. Rama reservada `feat/superhunter-directed-chain-audit-20261106`; no afirmar que contiene código sin verificar.
- El motor M6 enumera observaciones/aristas sin soporte, ramas fuera del recorrido dirigido y obligaciones de prueba. **No confirma causalidad, autorización, incidentes, severidad ni vulnerabilidades originales.**
- Próximo gate: terminar QA M6 y `verify-check`; publicar todos los archivos exactos y comprobar Git blob SHA; abrir PR borrador dependiente de #50. Antes de fusionar revisar aislamiento NQC y suites históricas.
- Plan crítico: [SUPERHUNTER_CRITICAL_RESEARCH.md](SUPERHUNTER_CRITICAL_RESEARCH.md). No mezclar con el proyecto defensivo separado.


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
