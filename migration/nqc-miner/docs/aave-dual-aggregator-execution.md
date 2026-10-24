# DualAggregator observado en la ruta WETH

La composición ejecuta ahora AaveOracle → EACAggregatorProxy → DualAggregator
con sus runtimes observados. El agregado WETH
`0x7c7fdfca295a787ded12bb5c1a49a8d2cc20e3f8` deja de ser un doble en el ejemplo de
liquidación. La fuente USDC, el resto del estado de liquidación y la entrada Pool
siguen siendo artificiales. No se certifica una liquidación histórica completa.

## Identidad reproducible

Las 23 fuentes literales publicadas se recompilan sin cambios mediante Solidity
0.8.24, optimizer 1000000 y objetivo Cancun, conservando los ajustes originales.
Diez posiciones de cinco inmutables se rellenan exclusivamente donde lo declara
el compilador. Cada aparición de un mismo inmutable debe concordar; rangos
solapados, fuera de límites o placeholders no nulos se rechazan.

Los **23186 bytes completos** coinciden con el bytecode publicado y con los dos
proveedores en los tres bloques retenidos. Incluyen la metadata disponible. El
contrato se compiló con `bytecodeHash: none`: esa metadata no vincula el texto
original de las fuentes. Se acredita equivalencia de runtime, no unicidad o
autenticación del texto original ni una prueba canónica de código/estado.

El proxy secundario inmutable es `0x5424384b256154046e9667ddfaaa5e550145215e` y el
límite de búsqueda es 20. Los getters minAnswer/maxAnswer/decimals se contrastan
con los valores inmutables. El layout del compilador fija:

| Storage | Contenido usado |
| --- | --- |
| Slot 13, bits 48–79 | Última ronda del agregado |
| Slot 13, bits 80–111 | Última ronda secundaria |
| Slot 13, bits 240–247 | Indicador de último reporte secundario |
| Slot 18, bits 0–31 | Cutoff en segundos |
| Mapping en slot 17 | int192 de respuesta, uint32 de observación y uint32 de registro |

Las claves del mapping usan Keccak Ethereum, no SHA3-256. El helper Python de dos
palabras ABI se contrasta con Alloy en 37 vectores y en todas las claves capturadas.

## Captura y reproducción de precios

La captura completa realiza **222 lecturas RPC** individuales, agrupadas en 30
etapas, con máximo cuatro conexiones y separación de inicio de al menos 125 ms.
Se conservan 20 transmisiones por bloque y proveedor. Código, slots y getters
usan EIP-1898 por hash con `requireCanonical=true`; cadena, finalización y
cabeceras se verifican antes y después. Los dos proveedores concuerdan y cada
solicitud/respuesta normalizada se reproduce offline. No se agregan liquidaciones.

El primer intento envió cuatro solicitudes JSON-RPC en un único lote HTTP; el
endpoint devolvió HTTP 500. Se conservan script, contador y fallo. La captura se
repitió mediante solicitudes individuales acotadas. En total se enviaron 226
solicitudes JSON-RPC dentro de 223 solicitudes HTTP; las cuatro iniciales no
obtuvieron respuestas individuales. No se atribuye su ejecución al proveedor.

| Bloque | Ronda directa / precio | Ronda del proxy / precio |
| --- | --- | --- |
| 26248075 | 25161 / 240275000000 | 25161 / 240275000000 |
| 26248113 | 25162 / 240029113527 | 25162 / 240029113527 |
| 26248378 | 25163 / 239563000000 | 25162 / 240029113527 |

El cutoff observado es 60 segundos. En el tercer bloque, la ronda 25163 se
registró en el propio timestamp del bloque. La búsqueda desde el proxy descarta
esa ronda por el cutoff y devuelve la 25162. La captura conserva slots y las
cinco palabras de `latestRoundData()` para ambos llamantes.

Nueve ejemplos locales reproducen, para los tres bloques, la consulta directa al
agregado, la consulta al proxy con los IDs de fase y `getAssetPrice(WETH)` a través
de AaveOracle. Se utilizan los slots y el timestamp observados, conservando un
entorno `synthetic_fixture`: balances/nonce del llamante, state root, tarifas y
fork no se autentican. El sandbox sigue en Cancun. No son transacciones históricas
reconstruidas, pruebas de inclusión ni preestado intrabloque certificado.

## Selección de rondas y límites

El proxy secundario conserva su ronda cuando `recordedTimestamp + cutoff >= now`.
Si esa suma es menor, busca desde la última ronda y visita como máximo 20 entradas.
Si ninguna cumple, devuelve la última secundaria. Para otro llamante, un reporte
secundario de la ronda actual registrado en el mismo bloque puede devolver la
ronda anterior. Se ejecuta el código original de estas ramas, incluidas las
operaciones uint32 verificadas de Solidity.

**El cutoff no certifica frescura.** La selección puede devolver una ronda antigua
y no impone una antigüedad máxima de la observación. Las pruebas no convierten
esta lógica en una política de precios frescos ni autentican el origen del reporte.

Se prueban igualdad y lados del cutoff; primera y vigésima ronda; exclusión de la
vigésima primera; búsqueda sin coincidencia; ronda cero; filtro primario dentro
del mismo bloque; sign extension de int192 y fallback para cero/negativos;
overflow temporal; testigos faltantes; control de acceso del proxy; y rollback
tardío USDC. Las dos rutas de liquidación conservan las 47 palabras de resultado,
eventos y cambios de storage frente a la composición previa y sus modelos enteros.

La muestra de liquidación sigue usando precios artificiales y reservas artificiales.
El alcance cubre lectura de precio y ronda actual; no certifica publicación de
reportes OCR, firmas, billing, propietarios, upgrades o historial de rondas.

## Reproducir y continuar

```bash
python3 research/build_aave_dual_aggregator_execution.py \
  --compiler /ruta/solc-0.8.24 --output /ruta/nueva/compilacion
cargo test --locked --offline --test aave_debt_execution_tests aave_dual_aggregator_execution
NQC_MINER_TEST_BINARY=/ruta/nqc-miner python3 -m unittest discover \
  -s research -p test_aave_dual_aggregator_execution.py
```

`NQC_MINER_DUAL_EVIDENCE_DIR` exporta los dos ejemplos de liquidación y
`NQC_MINER_DUAL_OBSERVED_DIR` las nueve lecturas con slots observados. Cada destino
debe ser nuevo. Compilación y pruebas usan evidencia retenida, sin RPC público.

Siguen pendientes la fuente USDC, autenticación de rondas/preestado/fork y frescura,
entrada Pool real, más reservas, mismo activo/multirreserva, metadata de los tokens
WETH/USDC, Foundry e integración operacional. **43/100**, sin nuevo crédito de fase.
Gas exclusivo de Titan, cero gas propio/prefund/fallback y cero principal,
colateral, garantía o recurso al operador. Sin gasto, firma, broadcast o despliegue.
