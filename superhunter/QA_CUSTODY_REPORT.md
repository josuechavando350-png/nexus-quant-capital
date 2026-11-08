# Reporte conjunto de QA y custodia

`qa_custody.py` conecta dos verificadores que antes se usaban por separado:
semántica de QA y firma de custodia. Además exige los ocho expedientes originales
de workers y reconstruye el log agregado. No ejecuta nuevos procesos, firma,
genera claves o acepta objetivos de investigación.

## Condiciones de aceptación

1. El digest de código indicado por el operador coincide con el paquete actual.
2. Los hashes de `COMPLETE.json` de QA y firma coinciden con las anclas externas.
3. La firma Ed25519 cubre exactamente el expediente QA y pertenece a una clave
   del archivo de confianza externo, autorizada para ese caso y productor,
   vigente y no revocada. La confianza nunca se toma del expediente firmado.
4. `quality.verify_bundle` recalcula un `LOCAL_QA_PASS` para ese código.
5. Los ocho recibos originales coinciden con los comprometidos por el agregado.
   Los logs originales reconstruyen `tests.log` byte por byte, en orden fijo.
6. Se comprueban nuevamente fuentes, inventarios, evidencia y archivo de
   confianza al terminar. Un cambio detectado rechaza el reporte.

El reporte tiene su propio manifiesto y una ancla requerida al verificarlo.
El verificador vuelve a ejecutar todas las comprobaciones de lectura y regenera
el reporte. Una revocación posterior invalida su aceptación actual, aunque el
reporte se haya creado antes. No hay una opción de reloj retrospectivo en CLI.

## Uso local

`review-qa-custody` requiere `--qa`, `--workers`, `--seal`, `--trust`,
`--source-digest`, `--qa-anchor`, `--seal-anchor`, `--case-id`, `--producer-id`
y `--out`. `verify-qa-custody` usa los mismos insumos y contexto, sustituyendo
`--out` por `--bundle` y añadiendo `--report-anchor`.

Ambos funcionan mediante `python3 -m superhunter` o
`python3 -m superhunter.qa_custody`. Se rechazan salidas dentro del checkout,
solapamientos, archivos extra y enlaces simbólicos en entradas. El directorio
workers debe contener exactamente `worker-0` a `worker-7`. Los expedientes QA y
firma deben ser directorios distintos; la política de confianza queda fuera de
ambos y de workers/reporte. Los originales no se modifican ni copian al reporte.

Se usan los límites existentes de lectura de archivos y un máximo agregado de
32 MB de entradas. La salida contiene hashes, identidades de caso/productor y
conteos, sin copiar los logs. Aun así es un expediente privado; la CLI imprime
solo estado, conteo y resultado de custodia, sin rutas ni excepciones privadas.

## Qué significa el resultado

`QA_RECEIPTS_AND_CUSTODY_VERIFIED` significa que las condiciones de los recibos
son coherentes y que una clave confiada atestigua esos bytes. **No autentica
que el proceso se ejecutó**, la identidad humana, un reloj o un productor
independiente. Un firmante con control del productor puede fabricar recibos
coherentes. La firma no convierte recibos sintéticos en ejecución real.

El tiempo de revisión actual no se congela dentro del reporte: se comprueba
vigencia en cada lectura. Cuando vence el sello, la CLI debe rechazarlo; no se
ha debilitado ese control para mantener indefinidamente un PASS de laboratorio.
Los resultados archivados describen la revisión realizada en su momento.

Este módulo es una conexión útil de custodia y QA. No cierra M1: faltan la
captura forense autenticada, las hipótesis y la aceptación del circuito completo.
No se declara una vulnerabilidad, causalidad ni operación 24/7.

## Pruebas focales

72 pruebas PASS, incluidas 24 nuevas. Los tests de integración usan criptografía
y verificadores reales sobre recibos **sintéticos**, con claves efímeras que no
se escriben a disco. Cubren anclas incorrectas, firma adulterada, caso/productor
incorrectos, revocación/caducidad, worker faltante/extra/symlink, cambios con
hashes recalculados, QA bloqueado aunque firmado, cambios durante la revisión,
reporte con afirmaciones elevadas, rutas privadas y CLI en procesos separados.

```sh
python3 -B -m unittest superhunter.tests.test_qa_custody superhunter.tests.test_custody superhunter.tests.test_quality_entrypoint -v
```

## Aceptación sobre QA real

**2,874 QA PASS**, cero fallos, errores o skips, con SDK real. Las 2,850
identidades anteriores permanecen en sus ocho grupos y se añaden 24. QA,
telemetría y preparación se verificaron desde otro proceso sin SDK.

Una clave efímera de laboratorio firmó el expediente QA real; nunca se escribió
la clave privada. El consumidor creó y verificó el reporte por CLI en procesos
separados. Rechazó cuatro controles: confianza revocada, log de worker
modificado con hashes nuevos, QA modificado sin actualizar firma y reporte
que atribuía autenticación de ejecución. El original siguió siendo válido.
Son siete comprobaciones con los resultados esperados, no siete corridas QA.

Digest: `23497a237e0b3a7be678baef6301196032823049c8560f56576d081e2402b58c`.
QA: `3b149bc0f819fffe51c0ea3666fbce3aa4728c012821f6193575ddc6748b34f8`.
Sello: `01fa64dda5f73529a564dbcec247db93de3e5de664f409c744fae71204a24e3f`.
Reporte: `32c4d45755e13edb4eee3da5a9b0c300aeb46e6e679a7da6d0654e22bb70ef1a`.
Máximo por worker: 84.553009 s; límites intactos.

La política pública fue definida por la misma sesión y no prueba un custodio
independiente. El sello expira 24 horas después de emitirse; su tiempo exacto
está en el expediente. La expiración posterior debe impedir una nueva
aceptación actual sin reemplazar el sello conforme a una política vigente.

Límite de repositorio PASS: 642 archivos históricos intactos y 229 archivos
Python anteriores sin cambios. No se reejecutaron los perfiles nativos
Slither/Geth/EELS ni se recertificó Rust/PFT/Census para este digest.
Evidencia: `SUPERHUNTER_QA_CUSTODIA_INTEGRADA_20261108.zip`.
