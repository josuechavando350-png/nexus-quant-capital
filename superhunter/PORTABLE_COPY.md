# Exportación privada verificable de copias preservadas

Sucesor de PR #98, commit `55358b980eb75fa30d6692c42f7056b57879af6a`.

`export-preserved-copy` empaqueta una copia de salvamento en un archivo ZIP
reproducible. `verify-preserved-archive` comprueba ese archivo sin extraerlo,
buscar sus directorios de origen ni ejecutar contenido. El archivo sigue siendo
verificable aunque esos directorios ya no estén disponibles.

## Contenido privado y uso

El archivo **incluye bytes privados originales, sin cifrar ni filtrar**. La
exportación requiere `--include-private-bytes` como elección explícita; no es
el resumen filtrado de `sharing.py`. Se escribe con modo 0600, en una ruta nueva
fuera del checkout y fuera de la copia de origen. No sobrescribe, publica ni
transmite archivos. La CLI no borra las carpetas originales ni la copia.

```bash
python3 -B -m superhunter export-preserved-copy \
  --bundle /ruta/copia-preservada --out /ruta/nueva/copia.zip \
  --include-private-bytes \
  --source-digest DIGEST_DEL_CODIGO \
  --input-anchor ANCLA_EXTERNA_DEL_INVENTARIO \
  --recovery-anchor ANCLA_EXTERNA_DEL_SALVAMENTO

python3 -B -m superhunter verify-preserved-archive \
  --archive /ruta/nueva/copia.zip \
  --source-digest DIGEST_DEL_CODIGO \
  --input-anchor ANCLA_EXTERNA_DEL_INVENTARIO \
  --recovery-anchor ANCLA_EXTERNA_DEL_SALVAMENTO \
  --archive-anchor ANCLA_EXTERNA_DEL_ARCHIVO
```

La carpeta de salida debe existir. Conservar las anclas fuera del archivo: la
exportación devuelve su SHA256; las otras dos vienen de la inspección/salvamento.
Se exige el checkout exacto del digest del verificador
(`SHA256(canonical(source_snapshot()))`).
Cambiar coherentemente archivo y todas sus anclas puede describir otros bytes;
ningún hash autentica al productor, la ejecución o el origen independiente.

## Identidad del verificador y de la copia histórica

`--source-digest` fija siempre el código del verificador actual. Para una copia
del mismo perfil creada anteriormente, añadir `--preserved-source-digest` tanto
al exportar como al verificar. Ese segundo valor debe conservarse externamente
junto con las anclas del expediente anterior; no se infiere del reporte.
Si se omite, se exige que ambas identidades coincidan.

La salida presenta `source_digest` y `preserved_source_digest` por separado.
El reporte histórico y cada byte conservado permanecen intactos. El lector actual
recalcula contenido y clasificación del único perfil conocido; no ejecuta ni
autentica al productor histórico. Otros perfiles y reportes incompatibles siguen
rechazándose. El digest antiguo no puede sustituir el del código actual.
El verificador de carpetas anterior conserva su contrato, sin migración implícita.

También se corrigió el rechazo excesivo de archivos hermanos del checkout:
se protege la ruta del archivo, no se prohíbe que su carpeta padre contenga
al checkout. Escribir dentro del repositorio o mediante symlinks sigue rechazándose.

## Perfil cerrado y límites

Se admite únicamente el ZIP_STORED canónico generado por este exportador.
No es un importador general de ZIP. El límite de entradas y del directorio
central se comprueba antes de que ZipFile construya su lista. Cada miembro tiene
nombre fijo, tipo regular, modo 0600, fecha fija y tamaño acotado. Se rechazan
compresión, ZIP64, comentarios, rutas, duplicados, symlinks, campos extra,
CRC incorrecto y bytes no canónicos. No se descomprime ni extrae contenido.

El salvamento conserva sus presupuestos: hasta 128 archivos de entrada,
2,000,000 bytes por archivo y 32 MiB totales. El archivo completo se limita a
35,685,504 bytes. Los límites operativos del proceso/sistema también se aplican.
Las fechas ZIP se fijan en 1980 para reproducibilidad; no prueban antigüedad,
fecha de captura o exportación y no autorizan borrar evidencia.

El lector de directorios y el de archivos comparten la derivación pura del
inventario/reporte. Cada contenedor valida su manifiesto y sus anclas, y revisa
otra vez bytes y fuentes antes de aceptar. Dos lecturas estables no autentican
un host ni descartan cambios transitorios restaurados entre lecturas.

| Código CLI | Significado limitado |
| --- | --- |
| 0 | Archivo válido de una captura estructuralmente completa |
| 1 | Archivo válido de una captura incompleta, inválida o pendiente |
| 2 | Rechazo de entrada, perfil, anclas, fuentes o E/S |

`captured_input_state` sigue describiendo bytes capturados, no el estado actual
del original. `source_bundle_current_state_checked` es true al exportar y false
al verificar el archivo por separado. No se acredita éxito semántico ni hallazgo.
Un fallo de fsync o una alteración detectada después de escribir puede dejar un
archivo para examen: no se elimina ni se informa que la exportación tuvo éxito.
Verificar sus bytes después no prueba que el exportador retornó correctamente
ni durabilidad frente a apagón. No existe purga o borrado automático.

## Validación

- 101 focales finales PASS, con los mismos bytes que la suite completa final.
- **3,057 QA PASS**, cero fallos/errores/skips; 3,017 anteriores conservadas
  en sus ocho grupos y 40 nuevas. SDK real y verificador separado sin SDK PASS.
- 48 comprobaciones CLI de la versión actual con cinco workers reales: control limpio y cuatro
  cortes SIGKILL instrumentados del propio proceso. Se preservan/exportan sus
  bytes y se retiran deliberadamente las diez carpetas temporales de origen y
  salvamento. Los archivos mantienen idéntico veredicto. No es pérdida natural.
- 31 controles CLI adicionales usan las cinco copias reales guardadas de PR98,
  cotejadas byte a byte con su ZIP anterior fijado por SHA256. Se preservan las
  identidades, anclas y bytes históricos. Solo se eliminan clones temporales;
  los expedientes anteriores permanecen intactos. Total final: 79 controles CLI.
- Los controles alterados e inyecciones de concurrencia/fsync se identifican
  como tales. Sin apagón, restauración, extracción o autenticación independiente.
- 245 Python anteriores idénticos. Cambian tres registros y la factorización
  del núcleo de verificación; ningún test anterior se modifica. Escritor,
  motor nativo y fixtures intactos; sin nuevas corridas nativas.

Digest `b1a08d189ce9879214f39e5c8b18f5c4bc157842279cb85c40b759f9e4bdf2fb`.
Evidencia: `SUPERHUNTER_EXPORTACION_PRIVADA_VERIFICABLE_20261108.zip`.
M1 parcial, 1/6 hitos cerrados. Los 642 históricos están intactos; el verificador
legado mantiene su rechazo preexistente. No se recertifica NQC.

La primera QA (3,050 pruebas) y los intentos que reprodujeron la incompatibilidad
se conservan en la evidencia, con sus identidades anteriores. No sustituyen los
resultados finales ni se presentan como ejecución del código histórico.
