# Patrocinio y prueba económica — 2026-10-16

Estado: **sin patrocinador contratado ni capital externo acreditado**. Capital del
fundador gastado en este trabajo: USD 0. Beneficio NQC realizado: USD 0.
Una cuenta sin ETH puede ejecutar con un paymaster; alguien debe financiar el
depósito del paymaster y la transacción del bundler, incluso ante fallos.

## Política propuesta: sólo presupuesto externo ya financiado

1. Un tercero aporta el depósito ETH y el presupuesto del bundler. Cubre también
   despliegues, stake, infraestructura, intentos revertidos y operaciones rechazadas.
   Antes de asumir obligaciones se necesita un acuerdo revisado que excluya deuda,
   garantías personales, reposiciones obligatorias y cargos automáticos al fundador.
   Un contrato Solidity por sí solo no acredita estas condiciones comerciales.
2. Admisión cerrada por defecto: red/EntryPoint/cuenta/ejecutor/mercado/router y
   selector permitidos; calldata firmada; nonce; ventana L2; código fijado; estado y
   cotización recientes; margen mínimo después de costes conservadores.
3. Reservar el prefund máximo de **cada** operación antes de autorizarla, incluyendo
   operaciones firmadas pendientes. Límites por operación, conjunto de operaciones,
   periodo y pérdidas acumuladas. No autorizar mientras falten fondos reservables.
4. Conciliar recibo final, UserOperationEvent, saldo del depósito, pago al beneficiario
   y resultado de tokens. El parámetro `actualGasCost` recibido en `postOp` todavía
   excluye su propio coste y la penalización final. No usarlo para liberar reservas.
5. Pagar al financiador únicamente con el excedente efectivamente recibido, según el
   acuerdo; los fallos no crean cuentas por cobrar al fundador. Si se agota el
   presupuesto, detenerse. No hay garantía de rentabilidad ni de continuidad.

`NqcBudgetPaymasterFixture` demuestra localmente una reserva especialmente
conservadora: consume el prefund entero del presupuesto vitalicio y nunca lo
reintegra durante `postOp`. Dos operaciones no pueden reservar el mismo dinero.
Esto sacrifica utilización para no subestimar el coste. No es un paymaster listo
para producción: faltan política detallada de llamadas, stake/admisión ERC-7562,
operación segura y conciliación externa antes de abrir un presupuesto nuevo.

## Opciones investigadas

| Opción | Qué aporta | Resultado para NQC |
|---|---|---|
| Alchemy Gas Manager | Infraestructura AA recomendada por Robinhood; facturación o créditos | No es capital gratuito. Su FAQ advierte posibles excesos temporales sobre límites y responsabilidad por gas cuando falla el cobro ERC-20. No acredita ausencia de deuda. |
| ZeroDev | Alternativa documentada por Robinhood; gas mediante tarjeta o créditos | Tampoco demuestra un financiador externo. Condiciones de prepago y cobertura de fallos deben acordarse explícitamente. |
| Unlinked | Su documentación anuncia un paymaster experimental financiado por su operador, con prueba de trabajo | Candidato de investigación, no sponsor confirmado. Usa EntryPoint v0.9 y Simple7702Account, no esta cuenta v0.7; publica perfiles pequeños de transferencia/aprobación. Compatibilidad con liquidaciones, latencia, presupuesto y condiciones siguen sin demostrar. |
| Financiador que comparte el excedente | Puede financiar depósito y bundler y asumir fallos | Ruta comercial a acreditar. No hay acuerdo ni fondos verificados en este expediente. |

No se creó cuenta, se compraron créditos, se contactó a terceros ni se envió una
UserOperation a esos servicios. La búsqueda de proveedores no es exhaustiva.

Fuentes primarias consultadas:

- [Robinhood: Account Abstraction](https://docs.robinhood.com/chain/account-abstraction/)
- [Alchemy: Gas Manager FAQs](https://www.alchemy.com/docs/wallets/reference/gas-manager-faqs)
- [ZeroDev: Sponsoring Gas](https://docs.zerodev.app/smart-accounts/sponsor-gas/evm)
- [Unlinked: FAQ](https://useunlinked.app/docs/faq)
- [Unlinked: parámetros](https://useunlinked.app/docs/parameters) — distingue perfiles de mainnet y parámetros etiquetados testnet; no se trataron estos últimos como estado mainnet.

## Cómo demostrar monetización

Para cada intento prospectivo registrar estado previo, hora de detección y envío,
inclusión o motivo de rechazo, cotización ejecutable, excedente recibido, gas final,
tarifas y reparto. Incluir TODOS los intentos, sin seleccionar sólo ganadores.

Para una sola entidad que financia paymaster y bundler, el pago interno entre ambos
no es un segundo gasto. El coste externo es la comisión de la transacción más
servicios, despliegues y operación. Si el bundler es un tercero, el gasto contractual
del patrocinador puede ser el débito del paymaster más sus tarifas. No sumar ambos
conceptos indiscriminadamente. En Arbitrum, una estimación total ya incluye el
componente L1: tampoco debe sumarse otra vez.

Con una definición consistente de quién paga, sea `q` la probabilidad prospectiva
de éxito, `S` el excedente bruto realizado por éxito, `Cs` el coste por éxito,
`Cf` el coste por fallo y `I` la infraestructura imputada por intento:

`E[neto/intento] = q × (S − Cs) − (1 − q) × Cf − I`.

El excedente del DEX sintético no estima `S`, ni la tasa de éxito de las pruebas
estima `q`. Con los datos actuales no se puede calcular un ingreso mensual fiable.
Para la meta de USD 5.000/mes harían falta 500 capturas a USD 10 netos o 200 a
USD 25 netos, por ejemplo: son requisitos aritméticos, no una previsión de capturas.

Siguiente puerta: replay con mercado y ruta reales, coste Nitro/DA y política de
cuenta real; después admisión del bundler y financiación sin recurso acreditada;
después observación prospectiva completa. Sólo con esos datos procede valorar una
prueba LIVE pequeña y expresamente autorizada.
