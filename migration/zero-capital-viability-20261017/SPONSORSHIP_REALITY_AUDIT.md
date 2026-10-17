# Dinero, obligaciones y patrocinio

Fecha de revisión: 2026-10-17. **PATROCINIO_NO_DEMOSTRADO** para las tres líneas. No se contactó a operadores, aceptó términos, abrió cuentas, firmó ni envió bundles. La documentación pública describe mecanismos; no acredita fondos comprometidos a NQC ni ausencia de recurso contra su propietario.

## Cuatro niveles de evidencia

| Ruta | Documentación pública | Verificación local o expediente | Aceptación de contraparte para NQC | Operación NQC comprobada |
|---|---|---|---|---|
| Titan | Financiación condicional documentada | Aritmética exacta; no política de producción ejecutada | PENDIENTE | Ninguna |
| Quasar | Financiación condicional documentada | Aritmética exacta; no política de producción ejecutada | PENDIENTE | Ninguna |
| AA v0.7 Robinhood | EntryPoint y bundler originales identificados | Trazas guardadas re-auditadas; prefunding ficticio | PENDIENTE | Ninguna |
| Aave/SVR | Señal/subasta documentadas | One-shot histórica no es ejecutor actual de puja | PENDIENTE | Ninguna |

**Titan.** [eth_sendBundle](https://docs.titanbuilder.xyz/api/eth_sendbundle) documenta anticipos cuando falta saldo para gas y valor, condicionados a aumento del balance del builder. Incluye opciones de transacciones que pueden revertir o eliminarse, reemplazo y devolución de parte de la recompensa; la devolución tiene su propio coste. No deducimos de ello un tope disponible para NQC, obligación de cubrir despliegue más ejecución, beneficiario de reembolso concreto, cobertura de pérdidas ni contrato sin recurso. La aceptación exacta de nonce, orden, ventanas y contenido sigue pendiente para nuestro candidato. Ninguna petición se envió.

**Quasar.** [eth_sendBundle](https://docs.quasar.win/api/eth_sendbundle) describe financiación condicional del gas y aumento de balance del builder. Sus campos de tiempo, reemplazo, exclusión/reversión y reembolso no constituyen garantía de inclusión. No extendemos su texto a financiar valor, una creación contractual o una secuencia de creación y ejecución sin prueba específica. No hay importe, destinatario ni compromiso aceptado para NQC.

**Servicios AA facturables.** [Alchemy](https://www.alchemy.com/docs/wallets/reference/gas-manager-faqs) describe adelanto con facturación/gestión de créditos y riesgos de cobro de gas incluso cuando falla el pago en ERC-20. [ZeroDev](https://docs.zerodev.app/smart-accounts/sponsor-gas/evm) documenta patrocinio sujeto a política y pago mediante tarjeta o créditos. Son mecanismos de asignación de coste al cliente; no acreditan que un tercero soporte gratuitamente todo el riesgo. Activarlos a cargo del propietario incumpliría G0. No se activaron.

## Balance del financiador

Se reutiliza `economic_ledger.py` sin alterarlo. En wei:

`M = R + U + V - A - F - P - O`.

A es anticipo; U devolución no utilizada; R reembolso de la operación; V otro ingreso **atribuible y verificado**; F gas de financiación; P pago separado al proponente; O otros costes. Admisión exige `M >= M_req`, pero M_req y el compromiso son DESCONOCIDOS. El gas consumido desde A no se vuelve a restar como un segundo pago. El pago a `block.coinbase` no entra automáticamente en V: falta demostrar identidad y derecho económico del receptor. El depósito de EntryPoint es saldo comprometido, no ingreso nuevo; stake también inmoviliza capital aunque sea recuperable.

`comparison_audit.py` ensaya un caso **hipotético, no oferta comercial**: A=10^15, U=6×10^14, F=2×10^13, R=V=P=O=0. Un top-up separado y operación incluida con revert deja pérdida del financiador de **420000000000000 wei**. La responsabilidad contractual del propietario queda `null`. Un bundle no incluido no consume gas on-chain de sus transacciones, pero puede haber costes externos; si el anticipo se incluyó por separado, no se puede asumir devolución atómica. Deben auditarse transacciones eliminadas, cambios de nonce/estado, expiración, top-ups parciales, reembolso y saldo retenido. Un revert incluido sí consume gas.

## Robinhood: quién pierde y quién cobra

Fuente exacta: `6693542e675f930a7ef0a4fd60cb72e7a6608845`, `migration/robinhood-real-state-replay-20261016/`. Se verificaron nuevamente los datos guardados, no se ejecutó Nitro ni una UserOperation nueva. `evidence/robinhood-reconciliation.json` conserva las tasas y `comparison.json` particiona cuatro actores.

| Delta, ETH | Simulación en índice 1 | Simulación fallida en padre |
|---|---:|---:|
| Gas nativo: pagador→red | 0.000057601054408 | 0.000039639718050 |
| Depósito paymaster→beneficiario fixture | 0.000079616762214 | 0.000050201161200 |
| Beneficiario menos gas, **si** mismo dueño del pagador | +0.000022015707806 | +0.000010561443150 |

Pagador y beneficiario tienen direcciones diferentes: la titularidad común **no está acreditada**. Si paymaster, beneficiario y pagador pertenecieran a una misma entidad, la transferencia interna se eliminaría y su coste externo sería solo la tasa de red. Si el beneficiario es externo al paymaster, el débito del paymaster sí es su coste. No sumamos ambas partidas como dos comisiones de red. No convertimos estos deltas en beneficio NQC.

Las fixtures aportan **0.1 ETH a EntryPoint y 0.01 ETH al bundler**. La liquidación falla en el estado padre y aun así hay cobro; el excedente USDG no puede cubrir ese intento fallido. Despliegue está excluido. La estimación DA cero en dos contextos no prueba DA siempre gratuita.

## Admisión v0.7: límites comprobados

Se leyeron las fuentes originales del bundler en `1868538f1d7678576291d2ecabb4443c797ad133`: ValidationManager, TracerResultParser, DepositManager y ReputationManager. Sus hashes están en `evidence/source-observations.json`. Son capas adicionales a que EntryPoint devuelva RETURN: ventanas de validez, firmas, reglas de almacenamiento/opcodes, reputación, stake aplicable y reserva de depósito para operaciones pendientes. No se utilizó `unsafe` ni validadores de sustitución.

El expediente contiene controles Geth locales: firma inválida, depósito cero y presupuesto cero revierten; ajustes de ventana y stake permiten otros controles EVM. No son ejecución integral del bundler y no fueron reejecutados aquí. Prefund del control: **249541240000000 wei**. El paquete completo quedó bloqueado por dependencias fijadas ausentes (`ethers` 5.7.2, paquetes `@ethersproject` 5.7.0, `async-mutex` 0.4.0 y artefactos dist); el expediente conserva una denegación automática de aprobación al intentar recuperar esa instalación. No se repitió la ruta denegada. El [ERC-7562 actual](https://eips.ethereum.org/EIPS/eip-7562) se usa como referencia conceptual, no como prueba de que todas sus versiones coinciden con ese commit.

**Dato indispensable pendiente:** contraparte identificada que comprometa anticipo, despliegue, depósito/stake, gas de fallos e infraestructura sin exigir pago, garantía, reposición o deuda personal. No se ha acreditado ninguna.
