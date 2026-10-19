# NQC054 — decisión económica y límite del preestado Morpho

**Resultado: `EVIDENCIA_INSUFICIENTE` para B y para admitir cualquier captura de NQC.**
Se descarta un escenario concreto: financiar toda la deuda de B con prima **≥1 bp
(0,01%)**, conservando venta y pago a coinbase observados, pierde dinero **incluso
con gas cero**. No se justifica seguir optimizando gas para ese escenario.
La ruta que recibe primero el colateral no queda descartada, pero carece de
preestado verificable, financiación del gas y evidencia de captura para NQC.
`commercial_admission=false`.

## Entrega y reproducción

- Base exacta: `014850d71b45d8a18eedfcc14b922fa51efb7512` (NQC053).
- Rama nueva: `research/nqc-054-morpho-prestate-economic-decision-20261019`.
- Original Morpho: `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`, rama
  `research/morpho-sponsored-gas-20261016`.
- Se agregan exclusivamente archivos de este experimento; no se ejecuta ningún
  colector de datos de los expedientes originales.
- [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) fija commit, ruta, blob Git y SHA256
  de 115 entradas: los 109 JSON/JSON.gz del expediente original y seis fuentes
  auxiliares de código, resultados y condiciones de patrocinio ya conservadas.
  Los documentos de orientación originales no se reinterpretan como pruebas de estado.
- [audit.py](audit.py) lee objetos Git inmutables y rechaza discrepancias de hash,
  cadena, identidades de mercado y árbol de llamadas incompleto. No contiene RPC.
- [evidence/audit.json](evidence/audit.json) contiene resultados, direcciones, slots,
  rutas de llamadas y la clasificación individual de las 141 transacciones.
- [VALIDATION.json](VALIDATION.json) y los logs contienen órdenes, versiones,
  salidas y conteos. [SHA256SUMS](SHA256SUMS) permite comprobar los entregables.

En un checkout completo con Python y `pycryptodome==4.0.1` ya disponibles:

```sh
python migration/experiments/nqc-054-morpho-prestate-economic-decision/run_checks.py
```

El análisis es offline; requiere disponer de los objetos Git de los commits
fijados. Se ejecutó en este entorno, sin pedir al propietario que use terminal o
instale dependencias. La orden no es una solicitud de acciones para Android.
La primera validación global falló por un pin preparado erróneamente como 3.23.0;
las 19 pruebas nuevas y las 9 de aislamiento aprobaron también en esa ejecución.
Se conserva `evidence/initial-version-mismatch.json` y sus logs iniciales. Se corrigió
el pin a la distribución realmente instalada (4.0.1), sin instalar ni alterar dependencias.

## Qué se obtuvo de nuevo

1. Se separan **47 destinos de código** y **28 contextos de almacenamiento** en
   158 llamadas de B. `DELEGATECALL` conserva el almacenamiento del llamador:
   contar implementaciones como cuentas de storage produciría un witness falso.
   El inventario total contiene **50 cuentas** observadas o participantes del prefijo,
   no 50 contratos ni un conjunto completo de accesos de estado.
2. Se derivan **10 slots Morpho** y se identifican **4 slots Fluid Liquidity** con
   claves exactas. Sus valores autenticados permanecen `null`. Los valores leídos
   dentro de B y los parámetros de calldata no se convierten en preestado.
3. El gas del prefijo tx0 se infiere en **243495** a partir del recibo acumulado
   de B. Esto no recupera su status, logs, accesos o cambios de estado.
4. Se demuestra el descarte por cota superior con gas cero; también se cuantifica
   la reducción de puja necesaria para duplicar el residuo, sin asumir inclusión.
5. La lectura histórica de allowance de WETH a Morpho devuelve `2**256-1`.
   El coste de B corresponde a un ejecutor ya configurado; no acredita el coste
   de preparar un ejecutor nuevo de NQC.
6. Se integra el recibo separado de C con la selección mensual: **1 disponible,
   23 respuestas `null`, 117 sin recibo archivado identificado**. C ya forma parte
   de las 141 transacciones: no se agrega como una oportunidad número 142.

No son nuevas observaciones de mercado ni nuevas ganancias. Son deducciones
reproducibles de archivos conservados. No se repite el verificador anterior del
trie de transacciones ni la conciliación económica de NQC053: se conservan sus
resultados e identidades exactas como dependencias explícitas.

## Preestado y replay

