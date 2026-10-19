# NQC055 — Sovereign Opportunity Radar

**Radar offline funcional de selección investigadora. Ninguna oportunidad rentable
admitida.** El motor organiza 142 expedientes: 141 transacciones de la muestra
incompleta de Morpho más el caso A anterior. No son 142 oportunidades comerciales.

El resultado práctico nuevo es una prioridad **condicionada de adquisición de
evidencia**, distinta de B: una liquidación WETH/pufETH declarada en índice cero.
Su recibo archivado es `null`; no se conoce venta, gas, financiación ni beneficio.
La propuesta no autoriza adquirir datos ni presupone acceso a un proveedor.

Base exacta: `4f966154829f774ac00ff2854126e30ccb140299`.
Rama nueva: `research/nqc-055-sovereign-opportunity-radar-20261019`.
Se comprobó que no existía continuación de NQC054 antes de escribir; se agregan
solo archivos de este directorio. `commercial_admission=false`.

## Qué funciona

| Módulo | Función verificable |
|---|---|
| `core.py` | Fuentes por commit/blob/SHA256, punteros JSON, importes enteros con activo/cadena/decimales, intervalos de costes y registro de identidades |
| `morpho.py` | Único adaptador: normaliza observaciones archivadas, fusiona duplicados exactos y aplica los límites históricos de B |
| `radar.py` | Tres preguntas separadas, nueve criterios visibles, catálogo de requisitos, selección determinista y grupos de reutilización |
| `test_radar.py` | 35 pruebas de datos conservados y entradas adversarias; las entradas sintéticas solo prueban el programa |
| `run_checks.py` | Ejecuta pruebas, aislamiento y dos procesos independientes para comparar resultados byte por byte |

[summary.json](evidence/summary.json) contiene la lectura compacta;
[radar.json](evidence/radar.json) contiene cada expediente, decisión, sus fuentes y
hashes. [POLICY.md](POLICY.md) delimita el criterio de selección.
[ADAPTERS.md](ADAPTERS.md) especifica la extensión a otras familias, sin implementar
integraciones ficticias.

## Resultado de selección

| Grupo | Resultado |
|---|---|
| B, colateral primero | Referencia congelada: requiere evidencia nueva; no se reabre ni se admite como rentable |
| B, toda la deuda financiada a ≥1 bp | Escenario descartado con venta y puja observadas, incluso con gas cero |
| A | Evento y gas de indexador; requiere venta, financiación y evidencia específica |
| Otros 140 expedientes de la muestra | No evaluables económicamente con los datos actuales |

El radar localiza **cuatro** transacciones declaradas con `txIndex=0`. Bajo la
política estructural fijada, la propuesta de siguiente expediente es:

- Ethereum, chain ID 1, Morpho Blue; bloque **26104570**, índice reportado **0**.
- Transacción: `0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4`.
- Mercado: `0x0eed5a89c7d397d02fd0b9b8e42811ca67e50ed5aeaa4f22e506516c716cfbbf`.
- Deuda observada: **0,590976235877976338 WETH**.
- Colateral observado: **0,569144086683595914 pufETH**,
  contrato `0xd9a442856c234a39a81a089c06451ebaa4306a72`.
- Fuente original: commit `0f26557c1f83e12efcf364ece6cebd8505d2e2c2`,
  `migration/experiments/morpho-sponsored-gas/evidence/2026-10-17-monthly/page-000.json`,
  puntero `/response/data/marketTransactions/items/91`.

Los dos importes tienen activos distintos: **no se restan entre sí**. No se asigna
precio USD a ninguno. El deudor y la ruta de venta siguen desconocidos. Solo hay
un caso con este par en la muestra, por lo que tampoco acredita recurrencia.

Ventaja investigadora condicional: si se confirma el índice cero, se evita
reproducir transacciones ordinarias previas del bloque. Siguen siendo necesarios
estado del padre y transiciones de sistema. WETH permite estudiar una denominación
compatible con gas ETH cuando se justifique la conversión; no aporta liquidez,
patrocinio ni una venta de pufETH. B no comparte este mercado ni esta ruta.

## Experimento de valor

