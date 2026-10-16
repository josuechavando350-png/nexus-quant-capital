# Más historia observable y lectura de estado en una llamada

**La cobertura de deuda llega a 16.804189% y la lectura de las mismas 23 cuentas
baja de 23.20–26.93 s a 2.97–3.35 s en tres comparaciones reales.** Sigue sin
cumplirse el objetivo hipotético de un segundo. No se encontraron candidatos
en los tres bloques observados; el 83.20% de deuda restante sigue fuera de la
cohorte. Este resultado no demuestra ingresos ni ausencia de oportunidades.

La ampliación parte de PR12, commit `9dd86e13083c95a076793020635fc7d4fb3d5053`.
El protocolo se publicó en
[`ba730e532ce93c983f5aa09c65a4a54fa6957c5b`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/ba730e532ce93c983f5aa09c65a4a54fa6957c5b)
antes de la primera consulta. Los 19 archivos fijados en
`registration-sources.json` permanecen idénticos, incluida la política, el lector,
su bytecode, las pruebas y el auditor. Las demás dependencias anteriores quedan
fijadas por el commit base, sin cambios. `summarize.py` es presentación añadida
después del registro y no interviene en selección o captura.

## Resultado del índice

Captura: **16 de octubre de 2026, 06:42:58–06:51:31 UTC** (00:42:58–00:51:31
en Ciudad de México), **512.82 segundos**. Se hicieron **256 métodos RPC en
176 peticiones HTTP, sin errores**. La auditoría offline reconstruyó el registro,
las lecturas y las comparaciones desde las respuestas originales.

| Medida | Resultado |
| --- | ---: |
| Intervalo anterior añadido | 89,046,281–89,446,280 |
| Bloques anteriores / eventos Borrow | 400,000 / 22 |
| Cuentas nuevas halladas en esa historia | 12 |
| Actualización posterior al checkpoint de PR12 | 26,255 bloques / 1 Borrow / 1 cuenta nueva |
| Intervalo acumulado, inclusive | 89,046,281–89,877,481 |
| Bloques / tramos / eventos acumulados | 831,201 / 84 / 38 |
| Cuentas congeladas / con deuda positiva | 23 / 19 |
| Cobertura de borrowShares, en los tres bloques | 16.8041891461% |
| Cobertura de las diez cuentas anteriores en esos mismos bloques | 10.1426100258% |
| Aporte de las trece cuentas nuevas en esos mismos bloques | 6.6615791202 puntos porcentuales |
| Señales dentro del umbral de 100 bps, por bloque | 0 |
| Posiciones calculadas como no saludables, por bloque | 0 |
| Rutas simuladas / transacciones enviadas en este ensayo | 0 / 0 |
| Beneficio propio y tasa de captura | Sin medir |

Numerador y denominador de cobertura: **144,609,107,071,935,320 /
860,553,911,973,656,785 borrowShares**. Quedan sin cubrir
715,944,804,901,721,465 participaciones. El porcentaje anterior de PR12
(10.1447045744%) correspondía a otro estado; la comparación de arriba recalcula
ambas cohortes en el mismo bloque para no atribuir cambios del mercado al índice.

La deuda almacenada del mercado fue **923,108.830158 USDG**; la deuda devengada
de las cuentas observadas sumó **155,128.922206–155,129.508574 USDG**.
Son obligaciones de prestatarios, no beneficio disponible. El menor margen de
salud fue 807 bps en cada bloque, frente al umbral de señal de 100 bps.
Las cuatro cuentas sin deuda permanecen en el registro.

Se conservaron byte por byte el registro fuente y sus logs/cabeceras. La unión
reconstruye exclusivamente los enlaces entre tramos en una copia nueva. El
registro anterior no se sobrescribe. No hay índice completo desde el origen del
mercado ni cobertura de nuevas aperturas posteriores al checkpoint.

## Lectura comparada sobre estado real

`NqcStateReadLens.sol` es un constructor usado mediante `eth_call` sin `to`.
Lee parámetros, mercado, precio, tasa y posiciones mediante `STATICCALL` y
devuelve un array ABI. No se despliega en la cadena ni se envía una transacción.
El initcode exacto se compila con solc 0.8.23; cada consulta añade únicamente las
cuentas congeladas y usa un límite de 2,000,000 gas en la simulación de lectura.
Ese límite no es una medición del coste del ciclo comercial NQC.

| Bloque | Orden fijado | Una llamada, s | Batch, s | Batch / una llamada |
| --- | --- | ---: | ---: | ---: |
| 89,878,023 | Una llamada → batch | 2.974 | 23.796 | 8.00 |
| 89,878,373 | Batch → una llamada | 3.348 | 23.203 | 6.93 |
| 89,878,726 | Una llamada → batch | 3.074 | 26.933 | 8.76 |

