# Selección de 12 candidatos y cobertura

Lock anterior al nuevo análisis individual, no estudio ciego: el caso B ya era conocido. El commit de selección fija hashes, reglas y salidas; no se sustituyeron transacciones por falta de datos. Se usa el censo guardado, no un barrido nuevo.

Universo: 143 eventos / 141 tx, 43 eventos de bad debt. Excluir cualquier tx con algún bad debt deja 98 tx; no 98 oportunidades económicamente admitidas. Bad debt no demuestra pérdidas del liquidador. El líder de 35 eventos concentra bad debt sNUSD; no se toma esa concentración como probabilidad de captura.

Orden: cuatro WETH sin bad debt por principal descendente; cuatro USDC por principal descendente dentro de USDC (elegido por mayor número de tx limpias, desempate por dirección); cuatro primeras tx de distintos activos restantes, orden cronológico. Principal no es incentivo ni beneficio. Activos diferentes nunca se suman para ordenar.

| Orden | Grupo / deuda | Transacción | Principal, unidades del token | Recibo guardado |
|---|---|---|---:|---|
| 1 | WETH_no_reported_bad_debt / WETH | `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b` | 26.039738525656992415 | RPC_API_EVENT_CROSSCHECK |
| 2 | WETH_no_reported_bad_debt / WETH | `0x485c12cd2cdf8768af3405d2aab0dbebe6d38e5b28615221913b751073e2bb9f` | 0.827768999713439745 | UNAVAILABLE |
| 3 | WETH_no_reported_bad_debt / WETH | `0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4` | 0.590976235877976338 | UNAVAILABLE |
| 4 | WETH_no_reported_bad_debt / WETH | `0x7f2a208841f2a9b51614d0c86a0420790a0c96a8c68473d474b592cf7442f530` | 0.000233990747116021 | UNAVAILABLE |
| 5 | largest_principal_same_asset / USDC | `0x6f35930cde64a17471a03f1580eb2a39911d7a273c15a36c444cb43fbc08da7b` | 60073.167740 | NOT_REQUESTED |
| 6 | largest_principal_same_asset / USDC | `0xead4476de6aa8922f1218fcd70eb86ce23400f04faf0568e9983b727bf8ce9a1` | 24289.049858 | NOT_REQUESTED |
| 7 | largest_principal_same_asset / USDC | `0x48afa385417269ae025aef266d0f4b8ae38b11c9cc39808b3a6e6e81ea68f355` | 18223.625301 | NOT_REQUESTED |
| 8 | largest_principal_same_asset / USDC | `0x444404d692c1e9c4e688cb0e0ee2637552a4fec472d662643fb6d9ff5e83dae9` | 6400.268378 | NOT_REQUESTED |
| 9 | other_asset_earliest_diversity / JPYR | `0x38d1030dbb93959ffc63d8663a6ac6a2c62b9d2f6f4311624f7a77a099453bff` | 575.820064 | UNAVAILABLE |
| 10 | other_asset_earliest_diversity / USDT | `0xccf5035c11493bc83cf3942aa126840f0e19f9a2f8270ada50c0e64d7d5b3133` | 32.649608 | UNAVAILABLE |
| 11 | other_asset_earliest_diversity / JPYC | `0x69067db0430e7bd2d7d580c3f00d10da174cee76717f949d1341e7a82cf7a13e` | 493.281274471133248431 | UNAVAILABLE |
| 12 | other_asset_earliest_diversity / msETH | `0xcef337c2375d51a445b2173db37700aea803ca23dfe929cdc4e6761d62ee4cf0` | 14.538288356343944934 | UNAVAILABLE |

Para los doce, API → observado. Solo B tiene recibo cruzado. Los campos posición/oracle/IRM → prestate → DEX en índice → P&L original completo → contrafactual NQC → financiación → sensibilidad auténtica → captura permanecen null. Hay siete recibos previos UNAVAILABLE y cuatro NOT_REQUESTED; la ausencia no se convierte en rentabilidad cero. Todos: **UNRATED_MISSING_WITNESS**. No se realizaron peticiones adicionales.

El símbolo no certifica compatibilidad. WETH evita una conversión adicional en ciertos caminos, pero sigue necesitando prestate y DEX. USDC/JPYR/USDT/JPYC/msETH requieren rutas y conversión de remuneración a ETH verificadas; el adapter V2 de este laboratorio no demuestra soporte de esos mercados históricos.

## Potencial mensual

**NO ESTIMABLE**: no hay una muestra de márgenes netos reproducidos ni probabilidad de captura observada. A: P&L propio certificado US$0. B: cero replays históricos NQC económicamente admitidos. C: solo sensibilidades de supuestos. D: expectativa mensual null. La frecuencia API no se transforma en frecuencia de oportunidades ganables.

Número mínimo de capturas para un objetivo, suponiendo explícitamente un neto por captura después de TODO coste variable y coste fijo mensual cero (cota inferior de requisitos, no previsión):

| Objetivo USD/mes | Neto supuesto US$10 | US$50 | US$100 | US$500 |
|---|---:|---:|---:|---:|
| 1,000 | 100 | 20 | 10 | 2 |
| 5,000 | 500 | 100 | 50 | 10 |
| 10,000 | 1,000 | 200 | 100 | 20 |
| 50,000 | 5,000 | 1,000 | 500 | 100 |

Fórmula exacta: ceil((objetivo + coste fijo mensual) / neto por captura). Los netos de esta tabla son hipótesis, no márgenes observados ni conversión de WETH a USD. Faltan precios ejecutables, financiación, cobertura de fallos, frecuencia elegible, intentos perdidos y competencia para investigar cualquiera de esos objetivos.
