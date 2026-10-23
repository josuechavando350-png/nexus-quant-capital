# Auditoría: consumo de colateral y comisión final

Fecha: 23 de octubre de 2026. Avance ponderado: **43/100**.

Se añadió `calculate-aave-collateral`, un cálculo de revisión 11 sobre entradas
suministradas. Resuelve el agotamiento de colateral escalado, la condición de
limpieza del flag y el ajuste final de comisión. Conserva enteros de 256 bits,
redondeos independientes, orden de operaciones y bytes de reversión.

## Resultado y referencia

El cálculo reproduce casos donde la suma nominal deja un sobrante, pero los dos
redondeos escalados agotan el saldo. Distingue agotamiento de una reserva de
agotamiento del colateral total, incluido polvo que pierde todo su valor al
redondear. La comisión se limita al saldo posterior a la operación del
liquidador. Si el límite la lleva a cero, se conserva que el bloque original
todavía llama al token.

El constructor extrae los fragmentos originales byte por byte y conserva hashes
de esos segmentos y de todas las fuentes importadas. La compilación usa solc
0.8.27 con hash fijado y los ajustes originales del pool. El harness generado
compila a 2436 bytes, SHA-256
`a655af58324c046620ed3bc44ab2bd455d06ed77c6d62d0c5559fdbee5a20629`.

## Verificación

- 187 pruebas Rust y 273 Python aprobadas: **460** en total, sin fallos ni
  omitidas en la batería final.
- 1089 ejecuciones diferenciales principales: 1081 éxitos, cuatro reversiones
  vacías de helpers y cuatro pánicos aritméticos. Se comparan ocho palabras ABI
  o los bytes completos de reversión. Otras pruebas suman siete ejecuciones
  dirigidas, para 1096 llamadas a la referencia. Son casos dentro de las pruebas,
  no pruebas generales adicionales.
- Cuatro nuevas pruebas Python verifican procedencia/compilación, rechazo de
  fuentes alteradas, comportamiento del CLI y composición de los comandos de
  reserva, importes y colateral con datos sintéticos.
- Clippy con advertencias como errores, formato, alcance, aislamiento e
  identidad del binario aprobados. Commit ejecutable auditado:
  `83d4d4d70eb3d3fddc0236f153e9232c0aab6dab`, `source_dirty=false`.
- Se conservan 531 archivos originales, 106 workflows deshabilitados y cero
  activos. Las modificaciones se limitan a `migration/nqc-miner/`.
- Entradas/salidas de compilador, fixture, logs y hashes se conservan en
  `evidence/aave-collateral-20261023/`. El bundle recupera el commit de fuente
  partiendo del commit publicado `389ac273d2a29807170d2f884e413eeb20d60fbb`.

El primer intento de formato desde la raíz no seleccionó toolchain; la ejecución
desde el módulo con el RUSTUP_HOME correspondiente y la batería final pasaron.
No hubo cambio de dependencias ni de código para resolver ese entorno.

## Límites

Los fragmentos no son contiguos en el pool real: se omiten quema de deuda y
operación del colateral entre ellos. La primera reversión del harness no debe
interpretarse como la primera reversión de una liquidación completa. El token
artificial solo suministra `scaledBalanceOf` y captura la llamada de comisión.
No reproduce sus transferencias, incentivos, permisos o estado autenticado.

`post_liquidator_scaled_balance` sigue siendo una entrada explícita; no se
inventa mediante una resta. La prueba de composición pasa resultados reales
entre los tres comandos, pero todos los valores proceden de un fixture. No
añade observaciones históricas ni certifica un fork, una posición o rentabilidad.
No se ejecutó Foundry fuzzing ni un build hermético.

Siguen pendientes deuda/deficit, tokens y dependencias autenticados, salud/eMode,
liquidez, transferencias, tasas y reconstrucción del estado intrabloque. Observer
permanece intacto; no hay activación, despliegue, firma ni gasto.
