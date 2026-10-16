# NQC V2 — preservación de código y evidencia desde nexus-engine

Corte documental: 2026-10-15. Repositorio receptor: `josuechavando350-png/nexus-quant-capital`, rama aislada `nqc/import-engine-v2-provenance-20261015`. Base inmutable: `b737723e0e429a40d993cf2433bc4d92c6316829` (PR #3). Fuente principal: `josuechavando350-png/nexus-engine@21e7df356600d411a5bd5371fa2a0d7292944703`, Git tree `6842333ac78db36ddd11ee7dd2e926fd05e771d9`.

## Alcance preservado y certificado solamente por SHA

- 207 copias bajo `source/` de módulos NQC de Census/RMC, T36, Morpho Blue, ERC-4337 y Rust; 194 corresponden a versiones nuevas o distintas de `ci/nqc-census` contra la base anterior, además de T36/Rust.
- 69 workflows adicionales del último árbol fuente, archivados únicamente como `.disabled`. La base conserva 106 workflows históricos previos inertes.
- 76 archivos recuperados de ramas de PR que no se encontraban en el último árbol fuente, incluido el PR #669 y liquidaciones/oráculos/competencia (Aave, Morpho, Compound III). Los dos archivos `.gz` del PR #669 se transfirieron como bytes originales usando base64, comprobando identidad Git blob.
- 25 versiones procedentes de ramas independientes recientes (Aave seizure, Curve, oracle, wsNET), todas en rutas aisladas. Los workflows de estas ramas también tienen sufijo `.disabled`.
- `MANIFEST.json` enumera cada archivo preservado, su ruta y Git blob SHA, sin reemplazar ni falsificar SHA de runs/commits originales. El manifiesto excluye sus propios metadatos y el README.
- Cero workflows en `.github/workflows/` dentro del repositorio receptor; ningún archivo original de `ci/`, `nqc-census/`, `AGENTS.md` o `README.md` fue modificado por este traslado.

### Frontera de cierre
Esta es una **preservación de código y evidencia con integridad Git dentro del alcance declarado**; NO es un merge funcional, recertificación del productor independiente, despliegue ni garantía de inventario completo de todas las 318 ramas históricas/PR de Nexus Engine. Los experimentos anteriores al snapshot original y los archivos ya existentes siguen trazados por sus fuentes originales. Si una auditoría descubre otras ramas únicas, deben incorporarse en otro lote sin declarar falsamente un 100% universal.

### Prohibiciones
No ejecutar workflows importados, tocar `main`, mezclar clientes/Cano/Vercel, desplegar, firmar, emitir UserOperations, gastar gas, usar fondos propios, contratar patrocinio o publicar secretos. La etiqueta `SUCCESS` en un test EVM local **no** representa ganancia realizada ni patrocinio real.

### Estado económico
NQC P&L realizado y conciliado: **USD 0**, según dossier y repositorios consultados; este traslado no altera la cifra. Hay márgenes brutos históricos de terceros, pero ningún resultado prospectivo propio competitivo y financiado. Gates pendientes: compatibilidad exacta de EntryPoint deployed en Robinhood 4663; caducidad L2 firmada; coste total UserOperation+reverts+postOp+L2; patrocinio auténtico sin recurso; rutas mismas alturas y Shadow prospectivo.

### Reproducción futura
Comparar todos los paths y SHA de `MANIFEST.json` contra el árbol de esta rama, verificar que los directorios originales sean iguales al commit base y que no exista ningún workflow activo. No confiar en el README como sustituto de los bytes; `MANIFEST.json` es un índice de integridad, no una certificación de mercado.
