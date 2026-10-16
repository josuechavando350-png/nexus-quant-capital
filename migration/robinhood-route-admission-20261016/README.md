# NQC: ruta real, admisión y corrección de gas — 2026-10-16

**Resultado: evidencia histórica útil y reproducible; monetización NQC todavía no demostrada.**
Esta continuación parte del commit `1c912476c6e0179a84e301ca708736e6e250a446`
y añade investigación aislada. No modifica los archivos históricos ni el trabajo
anterior. No habilita workflows ni ejecuta transacciones en una red real.

## Qué quedó comprobado

Se conciliaron los 22 recibos Robinhood del artefacto original, conservando sus
bytes y manifiesto. La muestra contiene 12 casos sistemáticos, 6 seleccionados
por tamaño fuera del top 3 y 4 por tamaño dentro del top 3. No representa una
muestra aleatoria de rentabilidad ni demuestra oportunidades capturables por NQC.

El caso reconstruido es
[`0xf9e0d2e…1974842`](https://explorer.chain.robinhood.com/tx/0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842),
bloque **66.744.162**, 19 de septiembre de 2026. El explorador independiente
coincide con los diez transfers, el bloque, el pagador y la comisión del recibo.
Los parámetros históricos de Morpho identifican USDG/wsNET, el oracle, IRM y
LLTV `0.625`. Las direcciones completas están en `route_audit.py` y el informe.

| Paso observado | Cantidad |
|---|---:|
| Colateral recibido y quemado | 0.093436250743843184 wsNET |
| Desempaquetado y unstaking | 0.308856441 sNET → 0.308856441 NET |
| NET enviado al colector | 0.015442822 NET |
| NET recibido por el pool | 0.293413619 NET |
| USDG recibido del pool | 226.094796 USDG |
| USDG repagado a Morpho | 194.034131 USDG |
| USDG enviado al pagador del gas | **32.060665 USDG** |
| Comisión nativa observada | **0.00003840668918 ETH** |

El colector recibió `floor(NET × 500 / 10000)`. La implementación NET consultada
contiene impuesto condicional según pares, exenciones y activación. Esto confirma
el tratamiento del recibo; no prueba que cualquier ruta o dirección soporte el
mismo impuesto hoy. No se recompiló ni comparó su runtime histórico completo.

La lectura `getReserves()` en el bloque **66.744.161** devolvió
`[335922719759, 434342007125, 1789786781]`. Las dos reservas coinciden exactamente
con las inferidas a partir de `Sync` y `Swap` del recibo. Aplicando la fórmula V2
con factor `997/1000` al NET efectivamente recibido se obtienen exactamente
`226094796` unidades mínimas de USDG. El factor es consistente con el intercambio;
no sustituye la verificación del código del pool.

Ignorar el impuesto daría **237.986092 USDG** con las mismas reservas: exageraría
el excedente en **11.891296 USDG**. El replay es aritmético, sin ejecución EVM de
los contratos de esa ruta. Los estados se solicitaron por número de bloque, sin
pruebas de estado ni fijación EIP-1898 por hash. El explorador truncó el calldata.

El excedente es anterior al gas. No se mezcló con la cotización ETH actual del
explorador: falta una conversión histórica ETH/USDG pertinente. USDG tampoco se
equipara automáticamente a USD. No se certifica beneficio neto del tercero.

En los 22 casos: **11** tienen salida USDG directa del pool principal bajo los
criterios conservadores del analizador, **9** tienen otros flujos o estructuras
complejas y **2** no muestran entrada USDG al liquidador y requieren inventario.
No se suma todo como ingresos. La clasificación describe flujos USDG, no propiedad
de direcciones, rentabilidad integral ni la totalidad de activos de cada estrategia.

## Corrección del laboratorio anterior

**Las cifras anteriores de gas total de la transacción deben sustituirse por las
de esta carpeta.** El montaje previo inyectaba el runtime del EntryPoint correcto,
pero escribía `1` en el slot `0` suponiendo que era el guard de reentrada.
`forge inspect EntryPoint storage-layout` confirma que `_status` está en el **slot 2**.
El slot 0 es la raíz de `deposits`. Un guard inicialmente cero permite ejecutar,
pero no reproduce su constructor y altera el coste de almacenamiento.

`reproduce_admission.py` corrige únicamente copias nuevas de los tests y del runner,
verifica el layout del compilador e inicializa/asserta el slot 2. El runtime sigue
teniendo el SHA-256 autenticado en el estudio anterior. Un nuevo test comprueba
también que el slot 0 permanezca intacto. Se repitieron siete recibos fríos.

| Escenario local | Gas anterior | Gas corregido | Débito paymaster ETH, sin cambio |
|---|---:|---:|---:|
| Éxito, callGas 1.800.000 | 455745 | **435845** | 0.001468690 |
| Éxito, callGas 600.000 | 455745 | **435845** | 0.001228690 |
| Caducidad L2 | 227095 | 207195 | 0.000638042 |
| Fallo de inventario DEX | 490058 | 470158 | 0.001111376 |
| Fallo de postOp | 516874 | 496974 | 0.001164982 |
| Sin gas de ejecución | 244271 | 224371 | 0.000554958 |
| Firma inválida, bundle revertido | 64046 | 46946 | 0 |

Precio local: 2 gwei. Mercado, DEX, fondos y ArbSys son fixtures; no se mide Nitro/DA
ni creación de cuenta dentro de `handleOps`. **435845 no es una estimación de gas
de la ruta real wsNET/sNET/NET/USDG.** El tercero usó otro ejecutor y su recibo
histórico consumió 568870 gas a otro precio. No son comparaciones de rendimiento.
La diferencia de coste por corregir el guard recae en la transacción del bundler;
el débito medido del paymaster no cambia. No sumar ambos pagos si pertenecen al
mismo operador consolidado.

## Admisión y capital

El paymaster anterior tiene depósito, pero cero stake. El test registra que su
validación lee/escribe el **slot propio 1** (`budgetRemaining`) y devuelve **64 bytes
de contexto**. ERC-7562 exige stake para ese acceso propio (`STO-031`) y prohíbe
contexto en un paymaster sin stake (`EREP-050`). Las reglas son de validación;
la consulta L2 en la ejecución no debe trasladarse a validación sin revisar esto.

Se inspeccionó el parser del bundler oficial v0.7, commit
`1868538f1d7678576291d2ecabb4443c797ad133`, para el acceso a storage, y el parser
actual `aae77140e5c2b1386d04eaeba2d23fc17a62bd87` para la regla de contexto.
URLs y hashes están en `evidence/bundler-reference.json`. **No se ejecutó el bundler**
ni su batería de conformidad. La especificación consultada sigue en estado Review;
la versión y política efectivas del proveedor deben confirmarse.

Los once tests nuevos prueban la frontera local: `handleOps` puede completar sin
stake; stake y depósito son distintos; el stake no paga gas; importes/delays
insuficientes y stake desbloqueado no satisfacen la política; el propietario y el
plazo controlan las retiradas. Se usan **0.02 ETH ficticios** como mínimo de prueba,
no como requisito anunciado por Robinhood o por un proveedor. El mínimo real
depende de la política correspondiente. Añadir stake resuelve esos límites locales;
no certifica todos los opcodes, reputación, cuentas nuevas o admisión del proveedor.

La política económica sigue siendo la de [SPONSORSHIP.md](../robinhood-aa-20261016/SPONSORSHIP.md).
Se necesitan fondos separados para depósito, stake inmovilizado, bundler,
despliegues, intentos fallidos y operación. El presupuesto conservador del contrato
no es financiación externa. Tampoco reserva por sí solo todas las operaciones
firmadas pendientes que distintos bundlers hayan simulado por separado: falta un
registro operativo de reservas y conciliación. No hay patrocinador acreditado ni
acuerdo que cubra esos costes sin obligaciones personales del fundador.

## Puertas pendientes para monetizar

| Puerta | Evidencia necesaria | Estado |
|---|---|---|
| Ruta completa | Calldata íntegro; estado y código fijados de mercado, oracle, wsNET, staking, NET y pool; balances antes/después en replay EVM | Pendiente |
| Coste NQC en Robinhood | Ciclo completo, política de cuenta, componente Nitro/DA, creación de cuenta cuando proceda | Pendiente |
| Bundler | Validación completa y estimación sin broadcast con EP v0.7; parámetros de stake y depósito; control de pendientes | Pendiente |
| Financiación | Fondos externos verificables y términos que cubran fallos, costes y ausencia de deuda personal | Pendiente |
| Captura | Registro prospectivo de todos los intentos, latencia, competencia, gas, tarifas y excedente neto realizado | Pendiente |

La vía inmediata es obtener los datos de replay y la simulación del proveedor;
después cerrar financiación y medir captura prospectiva. La consulta directa al
RPC público devolvió 403 en el trabajo anterior. En esta sesión se agotó el cupo
disponible del conector tras las lecturas históricas guardadas; no se abrieron
suscripciones ni se eludieron esas restricciones. No hay cotización actual acreditada.
No se puede proyectar un ingreso mensual a partir de esta muestra.

Valoración: **buena** evidencia histórica; **buena** mejora de rigor y corrección
del laboratorio; **bloqueante** la admisión/financiación no demostrada. Sería
**grave** presentar el excedente del tercero o del DEX sintético como ingresos NQC.
La evidencia actual no merece la calificación de producto monetizado excelente o supremo.

## Reproducción y resultado

Desde la raíz del repositorio, con Python estándar:

```bash
python migration/robinhood-route-admission-20261016/route_audit.py --out /tmp/route-report.json
python -m unittest discover -s migration/robinhood-route-admission-20261016 -p test_route_audit.py -v
python migration/robinhood-route-admission-20261016/compare_gas.py \
  --corrected migration/robinhood-route-admission-20261016/evidence/local/local-receipts.json \
  --out /tmp/gas-correction.json
```

Para recompilar, usar las dependencias, compiladores y binarios con los pins del
[trabajo anterior](../robinhood-aa-20261016/README.md). El destino debe ser nuevo y
estar fuera del repositorio. El script sólo usa una cadena Anvil en loopback:

```bash
python migration/robinhood-route-admission-20261016/reproduce_admission.py \
  --dependencies /ruta/dependencias \
  --foundry-bin /ruta/foundry-bin \
  --solc-019 /ruta/solc-0.8.19 \
  --solc-023 /ruta/solc-0.8.23 \
  --build /tmp/nqc-admission-fresh
```

Resultado final: **50 tests Solidity**, **18 tests Python del reconciliador**,
**9 tests de aislamiento**, siete recibos locales y verificación de 377 blobs
históricos. Cero fallos o skips en la corrida final. Rust no se modificó ni se
volvió a ejecutar. No se ejecutaron pruebas de bundler completo ni replay EVM real.

El primer test de storage falló porque se asumió que Foundry deduplicaba lecturas:
devolvió tres accesos al mismo slot. Se corrigió el test para exigir que todos
sean el slot 1 y conservar la comprobación de la escritura. El log inicial queda
guardado; la corrida final pasó. Los warnings restantes pertenecen a fixtures
recuperados, no a fallos de compilación. `MANIFEST.sha256` fija este expediente.

Fuentes primarias externas: [ERC-7562](https://eips.ethereum.org/EIPS/eip-7562),
[bundler oficial](https://github.com/eth-infinitism/bundler),
[explorador Robinhood](https://explorer.chain.robinhood.com/).
