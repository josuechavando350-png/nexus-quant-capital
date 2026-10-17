# Continuidad de Directiva 003

Fecha: 2026-10-17. Rama `research/nqc-morpho-sponsor-e2e-20261017`, basada en `544fd2d16d0b1cf1018dce006702a7abcbf0d0c6`. Consultar `PUBLICATION.md` para commits publicados/read-back. El HEAD que contiene este archivo se obtiene con `git rev-parse HEAD`; no se incrusta un hash autorreferencial imposible de conservar al editar el propio commit.

## Implementado y verificado

- `build_local.py`: original Morpho, V2, colateral ERC20 upstream y Solmate WETH, compiladores fijados; contrato histórico NQC intacto.
- `run_e2e.py` / `LabSupport.sol`: proceso Anvil local finito, sin claves, sin fork; 21 escenarios con recibos, call traces y snapshots; CREATE correcto y fallido, repago insuficiente, donaciones, gas alto y F01–F12.
- `reconcile.py`: flujo comprometido ETH/token, gas/burn/priority fee, inventario inicial, devolución recibida, margin del sponsor y bridge al gate manteniendo UNKNOWN.
- `sensitivity.py`: fracciones exactas para conversión y fronteras de gas, pool, remuneración y cap. Gas modelado fuera de los escenarios medidos se etiqueta matemático.
- `select_candidates.py`: 12 transacciones únicas seleccionadas sin comparación nominal entre activos; ningún reemplazo por datos faltantes.
- `test_evidence.py`: 10 tests de conciliación, corrupción de evidencia, límites, temporalidad de reorg, inventarios y no ascenso a certificación.

Validación ejecutada: 168 tests Python previos; 33 + 17 Solidity; 9 aislamiento; 10 nuevos tests de evidencia; 21 controles EVM y conciliación por paso. No se suman iteraciones como pruebas distintas. Logs completos en `evidence/`. Históricos/Rust/servicios externos: estados separados en `REGRESSION_AND_REPRODUCE.md`.

## Resultados económicos

Base sintética: NQC final 0.159365645570551238 WETH y 0 ETH, desde cero. Sponsor caja +0.043321588 ETH, después del cargo de oportunidad de laboratorio +0.043318588 ETH. Builder simulado +0.002 ETH; proponente tip +0.04 ETH más priority fees. Gas total 2,339,206, coste efectivo 0.004678412 ETH a 2 gwei. Inventarios externos y capital de la DEX no son ingreso NQC.

Mismo ciclo a 21 gwei: sponsor −0.001123326 ETH de caja, −0.001153326 ETH con oportunidad. Secuencias interrumpidas: no se presume devolución del anticipo; saldo retenido en EOA no es ganancia. Prueba de repago un wei insuficiente: Morpho original revierte, se deshace el swap y se cobra gas.

El flujo local no es un bundle aceptado ni un replay de Ethereum. EVM_LOCAL_PASS solo corresponde a ciclos completados; flags históricos/comerciales son null. P&L NQC certificado US$0; mensual NO ESTIMABLE.

## Bloqueos y correcciones

Caso B sin testigo padre+tx0+Fluid; 12 candidatos UNRATED_MISSING_WITNESS. No se inventan estados ni ingresos. La cifra B 0.001651296044494913 ETH continúa siendo residual aritmético de terceros después del tip completo, no beneficio NQC. No hay una contraparte real ni términos de ausencia de recurso, identificación del builder o prueba de captura.

Se adoptó la corrección independiente: el seguimiento de 95 s se eligió después del cierre de su ventana y mezclaba alturas. No demuestra observación prospectiva coherente. Un programa público verificable podría acreditar financiación; no se exige exclusivamente un acuerdo bilateral.

Se corrigieron el lector prematuro de recibos Anvil, el límite provisional del CREATE Morpho de setup y la proyección semántica al gate. No se modificó la lógica del ejecutor histórico. Ver limitaciones de reproducción en el documento de regresión.

Corrección de comparabilidad: el build inicial de `9188d693...` tenía optimizer runs 999999; se alineó Morpho a 200 y ahora coincide exactamente con el bytecode de la referencia previa. Se repitieron los escenarios; el cambio añade 544 gas a la liquidación base. El manifiesto conserva settings y el test exige esa identidad. Los márgenes de este documento ya incluyen la corrección.

## Continuación

Decisión y única siguiente prueba: `DECISION_FOR_DIRECTOR.md`. Comparar el ciclo C2 con recibos completos sobre esta fixture, sin nuevos servicios ni acceso financiero. Archivos de entrada: runner, ledger y artefactos Bundler3 originales anteriores. Criterio: fuente fijada, mismo estado, cero activo NQC inicial, todos los costes y movimientos conciliados, distinción de margen del operador y del financiador. La línea histórica solo se reabre con evidencia faltante auténtica.
