# Incorporación local de NQC Defense; activación operativa pendiente

Paquete nuevo: `migration/defense/`. No reemplaza archivos existentes. Base consultada: `16e352225ba8a6a931834c4edf3d86d9a2924b7d` de `josuechavando350-png/nexus-quant-capital`.

Esta ubicación mantiene el código nuevo separado de Census y del código recuperado inmutable, dentro de la zona admitida por el verificador actual. Es preparación local, no activación. Ninguna importación lateral, workflow o hook arranca el motor.

Antes de conectar consumidores productivos:

1. Materializar el checkout completo y comprobar su base. Si otro trabajo avanzó el commit, revisar los cambios y actualizar el anclaje solo después de esa revisión.
2. Incorporar solo los archivos nuevos de esta entrega, preservando todos los bytes originales.
3. Ejecutar `python3 -B migration/defense/tools/check_nqc_base.py .`, el verificador de aislamiento original y las pruebas pertinentes.
4. Seleccionar el consumidor específico de evidencias de NQC y definir cómo deberá actuar cuando una admisión falle. Esa conexión aún no existe y no se presume por compartir repositorio.
5. Medir observación local, errores y falsos positivos antes de cualquier activación que cambie operaciones.

En la versión 0.2.0 se completaron los pasos 1–3: 645 archivos recuperados y verificados por blob Git, adición local aislada, verificador original válido y 9 pruebas de aislamiento aprobadas. Las 100 pruebas propias también pasan. Se inspeccionó un archivo real de Census mediante el motor y se verificó su recibo y auditoría.

La versión 0.3.0 conecta un consumidor local nuevo: `ArtifactReader.read_json` y CLI `read-json` usan obligatoriamente `Engine.admit_bytes`. Los bytes se capturan durante la inspección y solo se entregan después de confirmar la decisión y su auditoría en SQLite. El lector no reabre la ruta. `python3 -B migration/defense/tools/check_nqc_consumer.py .` comprueba esta ruta con el manifiesto real de NQC, preservando sus bytes y verificando recibo, auditoría y aislamiento. Pasan 123 pruebas del paquete y 9 de aislamiento.

Los pasos 4–5 respecto al consumidor productivo de Census siguen pendientes. El lector nuevo es ejecutable localmente, pero no se introduce por importación lateral en el código original. No se afirma nueva certificación canónica ni funcionamiento 24/7. El usuario autorizó publicar código en la rama separada `NQC-defensive`; la activación productiva sigue pendiente. No se modificó ningún archivo de la base previamente rastreada de NQC.
