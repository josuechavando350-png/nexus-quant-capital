# NQC - Auditoría independiente del censo y sus sesgos

**Directiva 002; corte documental: 17 de octubre de 2026.**

## Dictamen

Se recomputaron **143 eventos, 141 transacciones, 60 mercados y 49 direcciones de liquidador** en los JSON guardados de Morpho Ethereum. Estos conteos describen los registros devueltos por una API para una ventana fija de 30 días. No son 141 oportunidades disponibles para NQC, ni un censo universal de Ethereum. El número de operaciones capturables, financiadas y con beneficio neto permanece **DESCONOCIDO**; las certificaciones de capturas económicas de NQC en este expediente son **0**. [S-TM-001, S-TM-008 a 010, S-TM-034 a 037]

La contribución nueva es analítica: se verificaron los bytes de entrada, se reconstruyeron independientemente selección y denominadores, se cruzó el recibo guardado de B con sus cinco importes y se midió el efecto exacto de filtros. El script no importa ni ejecuta el analizador de Astra, no consulta la cadena y no reproduce otro fork.

**Hallazgo principal:** la dirección que lidera el censo con 35 eventos sólo aparece en 35 registros con bad debt, todos el 26 de septiembre y todos con colateral sNUSD. El ranking observado no puede convertirse directamente en un ranking de beneficios, competencia normal o velocidad. Esa fecha contiene 36 de los 43 eventos con bad debt de todo el mes. [Cálculo independiente sobre S-TM-008 a 010; `concentration_findings` en el JSON de resultados]

## 1. Autoridad y reproducibilidad

Fuentes fijadas a Morpho HEAD `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`. Los SHA Git y SHA-256 completos, URLs inmutables, momentos de recuperación y horas originales de observación están en `evidence/temporal_sources.json`. Un hash comprueba identidad de los bytes del expediente; no autentica por sí mismo un índice contra el estado de Ethereum.

El paquete contiene 46 JSON originales necesarios para el cálculo, **517006 bytes**, en `evidence/census_inputs/`, más su manifiesto. El recibo B procede de la captura anterior `2026-10-17T04:11:08.409531+00:00`; se reutilizó la copia del equipo y no se volvió a consultar el RPC. Las otras 22 respuestas de recibo ya estaban guardadas. [S-TM-011 a 032, S-TM-051]

Desde esta carpeta:

```sh
python3 census_audit.py
```

Opcionalmente se pueden indicar `--input-dir` y `--output`. La ejecución verifica hashes de todas las entradas, enteros exactos, ventanas, identidad de eventos, páginas opuestas, selección de recibos y consistencia del control positivo. Su salida 0 significa que la auditoría offline terminó; **no es autorización económica**. El comando, versión de Python, SHA del script, salida y código de terminación están en `evidence/census_execution.txt`. Los 12 grupos de comprobaciones son nuevos controles de esta auditoría; no incrementan ni recertifican las suites históricas 168/50/9.

## 2. Universo contado y límites de paginación

| Magnitud | 30 días: [17-sep, 17-oct) UTC | 7 días: [10-oct, 17-oct) UTC |
|---|---:|---:|
| Eventos | 143 | 29 |
| Transacciones distintas | 141 | 28 |
| Mercados distintos | 60 | 22 |
| Direcciones de liquidador | 49 | 16 |
| Direcciones de token de deuda | 15 | 5 |
| Direcciones de colateral | 48 | 18 |
| Eventos que reportan bad debt | 43 | 3 |
| Transacciones con algún evento de bad debt | 43 | 3 |

Fuente: recomputación de páginas directas, inversas y consulta separada de siete días. La clave de evento es `(chainId, txHash, logIndex)`, no sólo la transacción. La selección no contenía filtros de rentabilidad, token, monto, liquidador ni bad debt. Las dos ventanas se superponen: **no se suman** para obtener 172 observaciones independientes. [S-TM-008 a 010, S-TM-034 a 037]

Las páginas directas contienen 100, 43 y 0 registros. Las inversas contienen 100 y 43. Coinciden todos los eventos y su contenido, no sólo el total. El primer `countTotal` inverso es 143; el siguiente es 43 después de aplicar el cursor. Sumarlos contaría dos veces parte de la población. La consulta de siete días coincide exactamente con el subconjunto temporal del mes. Esto confirma consistencia interna y agotamiento de esa paginación. El proveedor sigue siendo el mismo en las tres lecturas; no hay tres fuentes independientes.

