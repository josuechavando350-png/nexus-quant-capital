# Condiciones públicas revisadas — 16 de octubre de 2026 UTC

Investigación documental, sin cuentas, credenciales, compras, contacto comercial
ni solicitudes de patrocinio. Las notas son paráfrasis; no son ofertas para NQC,
verificación de saldos ni copias autenticadas del HTML. Las páginas pueden cambiar.

| Opción | Evidencia pública consultada | Implicación para capital propio cero |
|---|---|---|
| Alchemy | [Redes](https://www.alchemy.com/docs/wallets/supported-chains) enumera Robinhood Mainnet para bundler, patrocinio y pago ERC20. [FAQ](https://www.alchemy.com/docs/wallets/reference/gas-manager-faqs) describe facturación del gas adelantado/créditos comprados, tarifa PAYG de 8% y condiciones personalizadas. Advierte que el cobro ERC20 posterior fallido revierte la operación pero deja responsabilidad por gas; límites configurados pueden superarse brevemente. | Hay infraestructura anunciada para la red. No hay subvención ni aceptación de nuestra operación demostrada. La tarifa general no es cotización de nuestro paymaster. El tercero financiador tendría que ser responsable de la cuenta, pérdidas y facturas; no trasladarlas a Chavando. |
| ZeroDev | [Sponsoring Gas](https://docs.zerodev.app/smart-accounts/sponsor-gas/evm) describe tarjeta con facturación mensual o compra de créditos. | Abstrae el gas del usuario final, pero alguien lo paga. No se comprobó admisión del ejecutor/paymaster de NQC en Robinhood, ni una asignación gratuita. |
| Unlinked | [FAQ](https://useunlinked.app/docs/faq) declara tesorería financiada por el operador, presupuesto pequeño, Simple7702Account v0.9 y uso exclusivo de su relay. Anuncia mainnet Robinhood desde 30/sep/2026. | Posible servicio subvencionado bajo sus restricciones, no financiación comprometida para NQC. Nuestra ruta probada usa EntryPoint v0.7; cambiar de cuenta/EntryPoint/relay exige otro estudio. No asumir que acepta liquidaciones ni que el trabajo computacional cabe en su ventana. No se llamó al relay ni se verificaron sus saldos on-chain. |

[Parameters de Unlinked](https://useunlinked.app/docs/parameters) distingue
configuración de testnet. Sus cotas testnet NO se reutilizan como límites mainnet.
[Morpho Blue](https://docs.morpho.org/developers/contracts/blue/) documenta
`liquidate` y `flashLoan` como funciones distintas; el orden de efectivo de NQC
se acredita con la traza fijada y el código del repo, no con una inferencia de
marketing o con otro protocolo Morpho.

La consulta de `https://docs.robinhood.com/chain/account-abstraction/` mediante el
buscador no devolvió contenido accesible. No se presenta esa página como una
verificación nueva ni se cambió el endpoint RPC para eludir una denegación.

Conclusión documental: no se encontró un compromiso de financiar NQC sin recurso
contra el fundador. La documentación pública no puede acreditar aceptación privada,
presupuesto disponible, contrato ni transferencia de riesgo.
