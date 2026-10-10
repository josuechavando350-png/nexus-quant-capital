# Evaluación de la propuesta L2/L3 del usuario

Decisión posterior del usuario: **Ethereum + Base** son ahora las redes activas
de investigación. `base_expansion/README.md` registra alcance y primer acceso;
las demás redes quedan en espera. La comparación siguiente conserva su fecha
y carácter documental, sin convertirse en prueba de rentabilidad.

Investigación documental del 10 de octubre de 2026 UTC, a partir de PR #3
`3c8e9117f09ea3c6a076ab57e30642f8a165a0fe`. Responde a la propuesta de Base,
Arbitrum One, OP Mainnet, Linea, Orbit/ApeChain, Degen Chain y zkLink Nova.
Las prioridades siguientes son juicio de investigación; no constituyen un
ranking medido de rentabilidad ni amplían el alcance Ethereum declarado.

## Evaluación por red

| Red o familia | Tratamiento propuesto | Condición material |
| --- | --- | --- |
| Base | Primera evaluación de expansión | Aave/Morpho y rutas DEX con capital y salida en la misma cadena; medir captura y pujas en Flashblocks |
| Arbitrum One | Segunda evaluación, comparable con Base | Incluir prioridad PGA y coste de acceso a datos cuando corresponda; fijar el régimen histórico correcto |
| OP Mainnet | Siguiente candidata por reutilización | Adaptador propio de fees, despliegues, activos y ordenamiento; el núcleo común no prueba igualdad operativa |
| Linea | Evaluación selectiva | Demostrar financiación, actividad, salida y competencia; menor número de bots sigue sin evidencia |
| Orbit, incluyendo una posible evaluación de ApeChain | Selección por cadena concreta | Orbit es una tecnología, no una bolsa de liquidez única; cada cadena necesita identidad, gas y fuentes propios |
| Degen Chain | Observación condicionada a actividad económica verificable | DEGEN para gas, profundidad de salida y principal externo local; microtransacciones no equivalen a arbitrajes |
| zkLink Nova | Prioridad inferior para la tesis propuesta | Rechazar el supuesto de arbitraje atómico entre L2 distintas; evaluar sólo composiciones efectivamente financiadas dentro de una cadena |

## Correcciones verificadas

**Base.** La documentación oficial describe subastas de prioridad cada 200 ms,
con restricciones por llegada y orden ya fijado. Rust y Flashblocks no prueban
ventaja exclusiva ni captura. [Orden de transacciones](https://docs.base.org/specifications/transactions/transaction-ordering).

La página de [DefiLlama Base](https://defillama.com/chain/base), consultada en
esta investigación, mostraba USD 6.168 mil millones de TVL DeFi y USD 835.09
millones de volumen DEX de 24 horas. Son observaciones de un panel variable,
sin bloque fijado ni conciliación on-chain de NQC. No son capacidad flash,
profundidad ejecutable o ingreso capturable. La cifra propuesta de USD 6.4 mil
millones no se conserva como dato actual autenticado. TVL y TVS no se mezclan.

**Arbitrum One.** La guía oficial del 24 de septiembre de 2026 describe PGA
como sustituto de Timeboost. Fast Feed es observación temprana del orden ya
seleccionado y requiere un ticket; no permite adelantar esas transacciones.
Su coste no se presupone autorizado. [Guía oficial](https://blog.arbitrum.io/competing-for-transaction-priority-on-arbitrum/).
El estado/configuración y la fecha de activación deberán fijarse para cualquier
ventana de replay; una página actual no autentica el régimen de un bloque antiguo.

**OP Mainnet.** Comparte infraestructura reutilizable, pero la documentación
incluye gas de ejecución, datos L1 y comisión de operador. El modelo debe leer
los parámetros correspondientes a cada cadena y actualización.
[Fees](https://docs.optimism.io/op-stack/transactions/fees) y
[configurabilidad](https://specs.optimism.io/protocol/configurability.html).

**Orbit/Degen.** La tecnología permite gas configurable; no implica costes
universales ni principal disponible. Camelot documenta Degen como cadena Orbit
y el pago de gas en DEGEN. Esto exige autenticar saldo y coste de adquisición
dentro de la política acumulada; no se autorizan compras o puentes.
[Arbitrum chains](https://docs.arbitrum.io/launch-arbitrum-chain/overview/introduction) y
[Degen en Camelot](https://docs.camelot.exchange/orbital-liquidity-network/degen/).

**zkLink Nova.** Su propia introducción reconoce que la agregación sacrifica
interoperabilidad atómica entre rollups. Los activos depositados en Nova y
unificados allí no prueban una única transacción de préstamo, arbitraje y
repayment a través de varias L2. Se descarta esa premisa para NQC.
[Introducción](https://docs.zklink.io/) y
[token merge](https://docs.zklink.io/key-concepts/token-merge).

No se autenticaron afirmaciones de menor competencia en Linea, volumen rentable
recurrente en las L3, independencia de oportunidades, gas invariablemente
subcentavo ni ausencia de modificaciones por compartir EVM. Una lista de marcas
de protocolos tampoco demuestra que sus mercados estén activos o sean admisibles.

## Cómo comparar la expansión con Ethereum

Por cada ámbito fijado: enumerar mercados, posiciones y oportunidades; medir
financiación y repayment locales, compatibilidad y rutas a tamaños concretos;
reconstruir costes completos, frecuencia, vida útil y competencia. Conservar
rechazos, periodos vacíos e intentos fallidos. Separar rentabilidad condicional,
captura sustentada y P&L realizado. Medir el valor adicional para la cartera
después de conflictos compartidos, sin multiplicar la capacidad por el número
de redes o de rutas.

Un pico de volumen puede elevar la prioridad de observación; no autoriza
automáticamente trading. El criterio de activación deberá exigir estado válido,
capital externo, salida, coste total y controles aprobados. La expansión añade
necesidades de RPC, almacenamiento, sincronización, gas y validación; no se
presuponen servicios gratuitos o reinversión de utilidades.

La política MXN 2,000 acumulados sólo para gas permanece igual, sin principal,
colateral o garantías propios. No hubo barrido nuevo en estas redes, gasto,
contratación, firma, despliegue ni transmisión. Census Ethereum sigue abierto.

## Procedencia y límites de esta revisión

Las referencias son documentación de los proyectos/protocolos y un panel de
medición de su operador. Se conservan como fuentes de hipótesis, no como
testigos de RPC, bytecode, liquidez histórica ni ejecución. Una URL puede cambiar;
antes de admitir mercados se requieren capturas, hashes y bloques exactos.
La recuperación de una URL antigua de Base devolvió 404 y se resolvió con su
página oficial vigente. Una relectura adicional de documentación devolvió 503;
no produjo evidencia nueva ni invalida las lecturas previas exitosas.
