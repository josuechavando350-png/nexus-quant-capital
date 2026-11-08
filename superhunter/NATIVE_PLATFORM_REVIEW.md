# Revisión conjunta obligatoria: QA, EVM y conciliación

Esta ruta cierra la separación entre `review-platform` y `run-evm-accounting`.
El comando anterior conserva su contrato local-numérico. **No se le atribuye
retrospectivamente ejecución EVM.** El perfil nuevo exige ambas rutas y una
reproducción nativa antes de emitir un informe favorable.

## Recorrido

`review-native-platform --solc BINARIO --evm BINARIO --out CARPETA_NUEVA`

1. Comprueba los bytes fijados de solc y evm y la identidad de Z3 antes de crear
   una carpeta o iniciar la suite. No instala ni descarga herramientas.
2. Ejecuta `platform.run_platform`: QA completo, laboratorio nativo de NQC/DIABLO,
   fuzzing numérico, contabilidad, benchmark de permisos y secuencias.
3. Ejecuta el perfil EVM existente sobre sus **tres controles propios fijos**.
   Compila, resuelve, ejecuta constructores y llamadas, y concilia unidades.
4. Llama al replay nativo existente: vuelve a compilar y ejecutar los controles.
   No basta un recibo o una bandera que afirme `evm_executed=true`.
5. Vincula la identidad de las fuentes de QA con cada mapa de fuentes del motor
   nativo, comprueba inventarios cerrados y verifica que nada cambió durante el
   recorrido. Solo entonces escribe `review/COMPLETE.json`.

`verify-native-platform --solc BINARIO --evm BINARIO --bundle CARPETA --expected-source SHA256`

Este comando exige la huella de código esperada, conservada **fuera del paquete**.
No la obtiene de la afirmación del propio reporte. Revalida la evidencia de QA y
sus inventarios actuales, pero NO vuelve a ejecutar todas las pruebas unitarias.
Sí vuelve a compilar, resolver y ejecutar los tres controles EVM. Compara el
reporte Markdown, HTML, JSON y la bitácora con lo reconstruido. No hay fallback
que apruebe una revisión nativa sin binarios.

## Artefactos enlazados

- `local/`: paquete de revisión anterior completo, con su alcance local-numérico.
- `native/`: fuentes/capturas y salidas de compilador, solver y EVM del perfil
  existente, junto a la conciliación de cambios persistentes y sus bitácoras.
- `review/`: informe conjunto, resultados y bitácora original de DIABLO, con hashes
  de cada artefacto de las dos etapas. El manifiesto de finalización se escribe
  al final. Una interrupción puede dejar etapas parciales, nunca un cierre válido.

Los originales no se reescriben. La revisión posterior exige exactamente los
archivos registrados: directorios adicionales, archivos privados no declarados,
symlinks, archivos ausentes y cambios concurrentes provocan rechazo. Un rechazo
no se corrige borrando la etapa faltante del informe.

Los nombres y números de los controles no proceden de flags arbitrarios:
se mantienen los tres constructores y las 18 llamadas del perfil fijado, cinco
transferencias internas aplicadas y trece llamadas fallidas sin transferencia.
Los outcomes de reversión/agotar gas son esperados en controles negativos; no
se cuentan como vulnerabilidades de terceros.

## Uso y estados

Los comandos también están disponibles por `python -m superhunter`.
El éxito devuelve `FIXED_NATIVE_PLATFORM_REVIEW_PASS`; el rechazo o una etapa
incompleta devuelve `NATIVE_PLATFORM_REVIEW_BLOCKED`, con salida 2. No imprime
fuentes, rutas privadas ni texto de excepciones. Las salidas conservan permisos
privados 0700/0600. No se sobrescriben revisiones previas.

No se aceptan RPC, contratos externos, scripts, calldata, payloads o fuentes
arbitrarias. Los límites de cada worker y motor original no se amplían. El tiempo
total incluye ahora QA y dos ejecuciones nativas. El verificador añade una
tercera cuando se invoca después de la generación.

## Qué prueba y qué no

El informe demuestra coherencia y repetibilidad local del código y los controles
que se ejecutaron. No demuestra eficacia de descubrimiento, ausencia de errores,
seguridad de un contrato ajeno, autorización de un programa ni aptitud de
producción. Los mismos solc, Z3 y Geth se usan en la repetición; no son motores
independientes. Los hashes y AuditLog por sí solos no autentican productores.
La firma de custodia existente puede aplicarse aparte a evidencias compatibles,
pero este módulo NO firma ni genera claves.

Se conservan los tres planes 27/50/25 sin elevar estados amplios a completos.
El resumen de QA tiene `tests_reexecuted_by_verifier=false`. Las cantidades son
unidades de contratos propios; dinero, pérdidas y costos monetarios permanecen
sin estimar. `platform_complete` y `vulnerability_confirmed` siempre son falsos.

## Pruebas de esta unidad

Los tests unitarios sustituyen explícitamente la ejecución QA y `evm.execute`
con fixtures para aislar la orquestación; no se cuentan como aceptación nativa.
La aceptación separada ejecuta los comandos públicos con los binarios recibidos,
sin esos sustitutos. Los logs, las huellas y los checks no ejecutados se guardan
en el paquete de validación de la entrega, no se deducen del número de tests.
