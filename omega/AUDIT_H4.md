# Auditoría H4 — Opportunity Dossier / Evidence Vault

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.
Baseline previa a sincronización de inventario: `462bd0aaf68b6e40976feeec1a424034592a993e`.

## Alcance

Este hito añade una capa Omega de expediente por oportunidad para Census. No
certifica el componente 29, no reemplaza el store Rust existente y no concede
autoridad de ejecución.

## Implementación

- `opportunity_vault.py`: valida un dossier ligado a bloque, protocolo, mercado,
  posición, decisión, economía, competencia, escenarios, outcome y referencias
  de evidencia.
- `store_dossier`: escritura canónica, content-addressed, atómica y sin
  sobrescritura.
- `query_dossiers`: consulta fail-closed; cualquier registro desconocido,
  alterado o malformado bloquea la lectura completa.
- `OPPORTUNITY_DOSSIER_CONTRACT.md`: contrato explícito de alcance.

## Pruebas ejecutadas

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_opportunity_vault.py`

Resultado: **19 passed, 0 failed, 0 errors, 0 skipped**.

Las pruebas cubren: prohibición de GO en Census; prohibición de firma, broadcast,
gasto, cierre de Census y avance de fase; identidad ligada a bloque/posición;
las 14 categorías de costo; desconocidos como null y nunca cero implícito;
competencia all-or-none; prohibición de convertir resultados históricos en P&L
de NQC; publicación idempotente; no-clobber; filtros; symlinks; archivos extra;
campos inesperados; bloqueadores duplicados y coherencia decisión/economía.

También se ejecutó `python3 -m py_compile` sobre módulo y pruebas.

## Identidad de bytes comprobada

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| opportunity_vault.py | `1818fbf5d9a1e4bf295ef1ee2174608a932b0db70645526164039cd8929bdafe` | `6b797e035b330f8abcca4b1bf7abccce8fe112fc` |
| test_opportunity_vault.py | `e86a9827ad5d0a783849fc773acfcf72f13cff47c7e607068da24c22ff1c4d47` | `dba28daec04db8bd05abe7bab84a2824f3cd3ef0` |
| OPPORTUNITY_DOSSIER_CONTRACT.md | `7e14759dffd419ccc6bc426177edfc83cff497e58bcc84e7d3078bd0bb7e5f0a` | `30ca52935189da4a7d076420cc9ba4f7c5ab053a` |

Los tres Git blobs coinciden con `git hash-object` sobre los archivos que
pasaron las pruebas locales.

## Límites que permanecen abiertos

1. No hay expedientes poblados desde un ledger real por oportunidad; el
   agregado histórico anterior no contiene ese detalle.
2. La nueva capa todavía no está integrada físicamente con
   `nqc-census-store`; por tanto no hereda automáticamente sus garantías.
3. No hay prueba de replicación, reorg reconciliation ni recuperación conjunta
   dossier/store.
4. No se ha ejecutado la regresión completa Python/Rust del repositorio.
5. Census sigue abierto; componente 29 sigue **foundational_partial** y
   componentes certificados siguen en **0/36**.

## Medición

Controles H4: contrato/esquema, almacenamiento/query, pruebas adversariales y
publicación/read-back. Los cuatro quedan completos al sincronizar
`isolation.py`, `census_map.json`, `census_assessment.json` y README.

**H4 puede cerrarse al 100% como hito de implementación offline; esto NO significa
que Evidence Vault esté 100% certificado.**
