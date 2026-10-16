# Protocolo previo: historial anterior y lectura en una llamada

Objetivo: ampliar la cobertura de deuda observable y comparar adquisición de
estado en el mercado wsNET/USDG de Morpho, Robinhood 4663. No se mide rentabilidad,
inclusión, supervivencia de una ruta, Nitro/DA ni financiación en este ensayo.
Se publican estas reglas, fuentes y hashes antes de consultar el proveedor.

## Ventana y selección

Fuente inmutable: registro de continuación de PR12, commit
`9dd86e13083c95a076793020635fc7d4fb3d5053`, bloques 89,446,281–89,851,226.
Se anteponen exactamente **400,000 bloques: 89,046,281–89,446,280**, 40 tramos
contiguos de 10,000. La elección depende exclusivamente del inicio del registro
anterior. Se conservan todos los Borrow onBehalf, sin seleccionar por salud,
resultado de liquidación o tamaño de deuda. No se cambia esta ventana después
de leer posiciones. Se revalida el último bloque de la fuente antes y después
de la ampliación; la unión exige igualdad exacta de la cabecera limítrofe.
Los enlaces hash se reconstruyen en una copia; los logs y cabeceras originales
no se alteran. Luego se extiende hacia delante hasta la primera cabecera actual
recibida en esa fase menos 64 bloques, sin saltar ningún intervalo.

Topes conjuntos: 512 eventos, 128 alturas con eventos, 64 prestatarios. Ante
exceso se detiene sin recortar cuentas. Cada fase acepta como máximo 40 tramos.
Un prefijo parcial se conserva y se etiqueta como incompleto. Un cambio del
bloque de control invalida la copia; no hay rollback automático. Los 64 bloques
son un buffer operativo, no una prueba de finalidad. Una fuente RPC y sus logs
no prueban completitud criptográfica ni indexación desde el nacimiento.

## Comparación de lectura

Se congela el conjunto tras terminar ambas ventanas y antes de consultar
posiciones. Se verifican los tres runtimes y los cinco parámetros del mercado
contra la evidencia de PR8. Se observan tres nuevas cabeceras diferentes,
posteriores al congelamiento. Cada pareja usa exactamente el mismo hash de
bloque con `requireCanonical`, y vuelve a comprobar su identidad canónica.

Métodos comparados:

- `batch`: hasta cuatro métodos por POST, mercado/precio/posiciones y después
  tasa dependiente del mercado, usando el lector sin cambios de PR12.
- `creation`: un `eth_call` con `to` omitido, gas máximo 2,000,000 y el initcode
  exacto de `lens-build.json`, seguido únicamente de las cuentas congeladas en
  ABI. El constructor devuelve mercado/precio/tasa/posiciones. Sus interacciones
  con los protocolos son `STATICCALL`. No hay state overrides, despliegue en la
  cadena, firma ni envío de una transacción. El resultado ABI no es un contrato
  destinado a producción. Si el endpoint no acepta esta lectura, se registra
  el rechazo y se detiene; no se cambia de proveedor ni se usa otro mecanismo.

Orden fijado: **creation→batch, batch→creation, creation→batch**. Se exige igualdad
exacta del estado y de sus derivaciones en cada pareja. No es una muestra
aleatoria ni permite atribuir causalmente tiempos a caché, transporte o nodo.
Se informa el tiempo desde iniciar cada lectura hasta disponer de sus datos y
desde recibir la cabecera hasta completar la primera/segunda lectura. No incluye
el chequeo canónico posterior, la adquisición previa de cabecera, inclusión o
envío. El umbral de 1,000 ms es una hipótesis de ingeniería, no un SLA de mercado.

El porcentaje de deuda usa borrowShares observadas/total del mismo bloque;
igualdad solo concilia deuda positiva en ese bloque. El recuento de señales usa
la regla de PR12 (margen de salud ≤100 bps), sin convertirlas en oportunidades
rentables. Se mantienen `realized_profit` y tasa de captura como `null`.

## Reproducción y límites

Solc 0.8.23 commit f704f362, optimizador 200, EVM Paris, sin CBOR ni hash de
metadata. `build_lens.py` verifica los bytes. Las pruebas con mocks, incluidas
las de escritura rechazada por STATICCALL, son evidencia local exclusivamente.

Máximo 512 métodos RPC y 900 segundos comprobados antes de cada POST, con hasta
20 segundos adicionales para una petición ya iniciada; 2 MiB por respuesta,
32 MiB acumulados. Un solo endpoint documentado, sin paralelismo HTTP,
reintentos, bypass de cuota, claves, suscripciones o ejecución financiera.
Los errores detienen el ensayo y se publican con los resultados parciales.

`audit_experiment.py` reconstruye ventanas, cohortes, estado y tiempos desde
respuestas crudas y journal encadenado. No sustituye una segunda fuente ni
pruebas de estado. El manifiesto de fuentes incluye dependencias heredadas.

Fuentes de interfaz consultadas antes de observar:

- https://ethereum.github.io/execution-apis/api/methods/eth_call/
- https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-eth
- https://eips.ethereum.org/EIPS/eip-214
- https://www.quicknode.com/docs/robinhood/eth_getLogs
- https://www.quicknode.com/guides/robinhood/read-stock-tokens-data-onchain
- https://docs.robinhood.com/chain/connecting/