| Comprobación | Resultado y alcance |
|---|---|
| Normalización | 145 filas archivadas → 143 eventos únicos → 141 transacciones; A se agrega fuera de la ventana |
| Duplicados auténticos | 2: B y C aparecen también en el archivo de selección detallada; se fusionan sin sumar ingresos |
| Regresión de clasificación | 142/142 expedientes conservan ausencia de beneficio/admisión demostrados; no es precisión predictiva fuera de muestra |
| Rechazo conocido | Reproduce −754261612795662 wei como cota superior del escenario B de financiación ≥1 bp y gas cero |
| Falsas ganancias publicadas | 0 afirmaciones de beneficio neto capturado por NQC |
| Requisitos compartidos | 61 mercados y 54 pares contando A; agrupan esquemas de trabajo, no permiten copiar estado o márgenes |
| Selección nueva | Cuatro índices cero reportados; uno con deuda WETH; propuesta explícita con supuestos y datos faltantes |
| Determinismo | Dos procesos nuevos, semillas hash 1 y 55: salida idéntica byte por byte |

El valor frente a la revisión manual consiste en hacer esas reconciliaciones y
comprobaciones repetibles, mantener un expediente único por transacción y explicar
la siguiente solicitud de evidencia. **No se midió tiempo humano ahorrado ni una
mejora de precisión económica.** Las etiquetas de referencia vienen de NQC054;
no se presentan como validación independiente o etiquetas de entrenamiento.

**Resultado A:** implementado como selección investigadora, no como ranking de
rentabilidad. **Resultado B:** reproducción de un descarte previo, no descubrimiento
de otra estrategia inviable. **Resultado C:** persiste el límite: los archivos no
permiten escoger una oportunidad económicamente superior.

## Próximo experimento propuesto, no ejecutado

Primero, un paquete para la transacción seleccionada con pertenencia al bloque,
orden, recibo completo, traza completa y conciliación de deuda, colateral, venta,
gas y pagos de inclusión. Debe quedar ligada la procedencia a los bytes, contratos
y bloque correctos. La pertenencia declarada por un indexador no es prueba de orden.

Ese paquete permitiría una decisión barata **en dependencias**, no en precio
demostrado: si la venta menos deuda y costes conocidos tiene cota superior no
positiva, descartar esa ruta histórica antes de invertir en replay. Si conserva
margen, resolver después estado autenticado, financiación, obligaciones restantes
y condiciones de captura. Una cota positiva no demuestra beneficio realizable.

El coste monetario, horas, número de peticiones, disponibilidad del archivo y
valor económico esperado son `null`. La elección supone que evitar el prefijo
reduce trabajo y que comparar deuda WETH con gas ETH facilita la contabilidad.
No demuestra que sea el caso más barato o más rentable. El recibo previo fue
`null`: **no se ha reintentado** ni se propone eludir ese bloqueo. Cualquier
adquisición posterior necesitaría autorización explícita y una vía permitida.

## Límites y reproducción

18 fuentes se fijan y verifican en [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json):
datos originales Morpho, NQC053/NQC054 e instrucciones. Hash correcto significa
integridad del archivo preservado, no autenticación del estado de la cadena.
Los resultados heredados se consumen como dependencias; no se vuelven a ejecutar
los verificadores de trie, preestado ni suites anteriores sin cambios.

```sh
python migration/experiments/nqc-055-sovereign-opportunity-radar/run_checks.py
```

Requiere checkout completo con los commits fijados y Python 3.10 o posterior;
se ejecutó con Python 3.12.14 y biblioteca estándar, sin instalar dependencias.
La orden documenta reproducción para ejecutores técnicos; no exige terminal al
propietario que utiliza Android. Los hashes de entrega están en `SHA256SUMS`.

35 pruebas nuevas y 9 de aislamiento aprobadas; verificador de aislamiento PASS.
Cero pruebas fallidas u omitidas en las suites ejecutadas. No se ejecutaron
Rust/Solidity, replay EVM, RPC, estrategias ni operaciones financieras. El verificador
mantiene `original_objects_checked=false`; no se reclama recertificación histórica.

No hay pronóstico para USD 5000–45000 mensuales. Falta beneficio neto por captura,
financiación disponible, frecuencia capturable y costes recurrentes/fallos.
Triport: **0 de 8 acumuladas conocidas**, sin reinicio; canal seguro y registro
único siguen sin demostrarse. Blockscout/otros RPC: cero consultas nuevas.
Los límites futuros de gas (2000 MXN total, recargas 500, revisión al perder 1000
sin captura) se registran como política; no habilitan Canary ni fondos ahora.
No se inspeccionó ninguna cartera o secreto ni se implementó capacidad de gasto.
