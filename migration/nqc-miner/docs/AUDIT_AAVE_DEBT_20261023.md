# Auditoría: quema de deuda y déficit Aave

Fecha: 23 de octubre de 2026. Avance ponderado: **43/100**.

`calculate-aave-debt` reproduce la contabilidad de la función interna original
`LiquidationLogic._burnDebtTokens`, incluida la actualización de tasas y liquidez
virtual de ReserveLogic. A diferencia de un replay histórico, sus respuestas
de token y estrategia son entradas explícitas. Se conserva ese límite en cada
informe, incluso cuando todas las operaciones calculadas pasan.

## Resultado comprobado

La función omite el token cuando la deuda ya es cero y limpia el indicador de
préstamo antiguo. Con deuda, convierte el importe a quemar redondeando hacia
abajo; si no queda colateral usa toda la deuda. La deuda no repagada aumenta el
déficit con los límites enteros originales. El cálculo conserva exactamente
el total escalado y el booleano devueltos por el token simulado.

La estrategia recibe el déficit actualizado y el saldo virtual anterior al
repago, junto con la deuda total redondeada hacia arriba. Después se convierten
las tasas y el repago a 128 bits y se actualiza la liquidez virtual. Errores de
helpers, aritmética, SafeCast, índice de reserva y dependencias externas se
propagan en el orden de la función; un fallo no devuelve resultados parciales.

## Verificación

- **194 pruebas Rust y 277 Python**, 471 en total, aprobadas sin fallos ni
  omitidas en la batería final.
- 579 entradas principales: 500 éxitos, cinco reversiones vacías, siete pánicos
  de aritmética, dos SafeCast, dos índices inválidos y 63 errores externos con
  datos no vacíos. Se ejecutan otras 500 sondas en los casos exitosos para
  comparar los ocho argumentos ABI enviados a la estrategia: **1079 llamadas**.
- Las pruebas dirigidas añaden **24 llamadas**: quema parcial/completa, deuda
  cero, flags antiguos, conversiones separadas, orden de errores y errores
  externos vacíos, de 64 bytes y de 4096 bytes. Total: 1103 ejecuciones de
  referencia dentro de las pruebas, no 1103 pruebas generales adicionales.
- Se comparan diez resultados ABI, bytes de reversión y eventos completos
  (dirección, topics y datos). En los fallos se comprueba la ausencia de eventos
  y de cambios de storage del contrato; las sondas revierten deliberadamente.
- Cuatro nuevas pruebas Python verifican fuentes/compilación/storage, contrato
  estricto del CLI, respuestas externas/errores y composición colateral→déficit.
- Clippy con advertencias como errores, formato, alcance, aislamiento e identidad
  del binario aprobados. Fuente ejecutable:
  `3b6e088970c02223dfe9f6f2260ff03f018c65c6`, `source_dirty=false`.
- Se mantienen 531 archivos originales, 106 workflows deshabilitados y cero
  activos. Todo el cambio está dentro de `migration/nqc-miner/`.

El harness llama a la función interna original completa e importa todas las
fuentes sin alterarlas. solc 0.8.27 de hash fijado produce 4187 bytes de runtime,
SHA-256 `deba25955bc2b2bcac2d4811352c49869b675c098f6006c323911d1222f59fe8`.
El layout del compilador fija 23 slots estáticos y dos raíces de bytes dinámicos;
la prueba declara 128 posiciones en cada raíz explícitamente en el estado
sintético cerrado. Nunca se rellenan ausencias en un estado histórico.

## Trazabilidad y límites

Se conserva el primer fallo de compilación del test: la macro de llamada ABI
solicitaba una interfaz ausente en las versiones fijadas de Alloy. Se sustituyó
solo esa construcción del test por la codificación ABI canónica de sus dos
argumentos y tuple dinámico; no se cambiaron dependencias, fuentes originales
ni código de producción para resolverlo. Quedan retenidas la ejecución inicial
de seis pruebas y la ampliación final de siete, además de la batería completa.

El bundle recupera el commit de fuente a partir de
`01d72c3c1f183b2feb6c88caeca1b06a37381a03`. `verification.json` fija hashes de
documentación, compilación, fixtures indirectamente por el manifest y todos los
logs. No se presenta esta compilación de host como un build hermético.

La prueba no ejecuta el token ni la fórmula de la estrategia reales, ni el
recorrido multirreserva `_burnBadDebt`, la liquidación completa o transferencias
de activos. Tampoco autentica precios, eMode, posición, fork ni estado intrabloque.
No hubo nuevas observaciones históricas ni Foundry fuzzing. La siguiente etapa
es verificar esas dependencias y sustituir las respuestas suministradas.

Observer permanece intacto. No se activan workflows, despliegue, firma ni gasto;
no se acredita una nueva fase operativa ni rentabilidad.
