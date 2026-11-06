# Continuidad del trabajo

- Proyecto: defensa de NQC. Orden vigente actualizada: construir y publicar código en la rama separada `NQC-defensive`. Sin despliegue ni activación productiva. La autorización anterior de no publicar fue sustituida por el usuario.
- Versión actual: 0.3.0. Base NQC fijada: `16e352225ba8a6a931834c4edf3d86d9a2924b7d`.
- Ubicación nueva en NQC: `migration/defense/` más `migration/DEFENSE-INTEGRATION.md`. No modificar Census ni recovered-source para hacer pasar pruebas.
- Fuente de continuidad: la rama Git `NQC-defensive`, paquete `migration/defense/`. En este workspace, trabajar desde `nqc-review`; `nqc-unpublished` y el ZIP anterior son entregas históricas, no copias actuales que deban sincronizarse.
- Completado aquí: 8 subconjuntos del catálogo original; X101, X102, X103 y subconjuntos de X105/X106. Los 100 nombres del catálogo no son 100 implementaciones.
- Evidencia actual: 123 pruebas del paquete, 9 de aislamiento, aceptación local, comparación histórica del reloj 0.1/0.2, inspección de un artefacto real de Census y consumo del manifiesto real de NQC con verificación de recibo/exportación.
- Conexión nueva: `ArtifactReader` y CLI `read-json` reciben bytes aprobados y auditados a través de `Engine.admit_bytes`, después del commit SQLite. No reabren rutas. Probados cambio posterior del archivo, concurrencia del token y rollback real por fallo de auditoría/commit.
- Revisión completa de NQC recuperada: 645 archivos comprobados por tamaño y hash Git. Bloqueo de la descarga inicial resuelto por recuperación de blobs; no repetir el trabajo desde cero.
- Sin activación: el consumidor productivo de NQC aún no está obligado a pasar por este motor. No hay sensor continuo, eBPF, hardware validado, despliegue o certificación económica/canónica nueva.
- Trabajo siguiente: retención acotada y exportaciones paginadas con continuidad verificable; después anclaje independiente y políticas candidatas sobre recibos autorizados. La integración operativa en Census requiere definir su consumidor, procedencia de evidencias y conducta ante fallos sin alterar las fuentes inmutables.

Ejecutar las pruebas desde `migration/defense` con `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Desde la raíz NQC, ejecutar `python3 -B migration/defense/tools/check_nqc_base.py .` y las pruebas de aislamiento. Si cambió el commit por el trabajo simultáneo, revisar esa diferencia antes de cambiar el anclaje.