Ethereum mainnet, chain ID 1; Morpho Blue. B es
`0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`,
bloque **26190955**, índice **1**. No es Robinhood Chain.
El padre es **26190954**, raíz
`0xd1e393e15a1b2cbf4111ade0819b713b3cd7fe2237553013c12efa2765f6cdae`.

Antes de B hay que aplicar las transiciones de sistema pertinentes a la
configuración Ethereum de ese bloque y ejecutar tx0:
`0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`.
Va de `0x5875db54cd9ae2b2a875e09bb731772297ae9d92` a
`0x0000000aa232009084bd71a5797d089aa4edfad4`, selector `0x09c5eabe`,
740 bytes de calldata y límite de gas 449696. Su recibo archivado es `null`;
no se dispone de traza ni diff. No se presupone que sus efectos sean disjuntos.

[PRESTATE_REQUIREMENTS.md](PRESTATE_REQUIREMENTS.md) especifica cuentas, slots,
código, pruebas y configuración ausentes. **No se intentó un replay EVM**:
faltan entradas obligatorias. No hubo replay fallido ni exitoso, ni relleno con
ceros, estado posterior o estado de otra cadena/mercado. La exploración de 109
JSON/JSON.gz no encontró claves `accountProof`, `storageProof`, `structLogs` o
`prestate`; es un inventario, no un verificador de pruebas ni garantía de que una
búsqueda por marcadores detecte todo contenido anidado o serializado como texto.

## Economía: hechos, límites y condiciones

La conciliación archivada de NQC053 se mantiene como entrada fijada:

| Concepto | Cantidad observada |
|---|---:|
| Colateral recibido | 24,343983926960874121 ezETH |
| Deuda repagada | 26,039738525656992415 WETH |
| Salida de venta | 26,409680973611000000 ETH |
| Venta menos deuda | 0,369942447954007585 ETH |
| Transferencia a coinbase | 0,368092735714237547 ETH |
| Gas pagado | 0,000198416195275125 ETH |
| Residuo máximo antes de obligaciones desconocidas | 0,001651296044494913 ETH |

La venta pasó por el pool Fluid `0xdd72157a021804141817d46d9852a97addfb9f59`
y Liquidity `0x52aa899454998be5b000ad077a46bbe360f4e497`. Se observa el fill
histórico; faltan reservas y límites autenticados para verificar una cotización
anterior o una venta alternativa. El resultado de venta ya incorpora efectos de
la ruta: no se vuelven a restar spread, impacto o comisión del venue.

Con la venta y puja observadas, retirar **todo** el gas aumentaría el residuo
como máximo en 0,000198416195275125 ETH (aproximadamente 12,02%). Es una cota,
no una implementación posible. La cota resultante sería 0,001849712239770038 ETH.
Sobre toda la deuda, una prima de 1 bp redondeada hacia arriba cuesta
0,002603973852565700 ETH: resultado **−0,000754261612795662 ETH aun con gas cero**.
Con gas histórico: **−0,000952677808070787 ETH**. Costes adicionales no negativos
solo empeoran ese escenario. **`ECONOMICAMENTE_DESCARTADO` dentro de ese alcance.**
No se afirma que 1 bp sea una oferta real o el mínimo del mercado.

La llamada observada y la fuente Morpho permiten entregar colateral antes del
repago mediante callback. Esa ruta puede evitar pedir prestado el principal
completo. El préstamo externo de toda la deuda no es una obligación inevitable
de Morpho. Aun sin esa prima, un residuo positivo no acredita beneficio de NQC:

- Gas real: 745509 unidades; el remitente pagó el gas observado. El producto
  `gasLimit * maxFeePerGas` de B es **0,000712093319398500 ETH**; es un límite
  nominal de la transacción, no una lectura de saldo ni un compromiso de sponsor.
- Se observan 0,006392502690919791 WETH previos dentro del ejecutor y allowance
  máxima. No se acreditan propiedad consolidada, saldo histórico del remitente,
  coste de despliegue/aprobación de NQC o necesidad exacta de ese saldo previo.
- No existe compromiso verificable de patrocinio, tarifa, condiciones de devolución
  o responsabilidad por fallos para NQC. Las simulaciones Titan archivadas en
  chain 31337 con fondos artificiales no ofrecen tal financiación.
- Comisiones de financiación, obligaciones externas, pagos fuera de la traza,
  costes operativos y frecuencia/coste de intentos fallidos siguen desconocidos.