El control `eth_getLogs` guardado devolvió HTTP 200 y `[]` para el bloque, dirección Morpho y topic que contienen el evento B en el recibo guardado. La auditoría comprueba offline que el filtro cubre ese evento. Estado: **KNOWN_POSITIVE_OMISSION_OR_CONFLICT**. No distingue si la causa fue omisión, comportamiento del proveedor o un conflicto entre observaciones. Sí impide usar ese resultado vacío como certificación de completitud. [S-TM-006, S-TM-051]

La documentación actual de Morpho describe una API sin SLA garantizado; ese hecho no cuantifica el retraso de estas respuestas ni demuestra la causa del conflicto. [S-TM-058]

## 3. Concentración por activos y por dirección

| Token de deuda, etiqueta del proveedor | Eventos | Con bad debt |
|---|---:|---:|
| USDC | 94 | 40 |
| RLUSD | 9 | 0 |
| USDT | 9 | 1 |
| msETH | 7 | 0 |
| WETH | 7 | 1 |
| JPYR | 4 | 0 |
| AUSD | 3 | 0 |
| WBTC | 2 | 0 |
| DAI | 2 | 0 |
| EURCV | 1 | 0 |
| PYUSD | 1 | 0 |
| eUSD | 1 | 1 |
| frxUSD | 1 | 0 |
| USDS | 1 | 0 |
| JPYC | 1 | 0 |
| **Total** | **143** | **43** |

Los cálculos agrupan por dirección del token y verifican coherencia de decimales. El ticker sólo facilita la lectura; las direcciones completas, sumas de principal en unidades nativas y metadatos se conservan en `windows.30d.debt_assets`. No se suman tokens heterogéneos, no se supone paridad con USD y no se transforma principal repagado en ingreso. [S-TM-008 a 010]

USDC concentra 94/143 registros, aproximadamente 65.7%. La deuda WETH representa 7/143; quitar el único WETH con bad debt deja seis registros. Ninguna de esas dos cantidades prueba compatibilidad con la ruta NQC, liquidez real de salida, capital de gas o acceso a tiempo.

| Dirección observada | Eventos | Eventos con bad debt |
|---|---:|---:|
| `0xe683b8ee2710eabcbf347b7cb0735cda11ef31ba` | 35 | 35 |
| `0x00acd5005200e7009beb000000e35e1e002b5565` | 15 | 3 |
| `0x928def5fdffbd95dae449d7a3f35f05ffdb54960` | 7 | 0 |
| `0xfe1dcc4db359b161f9042e99c3b481a50f73dec1` | 6 | 0 |

Las dos primeras reúnen 50/143 eventos, aproximadamente 35.0%. Una dirección no equivale necesariamente a una empresa, y una empresa puede operar varias direcciones. No hay denominador de pujas perdidas ni medición de la primera recepción de estos actores.

La sensibilidad temporal es especialmente material: el 26-sep aporta 36/143 eventos y 36/43 bad debt, aproximadamente 83.7% de todos los eventos con bad debt. Los 35 eventos del líder corresponden a sNUSD, dirección de colateral `0x08efcc2f3e61185d0ea7f8830b3fec9bfa2ee313`. Al retirar esa fecha sólo como análisis de sensibilidad quedan 107 eventos/105 transacciones y siete eventos con bad debt. No se recomienda ocultar ese día; se muestra por qué una media mensual o una tasa de competencia uniforme sería frágil. [Cálculo independiente sobre S-TM-008 a 010]

Los días 18-sep, 22-sep, 03-oct y 09-oct no contienen registros en las respuestas. El 15-oct concentra 15 de los 29 eventos de la ventana corta. Son ceros y concentraciones del proveedor, con cobertura no certificada; no se ajustó un proceso probabilístico ni se derivaron intervalos de confianza.

## 4. La unidad de filtrado cambia el denominador

| Regla aplicada al mismo conjunto | Eventos restantes | Transacciones distintas | Eventos con bad debt |
|---|---:|---:|---:|
| Conservar todo | 143 | 141 | 43 |
| Quitar sólo eventos que reportan bad debt | 100 | 99 | 0 |
| Quitar transacciones completas con algún bad debt | 99 | 98 | 0 |
| Sólo deuda WETH | 7 | 7 | 1 |
| WETH y sin bad debt reportado | 6 | 6 | 0 |
| Selección diagnóstica de recibos | 25 | 23 | 3 |

