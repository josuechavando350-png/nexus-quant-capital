# Continuidad del trabajo

- Proyecto: defensa de NQC. Orden vigente actualizada: construir y publicar código en la rama separada `NQC-defensive`. Sin despliegue ni activación productiva. La autorización anterior de no publicar fue sustituida por el usuario.
- Versión actual: 0.2.1. Base NQC fijada: `16e352225ba8a6a931834c4edf3d86d9a2924b7d`.
- Ubicación nueva en NQC: `migration/defense/` más `migration/DEFENSE-INTEGRATION.md`. No modificar Census ni recovered-source para hacer pasar pruebas.
- En este workspace, la copia incorporada y comprobada está en `nqc-review/migration/defense`; `nqc-unpublished` se usa para preparar la exportación. Conservar ambas idénticas al entregar; continuar las modificaciones desde la copia de NQC.
- Completado aquí: 8 subconjuntos del catálogo original; X101, X102, X103 y subconjuntos de X105/X106. Los 100 nombres del catálogo no son 100 implementaciones.
- Evidencia actual: 104 pruebas del motor, 9 de aislamiento, aceptación local, comparación del reloj 0.1/0.2, prueba de un artefacto real de Census y verificador original de aislamiento.
- Revisión completa de NQC recuperada: 645 archivos comprobados por tamaño y hash Git. Bloqueo de la descarga inicial resuelto por recuperación de blobs; no repetir el trabajo desde cero.
- Sin activación: el consumidor productivo de NQC aún no está obligado a pasar por este motor. No hay sensor continuo, eBPF, hardware validado, despliegue o certificación económica/canónica nueva.
- Trabajo siguiente: seleccionar un consumidor concreto para una conexión explícita y comprobable; implementar anclajes externos y retención acotada; añadir evaluación de políticas candidatas usando recibos/corpus autorizado. Mantener diferenciado lo ejecutable de lo diseñado.

Ejecutar las pruebas desde `migration/defense` con `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Desde la raíz NQC, ejecutar `python3 -B migration/defense/tools/check_nqc_base.py .` y las pruebas de aislamiento. Si cambió el commit por el trabajo simultáneo, revisar esa diferencia antes de cambiar el anclaje.
