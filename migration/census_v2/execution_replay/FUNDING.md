# Comparación de financiación y pago atómico

Estado: investigación histórica reproducida; **Census sigue abierto**.
Productor nuevo sobre padre `0ed99812e4e1e6f0b9b03fffdab0b90f21cb5d39`.
Los productores exactos, originales, copias modificadas, errores, respuestas
RPC y logs están en `inputs/funding-scenarios.zip` (667,501 bytes, 70 miembros),
SHA-256 `bd9e850c0b53db8b951fdd09ff1ac9b279fc78f2d8ee31acf5462dc120a2c2e4`.
El manifiesto vincula cada intento a su versión de productor. No se cambia
el ejecutor original ni se atribuye certificación a estas variantes.

## Pregunta y resultado

Mismo borrower, principal de 10.684013854557827871 WETH, estado del bloque
25,938,047 y sólo avance de timestamp al siguiente bloque. Se conserva el
perfil Cancun original; no se reproducen transacciones anteriores del bloque
ganador ni se afirma observación de Nexus antes de la decisión.

| Escenario | Comisión flash WETH | Excedente WETH tras repayment | Pago nativo dentro del escenario |
| --- | ---: | ---: | ---: |
| Aave | 0.005342006927278914 | 0.090814117763741536 | 0 |
| Balancer | 0 | 0.096156124691020450 | 0 |
| Balancer y pago observado | 0 | 0.000240390311727552 | 0.095915734379292898 ETH |

El Vault `0xBA12222222228d8Ba445958a75a0704d566BF2C8` tiene en este fork
1,130.949051190579858151 WETH. Se obtiene la comisión de su contrato de tarifas
y el callback confirma exactamente el importe: cero en ese estado, no una
promesa de comisión futura. La prueba exige liquidez para el principal real.

La tercera variante retira exactamente el pago de WETH y lo envía al receptor
autenticado del header `0x6adb3bab5730852eb53987ea89d8e8f16393c200`.
Verifica aumento nativo exacto del destinatario, repayment y excedente del
operador. El saldo nativo previo de la dirección de estrategia, 577,021,548,053,172
wei, queda intacto: no se reinicia ni se usa como subsidio. El caso negativo
de beneficio imposible revierte pago, saldo del prestamista, estado del borrower
y consumo de identidad. No se envió ninguna transacción real.

La primera variante de pago exigía saldo nativo inicial cero y falló en sus dos
pruebas. Se conserva completa como `bid-capture-001`, productor v2. La versión
v3 exige conservar el saldo histórico y comprobar el incremento exacto por
retiro de WETH. Pasa usando únicamente las respuestas ya guardadas.

Si se exige a Aave igualar ese pago observado, su residual antes de gas sería
**−0.005101616615551362 WETH**. Es un escenario condicionado, no prueba de que
ese pago fuera el mínimo, ni de propiedad de destinatarios o acuerdos privados.

## Gas: sensibilidad parcial, no utilidad neta

Se codifica el calldata real (708 bytes) y se cuentan bytes cero/no cero. Para
Balancer son 439/269: componente intrínseco 4/16 de 27,060 unidades. Medición
del `execute` con pago: 533,435 unidades normal y 521,200 aislado. La suma
ilustrativa es 560,495 / 548,260; no es recibo de transacción de producción.

| Precio aplicado | Restante normal para todos los demás costes, WETH equivalente |
| --- | ---: |
| Base fee del bloque: 0.059451728 gwei | 0.000207067915442192 |
| 0.1 gwei | 0.000184340811727552 |
| 1 gwei | −0.000320104688272448 |
| 10 gwei | −0.005364559688272448 |

La tarifa que agota únicamente estos componentes es aproximadamente 0.429 gwei
en modo normal. No es un umbral operativo: faltan estado frío real, reglas del
fork de producción, refunds, despliegue/amortización, financiación del gas,
conversión del WETH residual a ETH y otros costes, fallos e inclusión competitiva.
Las mediciones de los dos modos no forman un intervalo garantizado. El pago
se resta una vez; el gas del ganador histórico no se resta además como si fuera
gas de esta estrategia. `complete_profit_wei` permanece `null` y admisión falsa.
El presupuesto conserva el máximo acumulado **MXN 2,000 sólo para gas**, sin
gasto ni principal/colateral/garantía propios autorizados en estas pruebas.

## Reproducción y límites

Nodies respondió 124 lecturas nuevas para Aave/Balancer y otras 3 para el intento
de pago. La semilla se conserva byte por byte; el witness combinado contiene
127 claves únicas, sin reemplazar errores ni mezclar operadores. No se vuelve
a intentar dRPC o BlockPI. Hay cuatro intentos y tres versiones de productor.

Las dos pruebas Solidity pasan por variante: captura de Aave/Balancer y replay
normal/aislado de ambas; pago corregido normal/aislado sólo offline. Son seis
pares exitosos de ejecución offline, no seis oportunidades independientes.
El consumidor verifica 483 + 253 respuestas servidas contra el witness y todos
los hashes de fuentes/logs. Sus pruebas prohíben abrir red y rechazan corrupción,
duplicación de métricas y doble descuento del pago. Pasan 25 controles Python
afectados y 9 de aislamiento; Rust no se modifica ni se vuelve a ejecutar.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/verify_funding.py \
  --archive migration/census_v2/execution_replay/inputs/funding-scenarios.zip \
  --output /tmp/funding-readback.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/execution_replay -p 'test_*.py'
```

`funding-validation/report.json` conserva métricas y aritmética entera. Para
repetir Solidity, extraer a directorio nuevo y usar el productor archivado con
los binarios de Forge/Solc cuyos hashes exige el runner. Pasar `--replay` al
witness correspondiente: jamás se consulta upstream en ese modo.

Una respuesta RPC ligada a hash no es prueba Merkle de estado. La selección
retrospectiva de un ganador tampoco demuestra descubrimiento oportuno, capacidad
de inclusión, frecuencia, beneficio de toda la población ni viabilidad comercial.
Siguen pendientes cobertura secundaria completa, admisión por token/ruta,
economía completa y certificación independiente de las tres verdades.