La diferencia 99 frente a 98 transacciones no es un error de redondeo. Una transacción contiene un evento con bad debt y otro sin él. Filtrar eventos conserva parte de esa misma ejecución. El gas y las obligaciones financieras siguen perteneciendo a la transacción completa. [Cálculo de `filter_sensitivity`]

Las dos transacciones multievento son:

- `0x5af6cc4bcec812d636eabb9cd11d2d676c55fb277bd9de1a75bbaeff20bab94b`: dos eventos sin bad debt en el mismo mercado; no son dos costes de gas independientes.
- `0x430f18682beba3cdf16305aa1f18e9f23ae42eb2294d0897b3ef4f0404e18f7e`: dos mercados; un evento con bad debt y otro sin él.

Un evento que reporta bad debt no queda etiquetado automáticamente como pérdida del liquidador. Tampoco se considera rentable por ausencia de bad debt. Faltan el estado, las rutas, los pagos, las relaciones de financiación y la consolidación del operador. Los filtros anteriores son sensibilidades del censo, no un clasificador de negocios buenos o malos.

## 5. Recibos: 22 nulos no son 22 pérdidas

La selección se reconstruyó sin usar los resultados de recibos: primera observación cronológica por token de deuda, todas las transacciones con deuda WETH y ambas transacciones multievento. La unión contiene 23 transacciones y 25 eventos; sólo tres eventos reportan bad debt. Esta composición difiere del conjunto completo y no constituye muestreo aleatorio de beneficios. [S-TM-033]

| Estado del expediente de recibos | Transacciones | Interpretación válida |
|---|---:|---|
| Recibo B previamente guardado y cotejado | 1 | Gas y evento corroborados entre esos archivos |
| Consultas nuevas guardadas con `result: null` | 22 | Respuesta sin recibo; ejecución, coste y causa siguen desconocidos |
| Fuera de la selección diagnóstica | 118 | No evaluadas mediante este diagnóstico; no se presume que el recibo sea inaccesible |
| Total de transacciones observadas | 141 | No es denominador de victoria NQC |

Los 22 nulos son 22/23 de la selección y 22/22 de las consultas nuevas. Es incorrecto decir que el 95.7% de todas las liquidaciones fracasó, o extrapolar indisponibilidad del proveedor al resto del mes. Un HTTP 200 no garantiza contenido útil. Tampoco se asigna gas cero a los nulos. [S-TM-011 a 032]

Para B, el cotejo nuevo encuentra una liquidación, el mismo mercado/dirección/logIndex y los cinco valores ABI esperados. El recibo guarda 745509 unidades de gas y precio efectivo 266148625 wei por gas: coste aritmético 198416195275125 wei. Ese recibo sigue sin aportar el estado previo completo, factura externa del operador, pujas perdidas ni beneficio NQC. [S-TM-051; `diagnostic_receipts`]

## 6. Sesgos que faltan por resolver

| Sesgo o hueco | Efecto sobre una estimación de ingresos | Evidencia correctiva necesaria |
|---|---|---|
| Ganadores elegidos retrospectivamente | Muestra condiciones que llegaron a ejecutarse; omite lo que NQC habría conocido antes | Selección de universo y decisiones registradas antes de los resultados |
| Supervivencia y logs de ejecuciones exitosas | Los reverts sin evento de liquidación desaparecen del subconjunto | Registro de intentos, rechazos, reverts y costes incluidos |
| Mismo indexador en varias consultas | Concordancia interna puede repetir la misma omisión | Control de cobertura contra una autoridad independiente, con fallos visibles |
| Retardo o censura del proveedor | Convierte ausencia de respuesta en falsa ausencia de oportunidad | Horas originales, retrasos/censura medidos, respuestas nulas preservadas |
| Incompatibilidad de activo o DEX | Confunde eventos económicos con rutas ejecutables | Contratos, parámetros y liquidez de conversión en el mismo estado |
| Estado que cambia dentro del bloque | Usa valores posteriores o mezcla prefijos | Testigo anterior y efectos de las transacciones previas |
| Flujo privado y acuerdos con builders | No observa igualdad de acceso a la información ni al orden | Pruebas de acceso y admisión del candidato concreto |
| Identidad por dirección | Sobreestima o subestima número de empresas rivales | Atribución acreditada; mantener direcciones si no existe |
| Gas, propinas y financiación ausentes | Trata un margen bruto como ingreso disponible | Libro por contraparte y por activo, incluidos fallos y obligaciones externas |
| Ventana corta y concentración episódica | Proyecta una frecuencia constante no demostrada | Varias ventanas fijadas por adelantado, sin elegir después la favorable |

