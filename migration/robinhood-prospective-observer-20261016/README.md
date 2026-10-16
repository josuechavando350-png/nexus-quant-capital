# Observador prospectivo: primer piloto y límites encontrados

Se implementó y ejecutó un observador de lectura acotado para el mercado
wsNET/USDG de Morpho en Robinhood. **La instrumentación funciona, pero este
piloto no produjo una muestra de prestatarios ni una medida de captura rentable.**
Detectó dos limitaciones concretas: la selección por Borrow muy reciente quedó
vacía aunque el mercado conserva deuda, y la adquisición secuencial de datos
resultó demasiado lenta para el presupuesto hipotético de un segundo.

Las reglas y la implementación se publicaron **antes** del piloto en el commit
[`10255dcbc7136c262d25bb46688ed9552ba54ca5`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/10255dcbc7136c262d25bb46688ed9552ba54ca5),
rama `nqc/observer-protocol-20261016`. No se ampliaron ventanas, cambiaron
umbrales o eligieron prestatarios después de ver el resultado. El preflight
previo solo consultó cadena y cabecera; no conoció posiciones ni señales.

## Resultado real de esta ejecución

Periodo: **2026-10-16 05:30:55–05:32:24 UTC**, unos **89.23 segundos**
(23:30:55–23:32:24 del 15 de octubre en Ciudad de México).
Fuente única: endpoint público de demostración documentado por QuickNode.

| Medida | Resultado |
| --- | ---: |
| Bloques de selección, inclusive | 89,829,806–89,831,853 |
| Eventos Borrow en esa ventana/mercado | 0 |
| Prestatarios seleccionados | 0 |
| Rondas posteriores completadas | 3 |
| Estados individuales de prestatarios observados | 0 |
| Simulaciones de ruta prospectivas ejecutadas | 0 |
| Solicitudes del piloto | 32 |
| Solicitudes del preflight | 2 |
| Latencia RPC mínima / mediana / máxima del piloto | 2.197 / 2.638 / 3.903 s |
| Captura, inclusión y beneficio real | Sin medir |

Las rondas observaron los bloques **89,832,181**, **89,832,352** y **89,832,527**.
En las tres, el campo almacenado `totalBorrowAssets` fue **922,734.828954 USDG**.
El modelo de devengo con tasa y estado de cada ronda da entre 922,739.400691 y
922,741.085137 USDG; son magnitudes de deuda agregada, no beneficios disponibles.

La deuda agregada positiva junto con cero eventos recientes muestra que esta
regla de selección puede dejar fuera posiciones abiertas con anterioridad.
No conocemos en este piloto el número de prestatarios activos ni su salud.
Las tres rondas vacías no se cuentan como tres periodos sin oportunidades.
Los campos de captura y beneficio permanecen `null`, no cero.

Reunir mercado, oracle y tasa tras recibir la cabecera tardó **11.625, 11.062 y
11.658 segundos**. Incluye la comprobación de la cabecera anterior; no hubo
lecturas de posiciones ni simulaciones en esos tiempos. Entre cabeceras
observadas quedaron **170 y 174 bloques intermedios sin observar**. Los cocientes
entre diferencias de timestamp y altura equivalen a unos 99–103 ms por bloque
en esos dos intervalos; no miden latencia individual del secuenciador.

Estas mediciones pertenecen a este entorno, este endpoint y consultas
secuenciales. No son un SLA del proveedor ni demuestran que toda infraestructura
de Robinhood tenga esa latencia. **Este montaje no acredita ejecución dentro
del siguiente bloque.** No se consumió dinero para descubrirlo.

## Qué deja implementado

`read_rpc.py` limita métodos, destinos, intervalos, bytes, solicitudes y tiempo.
Las vistas usan hash de bloque con `requireCanonical`; un error de transporte
o proveedor detiene el lector, sin reintentos ni cambio de endpoint. No hay
claves, firmas, envío, suscripciones o procesos persistentes. El presupuesto de
240 segundos se comprueba antes de cada consulta; una consulta ya iniciada puede
añadir hasta su timeout de 20 segundos. Esta ejecución duró 89.23 segundos.

`observer.py` selecciona todos los prestatarios de los eventos de la ventana
fijada y congela la cohorte antes de leer su salud. Conserva un diario con hashes
encadenados, tiempos monotónicos y respuestas RPC originales. Contrasta las
cabeceras y los runtime Morpho/oracle/IRM contra la evidencia histórica, y exige
direcciones de fixtures sin código al comienzo.

`model.py` calcula deuda devengada, redondeos y margen de salud con la matemática
de Morpho fijada. La calibración reproduce el repago histórico de **194.034131
USDG** del caso de PR8. Es una comprobación del cálculo, no un candidato nuevo.
La tasa view del IRM y el precio son insumos observados; la traza de ruta sigue
siendo la comprobación necesaria de ejecutabilidad.

