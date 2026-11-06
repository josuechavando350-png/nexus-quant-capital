# Procedencia y cómo reproducir lo comprobado

## Origen de la instantánea

El código bajo `superhunter/` se extrajo de `SUPERHUNTER_holdout_etiquetas_2005.zip`. El archivo completo de conversación contiene la evidencia privada y registros de QA (no se publica indiscriminadamente porque pueden incluir paths y expedientes locales). Los 210 archivos de código/proyecto se preservan byte a byte en esta publicación. Esta documentación no modifica el inventario de módulos probado.

## Validación local exacta

`LOCAL_QA_PASS`: 2,005 tests (1,969 anteriores + 36 nuevos), 0 fallos, errores u omisiones, sobre el digest de fuentes y políticas:

`205b61fee612c263510c581216010c527d84e51f934d2c1ca9451fbd87ed6ed4`

La misma huella se observó al ejecutar `verify-check` sobre los artefactos extraídos del ZIP final. Dos intentos previos de esta entrega terminaron incompletos y no forman parte de los 2,005 aprobados. No se ha ejecutado nuevamente la suite completa después de la transferencia remota; se comprobarán los hashes de blobs y árboles públicos contra los bytes locales.

## Reproducción

Desde un checkout de esta rama, en un entorno Python compatible con las dependencias fijadas:

```bash
python3 -m unittest discover -s superhunter/tests -v
python3 -m superhunter check --out /ruta/privada/qa-nueva
python3 -m superhunter verify-check --bundle /ruta/privada/qa-nueva
```

Para reproducir los controles EVM se necesitan binarios oficiales con SHA/firmas comprobados y entradas propias del laboratorio. No se incluyen ejecutables externos, llaves privadas, cuentas ni endpoints. Algunos comandos de aceptación pueden requerir dependencias que no están instaladas en un checkout nuevo; esa ausencia debe bloquear, no producir un PASS aparente.

Para ver todas las funcionalidades y sus restricciones consulte `README.md`, `HOLDOUT_PROTOCOL.md`, `PROGRAM_INTELLIGENCE.md`, `EVM_OPCODE_TRACES.md` y los módulos respectivos.

## Interpretación

La coincidencia SHA-256 demuestra igualdad de bytes, NO autenticidad de productores externos ni ausencia de vulnerabilidades. Los tests del laboratorio son controles conocidos. La política de NQC en `AGENTS.md` exige ejecutar el verificador global de aislamiento y pruebas afectadas antes de proponer fusión; quedan pendientes en esta rama y no se habilitan workflows automáticamente.
