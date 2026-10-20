# Pruebas e identidad - sin certificación económica

Padre de la nueva rama: b5f263c3b620c7ad8f81f3a205288f52b0baf605, árbol 960a7a260a131693cfac49b234a58e772a88a22f; padre del padre df29f5539910caae90604c0f6c39292998074f0c. Main auditada: 16e352225ba8a6a931834c4edf3d86d9a2924b7d. Ramas/commits observados completos en evidence/github_initial.json y evidence/github_logs_metadata.json.

| Verificación | Resultado real |
|---|---|
| Seis fuentes frente al MANIFEST y bundle Git | PASS, bytes y SHA256 idénticos. |
| Bundle comprimido de evidencia del cuarto run | PASS, 33 fragmentos, 49169 bytes, SHA256 y ocho archivos recuperados. |
| Hash RLP de dos cabeceras | PASS. |
| Hash de 41 transacciones y raíz de trie | PASS. No prueba consenso por sí mismo. |
| Recuperación de firmantes tx0/tx1 | PASS, firmas históricas. |
| Guard original / wrapper de archivo | 12 + 6 tests offline aprobados localmente; pruebas de transporte. |
| Adaptador y prohibición de reintento tras 403 | 7 tests offline aprobados. |
| Compilación Solidity original | PASS, solc 0.8.26, 2 archivos. |
| Verificador original en worktree main | PASS, 531 fuentes y 106 workflows deshabilitados; no recertificación original. |
| Tests de aislamiento en main | 9/9 PASS. |
| Verificador global en rama de investigación | FAIL: forbidden active/client tree. Workflow previo conservado. |
| Tests de aislamiento en rama de investigación | 7 PASS, 2 ERROR: directorio workflow ya existente y rechazo del árbol activo. No se alteró el test. |
| Original EVM | FAIL de infraestructura/evidencia en setUp; cero pruebas económicas aprobadas. |
| Reproducción offline del bloqueo | Mismo primer slot faltante; original sigue FAIL; cero red. |
| Variante, seguridad, gas, sensibilidad/neto | NO EJECUTADOS porque A no pasó. |
| Rust / certificación completa PFT-Census | NO EJECUTADOS, fuente original intacta; no afirmamos certificación. |

Todos los cambios de este turno son adiciones bajo migration/experiments/nqc-068-commercial-proof-20261020/. No se modifican fuentes previas, main, otros repositorios, workflows, clientes, secretos ni permisos. No se activan pipelines: el workflow existente tiene branch/path exactos distintos de esta rama y no se toca. Auditoría final de rutas y commit en GIT_PUBLICATION.json / evidence/git_scope.json. Los archivos de evidencia no autorizan ejecutar viejos productores.

Los logs de ejecución contienen hashes de herramientas; TOOLS_AND_BUILD.json conserva hashes locales de binarios y compilados. SHA256SUMS cubre entregables y evidencia salvo sí mismo; PUBLICATION se añade después como registro del commit inicial, sin prometer un hash circular del propio commit.
