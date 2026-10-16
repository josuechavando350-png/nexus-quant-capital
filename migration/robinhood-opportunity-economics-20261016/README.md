# NQC: detección anticipada, margen y capital de patrocinio

**Hay una hipótesis de detección concreta y una mejora de capital comprobada en
simulación. La captura futura, la admisión comercial y la financiación siguen
sin demostrarse.** Este trabajo amplía PR8 sin alterar sus fuentes ni resultados.

## 1. Qué podemos anticipar

Se hicieron diez nuevas consultas de lectura al endpoint público de demostración
documentado por QuickNode. Se conservan peticiones, respuestas y hashes.

| Contexto del caso 66744162 | Operación NQC | Excedente USDG |
|---|---|---:|
| Estado al cierre del bloque anterior, reloj original | Rechazo: posición sana | 0 |
| Mismo estado anterior, únicamente reloj +1 segundo | Éxito | 32.060665 |
| Mismo estado anterior, únicamente reloj +2 segundos | Éxito | 32.062461 |
| Mismo estado anterior, únicamente reloj +4 segundos | Éxito | 32.066049 |
| Estado real inmediatamente anterior a la liquidación | Éxito | 32.060665 |
| Estado real al cierre del bloque de la liquidación | Rechazo: posición sana | 0 |

Los 29 eventos del protocolo de la proyección +1 coinciden con la simulación
en el índice real. Coinciden también bytecodes y 112 slots leídos de contratos
del protocolo. El cambio de tiempo es suficiente para cambiar el resultado
en este estado; no fue necesario introducir una actualización ajena del oracle.
ArbOS sigue siendo nativo; sus slots de sistema no se presentan como contratos
del protocolo ni se exige que sean idénticos entre bloques.

El bloque completo identifica una transacción de sistema tipo 106 en el índice
0 y la liquidación en el índice 1. Al cierre, la deuda del prestatario es cero;
conserva 39193275743260624 unidades de colateral. La diferencia de colateral
coincide con las 93436250743843184 unidades incautadas. La primera comprobación
de desarrollo suponía equivocadamente colateral final cero: se corrigió para
comprobar deuda cero y el delta exacto, conservando la respuesta original.

**Hipótesis de trabajo:** vigilar posiciones ya conocidas y simular su
elegibilidad a horizontes cortos de tiempo usando únicamente el estado disponible.
La elegibilidad puede anticiparse en este caso. El competidor ya lo capturó en
la primera transacción no sistémica; observar el bloque cerrado habría llegado
tarde. El segundo entre timestamps no mide latencia ni garantiza una ventana de
un segundo. La proyección +4 tampoco prueba que la oportunidad real durase cuatro
segundos: omite deliberadamente las operaciones posteriores de otros usuarios.

El caso, prestatario y tamaño se eligieron retrospectivamente. No es una prueba
de descubrimiento prospectivo. En la muestra previa, seleccionada y enriquecida
por tamaño, 7 de los 11 casos de esta ruta están en índice 1. Los otros índices
son 3, 4, 44 y 63. No se inspeccionó la transacción de sistema de esos otros
bloques, ni se infiere frecuencia de oportunidades o cuota de mercado.

La documentación oficial de Robinhood describe orden por llegada. La de Nitro
describe el feed estándar como publicación de bloques completos. Por ello, el
feed puede acelerar la actualización de estado, pero no debe tratarse como una
vista garantizada de transacciones pendientes que permita adelantarse dentro
del mismo bloque. No se midió aquí la latencia de un feed ni de un bundler.

## 2. Mejora comprobada: menos capital reservado

`prepare_fee_variant.py` verifica el hash de la operación anterior y su ABI,
cambia solo `maxFeePerGas` y vuelve a firmar con la **clave pública de laboratorio
0x1234**. No admite una clave de usuario ni envía transacciones.

| Campo | PR8 | Variante histórica |
|---|---:|---:|
| Precio máximo, gwei | 2 | 0.102271 |
| Gas reservado total | 2440000 | 2440000 |
| Prefund máximo, ETH | 0.00488 | 0.00024954124 |
| Cargo al patrocinador, ETH | 0.000079616762214 | 0.000079616762214 |
| Comisión nativa Nitro, ETH | 0.000057601054408 | 0.000057601662034 |
| Excedente USDG | 32.060665 | 32.060665 |

La variante mantiene 50% de margen sobre la base histórica más la prioridad
original. El prefund baja **94.88645%**, sin reducir límites de gas ni mejorar
artificialmente el excedente. El `innerHandleOp` de Nitro confirma el nuevo
prefund. El gas nativo cambia de 853172 a 853181; no se atribuye la diferencia
a una causa no aislada. La comisión total sale de los movimientos nativos de
Nitro, no de sumar otra tarifa DA a posteriori.