La ruta de candidatos prepara una cantidad determinista, registra el payload
antes de simular y prueba el estado observado y una hipótesis +1 segundo. Luego
contrasta el mismo payload con la siguiente cabecera observada. Mantiene su
deadline original: si ya pasó, clasifica el intervalo como no observado. Los
últimos candidatos quedan censurados al acabar la ejecución. También registra
descartes por capacidad y falta de tamaño válido.

**Esa ruta de candidatos pasó pruebas sintéticas, pero no se activó con datos
nuevos en este piloto.** Las simulaciones previstas son de ruta directa mediante
`debug_traceCall`, no del ciclo completo de cuenta abstracta/paymaster. Las
fixtures son overrides efímeros de tres direcciones propias; no se reemplaza el
protocolo ni ArbSys. No hubo ninguna traza remota prospectiva en esta ejecución.

`audit.py` verifica respuestas, diario, cohorte, orden temporal, estado por hash,
payloads, costes de ruta y resultados futuros. Separa rondas vacías, rechazos,
simulaciones fallidas, intervalos no observados y resultados censurados.
`diagnose_pilot.py` produce el diagnóstico posterior sin alterar la selección.

La sensibilidad económica conserva supuestos explícitos: 3000 USDG/ETH, haircut
del 10%, costes de infraestructura y prefund histórico como coste conservador
por éxito/fallo. No son cotizaciones ni costes completos prospectivos verificados.
No se calculó margen para candidatos reales porque no hubo candidatos observados.
Financiación acreditada y autorizaciones de producción permanecen en cero/falso.

## Prueba siguiente que exige la evidencia

Hay que formar un registro persistente de prestatarios a partir de eventos
anteriores independientes de sus resultados y reconciliarlo con posiciones
actuales. Mirar solo nuevas aperturas durante una ventana corta no cubre las
posiciones existentes. El registro deberá declarar cobertura, huecos de historial,
reorganizaciones y criterio de muestreo antes de evaluar salud o rentabilidad.

También hace falta medir adquisición de estado y simulación con acceso apto
para baja latencia. Con una cohorte no vacía y un presupuesto de datos medido,
el siguiente ensayo podrá evaluar supervivencia de candidatos. Después siguen
admisión completa de bundler, inclusión, costes AA/Nitro/DA, reparto del excedente
y financiación prepagada. No hay aún una tasa de éxito comercial defendible.

## Verificaciones y reproducción

**22 pruebas nuevas y 61 de regresión/aislamiento pasan: 83 Python en total.**
Incluyen límites RPC, errores sin reintento, ABI y redondeos, calibración histórica,
cohorte sin información futura, secuencia temporal, ausencia de señales, cohorte
vacía, payload conservado, huecos entre bloques y corrupción de evidencia.
Los casos sintéticos están identificados como tales y no se agregan al piloto.

Se preservan 377 blobs originales, 106 workflows deshabilitados y cero activos.
No hubo cambios Solidity/Rust ni una ejecución nueva de esas suites. Las suites
de regresión son las 16 de PR10, 20 de PR9, 16 de PR8 y nueve de aislamiento.

Desde la raíz del repo, sin red:

```bash
python -m unittest discover -s migration/robinhood-prospective-observer-20261016 -p 'test_*.py' -v
python migration/robinhood-prospective-observer-20261016/audit.py \
  migration/robinhood-prospective-observer-20261016/evidence/pilot --out /tmp/nqc-pilot-audit.json
python migration/robinhood-prospective-observer-20261016/diagnose_pilot.py \
  migration/robinhood-prospective-observer-20261016/evidence/pilot --out /tmp/nqc-pilot-diagnostics.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

`observer.py --out /directorio/nuevo --registration-commit COMMIT` hace una nueva
ejecución remota limitada. Para reproducir la implementación registrada, usar el
commit enlazado y comprobar `registration-sources.json`. Una nueva ejecución
observa otro periodo; no reproduce el estado de este piloto. No existe daemon
activo ni observación programada después de terminar este turno.

El diario detecta alteraciones respecto de sus hashes publicados; no prueba una
hora independiente ni estado EVM mediante pruebas criptográficas. Solo se usó
una fuente. `MANIFEST.sha256` autentica el paquete publicado, no certifica un
productor nuevo como si fuera el productor original de PFT/Census.

Fuentes primarias consultadas el 16 de octubre de 2026:

- [Robinhood: conexión, identificadores y límites de endpoints públicos](https://docs.robinhood.com/chain/connecting/).
- [QuickNode: eth_getLogs y endpoint público de ejemplo](https://www.quicknode.com/docs/robinhood/eth_getLogs).
- [QuickNode: eth_call](https://www.quicknode.com/docs/robinhood/eth_call).
- [Morpho fijado: devengo, salud y liquidación](https://github.com/morpho-org/morpho-blue/blob/8e26ca6a8dbc5089edcd67fb576248810fd2870a/src/Morpho.sol).
