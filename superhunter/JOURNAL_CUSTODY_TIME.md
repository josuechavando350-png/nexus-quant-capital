# Custodia y contexto temporal de registros locales

Esta entrega corrige un fallo de aritmética temporal y conecta el importador de
journal con la custodia existente. El consumidor es de lectura local: no adquiere
logs, firma, genera claves, ejecuta procesos, consulta hosts ni escanea objetivos.

## Corrección de límites de fecha

El analizador restaba/sumaba `timedelta` a fechas válidas. Cerca de los años 1 y
9999, un margen de incertidumbre positivo desbordaba `datetime`: se reprodujo
`OverflowError` en tres controles, incluido el máximo timestamp aceptado por
el parser journal. Ninguno debía perder su estado `INCONCLUSIVE_ORDER`.

Ahora compara intervalos en microsegundos enteros exactos desde un origen fijo.
No usa flotantes, no recorta los intervalos ni reduce la incertidumbre. Los
intervalos pueden extenderse matemáticamente más allá del rango de `datetime`,
sin inventar un timestamp representable. La salida conserva las marcas de
tiempo originales normalizadas. Una conversión de zona horaria que quedaría
fuera del rango UTC se rechaza con `TIMESTAMP_UTC_RANGE`, sin traceback de datos.

Los tres controles ahora devuelven `INCONCLUSIVE_ORDER`. Las pruebas nuevas
incluyen extremos, rango completo, inversión, intervalos que se tocan, separación
de un microsegundo, límite máximo de journal y conversión UTC fuera de rango.

## Nuevo consumidor

`journal_custody.py` exige un expediente journal existente, su sello de custodia,
una política pública de confianza externa y anclas de código/journal/sello.
El operador debe fijar la identidad de fuente y la incertidumbre esperadas;
ambas tienen que coincidir exactamente con la metadata firmada. Esto impide
cambiar silenciosamente el contexto, pero no autentica que el reloj sea correcto.

El consumidor verifica la firma y su ámbito, vigencia y revocación. Después
repite la normalización, offsets y hashes de líneas y análisis temporal mediante
el verificador real del journal. Finalmente comprueba nuevamente bytes,
inventarios, política y fuentes. La firma no sustituye esa revisión semántica.

| Resultado | Salida CLI |
| --- | ---: |
| Custodia válida y orden declarado coherente | 0 |
| Custodia válida y orden incierto o contradictorio | 1 |
| Evidencia, firma, ancla o contexto inválidos | 2 |

Un reporte incierto se conserva para revisión; no se convierte en PASS. Al
verificarlo se exige su ancla y se regenera desde los originales y la confianza
actual. Un sello vencido o revocado no retiene una aprobación anterior.

## Comandos

`review-journal-custody` exige `--journal-bundle`, `--seal`, `--trust`,
`--source-digest`, `--journal-anchor`, `--seal-anchor`, `--case-id`,
`--producer-id`, `--expected-source-id`, `--expected-clock-uncertainty-ms`
y `--out`. `verify-journal-custody` usa los mismos insumos, cambia `--out` por
`--bundle` y exige `--report-anchor`.

Funcionan con `python3 -m superhunter` o `python3 -m superhunter.journal_custody`.
Las salidas son directorios nuevos fuera del checkout y separados de los
insumos; la confianza queda fuera de expedientes y reporte. La CLI no imprime
rutas, mensajes originales ni identidades del caso. El reporte no copia MESSAGE.

## Validación focal y aceptación de CLI

- 70 pruebas focales PASS, incluidas 32 nuevas: diez de límites temporales y
  22 de custodia/contexto. Ninguna prueba anterior se reescribió.
- Cuatro controles **sintéticos**, escritos explícitamente en formato journal:
  coherencia, solapamiento, contradicción y límite máximo. No provienen de
  journald ni de adquisición de logs del host.
- Parsers, firma Ed25519 y verificadores reales; creación y verificación por
  CLI en procesos separados. Dieciséis invocaciones con resultados esperados:
  cuatro importaciones, ocho creaciones/verificaciones, tres controles
  rechazados y una nueva verificación del original incierto.
- Se rechaza una reducción del margen de incertidumbre esperado, una clave
  revocada y un reporte incierto que se cambió a coherente recalculando hashes.
- La clave privada efímera de laboratorio nunca se escribió a disco. La política
  pública fue definida por la misma sesión; no prueba custodio independiente.

```sh
python3 -B -m unittest superhunter.tests.test_timeline_boundaries superhunter.tests.test_journal_custody superhunter.tests.test_journal_ingest superhunter.tests.test_forensic_timeline superhunter.tests.test_quality_entrypoint -v
```

La identidad de fuente, el tiempo y sus márgenes siguen siendo declaraciones.
La firma prueba custodia de bytes bajo la política aportada; no autenticación de
la ejecución, causalidad o incidente. No se cierra M1 ni la operación continua.
Los sellos de aceptación expiran 24 horas después de emitirse; no hay bypass del
reloj para mantener una aceptación actual después de su vencimiento.

## Aceptación completa

**2,906 QA PASS**, cero fallos, errores o skips. Se conservan las 2,874
identidades anteriores en sus ocho grupos y se añaden 32. SDK real en
producción del QA; verificación separada de QA, telemetría y preparación
en un entorno sin SDK. Los dieciséis comandos de aceptación sobre controles
sintéticos son distintos de esta corrida completa de QA.

Digest: `4656f2218dcc1ad7144686c201c4feffc34dab0d90f90e60788a3185de951f12`.
Ancla QA: `303af7a7080b3406592a63fcfe2208c638d6f276c8952b93fef18138f69410d9`.
Máximo por worker: 86.534811 s; presupuestos intactos.
Se conservaron 230 archivos Python previos y todos los tests anteriores.
Límite del repositorio PASS, 642 archivos históricos protegidos intactos.

No se reejecutaron perfiles nativos Slither/Geth/EELS para este digest ni se
recertificó Rust/PFT/Census. Las evidencias anteriores mantienen sus identidades.
Archivo: `SUPERHUNTER_JOURNAL_CUSTODIA_TIEMPOS_20261108.zip`.
