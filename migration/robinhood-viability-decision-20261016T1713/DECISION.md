# Decisión del segundo incremento — 16/oct/2026

**Recomiendo congelar el desarrollo activo de NQC bajo la condición actual de
cero capital propio.** Se cerraron los dos incrementos acordados: PR25 corrigió y
comprobó la validación EVM nativa; éste agotó la comprobación del entorno disponible
y de las alternativas documentadas de patrocinio. No se acreditaron admisión
completa ni financiación utilizable. Esto es una decisión de asignación de trabajo,
no una demostración de que NQC nunca pueda ganar dinero.

## Lo que sabemos y lo que falta

| Requisito | Evidencia al cierre | Resultado |
|---|---|---|
| Validación EVM de la firma/cuenta/paymaster | PR25: seis controles locales; replay offline exacto revalidado aquí | Demostrado sólo en laboratorio |
| Admisión completa | No se ejecutaron ValidationManager, parser ERC-7562, DepositManager, reputación ni mempool como conjunto | No demostrada |
| Entorno para esa prueba | Preflight de sólo lectura: faltan cuatro paquetes fijados y tres entradas compiladas de workspaces | Bloqueado en los directorios revisados |
| Gas y pérdidas sin dinero/deuda del fundador | Ningún compromiso, saldo reservado o política aceptada para NQC aportado al expediente | No demostrado |
| Captura repetible con margen neto | Sin nueva cohorte/candidato, inclusión o campaña prospectiva en este incremento | No demostrado |

La salida 1 del preflight es el resultado esperado `BLOCKED_PREREQUISITES`, no una
prueba de bundler que haya rechazado una operación. Faltan `ethers@5.7.2`,
`@ethersproject/properties@5.7.0`, `@ethersproject/providers@5.7.2`,
`async-mutex@0.4.0` y los `dist/src/index.js` de validation-manager/utils/sdk.
Se encontró debug 4.3.4 en caché; otras versiones no se contaron como compatibles.
Se inspeccionaron tres directorios node_modules y una caché Yarn, enumerados en
`evidence/environment.json`. No es una búsqueda universal de toda máquina posible.
Incluso encontrar todos esos archivos sólo permitiría preparar el build: faltaría
validar dependencias transitivas, integridad, resolución y ejecución real.

La instalación de PR24 quedó incompleta por red. La revisión automática rechazó
posteriormente consultar el instalador por riesgo de continuar tráfico después de
su parada. En este incremento no se reanudó, no se instaló nada y no hubo una nueva
denegación. No se sustituyeron dependencias por stubs ni se relajaron validadores.

## Patrocinio: tres alternativas revisadas

Revisión documental el 16/oct/2026; no consultas a relays, cuentas de proveedor,
claves, ofertas negociadas ni comprobación on-chain de fondos. No es un censo de
todos los posibles financiadores. Fuentes y límites en `evidence/providers.json`.

| Alternativa | Condición publicada relevante | Consecuencia para NQC |
|---|---|---|
| [Alchemy](https://www.alchemy.com/docs/wallets/reference/gas-manager-faqs) | Adelanta gas facturable o permite comprar créditos; PAYG publica 8%; un cobro ERC20 posterior fallido no elimina la responsabilidad del gas | Infraestructura cobrable; no acredita un tercero que absorba nuestros fallos |
| [ZeroDev](https://docs.zerodev.app/smart-accounts/sponsor-gas/evm) | Gas mediante cargo mensual a tarjeta o créditos comprados | Tampoco acredita financiación sin aportación ni obligación personal |
| [Unlinked](https://useunlinked.app/docs/relay) | Su relay exige EP v0.9, cuenta/delegación permitida y plantillas autorizadas | No es sustituto directo demostrado de la ruta v0.7 de NQC; no consta admisión de su liquidación |

Unlinked declara una tesorería del operador que paga fallos, pero con presupuesto
pequeño y acotado. Sus parámetros numéricos publicados están rotulados testnet;
no se aplicaron a mainnet. Su FAQ anuncia mainnet desde el 30/sep/2026 mientras
Quickstart aún contiene una frase de no despliegue: conservamos esa inconsistencia
sin resolverla a favor de disponibilidad. No probamos que el servicio esté caído,
que carezca de fondos ni que jamás pudiera admitir una integración distinta.

La documentación oficial de Robinhood sí lista EntryPoint v0.7 y opciones AA de
Alchemy/ZeroDev. La compatibilidad general de red tampoco certifica nuestra
operación concreta ni concede crédito. No se ejecutaron ejemplos de envío.

## Qué conservar y qué cambiaría la decisión

Conservar todos los PR borrador, código, capturas negativas y positivas, fuentes y
377 blobs originales. Mantener los 106 workflows deshabilitados y la tarea que ya
estaba pausada. No ampliar historia, cambiar arquitectura o repetir simulaciones
antiguas como sustituto de los dos bloqueos.

Una reapertura técnica acotada tendría sentido con **evidencia nueva**: un entorno
completo permitido y reproducible para la admisión, junto con una contraparte o
programa que ofrezca financiar el piloto exacto sin aportación/garantía/deuda del
fundador. Los términos mínimos están en `REOPENING.md`; una página de marketing o
un compromiso inventado no los satisface. La primera prueba sería admisión local
completa bajo protocolo nuevo y sin envíos. Nada se ha contratado ni solicitado.

Después todavía harían falta oportunidades nuevas y una campaña preregistrada
que cuente todos los intentos, fallos, gas, Nitro/DA, comisiones y conversión de
beneficio a caja de gas. Admitir una operación no prueba su inclusión ni su margen.

Confianza alta en los bloqueos documentados y la separación entre tipos de
evidencia; insuficiente para afirmar rentabilidad. No asignamos un porcentaje de
éxito ni convertimos la corrección de laboratorio en progreso comercial medido.