Estos efectos identifican por qué faltan inferencias; no se les asigna una magnitud inventada ni un signo universal sobre el beneficio. [S-TM-004; análisis independiente]

## 7. Embudo obligatorio de seis capas

| Capa | Medición en este expediente Morpho | Operaciones NQC certificadas |
|---|---|---:|
| 1. Eventos observados | 143 eventos / 141 transacciones API | No equivale a admisión |
| 2. Estados auténticos reproducidos | DESCONOCIDO en la población | 0 |
| 3. Rutas ejecutables desde esos estados | DESCONOCIDO | 0 |
| 4. P&L completo positivo | DESCONOCIDO | 0 |
| 5. Financiación sin recurso al fundador | DESCONOCIDO | 0 |
| 6. Acceso previo e inclusión ganable | DESCONOCIDO | 0 |

**Cero certificaciones no significa cero oportunidades reales.** Significa que no hay ninguna cadena de evidencia que atraviese las seis capas para NQC. Los éxitos sintéticos de contratos, la frecuencia API y el resultado de un tercero no sustituyen capas faltantes. El embudo de Morpho no recertifica ni reclasifica las simulaciones históricas separadas de Aave o Robinhood. [S-TM-001 a 005]

## 8. Cotas optimistas: únicamente pruebas condicionales

Para un conjunto cerrado de transacciones observadas, supóngase que cada una admite a lo sumo una captura independiente de NQC y que `u_i` es una cota superior **demostrada** de su margen neto. Con costes fijos `F` y pérdidas inevitables `L`, sería necesario:

`objetivo <= suma(max(0, u_i)) - F - L`.

Sin cotas `u_i`, el número 141 no acota el dinero. Como ejercicio explícitamente hipotético, si cada una de esas 141 transacciones estuviera limitada a USD 100 netos, se pudiera ganar el 100% y `F=L=0`, el máximo del conjunto sería USD 14100. Bajo esas premisas, USD 50000 sería imposible para ese conjunto. No demuestra un techo del protocolo, del mes siguiente ni de otras estrategias.

La sensibilidad al filtrado es concreta: con la misma hipótesis de USD 100 máximos por transacción y excluyendo transacciones completas con cualquier bad debt, 98 transacciones permitirían como máximo USD 9800. Excluir sólo eventos dejaría 99 transacciones y USD 9900, pero conserva el riesgo de la transacción mixta. No se ha demostrado que esos filtros sean económicamente correctos ni que USD 100 sea una cota real.

No se ha estimado una probabilidad de ganar. Su denominador exigiría oportunidades elegibles conocidas a tiempo y ofertas perdidas registradas. Dividir una captura hipotética entre 141 liquidaciones de terceros no produce una tasa de victoria.

## 9. Próxima prueba que cambia el diagnóstico

Para mejorar este censo hace falta una autoridad de cobertura que pase un control positivo conocido y devuelva estados/recibos coherentes de una selección predefinida, incluidos los faltantes. Para estimar ingresos, además hace falta atravesar el embudo con decisiones tomadas antes del resultado y financiación sin recurso documentada. El protocolo temporal propuesto se detalla en `TEMPORAL_COMPETITION_AUDIT.md`; no hay un monitor permanente activo.

El resultado entregado permite detectar extrapolaciones inválidas hoy y volver a calcularlas con entradas nuevas identificadas por hash. Mantiene **DESCONOCIDO** donde la evidencia todavía no responde.

## Referencias

Los identificadores S-TM remiten al ledger verificable `evidence/temporal_sources.json`. Fuentes de mayor relevancia:

- [S-TM-004: MONTHLY_POTENTIAL, Morpho HEAD fijado](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/MONTHLY_POTENTIAL.md).
- [S-TM-036: selección de la ventana](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-monthly/selection.json).
- [S-TM-006: respuesta guardada del control positivo](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-monthly/b-morpho-logs.json).
- [S-TM-051: recibo B guardado](https://github.com/josuechavando350-png/nexus-quant-capital/blob/0f26557c1f83e12efcf364ece6cebd8505d2e2c2/migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-profitability/b-receipt.json).
- [S-TM-058: documentación oficial de la API Morpho](https://docs.morpho.org/developers/api/get-started/).