Con un presupuesto hipotético de 0.01 ETH caben 2 reservas originales o 40
reservas de la variante, antes de otros requisitos. Esto no autoriza operaciones
concurrentes: nonces, reputación y reglas del bundler siguen aplicando. El nuevo
precio es para ese bloque histórico; no es una cotización para enviar hoy.

## 3. Margen: umbrales reproducibles, no promesas

`economics.py` exige supuestos explícitos y usa Decimal. Para un paymaster propio
y bundler externo cuenta el cargo del paymaster. Operando ambos se usaría la
comisión de red consolidada, más costes operativos; no se suman ambas como dos
comisiones de red. Impuesto NET, comisión del pool e impacto observado ya están
dentro del excedente histórico.

Escenario ilustrativo: 3000 USDG por ETH; 10% de descuento adicional sobre el
excedente; 0.02 USDG de RPC por intento; 250 USDG de infraestructura, 25 de
despliegue amortizado y 2 de capital por periodo; 1000 intentos en ese periodo.
No son precios contratados, costes completos medidos, previsión de volumen ni
supuesto de paridad USDG/USD. Los intentos de esta tabla se suponen incluidos en
cadena; un rechazo previo del bundler no consume ese gas, pero sí recursos.
Si un bundle llega a minarse y revierte antes del cobro al paymaster, el pagador
de red puede perder gas sin reembolso de EntryPoint. Quién asume ese caso debe
quedar en las condiciones del bundler; esta tabla modela cargos al patrocinador,
no una garantía sobre todas las responsabilidades de un contrato comercial.

| Cargo supuesto por fallo | Éxitos mínimos entre 1000 para beneficio positivo |
|---|---:|
| Mayor fallo Nitro observado en este caso | 16 |
| Cada fallo consume el prefund original completo | 346 |
| Cada fallo consume el prefund ajustado completo | 36 |

No se convierte el gas observado en un límite universal. Con 1% de captura,
el primer escenario pierde 159.939967 USDG por periodo; con 5% gana
990.714101 USDG. **No conocemos la tasa de captura ni sabemos si existen esos
1000 intentos con este excedente.** `result.json` conserva los valores exactos
y sensibilidades, incluyendo un recargo ilustrativo del 8%, sin presentarlo
como cotización de Alchemy para este paymaster.

Un financiador que asuma todos los costes del escenario y reciba 25% del
excedente necesita más de 6.281799% de captura para equilibrarse. Con 50% necesita
más de 3.121569%. Estos repartos son pruebas matemáticas, no ofertas ni acuerdos.
Sin participación o reembolso suficiente, financiar gas no es negocio para él.

## 4. Bundler y patrocinio: disponible no significa contratado

Las fuentes oficiales de Robinhood identifican Alchemy y ZeroDev, y publican
EntryPoint v0.7 en la dirección ya verificada. Alchemy documenta Robinhood en sus
redes de bundler y patrocinio; su API declara compatibilidad v0.7. No se abrió
cuenta, se buscó una clave, se solicitó patrocinio ni se ejecutó un bundler de
producción. No hay admisión de nuestra cuenta/paymaster acreditada.

Las condiciones documentadas de Gas Manager incluyen facturación del gas,
posibles excesos momentáneos sobre límites y responsabilidad por gas cuando
falla el cobro ERC20 posterior. La tarifa PAYG publicada es 8%; la disponibilidad
gratuita en testnet no financia mainnet. Es infraestructura comercial, no un
compromiso de asumir nuestras pérdidas sin recurso al fundador.

La traza conserva `preOpGas=130164`, frente a 780000 de límites previos: 16.69%.
Sirve de comparación con el umbral de eficiencia del 15% documentado por
Alchemy; no sustituye su simulación ni todos sus controles. Siguen pendientes
stake/reputación del paymaster, compatibilidad de la cuenta EIP-191, políticas
de calldata, coste de creación, estimación de UserOperation y latencia.

Hay un límite concreto del prototipo: el paymaster devuelve `validationData=0`
y el reloj L2 se revisa durante ejecución. Caducar la oportunidad no caduca la
autorización del patrocinio. Un intento tardío puede revertir y cobrar gas.
Hace falta caducidad en validación, ligada a la autorización completa, además
del control de bloque durante ejecución. No se cambió el contrato recuperado.

`reservation_model.py` implementa un modelo offline de fondo prepagado finito:
reserva el máximo antes de conceder una autorización hipotética, incluye
pendientes, evita duplicados y serializa solicitudes simultáneas con SQLite.
Ni el tiempo ni registrar un gasto menor reciclan su presupuesto de por vida.
No verifica financiación real, firmas, recibos canónicos, finalización ni reorgs;
no es un control listo para custodiar dinero. Capital financiado acreditado
para este plan: **ninguno**. Fondo por defecto de producción: bloqueado.

