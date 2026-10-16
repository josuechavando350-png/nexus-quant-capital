# Protocolo antes de observar los resultados

Este ensayo sigue al piloto vacío de PR11. Su objetivo es medir cobertura de
prestatarios y adquisición de estado, no ingresos ni supervivencia de una ruta.
Se publicarán código, política y hashes antes de la primera consulta del ensayo.

Selección: un solo mercado, wsNET/USDG de Morpho en Robinhood (4663). Se tomará
la primera cabecera actual, se restarán 64 bloques y se leerán **400,000 bloques
contiguos terminando en ese ancla**, en 40 tramos de 10,000. Los 64 bloques son
un buffer operativo; no una afirmación de finalidad. La ventana depende solo de
la primera altura recibida. No se sembrará con liquidaciones conocidas, ni se
ampliará tras ver cuentas, salud o resultados. Se incluirán todos los onBehalf
distintos de Borrow, sin ordenar por riesgo. Topes: 512 eventos, 128 bloques con
eventos y 64 prestatarios; un exceso detiene el ensayo sin recortar la muestra.

El registro guarda un prefijo contiguo tras verificar cada tramo y admite
continuación en otro directorio, conservando la versión anterior. Revalida su
último bloque de control antes de continuar. Un cambio de bloque invalida el
registro; no hay rollback automático. Una ejecución interrumpida conserva su
prefijo y no lo presenta como cobertura del objetivo completo. No hay certeza
de indexación desde el nacimiento del mercado, prueba criptográfica de todos
los logs ni segunda fuente. Una respuesta vacía del proveedor se registra como
tal, no como una prueba criptográfica de ausencia.

Después de terminar el objetivo, se congela la lista antes de consultar salud.
Se verifican parámetros de mercado y runtimes contra PR8. Se leen tres bloques
nuevos, con todas las posiciones congeladas, mercado, precio y tasa fijados por
hash con requireCanonical. Se calcula la proporción exacta de borrowShares
cubierta; igualdad con el total solo cubre deuda positiva en ese bloque, no toda
la historia ni futuras aperturas. Deuda, señales y beneficio son conceptos
separados; no hay trazas de rutas ni métrica de beneficio en este ensayo.

Lectura agrupada: hasta cuatro elementos por batch JSON-RPC, cada uno contado
contra el presupuesto y validado por ID. No se asume que el proveedor los
ejecute simultáneamente. La tasa depende del estado del mercado y se lee después.
En el primer bloque se repite la misma lectura secuencialmente y se exige igualdad
exacta. Orden fijo: batch y luego secuencial. Es una comparación pareada única,
sin aleatorización, sin separar caché, red o procesamiento del proveedor.
Las otras dos rondas solo usan batch. Se informa tiempo hasta reunir los datos,
desde su inicio y desde recibir la cabecera; no incluye envío/inclusión. El
presupuesto de 1 segundo es una hipótesis, no un SLA verificado.

Límites por ejecución: 512 métodos RPC, 900 segundos comprobados antes de cada
POST, hasta 20 segundos adicionales por petición ya iniciada, 2 MiB por respuesta
y 32 MiB acumulados. Sin paralelismo HTTP, reintentos, cambios de endpoint, firmas,
despliegue, claves o suscripciones. Ante error de proveedor se conserva la
evidencia y se termina. No hay daemon después de la ejecución.

Fuentes de interfaz consultadas antes del ensayo:

- https://www.quicknode.com/docs/robinhood/eth_getLogs
- https://www.quicknode.com/guides/robinhood/read-stock-tokens-data-onchain
- https://support.quicknode.com/articles/3261121056-understanding-the-10-000-block-range-limit-for-querying-logs-and-events
- https://www.quicknode.com/guides/quicknode-products/apis/guide-to-efficient-rpc-requests
- https://www.jsonrpc.org/specification
- https://docs.robinhood.com/chain/connecting/

Los límites de un endpoint de demostración pueden ser distintos de los de una
cuenta. Un rechazo no autoriza evadirlo ni prueba que falten oportunidades.
