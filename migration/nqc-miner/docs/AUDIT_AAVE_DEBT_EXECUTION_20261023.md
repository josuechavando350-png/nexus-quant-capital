# Auditoría: ejecución conjunta de deuda Aave

Fecha: 23 de octubre de 2026. Avance ponderado: **43/100**.

La función interna original `LiquidationLogic._burnDebtTokens` ya se ejecuta
junto con el token de deuda variable y la estrategia de tasas reales cuyo código
se verificó en el bloque anterior. La quema, su resultado y las tasas se calculan
durante una misma transacción local de REVM; no son respuestas prefijadas en esta
composición. El modelo CLI aislado anterior conserva sus entradas y límites.

## Resultado concreto

En el ejemplo retenido, un repago nominal de 40 con índice 1.5 convierte la quema
a 26 unidades escaladas. El token reduce el saldo escalado de 100 a 74 y el total
de 1000 a 974. Devuelve ese total real al Pool, sustituyendo el valor de caché
artificialmente diferente. La estrategia carga sus parámetros de storage y
calcula las tasas con sus redondeos originales.

Los intereses acumulados hacen que este caso emita `Mint` durante una quema.
La sonda de recompensas recibe los saldos previos y observa mediante getters el
saldo, suministro e índice ya actualizados. Los eventos completos y los cinco
slots cambiados del Pool, dos del token y uno de la sonda coinciden con el cálculo
independiente. El caso se repite por el CLI con igualdad de resultado completo.

## Verificación

La batería final aprueba **202 pruebas Rust y 293 Python: 495 en total**, sin
fallos ni pruebas omitidas. Clippy con advertencias denegadas, formato, identidad
de fuente/binario, alcance y aislamiento también pasan. Los resultados están en
`evidence/aave-debt-execution-20261023/offline/summary.json`; la identidad de fuente
y los hashes de la entrega quedan vinculados en `verification.json`.

Ocho pruebas Rust nuevas contienen **632 intentos de sandbox**: 600 éxitos con
semilla fija y 32 casos dirigidos. El total es 611 éxitos, 14 reversiones completas
y siete rechazos por testigos de estado ausentes. Los éxitos comparan diez
resultados ABI, todos los eventos ordenados y todos los cambios de almacenamiento
de contratos. Cada reversión exige ausencia de logs y cambios de storage en
Pool, token y recompensas, incluidos errores posteriores al callback exitoso.

Se cubren deuda parcial/completa/cero, colateral agotado, total restante cero,
utilización antes/en/después del punto de cambio de pendiente, saldo máximo de
120 bits, preservación de bits de delegación, redondeo de quema a cero, límites de
saldo/suministro/índice, SafeCast, caller no autorizado, callbacks fallidos,
repago/liquidez y factor de reserva inválidos. El intento de quema desde la sonda
falla el control `onlyPool` del token real; no se declara seguridad general frente
a reentrancia.

Cuatro pruebas Python vinculan fuentes originales, compilación, código real,
layouts y flags; ejecutan el ejemplo por el CLI y rechazan dependencias, slots o
hashes de código inconsistentes. Los logs de fallos preliminares de conversión,
inferencia de tipos, prefijo de selector y estilo están conservados. Se corrigió
el checksum textual de una dirección del proxy sintético. No se cambiaron
fuentes originales, dependencias ni reglas de lint para resolver esos problemas.

Fuente ejecutada: `60dd3ebee9c117a3e35c7d4ba1545e2032649232`.
El bundle requiere `3d47c20299657af4cbbd04dce19a4b42cd3c3e5a`.

## Límite de confianza

Confianza alta en esta composición dentro de los casos ejecutados. El estado,
la entrada del Pool, el proxy de forwarding y el comportamiento de recompensas
siguen siendo sintéticos. El token usa su runtime verificado de 7198 bytes y la
estrategia el de 4038 bytes, sin recompilarlos conjuntamente ni cambiar sus
perfiles originales. Las fuentes del Pool importadas por el wrapper tampoco se
alteran.

Faltan el proxy desplegado, controlador real de recompensas, balances y parámetros
históricos autenticados, aToken y transferencias del activo, deuda multirreserva,
salud/eMode y estado intrabloque bajo el fork histórico correcto. La ejecución
usa el perfil Cancun soportado por el sandbox; no certifica el fork histórico.
No se declara liquidación completa, Foundry fuzzing, build hermético ni ganancia.
El gas del ejemplo corresponde únicamente a este harness artificial.

No se añaden eventos históricos ni crédito operativo. Observer permanece intacto;
no se habilitan workflows, firma, envío de transacciones, despliegue ni gasto.