Duplicar el residuo conservando venta y gas exigiría reducir la transferencia
a coinbase en **0,001651296044494913 ETH**, dejándola en
**0,366441439669742634 ETH**. No hay pujas rivales, aceptación del builder o
probabilidad de captura que justifiquen esa reducción. Conservar el pago entero
como ingreso de NQC no es una mejora acreditada. Tampoco se demuestra que una
ruta de venta distinta o un ejecutor nuevo obtengan más que el residuo observado.

## Otros candidatos y decisión de detener

| Candidato | Calidad de evidencia | Decisión y bloqueo |
|---|---|---|
| B | Recibo y traza completos; máximo detalle económico | `EVIDENCIA_INSUFICIENTE`: preestado, financiación y captura |
| A, bloque 25402186, índice 226 | Transacción y bloque completos, datos de evento/indexador | `EVIDENCIA_INSUFICIENTE`: sin libro de venta/financiación; requiere 226 transacciones previas |
| C, bloque 26189539, índice 222 | Evento con deuda USDT 513394 unidades y colateral wstETH 171268871993022 unidades; recibo `null` | `EVIDENCIA_INSUFICIENTE`: deuda pequeña no prueba que los costes superen el ingreso |
| Otras filas de la muestra | Eventos/identidades; sin conciliación completa | `EVIDENCIA_INSUFICIENTE`: faltan venta, gas, puja y financiación |

La identidad, activos, mercados e importes crudos de cada fila están en el JSON.
La clasificación por calidad de evidencia no es una clasificación por margen:
este último es desconocido para las alternativas. La muestra diagnóstica de
143 eventos/141 transacciones tiene cobertura incompleta; no representa 141
oportunidades rentables o capturables. La investigación adicional con esos mismos
archivos se detiene: no hay otro candidato con contabilidad suficiente para una
decisión económica positiva o negativa. No se solicitan recibos ni se repiten RPC.

## Metas mensuales: criterios de evidencia, sin pronóstico

Beneficio neto capturado por NQC: **no demostrado**. Frecuencia capturable:
**desconocida**. Los 143 eventos son observaciones, no ganancias. No se utiliza una
cotización USD inventada ni se repiten los escenarios numéricos de NQC053.

Para cada meta `T`, capturas necesarias = `ceil((T + costes mensuales y fallos) / n)`
si `n` es un beneficio neto positivo en USD por captura realmente acreditado.
Faltan tanto `n` como los costes y la tasa de captura. Con márgenes heterogéneos
hay que sumar los resultados netos de cada captura, no imponer un promedio supuesto.

| Meta mensual | Evidencia necesaria antes de sostenerla |
|---|---|
| USD 5000 | Una ruta autenticada con financiación disponible, beneficio neto y captura competitiva; después medir volumen elegible, éxitos, fallos y costes en varias ventanas |
| USD 15000 | Lo anterior más capacidad adicional de liquidez, financiación concurrente y oportunidades marginales; no multiplicar por tres el caso B |
| USD 45000 | Evidencia de escala tras las etapas anteriores: deterioro de margen/competencia, capacidad real del sponsor y costes recurrentes; no extrapolar una muestra incompleta |

Escalar sin capital inicial exige que un tercero cubra gas y preparación bajo
términos explícitos y financiables. El reciclaje atómico del colateral no resuelve
por sí solo ese adelanto ni las pérdidas de intentos fallidos.

## Seguridad y siguiente movimiento

Triport: **0 nuevas, 0 conocidas acumuladas de 8 totales**. Presupuesto único sin
reinicio. Canal de credencial y autoridad durable única siguen **no demostrados**,
según NQC053. No se inspecciona, solicita ni usa una credencial en este experimento.
No se modifica el registro ni se repiten sus pruebas: no hubo cambios.
Blockscout y otros proveedores: **0 consultas nuevas**. Cero operaciones financieras.

El siguiente movimiento de mayor impacto es obtener, mediante una vía de evidencia
expresamente autorizada, un paquete Ethereum de estado del padre y ejecución de tx0
que satisfaga el inventario, junto con condiciones reales de adelanto de gas y
captura para la ruta de colateral primero. **No está autorizado ni se ha iniciado
ese acceso en NQC054.** Si no pueden conseguirse ambas clases de evidencia, B no
justifica más optimización y se debe buscar un candidato con expediente económico
completo, no construir más infraestructura genérica.
