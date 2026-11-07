# Evidencia de QA bloqueado

Los criterios de `LOCAL_QA_PASS` y los ocho workers conservan sus límites y
verificadores. Si el proceso, un recibo o el agregado fallan, `check --out RUTA`
guarda los artefactos disponibles en `RUTA.failure` antes de eliminar el directorio
temporal. Tanto RUTA como RUTA.failure deben ser nuevos; no se sobrescribe evidencia.

Un fallo de aserción con recibos completos sigue produciendo el paquete ordinario
`LOCAL_QA_BLOCKED`. El paquete `.failure` se reserva para excepciones que impiden
validar o producir el agregado. Una salida de worker enlazada no se sigue; la
copia de hashes se congela antes de la ejecución.

Se conservan exactamente los recibos, logs ya redactados y marcadores disponibles
de cada worker. El informe incluye el digest de fuentes, etapa, tipo fijo de
error, salida de procesos, contadores declarados y pruebas sin registro observable.
No publica mensajes de excepciones, argumentos, stdout o stderr arbitrarios.

Una excepción de `setUpClass` puede impedir que comiencen varias pruebas. Esas
pruebas quedan identificadas como no observadas; no se inventan resultados ni se
aumenta `tests_run`. Un recibo ausente o inválido deja los conteos desconocidos.
Una discrepancia de fuente o de manifiesto impide usar ese recibo para establecer
el inventario global. Los contadores siguen siendo afirmaciones del recibo,
no una autenticación independiente del productor.

```sh
python -m superhunter verify-failed-check --bundle RUTA.failure --source-digest DIGEST
```

Este verificador comprueba hashes y recalcula el informe sin ejecutar pruebas.
Devuelve `QA_FAILURE_EVIDENCE_VERIFIED`, `qa_passed: false` y código **1** cuando
la evidencia del fallo es coherente. Código **2** indica evidencia inválida.
Nunca devuelve PASS. `verify-check` sigue rechazando estos paquetes.

Un timeout puede ocurrir antes del primer recibo: en ese caso el inventario y el
número de pruebas no observadas son desconocidos. No observar una prueba en un
recibo incompleto no prueba por sí solo que nunca se ejecutó. Los fallos al escribir
evidencia, permisos del directorio o disco lleno siguen siendo errores; no se
afirma que un archivo se guardó cuando la escritura falló.
