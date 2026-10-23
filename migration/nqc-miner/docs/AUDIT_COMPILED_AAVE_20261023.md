# Auditoría: equivalencia compilada del Aave histórico

Fecha de evidencias: 23 de octubre de 2026 UTC. Avance ponderado: **43/100**,
sin puntos nuevos ni salida de fase.

## Resultado verificable

El pool observado antes de los tres eventos Ethereum y sus cinco bibliotecas
enlazadas se reproducen mediante compilación local. Se comparan los bytes
completos de cada contrato en los bloques 26248075, 26248113 y 26248378 contra
las respuestas de dos proveedores: **36 comparaciones exactas**. La captura
retiene 90 solicitudes/respuestas, finalización y revalidaciones de los bloques
y eventos; las observaciones se vinculan por hash a la entrega anterior.

| Contrato | Bytes históricos | Perfil de compilación |
| --- | ---: | --- |
| PoolInstance | 21.146 | Cancun, fuentes del pool |
| PoolLogic | 7.311 | Cancun, fuentes del pool |
| BorrowLogic | 9.587 | Cancun, fuentes del pool |
| SupplyLogic | 10.302 | Cancun, fuentes del pool |
| FlashLoanLogic | 8.227 | Shanghai, fuentes propias |
| LiquidationLogic | 12.101 | Cancun, fuentes del pool |

Ambos perfiles usan solc 0.8.27, optimizador de 200 ejecuciones, `viaIR=false`
y `bytecodeHash=none`. El compilador se fija por SHA-256 contra el índice
oficial. La recompilación deshabilita la lectura de imports externos y no usa
red. El pool recompilado declara revisión 11. Se resuelven sus dos inmutables,
cinco enlaces y el enlace transitivo de FlashLoanLogic a BorrowLogic.

## Hallazgo y corrección

La compilación conjunta del pool generaba un FlashLoanLogic de 8.206 bytes,
incompatible con el observado. La auditoría falló y se conservan la entrada,
salida y diagnóstico en `preflight-001/`. La consulta de esa biblioteca a
Sourcify para Ethereum devolvió 404. La página verificada de Ethereum en
Etherscan proporcionó sus 28 fuentes y parámetros propios; el parser trata
el contenido como datos, sin ejecutar scripts. Su compilación Shanghai reproduce
los 8.227 bytes. La prueba de regresión exige rechazar el artefacto conjunto
anterior y comparar el correcto. No se ocultan ni normalizan bytes distintos.

Las fuentes del pool permanecen intactas; no se sustituye su perfil Cancun.
Las cinco bibliotecas quedan vinculadas a sus direcciones y al código observado
en Ethereum. No se importan observaciones de otras cadenas a esta muestra.

## Comprobaciones

El conjunto específico incluye 14 pruebas: correspondencia completa, 36
mutaciones por contrato/bloque/proveedor, cobertura de proveedores y bloques,
metadatos alterados, compilador incorrecto, fuentes no literales, enlaces
desconocidos/solapados/fuera de rango, inmutables, prefijo de biblioteca, errores
de compilación, cadena equivocada, código vacío, desacuerdo y reorg. También
reproduce el fallo real de FlashLoanLogic y valida la extracción del explorador,
el índice del compilador y las tres funciones de liquidación conservadas.

Se vuelve a ejecutar toda la suite Python de investigación con el binario Rust
previamente auditado. El primer lanzamiento omitió `NQC_MINER_TEST_BINARY` y
produjo 11 errores de configuración; su salida completa se conserva en
`python-preflight-missing-env.txt`. La ejecución corregida está en
`python-research-tests.txt`: **256 pruebas aprobadas, cero fallos y cero omitidas**.
No se repiten Rust/Clippy porque esta continuación no modifica código Rust ni
dependencias. La referencia anterior conserva 167 pruebas Rust aprobadas.

El verificador de aislamiento conserva 531 archivos de origen, 106 workflows
deshabilitados y cero activos. Todos los cambios de la entrega están en
`migration/nqc-miner/`; se mantiene intacto Observer y la evidencia nativa
de Termux. El manifiesto final `verification.json` fija los hashes de entrega.

## Límites

La ausencia de hash de fuentes en los metadatos impide afirmar identidad única
del texto original; se demuestra equivalencia de runtime de las fuentes
conservadas. El número de revisión no prueba una etiqueta de lanzamiento.
El acuerdo de proveedores tampoco autentica criptográficamente el estado.

Faltan los demás bloques usados, las dependencias externas, la reconstrucción
inmediatamente anterior a cada transacción y la ejecución completa con precios,
liquidez, transferencias y costes. Las reglas exactas identificadas están en
`docs/aave-version-gates.md`; por sí solas no acreditan elegibilidad ejecutable,
latencia, rentabilidad ni un gate operativo. No se añade ningún evento a los
tres existentes ni se habilita firma, envío de transacciones o despliegue.