En las tres parejas coinciden exactamente mercado, precio, tasa, posiciones,
cobertura y cálculos de salud, fijados por hash con `requireCanonical`.
Las entradas pasan de **26 métodos RPC en ocho POST** a **un método en un POST**;
la comprobación canónica posterior requiere otro POST en ambos casos.

Los tiempos anteriores terminan al disponer de las entradas y excluyen esa
comprobación canónica. En las rondas donde la nueva lectura fue primero,
transcurrieron **2.978 y 3.076 s desde recibir la cabecera** hasta completar
las entradas. La ronda con batch primero tardó 23.206 s. Ninguna cumple 1,000 ms.
El bloque observado estaba 542, 892 y 1,245 alturas después del checkpoint,
respectivamente; esos intervalos posteriores no se presentan como indexados.

Son tres parejas de una única cohorte y un único proveedor, con orden previo,
sin aleatorización ni aislamiento de caché, red o carga. No son un SLA ni una
distribución de latencias de producción. Todas las respuestas HTTP del ensayo
tardaron al menos 2.342 s y su mediana fue 2.782 s; no se midió por separado qué
parte corresponde al transporte o al nodo. No se infiere de aquí inclusión,
prioridad de ejecución o supervivencia de oportunidades.

## Decisión y límites comerciales

La mejora de adquisición está comprobada en esta muestra y permite observar
más cuentas con menos viajes RPC. La cobertura sigue siendo insuficiente para
concluir si este mercado ofrece oportunidades capturables por NQC. El siguiente
lote debe ampliar historia anterior manteniendo la cohorte y conciliarla otra
vez; la optimización de transporte requiere un ensayo independiente y previo.

Las pruebas históricas de ciclo NQC y costes Nitro/DA de PR8–PR9 conservan su
alcance histórico. Este ensayo no las convierte en captura prospectiva. Siguen
sin demostrarse frecuencia rentable, supervivencia, admisión de producción del
bundler y financiación comercial del patrocinio. No se han comprometido fondos,
contratado servicios ni creado ingresos. USDG no se equipara automáticamente a USD.

La confianza depende de una sola fuente RPC, sin pruebas criptográficas de
estado/logs ni nodo independiente. Los hashes detectan alteraciones respecto
del paquete publicado; no certifican por sí solos la verdad del proveedor o la
hora de captura. El buffer de 64 bloques no demuestra finalidad.

## Verificación y reproducción

**72 pruebas Python aprobadas**: 16 nuevas, 25 de registro, 22 del observador y
nueve de aislamiento. **11 pruebas Solidity aprobadas** con mocks: orden/límites,
identidad, salida ABI, propagación de errores y rechazo de escrituras desde las
vistas. El gas de esos mocks no es una cotización de Robinhood. Se verificaron
377 blobs originales, 106 workflows deshabilitados y cero activos. No cambió
Rust ni se repitieron suites ajenas al cambio.

Desde la raíz, sin consultas de red:

```bash
python -m unittest discover -s migration/robinhood-history-backfill-20261016 -p 'test_experiment.py' -v
python migration/robinhood-history-backfill-20261016/build_lens.py --solc /ruta/solc-0.8.23
python migration/robinhood-history-backfill-20261016/audit_experiment.py \
  migration/robinhood-history-backfill-20261016/evidence/pilot --out /tmp/nqc-history-audit.json
python migration/robinhood-history-backfill-20261016/summarize.py \
  migration/robinhood-history-backfill-20261016/evidence/pilot --out /tmp/nqc-history-summary.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Para Solidity, copiar `NqcStateReadLens.sol` y `test/` a un directorio de build
nuevo, configurar Foundry con solc 0.8.23, optimizador 200, EVM Paris y metadata
CBOR deshabilitada, y ejecutar `forge test -vv`. No se modifica código archivado.

La captura real usó `run_experiment.py --out DIRECTORIO_NUEVO
--registration-commit ba730e532ce93c983f5aa09c65a4a54fa6957c5b`. Repetir ese
comando vuelve a consultar la ventana fija original; **no sirve para avanzar a
otra ventana sin registrar una nueva política y fuente**. `CONTINUITY.md`
identifica el siguiente punto de partida. El proceso de captura terminó; las
continuaciones horarias son tareas separadas, no un daemon de mercado continuo.

`evidence/provenance.json`, `pilot-report.json`, `pilot-summary.json` y
`MANIFEST.sha256` conservan procedencia, datos derivados y hashes del paquete.
