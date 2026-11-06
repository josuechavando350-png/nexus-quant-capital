# SUPERHUNTER — Estado público verificable (6 de noviembre de 2026)

**Proyecto:** NQC × DIABLO = SUPERHUNTER. Estado: **LABORATORIO LOCAL DE INVESTIGACIÓN DEFENSIVA; NO CERTIFICADO PARA PRODUCCIÓN**. Código fuente público propuesto en esta rama; `main` no se modifica.

## Punto de restauración y evidencia

- Baseline recuperable: `SUPERHUNTER_holdout_etiquetas_2005.zip`, 210 archivos de paquete `superhunter/` (antes de añadir documentación de publicación).
- Última validación local **cerrada**: `LOCAL_QA_PASS`, **2,005 pruebas** con 0 fallos/errores/skips; 1,969 identidades anteriores conservadas + 36 nuevas.
- SHA-256 del inventario ejecutable/políticas probado por `quality.source_snapshot()`: `205b61fee612c263510c581216010c527d84e51f934d2c1ca9451fbd87ed6ed4`.
- Verificación aparte de `verify-check` realizada sobre el ZIP extraído, con el mismo digest.
- Dos intentos anteriores de esa versión no aprobaron (timeout y límite de recursos); se conservaron y se ajustó el reparto de tests sin eliminar controles.
- Controles con etiquetas reservadas: `prepare-holdout` / `freeze-holdout` / `score-holdout` / `verify-holdout`. Pruebas positivas y negativas en cuatro casos **conocidos**, no un benchmark ciego.
- Esta publicación agrega solo documentación Markdown y el código exacto del ZIP; no modifica los `.py` ni los catálogos `.json` probados. Los hashes completos de los archivos están en `MANIFEST_PUBLICO_SHA256.md`.
- Los tests del paquete no equivalen a detección de vulnerabilidades nuevas ni certifican un despliegue.

## Inventario de compromisos (no sumar las listas: se solapan)

| Catálogo | Estado limitado/ parcial | Pendiente | Rediseño defensivo | Completo certificado |
|---|---:|---:|---:|---:|
| 27 hitos originales | 12 acotados + 3 parciales | 12 | 0 | 0 |
| 50 capacidades | 9 | 24 | 17 | 0 |
| 25 iniciativas PDF | 5 | 20 | 0 | 0 |

El **40%** mencionado en conversaciones previas es estimación subjetiva de desarrollo, no KPI auditado ni derivado de estos catálogos. No se actualiza sin un modelo de progreso calibrado.

## Funciones efectivamente presentes en el paquete

- Puente de evidencia `Candidate`/`Reconstruction` entre DIABLO/NQC, sin promoción a exploit confirmado.
- Ingesta offline de diagnósticos Slither y perfiles de coherencia fuente/AST/almacenamiento. **No implica ejecución de Slither**.
- Analizador Python de importaciones e inventario de módulos (referencias sintácticas, no prueba de conectividad en runtime).
- Comprobación de políticas y alcance local para ocho etiquetas de plataformas, sin cuentas ni conectores operativos.
- Auditoría, privacidad, controles de integridad, validación de identidad de artefactos y custodia firmada acotada.
- Controles de permisos RBAC, modelo formal Z3 y conciliación contable de datos declarados.
- Compilación real con `solc 0.8.30`, comprobación formal con Z3 y ejecución EVM Geth verificada sobre **contratos propios conocidos**.
- Ensayos de reversiones, estados persistentes, guardas de pausa y autorización, trazas de opcodes, fuzzing de secuencias, mutación guiada y comparación frente a control sin feedback.
- Resultados de la comparación multisemilla con cuatro semillas: no se demostró superioridad de cobertura del guiado en el corpus probado.
- Protocolo offline de compromiso, congelación, revelación y verificación de etiquetas; **no certifica un corpus verdaderamente ciego**, pues los ejemplos de laboratorio son conocidos.

## Límites negativos explícitos

- Vulnerabilidades originales confirmadas de programas externos: **0**.
- Programas bug bounty autorizados efectivamente conectados y analizados en línea: **0**. La lista de ocho plataformas es inventario de nombres/políticas, no API viva.
- Operación autónoma continua 24/7 demostrada: **NO**.
- 20 programas simultáneos reales demostrados: **NO**. Se hicieron controles de registros sintéticos.
- Ausencia universal de falsos positivos, detección de todos los bugs, ventaja comercial frente a otros proveedores: **NO DEMOSTRADO**.
- Verificación remota independiente de producer, firma de hallazgos reales, auditoría de código histórico NQC completa y verificador de aislamiento global: **PENDIENTES**.
- No se incluyeron binarios de terceras partes, claves, tokens, datos de usuarios ni informes confidenciales de programas.

## Estado GitHub y seguridad de publicación

Esta rama de publicación incluye una **instantánea consolidada de código**, independiente de los PR fragmentarios anteriores (p. ej. #35, #37, #38, #40, #43). Esos PR requieren conciliación antes de cerrar o fusionar; no asumir que ya se combinaron.

NQC exige preservar `ci/`, `migration/`, `nqc-census/`, sus bytes originales y workflows heredados deshabilitados. Esta publicación agrega únicamente `superhunter/`. `main` queda intacto hasta completar revisión de aislamiento y las pruebas históricas de Python/Rust.

**Siguiente meta medible:** un benchmark externo realmente ciego con custodio de etiquetas separado, seguido de un caso autorizado cuyo hallazgo se reproduzca y sea confirmado de forma independiente. No usar el número de tests como sustituto.
