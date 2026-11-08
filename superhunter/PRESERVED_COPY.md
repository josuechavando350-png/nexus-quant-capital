# Verificar una copia preservada sin la carpeta original

Sucesor de PR #97, commit `c654c53825c172028ad506b1ead92f5088c32e0c`.

`verify-preserved-copy` verifica un expediente producido por
[preserve-local-bundle](BUNDLE_RECOVERY.md) sin buscar, abrir ni restaurar el
original. Es útil cuando ese original ya no existe o no está disponible.
El verificador anterior `verify-preserved-bundle` sigue comprobando también
el original actual; no se altera su contrato ni se sustituye por esta revisión.

## Uso y alcance de las anclas

```bash
python3 -B -m superhunter verify-preserved-copy \
  --bundle /ruta/copia-preservada \
  --source-digest DIGEST_DEL_CODIGO \
  --input-anchor ANCLA_EXTERNA_DEL_INVENTARIO_ORIGINAL \
  --recovery-anchor ANCLA_EXTERNA_DEL_SALVAMENTO
```

Los valores deben conservarse fuera de la copia, desde la inspección y creación
originales. Se requiere el checkout exacto correspondiente al digest; no se
aceptan automáticamente archivos de otra versión. El digest es SHA256 de
`canonical(quality.source_snapshot())`.

Se comprueban manifiesto y anclas, mapeo exacto de nombres a archivos numerados,
tamaños y hashes. El inventario original se reconstruye solo en memoria; sus
nombres no se interpretan como rutas para acceder al sistema de archivos. Se
recalculan clasificación y reporte completos y se vuelven a revisar bytes y
fuentes al final. Se rechazan archivos extra, ausentes, duplicados, symlinks,
cambios durante la revisión y promociones del reporte. Los presupuestos del
salvamento se conservan: 128 archivos de entrada, 2 MB por archivo, 32 MiB total.

`PRESERVED_COPY_VERIFIED` significa que la copia coincide con las anclas dadas.
`captured_input_state` informa el estado de los bytes capturados, no el estado
actual de la carpeta original. `original_current_state_checked` y
`original_restored` son siempre false. El resultado no autentica al productor,
la ejecución, una pérdida natural de datos ni un hallazgo. Si se sustituyen
coherentemente copia y todas las anclas externas, pueden describir otros bytes;
los hashes no son autenticación.

| Código CLI | Resultado limitado |
| --- | --- |
| 0 | Copia verificada de una captura estructuralmente completa |
| 1 | Copia verificada de una captura incompleta, inválida o pendiente |
| 2 | Rechazo de copia, anclas, fuentes o entrada |

La consola omite nombres y contenido de los archivos conservados. No se ejecuta
contenido, no se crea un original nuevo y no se repara un marcador incompleto.

## Validación ejecutada

- 61 pruebas focales PASS; 25 nuevas y todas las anteriores intactas.
- 3,017 QA PASS, cero fallos/errores/skips; 2,992 anteriores retenidas en sus
  mismos ocho grupos. SDK real y verificación separada sin SDK PASS.
- 36 comprobaciones CLI con cinco workers reales: control limpio y cuatro
  cortes SIGKILL instrumentados del propio proceso. Se preservan los bytes y
  luego se eliminan deliberadamente las cinco carpetas recién creadas. Las
  copias mantienen idéntico veredicto antes/después; el verificador que exige
  el original rechaza su ausencia. No se presenta esto como pérdida natural.
- Los controles alterados se identifican por separado. Las pruebas de cambios
  concurrentes inyectan explícitamente la modificación. No se certifica apagón.
- 244 archivos Python anteriores idénticos; cambian solo tres registros y se
  añaden módulo/tests. El escritor, salvamento, motor nativo y fixtures previos
  no cambian. No se repiten corridas nativas en este incremento.

Digest `324a5e56ef87d801455b64aa3de8ab11ef2e41e0c6f5118bb09932758ebe40a4`.
La evidencia completa se conserva en
`SUPERHUNTER_COPIA_VERIFICABLE_SIN_ORIGINAL_20261108.zip`.
M1 sigue parcial, 1/6 hitos cerrados. Los 642 históricos están intactos; el
verificador legado conserva su rechazo preexistente. No se recertifica NQC.