## 5. Siguiente prueba y criterios de salida

`shadow_gate.py` es una función pura de decisión en papel: rechaza datos futuros,
casos elegidos retrospectivamente, simulaciones no disponibles al decidir,
estado viejo, margen no positivo y capital insuficiente. Exige evidencias
de admisión, caducidad en validación, financiación sin recurso y presupuesto de
latencia. Incluso un resultado positivo no habilita envío ni firma.

El observador prospectivo todavía no está desplegado. Su ensayo debe fijar
antes de observar los resultados el universo de mercados/prestatarios,
horizontes de tiempo, reglas de tamaño y coste, y periodo de evaluación. Debe
guardar cada señal con hash de bloque, hora monotónica de recepción, final de
simulación, decisión y motivo de rechazo. Debe incluir oportunidades perdidas,
candidatos falsos y periodos sin señal, sin seleccionar solo liquidaciones que
ya tuvieron éxito. Simulaciones +1/+2/+4 son hipótesis, no datos del futuro.

El primer ensayo útil mide cuánto tarda detectar y preparar cada candidato con
estado disponible, y si sigue siendo ejecutable al siguiente estado realmente
observado. Una simulación que sobrevive no demuestra inclusión: después haría
falta medir admisión e inclusión con un operador autorizado y capital acotado.
La ruta comercial propuesta para evaluar es un bundler administrado y un fondo
ETH externo prepagado con pérdidas limitadas y reparto explícito. No existe aún
acuerdo que demuestre ausencia de deuda o garantías personales.

No se inicia un servicio de baja latencia sobre un endpoint de demostración ni
se presenta una simulación histórica como ese servicio. La decisión de invertir
dependerá de observaciones prospectivas, costes contratados y condiciones del
financiador, además de cerrar los requisitos técnicos anteriores.

## Reproducción y verificaciones

Desde la raíz del repo:

```bash
python migration/robinhood-opportunity-economics-20261016/audit_opportunity.py --out /tmp/nqc-opportunity-result.json
python -m unittest discover -s migration/robinhood-opportunity-economics-20261016 -p test_opportunity.py -v
python -m unittest discover -s migration/robinhood-real-state-replay-20261016 -p test_result.py -v
python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Los tests son offline. Las peticiones remotas exactas están en cada
`evidence/*/requests.json`; solo se ejecutaron métodos de lectura, fijados a
dos bloques históricos. La variante se puede reconstruir con
`prepare_fee_variant.py --cast /ruta/cast --out /tmp/directorio-nuevo` usando
el binario fijado de Foundry 1.7.1. No se compilaron ni cambiaron contratos
Solidity en este incremento; no hubo cambios Rust ni nueva suite Rust.

Veinte pruebas nuevas cubren conciliación, corrupción de evidencia, overrides,
margen, reservas concurrentes, persistencia, duplicados y filtros temporales.
Se añaden las dieciséis pruebas de PR8 y nueve de aislamiento. Los logs finales
y manifiesto de hashes acompañan la evidencia. Una incidencia transitoria de
transporte de la herramienta de edición se resolvió sin cambio de alcance.

## Fuentes primarias consultadas el 16 de octubre de 2026

- [Robinhood: orden de transacciones](https://docs.robinhood.com/chain/).
- [Robinhood: cuenta abstracta, proveedores y EntryPoints](https://docs.robinhood.com/chain/account-abstraction/).
- [Robinhood: endpoints y límites públicos](https://docs.robinhood.com/chain/connecting/).
- [Nitro: contenido del feed estándar](https://docs.arbitrum.io/run-a-node/sequencer/read-sequencer-feed).
- [Alchemy: redes disponibles](https://www.alchemy.com/docs/wallets/supported-chains).
- [Alchemy: bundler y versiones](https://www.alchemy.com/docs/wallets/transactions/low-level-infra/bundler/overview).
- [Alchemy: criterios de gas](https://www.alchemy.com/docs/wallets/reference/bundler-faqs).
- [Alchemy: facturación, límites y cobro ERC20](https://www.alchemy.com/docs/wallets/reference/gas-manager-faqs).
- [QuickNode: endpoint público y trazas](https://www.quicknode.com/docs/robinhood/debug_traceTransaction).
- [EntryPoint v0.7: prefund](https://github.com/eth-infinitism/account-abstraction/blob/7af70c8993a6f42973f520ae0752386a5032abe7/contracts/core/EntryPoint.sol).
